"""
Message Manager for handling trading system notifications and message routing.

This manager handles business-level message operations including formatting,
templating, queuing, and routing messages to appropriate transports.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from decimal import Decimal

from src.interfaces.message_transport import MessageTransport
from src.interfaces.factory import get_message_transport
from src.models.trading_models import Order, Portfolio, Position, TradingEvent

logger = logging.getLogger(__name__)


class MessageManager:
    """
    Message Manager for handling trading system notifications and message routing.
    
    This manager provides:
    - Business-level message operations
    - Message formatting and templating
    - Queue management and throttling
    - Routing to appropriate transports
    - Retry logic for failed messages
    """
    
    def __init__(self, transport: MessageTransport = None):
        """
        Initialize Message Manager.
        
        Args:
            transport: Message transport instance (defaults to factory)
        """
        self.transport = transport or get_message_transport()
        self.is_processing = False
        self.processing_task = None  # Store the processing task reference
        self.message_queue = asyncio.Queue()
        self.failed_messages = []
        self.max_retries = 3
        self.retry_delay = 2.0  # seconds (much shorter retry delay)
        self.rate_limit_delay = 1.0  # seconds between messages
        self.last_message_time = 0
        
        # Message statistics
        self.stats = {
            'total_sent': 0,
            'total_failed': 0,
            'queue_size': 0,
            'last_sent': None
        }
    
    async def start_processing(self):
        """Start processing messages from the queue."""
        if self.is_processing:
            logger.warning("Message Manager is already processing")
            return
        
        self.is_processing = True
        logger.info("Message Manager started processing")
        
        # Start background task to process messages and keep reference
        self.processing_task = asyncio.create_task(self._process_messages())
        logger.info("Message processing background task started")
    
    async def stop_processing(self):
        """Stop processing messages."""
        self.is_processing = False
        
        # Cancel the processing task if it exists
        if self.processing_task and not self.processing_task.done():
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                logger.info("Message processing task cancelled")
        
        logger.info("Message Manager stopped processing")
    
    async def _process_messages(self):
        """Background task to process messages from the queue."""
        logger.info("Message processing loop started")
        while self.is_processing:
            try:
                # Get message from queue with timeout
                try:
                    message_data = await asyncio.wait_for(
                        self.message_queue.get(), 
                        timeout=1.0
                    )
                    logger.debug(f"Processing message: {message_data.get('type', 'unknown')}")
                except asyncio.TimeoutError:
                    continue
                
                # Process the message
                await self._send_message_with_retry(message_data)
                
                # Update stats
                self.stats['queue_size'] = self.message_queue.qsize()
                
                # Rate limiting
                await self._rate_limit()
                
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                await asyncio.sleep(1)
        
        logger.info("Message processing loop ended")
    
    async def _send_message_with_retry(self, message_data: Dict[str, Any]):
        """Send message with retry logic."""
        message_text = message_data.get('text', '')
        message_type = message_data.get('type', 'info')
        retries = message_data.get('retries', 0)
        
        try:
            # Send message via transport using plain text to avoid parsing issues
            from interfaces.message_transport import MessageFormat
            success = await self.transport.send_raw_message(
                content=message_text,
                format_type=MessageFormat.PLAIN_TEXT  # Use plain text instead of Markdown
            )
            
            if success:
                self.stats['total_sent'] += 1
                self.stats['last_sent'] = datetime.now()
                logger.debug(f"Message sent successfully: {message_type}")
            else:
                raise Exception("Transport failed to send message")
                
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            
            if retries < self.max_retries:
                # Retry later
                message_data['retries'] = retries + 1
                await asyncio.sleep(self.retry_delay)
                await self.message_queue.put(message_data)
                logger.info(f"Message queued for retry ({retries + 1}/{self.max_retries})")
            else:
                # Max retries reached
                self.stats['total_failed'] += 1
                self.failed_messages.append({
                    'message': message_data,
                    'failed_at': datetime.now(),
                    'error': str(e)
                })
                logger.error(f"Message failed after {self.max_retries} retries")
    
    async def _rate_limit(self):
        """Apply rate limiting between messages."""
        import time
        current_time = time.time()
        time_since_last = current_time - self.last_message_time
        
        if time_since_last < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - time_since_last)
        
        self.last_message_time = time.time()
    
    def _escape_markdown(self, text: str, max_length: int = None) -> str:
        """
        Escape special Markdown characters in text to prevent parsing errors.
        
        Args:
            text: Text to escape
            max_length: Maximum length to truncate to (optional)
            
        Returns:
            Escaped and optionally truncated text
        """
        if not text:
            return ""
        
        # Escape common Markdown special characters
        escaped = text.replace('*', '\\*').replace('_', '\\_').replace('[', '\\[').replace(']', '\\]')
        escaped = escaped.replace('`', '\\`').replace('~', '\\~')
        
        # Truncate if specified
        if max_length and len(escaped) > max_length:
            escaped = escaped[:max_length] + "..."
        
        return escaped
    
    # Public API methods
    
    async def send_order_notification(self, order: Order, event_type: str):
        """
        Send order notification message.
        
        Args:
            order: Order object
            event_type: Type of event (created, filled, canceled, etc.)
        """
        try:
            # Use transport's specialized method if available
            if hasattr(self.transport, 'send_order_notification'):
                await self.transport.send_order_notification(order, event_type)
                return
            
            # Fallback to formatted message
            message = self._format_order_message(order, event_type)
            await self._queue_message(message, 'order_notification')
            
        except Exception as e:
            logger.error(f"Error sending order notification: {e}")
    
    async def send_portfolio_update(self, portfolio: Portfolio):
        """
        Send portfolio update message.
        
        Args:
            portfolio: Portfolio object
        """
        try:
            # Use transport's specialized method if available
            if hasattr(self.transport, 'send_portfolio_update'):
                await self.transport.send_portfolio_update(portfolio)
                return
            
            # Fallback to formatted message
            message = self._format_portfolio_message(portfolio)
            await self._queue_message(message, 'portfolio_update')
            
        except Exception as e:
            logger.error(f"Error sending portfolio update: {e}")
    
    async def send_system_alert(self, message: str, alert_type: str = "info"):
        """
        Send system alert message.
        
        Args:
            message: Alert message
            alert_type: Type of alert (info, warning, error, success)
        """
        try:
            # Use transport's specialized method if available
            if hasattr(self.transport, 'send_system_alert'):
                await self.transport.send_system_alert(message, alert_type)
                return
            
            # Fallback to formatted message
            formatted_message = self._format_alert_message(message, alert_type)
            await self._queue_message(formatted_message, 'system_alert')
            
        except Exception as e:
            logger.error(f"Error sending system alert: {e}")
    
    async def send_workflow_notification(self, workflow_type: str, message: str, data: Dict[str, Any] = None):
        """
        Send workflow notification message.
        
        Args:
            workflow_type: Type of workflow (analysis, rebalance, etc.)
            message: Notification message
            data: Additional data context
        """
        try:
            formatted_message = self._format_workflow_message(workflow_type, message, data)
            await self._queue_message(formatted_message, 'workflow_notification')
            
        except Exception as e:
            logger.error(f"Error sending workflow notification: {e}")
    
    async def send_error_alert(self, error: Exception, context: str = None):
        """
        Send error alert message.
        
        Args:
            error: Exception object
            context: Additional context about the error
        """
        try:
            error_message = f"Error: {str(error)}"
            if context:
                error_message += f"\nContext: {context}"
            
            await self.send_system_alert(error_message, "error")
            
        except Exception as e:
            logger.error(f"Error sending error alert: {e}")
    
    async def send_message(self, message: str, message_type: str = "info"):
        """
        Send a general message.
        
        Args:
            message: Message text
            message_type: Type of message (info, warning, error, success)
        """
        try:
            await self.send_system_alert(message, message_type)
        except Exception as e:
            logger.error(f"Error sending message: {e}")
    
    async def send_error(self, message: str, context: str = None):
        """
        Send an error message.
        
        Args:
            message: Error message text
            context: Additional context about the error
        """
        try:
            error_message = message
            if context:
                error_message += f"\nContext: {context}"
            
            await self.send_system_alert(error_message, "error")
        except Exception as e:
            logger.error(f"Error sending error message: {e}")
    
    async def send_analysis_summary(self, analysis_text: str):
        """
        Send analysis summary message.
        
        Args:
            analysis_text: Analysis summary text
        """
        try:
            # Escape and truncate analysis text
            safe_analysis = self._escape_markdown(analysis_text, max_length=800)
            
            summary_message = f"""
