"""
Alpaca API integration for trading operations using alpaca-py package.
"""

import logging
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.trading.requests import (
    MarketOrderRequest, LimitOrderRequest, StopOrderRequest, StopLimitOrderRequest,
    GetOrdersRequest, ClosePositionRequest, GetPortfolioHistoryRequest
)
from alpaca.trading.enums import (
    OrderSide as AlpacaOrderSide, 
    OrderType as AlpacaOrderType, 
    TimeInForce as AlpacaTimeInForce,
    OrderStatus as AlpacaOrderStatus,
    PositionSide as AlpacaPositionSide
)
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest, StockLatestTradeRequest
from alpaca.data.timeframe import TimeFrame
from src.models.trading_models import (
    Order, Portfolio, Position, MarketData, OrderSide, OrderType, 
    OrderStatus, TimeInForce, PositionSide
)
from config import settings

logger = logging.getLogger(__name__)


class AlpacaAPI:
    """Alpaca API wrapper for trading operations using alpaca-py"""
    
    def __init__(self):
        """Initialize Alpaca clients"""
        try:
            # Initialize trading client for orders and account management
            self.trading_client = TradingClient(
                api_key=settings.alpaca_api_key,
                secret_key=settings.alpaca_secret_key,
                paper=settings.paper_trading
            )
            
            # Initialize data client for market data (no auth required for basic data)
            self.data_client = StockHistoricalDataClient(
                api_key=settings.alpaca_api_key,
                secret_key=settings.alpaca_secret_key
            )
            
            logger.info("Alpaca API clients initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Alpaca API: {e}")
            raise
    
    async def get_account(self) -> Optional[Dict[str, Any]]:
        """Get account information"""
        try:
            account = self.trading_client.get_account()
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
    
    async def get_positions(self) -> List[Position]:
        """Get current positions"""
        try:
            positions_response = self.trading_client.get_all_positions()
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
    
    async def get_portfolio(self) -> Optional[Portfolio]:
        """Get current portfolio information"""
        try:
            account_info = await self.get_account()
            if not account_info:
                return None
                
            positions = await self.get_positions()
            
            # Calculate P&L (simplified)
            total_pnl = sum(pos.unrealized_pnl for pos in positions)
            
            portfolio = Portfolio(
                equity=account_info["equity"],
                cash=account_info["cash"],
                market_value=account_info["portfolio_value"],
                day_trade_count=0,  # Not directly available in alpaca-py
                buying_power=account_info["buying_power"],
                positions=positions,
                total_pnl=total_pnl,
                day_pnl=Decimal("0")  # Would need historical data to calculate
            )
            
            return portfolio
            
        except Exception as e:
            logger.error(f"Failed to get portfolio: {e}")
            return None
    
    async def submit_order(self, order: Order) -> Optional[str]:
        """Submit a new order"""
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
                request = StopOrderRequest(
                    symbol=order.symbol,
                    qty=float(order.quantity),
                    side=self._convert_order_side_to_alpaca(order.side),
                    time_in_force=self._convert_time_in_force_to_alpaca(order.time_in_force),
                    stop_price=float(order.stop_loss) if order.stop_loss else float(order.stop_price)
                )
            else:
                logger.error(f"Unsupported order type: {order.order_type}")
                return None
            
            # Submit order
            alpaca_order = self.trading_client.submit_order(request)
            
            logger.info(f"Order submitted: {alpaca_order.id} - {order.symbol} {order.side} {order.quantity}")
            return alpaca_order.id
            
        except Exception as e:
            logger.error(f"Failed to submit order: {e}")
            return None
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order"""
        try:
            self.trading_client.cancel_order_by_id(order_id)
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    async def get_orders(self, status: Optional[str] = None) -> List[Order]:
        """Get list of orders"""
        try:
            # Create request
            request = GetOrdersRequest(
                status=status,
                limit=100
            )
            
            alpaca_orders = self.trading_client.get_orders(request)
            orders = []
            
            for alpaca_order in alpaca_orders:
                order = Order(
                    id=alpaca_order.id,
                    symbol=alpaca_order.symbol,
                    side=self._convert_alpaca_side_to_order_side(alpaca_order.side),
                    order_type=self._convert_alpaca_type_to_order_type(alpaca_order.order_type),
                    quantity=Decimal(str(alpaca_order.qty)),
                    price=Decimal(str(alpaca_order.limit_price)) if alpaca_order.limit_price else None,
                    stop_price=Decimal(str(alpaca_order.stop_price)) if alpaca_order.stop_price else None,
                    time_in_force=self._convert_alpaca_tif_to_time_in_force(alpaca_order.time_in_force),
                    status=self._convert_alpaca_status_to_order_status(alpaca_order.status),
                    filled_quantity=Decimal(str(alpaca_order.filled_qty)) if alpaca_order.filled_qty else Decimal("0"),
                    filled_price=Decimal(str(alpaca_order.filled_avg_price)) if alpaca_order.filled_avg_price else None,
                    created_at=alpaca_order.created_at,
                    updated_at=alpaca_order.updated_at
                )
                orders.append(order)
            
            return orders
            
        except Exception as e:
            logger.error(f"Failed to get orders: {e}")
            return []
    
    async def get_order(self, order_id: str) -> Optional[Order]:
        """Get specific order by ID"""
        try:
            alpaca_order = self.trading_client.get_order_by_id(order_id)
            
            order = Order(
                id=alpaca_order.id,
                symbol=alpaca_order.symbol,
                side=self._convert_alpaca_side_to_order_side(alpaca_order.side),
                order_type=self._convert_alpaca_type_to_order_type(alpaca_order.order_type),
                quantity=Decimal(str(alpaca_order.qty)),
                price=Decimal(str(alpaca_order.limit_price)) if alpaca_order.limit_price else None,
                stop_price=Decimal(str(alpaca_order.stop_price)) if alpaca_order.stop_price else None,
                time_in_force=self._convert_alpaca_tif_to_time_in_force(alpaca_order.time_in_force),
                status=self._convert_alpaca_status_to_order_status(alpaca_order.status),
                filled_quantity=Decimal(str(alpaca_order.filled_qty)) if alpaca_order.filled_qty else Decimal("0"),
                filled_price=Decimal(str(alpaca_order.filled_avg_price)) if alpaca_order.filled_avg_price else None,
                created_at=alpaca_order.created_at,
                updated_at=alpaca_order.updated_at
            )
            
            return order
            
        except Exception as e:
            logger.error(f"Failed to get order {order_id}: {e}")
            return None
    
    async def get_market_data(self, symbol: str, timeframe: str = "1Day", limit: int = 100) -> List[Dict[str, Any]]:
        """Get historical market data"""
        try:
            # Convert timeframe string to TimeFrame enum
            tf = self._convert_timeframe(timeframe)
            
            # Create request for historical bars
            request = StockBarsRequest(
                symbol_or_symbols=[symbol],
                timeframe=tf,
                limit=limit
            )
            
            bars_response = self.data_client.get_stock_bars(request)
            bars_data = []
            
            if symbol in bars_response.data:
                for bar in bars_response.data[symbol]:
                    bars_data.append({
                        "symbol": symbol,
                        "timestamp": bar.timestamp,
                        "open": float(bar.open),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "close": float(bar.close),
                        "volume": int(bar.volume)
                    })
            
            return bars_data
            
        except Exception as e:
            logger.error(f"Failed to get market data for {symbol}: {e}")
            return []
    
    async def is_market_open(self) -> bool:
        """Check if market is currently open"""
        try:
            clock = self.trading_client.get_clock()
            return clock.is_open
        except Exception as e:
            logger.error(f"Failed to get market status: {e}")
            return False
    
    # Helper methods for enum conversions
    @staticmethod
    def _convert_order_side_to_alpaca(side: OrderSide) -> AlpacaOrderSide:
        """Convert OrderSide to Alpaca OrderSide"""
        mapping = {
            OrderSide.BUY: AlpacaOrderSide.BUY,
            OrderSide.SELL: AlpacaOrderSide.SELL
        }
        return mapping[side]
    
    @staticmethod
    def _convert_alpaca_side_to_order_side(side: AlpacaOrderSide) -> OrderSide:
        """Convert Alpaca OrderSide to OrderSide"""
        mapping = {
            AlpacaOrderSide.BUY: OrderSide.BUY,
            AlpacaOrderSide.SELL: OrderSide.SELL
        }
        return mapping[side]
    
    @staticmethod
    def _convert_time_in_force_to_alpaca(tif: TimeInForce) -> AlpacaTimeInForce:
        """Convert TimeInForce to Alpaca TimeInForce"""
        mapping = {
            TimeInForce.DAY: AlpacaTimeInForce.DAY,
            TimeInForce.GTC: AlpacaTimeInForce.GTC,
            TimeInForce.IOC: AlpacaTimeInForce.IOC,
            TimeInForce.FOK: AlpacaTimeInForce.FOK
        }
        return mapping.get(tif, AlpacaTimeInForce.DAY)
    
    @staticmethod
    def _convert_alpaca_tif_to_time_in_force(tif: AlpacaTimeInForce) -> TimeInForce:
        """Convert Alpaca TimeInForce to TimeInForce"""
        mapping = {
            AlpacaTimeInForce.DAY: TimeInForce.DAY,
            AlpacaTimeInForce.GTC: TimeInForce.GTC,
            AlpacaTimeInForce.IOC: TimeInForce.IOC,
            AlpacaTimeInForce.FOK: TimeInForce.FOK
        }
        return mapping.get(tif, TimeInForce.DAY)
    
    @staticmethod
    def _convert_alpaca_type_to_order_type(order_type: AlpacaOrderType) -> OrderType:
        """Convert Alpaca OrderType to OrderType"""
        mapping = {
            AlpacaOrderType.MARKET: OrderType.MARKET,
            AlpacaOrderType.LIMIT: OrderType.LIMIT,
            AlpacaOrderType.STOP: OrderType.STOP_LOSS,
            AlpacaOrderType.STOP_LIMIT: OrderType.STOP_LIMIT
        }
        return mapping.get(order_type, OrderType.MARKET)
    
    @staticmethod
    def _convert_alpaca_status_to_order_status(status: AlpacaOrderStatus) -> OrderStatus:
        """Convert Alpaca OrderStatus to OrderStatus"""
        mapping = {
            AlpacaOrderStatus.NEW: OrderStatus.SUBMITTED,
            AlpacaOrderStatus.PARTIALLY_FILLED: OrderStatus.PARTIALLY_FILLED,
            AlpacaOrderStatus.FILLED: OrderStatus.FILLED,
            AlpacaOrderStatus.DONE_FOR_DAY: OrderStatus.CANCELLED,
            AlpacaOrderStatus.CANCELED: OrderStatus.CANCELLED,
            AlpacaOrderStatus.EXPIRED: OrderStatus.CANCELLED,
            AlpacaOrderStatus.REPLACED: OrderStatus.SUBMITTED,
            AlpacaOrderStatus.PENDING_CANCEL: OrderStatus.PENDING,
            AlpacaOrderStatus.PENDING_REPLACE: OrderStatus.PENDING,
            AlpacaOrderStatus.ACCEPTED: OrderStatus.SUBMITTED,
            AlpacaOrderStatus.PENDING_NEW: OrderStatus.PENDING,
            AlpacaOrderStatus.ACCEPTED_FOR_BIDDING: OrderStatus.SUBMITTED,
            AlpacaOrderStatus.STOPPED: OrderStatus.CANCELLED,
            AlpacaOrderStatus.REJECTED: OrderStatus.REJECTED,
            AlpacaOrderStatus.SUSPENDED: OrderStatus.PENDING,
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
        return mapping.get(side, PositionSide.LONG)
    
    @staticmethod
    def _convert_timeframe(timeframe: str) -> TimeFrame:
        """Convert timeframe string to Alpaca TimeFrame"""
        mapping = {
            "1Min": TimeFrame.Minute,
            "5Min": TimeFrame(5, "Minute"),
            "15Min": TimeFrame(15, "Minute"),
            "30Min": TimeFrame(30, "Minute"),
            "1Hour": TimeFrame.Hour,
            "1Day": TimeFrame.Day,
            "1Week": TimeFrame.Week,
            "1Month": TimeFrame.Month
        }
        return mapping.get(timeframe, TimeFrame.Day)
    
    @staticmethod
    def _parse_timestamp(timestamp_str: str) -> datetime:
        """Parse timestamp string to datetime"""
        try:
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except ValueError:
            return datetime.now(timezone.utc) 