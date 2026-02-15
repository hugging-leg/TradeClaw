"""
组合 & 持仓 API — 直接从 Broker 获取，保证数据一致性
"""

from fastapi import APIRouter, Depends, Query

from src.api.deps import get_trading_system
from src.trading_system import TradingSystem

router = APIRouter()

# Alpaca period 映射
_DAYS_TO_PERIOD = {
    7: "1W",
    30: "1M",
    90: "3M",
    180: "6M",
    365: "1A",
}


def _days_to_period(days: int) -> str:
    """将天数转换为 Alpaca period 字符串"""
    for threshold, period in sorted(_DAYS_TO_PERIOD.items()):
        if days <= threshold:
            return period
    return "1A"


@router.get("/portfolio")
async def get_portfolio(ts: TradingSystem = Depends(get_trading_system)):
    """获取当前组合（实时，来自 Broker）"""
    portfolio = await ts.get_portfolio()
    return _portfolio_to_dict(portfolio)


@router.get("/portfolio/history")
async def get_portfolio_history(
    days: int = Query(default=30, ge=1, le=365),
    ts: TradingSystem = Depends(get_trading_system),
):
    """获取组合历史（直接从 Broker API 查询）"""
    period = _days_to_period(days)
    history = await ts.broker_api.get_portfolio_history(
        period=period, timeframe="1D"
    )
    return history


def _portfolio_to_dict(portfolio) -> dict:
    """将 Portfolio model 转为 API 响应格式"""
    positions = []
    for p in portfolio.positions:
        positions.append({
            "symbol": p.symbol,
            "quantity": float(p.quantity),
            "market_value": float(p.market_value),
            "cost_basis": float(p.cost_basis),
            "unrealized_pnl": float(p.unrealized_pnl),
            "unrealized_pnl_percentage": float(p.unrealized_pnl_percentage),
            "side": p.side,
            "avg_entry_price": float(p.avg_entry_price) if p.avg_entry_price else None,
            "current_price": float(p.current_price),
        })

    return {
        "equity": float(portfolio.equity),
        "cash": float(portfolio.cash),
        "market_value": float(portfolio.market_value),
        "day_trade_count": portfolio.day_trade_count,
        "buying_power": float(portfolio.buying_power),
        "positions": positions,
        "total_pnl": float(portfolio.total_pnl),
        "day_pnl": float(portfolio.day_pnl),
        "last_updated": portfolio.last_updated.isoformat() if portfolio.last_updated else None,
    }