📊 *Analysis Summary*

{safe_analysis}

📅 *Time*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """
            
            await self._queue_message(summary_message.strip(), 'analysis_summary')
            
        except Exception as e:
            logger.error(f"Error sending analysis summary: {e}")
    
    async def send_decision_summary(self, decision):
        """
        Send decision summary message.
        
        Args:
            decision: TradingDecision object or None
        """
        try:
            if decision is None:
                decision_message = f"""
🤖 **Trading Decision**

📊 **Action**: HOLD
💭 **Reason**: No trading decision made

📅 **Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """
            else:
                # Safely handle None values
                price_value = getattr(decision, 'price', None)
                price_str = f"${float(price_value):,.2f}" if price_value is not None else "Market Price"
                
                quantity_value = getattr(decision, 'quantity', None)
                quantity_str = str(quantity_value) if quantity_value is not None else "N/A"
                
                decision_message = f"""
🤖 **Trading Decision**

📊 **Action**: {decision.action.value if hasattr(decision, 'action') else 'HOLD'}
📈 **Symbol**: {getattr(decision, 'symbol', 'N/A')}
📦 **Quantity**: {quantity_str}
💰 **Price**: {price_str}
💭 **Reason**: {getattr(decision, 'reasoning', 'No reason provided')}

📅 **Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """
            
            await self._queue_message(decision_message.strip(), 'decision_summary')
            
        except Exception as e:
            logger.error(f"Error sending decision summary: {e}")
    
    async def send_trade_execution(self, symbol: str, action: str, quantity: str, order_id: str):
        """
        Send trade execution notification.
        
        Args:
            symbol: Trading symbol
            action: Trading action (BUY/SELL)
            quantity: Order quantity
            order_id: Order ID
        """
        try:
            execution_message = f"""
