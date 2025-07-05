"""
Unit tests for trading models.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone
from src.models.trading_models import (
    Order, OrderStatus, OrderType, OrderSide, TimeInForce,
    Position, PositionSide, Portfolio, TradingDecision, TradingAction,
    NewsItem, TradingEvent
)


class TestOrder:
    """Test Order model."""
    
    def test_order_creation(self):
        """Test creating an order."""
        order = Order(
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("100"),
            time_in_force=TimeInForce.DAY
        )
        
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.MARKET
        assert order.quantity == Decimal("100")
        assert order.time_in_force == TimeInForce.DAY
        assert order.status == OrderStatus.PENDING
        assert order.filled_quantity == Decimal("0")
        assert order.filled_price is None
        assert order.created_at is not None
        assert order.updated_at is not None
    
    def test_limit_order_creation(self):
        """Test creating a limit order."""
        order = Order(
            symbol="TSLA",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=Decimal("50"),
            price=Decimal("200.50"),
            time_in_force=TimeInForce.GTC
        )
        
        assert order.symbol == "TSLA"
        assert order.price == Decimal("200.50")
        assert order.time_in_force == TimeInForce.GTC
    
    def test_stop_loss_order_creation(self):
        """Test creating a stop loss order."""
        order = Order(
            symbol="MSFT",
            side=OrderSide.SELL,
            order_type=OrderType.STOP_LOSS,
            quantity=Decimal("25"),
            stop_loss=Decimal("150.00")
        )
        
        assert order.stop_loss == Decimal("150.00")
    
    def test_order_filled_percentage(self):
        """Test order filled percentage calculation."""
        order = Order(
            symbol="GOOGL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("100"),
            filled_quantity=Decimal("75")
        )
        
        assert order.filled_percentage == Decimal("75.0")
    
    def test_order_is_filled(self):
        """Test order is_filled property."""
        order = Order(
            symbol="AMZN",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("100"),
            filled_quantity=Decimal("100"),
            status=OrderStatus.FILLED
        )
        
        assert order.is_filled is True
    
    def test_order_is_not_filled(self):
        """Test order is_filled property when not filled."""
        order = Order(
            symbol="AMZN",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("100"),
            filled_quantity=Decimal("50"),
            status=OrderStatus.PARTIALLY_FILLED
        )
        
        assert order.is_filled is False


class TestPosition:
    """Test Position model."""
    
    def test_position_creation(self):
        """Test creating a position."""
        position = Position(
            symbol="AAPL",
            quantity=Decimal("100"),
            market_value=Decimal("15000.00"),
            avg_entry_price=Decimal("150.00"),
            side=PositionSide.LONG
        )
        
        assert position.symbol == "AAPL"
        assert position.quantity == Decimal("100")
        assert position.market_value == Decimal("15000.00")
        assert position.avg_entry_price == Decimal("150.00")
        assert position.side == PositionSide.LONG
        assert position.unrealized_pnl == Decimal("0.00")
    
    def test_position_with_unrealized_pnl(self):
        """Test position with unrealized P&L."""
        position = Position(
            symbol="TSLA",
            quantity=Decimal("50"),
            market_value=Decimal("10000.00"),
            avg_entry_price=Decimal("180.00"),
            side=PositionSide.LONG,
            unrealized_pnl=Decimal("1000.00")
        )
        
        assert position.unrealized_pnl == Decimal("1000.00")
    
    def test_short_position(self):
        """Test creating a short position."""
        position = Position(
            symbol="NFLX",
            quantity=Decimal("-25"),
            market_value=Decimal("-12500.00"),
            avg_entry_price=Decimal("500.00"),
            side=PositionSide.SHORT,
            unrealized_pnl=Decimal("-500.00")
        )
        
        assert position.side == PositionSide.SHORT
        assert position.quantity == Decimal("-25")
        assert position.unrealized_pnl == Decimal("-500.00")


class TestPortfolio:
    """Test Portfolio model."""
    
    def test_portfolio_creation(self):
        """Test creating a portfolio."""
        positions = [
            Position(
                symbol="AAPL",
                quantity=Decimal("100"),
                market_value=Decimal("15000.00"),
                avg_entry_price=Decimal("150.00"),
                side=PositionSide.LONG
            ),
            Position(
                symbol="GOOGL",
                quantity=Decimal("10"),
                market_value=Decimal("2500.00"),
                avg_entry_price=Decimal("2500.00"),
                side=PositionSide.LONG
            )
        ]
        
        portfolio = Portfolio(
            equity=Decimal("25000.00"),
            cash=Decimal("7500.00"),
            market_value=Decimal("17500.00"),
            day_pnl=Decimal("500.00"),
            total_pnl=Decimal("2500.00"),
            positions=positions
        )
        
        assert portfolio.equity == Decimal("25000.00")
        assert portfolio.cash == Decimal("7500.00")
        assert portfolio.market_value == Decimal("17500.00")
        assert portfolio.day_pnl == Decimal("500.00")
        assert portfolio.total_pnl == Decimal("2500.00")
        assert len(portfolio.positions) == 2
    
    def test_empty_portfolio(self):
        """Test creating an empty portfolio."""
        portfolio = Portfolio(
            equity=Decimal("10000.00"),
            cash=Decimal("10000.00"),
            market_value=Decimal("0.00"),
            day_pnl=Decimal("0.00"),
            total_pnl=Decimal("0.00"),
            positions=[]
        )
        
        assert len(portfolio.positions) == 0
        assert portfolio.market_value == Decimal("0.00")


class TestTradingDecision:
    """Test TradingDecision model."""
    
    def test_trading_decision_creation(self):
        """Test creating a trading decision."""
        decision = TradingDecision(
            symbol="AAPL",
            action=TradingAction.BUY,
            quantity=Decimal("100"),
            confidence=Decimal("0.85"),
            reasoning="Strong earnings report and positive outlook"
        )
        
        assert decision.symbol == "AAPL"
        assert decision.action == TradingAction.BUY
        assert decision.quantity == Decimal("100")
        assert decision.confidence == Decimal("0.85")
        assert decision.reasoning == "Strong earnings report and positive outlook"
        assert decision.created_at is not None
    
    def test_hold_decision(self):
        """Test creating a hold decision."""
        decision = TradingDecision(
            symbol="TSLA",
            action=TradingAction.HOLD,
            confidence=Decimal("0.60"),
            reasoning="Neutral market conditions"
        )
        
        assert decision.action == TradingAction.HOLD
        assert decision.quantity is None
    
    def test_sell_decision(self):
        """Test creating a sell decision."""
        decision = TradingDecision(
            symbol="MSFT",
            action=TradingAction.SELL,
            quantity=Decimal("50"),
            confidence=Decimal("0.90"),
            reasoning="Profit taking after strong run"
        )
        
        assert decision.action == TradingAction.SELL
        assert decision.quantity == Decimal("50")


class TestNewsItem:
    """Test NewsItem model."""
    
    def test_news_item_creation(self):
        """Test creating a news item."""
        news_item = NewsItem(
            title="Apple Reports Strong Q4 Earnings",
            description="Apple Inc. reported quarterly earnings that beat analyst expectations",
            url="https://example.com/news/apple-earnings",
            source="Reuters",
            symbols=["AAPL"],
            sentiment=Decimal("0.75"),
            published_at=datetime(2023, 10, 30, 16, 0, tzinfo=timezone.utc)
        )
        
        assert news_item.title == "Apple Reports Strong Q4 Earnings"
        assert news_item.symbols == ["AAPL"]
        assert news_item.sentiment == Decimal("0.75")
        assert news_item.source == "Reuters"
        assert news_item.published_at.year == 2023
        assert news_item.created_at is not None
    
    def test_news_item_multiple_symbols(self):
        """Test news item with multiple symbols."""
        news_item = NewsItem(
            title="Tech Stocks Rally",
            description="Major tech stocks see significant gains",
            url="https://example.com/news/tech-rally",
            source="Bloomberg",
            symbols=["AAPL", "GOOGL", "MSFT", "AMZN"],
            sentiment=Decimal("0.85"),
            published_at=datetime(2023, 10, 30, 14, 0, tzinfo=timezone.utc)
        )
        
        assert len(news_item.symbols) == 4
        assert "AAPL" in news_item.symbols
        assert "GOOGL" in news_item.symbols
    
    def test_news_item_negative_sentiment(self):
        """Test news item with negative sentiment."""
        news_item = NewsItem(
            title="Market Concerns Over Economic Data",
            description="Weak economic indicators raise market concerns",
            url="https://example.com/news/economic-concerns",
            source="Financial Times",
            symbols=["SPY"],
            sentiment=Decimal("-0.60"),
            published_at=datetime(2023, 10, 30, 10, 0, tzinfo=timezone.utc)
        )
        
        assert news_item.sentiment == Decimal("-0.60")


class TestTradingEvent:
    """Test TradingEvent model."""
    
    def test_trading_event_creation(self):
        """Test creating a trading event."""
        event = TradingEvent(
            event_type="order_created",
            data={
                "symbol": "AAPL",
                "side": "buy",
                "quantity": "100",
                "price": "150.00"
            }
        )
        
        assert event.event_type == "order_created"
        assert event.data["symbol"] == "AAPL"
        assert event.data["side"] == "buy"
        assert event.processed is False
        assert event.timestamp is not None
    
    def test_trading_event_with_timestamp(self):
        """Test creating a trading event with specific timestamp."""
        timestamp = datetime(2023, 10, 30, 12, 0, tzinfo=timezone.utc)
        event = TradingEvent(
            event_type="portfolio_updated",
            data={"equity": "25000.00"},
            timestamp=timestamp
        )
        
        assert event.timestamp == timestamp
    
    def test_trading_event_processed(self):
        """Test trading event processed status."""
        event = TradingEvent(
            event_type="order_filled",
            data={"order_id": "12345"},
            processed=True
        )
        
        assert event.processed is True


@pytest.mark.parametrize("side,expected", [
    (OrderSide.BUY, "buy"),
    (OrderSide.SELL, "sell")
])
def test_order_side_values(side, expected):
    """Test OrderSide enum values."""
    assert side.value == expected


@pytest.mark.parametrize("status,expected", [
    (OrderStatus.PENDING, "pending"),
    (OrderStatus.SUBMITTED, "submitted"),
    (OrderStatus.FILLED, "filled"),
    (OrderStatus.CANCELLED, "cancelled"),
    (OrderStatus.REJECTED, "rejected")
])
def test_order_status_values(status, expected):
    """Test OrderStatus enum values."""
    assert status.value == expected


@pytest.mark.parametrize("order_type,expected", [
    (OrderType.MARKET, "market"),
    (OrderType.LIMIT, "limit"),
    (OrderType.STOP_LOSS, "stop_loss"),
    (OrderType.TAKE_PROFIT, "take_profit")
])
def test_order_type_values(order_type, expected):
    """Test OrderType enum values."""
    assert order_type.value == expected


@pytest.mark.parametrize("action,expected", [
    (TradingAction.BUY, "buy"),
    (TradingAction.SELL, "sell"),
    (TradingAction.HOLD, "hold")
])
def test_trading_action_values(action, expected):
    """Test TradingAction enum values."""
    assert action.value == expected 