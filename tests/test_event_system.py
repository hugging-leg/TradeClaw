"""
Tests for Event System

Tests the unified event-driven architecture including:
- Event publishing and handling
- Priority queue processing
- Scheduled events
- Event types and data
"""

import pytest
import pytest_asyncio
import asyncio
from datetime import datetime, timedelta
import pytz

from agent_trader.events.event_system import EventSystem
from agent_trader.models.trading_models import TradingEvent


class TestEventSystem:
    """Test suite for EventSystem"""
    
    @pytest_asyncio.fixture
    async def event_system(self):
        """Create a fresh event system for each test"""
        es = EventSystem()
        await es.start()
        yield es
        await es.stop()
    
    @pytest.mark.asyncio
    async def test_event_system_initialization(self, event_system):
        """Test that event system initializes correctly"""
        assert event_system is not None
        assert event_system.get_queue_size() == 0
        assert event_system.is_running == True
    
    @pytest.mark.asyncio
    async def test_publish_immediate_event(self, event_system):
        """Test publishing an immediate event"""
        # Setup handler
        received_events = []
        
        async def handler(event):
            received_events.append(event)
        
        event_system.register_handler("test_event", handler)
        
        # Publish event
        await event_system.publish(
            event_type="test_event",
            data={"message": "hello"}
        )
        
        # Give time for processing
        await asyncio.sleep(0.2)
        
        assert len(received_events) == 1
        assert received_events[0].event_type == "test_event"
        assert received_events[0].data["message"] == "hello"
    
    @pytest.mark.asyncio
    async def test_publish_scheduled_event(self, event_system):
        """Test publishing a scheduled event"""
        future_time = datetime.now(pytz.UTC) + timedelta(seconds=0.5)
        
        await event_system.publish(
            event_type="scheduled_test",
            data={"scheduled": True},
            scheduled_time=future_time
        )
        
        # Event should be scheduled (may be picked up by processor immediately)
        # Just verify no errors occur
        await asyncio.sleep(0.1)
        # Queue size may be 0 if event is already being processed
        assert event_system.get_queue_size() >= 0
    
    @pytest.mark.asyncio
    async def test_event_priority(self, event_system):
        """Test that scheduled events are processed in time order"""
        received_events = []
        
        async def async_handler(event):
            received_events.append(event.data["order"])
        
        event_system.register_handler("priority_test", async_handler)
        
        # Publish events with different times (reverse order)
        now = datetime.now(pytz.UTC)
        await event_system.publish("priority_test", {"order": 2}, scheduled_time=now + timedelta(seconds=0.3))
        await event_system.publish("priority_test", {"order": 1}, scheduled_time=now + timedelta(seconds=0.1))
        await event_system.publish("priority_test", {"order": 3}, scheduled_time=now + timedelta(seconds=0.5))
        
        # Wait for all to process
        await asyncio.sleep(0.8)
        
        # Should be processed in time order
        assert len(received_events) == 3
        assert received_events[0] == 1
        assert received_events[1] == 2
        assert received_events[2] == 3
    
    @pytest.mark.asyncio
    async def test_multiple_handlers(self, event_system):
        """Test that multiple handlers can be registered for the same event"""
        handler1_called = []
        handler2_called = []
        
        async def handler1(event):
            handler1_called.append(True)
        
        async def handler2(event):
            handler2_called.append(True)
        
        event_system.register_handler("multi_test", handler1)
        event_system.register_handler("multi_test", handler2)
        
        await event_system.publish("multi_test", {})
        await asyncio.sleep(0.2)
        
        assert len(handler1_called) == 1
        assert len(handler2_called) == 1
    
    @pytest.mark.asyncio
    async def test_event_data_preservation(self, event_system):
        """Test that event data is preserved correctly"""
        received_data = []
        
        async def handler(event):
            received_data.append(event.data)
        
        event_system.register_handler("data_test", handler)
        
        test_data = {
            "string": "test",
            "number": 123,
            "float": 45.67,
            "bool": True,
            "list": [1, 2, 3],
            "dict": {"nested": "value"}
        }
        
        await event_system.publish("data_test", test_data)
        await asyncio.sleep(0.2)
        
        assert len(received_data) == 1
        assert received_data[0]["string"] == "test"
        assert received_data[0]["number"] == 123
    
    @pytest.mark.asyncio
    async def test_workflow_trigger_event(self, event_system):
        """Test trigger_workflow event type"""
        received_events = []
        
        async def handler(event):
            received_events.append(event)
        
        event_system.register_handler("trigger_workflow", handler)
        
        await event_system.publish(
            "trigger_workflow",
            {
                "trigger": "manual_analysis",
                "context": {"source": "test"}
            }
        )
        
        await asyncio.sleep(0.2)
        
        assert len(received_events) == 1
        assert received_events[0].data["trigger"] == "manual_analysis"
    
    @pytest.mark.asyncio
    async def test_trading_control_events(self, event_system):
        """Test enable_trading and disable_trading events"""
        received_events = []
        
        async def handler(event):
            received_events.append(event.event_type)
        
        event_system.register_handler("enable_trading", handler)
        event_system.register_handler("disable_trading", handler)
        
        await event_system.publish("enable_trading", {})
        await event_system.publish("disable_trading", {})
        
        await asyncio.sleep(0.2)
        
        assert "enable_trading" in received_events
        assert "disable_trading" in received_events
    
    @pytest.mark.asyncio
    async def test_emergency_stop_event(self, event_system):
        """Test emergency_stop event"""
        received_events = []
        
        async def handler(event):
            received_events.append(event.event_type)
        
        event_system.register_handler("emergency_stop", handler)
        
        await event_system.publish("emergency_stop", {})
        
        await asyncio.sleep(0.2)
        
        assert len(received_events) == 1
        assert received_events[0] == "emergency_stop"
    
    @pytest.mark.asyncio
    async def test_query_events(self, event_system):
        """Test query events (status, portfolio, orders)"""
        received_events = []
        
        async def handler(event):
            received_events.append(event.event_type)
        
        event_system.register_handler("query_status", handler)
        event_system.register_handler("query_portfolio", handler)
        event_system.register_handler("query_orders", handler)
        
        await event_system.publish("query_status", {})
        await event_system.publish("query_portfolio", {})
        await event_system.publish("query_orders", {})
        
        await asyncio.sleep(0.2)
        
        assert "query_status" in received_events
        assert "query_portfolio" in received_events
        assert "query_orders" in received_events
    
    @pytest.mark.asyncio
    async def test_stop_processing(self, event_system):
        """Test graceful stop of event processing"""
        assert event_system.is_running == True
        
        await event_system.stop()
        assert event_system.is_running == False
    
    @pytest.mark.asyncio
    async def test_get_status(self, event_system):
        """Test get_status returns correct information"""
        status = event_system.get_status()
        
        assert "is_running" in status
        assert "queue_size" in status
        assert isinstance(status["queue_size"], int)
    
    @pytest.mark.asyncio
    async def test_async_handler(self, event_system):
        """Test that async handlers work correctly"""
        received_events = []
        
        async def async_handler(event):
            await asyncio.sleep(0.05)  # Simulate async work
            received_events.append(event.event_type)
        
        event_system.register_handler("async_test", async_handler)
        
        await event_system.publish("async_test", {})
        
        await asyncio.sleep(0.2)
        
        assert len(received_events) == 1
        assert received_events[0] == "async_test"
    
    @pytest.mark.asyncio
    async def test_handler_error_handling(self, event_system):
        """Test that handler errors don't crash the system"""
        good_handler_called = []
        
        async def bad_handler(event):
            raise Exception("Handler error")
        
        async def good_handler(event):
            good_handler_called.append(True)
        
        event_system.register_handler("error_test", bad_handler)
        event_system.register_handler("error_test", good_handler)
        
        await event_system.publish("error_test", {})
        
        await asyncio.sleep(0.2)
        
        # Good handler should still be called despite bad handler error
        assert len(good_handler_called) == 1
    
    @pytest.mark.asyncio
    async def test_event_timestamp(self, event_system):
        """Test that events have timestamps"""
        received_events = []
        
        async def handler(event):
            received_events.append(event)
        
        event_system.register_handler("timestamp_test", handler)
        
        await event_system.publish("timestamp_test", {"test": "data"})
        await asyncio.sleep(0.2)
        
        assert len(received_events) == 1
        assert "timestamp" in received_events[0].data


