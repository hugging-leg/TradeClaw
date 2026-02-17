"""
回测 API

- 提交回测任务 → 返回 task_id
- 查询回测状态/结果
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from agent_trader.services.backtest_runner import BacktestRunner

router = APIRouter()

# 全局 BacktestRunner 实例（在 main.py 中通过 set_backtest_runner 注入）
_backtest_runner: Optional[BacktestRunner] = None


def set_backtest_runner(runner: BacktestRunner) -> None:
    global _backtest_runner
    _backtest_runner = runner


def get_backtest_runner() -> BacktestRunner:
    if _backtest_runner is None:
        raise RuntimeError("BacktestRunner not initialized")
    return _backtest_runner


class BacktestRequest(BaseModel):
    """回测请求"""
    start_date: str
    end_date: str
    initial_capital: float = 100000.0
    workflow_type: str = "llm_portfolio"
    symbols: list[str] = []


@router.post("/backtest")
async def submit_backtest(req: BacktestRequest):
    """提交回测任务"""
    runner = get_backtest_runner()
    task_id = await runner.submit(req.model_dump())
    task = runner.get_task(task_id)
    return task.to_dict() if task else {"id": task_id, "status": "pending"}


@router.get("/backtest")
async def list_backtests():
    """获取所有回测任务"""
    runner = get_backtest_runner()
    return runner.get_all_tasks()


@router.get("/backtest/{task_id}")
async def get_backtest(task_id: str):
    """获取回测任务状态"""
    runner = get_backtest_runner()
    task = runner.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Backtest {task_id} not found")
    return task.to_dict()
