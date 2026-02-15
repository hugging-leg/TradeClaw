"""
调度器 Mixin — 为 TradingSystem 提供 APScheduler 能力

职责：
- APScheduler 实例管理（初始化、启动、停止）
- Cron / Interval / Delayed 任务的增删改查
- 交易日 / 市场开放 guard 装饰
- 任务执行历史记录（数据库持久化 + 内存热缓存）
- Job 序列化（供 API 返回）

设计：
- 作为 Mixin 被 TradingSystem 继承，不独立实例化
- 所有 APScheduler 细节封装在此，TradingSystem 只关注业务逻辑
- 交易日历检查复用 time_utils，不重复实现
- 使用 SQLAlchemyJobStore 持久化任务，重启后恢复用户动态添加的任务
- 执行历史持久化到 SchedulerJobExecution 表
"""

from __future__ import annotations

import functools
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Callable, Coroutine, Dict, List, Optional

import pytz
from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MISSED,
    JobExecutionEvent,
)
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import settings
from src.utils.logging_config import get_logger
from src.utils.time_utils import (
    get_next_trading_day,
    is_market_open as check_market_open,
    is_trading_day as check_trading_day,
    XCALS_AVAILABLE,
)
from src.utils.timezone import utc_now

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Standalone helper（不依赖实例状态，可供外部使用）
# ---------------------------------------------------------------------------

