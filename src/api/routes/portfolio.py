"""
组合 & 持仓 API
"""

from fastapi import APIRouter, Depends, Query

from src.api.deps import get_trading_system
from src.trading_system import TradingSystem
from src.db.repository import TradingRepository

router = APIRouter()


@router.get("/portfolio")
async def get_portfolio(ts: TradingSystem = Depends(get_trading_system)):
    """获取当前组合（实时，来自 Broker）"""
    portfolio = await ts.get_portfolio()
    # Portfolio 是 pydantic model / dataclass，转 dict
    return _portfolio_to_dict(portfolio)


@router.get("/portfolio/history")
async def get_portfolio_history(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=100, ge=1, le=1000),
):
    """获取组合历史快照（来自 DB）"""
    snapshots = await TradingRepository.get_portfolio_history(days=days, limit=limit)
    return [s.to_dict() for s in snapshots]


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
