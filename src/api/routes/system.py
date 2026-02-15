"""
系统状态 & 操作 API
"""

from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import get_trading_system
from src.trading_system import TradingSystem

router = APIRouter()


@router.get("/system/status")
async def get_status(ts: TradingSystem = Depends(get_trading_system)):
    """获取系统状态"""
    state = ts.get_system_state()

    try:
        state["market_open"] = await ts.is_market_open()
    except Exception:
        state["market_open"] = None

    return state


@router.post("/system/trading/enable")
async def enable_trading(ts: TradingSystem = Depends(get_trading_system)):
    """启用交易"""
    await ts.enable_trading()
    return {"success": True, "message": "Trading enabled"}


@router.post("/system/trading/disable")
async def disable_trading(ts: TradingSystem = Depends(get_trading_system)):
    """禁用交易"""
    await ts.disable_trading(reason="API request")
    return {"success": True, "message": "Trading disabled"}


@router.post("/system/emergency-stop")
async def emergency_stop(ts: TradingSystem = Depends(get_trading_system)):
    """紧急停止"""
    await ts.emergency_stop()
    return {"success": True, "message": "Emergency stop triggered"}


@router.post("/system/analyze")
async def trigger_analysis(ts: TradingSystem = Depends(get_trading_system)):
    """手动触发分析"""
    if ts._workflow_lock.locked():
        raise HTTPException(
            status_code=429,
            detail="A workflow is already running. Please wait.",
        )
    await ts.trigger_workflow(trigger="manual_analysis", context={"source": "api"})
    return {"success": True, "message": "Analysis triggered"}
