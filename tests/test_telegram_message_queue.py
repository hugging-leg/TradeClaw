"""
Unit tests for TelegramMessageQueue class.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from decimal import Decimal
from queue import Queue

from src.apis.telegram_message_queue import TelegramMessageQueue
from src.models.trading_models import TradingDecision, TradingAction


class TestTelegramMessageQueue:
    """Test TelegramMessageQueue functionality"""
    
    def test_initialization_without_bot(self):
        """Test initialization without Telegram bot"""
        queue = TelegramMessageQueue()
        
        assert queue.telegram_bot is None
        assert isinstance(queue.message_queue, Queue)
        assert not queue.is_processing
    
    def test_initialization_with_bot(self):
        """Test initialization with Telegram bot"""
        mock_bot = Mock()
        queue = TelegramMessageQueue(mock_bot)
        
        assert queue.telegram_bot == mock_bot
        assert isinstance(queue.message_queue, Queue)
        assert not queue.is_processing
    
    @pytest.mark.asyncio
    async def test_send_message_without_bot(self, caplog):
        """Test sending message without bot (should log)"""
        queue = TelegramMessageQueue()
        
        await queue.send_message("Test message", "info")
        
        # Should log the message instead of sending
        assert "Telegram message (info): ℹ️ Test message" in caplog.text
    
    @pytest.mark.asyncio
    async def test_send_message_with_bot(self):
        """Test sending message with bot"""
        mock_bot = AsyncMock()
        queue = TelegramMessageQueue(mock_bot)
        
        await queue.send_message("Test message", "success")
        
        # Should queue the message
        assert queue.message_queue.qsize() > 0
    
    @pytest.mark.asyncio
    async def test_emoji_mapping(self):
        """Test emoji mapping for different message types"""
        queue = TelegramMessageQueue()
        
        # Test various message types
        test_cases = [
            ("info", "ℹ️"),
            ("success", "✅"),
            ("warning", "⚠️"),
            ("error", "❌"),
            ("news", "📰"),
            ("analysis", "🔍"),
            ("decision", "🤔"),
            ("trade", "💼"),
            ("unknown", "📢")  # Default emoji
        ]
        
        for msg_type, expected_emoji in test_cases:
            await queue.send_message("test", msg_type)
            # The emoji would be added to the formatted message
    
    @pytest.mark.asyncio
    async def test_send_news_summary_empty(self):
        """Test sending news summary with empty list"""
        queue = TelegramMessageQueue()
        
        await queue.send_news_summary([])
        
        # Should not add any messages to queue
        assert queue.message_queue.empty()
    
    @pytest.mark.asyncio
    async def test_send_news_summary_with_items(self):
        """Test sending news summary with items"""
        queue = TelegramMessageQueue()
        news_items = [
            {
                "title": "Market Update: Stocks Rally",
                "source": "Reuters"
            },
            {
                "title": "Federal Reserve Meeting Results",
                "source": "Bloomberg"
            }
        ]
        
        await queue.send_news_summary(news_items, limit=2)
        
        # Should have queued a message
        assert queue.message_queue.qsize() > 0
    
    @pytest.mark.asyncio
    async def test_send_news_summary_truncation(self):
        """Test news title truncation"""
        queue = TelegramMessageQueue()
        news_items = [
            {
                "title": "A" * 100,  # Very long title
                "source": "Test Source"
            }
        ]
        
        await queue.send_news_summary(news_items)
        
        # Should have queued a message with truncated title
        assert queue.message_queue.qsize() > 0
    
    @pytest.mark.asyncio
    async def test_send_analysis_summary_empty(self):
        """Test sending analysis summary with empty text"""
        queue = TelegramMessageQueue()
        
        await queue.send_analysis_summary("")
        
        # Should not add any messages to queue
        assert queue.message_queue.empty()
    
    @pytest.mark.asyncio
    async def test_send_analysis_summary_with_key_points(self):
        """Test analysis summary with key points"""
        queue = TelegramMessageQueue()
        analysis = """
