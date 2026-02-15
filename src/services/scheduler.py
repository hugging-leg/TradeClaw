"""
调度服务 - 使用 APScheduler 实现可靠的任务调度

功能：
- 定时任务调度（Cron 表达式）
- 一次性延迟任务
- 任务持久化（可选）
- 任务冲突检测
- 交易日历感知（使用 time_utils）
"""

import asyncio
from src.utils.logging_config import get_logger
from typing import Dict, Any, Optional, Callable, Awaitable, List
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from enum import Enum
import pytz

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.events import (
    EVENT_JOB_EXECUTED,
    EVENT_JOB_ERROR,
    EVENT_JOB_MISSED,
    JobExecutionEvent
)

# 使用统一的时间工具
from src.utils.time_utils import (
    is_trading_day as _is_trading_day,
    is_market_open as _is_market_open,
    get_next_trading_day,
    XCALS_AVAILABLE
)

logger = get_logger(__name__)


class JobPriority(Enum):
    """任务优先级"""
    CRITICAL = 0   # 紧急任务（如风险告警）
    HIGH = 1       # 高优先级（如手动触发的分析）
    NORMAL = 2     # 普通优先级（如定时分析）
    LOW = 3        # 低优先级（如后台检查）


@dataclass
class ScheduledJob:
    """调度任务定义"""
    id: str
    name: str
    func: Callable[..., Awaitable[Any]]
    trigger_type: str  # 'cron', 'date', 'interval'
    trigger_args: Dict[str, Any]
    priority: JobPriority = JobPriority.NORMAL
    require_market_open: bool = False  # 是否要求市场开放
    require_trading_day: bool = True   # 是否要求交易日
    max_instances: int = 1             # 最大并发实例数
    coalesce: bool = True              # 是否合并错过的执行
    metadata: Dict[str, Any] = field(default_factory=dict)


