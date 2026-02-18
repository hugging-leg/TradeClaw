"""
回测 API

- 提交回测任务（配置费率、滑点、初始资金等）
- 查询回测状态/结果
- 取消运行中的回测
- SSE 实时进度推送
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List

from agent_trader.services.backtest_runner import BacktestRunner, BacktestConfig

router = APIRouter()

# 全局 BacktestRunner 实例（在 app.py 中注入）
_backtest_runner: Optional[BacktestRunner] = None


def set_backtest_runner(runner: BacktestRunner) -> None:
    global _backtest_runner
    _backtest_runner = runner


def get_backtest_runner() -> BacktestRunner:
    if _backtest_runner is None:
        raise RuntimeError("BacktestRunner not initialized")
    return _backtest_runner


# ============================================================
# Request / Response Models
# ============================================================

class BacktestRequest(BaseModel):
    """回测请求"""
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    initial_capital: float = Field(100000.0, description="Initial capital ($)")
    workflow_type: str = Field("llm_portfolio", description="Workflow type to backtest")
    commission_rate: float = Field(0.001, description="Commission rate (0.001 = 0.1%)")
    slippage_bps: float = Field(5.0, description="Slippage in basis points")
    run_interval_days: int = Field(1, description="Run workflow every N trading days")


class BacktestCancelResponse(BaseModel):
    success: bool
    message: str


# ============================================================
# Routes
# ============================================================

@router.post("/backtest")
async def submit_backtest(req: BacktestRequest):
    """提交回测任务"""
    runner = get_backtest_runner()

    config = BacktestConfig(
        start_date=req.start_date,
        end_date=req.end_date,
        initial_capital=req.initial_capital,
        workflow_type=req.workflow_type,
        commission_rate=req.commission_rate,
        slippage_bps=req.slippage_bps,
        run_interval_days=req.run_interval_days,
    )

    task_id = await runner.submit(config)
    task = runner.get_task(task_id)
    return task.to_dict() if task else {"id": task_id, "status": "pending"}


@router.get("/backtest")
async def list_backtests():
    """获取所有回测任务（内存 + DB 合并）"""
    runner = get_backtest_runner()
    # 内存中的任务（包含运行中的）
    in_memory = runner.get_all_tasks()
    in_memory_ids = {t["id"] for t in in_memory}

    # DB 中的历史任务
    try:
        from agent_trader.utils.db_utils import DB_AVAILABLE, get_trading_repository
        if DB_AVAILABLE:
            repo = get_trading_repository()
            if repo:
                db_results = await repo.get_backtest_results(limit=50)
                # 合并：DB 中有但内存中没有的
                for r in db_results:
                    if r["id"] not in in_memory_ids:
                        in_memory.append(r)
    except Exception:
        pass

    return in_memory


@router.get("/backtest/{task_id}")
async def get_backtest(task_id: str):
    """获取回测任务详情"""
    runner = get_backtest_runner()
    task = runner.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Backtest {task_id} not found")
    return task.to_dict()


@router.post("/backtest/{task_id}/cancel")
async def cancel_backtest(task_id: str):
    """取消回测任务"""
    runner = get_backtest_runner()
    success = runner.cancel(task_id)
    if success:
        return BacktestCancelResponse(success=True, message=f"Backtest {task_id} cancellation requested")
    raise HTTPException(status_code=400, detail=f"Cannot cancel backtest {task_id}")
