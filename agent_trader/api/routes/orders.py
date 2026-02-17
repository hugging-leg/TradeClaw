"""
订单 API — 直接从 Broker 获取，保证数据一致性
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from agent_trader.api.deps import get_trading_system
from agent_trader.trading_system import TradingSystem

router = APIRouter()


@router.get("/orders")
async def get_orders(
    status: Optional[str] = Query(default=None, description="Filter by status: open, closed, all"),
    ts: TradingSystem = Depends(get_trading_system),
):
    """获取订单列表（直接从 Broker API 查询）"""
    broker_status = status if status and status != "all" else None
    orders = await ts.broker_api.get_orders(status=broker_status)
    return [_order_to_dict(o) for o in orders]


@router.get("/orders/active")
async def get_active_orders(ts: TradingSystem = Depends(get_trading_system)):
    """获取活跃订单（实时，来自 Broker）"""
    orders = await ts.get_active_orders()
    return [_order_to_dict(o) for o in orders]


@router.delete("/orders/{order_id}")
async def cancel_order(
    order_id: str,
    ts: TradingSystem = Depends(get_trading_system),
):
    """取消指定订单（调用 Broker API）"""
    success = await ts.broker_api.cancel_order(order_id)
    if not success:
        raise HTTPException(status_code=400, detail=f"Failed to cancel order {order_id}")
    return {"success": True, "order_id": order_id, "message": "Order cancelled"}


def _order_to_dict(order) -> dict:
    """将 Order model 转为 API 响应格式"""
    return {
        "id": order.id,
        "symbol": order.symbol,
        "side": order.side.value if hasattr(order.side, "value") else str(order.side),
        "order_type": order.order_type.value if hasattr(order.order_type, "value") else str(order.order_type),
        "quantity": float(order.quantity),
        "price": float(order.price) if order.price else None,
        "stop_price": float(order.stop_price) if hasattr(order, "stop_price") and order.stop_price else None,
        "stop_loss": float(order.stop_loss) if hasattr(order, "stop_loss") and order.stop_loss else None,
        "take_profit": float(order.take_profit) if hasattr(order, "take_profit") and order.take_profit else None,
        "time_in_force": order.time_in_force.value if hasattr(order.time_in_force, "value") else str(order.time_in_force),
        "status": order.status.value if hasattr(order.status, "value") else str(order.status),
        "filled_quantity": float(order.filled_quantity) if hasattr(order, "filled_quantity") and order.filled_quantity else 0,
        "filled_price": float(order.filled_price) if hasattr(order, "filled_price") and order.filled_price else None,
        "broker_order_id": getattr(order, "broker_order_id", None),
        "created_at": order.created_at.isoformat() if hasattr(order, "created_at") and order.created_at else None,
        "updated_at": order.updated_at.isoformat() if hasattr(order, "updated_at") and order.updated_at else None,
        "filled_at": order.filled_at.isoformat() if hasattr(order, "filled_at") and order.filled_at else None,
        "cancelled_at": order.cancelled_at.isoformat() if hasattr(order, "cancelled_at") and order.cancelled_at else None,
        "error_message": getattr(order, "error_message", None),
    }
