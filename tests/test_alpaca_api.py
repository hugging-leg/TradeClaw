"""
Unit tests for Alpaca API integration using alpaca-py package.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from decimal import Decimal
from datetime import datetime, timezone
from alpaca.trading.enums import OrderSide as AlpacaOrderSide, OrderType as AlpacaOrderType, OrderStatus as AlpacaOrderStatus
from alpaca.trading.enums import TimeInForce as AlpacaTimeInForce, PositionSide as AlpacaPositionSide
from src.apis.alpaca_api import AlpacaAPI
from src.models.trading_models import (
    Order, Position, Portfolio, OrderSide, OrderType, 
    OrderStatus, TimeInForce, PositionSide
)


class TestAlpacaAPI:
    """Test suite for AlpacaAPI class"""
    
    @pytest.fixture
    def mock_trading_client(self):
        """Mock TradingClient"""
        with patch('src.apis.alpaca_api.TradingClient') as mock_client:
            mock_instance = Mock()
            mock_client.return_value = mock_instance
            
            # Mock account
            mock_account = Mock()
            mock_account.status = "ACTIVE"
            mock_account.equity = 100000.0
            mock_account.cash = 50000.0
            mock_account.portfolio_value = 100000.0
            mock_account.daytrading_buying_power = 200000.0
            mock_account.regt_buying_power = 100000.0
            mock_account.buying_power = 100000.0
            mock_account.trade_suspended_by_user = False
            mock_account.transfers_blocked = False
            mock_instance.get_account.return_value = mock_account
            
            yield mock_instance
    
    @pytest.fixture
    def mock_data_client(self):
        """Mock StockHistoricalDataClient"""
        with patch('src.apis.alpaca_api.StockHistoricalDataClient') as mock_client:
            mock_instance = Mock()
            mock_client.return_value = mock_instance
            yield mock_instance
    
    @pytest.fixture
    def alpaca_api(self, mock_trading_client, mock_data_client):
        """Create AlpacaAPI instance with mocked clients"""
        return AlpacaAPI()
    
    @pytest.mark.asyncio
    async def test_get_account(self, alpaca_api, mock_trading_client):
        """Test getting account information"""
        account_info = await alpaca_api.get_account()
        
        assert account_info is not None
        assert account_info["equity"] == Decimal("100000.0")
        assert account_info["cash"] == Decimal("50000.0")
        assert account_info["portfolio_value"] == Decimal("100000.0")
        assert account_info["status"] == "ACTIVE"
        assert account_info["trade_suspended_by_user"] is False
        
        mock_trading_client.get_account.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_account_failure(self, alpaca_api, mock_trading_client):
        """Test account retrieval failure"""
        mock_trading_client.get_account.side_effect = Exception("API Error")
        
        account_info = await alpaca_api.get_account()
        assert account_info is None
    
    @pytest.mark.asyncio
    async def test_get_positions(self, alpaca_api, mock_trading_client):
        """Test getting positions"""
        # Mock position data
        mock_position = Mock()
        mock_position.symbol = "AAPL"
        mock_position.qty = 100
        mock_position.market_value = 15000.0
        mock_position.cost_basis = 14000.0
        mock_position.unrealized_pl = 1000.0
        mock_position.unrealized_plpc = 0.0714
        mock_position.side = AlpacaPositionSide.LONG
        mock_position.avg_entry_price = 140.0
        
        mock_trading_client.get_all_positions.return_value = [mock_position]
        
        positions = await alpaca_api.get_positions()
        
        assert len(positions) == 1
        position = positions[0]
        assert position.symbol == "AAPL"
        assert position.quantity == Decimal("100")
        assert position.market_value == Decimal("15000.0")
        assert position.cost_basis == Decimal("14000.0")
        assert position.unrealized_pnl == Decimal("1000.0")
        assert position.side == PositionSide.LONG
        assert position.avg_entry_price == Decimal("140.0")
        
        mock_trading_client.get_all_positions.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_positions_failure(self, alpaca_api, mock_trading_client):
        """Test positions retrieval failure"""
        mock_trading_client.get_all_positions.side_effect = Exception("API Error")
        
        positions = await alpaca_api.get_positions()
        assert positions == []
    
    @pytest.mark.asyncio
    async def test_get_portfolio(self, alpaca_api, mock_trading_client):
        """Test getting portfolio"""
        # Mock position
        mock_position = Mock()
        mock_position.symbol = "AAPL"
        mock_position.qty = 100
        mock_position.market_value = 15000.0
        mock_position.cost_basis = 14000.0
        mock_position.unrealized_pl = 1000.0
        mock_position.unrealized_plpc = 0.0714
        mock_position.side = AlpacaPositionSide.LONG
        mock_position.avg_entry_price = 140.0
        
        mock_trading_client.get_all_positions.return_value = [mock_position]
        
        portfolio = await alpaca_api.get_portfolio()
        
        assert portfolio is not None
        assert portfolio.equity == Decimal("100000.0")
        assert portfolio.cash == Decimal("50000.0")
        assert portfolio.market_value == Decimal("100000.0")
        assert portfolio.buying_power == Decimal("100000.0")
        assert len(portfolio.positions) == 1
        assert portfolio.total_pnl == Decimal("1000.0")
        assert portfolio.day_trade_count == 0
    
    @pytest.mark.asyncio
    async def test_submit_market_order(self, alpaca_api, mock_trading_client):
        """Test submitting a market order"""
        # Mock order response
        mock_order = Mock()
        mock_order.id = "order_123"
        mock_trading_client.submit_order.return_value = mock_order
        
        order = Order(
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("100"),
            time_in_force=TimeInForce.DAY
        )
        
        order_id = await alpaca_api.submit_order(order)
        
        assert order_id == "order_123"
        mock_trading_client.submit_order.assert_called_once()
        
        # Verify the request was created correctly
        call_args = mock_trading_client.submit_order.call_args[0][0]
        assert call_args.symbol == "AAPL"
        assert call_args.qty == 100.0
        assert call_args.side == AlpacaOrderSide.BUY
        assert call_args.time_in_force == AlpacaTimeInForce.DAY
    
    @pytest.mark.asyncio
    async def test_submit_limit_order(self, alpaca_api, mock_trading_client):
        """Test submitting a limit order"""
        mock_order = Mock()
        mock_order.id = "order_456"
        mock_trading_client.submit_order.return_value = mock_order
        
        order = Order(
            symbol="TSLA",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=Decimal("50"),
            price=Decimal("800.00"),
            time_in_force=TimeInForce.GTC
        )
        
        order_id = await alpaca_api.submit_order(order)
        
        assert order_id == "order_456"
        mock_trading_client.submit_order.assert_called_once()
        
        # Verify the request was created correctly
        call_args = mock_trading_client.submit_order.call_args[0][0]
        assert call_args.symbol == "TSLA"
        assert call_args.qty == 50.0
        assert call_args.side == AlpacaOrderSide.SELL
        assert call_args.limit_price == 800.0
        assert call_args.time_in_force == AlpacaTimeInForce.GTC
    
    @pytest.mark.asyncio
    async def test_submit_stop_order(self, alpaca_api, mock_trading_client):
        """Test submitting a stop order"""
        mock_order = Mock()
        mock_order.id = "order_789"
        mock_trading_client.submit_order.return_value = mock_order
        
        order = Order(
            symbol="MSFT",
            side=OrderSide.SELL,
            order_type=OrderType.STOP_LOSS,
            quantity=Decimal("25"),
            stop_loss=Decimal("290.00"),
            time_in_force=TimeInForce.DAY
        )
        
        order_id = await alpaca_api.submit_order(order)
        
        assert order_id == "order_789"
        mock_trading_client.submit_order.assert_called_once()
        
        # Verify the request was created correctly
        call_args = mock_trading_client.submit_order.call_args[0][0]
        assert call_args.symbol == "MSFT"
        assert call_args.qty == 25.0
        assert call_args.side == AlpacaOrderSide.SELL
        assert call_args.stop_price == 290.0
        assert call_args.time_in_force == AlpacaTimeInForce.DAY
    
    @pytest.mark.asyncio
    async def test_submit_order_failure(self, alpaca_api, mock_trading_client):
        """Test order submission failure"""
        mock_trading_client.submit_order.side_effect = Exception("API Error")
        
        order = Order(
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("100"),
            time_in_force=TimeInForce.DAY
        )
        
        order_id = await alpaca_api.submit_order(order)
        assert order_id is None
    
    @pytest.mark.asyncio
    async def test_cancel_order(self, alpaca_api, mock_trading_client):
        """Test canceling an order"""
        mock_trading_client.cancel_order_by_id.return_value = None
        
        result = await alpaca_api.cancel_order("order_123")
        
        assert result is True
        mock_trading_client.cancel_order_by_id.assert_called_once_with("order_123")
    
    @pytest.mark.asyncio
    async def test_cancel_order_failure(self, alpaca_api, mock_trading_client):
        """Test order cancellation failure"""
        mock_trading_client.cancel_order_by_id.side_effect = Exception("API Error")
        
        result = await alpaca_api.cancel_order("order_123")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_get_orders(self, alpaca_api, mock_trading_client):
        """Test getting orders"""
        # Mock order data
        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.symbol = "AAPL"
        mock_order.side = AlpacaOrderSide.BUY
        mock_order.order_type = AlpacaOrderType.MARKET
        mock_order.qty = 100
        mock_order.limit_price = None
        mock_order.stop_price = None
        mock_order.time_in_force = AlpacaTimeInForce.DAY
        mock_order.status = AlpacaOrderStatus.FILLED
        mock_order.filled_qty = 100
        mock_order.filled_avg_price = 150.0
        mock_order.created_at = datetime.now(timezone.utc)
        mock_order.updated_at = datetime.now(timezone.utc)
        
        mock_trading_client.get_orders.return_value = [mock_order]
        
        orders = await alpaca_api.get_orders()
        
        assert len(orders) == 1
        order = orders[0]
        assert order.id == "order_123"
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.MARKET
        assert order.quantity == Decimal("100")
        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == Decimal("100")
        assert order.filled_price == Decimal("150.0")
        
        mock_trading_client.get_orders.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_order_by_id(self, alpaca_api, mock_trading_client):
        """Test getting specific order by ID"""
        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.symbol = "AAPL"
        mock_order.side = AlpacaOrderSide.BUY
        mock_order.order_type = AlpacaOrderType.LIMIT
        mock_order.qty = 100
        mock_order.limit_price = 150.0
        mock_order.stop_price = None
        mock_order.time_in_force = AlpacaTimeInForce.GTC
        mock_order.status = AlpacaOrderStatus.NEW
        mock_order.filled_qty = 0
        mock_order.filled_avg_price = None
        mock_order.created_at = datetime.now(timezone.utc)
        mock_order.updated_at = datetime.now(timezone.utc)
        
        mock_trading_client.get_order_by_id.return_value = mock_order
        
        order = await alpaca_api.get_order("order_123")
        
        assert order is not None
        assert order.id == "order_123"
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.LIMIT
        assert order.price == Decimal("150.0")
        assert order.status == OrderStatus.SUBMITTED
        assert order.filled_quantity == Decimal("0")
        
        mock_trading_client.get_order_by_id.assert_called_once_with("order_123")
    
    @pytest.mark.asyncio
    async def test_get_market_data(self, alpaca_api, mock_data_client):
        """Test getting market data"""
        # Mock bar data
        mock_bar = Mock()
        mock_bar.timestamp = datetime.now(timezone.utc)
        mock_bar.open = 150.0
        mock_bar.high = 155.0
        mock_bar.low = 149.0
        mock_bar.close = 152.0
        mock_bar.volume = 1000000
        
        mock_bars_response = Mock()
        mock_bars_response.data = {"AAPL": [mock_bar]}
        mock_data_client.get_stock_bars.return_value = mock_bars_response
        
        market_data = await alpaca_api.get_market_data("AAPL")
        
        assert len(market_data) == 1
        bar = market_data[0]
        assert bar["symbol"] == "AAPL"
        assert bar["open"] == 150.0
        assert bar["high"] == 155.0
        assert bar["low"] == 149.0
        assert bar["close"] == 152.0
        assert bar["volume"] == 1000000
        
        mock_data_client.get_stock_bars.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_market_data_failure(self, alpaca_api, mock_data_client):
        """Test market data retrieval failure"""
        mock_data_client.get_stock_bars.side_effect = Exception("API Error")
        
        market_data = await alpaca_api.get_market_data("AAPL")
        assert market_data == []
    
    @pytest.mark.asyncio
    async def test_is_market_open(self, alpaca_api, mock_trading_client):
        """Test checking if market is open"""
        mock_clock = Mock()
        mock_clock.is_open = True
        mock_trading_client.get_clock.return_value = mock_clock
        
        is_open = await alpaca_api.is_market_open()
        
        assert is_open is True
        mock_trading_client.get_clock.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_is_market_open_failure(self, alpaca_api, mock_trading_client):
        """Test market status check failure"""
        mock_trading_client.get_clock.side_effect = Exception("API Error")
        
        is_open = await alpaca_api.is_market_open()
        assert is_open is False
    
    # Test enum conversion methods
    def test_order_side_conversions(self):
        """Test order side enum conversions"""
        # Test to Alpaca
        assert AlpacaAPI._convert_order_side_to_alpaca(OrderSide.BUY) == AlpacaOrderSide.BUY
        assert AlpacaAPI._convert_order_side_to_alpaca(OrderSide.SELL) == AlpacaOrderSide.SELL
        
        # Test from Alpaca
        assert AlpacaAPI._convert_alpaca_side_to_order_side(AlpacaOrderSide.BUY) == OrderSide.BUY
        assert AlpacaAPI._convert_alpaca_side_to_order_side(AlpacaOrderSide.SELL) == OrderSide.SELL
    
    def test_time_in_force_conversions(self):
        """Test time in force enum conversions"""
        # Test to Alpaca
        assert AlpacaAPI._convert_time_in_force_to_alpaca(TimeInForce.DAY) == AlpacaTimeInForce.DAY
        assert AlpacaAPI._convert_time_in_force_to_alpaca(TimeInForce.GTC) == AlpacaTimeInForce.GTC
        
        # Test from Alpaca
        assert AlpacaAPI._convert_alpaca_tif_to_time_in_force(AlpacaTimeInForce.DAY) == TimeInForce.DAY
        assert AlpacaAPI._convert_alpaca_tif_to_time_in_force(AlpacaTimeInForce.GTC) == TimeInForce.GTC
    
    def test_order_type_conversions(self):
        """Test order type enum conversions"""
        assert AlpacaAPI._convert_alpaca_type_to_order_type(AlpacaOrderType.MARKET) == OrderType.MARKET
        assert AlpacaAPI._convert_alpaca_type_to_order_type(AlpacaOrderType.LIMIT) == OrderType.LIMIT
        assert AlpacaAPI._convert_alpaca_type_to_order_type(AlpacaOrderType.STOP) == OrderType.STOP_LOSS
    
    def test_order_status_conversions(self):
        """Test order status enum conversions"""
        assert AlpacaAPI._convert_alpaca_status_to_order_status(AlpacaOrderStatus.NEW) == OrderStatus.SUBMITTED
        assert AlpacaAPI._convert_alpaca_status_to_order_status(AlpacaOrderStatus.FILLED) == OrderStatus.FILLED
        assert AlpacaAPI._convert_alpaca_status_to_order_status(AlpacaOrderStatus.CANCELED) == OrderStatus.CANCELLED
    
    def test_position_side_conversions(self):
        """Test position side enum conversions"""
        assert AlpacaAPI._convert_alpaca_position_side(AlpacaPositionSide.LONG) == PositionSide.LONG
        assert AlpacaAPI._convert_alpaca_position_side(AlpacaPositionSide.SHORT) == PositionSide.SHORT
    
    def test_timeframe_conversions(self):
        """Test timeframe string conversions"""
        from alpaca.data.timeframe import TimeFrame
        
        # Test timeframe conversions by comparing their string representations
        assert str(AlpacaAPI._convert_timeframe("1Day")) == str(TimeFrame.Day)
        assert str(AlpacaAPI._convert_timeframe("1Hour")) == str(TimeFrame.Hour)
        assert str(AlpacaAPI._convert_timeframe("1Min")) == str(TimeFrame.Minute)
        assert str(AlpacaAPI._convert_timeframe("1Week")) == str(TimeFrame.Week)
        
        # Test that unknown timeframes default to Day
        assert str(AlpacaAPI._convert_timeframe("UnknownTimeframe")) == str(TimeFrame.Day)
    
    def test_initialization_failure(self):
        """Test API initialization failure"""
        with patch('src.apis.alpaca_api.TradingClient') as mock_client:
            mock_client.side_effect = Exception("Authentication failed")
            
            with pytest.raises(Exception, match="Authentication failed"):
                AlpacaAPI() 