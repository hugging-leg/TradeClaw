"""
Unit tests for event system (in-memory only).
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
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
        assert event_system.event_handlers == {}
        assert event_system.is_running is False
        assert event_system.event_queue is not None
    
    @pytest.mark.asyncio
    async def test_initialize(self, event_system):
        """Test initialization."""
        await event_system.initialize()
        # Should not raise any exceptions
        assert True
    
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
    async def test_publish_event(self, event_system, sample_event):
        """Test publishing an event."""
        await event_system.publish_event(sample_event)
        
        # Event should be in the queue
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
        
        # Should not raise an exception and event should be processed
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
        portfolio = Portfolio(
            equity=Decimal("10000"),
            cash=Decimal("5000"),
            market_value=Decimal("5000"),
            day_pnl=Decimal("100"),
            total_pnl=Decimal("500"),
            positions=[]
        )
        
        with patch.object(event_system, 'publish_event') as mock_publish:
            await event_system.publish_portfolio_event(portfolio)
            
            mock_publish.assert_called_once()
            event = mock_publish.call_args[0][0]
            assert event.event_type == "portfolio_updated"
            assert event.data["equity"] == "10000"
    
    @pytest.mark.asyncio
    async def test_publish_market_event(self, event_system):
        """Test publishing a market event."""
        data = {"symbol": "AAPL", "price": "150.00", "volume": "1000"}
        
        with patch.object(event_system, 'publish_event') as mock_publish:
            await event_system.publish_market_event("market_data", data)
            
            mock_publish.assert_called_once()
            event = mock_publish.call_args[0][0]
            assert event.event_type == "market_data"
            assert event.data == data
    
    @pytest.mark.asyncio
    async def test_publish_system_event(self, event_system):
        """Test publishing a system event."""
        with patch.object(event_system, 'publish_event') as mock_publish:
            await event_system.publish_system_event("system_alert", "Test message", "warning")
            
            mock_publish.assert_called_once()
            event = mock_publish.call_args[0][0]
            assert event.event_type == "system_alert"
            assert event.data["message"] == "Test message"
            assert event.data["level"] == "warning"
    
    @pytest.mark.asyncio
    async def test_start_and_stop(self, event_system):
        """Test starting and stopping the event system."""
        await event_system.start()
        assert event_system.is_running is True
        
        await event_system.stop()
        assert event_system.is_running is False
    
    @pytest.mark.asyncio
    async def test_get_event_history(self, event_system):
        """Test getting event history."""
        # In-memory version returns empty list
        history = await event_system.get_event_history()
        assert history == []
    
    @pytest.mark.asyncio
    async def test_process_events_loop(self, event_system):
        """Test event processing loop."""
        events_processed = []
        
        async def test_handler(event):
            events_processed.append(event)
        
        event_system.register_handler("test_event", test_handler)
        
        # Start the event system
        await event_system.start()
        
        # Publish an event
        sample_event = TradingEvent(
            event_type="test_event",
            data={"test": "data"}
        )
        await event_system.publish_event(sample_event)
        
        # Wait for processing
        await asyncio.sleep(0.1)
        
        # Stop the system
        await event_system.stop()
        
        # Check that event was processed
        assert len(events_processed) == 1
        assert events_processed[0].event_type == "test_event"


class TestEventSystemIntegration:
    """Integration tests for event system."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_event_flow(self):
        """Test complete event flow from publish to processing."""
        system = EventSystem()
        processed_events = []
        
        async def test_handler(event):
            processed_events.append(event)
        
        system.register_handler("integration_test", test_handler)
        
        # Start the system
        await system.start()
        
        # Publish events
        for i in range(3):
            event = TradingEvent(
                event_type="integration_test",
                data={"test_id": i}
            )
            await system.publish_event(event)
        
        # Wait for processing
        await asyncio.sleep(0.1)
        
        # Stop the system
        await system.stop()
        
        # Verify all events were processed
        assert len(processed_events) == 3
        for i, event in enumerate(processed_events):
            assert event.data["test_id"] == i
    
    @pytest.mark.asyncio
    async def test_multiple_handlers_same_event(self):
        """Test multiple handlers for the same event type."""
        system = EventSystem()
        handler1_calls = []
        handler2_calls = []
        
        async def handler1(event):
            handler1_calls.append(event)
        
        def handler2(event):  # Sync handler
            handler2_calls.append(event)
        
        system.register_handler("multi_test", handler1)
        system.register_handler("multi_test", handler2)
        
        await system.start()
        
        event = TradingEvent(
            event_type="multi_test",
            data={"test": "multi"}
        )
        await system.publish_event(event)
        
        await asyncio.sleep(0.1)
        await system.stop()
        
        # Both handlers should have been called
        assert len(handler1_calls) == 1
        assert len(handler2_calls) == 1 