✅ **Trade Executed**

📊 **Symbol**: {symbol}
📈 **Action**: {action.upper()}
📦 **Quantity**: {quantity}
🔢 **Order ID**: {order_id}

📅 **Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """
            
            await self._queue_message(execution_message.strip(), 'trade_execution')
            
        except Exception as e:
            logger.error(f"Error sending trade execution: {e}")
    
    async def send_workflow_complete(self):
        """
        Send workflow completion notification.
        """
        try:
            completion_message = f"""
🎉 **Workflow Complete**

The trading workflow has been completed successfully.

📅 **Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """
            
            await self._queue_message(completion_message.strip(), 'workflow_complete')
            
        except Exception as e:
            logger.error(f"Error sending workflow completion: {e}")
    
    async def send_tool_result(self, tool_name: str, tool_args: dict, tool_result: str, success: bool = True):
        """
        Send detailed tool execution result.
        
        Args:
            tool_name: Name of the executed tool
            tool_args: Arguments passed to the tool
            tool_result: Result returned by the tool
            success: Whether the tool execution was successful
        """
        try:
            emoji = "✅" if success else "❌"
            status = "Success" if success else "Failed"
            
            # Format arguments nicely
            args_str = ""
            if tool_args:
                args_str = "\n*Arguments:*\n"
                for key, value in tool_args.items():
                    # Escape argument values as well
                    safe_value = self._escape_markdown(str(value), max_length=100)
                    args_str += f"• {key}: {safe_value}\n"
            
            # Escape and truncate tool result
            result_preview = self._escape_markdown(tool_result, max_length=400)
            
            tool_message = f"""
🔧 *Tool Execution {status}*

📋 *Tool*: {tool_name}
{args_str}
📊 *Result*:
{result_preview}

📅 *Time*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """
            
            await self._queue_message(tool_message.strip(), 'tool_result')
            
        except Exception as e:
            logger.error(f"Error sending tool result: {e}")
    
    async def send_reasoning_summary(self, reasoning_text: str, tool_calls_count: int = 0):
        """
        Send AI reasoning summary with tool usage statistics.
        
        Args:
            reasoning_text: The AI's reasoning and analysis
            tool_calls_count: Number of tools used in the analysis
        """
        try:
            # Escape and truncate reasoning text
            safe_reasoning = self._escape_markdown(reasoning_text, max_length=800)
            
            reasoning_message = f"""
🧠 *AI Reasoning & Analysis*

{safe_reasoning}

📊 *Tool Usage*: {tool_calls_count} tools executed
📅 *Time*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """
            
            await self._queue_message(reasoning_message.strip(), 'reasoning_summary')
            
        except Exception as e:
            logger.error(f"Error sending reasoning summary: {e}")
    
    async def _queue_message(self, message: str, message_type: str):
        """Queue a message for processing."""
        message_data = {
            'text': message,
            'type': message_type,
            'timestamp': datetime.now(),
            'retries': 0
        }
        
        await self.message_queue.put(message_data)
        self.stats['queue_size'] = self.message_queue.qsize()
        
        logger.debug(f"Message queued: {message_type}, Queue size: {self.stats['queue_size']}")
        logger.debug(f"Message preview: {message[:100]}...")  # Log first 100 chars
    
    # Message formatting methods
    
    def _format_order_message(self, order: Order, event_type: str) -> str:
        """Format order notification message."""
        emoji_map = {
            'created': '📝',
            'filled': '✅',
            'partially_filled': '📊',
            'canceled': '❌',
            'rejected': '🚫'
        }
        
        emoji = emoji_map.get(event_type, '📝')
        title = f"Order {event_type.replace('_', ' ').title()}"
        
        message = f"""
{emoji} **{title}**

