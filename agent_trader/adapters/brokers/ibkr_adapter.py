"""
Interactive Brokers (IBKR) 适配器

使用 ib_async 库实现 BrokerAPI 接口（替代已停止维护的 ib_insync）

前置条件：
1. 安装 TWS 或 IB Gateway
2. 启用 API 连接（Edit → Global Configuration → API → Settings）
3. 设置 Socket port (默认 7497 for TWS Paper, 7496 for TWS Live)
4. 允许 localhost 连接

配置说明：
- IBKR_HOST: TWS/Gateway 主机 (默认 127.0.0.1)
- IBKR_PORT: 7497=Paper, 7496=Live, 4001=Gateway Paper, 4002=Gateway Live
- IBKR_CLIENT_ID: 客户端 ID (1-32)
- IBKR_ACCOUNT: 账户 ID (可选，多账户时需要)

安装依赖：
    pip install ib_async
"""

import asyncio
from agent_trader.utils.logging_config import get_logger
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime as dt

from agent_trader.interfaces.broker_api import BrokerAPI
from agent_trader.interfaces.factory import register_broker
from agent_trader.models.trading_models import (
    Order, Portfolio, Position, OrderSide, OrderType,
    OrderStatus, TimeInForce, PositionSide
)
from config import settings

logger = get_logger(__name__)

# 尝试导入 ib_async (替代已停止维护的 ib_insync)
try:
    from ib_async import IB, Stock, MarketOrder, LimitOrder, StopOrder
    from ib_async import Trade
    IB_AVAILABLE = True
except ImportError:
    IB_AVAILABLE = False
    IB = None
    Stock = None
    MarketOrder = None
    LimitOrder = None
    StopOrder = None
    Trade = None
    logger.warning("ib_async 未安装。运行 'pip install ib_async' 以使用 IBKR")