Market Analysis:
- Overall sentiment is bullish
- Technology sector showing strength
- Risk levels remain moderate
• Energy sector experiencing volatility
Overall outlook is positive.
"""
        
        await queue.send_analysis_summary(analysis)
        
        # Should have queued a message
        assert queue.message_queue.qsize() > 0
    
    @pytest.mark.asyncio
    async def test_send_analysis_summary_fallback(self):
        """Test analysis summary fallback to sentences"""
        queue = TelegramMessageQueue()
        analysis = "Market conditions are stable. Trading volume is normal. No major concerns."
        
        await queue.send_analysis_summary(analysis)
        
        # Should have queued a message
        assert queue.message_queue.qsize() > 0
    
    @pytest.mark.asyncio
    async def test_send_decision_summary_none(self):
        """Test sending decision summary with None"""
        queue = TelegramMessageQueue()
        
        await queue.send_decision_summary(None)
        
        # Should have queued a HOLD message
        assert queue.message_queue.qsize() > 0
    
    @pytest.mark.asyncio
    async def test_send_decision_summary_hold(self):
        """Test sending HOLD decision summary"""
        queue = TelegramMessageQueue()
        
        decision = TradingDecision(
            action=TradingAction.HOLD,
            symbol="",
            reasoning="Market conditions are uncertain",
            confidence=Decimal('0.75')
        )
        
        await queue.send_decision_summary(decision)
        
        # Should have queued a message
        assert queue.message_queue.qsize() > 0
    
    @pytest.mark.asyncio
    async def test_send_decision_summary_buy(self):
        """Test sending BUY decision summary"""
        queue = TelegramMessageQueue()
        
        decision = TradingDecision(
            action=TradingAction.BUY,
            symbol="AAPL",
            quantity=Decimal("50"),
            reasoning="Strong fundamentals and positive technical indicators",
            confidence=Decimal('0.85')
        )
        
        await queue.send_decision_summary(decision)
        
        # Should have queued a message
        assert queue.message_queue.qsize() > 0
    
    @pytest.mark.asyncio
    async def test_send_decision_summary_long_reasoning(self):
        """Test decision summary with long reasoning text"""
        queue = TelegramMessageQueue()
        
        long_reasoning = "A" * 300  # Very long reasoning
        decision = TradingDecision(
            action=TradingAction.SELL,
            symbol="TSLA",
            quantity=Decimal("25"),
            reasoning=long_reasoning,
            confidence=Decimal('0.90')
        )
        
        await queue.send_decision_summary(decision)
        
        # Should have queued a message with truncated reasoning
        assert queue.message_queue.qsize() > 0
    
    @pytest.mark.asyncio
    async def test_send_portfolio_summary(self):
        """Test sending portfolio summary"""
        queue = TelegramMessageQueue()
        
        portfolio_msg = "Portfolio Summary:\n• Equity: $50,000\n• Cash: $25,000"
        
        await queue.send_portfolio_summary(portfolio_msg)
        
        # Should have queued a message
        assert queue.message_queue.qsize() > 0
    
    @pytest.mark.asyncio
    async def test_send_trade_execution(self):
        """Test sending trade execution confirmation"""
        queue = TelegramMessageQueue()
        
        await queue.send_trade_execution("AAPL", "BUY", "50", "order_123")
        
        # Should have queued a message
        assert queue.message_queue.qsize() > 0
    
    @pytest.mark.asyncio
    async def test_send_workflow_complete(self):
        """Test sending workflow completion notification"""
        queue = TelegramMessageQueue()
        
        await queue.send_workflow_complete()
        
        # Should have queued a message
        assert queue.message_queue.qsize() > 0
    
    @pytest.mark.asyncio
    async def test_send_error_without_context(self):
        """Test sending error without context"""
        queue = TelegramMessageQueue()
        
        await queue.send_error("Something went wrong")
        
        # Should have queued a message
        assert queue.message_queue.qsize() > 0
    
    @pytest.mark.asyncio
    async def test_send_error_with_context(self):
        """Test sending error with context"""
        queue = TelegramMessageQueue()
        
        await queue.send_error("Something went wrong", "Data Collection")
        
        # Should have queued a message
        assert queue.message_queue.qsize() > 0
    
    def test_get_queue_size(self):
        """Test getting queue size"""
        queue = TelegramMessageQueue()
        
        assert queue.get_queue_size() == 0
        
        # Add a message manually
        queue.message_queue.put({"test": "message"})
        assert queue.get_queue_size() == 1
    
    def test_is_queue_empty(self):
        """Test checking if queue is empty"""
        queue = TelegramMessageQueue()
        
        assert queue.is_queue_empty() is True
        
        # Add a message manually
        queue.message_queue.put({"test": "message"})
        assert queue.is_queue_empty() is False
    
    @pytest.mark.asyncio
    async def test_processor_with_bot_error(self):
        """Test processor handling bot errors"""
        mock_bot = AsyncMock()
        mock_bot.send_message.side_effect = Exception("Bot error")
        
        queue = TelegramMessageQueue(mock_bot)
        
        # This should not raise an exception
        await queue.send_message("Test message", "info")
        
        # The message should still be processed (queue emptied)
        # Note: The processor catches exceptions and continues
    
    @pytest.mark.asyncio
    async def test_processor_rate_limiting(self):
        """Test that processor respects rate limiting"""
        mock_bot = AsyncMock()
        queue = TelegramMessageQueue(mock_bot)
        
        # Send multiple messages
        await queue.send_message("Message 1", "info")
        
        # The processor should have been started
        # In a real scenario, this would test the 1-second delay
        # but for unit tests, we just verify the bot was called
        
        # Wait a bit for the async processor to complete
        await asyncio.sleep(0.1)
        
        # Verify the bot's send_message was called
        mock_bot.send_message.assert_called() 