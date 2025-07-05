"""
Telegram message queue system for real-time notifications during trading workflows.

This module provides a message queue system that:
- Handles real-time Telegram notifications during AI trading workflows
- Implements rate limiting to prevent Telegram API flooding
- Provides intelligent message formatting and categorization
- Supports graceful degradation when Telegram bot is unavailable
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from queue import Queue, Empty

from src.models.trading_models import TradingDecision, TradingAction


logger = logging.getLogger(__name__)


class TelegramMessageQueue:
    """
    Message queue for Telegram notifications during workflow execution.
    
    Features:
    - Anti-flood protection with 1-second delays between messages
    - Message type categorization with emojis
    - Automatic message summarization for long content
    - Graceful fallback to logging when Telegram bot unavailable
    """
    
    def __init__(self, telegram_bot=None):
        """
        Initialize the message queue.
        
        Args:
            telegram_bot: Optional Telegram bot instance for sending messages
        """
        self.telegram_bot = telegram_bot
        self.message_queue = Queue()
        self.is_processing = False
        self._processor_task = None
    
    async def send_message(self, message: str, message_type: str = "info"):
        """
        Add message to queue for sending with emoji categorization.
        
        Args:
            message: Message content to send
            message_type: Type of message (info, success, warning, error, news, analysis, decision, trade)
        """
        if not self.telegram_bot:
            logger.info(f"Telegram message ({message_type}): {message}")
            return
        
        emoji_map = {
            "info": "ℹ️",
            "success": "✅", 
            "warning": "⚠️",
            "error": "❌",
            "news": "📰",
            "analysis": "🔍",
            "decision": "🤔",
            "trade": "💼"
        }
        
        emoji = emoji_map.get(message_type, "📢")
        formatted_message = f"{emoji} {message}"
        
        # Add to queue
        self.message_queue.put({
            "message": formatted_message,
            "timestamp": datetime.now(),
            "type": message_type
        })
        
        # Start processor if not running
        if not self.is_processing:
            await self._start_processor()
    
    async def _start_processor(self):
        """
        Start processing messages from queue with rate limiting.
        
        Processes messages one by one with 1-second delays to avoid
        Telegram API rate limits.
        """
        if self.is_processing:
            return
            
        self.is_processing = True
        
        try:
            while not self.message_queue.empty():
                try:
                    msg_data = self.message_queue.get_nowait()
                    if self.telegram_bot:
                        await self.telegram_bot.send_message(
                            msg_data["message"], 
                            parse_mode="Markdown"
                        )
                        # Small delay to avoid flooding
                        await asyncio.sleep(1)
                except Empty:
                    break
                except Exception as e:
                    logger.error(f"Error sending Telegram message: {e}")
        finally:
            self.is_processing = False
    
    async def send_news_summary(self, news_items: List[Dict], limit: int = 5):
        """
        Send formatted news summary with key headlines.
        
        Args:
            news_items: List of news item dictionaries
            limit: Maximum number of news items to show
        """
        if not news_items:
            return
        
        message = "📰 **Latest Market News**\n\n"
        
        for i, news in enumerate(news_items[:limit], 1):
            title = news.get('title', 'No title')
            source = news.get('source', 'Unknown')
            
            # Truncate long titles
            title_display = title[:80] + '...' if len(title) > 80 else title
            message += f"**{i}.** {title_display}\n"
            message += f"   *Source: {source}*\n\n"
        
        if len(news_items) > limit:
            message += f"*...and {len(news_items) - limit} more articles*"
        
        await self.send_message(message, "news")
    
    async def send_analysis_summary(self, analysis: str):
        """
        Send formatted market analysis summary with key points extraction.
        
        Args:
            analysis: Raw analysis text from LLM
        """
        if not analysis:
            return
        
        # Extract key points from analysis
        lines = analysis.split('\n')
        key_points = []
        
        for line in lines:
            line = line.strip()
            if line and (line.startswith('-') or line.startswith('•') or 
                        'sentiment' in line.lower() or 'trend' in line.lower() or
                        'risk' in line.lower() or 'opportunity' in line.lower()):
                key_points.append(line)
        
        message = "🔍 **Market Analysis Summary**\n\n"
        
        if key_points:
            for point in key_points[:5]:  # Limit to 5 key points
                # Clean up point formatting
                clean_point = point.lstrip('-•').strip()
                message += f"• {clean_point}\n"
        else:
            # Fallback to first few sentences
            sentences = analysis.split('.')[:3]
            for sentence in sentences:
                if sentence.strip():
                    message += f"• {sentence.strip()}.\n"
        
        if len(analysis) > 500:
            message += f"\n*Full analysis: {len(analysis)} characters*"
        
        await self.send_message(message, "analysis")
    
    async def send_decision_summary(self, decision: Optional[TradingDecision]):
        """
        Send formatted trading decision with action details.
        
        Args:
            decision: TradingDecision object or None for no decision
        """
        if not decision:
            await self.send_message("**Decision:** HOLD - No trading action recommended", "decision")
            return
        
        message = f"🤔 **Trading Decision**\n\n"
        message += f"**Action:** {decision.action.value.upper()}\n"
        
        # Only show symbol and quantity for BUY/SELL decisions
        if decision.action in [TradingAction.BUY, TradingAction.SELL]:
            symbol_display = decision.symbol or 'Not specified'
            message += f"**Symbol:** {symbol_display}\n"
            if decision.quantity:
                message += f"**Quantity:** {decision.quantity}\n"
        
        message += f"**Confidence:** {float(decision.confidence):.1%}\n"
        
        # Truncate reasoning if too long
        reasoning = decision.reasoning
        if len(reasoning) > 200:
            reasoning = reasoning[:200] + "..."
        
        message += f"**Reasoning:** {reasoning}"
        
        await self.send_message(message, "decision")
    
    async def send_portfolio_summary(self, portfolio_msg: str):
        """
        Send formatted portfolio status summary.
        
        Args:
            portfolio_msg: Pre-formatted portfolio message
        """
        await self.send_message(portfolio_msg, "info")
    
    async def send_trade_execution(self, symbol: str, action: str, quantity: str, order_id: str):
        """
        Send trade execution confirmation.
        
        Args:
            symbol: Stock symbol
            action: Trading action (BUY/SELL)
            quantity: Number of shares
            order_id: Order identifier
        """
        message = f"**Trade Executed**\n\n"
        message += f"✅ {symbol} {action.upper()} {quantity} shares\n"
        message += f"📋 Order ID: {order_id}"
        
        await self.send_message(message, "success")
    
    async def send_workflow_complete(self):
        """Send workflow completion notification."""
        message = "**Workflow Complete**\n\n🎯 Trading analysis and execution cycle finished successfully!"
        await self.send_message(message, "success")
    
    async def send_error(self, error_message: str, context: str = ""):
        """
        Send error notification.
        
        Args:
            error_message: Error description
            context: Optional context about where error occurred
        """
        message = f"**Error**"
        if context:
            message += f" - {context}"
        message += f"\n\n{error_message}"
        
        await self.send_message(message, "error")
    
    def get_queue_size(self) -> int:
        """Get current number of messages in queue."""
        return self.message_queue.qsize()
    
    def is_queue_empty(self) -> bool:
        """Check if message queue is empty."""
        return self.message_queue.empty() 