"""
Tests for Trading Event model

The old EventSystem (pub-sub queue) has been removed.
TradingSystem now uses direct method calls instead.
This test file validates the TradingEvent model that is still used.
"""

import pytest
from datetime import datetime, timedelta
import pytz

from agent_trader.models.trading_models import TradingEvent


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

    def test_trading_event_types(self):
        """Test various event types used in the system"""
        event_types = [
            "trigger_workflow",
            "enable_trading",
            "disable_trading",
            "emergency_stop",
            "query_status",
            "query_portfolio",
            "query_orders",
        ]
        for et in event_types:
            event = TradingEvent(event_type=et, data={})
            assert event.event_type == et

    def test_trading_event_data_preservation(self):
        """Test that event data is preserved correctly"""
        test_data = {
            "string": "test",
            "number": 123,
            "float": 45.67,
            "bool": True,
            "list": [1, 2, 3],
            "dict": {"nested": "value"}
        }
        
        event = TradingEvent(event_type="data_test", data=test_data)
        
        assert event.data["string"] == "test"
        assert event.data["number"] == 123
        assert event.data["float"] == 45.67
        assert event.data["bool"] is True
        assert event.data["list"] == [1, 2, 3]
        assert event.data["dict"]["nested"] == "value"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
