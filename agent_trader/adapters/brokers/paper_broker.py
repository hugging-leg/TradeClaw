"""
Paper Broker Adapter — 内存撮合引擎（回测用）

实现 BrokerAPI 接口，在内存中维护组合状态：
- 现金 / 持仓 / 订单历史
- 市价单以当日价格 ± 滑点立即成交
- 限价单检查当日 high/low 是否触及
- 佣金 = 成交金额 × commission_rate

不注册到 BrokerFactory（回测专用，由 BacktestRunner 手动创建）。
"""

import uuid
from decimal import Decimal
from datetime import datetime
from typing import Optional, List, Dict, Any

from agent_trader.interfaces.broker_api import BrokerAPI
from agent_trader.models.trading_models import (
    Order, Portfolio, Position,
    OrderSide, OrderType, OrderStatus, PositionSide, TimeInForce,
)
from agent_trader.utils.logging_config import get_logger
from agent_trader.utils.timezone import utc_now

logger = get_logger(__name__)


class PaperBrokerAdapter(BrokerAPI):
    """
    内存撮合 Broker（回测专用）

    Args:
        initial_capital: 初始资金
        commission_rate: 佣金费率（如 0.001 = 0.1%）
        slippage_bps: 滑点（基点，如 5.0 = 0.05%）
        price_provider: 回调函数，给定 symbol 返回当日行情
                        签名: (symbol: str) -> Optional[Dict] 包含 close, high, low
    """

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        commission_rate: float = 0.0,
        slippage_bps: float = 0.0,
        price_provider=None,
    ):
        self._initial_capital = Decimal(str(initial_capital))
        self._cash = Decimal(str(initial_capital))
        self._commission_rate = Decimal(str(commission_rate))
        self._slippage_pct = Decimal(str(slippage_bps)) / Decimal("10000")
        self._price_provider = price_provider  # async (symbol) -> dict | None

        # 持仓: symbol -> {quantity, cost_basis, avg_entry_price}
        self._positions: Dict[str, Dict[str, Decimal]] = {}

        # 订单历史
        self._orders: List[Order] = []

        # 交易历史（用于统计）
        self._trades: List[Dict[str, Any]] = []

        logger.info(
            "PaperBroker initialized: capital=%.2f commission=%.4f slippage=%.1f bps",
            initial_capital, commission_rate, slippage_bps,
        )

    # ------------------------------------------------------------------
    # 价格查询（委托给 price_provider）
    # ------------------------------------------------------------------

    async def _get_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取当日行情"""
        if self._price_provider is None:
            return None
        return await self._price_provider(symbol)

    def _apply_slippage(self, price: Decimal, side: OrderSide) -> Decimal:
        """应用滑点"""
        if self._slippage_pct == 0:
            return price
        if side == OrderSide.BUY:
            return price * (1 + self._slippage_pct)
        else:
            return price * (1 - self._slippage_pct)

    def _calc_commission(self, notional: Decimal) -> Decimal:
        """计算佣金"""
        return abs(notional) * self._commission_rate

    # ------------------------------------------------------------------
    # BrokerAPI 实现
    # ------------------------------------------------------------------

    async def get_account(self) -> Optional[Dict[str, Any]]:
        equity = await self._calc_equity()
        return {
            "equity": float(equity),
            "cash": float(self._cash),
            "buying_power": float(self._cash),
            "initial_capital": float(self._initial_capital),
            "positions_count": len(self._positions),
        }

    async def get_positions(self) -> List[Position]:
        positions = []
        for symbol, pos in self._positions.items():
            if pos["quantity"] == 0:
                continue
            price_data = await self._get_price(symbol)
            current_price = Decimal(str(price_data["close"])) if price_data else pos["avg_entry_price"]
            market_value = pos["quantity"] * current_price
            cost_basis = pos["quantity"] * pos["avg_entry_price"]
            unrealized_pnl = market_value - cost_basis
            unrealized_pnl_pct = (
                (unrealized_pnl / cost_basis * 100) if cost_basis != 0 else Decimal("0")
            )

            positions.append(Position(
                symbol=symbol,
                quantity=pos["quantity"],
                market_value=market_value,
                cost_basis=cost_basis,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_percentage=unrealized_pnl_pct,
                side=PositionSide.LONG if pos["quantity"] > 0 else PositionSide.SHORT,
                avg_entry_price=pos["avg_entry_price"],
            ))
        return positions

    async def get_portfolio(self) -> Optional[Portfolio]:
        positions = await self.get_positions()
        market_value = sum(p.market_value for p in positions)
        equity = self._cash + market_value
        day_pnl = equity - self._initial_capital  # 简化：用总 PnL 代替日 PnL
        total_pnl = equity - self._initial_capital

        return Portfolio(
            equity=equity,
            cash=self._cash,
            market_value=market_value,
            buying_power=self._cash,
            positions=positions,
            total_pnl=total_pnl,
            day_pnl=day_pnl,
            last_updated=utc_now(),
        )

    async def submit_order(self, order: Order) -> Optional[str]:
        """
        提交订单并尝试立即撮合。

        市价单：以当日收盘价 ± 滑点立即成交
        限价单：检查当日 high/low 是否触及限价
        """
        order_id = str(uuid.uuid4())[:12]
        order.id = order_id
        order.status = OrderStatus.SUBMITTED

        logger.info(
            "PaperBroker: submit_order %s %s %s qty=%s type=%s",
            order.side.value, order.symbol, order.order_type.value,
            order.quantity, order.order_type.value,
        )

        price_data = await self._get_price(order.symbol)
        if price_data is None:
            order.status = OrderStatus.REJECTED
            self._orders.append(order)
            logger.warning("Order rejected: no price data for %s", order.symbol)
            return None

        close_price = Decimal(str(price_data["close"]))
        high_price = Decimal(str(price_data.get("high", price_data["close"])))
        low_price = Decimal(str(price_data.get("low", price_data["close"])))

        fill_price: Optional[Decimal] = None

        if order.order_type == OrderType.MARKET:
            fill_price = self._apply_slippage(close_price, order.side)

        elif order.order_type == OrderType.LIMIT and order.price is not None:
            if order.side == OrderSide.BUY and low_price <= order.price:
                fill_price = min(order.price, close_price)
            elif order.side == OrderSide.SELL and high_price >= order.price:
                fill_price = max(order.price, close_price)

        elif order.order_type == OrderType.STOP_LOSS and order.stop_price is not None:
            if order.side == OrderSide.SELL and low_price <= order.stop_price:
                fill_price = self._apply_slippage(order.stop_price, order.side)
            elif order.side == OrderSide.BUY and high_price >= order.stop_price:
                fill_price = self._apply_slippage(order.stop_price, order.side)

        if fill_price is not None:
            self._fill_order(order, fill_price)
        else:
            # 限价单未触及，标记为 cancelled（简化处理，不支持跨日挂单）
            order.status = OrderStatus.CANCELLED
            logger.debug("Order not filled (price not reached): %s %s %s @ %s",
                         order.side.value, order.quantity, order.symbol, order.price)

        self._orders.append(order)
        return order_id if order.status == OrderStatus.FILLED else None

    def _fill_order(self, order: Order, fill_price: Decimal) -> None:
        """执行成交"""
        notional = fill_price * order.quantity
        commission = self._calc_commission(notional)

        if order.side == OrderSide.BUY:
            total_cost = notional + commission
            if total_cost > self._cash:
                # 资金不足，按可用资金调整数量
                affordable_qty = int(
                    (self._cash - commission) / fill_price
                )
                if affordable_qty <= 0:
                    order.status = OrderStatus.REJECTED
                    logger.warning(
                        "Order rejected: insufficient cash for %s (need %.2f, have %.2f)",
                        order.symbol, float(total_cost), float(self._cash),
                    )
                    return
                order.quantity = Decimal(str(affordable_qty))
                notional = fill_price * order.quantity
                commission = self._calc_commission(notional)
                total_cost = notional + commission

            self._cash -= total_cost
            self._update_position(order.symbol, order.quantity, fill_price)

        else:  # SELL
            pos = self._positions.get(order.symbol)
            if pos is None or pos["quantity"] < order.quantity:
                # 持仓不足，按实际持仓卖出
                actual_qty = pos["quantity"] if pos else Decimal("0")
                if actual_qty <= 0:
                    order.status = OrderStatus.REJECTED
                    logger.warning("Order rejected: no position for %s", order.symbol)
                    return
                order.quantity = actual_qty
                notional = fill_price * order.quantity
                commission = self._calc_commission(notional)

            self._cash += notional - commission
            self._update_position(order.symbol, -order.quantity, fill_price)

        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.filled_price = fill_price
        order.updated_at = utc_now()

        self._trades.append({
            "symbol": order.symbol,
            "side": order.side.value,
            "quantity": float(order.quantity),
            "price": float(fill_price),
            "commission": float(commission),
            "timestamp": utc_now().isoformat(),
            "order_id": order.id,
        })

        logger.info(
            "Order filled: %s %s %s @ %.4f (commission: %.4f)",
            order.side.value, order.quantity, order.symbol,
            float(fill_price), float(commission),
        )

    def _update_position(self, symbol: str, qty_delta: Decimal, price: Decimal) -> None:
        """更新持仓"""
        if symbol not in self._positions:
            self._positions[symbol] = {
                "quantity": Decimal("0"),
                "cost_basis": Decimal("0"),
                "avg_entry_price": Decimal("0"),
            }

        pos = self._positions[symbol]
        old_qty = pos["quantity"]
        new_qty = old_qty + qty_delta

        if qty_delta > 0:
            # 加仓：更新平均成本
            old_cost = old_qty * pos["avg_entry_price"]
            new_cost = old_cost + qty_delta * price
            pos["avg_entry_price"] = new_cost / new_qty if new_qty != 0 else Decimal("0")
        # 减仓不改变 avg_entry_price

        pos["quantity"] = new_qty
        pos["cost_basis"] = new_qty * pos["avg_entry_price"]

        # 清仓时移除
        if new_qty == 0:
            del self._positions[symbol]

    async def cancel_order(self, order_id: str) -> bool:
        for order in self._orders:
            if order.id == order_id and order.status == OrderStatus.SUBMITTED:
                order.status = OrderStatus.CANCELLED
                return True
        return False

    async def get_orders(self, status: Optional[str] = None) -> List[Order]:
        if status:
            return [o for o in self._orders if o.status.value == status]
        return list(self._orders)

    async def get_order(self, order_id: str) -> Optional[Order]:
        for order in self._orders:
            if order.id == order_id:
                return order
        return None

    async def get_market_data(self, symbol: str, timeframe: str = "1Day", limit: int = 100) -> List[Dict[str, Any]]:
        """委托给 price_provider（回测中由 BacktestMarketDataAdapter 提供）"""
        return []

    async def is_market_open(self) -> bool:
        """回测中市场始终开放"""
        return True

    def get_provider_name(self) -> str:
        return "Paper (Backtest)"

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": "Paper Broker (Backtest)",
            "type": "paper",
            "initial_capital": float(self._initial_capital),
            "commission_rate": float(self._commission_rate),
            "slippage_bps": float(self._slippage_pct * 10000),
        }

    async def get_portfolio_history(self, period: str = "1M", timeframe: str = "1D") -> List[Dict[str, Any]]:
        return []

    # ------------------------------------------------------------------
    # 回测专用辅助方法
    # ------------------------------------------------------------------

    async def _calc_equity(self) -> Decimal:
        """计算当前总权益"""
        positions = await self.get_positions()
        market_value = sum(p.market_value for p in positions)
        return self._cash + market_value

    def get_trades(self) -> List[Dict[str, Any]]:
        """获取所有成交记录"""
        return list(self._trades)

    def reset(self) -> None:
        """重置到初始状态"""
        self._cash = self._initial_capital
        self._positions.clear()
        self._orders.clear()
        self._trades.clear()
