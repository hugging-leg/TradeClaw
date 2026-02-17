"""
回测运行器

使用 ProcessPoolExecutor 在独立进程中执行回测，
避免阻塞主进程的实盘交易 event loop。

当前为框架实现，回测核心逻辑待后续完善。
"""

import asyncio
import uuid
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from agent_trader.utils.logging_config import get_logger
from agent_trader.utils.timezone import utc_now

logger = get_logger(__name__)


class BacktestStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class BacktestTask:
    """回测任务状态"""
    id: str
    config: Dict[str, Any]
    status: BacktestStatus = BacktestStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=utc_now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "config": self.config,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


def _run_backtest_in_process(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    在子进程中执行回测（同步函数，由 ProcessPoolExecutor 调用）

    TODO: 实现完整的回测引擎
    当前返回占位结果。
    """
    # 占位实现 — 后续替换为真实回测逻辑
    return {
        "status": "completed",
        "message": "Backtest engine not yet implemented",
        "config": config,
        "total_return": 0.0,
        "sharpe_ratio": 0.0,
        "max_drawdown": 0.0,
        "win_rate": 0.0,
        "total_trades": 0,
        "equity_curve": [],
        "trades": [],
    }


class BacktestRunner:
    """
    回测运行管理器

    - 接受回测请求，分配 task_id
    - 在 ProcessPoolExecutor 中异步执行
    - 维护任务状态，供 API 查询
    """

    def __init__(self, max_workers: int = 2):
        self._executor = ProcessPoolExecutor(max_workers=max_workers)
        self._tasks: Dict[str, BacktestTask] = {}
        self._max_tasks = 100  # 内存中最多保留的历史任务数

    async def submit(self, config: Dict[str, Any]) -> str:
        """
        提交回测任务

        Returns:
            task_id
        """
        task_id = str(uuid.uuid4())[:8]
        task = BacktestTask(id=task_id, config=config)
        self._tasks[task_id] = task

        # 清理过多的历史任务
        self._cleanup_old_tasks()

        # 在 ProcessPoolExecutor 中异步执行
        loop = asyncio.get_running_loop()
        task.status = BacktestStatus.RUNNING
        task.started_at = utc_now()

        logger.info(f"提交回测任务: {task_id}")

        # 使用 run_in_executor 将同步函数提交到进程池
        future = loop.run_in_executor(self._executor, _run_backtest_in_process, config)

        # 注册回调
        asyncio.ensure_future(self._wait_for_result(task_id, future))

        return task_id

    async def _wait_for_result(self, task_id: str, future):
        """等待回测完成并更新状态"""
        task = self._tasks.get(task_id)
        if not task:
            return

        try:
            result = await future
            task.status = BacktestStatus.COMPLETED
            task.result = result
            task.completed_at = utc_now()
            logger.info(f"回测完成: {task_id}")
        except Exception as e:
            task.status = BacktestStatus.FAILED
            task.error = str(e)
            task.completed_at = utc_now()
            logger.error(f"回测失败: {task_id} - {e}")

    def get_task(self, task_id: str) -> Optional[BacktestTask]:
        """获取任务状态"""
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[dict]:
        """获取所有任务"""
        return [t.to_dict() for t in self._tasks.values()]

    def _cleanup_old_tasks(self):
        """清理过多的历史任务（保留最新的 _max_tasks 个）"""
        if len(self._tasks) > self._max_tasks:
            sorted_ids = sorted(
                self._tasks.keys(),
                key=lambda tid: self._tasks[tid].created_at,
            )
            to_remove = sorted_ids[: len(sorted_ids) - self._max_tasks]
            for tid in to_remove:
                # 只删除已完成的任务
                if self._tasks[tid].status in (BacktestStatus.COMPLETED, BacktestStatus.FAILED):
                    del self._tasks[tid]

    def shutdown(self):
        """关闭进程池"""
        self._executor.shutdown(wait=False)
        logger.info("BacktestRunner 已关闭")