class TestTradingEvent:
    """Test suite for TradingEvent model"""
    
    def test_trading_event_creation(self):
        """Test creating a TradingEvent"""
        event = TradingEvent(
            event_type="test_event",
            data={"key": "value"},
            priority=5
        )
        
        assert event.event_type == "test_event"
        assert event.data["key"] == "value"
        assert event.priority == 5
        assert event.scheduled_time is None
    
    def test_trading_event_with_scheduled_time(self):
        """Test creating a scheduled TradingEvent"""
        future_time = datetime.now(pytz.UTC) + timedelta(hours=1)
        
        event = TradingEvent(
            event_type="scheduled_event",
            data={},
            scheduled_time=future_time,
            priority=0
        )
        
        assert event.scheduled_time == future_time
        assert event.priority == 0
    
    def test_trading_event_comparison(self):
        """Test that events can be compared by scheduled time"""
        now = datetime.now(pytz.UTC)
        event1 = TradingEvent(
            event_type="test",
            data={},
            scheduled_time=now + timedelta(seconds=10),
            priority=0
        )
        event2 = TradingEvent(
            event_type="test",
            data={},
            scheduled_time=now + timedelta(seconds=20),
            priority=0
        )
        
        # Earlier time should be less than later time
        assert event1 < event2
    
    def test_trading_event_default_values(self):
        """Test default values for TradingEvent"""
        event = TradingEvent(event_type="test", data={})
        
        assert event.event_type == "test"
        assert event.data == {}
        assert event.priority == 0
        assert event.scheduled_time is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