def trading_day_guard(
    func: Callable[..., Coroutine],
    *,
    require_trading_day: bool = True,
    require_market_open: bool = False,
    exchange: str = "XNYS",
    timezone_str: str = "US/Eastern",
    job_id: str = "",
) -> Callable[..., Coroutine]:
    """
    装饰器：为 APScheduler 回调添加交易日 / 市场开放检查。

    如果条件不满足，静默跳过执行并返回 None。
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        if require_trading_day:
            try:
                if not check_trading_day(exchange=exchange, timezone=timezone_str):
                    logger.debug("跳过任务 %s: 非交易日", job_id)
                    return None
            except Exception as exc:
                logger.warning("交易日检查失败，默认执行 %s: %s", job_id, exc)

        if require_market_open:
            try:
                if not check_market_open(exchange=exchange, timezone=timezone_str):
                    logger.debug("跳过任务 %s: 市场未开放", job_id)
                    return None
            except Exception as exc:
                logger.warning("市场状态检查失败，默认执行 %s: %s", job_id, exc)

        return await func(*args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# SchedulerMixin
# ---------------------------------------------------------------------------

class SchedulerMixin:
    """
    APScheduler Mixin — 通过多继承注入到 TradingSystem。

    使用方需要在 __init__ 中调用 ``_init_scheduler()``，
    并在 start / stop 中分别调用 ``_start_scheduler()`` / ``_stop_scheduler()``。

    持久化：
    - 任务存储使用 SQLAlchemyJobStore（与业务共享同一数据库）
    - 执行历史写入 scheduler_job_executions 表
    - 内存中保留最近 N 条执行记录作为热缓存（API 快速查询）

    Attributes set by this mixin:
        _scheduler: AsyncIOScheduler
        _tz: pytz timezone
        _exchange: str
        _job_history_cache: deque  (内存热缓存)
    """

    # ------------------------------------------------------------------
    # 初始化 / 生命周期
    # ------------------------------------------------------------------

    def _init_scheduler(self) -> None:
        """初始化 APScheduler 实例（在 __init__ 中调用）"""
        self._tz = pytz.timezone(settings.trading_timezone)
        self._exchange: str = settings.exchange

        # APScheduler 3.x 的 SQLAlchemyJobStore 使用同步 engine，
        # 直接从 settings 获取同步 database URL。
        db_url = settings.get_database_url()

        self._scheduler = AsyncIOScheduler(
            timezone=self._tz,
            jobstores={
                "default": SQLAlchemyJobStore(url=db_url, tablename="apscheduler_jobs"),
            },
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": settings.scheduler_misfire_grace_time,
            },
        )
        self._scheduler.add_listener(
            self._on_job_event,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED,
        )

        # 内存热缓存（有界 deque，不会无限增长）
        self._job_history_cache: deque[Dict[str, Any]] = deque(
            maxlen=settings.scheduler_max_history,
        )

    def _start_scheduler(self) -> None:
        """启动 APScheduler（在 start() 中调用）"""
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("APScheduler 已启动 (jobstore: SQLAlchemy)")

    def _stop_scheduler(self, wait: bool = True) -> None:
        """停止 APScheduler（在 stop() 中调用）"""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
            logger.info("APScheduler 已停止")

    # ------------------------------------------------------------------
    # Internal — 公共添加逻辑（消除 add_cron/interval/delayed 的重复）
    # ------------------------------------------------------------------

    def _add_job(
        self,
        job_id: str,
        func: Callable[..., Coroutine],
        trigger,
        *,
        require_trading_day: bool = True,
        require_market_open: bool = False,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        统一的任务添加入口。

        封装 trading_day_guard 包装 + scheduler.add_job + 异常处理。
        """
        try:
            wrapped = trading_day_guard(
                func,
                require_trading_day=require_trading_day,
                require_market_open=require_market_open,
                exchange=self._exchange,
                timezone_str=settings.trading_timezone,
                job_id=job_id,
            )
            self._scheduler.add_job(
                wrapped,
                trigger=trigger,
                id=job_id,
                name=job_id,
                kwargs=kwargs or {},
                replace_existing=True,
            )
            return True
        except Exception as e:
            logger.error("添加任务失败 %s: %s", job_id, e)
            return False

    # ------------------------------------------------------------------
    # Public — 任务管理（供 API / 内部注册 共用）
    # ------------------------------------------------------------------

    def add_cron_job(
        self,
        job_id: str,
        func: Callable[..., Coroutine],
        hour: int,
        minute: int,
        day_of_week: str = "mon-fri",
        require_trading_day: bool = True,
        require_market_open: bool = False,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """添加 Cron 定时任务。"""
        trigger = CronTrigger(
            hour=hour, minute=minute, day_of_week=day_of_week, timezone=self._tz,
        )
        success = self._add_job(
            job_id, func, trigger,
            require_trading_day=require_trading_day,
            require_market_open=require_market_open,
            kwargs=kwargs,
        )
        if success:
            logger.info("添加 Cron 任务: %s (%s %02d:%02d)", job_id, day_of_week, hour, minute)
        return success

    def add_interval_job(
        self,
        job_id: str,
        func: Callable[..., Coroutine],
        minutes: Optional[int] = None,
        hours: Optional[int] = None,
        require_trading_day: bool = True,
        require_market_open: bool = False,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """添加 Interval 周期任务。"""
        trigger = IntervalTrigger(
            minutes=minutes or 0, hours=hours or 0, timezone=self._tz,
        )
        success = self._add_job(
            job_id, func, trigger,
            require_trading_day=require_trading_day,
            require_market_open=require_market_open,
            kwargs=kwargs,
        )
        if success:
            interval_str = f"{hours}h" if hours else f"{minutes}m"
            logger.info("添加 Interval 任务: %s (每 %s)", job_id, interval_str)
        return success

    def add_delayed_job(
        self,
        job_id: str,
        func: Callable[..., Coroutine],
        delay_seconds: Optional[float] = None,
        delay_hours: Optional[float] = None,
        run_at: Optional[datetime] = None,
        require_trading_day: bool = False,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        添加一次性延迟任务。

        必须指定 delay_seconds / delay_hours / run_at 之一。
        """
        try:
            now = utc_now()
            if run_at is not None:
                run_time = run_at if run_at.tzinfo else run_at.replace(tzinfo=pytz.UTC)
            elif delay_hours is not None:
                run_time = now + timedelta(hours=delay_hours)
            elif delay_seconds is not None:
                run_time = now + timedelta(seconds=delay_seconds)
            else:
                raise ValueError("Must specify delay_seconds, delay_hours, or run_at")

            if require_trading_day:
                run_time = self._adjust_to_trading_day(run_time)

            trigger = DateTrigger(run_date=run_time, timezone=self._tz)
            success = self._add_job(
                job_id, func, trigger,
                require_trading_day=require_trading_day,
                require_market_open=False,
                kwargs=kwargs,
            )
            if success:
                logger.info("添加延迟任务: %s (执行时间: %s)", job_id, run_time.isoformat())
            return success

        except Exception as e:
            logger.error("添加延迟任务失败 %s: %s", job_id, e)
            return False

    def remove_job(self, job_id: str) -> bool:
        """移除任务"""
        try:
            self._scheduler.remove_job(job_id)
            logger.info("已移除任务: %s", job_id)
            return True
        except Exception as e:
            logger.debug("移除任务失败 %s: %s", job_id, e)
            return False

    def pause_job(self, job_id: str) -> bool:
        """暂停任务"""
        try:
            self._scheduler.pause_job(job_id)
            logger.info("已暂停任务: %s", job_id)
            return True
        except Exception as e:
            logger.error("暂停任务失败 %s: %s", job_id, e)
            return False

    def resume_job(self, job_id: str) -> bool:
        """恢复任务"""
        try:
            self._scheduler.resume_job(job_id)
            logger.info("已恢复任务: %s", job_id)
            return True
        except Exception as e:
            logger.error("恢复任务失败 %s: %s", job_id, e)
            return False

    # ------------------------------------------------------------------
    # Public — 查询
    # ------------------------------------------------------------------

    def get_job_info(self, job_id: str) -> Optional[Dict[str, Any]]:
        """获取单个任务信息"""
        job = self._scheduler.get_job(job_id)
        if not job:
            return None
        return self._serialize_job(job)

    def get_all_jobs(self) -> List[Dict[str, Any]]:
        """获取所有任务"""
        return [self._serialize_job(j) for j in self._scheduler.get_jobs()]

    def count_jobs_by_prefix(self, prefix: str) -> int:
        """统计指定前缀的任务数量"""
        return sum(1 for j in self._scheduler.get_jobs() if j.id.startswith(prefix))

    def get_jobs_by_prefix(self, prefix: str) -> List[Dict[str, Any]]:
        """获取指定前缀的所有任务"""
        return [
            self._serialize_job(j)
            for j in self._scheduler.get_jobs()
            if j.id.startswith(prefix)
        ]

    def get_scheduler_status(self) -> Dict[str, Any]:
        """获取调度器完整状态"""
        return {
            "running": self._scheduler.running,
            "timezone": str(self._tz),
            "exchange": self._exchange,
            "calendar_available": XCALS_AVAILABLE,
            "is_trading_day": self._check_trading_day_sync(),
            "is_market_open_now": self._check_market_open_sync(),
            "total_jobs": len(self._scheduler.get_jobs()),
            "jobs": self.get_all_jobs(),
            "recent_executions": list(self._job_history_cache),
        }

    async def get_execution_history(
        self,
        limit: int = 50,
        job_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        从数据库查询执行历史。

        Args:
            limit: 最大返回条数
            job_id: 可选，按 job_id 过滤
        """
        from src.db.session import get_db
        from src.db.models import SchedulerJobExecution
        from sqlalchemy import select

        try:
            async with get_db() as db:
                stmt = (
                    select(SchedulerJobExecution)
                    .order_by(SchedulerJobExecution.executed_at.desc())
                    .limit(limit)
                )
                if job_id:
                    stmt = stmt.where(SchedulerJobExecution.job_id == job_id)

                result = await db.execute(stmt)
                rows = result.scalars().all()
                return [row.to_dict() for row in rows]
        except Exception as e:
            logger.error("查询执行历史失败: %s", e)
            # Fallback to in-memory cache
            cache = list(self._job_history_cache)
            if job_id:
                cache = [r for r in cache if r.get("job_id") == job_id]
            return cache[:limit]

    # ------------------------------------------------------------------
    # Internal — helpers
    # ------------------------------------------------------------------

    def _adjust_to_trading_day(self, dt: datetime) -> datetime:
        """调整时间到下一个交易日（保留时分秒）"""
        try:
            next_day = get_next_trading_day(
                dt=dt,
                exchange=self._exchange,
                timezone=settings.trading_timezone,
            )
            return dt.replace(year=next_day.year, month=next_day.month, day=next_day.day)
        except Exception as e:
            logger.warning("调整到交易日失败: %s", e)
            return dt

    def _check_trading_day_sync(self, dt: Optional[datetime] = None) -> bool:
        """同步检查是否为交易日（用于 status 查询等同步上下文）"""
        try:
            return check_trading_day(
                dt=dt, exchange=self._exchange, timezone=settings.trading_timezone,
            )
        except Exception:
            return True  # 失败时默认允许

    def _check_market_open_sync(self) -> bool:
        """同步检查市场是否开放（用于 status 查询等同步上下文）"""
        try:
            return check_market_open(
                exchange=self._exchange, timezone=settings.trading_timezone,
            )
        except Exception:
            return True

    @staticmethod
    def _serialize_job(job) -> Dict[str, Any]:
        """序列化 APScheduler Job 为 dict"""
        trigger = job.trigger
        trigger_type = "unknown"
        trigger_args: Dict[str, Any] = {}

        if isinstance(trigger, CronTrigger):
            trigger_type = "cron"
            for f in trigger.fields:
                trigger_args[f.name] = str(f)
        elif isinstance(trigger, IntervalTrigger):
            trigger_type = "interval"
            trigger_args["interval_seconds"] = trigger.interval.total_seconds()
        elif isinstance(trigger, DateTrigger):
            trigger_type = "date"
            trigger_args["run_date"] = trigger.run_date.isoformat() if trigger.run_date else None

        return {
            "id": job.id,
            "name": job.name,
            "trigger_type": trigger_type,
            "trigger": str(trigger),
            "trigger_args": trigger_args,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "pending": job.pending,
        }

    def _on_job_event(self, event: JobExecutionEvent) -> None:
        """APScheduler 任务执行事件回调 — 写入数据库 + 更新内存缓存"""
        record = {
            "job_id": event.job_id,
            "scheduled_time": (
                event.scheduled_run_time.isoformat() if event.scheduled_run_time else None
            ),
            "executed_at": utc_now().isoformat(),
            "success": event.exception is None,
            "error": str(event.exception) if event.exception else None,
        }

        # 1. 更新内存热缓存（deque 自动淘汰旧数据）
        self._job_history_cache.append(record)

        # 2. 异步写入数据库（fire-and-forget，不阻塞调度器线程）
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._persist_job_execution(record))
            else:
                logger.debug("Event loop not running, skipping DB persist for job %s", event.job_id)
        except RuntimeError:
            logger.debug("No event loop, skipping DB persist for job %s", event.job_id)

        if event.exception:
            logger.error("任务 %s 执行失败: %s", event.job_id, event.exception)
        else:
            logger.debug("任务 %s 执行成功", event.job_id)

    async def _persist_job_execution(self, record: Dict[str, Any]) -> None:
        """将执行记录持久化到数据库"""
        try:
            from src.db.session import get_db
            from src.db.models import SchedulerJobExecution

            async with get_db() as db:
                execution = SchedulerJobExecution(
                    job_id=record["job_id"],
                    scheduled_time=(
                        datetime.fromisoformat(record["scheduled_time"])
                        if record.get("scheduled_time")
                        else None
                    ),
                    executed_at=datetime.fromisoformat(record["executed_at"]),
                    success=record["success"],
                    error=record.get("error"),
                )
                db.add(execution)
                # commit is handled by get_db context manager

        except Exception as e:
            logger.warning("持久化执行记录失败 (job: %s): %s", record.get("job_id"), e)
