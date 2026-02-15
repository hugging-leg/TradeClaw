"""
Scheduler API — 任务管理 + 规则触发器

所有调度管理直接调用 TradingSystem 的 public 方法，
不经过任何中间层。
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from src.api.deps import get_trading_system
from src.trading_system import TradingSystem

router = APIRouter()


# ========== Pydantic Schemas ==========

class CronJobRequest(BaseModel):
    """创建 Cron 任务请求"""
    job_id: str
    hour: int
    minute: int
    day_of_week: str = "mon-fri"
    require_trading_day: bool = True
    require_market_open: bool = False
    trigger_name: str = "custom"


class IntervalJobRequest(BaseModel):
    """创建 Interval 任务请求"""
    job_id: str
    minutes: Optional[int] = None
    hours: Optional[int] = None
    require_trading_day: bool = True
    require_market_open: bool = True
    trigger_name: str = "custom"


class RuleTriggerUpdate(BaseModel):
    """更新规则触发器"""
    threshold: Optional[float] = None
    enabled: Optional[bool] = None


# ========== Jobs ==========

@router.get("/scheduler/status")
async def get_scheduler_status(ts: TradingSystem = Depends(get_trading_system)):
    """获取调度器状态"""
    return ts.get_scheduler_status()


@router.get("/scheduler/jobs")
async def get_jobs(ts: TradingSystem = Depends(get_trading_system)):
    """获取所有调度任务"""
    return ts.get_all_jobs()


@router.get("/scheduler/jobs/{job_id}")
async def get_job(job_id: str, ts: TradingSystem = Depends(get_trading_system)):
    """获取单个任务详情"""
    info = ts.get_job_info(job_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return info


@router.post("/scheduler/jobs/cron")
async def create_cron_job(
    req: CronJobRequest,
    ts: TradingSystem = Depends(get_trading_system),
):
    """创建 Cron 定时任务（回调为 trigger_workflow）"""

    # 用户通过 API 创建的任务，回调统一为 trigger_workflow
    async def _trigger_callback() -> None:
        await ts.trigger_workflow(
            trigger=req.trigger_name,
            context={"source": "scheduled", "job_id": req.job_id},
        )

    success = ts.add_cron_job(
        job_id=req.job_id,
        func=_trigger_callback,
        hour=req.hour,
        minute=req.minute,
        day_of_week=req.day_of_week,
        require_trading_day=req.require_trading_day,
        require_market_open=req.require_market_open,
    )
    if not success:
        raise HTTPException(status_code=400, detail=f"Failed to create job {req.job_id}")
    return ts.get_job_info(req.job_id)


@router.post("/scheduler/jobs/interval")
async def create_interval_job(
    req: IntervalJobRequest,
    ts: TradingSystem = Depends(get_trading_system),
):
    """创建 Interval 周期任务（回调为 trigger_workflow）"""
    if not req.minutes and not req.hours:
        raise HTTPException(status_code=400, detail="Must specify minutes or hours")

    async def _trigger_callback() -> None:
        await ts.trigger_workflow(
            trigger=req.trigger_name,
            context={"source": "scheduled", "job_id": req.job_id},
        )

    success = ts.add_interval_job(
        job_id=req.job_id,
        func=_trigger_callback,
        minutes=req.minutes,
        hours=req.hours,
        require_trading_day=req.require_trading_day,
        require_market_open=req.require_market_open,
    )
    if not success:
        raise HTTPException(status_code=400, detail=f"Failed to create job {req.job_id}")
    return ts.get_job_info(req.job_id)


@router.delete("/scheduler/jobs/{job_id}")
async def delete_job(job_id: str, ts: TradingSystem = Depends(get_trading_system)):
    """删除任务"""
    success = ts.remove_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return {"success": True, "message": f"Job {job_id} removed"}


@router.post("/scheduler/jobs/{job_id}/pause")
async def pause_job(job_id: str, ts: TradingSystem = Depends(get_trading_system)):
    """暂停任务"""
    success = ts.pause_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return ts.get_job_info(job_id)


@router.post("/scheduler/jobs/{job_id}/resume")
async def resume_job(job_id: str, ts: TradingSystem = Depends(get_trading_system)):
    """恢复任务"""
    success = ts.resume_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return ts.get_job_info(job_id)


# ========== Execution History ==========

@router.get("/scheduler/history")
async def get_execution_history(
    limit: int = 50,
    job_id: Optional[str] = None,
    ts: TradingSystem = Depends(get_trading_system),
):
    """查询任务执行历史（从数据库持久化存储中查询）"""
    return await ts.get_execution_history(limit=limit, job_id=job_id)


# ========== Rule Triggers (RealtimeMonitor thresholds) ==========

@router.get("/scheduler/rules")
async def get_rule_triggers(ts: TradingSystem = Depends(get_trading_system)):
    """获取规则触发器配置"""
    monitor = ts.realtime_monitor
    return [
        {
            "id": "price_change",
            "name": "Price Change",
            "type": "price_change",
            "enabled": monitor.is_monitoring,
            "threshold": float(monitor.price_change_threshold),
            "description": "Trigger when position price changes beyond threshold (%)",
        },
        {
            "id": "volatility",
            "name": "Volatility",
            "type": "volatility",
            "enabled": monitor.is_monitoring,
            "threshold": float(monitor.volatility_threshold),
            "description": "Trigger when intraday volatility exceeds threshold (%)",
        },
    ]


@router.patch("/scheduler/rules/{rule_id}")
async def update_rule_trigger(
    rule_id: str,
    update: RuleTriggerUpdate,
    ts: TradingSystem = Depends(get_trading_system),
):
    """更新规则触发器阈值"""
    from decimal import Decimal

    monitor = ts.realtime_monitor

    if rule_id == "price_change":
        if update.threshold is not None:
            monitor.price_change_threshold = Decimal(str(update.threshold))
    elif rule_id == "volatility":
        if update.threshold is not None:
            monitor.volatility_threshold = Decimal(str(update.threshold))
    else:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")

    return await get_rule_triggers(ts)