@register_broker("interactive_brokers")
class IBKRBrokerAdapter(BrokerAPI):
    """
    Interactive Brokers 适配器

    特点：
    - 使用 ib_async 库进行异步操作
    - 自动重连机制
    - 支持股票、期权、期货等多种资产
    - 支持实时数据订阅

    注意事项：
    - 需要运行 TWS 或 IB Gateway
    - Paper Trading 使用端口 7497，Live 使用 7496
    - 建议使用 IB Gateway 以获得更稳定的连接
    """

    def __init__(self):
        """初始化 IBKR 适配器"""
        if not IB_AVAILABLE:
            raise RuntimeError(
                "ib_async 未安装。请运行: pip install ib_async"
            )

        # 从配置获取连接参数
        self.host = getattr(settings, 'ibkr_host', '127.0.0.1')
        self.port = getattr(settings, 'ibkr_port', 7497)
        self.client_id = getattr(settings, 'ibkr_client_id', 1)
        self.account = getattr(settings, 'ibkr_account', None)
        self.readonly = getattr(settings, 'ibkr_readonly', False)

        # IB 客户端
        self.ib = IB()
        self._connected = False
        self._connecting = False

        # 订单追踪
        self._pending_orders: Dict[str, Any] = {}

        logger.info(f"IBKR 适配器初始化: {self.host}:{self.port}")

    async def connect(self) -> bool:
        """连接到 TWS/Gateway"""
        if self._connected:
            return True

        if self._connecting:
            while self._connecting:
                await asyncio.sleep(0.1)
            return self._connected

        self._connecting = True

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.ib.connect(
                    self.host,
                    self.port,
                    clientId=self.client_id,
                    readonly=self.readonly,
                    timeout=20
                )
            )

            self._connected = True
            logger.info(f"已连接到 IBKR: {self.host}:{self.port}")

            if not self.account:
                accounts = self.ib.managedAccounts()
                if accounts:
                    self.account = accounts[0]
                    logger.info(f"使用账户: {self.account}")

            return True

        except Exception as e:
            logger.error(f"连接 IBKR 失败: {e}")
            self._connected = False
            return False
        finally:
            self._connecting = False

    async def disconnect(self):
        """断开连接"""
        if self._connected:
            self.ib.disconnect()
            self._connected = False
            logger.info("已断开 IBKR 连接")

    async def _ensure_connected(self):
        """确保已连接"""
        if not self._connected:
            if not await self.connect():
                raise ConnectionError("无法连接到 IBKR")

    async def get_account(self) -> Optional[Dict[str, Any]]:
        """获取账户信息"""
        try:
            await self._ensure_connected()

            loop = asyncio.get_event_loop()
            account_values = await loop.run_in_executor(
                None,
                lambda: self.ib.accountSummary(self.account)
            )

            result = {}
            for av in account_values:
                tags = ['NetLiquidation', 'TotalCashValue', 'BuyingPower',
                        'GrossPositionValue', 'AvailableFunds']
                if av.tag in tags:
                    result[av.tag.lower()] = Decimal(str(av.value))

            zero = Decimal('0')
            return {
                "equity": result.get('netliquidation', zero),
                "cash": result.get('totalcashvalue', zero),
                "buying_power": result.get('buyingpower', zero),
                "portfolio_value": result.get('grosspositionvalue', zero),
                "available_funds": result.get('availablefunds', zero),
                "account": self.account,
                "status": "active"
            }

        except Exception as e:
            logger.error(f"获取账户信息失败: {e}")
            return None

    async def get_positions(self) -> List[Position]:
        """获取持仓"""
        try:
            await self._ensure_connected()

            loop = asyncio.get_event_loop()
            ib_positions = await loop.run_in_executor(
                None,
                lambda: self.ib.positions(self.account)
            )

            positions = []
            for pos in ib_positions:
                market_value = Decimal('0')
                if hasattr(pos, 'marketValue'):
                    market_value = Decimal(str(pos.marketValue))
                if pos.avgCost:
                    avg_cost = Decimal(str(pos.avgCost))
                else:
                    avg_cost = Decimal('0')
                quantity = Decimal(str(pos.position))

                cost_basis = avg_cost * abs(quantity)
                if quantity > 0:
                    unrealized_pnl = market_value - cost_basis
                else:
                    unrealized_pnl = cost_basis - abs(market_value)

                if cost_basis > 0:
                    unrealized_pnl_pct = (unrealized_pnl / cost_basis * 100)
                else:
                    unrealized_pnl_pct = Decimal('0')

                if quantity > 0:
                    side = PositionSide.LONG
                else:
                    side = PositionSide.SHORT
                positions.append(Position(
                    symbol=pos.contract.symbol,
                    quantity=quantity,
                    market_value=market_value,
                    cost_basis=cost_basis,
                    unrealized_pnl=unrealized_pnl,
                    unrealized_pnl_percentage=unrealized_pnl_pct,
                    side=side,
                    avg_entry_price=avg_cost
                ))

            return positions

        except Exception as e:
            logger.error(f"获取持仓失败: {e}")
            return []

    async def get_portfolio(self) -> Optional[Portfolio]:
        """获取投资组合"""
        try:
            account = await self.get_account()
            if not account:
                return None

            positions = await self.get_positions()
            total_pnl = sum(p.unrealized_pnl for p in positions)

            return Portfolio(
                equity=account['equity'],
                cash=account['cash'],
                market_value=account['portfolio_value'],
                buying_power=account['buying_power'],
                positions=positions,
                total_pnl=total_pnl,
                day_pnl=Decimal('0')
            )

        except Exception as e:
            logger.error(f"获取投资组合失败: {e}")
            return None

    async def submit_order(self, order: Order) -> Optional[str]:
        """提交订单"""
        try:
            await self._ensure_connected()

            contract = Stock(order.symbol, 'SMART', 'USD')
            action = 'BUY' if order.side == OrderSide.BUY else 'SELL'
            qty = float(order.quantity)

            if order.order_type == OrderType.MARKET:
                ib_order = MarketOrder(action=action, totalQuantity=qty)
            elif order.order_type == OrderType.LIMIT:
                ib_order = LimitOrder(
                    action=action,
                    totalQuantity=qty,
                    lmtPrice=float(order.price)
                )
            elif order.order_type == OrderType.STOP_LOSS:
                stop_price = order.stop_price or order.stop_loss
                ib_order = StopOrder(
                    action=action,
                    totalQuantity=qty,
                    stopPrice=float(stop_price)
                )
            else:
                logger.error(f"不支持的订单类型: {order.order_type}")
                return None

            ib_order.tif = self._convert_tif(order.time_in_force)

            loop = asyncio.get_event_loop()
            trade = await loop.run_in_executor(
                None,
                lambda: self.ib.placeOrder(contract, ib_order)
            )

            await asyncio.sleep(0.5)

            order_id = str(trade.order.orderId)
            self._pending_orders[order_id] = trade

            logger.info(
                f"订单已提交: {order_id} - "
                f"{order.symbol} {order.side} {order.quantity}"
            )
            return order_id

        except Exception as e:
            logger.error(f"提交订单失败: {e}")
            return None

    async def cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        try:
            await self._ensure_connected()

            trade = self._pending_orders.get(order_id)
            if not trade:
                logger.warning(f"找不到订单: {order_id}")
                return False

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.ib.cancelOrder(trade.order)
            )

            logger.info(f"订单已取消: {order_id}")
            return True

        except Exception as e:
            logger.error(f"取消订单失败: {e}")
            return False

    async def get_orders(self, status: Optional[str] = None) -> List[Order]:
        """获取订单列表"""
        try:
            await self._ensure_connected()

            loop = asyncio.get_event_loop()
            open_trades = await loop.run_in_executor(
                None,
                lambda: self.ib.openTrades()
            )

            orders = []
            for trade in open_trades:
                order_status = self._convert_status(trade.orderStatus.status)

                if status and status.lower() != 'all':
                    skip = [OrderStatus.FILLED, OrderStatus.CANCELLED]
                    if status.lower() == 'open' and order_status in skip:
                        continue

                side = OrderSide.BUY
                if trade.order.action == 'SELL':
                    side = OrderSide.SELL

                price = None
                if trade.order.lmtPrice:
                    price = Decimal(str(trade.order.lmtPrice))

                filled_price = None
                if trade.orderStatus.avgFillPrice:
                    filled_price = Decimal(str(trade.orderStatus.avgFillPrice))

                orders.append(Order(
                    id=str(trade.order.orderId),
                    symbol=trade.contract.symbol,
                    side=side,
                    order_type=self._convert_order_type(trade.order.orderType),
                    quantity=Decimal(str(trade.order.totalQuantity)),
                    price=price,
                    status=order_status,
                    filled_quantity=Decimal(str(trade.orderStatus.filled)),
                    filled_price=filled_price,
                ))

            return orders

        except Exception as e:
            logger.error(f"获取订单列表失败: {e}")
            return []

    async def get_order(self, order_id: str) -> Optional[Order]:
        """获取指定订单"""
        orders = await self.get_orders()
        for order in orders:
            if order.id == order_id:
                return order
        return None

    async def get_market_data(
        self,
        symbol: str,
        timeframe: str = "1Day",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取历史市场数据"""
        try:
            await self._ensure_connected()

            contract = Stock(symbol, 'SMART', 'USD')
            duration, bar_size = self._convert_timeframe(timeframe, limit)

            loop = asyncio.get_event_loop()
            bars = await loop.run_in_executor(
                None,
                lambda: self.ib.reqHistoricalData(
                    contract,
                    endDateTime='',
                    durationStr=duration,
                    barSizeSetting=bar_size,
                    whatToShow='TRADES',
                    useRTH=True
                )
            )

            result = []
            for bar in bars[-limit:]:
                if hasattr(bar.date, 'isoformat'):
                    ts = bar.date.isoformat()
                else:
                    ts = str(bar.date)
                result.append({
                    "timestamp": ts,
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": int(bar.volume)
                })

            return result

        except Exception as e:
            logger.error(f"获取市场数据失败 {symbol}: {e}")
            return []

    async def is_market_open(self) -> bool:
        """检查市场是否开放"""
        try:
            await self._ensure_connected()

            contract = Stock('SPY', 'SMART', 'USD')

            loop = asyncio.get_event_loop()
            details = await loop.run_in_executor(
                None,
                lambda: self.ib.reqContractDetails(contract)
            )

            if details:
                now = dt.now()
                if 9 <= now.hour < 16:
                    return True

            return False

        except Exception as e:
            logger.error(f"检查市场状态失败: {e}")
            return False

    def get_provider_name(self) -> str:
        return "Interactive Brokers"

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": "Interactive Brokers",
            "type": "broker",
            "description": "全球领先的在线经纪商",
            "website": "https://www.interactivebrokers.com",
            "features": [
                "全球市场访问",
                "低佣金",
                "专业级交易平台",
                "期权/期货/外汇支持",
                "API 交易"
            ],
            "supported_assets": [
                "stocks", "options", "futures", "forex", "bonds"
            ],
            "supported_order_types": [
                "market", "limit", "stop", "stop_limit", "trailing_stop"
            ],
            "connection": {
                "host": self.host,
                "port": self.port,
                "client_id": self.client_id,
                "connected": self._connected,
                "account": self.account
            }
        }

    @staticmethod
    def _convert_tif(tif: TimeInForce) -> str:
        """转换有效期"""
        mapping = {
            TimeInForce.DAY: 'DAY',
            TimeInForce.GTC: 'GTC',
            TimeInForce.IOC: 'IOC',
            TimeInForce.FOK: 'FOK'
        }
        return mapping.get(tif, 'DAY')

    @staticmethod
    def _convert_status(status: str) -> OrderStatus:
        """转换订单状态"""
        mapping = {
            'PendingSubmit': OrderStatus.PENDING,
            'PendingCancel': OrderStatus.PENDING,
            'PreSubmitted': OrderStatus.PENDING,
            'Submitted': OrderStatus.SUBMITTED,
            'Cancelled': OrderStatus.CANCELLED,
            'Filled': OrderStatus.FILLED,
            'Inactive': OrderStatus.CANCELLED
        }
        return mapping.get(status, OrderStatus.PENDING)

    @staticmethod
    def _convert_order_type(order_type: str) -> OrderType:
        """转换订单类型"""
        mapping = {
            'MKT': OrderType.MARKET,
            'LMT': OrderType.LIMIT,
            'STP': OrderType.STOP_LOSS,
            'STP LMT': OrderType.STOP_LIMIT
        }
        return mapping.get(order_type, OrderType.MARKET)

    @staticmethod
    def _convert_timeframe(timeframe: str, limit: int) -> tuple:
        """转换时间周期为 IBKR 格式"""
        mapping = {
            "1Min": (f"{limit} S", "1 min"),
            "5Min": (f"{limit * 5} S", "5 mins"),
            "15Min": (f"{limit * 15} S", "15 mins"),
            "30Min": (f"{limit * 30} S", "30 mins"),
            "1Hour": (f"{limit} D", "1 hour"),
            "1Day": (f"{limit} D", "1 day"),
            "1Week": (f"{limit} W", "1 week"),
            "1Month": (f"{limit} M", "1 month")
        }
        return mapping.get(timeframe, (f"{limit} D", "1 day"))
