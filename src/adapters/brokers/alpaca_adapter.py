"""
Alpaca broker adapter implementing the BrokerAPI interface.

This adapter wraps the Alpaca API to provide a unified interface for trading operations.
使用 run_in_executor 避免同步调用阻塞事件循环。
"""

import asyncio
from src.utils.logging_config import get_logger
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from functools import partial, wraps

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.trading.requests import (
    MarketOrderRequest, LimitOrderRequest, StopOrderRequest, StopLimitOrderRequest,
    GetOrdersRequest
)
from alpaca.trading.enums import (
    OrderSide as AlpacaOrderSide,
    OrderType as AlpacaOrderType,
    TimeInForce as AlpacaTimeInForce,
    OrderStatus as AlpacaOrderStatus,
    PositionSide as AlpacaPositionSide
)
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from src.interfaces.broker_api import BrokerAPI
from src.interfaces.factory import register_broker
from src.models.trading_models import (
    Order, Portfolio, Position, OrderSide, OrderType,
    OrderStatus, TimeInForce, PositionSide
)
from config import settings

logger = get_logger(__name__)


# 直接使用 tenacity 装饰器
def broker_retry(max_attempts: int = 3):
    """Broker API 重试装饰器"""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        reraise=True
    )


@register_broker("alpaca")
class AlpacaBrokerAdapter(BrokerAPI):
    """
    Alpaca broker adapter implementing BrokerAPI interface

    改进点：
    - 使用 run_in_executor 避免同步调用阻塞
    - 添加重试机制
    - 统一的错误处理
    """

    def __init__(self):
        """Initialize Alpaca clients"""
        try:
            # Initialize trading client for orders and account management
            self.trading_client = TradingClient(
                api_key=settings.alpaca_api_key,
                secret_key=settings.alpaca_secret_key,
                paper=settings.paper_trading
            )

            # Initialize data client for market data
            self.data_client = StockHistoricalDataClient(
                api_key=settings.alpaca_api_key,
                secret_key=settings.alpaca_secret_key
            )

            # 获取事件循环的 executor
            self._executor = None

            logger.info("Alpaca broker adapter initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Alpaca broker adapter: {e}")
            raise

    async def _run_sync(self, func, *args, **kwargs):
        """
        在线程池中运行同步函数，避免阻塞事件循环

        使用 asyncio.to_thread (Python 3.9+) 或 run_in_executor

        Args:
            func: 同步函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数返回值
        """
        # 使用 partial 来传递参数
        if kwargs:
            func_with_args = partial(func, *args, **kwargs)
        elif args:
            func_with_args = partial(func, *args)
        else:
            func_with_args = func

        # Python 3.9+ 推荐使用 asyncio.to_thread
        # 但它不支持自定义 executor，所以这里使用 run_in_executor
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, func_with_args)

    @broker_retry(max_attempts=3)
    async def get_account(self) -> Optional[Dict[str, Any]]:
        """Get account information"""
        try:
            account = await self._run_sync(self.trading_client.get_account)
            return {
                "equity": Decimal(str(account.equity)),
                "cash": Decimal(str(account.cash)),
                "portfolio_value": Decimal(str(account.portfolio_value)),
                "daytrading_buying_power": Decimal(str(account.daytrading_buying_power)),
                "regt_buying_power": Decimal(str(account.regt_buying_power)),
                "buying_power": Decimal(str(account.buying_power)),
                "status": account.status,
                "trade_suspended_by_user": account.trade_suspended_by_user,
                "transfers_blocked": account.transfers_blocked
            }
        except Exception as e:
            logger.error(f"Failed to get account: {e}")
            return None

    @broker_retry(max_attempts=3)
    async def get_positions(self) -> List[Position]:
        """Get current positions"""
        try:
            positions_response = await self._run_sync(
                self.trading_client.get_all_positions
            )
            positions = []

            for pos in positions_response:
                position = Position(
                    symbol=pos.symbol,
                    quantity=Decimal(str(pos.qty)),
                    market_value=Decimal(str(pos.market_value)),
                    cost_basis=Decimal(str(pos.cost_basis)),
                    unrealized_pnl=Decimal(str(pos.unrealized_pl)),
                    unrealized_pnl_percentage=Decimal(str(pos.unrealized_plpc)),
                    side=self._convert_alpaca_position_side(pos.side),
                    avg_entry_price=Decimal(str(pos.avg_entry_price))
                )
                positions.append(position)

            return positions

        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []

    @broker_retry(max_attempts=3)
    async def get_portfolio(self) -> Optional[Portfolio]:
        """Get current portfolio information"""
        try:
            account_info = await self.get_account()
            if not account_info:
                return None

            positions = await self.get_positions()

            # Calculate P&L
            total_pnl = sum(pos.unrealized_pnl for pos in positions)

            portfolio = Portfolio(
                equity=account_info["equity"],
                cash=account_info["cash"],
                market_value=account_info["portfolio_value"],
                day_trade_count=0,
                buying_power=account_info["buying_power"],
                positions=positions,
                total_pnl=total_pnl,
                day_pnl=Decimal("0")
            )

            return portfolio

        except Exception as e:
            logger.error(f"Failed to get portfolio: {e}")
            return None

    async def submit_order(self, order: Order) -> Optional[str]:
        """
        Submit a new order

        注意：交易操作不使用自动重试，避免重复下单
        """
        try:
            # Convert to Alpaca request format
            if order.order_type == OrderType.MARKET:
                request = MarketOrderRequest(
                    symbol=order.symbol,
                    qty=float(order.quantity),
                    side=self._convert_order_side_to_alpaca(order.side),
                    time_in_force=self._convert_time_in_force_to_alpaca(order.time_in_force)
                )
            elif order.order_type == OrderType.LIMIT:
                request = LimitOrderRequest(
                    symbol=order.symbol,
                    qty=float(order.quantity),
                    side=self._convert_order_side_to_alpaca(order.side),
                    time_in_force=self._convert_time_in_force_to_alpaca(order.time_in_force),
                    limit_price=float(order.price) if order.price else None
                )
            elif order.order_type == OrderType.STOP_LOSS:
                stop_price = order.stop_loss or order.stop_price
                if not stop_price:
                    logger.error("Stop loss order requires stop_price or stop_loss")
                    return None
                request = StopOrderRequest(
                    symbol=order.symbol,
                    qty=float(order.quantity),
                    side=self._convert_order_side_to_alpaca(order.side),
                    time_in_force=self._convert_time_in_force_to_alpaca(order.time_in_force),
                    stop_price=float(stop_price)
                )
            else:
                logger.error(f"Unsupported order type: {order.order_type}")
                return None

            # Submit order (在 executor 中运行)
            alpaca_order = await self._run_sync(
                self.trading_client.submit_order,
                request
            )

            logger.info(
                f"Order submitted: {alpaca_order.id} - "
                f"{order.symbol} {order.side.value} {order.quantity}"
            )
            return str(alpaca_order.id)

        except Exception as e:
            logger.error(f"Failed to submit order: {e}")
            return None

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order"""
        try:
            await self._run_sync(
                self.trading_client.cancel_order_by_id,
                order_id
            )
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    @broker_retry(max_attempts=3)
    async def get_orders(self, status: Optional[str] = None) -> List[Order]:
        """Get list of orders"""
        try:
            # Create request
            request = GetOrdersRequest(
                status=status,
                limit=100
            )

            alpaca_orders = await self._run_sync(
                self.trading_client.get_orders,
                request
            )
            orders = []

            for alpaca_order in alpaca_orders:
                order = Order(
                    id=str(alpaca_order.id),
                    symbol=alpaca_order.symbol,
                    side=self._convert_alpaca_side_to_order_side(alpaca_order.side),
                    order_type=self._convert_alpaca_type_to_order_type(alpaca_order.order_type),
                    quantity=Decimal(str(alpaca_order.qty)),
                    price=Decimal(str(alpaca_order.limit_price)) if alpaca_order.limit_price else None,
                    stop_price=Decimal(str(alpaca_order.stop_price)) if alpaca_order.stop_price else None,
                    time_in_force=self._convert_alpaca_tif_to_time_in_force(alpaca_order.time_in_force),
                    status=self._convert_alpaca_status_to_order_status(alpaca_order.status),
                    filled_quantity=Decimal(str(alpaca_order.filled_qty)) if alpaca_order.filled_qty else Decimal('0'),
                    filled_price=Decimal(str(alpaca_order.filled_avg_price)) if alpaca_order.filled_avg_price else None,
                    created_at=alpaca_order.created_at,
                    updated_at=alpaca_order.updated_at
                )
                orders.append(order)

            return orders

        except Exception as e:
            logger.error(f"Failed to get orders: {e}")
            return []

    @broker_retry(max_attempts=3)
    async def get_order(self, order_id: str) -> Optional[Order]:
        """Get specific order by ID"""
        try:
            alpaca_order = await self._run_sync(
                self.trading_client.get_order_by_id,
                order_id
            )

            return Order(
                id=str(alpaca_order.id),
                symbol=alpaca_order.symbol,
                side=self._convert_alpaca_side_to_order_side(alpaca_order.side),
                order_type=self._convert_alpaca_type_to_order_type(alpaca_order.order_type),
                quantity=Decimal(str(alpaca_order.qty)),
                price=Decimal(str(alpaca_order.limit_price)) if alpaca_order.limit_price else None,
                stop_price=Decimal(str(alpaca_order.stop_price)) if alpaca_order.stop_price else None,
                time_in_force=self._convert_alpaca_tif_to_time_in_force(alpaca_order.time_in_force),
                status=self._convert_alpaca_status_to_order_status(alpaca_order.status),
                filled_quantity=Decimal(str(alpaca_order.filled_qty)) if alpaca_order.filled_qty else Decimal('0'),
                filled_price=Decimal(str(alpaca_order.filled_avg_price)) if alpaca_order.filled_avg_price else None,
                created_at=alpaca_order.created_at,
                updated_at=alpaca_order.updated_at
            )

        except Exception as e:
            logger.error(f"Failed to get order {order_id}: {e}")
            return None

    @broker_retry(max_attempts=3)
    async def get_market_data(
        self,
        symbol: str,
        timeframe: str = "1Day",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get market data for a symbol"""
        try:
            # Convert timeframe to Alpaca format
            alpaca_timeframe = self._convert_timeframe(timeframe)

            # Create request
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=alpaca_timeframe,
                limit=limit
            )

            bars = await self._run_sync(
                self.data_client.get_stock_bars,
                request
            )
            market_data = []

            # Check if symbol exists in response data
            if not hasattr(bars, 'data') or symbol not in bars.data or not bars.data[symbol]:
                logger.warning(
                    f"No market data available for {symbol} "
                    f"(timeframe: {timeframe}, limit: {limit})"
                )
                return []

            for bar in bars[symbol]:
                market_data.append({
                    "timestamp": bar.timestamp.isoformat() if hasattr(bar.timestamp, 'isoformat') else str(bar.timestamp),
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": bar.volume
                })

            return market_data

        except Exception as e:
            logger.error(f"Failed to get market data for {symbol}: {e}")
            return []

    @broker_retry(max_attempts=3)
    async def is_market_open(self) -> bool:
        """Check if market is currently open"""
        try:
            clock = await self._run_sync(self.trading_client.get_clock)
            return clock.is_open
        except Exception as e:
            logger.error(f"Failed to check market status: {e}")
            return False

    def get_provider_name(self) -> str:
        """Get the name of the broker provider"""
        return "Alpaca"

    def get_provider_info(self) -> Dict[str, Any]:
        """Get detailed information about the broker provider"""
        return {
            "name": "Alpaca",
            "type": "broker",
            "description": "Commission-free stock trading API",
            "website": "https://alpaca.markets",
            "features": [
                "Commission-free trading",
                "Real-time market data",
                "Paper trading",
                "Crypto trading",
                "Fractional shares",
                "API-first platform"
            ],
            "supported_assets": ["stocks", "etfs", "crypto"],
            "supported_order_types": ["market", "limit", "stop", "stop_limit"],
            "paper_trading": settings.paper_trading,
            "rate_limits": {
                "orders": "200 per minute",
                "account": "200 per minute",
                "market_data": "200 per minute"
            }
        }

    # ========== Helper methods for type conversion ==========

    @staticmethod
    def _convert_order_side_to_alpaca(side: OrderSide) -> AlpacaOrderSide:
        """Convert OrderSide to Alpaca OrderSide"""
        mapping = {
            OrderSide.BUY: AlpacaOrderSide.BUY,
            OrderSide.SELL: AlpacaOrderSide.SELL
        }
        result = mapping.get(side)
        if result is None:
            raise ValueError(f"Unknown order side: {side}")
        return result

    @staticmethod
    def _convert_alpaca_side_to_order_side(side: AlpacaOrderSide) -> OrderSide:
        """Convert Alpaca OrderSide to OrderSide"""
        mapping = {
            AlpacaOrderSide.BUY: OrderSide.BUY,
            AlpacaOrderSide.SELL: OrderSide.SELL
        }
        result = mapping.get(side)
        if result is None:
            raise ValueError(f"Unknown Alpaca order side: {side}")
        return result

    @staticmethod
    def _convert_time_in_force_to_alpaca(tif: TimeInForce) -> AlpacaTimeInForce:
        """Convert TimeInForce to Alpaca TimeInForce"""
        mapping = {
            TimeInForce.DAY: AlpacaTimeInForce.DAY,
            TimeInForce.GTC: AlpacaTimeInForce.GTC,
            TimeInForce.IOC: AlpacaTimeInForce.IOC,
            TimeInForce.FOK: AlpacaTimeInForce.FOK
        }
        result = mapping.get(tif)
        if result is None:
            raise ValueError(f"Unknown time in force: {tif}")
        return result

    @staticmethod
    def _convert_alpaca_tif_to_time_in_force(tif: AlpacaTimeInForce) -> TimeInForce:
        """Convert Alpaca TimeInForce to TimeInForce"""
        mapping = {
            AlpacaTimeInForce.DAY: TimeInForce.DAY,
            AlpacaTimeInForce.GTC: TimeInForce.GTC,
            AlpacaTimeInForce.IOC: TimeInForce.IOC,
            AlpacaTimeInForce.FOK: TimeInForce.FOK
        }
        result = mapping.get(tif)
        if result is None:
            raise ValueError(f"Unknown Alpaca time in force: {tif}")
        return result

    @staticmethod
    def _convert_alpaca_type_to_order_type(order_type: AlpacaOrderType) -> OrderType:
        """Convert Alpaca OrderType to OrderType"""
        mapping = {
            AlpacaOrderType.MARKET: OrderType.MARKET,
            AlpacaOrderType.LIMIT: OrderType.LIMIT,
            AlpacaOrderType.STOP: OrderType.STOP_LOSS,
            AlpacaOrderType.STOP_LIMIT: OrderType.STOP_LIMIT
        }
        result = mapping.get(order_type)
        if result is None:
            raise ValueError(f"Unknown Alpaca order type: {order_type}")
        return result

    @staticmethod
    def _convert_alpaca_status_to_order_status(status: AlpacaOrderStatus) -> OrderStatus:
        """Convert Alpaca OrderStatus to OrderStatus"""
        mapping = {
            AlpacaOrderStatus.NEW: OrderStatus.PENDING,
            AlpacaOrderStatus.PARTIALLY_FILLED: OrderStatus.PARTIALLY_FILLED,
            AlpacaOrderStatus.FILLED: OrderStatus.FILLED,
            AlpacaOrderStatus.DONE_FOR_DAY: OrderStatus.CANCELLED,
            AlpacaOrderStatus.CANCELED: OrderStatus.CANCELLED,
            AlpacaOrderStatus.EXPIRED: OrderStatus.CANCELLED,
            AlpacaOrderStatus.REPLACED: OrderStatus.PENDING,
            AlpacaOrderStatus.PENDING_CANCEL: OrderStatus.PENDING,
            AlpacaOrderStatus.PENDING_REPLACE: OrderStatus.PENDING,
            AlpacaOrderStatus.ACCEPTED: OrderStatus.PENDING,
            AlpacaOrderStatus.PENDING_NEW: OrderStatus.PENDING,
            AlpacaOrderStatus.ACCEPTED_FOR_BIDDING: OrderStatus.PENDING,
            AlpacaOrderStatus.STOPPED: OrderStatus.CANCELLED,
            AlpacaOrderStatus.REJECTED: OrderStatus.REJECTED,
            AlpacaOrderStatus.SUSPENDED: OrderStatus.CANCELLED,
            AlpacaOrderStatus.CALCULATED: OrderStatus.PENDING
        }
        return mapping.get(status, OrderStatus.PENDING)

    @staticmethod
    def _convert_alpaca_position_side(side: AlpacaPositionSide) -> PositionSide:
        """Convert Alpaca PositionSide to PositionSide"""
        mapping = {
            AlpacaPositionSide.LONG: PositionSide.LONG,
            AlpacaPositionSide.SHORT: PositionSide.SHORT
        }
        result = mapping.get(side)
        if result is None:
            raise ValueError(f"Unknown Alpaca position side: {side}")
        return result

    @staticmethod
    def _convert_timeframe(timeframe: str) -> TimeFrame:
        """Convert string timeframe to Alpaca TimeFrame"""
        timeframe_map = {
            "1Min": TimeFrame.Minute,
            "5Min": TimeFrame(5, TimeFrame.Minute),
            "15Min": TimeFrame(15, TimeFrame.Minute),
            "30Min": TimeFrame(30, TimeFrame.Minute),
            "1Hour": TimeFrame.Hour,
            "1Day": TimeFrame.Day,
            "1Week": TimeFrame.Week,
            "1Month": TimeFrame.Month
        }
        return timeframe_map.get(timeframe, TimeFrame.Day)