class TradingScheduler:
    """
    交易调度服务

    特点：
    - 基于 APScheduler 的可靠调度
    - 交易日历感知（自动跳过非交易日）
    - 任务优先级支持
    - 任务执行追踪
    - 优雅的启停

    使用示例：
        scheduler = TradingScheduler(timezone='US/Eastern')
        await scheduler.start()

        # 添加每日定时任务
        scheduler.add_cron_job(
            job_id='daily_analysis',
            func=run_daily_analysis,
            hour=9, minute=35,
            require_trading_day=True
        )

        # 添加一次性延迟任务
        scheduler.add_delayed_job(
            job_id='llm_scheduled_123',
            func=run_analysis,
            delay_hours=2.5,
            priority=JobPriority.HIGH
        )
    """

    def __init__(
        self,
        timezone: str = 'US/Eastern',
        exchange: str = 'XNYS'
    ):
        self.timezone = pytz.timezone(timezone)
        self.exchange = exchange
        self._timezone_str = timezone

        # 初始化调度器
        self._scheduler = AsyncIOScheduler(
            timezone=self.timezone,
            jobstores={'default': MemoryJobStore()},
            job_defaults={
                'coalesce': True,
                'max_instances': 1,
                'misfire_grace_time': 60  # 错过后60秒内仍执行
            }
        )

        # 任务追踪
        self._jobs: Dict[str, ScheduledJob] = {}
        self._execution_history: List[Dict[str, Any]] = []
        self._max_history = 100

        # 状态
        self._started = False

        # 注册事件监听
        self._scheduler.add_listener(
            self._on_job_executed,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED
        )

    async def start(self) -> bool:
        """启动调度器"""
        if self._started:
            logger.warning("调度器已在运行")
            return True

        try:
            self._scheduler.start()
            self._started = True
            logger.info("交易调度器已启动")
            return True
        except Exception as e:
            logger.error(f"启动调度器失败: {e}")
            return False

    async def stop(self, wait: bool = True) -> bool:
        """停止调度器"""
        if not self._started:
            return True

        try:
            self._scheduler.shutdown(wait=wait)
            self._started = False
            logger.info("交易调度器已停止")
            return True
        except Exception as e:
            logger.error(f"停止调度器失败: {e}")
            return False

    def add_cron_job(
        self,
        job_id: str,
        func: Callable[..., Awaitable[Any]],
        hour: int,
        minute: int,
        day_of_week: str = 'mon-fri',
        require_trading_day: bool = True,
        require_market_open: bool = False,
        priority: JobPriority = JobPriority.NORMAL,
        kwargs: Dict[str, Any] = None
    ) -> bool:
        """
        添加 Cron 定时任务

        Args:
            job_id: 任务唯一标识
            func: 异步执行函数
            hour: 小时 (0-23)
            minute: 分钟 (0-59)
            day_of_week: 星期 (默认周一至周五)
            require_trading_day: 是否要求交易日
            require_market_open: 是否要求市场开放
            priority: 任务优先级
            kwargs: 传递给 func 的参数

        Returns:
            是否添加成功
        """
        try:
            # 包装函数以添加交易日检查
            wrapped_func = self._wrap_with_trading_check(
                func,
                require_trading_day,
                require_market_open,
                job_id
            )

            trigger = CronTrigger(
                hour=hour,
                minute=minute,
                day_of_week=day_of_week,
                timezone=self.timezone
            )

            self._scheduler.add_job(
                wrapped_func,
                trigger=trigger,
                id=job_id,
                name=job_id,
                kwargs=kwargs or {},
                replace_existing=True
            )

            # 记录任务
            self._jobs[job_id] = ScheduledJob(
                id=job_id,
                name=job_id,
                func=func,
                trigger_type='cron',
                trigger_args={
                    'hour': hour,
                    'minute': minute,
                    'day_of_week': day_of_week
                },
                priority=priority,
                require_market_open=require_market_open,
                require_trading_day=require_trading_day
            )

            logger.info(
                f"添加 Cron 任务: {job_id} "
                f"(每 {day_of_week} {hour:02d}:{minute:02d})"
            )
            return True

        except Exception as e:
            logger.error(f"添加 Cron 任务失败 {job_id}: {e}")
            return False

    def add_delayed_job(
        self,
        job_id: str,
        func: Callable[..., Awaitable[Any]],
        delay_seconds: float = None,
        delay_hours: float = None,
        run_at: datetime = None,
        priority: JobPriority = JobPriority.NORMAL,
        require_trading_day: bool = False,
        kwargs: Dict[str, Any] = None
    ) -> bool:
        """
        添加一次性延迟任务

        Args:
            job_id: 任务唯一标识
            func: 异步执行函数
            delay_seconds: 延迟秒数
            delay_hours: 延迟小时数
            run_at: 指定执行时间 (优先于 delay)
            priority: 任务优先级
            require_trading_day: 是否要求交易日
            kwargs: 传递给 func 的参数

        Returns:
            是否添加成功
        """
        try:
            # 计算执行时间（统一使用 UTC）
            now_utc = datetime.now(pytz.UTC)
            if run_at:
                run_time = run_at
                # 确保是 aware datetime
                if run_time.tzinfo is None:
                    run_time = run_time.replace(tzinfo=pytz.UTC)
            elif delay_hours is not None:
                run_time = now_utc + timedelta(hours=delay_hours)
            elif delay_seconds is not None:
                run_time = now_utc + timedelta(seconds=delay_seconds)
            else:
                raise ValueError("必须指定 delay_seconds, delay_hours 或 run_at")

            # 如果要求交易日，调整到下一个交易日
            if require_trading_day:
                run_time = self._adjust_to_trading_day(run_time)

            # 包装函数
            wrapped_func = self._wrap_with_trading_check(
                func,
                require_trading_day,
                require_market_open=False,
                job_id=job_id
            )

            trigger = DateTrigger(run_date=run_time, timezone=self.timezone)

            self._scheduler.add_job(
                wrapped_func,
                trigger=trigger,
                id=job_id,
                name=job_id,
                kwargs=kwargs or {},
                replace_existing=True
            )

            # 记录任务
            self._jobs[job_id] = ScheduledJob(
                id=job_id,
                name=job_id,
                func=func,
                trigger_type='date',
                trigger_args={'run_date': run_time.isoformat()},
                priority=priority,
                require_trading_day=require_trading_day
            )

            logger.info(f"添加延迟任务: {job_id} (执行时间: {run_time})")
            return True

        except Exception as e:
            logger.error(f"添加延迟任务失败 {job_id}: {e}")
            return False

    def add_interval_job(
        self,
        job_id: str,
        func: Callable[..., Awaitable[Any]],
        minutes: int = None,
        hours: int = None,
        require_market_open: bool = True,
        priority: JobPriority = JobPriority.LOW,
        kwargs: Dict[str, Any] = None
    ) -> bool:
        """
        添加周期性任务

        Args:
            job_id: 任务唯一标识
            func: 异步执行函数
            minutes: 间隔分钟数
            hours: 间隔小时数
            require_market_open: 是否要求市场开放
            priority: 任务优先级
            kwargs: 传递给 func 的参数

        Returns:
            是否添加成功
        """
        try:
            # 包装函数
            wrapped_func = self._wrap_with_trading_check(
                func,
                require_trading_day=True,
                require_market_open=require_market_open,
                job_id=job_id
            )

            trigger = IntervalTrigger(
                minutes=minutes or 0,
                hours=hours or 0,
                timezone=self.timezone
            )

            self._scheduler.add_job(
                wrapped_func,
                trigger=trigger,
                id=job_id,
                name=job_id,
                kwargs=kwargs or {},
                replace_existing=True
            )

            interval_str = f"{hours}h" if hours else f"{minutes}m"
            logger.info(f"添加周期任务: {job_id} (每 {interval_str})")
            return True

        except Exception as e:
            logger.error(f"添加周期任务失败 {job_id}: {e}")
            return False

    def remove_job(self, job_id: str) -> bool:
        """移除任务"""
        try:
            self._scheduler.remove_job(job_id)
            if job_id in self._jobs:
                del self._jobs[job_id]
            logger.info(f"已移除任务: {job_id}")
            return True
        except Exception as e:
            logger.debug(f"移除任务失败 {job_id}: {e}")
            return False

    def pause_job(self, job_id: str) -> bool:
        """暂停任务"""
        try:
            self._scheduler.pause_job(job_id)
            logger.info(f"已暂停任务: {job_id}")
            return True
        except Exception as e:
            logger.error(f"暂停任务失败 {job_id}: {e}")
            return False

    def resume_job(self, job_id: str) -> bool:
        """恢复任务"""
        try:
            self._scheduler.resume_job(job_id)
            logger.info(f"已恢复任务: {job_id}")
            return True
        except Exception as e:
            logger.error(f"恢复任务失败 {job_id}: {e}")
            return False

    def get_job_info(self, job_id: str) -> Optional[Dict[str, Any]]:
        """获取任务信息"""
        job = self._scheduler.get_job(job_id)
        if not job:
            return None

        scheduled_job = self._jobs.get(job_id)
        return {
            'id': job.id,
            'name': job.name,
            'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
            'trigger': str(job.trigger),
            'priority': scheduled_job.priority.name if scheduled_job else 'UNKNOWN',
            'require_trading_day': scheduled_job.require_trading_day if scheduled_job else False,
            'require_market_open': scheduled_job.require_market_open if scheduled_job else False
        }

    def get_all_jobs(self) -> List[Dict[str, Any]]:
        """获取所有任务"""
        jobs = []
        for job in self._scheduler.get_jobs():
            info = self.get_job_info(job.id)
            if info:
                jobs.append(info)
        return jobs

    def is_trading_day(self, date: datetime = None) -> bool:
        """检查是否为交易日（使用 time_utils）"""
        try:
            return _is_trading_day(
                dt=date,
                exchange=self.exchange,
                timezone=self._timezone_str
            )
        except Exception as e:
            logger.warning(f"检查交易日失败，默认允许执行: {e}")
            return True

    def is_market_open(self) -> bool:
        """检查市场是否开放（使用 time_utils）"""
        try:
            return _is_market_open(
                exchange=self.exchange,
                timezone=self._timezone_str
            )
        except Exception as e:
            logger.warning(f"检查市场状态失败，默认允许执行: {e}")
            return True

    def get_next_market_open(self) -> Optional[datetime]:
        """获取下一个市场开放时间"""
        try:
            from src.utils.time_utils import get_next_market_open
            return get_next_market_open(
                exchange=self.exchange,
                timezone=self._timezone_str
            )
        except Exception as e:
            logger.warning(f"获取下一个市场开放时间失败: {e}")
            return None

    def get_status(self) -> Dict[str, Any]:
        """获取调度器状态"""
        return {
            'running': self._started,
            'timezone': str(self.timezone),
            'exchange': self.exchange,
            'calendar_available': XCALS_AVAILABLE,
            'is_trading_day': self.is_trading_day(),
            'is_market_open': self.is_market_open(),
            'total_jobs': len(self._scheduler.get_jobs()),
            'jobs': self.get_all_jobs(),
            'recent_executions': self._execution_history[-10:]
        }

    def _wrap_with_trading_check(
        self,
        func: Callable[..., Awaitable[Any]],
        require_trading_day: bool,
        require_market_open: bool,
        job_id: str
    ) -> Callable[..., Awaitable[Any]]:
        """包装函数以添加交易日/市场开放检查"""

        async def wrapper(*args, **kwargs):
            # 检查交易日
            if require_trading_day and not self.is_trading_day():
                logger.debug(f"跳过任务 {job_id}: 非交易日")
                return None

            # 检查市场开放
            if require_market_open and not self.is_market_open():
                logger.debug(f"跳过任务 {job_id}: 市场未开放")
                return None

            # 执行原函数
            return await func(*args, **kwargs)

        return wrapper

    def _adjust_to_trading_day(self, dt: datetime) -> datetime:
        """调整时间到下一个交易日（使用 time_utils）"""
        try:
            next_day = get_next_trading_day(
                dt=dt,
                exchange=self.exchange,
                timezone=self._timezone_str
            )
            # 保留原始时间，只更新日期
            return dt.replace(
                year=next_day.year,
                month=next_day.month,
                day=next_day.day
            )
        except Exception as e:
            logger.warning(f"调整到交易日失败: {e}")
            return dt

    def _on_job_executed(self, event: JobExecutionEvent):
        """任务执行事件处理"""
        execution_record = {
            'job_id': event.job_id,
            'scheduled_time': event.scheduled_run_time.isoformat() if event.scheduled_run_time else None,
            'executed_at': datetime.now(pytz.UTC).isoformat(),
            'success': event.exception is None,
            'error': str(event.exception) if event.exception else None
        }

        self._execution_history.append(execution_record)

        # 限制历史记录数量
        if len(self._execution_history) > self._max_history:
            self._execution_history = self._execution_history[-self._max_history:]

        if event.exception:
            logger.error(f"任务 {event.job_id} 执行失败: {event.exception}")
        else:
            logger.debug(f"任务 {event.job_id} 执行成功")


# 便捷函数
def create_scheduler(
    timezone: str = 'US/Eastern',
    exchange: str = 'XNYS'
) -> TradingScheduler:
    """创建交易调度器"""
    return TradingScheduler(timezone=timezone, exchange=exchange)