📊 Symbol: {order.symbol}
📈 Side: {order.side.value.upper()}
📦 Quantity: {order.quantity}
💰 Type: {order.order_type.value.upper()}
"""
        
        if order.price:
            message += f"💵 Price: ${float(order.price):,.2f}\n"
        
        if order.filled_quantity and order.filled_quantity > 0:
            message += f"✅ Filled: {order.filled_quantity}\n"
        
        if order.filled_price:
            message += f"💲 Fill Price: ${float(order.filled_price):,.2f}\n"
        
        if order.id:
            message += f"🔢 Order ID: {order.id}\n"
        
        return message.strip()
    
    def _format_portfolio_message(self, portfolio: Portfolio) -> str:
        """Format portfolio update message."""
        day_pnl_pct = (float(portfolio.day_pnl) / float(portfolio.equity)) * 100
        pnl_emoji = "📈" if portfolio.day_pnl > 0 else "📉" if portfolio.day_pnl < 0 else "➡️"
        
        message = f"""
💼 **Portfolio Update**

💰 Total Equity: ${float(portfolio.equity):,.2f}
{pnl_emoji} Day P&L: ${float(portfolio.day_pnl):,.2f} ({day_pnl_pct:.2f}%)
📊 Market Value: ${float(portfolio.market_value):,.2f}
💵 Cash: ${float(portfolio.cash):,.2f}
📈 Total P&L: ${float(portfolio.total_pnl):,.2f}

📦 Positions: {len(portfolio.positions)}
        """
        
        return message.strip()
    
    def _format_alert_message(self, message: str, alert_type: str) -> str:
        """Format system alert message."""
        emoji_map = {
            'info': 'ℹ️',
            'warning': '⚠️',
            'error': '🚨',
            'success': '✅'
        }
        
        emoji = emoji_map.get(alert_type, 'ℹ️')
        title = alert_type.upper()
        
        # Escape the message text to prevent Markdown issues
        safe_message = self._escape_markdown(message, max_length=600)
        
        formatted_message = f"""
{emoji} *{title}*

{safe_message}

📅 *Time*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        
        return formatted_message.strip()
    
    def _format_workflow_message(self, workflow_type: str, message: str, data: Dict[str, Any] = None) -> str:
        """Format workflow notification message."""
        emoji_map = {
            'analysis': '📊',
            'rebalance': '⚖️',
            'risk_check': '🛡️',
            'eod_analysis': '🌅',
            'news_analysis': '📰'
        }
        
        emoji = emoji_map.get(workflow_type, '🔄')
        title = workflow_type.replace('_', ' ').title()
        
        # Escape the message text to prevent Markdown issues
        safe_message = self._escape_markdown(message, max_length=600)
        
        formatted_message = f"""
{emoji} *{title}*

{safe_message}
        """
        
        if data:
            formatted_message += "\n\n📋 *Details:*\n"
            for key, value in data.items():
                # Escape the data values as well
                safe_value = self._escape_markdown(str(value), max_length=100)
                formatted_message += f"• {key}: {safe_value}\n"
        
        return formatted_message.strip()
    
    # Statistics and monitoring
    
    def get_stats(self) -> Dict[str, Any]:
        """Get message statistics."""
        return {
            **self.stats,
            'queue_size': self.message_queue.qsize(),
            'failed_messages_count': len(self.failed_messages),
            'is_processing': self.is_processing,
            'transport_info': self.transport.get_transport_info() if hasattr(self.transport, 'get_transport_info') else None
        }
    
    def get_failed_messages(self) -> List[Dict[str, Any]]:
        """Get list of failed messages."""
        return self.failed_messages.copy()
    
    def clear_failed_messages(self):
        """Clear the failed messages list."""
        self.failed_messages.clear()
        logger.info("Failed messages list cleared")


# Convenience function for creating message manager
def create_message_manager(transport: MessageTransport = None) -> MessageManager:
    """
    Create a message manager instance.
    
    Args:
        transport: Message transport instance (defaults to factory)
        
    Returns:
        MessageManager instance
    """
    return MessageManager(transport=transport)


# Convenience function for getting message manager
def get_message_manager() -> MessageManager:
    """
    Get a message manager instance using default transport.
    
    Returns:
        MessageManager instance
    """
    return create_message_manager() 