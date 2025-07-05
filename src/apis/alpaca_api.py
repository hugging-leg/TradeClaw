import alpaca_trade_api as tradeapi
from typing import List, Optional, Dict, Any
from decimal import Decimal
from datetime import datetime, timedelta
import logging
from config import settings
from src.models.trading_models import (
    Order, Portfolio, Position, MarketData, OrderSide, OrderType, 
    OrderStatus, TimeInForce
)


logger = logging.getLogger(__name__)


class AlpacaAPI:
    """Alpaca API wrapper for trading operations"""
    
    def __init__(self):
        self.api = tradeapi.REST(
            settings.alpaca_api_key,
            settings.alpaca_secret_key,
            settings.alpaca_base_url,
            api_version='v2'
        )
        self.account = None
        self._initialize_account()
    
    def _initialize_account(self):
        """Initialize account information"""
        try:
            self.account = self.api.get_account()
            logger.info(f"Alpaca account initialized: {self.account.status}")
        except Exception as e:
            logger.error(f"Failed to initialize Alpaca account: {e}")
            raise
    
    def get_portfolio(self) -> Portfolio:
        """Get current portfolio information"""
        try:
            account = self.api.get_account()
            positions = self.api.list_positions()
            
            portfolio_positions = []
            for pos in positions:
                position = Position(
                    symbol=pos.symbol,
                    quantity=Decimal(str(pos.qty)),
                    market_value=Decimal(str(pos.market_value)),
                    cost_basis=Decimal(str(pos.cost_basis)),
                    unrealized_pnl=Decimal(str(pos.unrealized_pl)),
                    unrealized_pnl_percentage=Decimal(str(pos.unrealized_plpc)),
                    side=pos.side
                )
                portfolio_positions.append(position)
            
            portfolio = Portfolio(
                equity=Decimal(str(account.equity)),
                cash=Decimal(str(account.cash)),
                market_value=Decimal(str(account.portfolio_value)),
                day_trade_count=int(account.daytrade_count),
                buying_power=Decimal(str(account.buying_power)),
                positions=portfolio_positions,
                total_pnl=Decimal(str(account.equity)) - Decimal(str(account.last_equity)),
                day_pnl=Decimal(str(account.equity)) - Decimal(str(account.last_equity))
            )
            
            return portfolio
        except Exception as e:
            logger.error(f"Failed to get portfolio: {e}")
            raise
    
    def place_order(self, order: Order) -> Order:
        """Place a new order"""
        try:
            # Convert our order model to Alpaca format
            alpaca_order = self.api.submit_order(
                symbol=order.symbol,
                qty=str(order.quantity),
                side=order.side.value,
                type=order.order_type.value,
                time_in_force=order.time_in_force.value,
                limit_price=str(order.price) if order.price else None,
                stop_price=str(order.stop_price) if order.stop_price else None,
                client_order_id=order.client_order_id
            )
            
            # Update our order model with Alpaca response
            order.id = alpaca_order.id
            order.status = OrderStatus(alpaca_order.status)
            order.created_at = alpaca_order.created_at
            order.updated_at = alpaca_order.updated_at
            
            logger.info(f"Order placed: {order.symbol} {order.side} {order.quantity} @ {order.price}")
            return order
            
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            raise
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order"""
        try:
            self.api.cancel_order(order_id)
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    def get_orders(self, status: Optional[str] = None, limit: int = 100) -> List[Order]:
        """Get list of orders"""
        try:
            alpaca_orders = self.api.list_orders(
                status=status,
                limit=limit,
                nested=True
            )
            
            orders = []
            for alpaca_order in alpaca_orders:
                order = Order(
                    id=alpaca_order.id,
                    symbol=alpaca_order.symbol,
                    side=OrderSide(alpaca_order.side),
                    order_type=OrderType(alpaca_order.order_type),
                    quantity=Decimal(str(alpaca_order.qty)),
                    price=Decimal(str(alpaca_order.limit_price)) if alpaca_order.limit_price else None,
                    stop_price=Decimal(str(alpaca_order.stop_price)) if alpaca_order.stop_price else None,
                    time_in_force=TimeInForce(alpaca_order.time_in_force),
                    status=OrderStatus(alpaca_order.status),
                    filled_quantity=Decimal(str(alpaca_order.filled_qty)),
                    filled_price=Decimal(str(alpaca_order.filled_avg_price)) if alpaca_order.filled_avg_price else None,
                    created_at=alpaca_order.created_at,
                    updated_at=alpaca_order.updated_at,
                    client_order_id=alpaca_order.client_order_id
                )
                orders.append(order)
            
            return orders
            
        except Exception as e:
            logger.error(f"Failed to get orders: {e}")
            raise
    
    def get_market_data(self, symbol: str) -> MarketData:
        """Get current market data for a symbol"""
        try:
            # Get latest quote
            latest_quote = self.api.get_latest_quote(symbol)
            
            market_data = MarketData(
                symbol=symbol,
                price=Decimal(str((latest_quote.bid_price + latest_quote.ask_price) / 2)),
                bid=Decimal(str(latest_quote.bid_price)),
                ask=Decimal(str(latest_quote.ask_price)),
                volume=latest_quote.bid_size + latest_quote.ask_size,
                timestamp=latest_quote.timestamp
            )
            
            return market_data
            
        except Exception as e:
            logger.error(f"Failed to get market data for {symbol}: {e}")
            raise
    
    def get_historical_data(self, symbol: str, timeframe: str = "1Day", limit: int = 100) -> List[Dict[str, Any]]:
        """Get historical price data"""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=limit)
            
            bars = self.api.get_bars(
                symbol,
                timeframe,
                start=start_date.isoformat(),
                end=end_date.isoformat(),
                limit=limit
            )
            
            historical_data = []
            for bar in bars:
                historical_data.append({
                    'timestamp': bar.timestamp,
                    'open': float(bar.open),
                    'high': float(bar.high),
                    'low': float(bar.low),
                    'close': float(bar.close),
                    'volume': int(bar.volume)
                })
            
            return historical_data
            
        except Exception as e:
            logger.error(f"Failed to get historical data for {symbol}: {e}")
            raise
    
    def is_market_open(self) -> bool:
        """Check if market is currently open"""
        try:
            clock = self.api.get_clock()
            return clock.is_open
        except Exception as e:
            logger.error(f"Failed to check market status: {e}")
            return False
    
    def get_market_calendar(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Get market calendar"""
        try:
            calendar = self.api.get_calendar(
                start=start_date.date(),
                end=end_date.date()
            )
            
            return [
                {
                    'date': day.date,
                    'open': day.open,
                    'close': day.close
                }
                for day in calendar
            ]
            
        except Exception as e:
            logger.error(f"Failed to get market calendar: {e}")
            raise 