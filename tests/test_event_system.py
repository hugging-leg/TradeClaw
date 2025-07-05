"""
Unit tests for event system.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone
from src.events.event_system import EventSystem
from src.models.trading_models import TradingEvent, Order, OrderSide, OrderType, Portfolio, Position, PositionSide
from decimal import Decimal


class TestEventSystem:
    """Test EventSystem class."""
    
    @pytest.fixture
    def event_system(self):
        """Create an event system instance."""
        return EventSystem()
    
    @pytest.fixture
    def sample_event(self):
        """Create a sample trading event."""
        return TradingEvent(
            event_type="test_event",
            data={"symbol": "AAPL", "price": "150.00"}
        )
    
    def test_event_system_initialization(self, event_system):
        """Test event system initialization."""
        assert event_system.redis_client is None
        assert event_system.pubsub is None
        assert event_system.event_handlers == {}
        assert event_system.is_running is False
        assert event_system.event_queue is not None
        assert hasattr(event_system, 'use_redis')
    
    @pytest.mark.asyncio
    async def test_initialize_without_redis(self, event_system):
        """Test initialization without Redis."""
        with patch.dict('os.environ', {'USE_REDIS': 'false'}):
            event_system.use_redis = False
            await event_system.initialize()
            
            assert event_system.redis_client is None
            assert event_system.use_redis is False
    
    @pytest.mark.asyncio
    @patch('src.events.event_system.settings')
    async def test_initialize_with_redis_success(self, mock_settings, event_system):
        """Test successful Redis initialization."""
        mock_settings.redis_url = "redis://localhost:6379/0"
        
        with patch('redis.asyncio.from_url') as mock_redis:
            mock_client = AsyncMock()
            mock_pubsub = AsyncMock()
            mock_client.pubsub.return_value = mock_pubsub
            mock_redis.return_value = mock_client
            
            event_system.use_redis = True
            await event_system.initialize()
            
            assert event_system.redis_client is not None
            assert event_system.pubsub is not None
    
    @pytest.mark.asyncio
    @patch('src.events.event_system.settings')
    async def test_initialize_with_redis_failure(self, mock_settings, event_system):
        """Test Redis initialization failure fallback."""
        mock_settings.redis_url = "redis://localhost:6379/0"
        
        with patch('redis.asyncio.from_url', side_effect=Exception("Connection failed")):
            event_system.use_redis = True
            await event_system.initialize()
            
            assert event_system.redis_client is None
            assert event_system.use_redis is False
    
    def test_register_handler(self, event_system):
        """Test registering an event handler."""
        handler = Mock()
        event_system.register_handler("test_event", handler)
        
        assert "test_event" in event_system.event_handlers
        assert handler in event_system.event_handlers["test_event"]
    
    def test_register_multiple_handlers(self, event_system):
        """Test registering multiple handlers for the same event type."""
        handler1 = Mock()
        handler2 = Mock()
        
        event_system.register_handler("test_event", handler1)
        event_system.register_handler("test_event", handler2)
        
        assert len(event_system.event_handlers["test_event"]) == 2
        assert handler1 in event_system.event_handlers["test_event"]
        assert handler2 in event_system.event_handlers["test_event"]
    
    def test_unregister_handler(self, event_system):
        """Test unregistering an event handler."""
        handler = Mock()
        event_system.register_handler("test_event", handler)
        event_system.unregister_handler("test_event", handler)
        
        assert handler not in event_system.event_handlers["test_event"]
    
    def test_unregister_nonexistent_handler(self, event_system):
        """Test unregistering a non-existent handler."""
        handler = Mock()
        # Should not raise an exception
        event_system.unregister_handler("test_event", handler)
    
    @pytest.mark.asyncio
    async def test_publish_event_without_redis(self, event_system, sample_event):
        """Test publishing an event without Redis."""
        event_system.use_redis = False
        event_system.redis_client = None
        
        await event_system.publish_event(sample_event)
        
        # Event should be in the queue
        assert not event_system.event_queue.empty()
    
    @pytest.mark.asyncio
    async def test_publish_event_with_redis(self, event_system, sample_event):
        """Test publishing an event with Redis."""
        mock_redis = AsyncMock()
        event_system.redis_client = mock_redis
        event_system.use_redis = True
        
        await event_system.publish_event(sample_event)
        
        # Event should be published to Redis and queued locally
        mock_redis.publish.assert_called_once()
        assert not event_system.event_queue.empty()
    
    @pytest.mark.asyncio
    async def test_handle_event(self, event_system, sample_event):
        """Test handling an event."""
        handler = AsyncMock()
        event_system.register_handler("test_event", handler)
        
        await event_system._handle_event(sample_event)
        
        handler.assert_called_once_with(sample_event)
        assert sample_event.processed is True
    
    @pytest.mark.asyncio
    async def test_handle_event_with_sync_handler(self, event_system, sample_event):
        """Test handling an event with synchronous handler."""
        handler = Mock()
        event_system.register_handler("test_event", handler)
        
        await event_system._handle_event(sample_event)
        
        handler.assert_called_once_with(sample_event)
        assert sample_event.processed is True
    
    @pytest.mark.asyncio
    async def test_handle_event_no_handlers(self, event_system, sample_event):
        """Test handling an event with no registered handlers."""
        await event_system._handle_event(sample_event)
        
        # Should not raise an exception
        assert sample_event.processed is True
    
    @pytest.mark.asyncio
    async def test_handle_event_handler_exception(self, event_system, sample_event):
        """Test handling an event when handler raises exception."""
        handler = Mock(side_effect=Exception("Handler error"))
        event_system.register_handler("test_event", handler)
        
        await event_system._handle_event(sample_event)
        
        # Event should still be marked as processed
        assert sample_event.processed is True
    
    @pytest.mark.asyncio
    async def test_publish_order_event(self, event_system):
        """Test publishing an order event."""
        order = Order(
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("100")
        )
        
        with patch.object(event_system, 'publish_event') as mock_publish:
            await event_system.publish_order_event(order, "order_created")
            
            mock_publish.assert_called_once()
            event = mock_publish.call_args[0][0]
            assert event.event_type == "order_created"
            assert event.data["symbol"] == "AAPL"
            assert event.data["side"] == "buy"
    
    @pytest.mark.asyncio
    async def test_publish_portfolio_event(self, event_system):
        """Test publishing a portfolio event."""
        positions = [
            Position(
                symbol="AAPL",
                quantity=Decimal("100"),
                market_value=Decimal("15000.00"),
                avg_entry_price=Decimal("150.00"),
                side=PositionSide.LONG
            )
        ]
        
        portfolio = Portfolio(
            equity=Decimal("25000.00"),
            cash=Decimal("10000.00"),
            market_value=Decimal("15000.00"),
            day_pnl=Decimal("500.00"),
            total_pnl=Decimal("2500.00"),
            positions=positions
        )
        
        with patch.object(event_system, 'publish_event') as mock_publish:
            await event_system.publish_portfolio_event(portfolio)
            
            mock_publish.assert_called_once()
            event = mock_publish.call_args[0][0]
            assert event.event_type == "portfolio_updated"
            assert event.data["equity"] == "25000.00"
            assert len(event.data["positions"]) == 1
    
    @pytest.mark.asyncio
    async def test_publish_market_event(self, event_system):
        """Test publishing a market event."""
        data = {"symbol": "AAPL", "price": 150.00, "volume": 1000000}
        
        with patch.object(event_system, 'publish_event') as mock_publish:
            await event_system.publish_market_event("market_data_updated", data)
            
            mock_publish.assert_called_once()
            event = mock_publish.call_args[0][0]
            assert event.event_type == "market_data_updated"
            assert event.data == data
    
    @pytest.mark.asyncio
    async def test_publish_system_event(self, event_system):
        """Test publishing a system event."""
        with patch.object(event_system, 'publish_event') as mock_publish:
            await event_system.publish_system_event("system_startup", "Trading system started", "info")
            
            mock_publish.assert_called_once()
            event = mock_publish.call_args[0][0]
            assert event.event_type == "system_startup"
            assert event.data["message"] == "Trading system started"
            assert event.data["level"] == "info"
    
    @pytest.mark.asyncio
    async def test_start_and_stop(self, event_system):
        """Test starting and stopping the event system."""
        event_system.use_redis = False
        
        await event_system.start()
        assert event_system.is_running is True
        
        await event_system.stop()
        assert event_system.is_running is False
    
    @pytest.mark.asyncio
    async def test_start_with_redis(self, event_system):
        """Test starting with Redis."""
        mock_redis = AsyncMock()
        mock_pubsub = AsyncMock()
        mock_redis.pubsub.return_value = mock_pubsub
        
        event_system.redis_client = mock_redis
        event_system.pubsub = mock_pubsub
        event_system.use_redis = True
        
        await event_system.start()
        
        mock_pubsub.subscribe.assert_called_once_with("trading_events")
        assert event_system.is_running is True
    
    @pytest.mark.asyncio
    async def test_get_event_history(self, event_system):
        """Test getting event history (simplified version)."""
        history = await event_system.get_event_history()
        
        # In the simplified version, history is empty
        assert history == []
    
    @pytest.mark.asyncio
    async def test_process_events_loop(self, event_system):
        """Test the event processing loop."""
        handler = AsyncMock()
        event_system.register_handler("test_event", handler)
        event_system.is_running = True
        
        # Add an event to the queue
        test_event = TradingEvent(event_type="test_event", data={"test": "data"})
        await event_system.event_queue.put(test_event)
        
        # Run the process events method once
        with patch('asyncio.wait_for') as mock_wait_for:
            mock_wait_for.return_value = test_event
            
            # Simulate one iteration of the loop
            await event_system._process_events()
            
            # Handler should have been called
            handler.assert_called_once_with(test_event)


class TestEventSystemIntegration:
    """Integration tests for event system."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_event_flow(self):
        """Test complete event flow from publish to handling."""
        event_system = EventSystem()
        event_system.use_redis = False
        
        # Set up handler
        received_events = []
        
        async def test_handler(event):
            received_events.append(event)
        
        event_system.register_handler("test_event", test_handler)
        
        # Publish event
        test_event = TradingEvent(
            event_type="test_event",
            data={"symbol": "AAPL", "action": "buy"}
        )
        
        await event_system.publish_event(test_event)
        
        # Process the event
        queued_event = await event_system.event_queue.get()
        await event_system._handle_event(queued_event)
        
        # Verify event was handled
        assert len(received_events) == 1
        assert received_events[0].event_type == "test_event"
        assert received_events[0].data["symbol"] == "AAPL"
        assert received_events[0].processed is True
    
    @pytest.mark.asyncio
    async def test_multiple_handlers_same_event(self):
        """Test multiple handlers for the same event type."""
        event_system = EventSystem()
        event_system.use_redis = False
        
        # Set up multiple handlers
        handler1_calls = []
        handler2_calls = []
        
        async def handler1(event):
            handler1_calls.append(event)
        
        def handler2(event):  # Sync handler
            handler2_calls.append(event)
        
        event_system.register_handler("test_event", handler1)
        event_system.register_handler("test_event", handler2)
        
        # Publish and handle event
        test_event = TradingEvent(event_type="test_event", data={"test": "data"})
        await event_system.publish_event(test_event)
        
        queued_event = await event_system.event_queue.get()
        await event_system._handle_event(queued_event)
        
        # Both handlers should have been called
        assert len(handler1_calls) == 1
        assert len(handler2_calls) == 1
        assert handler1_calls[0] == queued_event
        assert handler2_calls[0] == queued_event 