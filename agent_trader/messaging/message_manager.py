"""
Message Manager for handling trading system notifications and message routing.

This manager handles business-level message operations including formatting,
templating, queuing, and routing messages to appropriate transports.

使用 tenacity 进行重试，使用 aiolimiter 进行速率限制。
"""

import asyncio
from agent_trader.utils.logging_config import get_logger
from typing import Dict, List, Any, Optional
from decimal import Decimal

from agent_trader.utils.timezone import utc_now, format_for_display

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
from aiolimiter import AsyncLimiter

from agent_trader.interfaces.message_transport import MessageTransport, MessageFormat
from agent_trader.models.trading_models import Order, Portfolio, Position
from config import settings
from agent_trader.utils.string_utils import safe_format_text
from agent_trader.utils.message_formatters import (
    format_alert_message,
    format_portfolio_message,
    format_order_message,
    format_workflow_message,
    format_trade_execution_message,
    format_tool_result_message,
    format_analysis_summary_message,
    format_decision_summary_message,
    format_reasoning_summary_message
)

logger = get_logger(__name__)

# 消息速率限制（从配置读取）
MESSAGE_RATE_LIMITER = AsyncLimiter(settings.message_rate_limit, 1.0)


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
    
    def __init__(self, transport: MessageTransport):
        """
        Initialize Message Manager.
        
        Args:
            transport: Message transport instance (required)
        """
        if transport is None:
            raise ValueError("MessageTransport is required")
        
        self.transport = transport
        self.is_processing = False
        self.processing_task = None
        self.message_queue = asyncio.Queue()
        self.failed_messages = []
        self._max_failed_messages = 100
        self.transport_initialized = False

        # 使用 aiolimiter 进行速率限制
        self._rate_limiter = MESSAGE_RATE_LIMITER

        # Message statistics
        self.stats = {
            'total_sent': 0,
            'total_failed': 0,
            'queue_size': 0,
            'last_sent': None,
            'processing_errors': 0,
            'initialization_attempts': 0
        }
    
    async def start_processing(self):
        """Start processing messages from the queue."""
        if self.is_processing:
            logger.warning("Message Manager is already processing")
            return
        
        # Initialize transport if needed
        await self._ensure_transport_initialized()
        
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
    
    async def _ensure_transport_initialized(self) -> bool:
        """
        确保 transport 已初始化并启动

        简化的初始化逻辑：
        - 检查 transport.is_initialized 和 transport.is_started
        - 如果未初始化/启动，则调用对应方法
        """
        if self.transport_initialized:
            return True

        try:
            self.stats['initialization_attempts'] += 1

            # 检查是否已初始化
            if not self.transport.is_initialized:
                logger.info("初始化 message transport...")
                if not await self.transport.initialize():
                    logger.warning("Message transport 初始化失败")
                    return False
                logger.info("Message transport 初始化成功")

            # 检查是否已启动
            if not self.transport.is_started:
                logger.info("启动 message transport...")
                if not await self.transport.start():
                    logger.warning("Message transport 启动失败")
                    return False
                logger.info("Message transport 启动成功")

            self.transport_initialized = True
            return True

        except Exception as e:
            logger.error(f"Transport 初始化错误: {e}")
            return False
    
    async def _process_messages(self):
        """后台任务：从队列处理消息"""
        logger.info("消息处理循环已启动")

        while self.is_processing:
            try:
                # 从队列获取消息（带超时）
                try:
                    message_data = await asyncio.wait_for(
                        self.message_queue.get(),
                        timeout=1.0
                    )
                    logger.debug(f"处理消息: {message_data.get('type', 'unknown')}")
                except asyncio.TimeoutError:
                    continue

                # 使用速率限制器
                await self._rate_limiter.acquire()

                # 发送消息（带重试）
                await self._send_message_with_retry(message_data)

                # 更新统计
                self.stats['queue_size'] = self.message_queue.qsize()

            except asyncio.CancelledError:
                logger.info("消息处理已取消")
                break
            except Exception as e:
                logger.error(f"处理消息时出错: {e}")
                self.stats['processing_errors'] += 1
                await asyncio.sleep(1)

        logger.info("消息处理循环已结束")

    async def _send_message_with_retry(self, message_data: Dict[str, Any]):
        """
        发送消息（使用 tenacity 重试）

        重试策略：指数退避，最多 3 次
        """
        message_text = message_data.get('text', '')
        message_type = message_data.get('type', 'info')

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(Exception),
            reraise=True
        )
        async def _send():
            # 检查 transport 是否可用
            if not self.transport_initialized:
                if not await self._ensure_transport_initialized():
                    raise RuntimeError("Transport 不可用")

            transport_available = True
            if hasattr(self.transport, 'is_available'):
                transport_available = self.transport.is_available()

            if not transport_available:
                raise RuntimeError("Transport 报告不可用")

            success = await self.transport.send_raw_message(
                content=message_text,
                format_type=MessageFormat.MARKDOWN
            )

            if not success:
                raise RuntimeError("Transport 发送失败")

            return True

        try:
            await _send()
            self.stats['total_sent'] += 1
            self.stats['last_sent'] = utc_now()
            logger.debug(f"消息发送成功: {message_type}")

        except Exception as e:
            logger.debug(f"消息发送失败 ({message_type}): {e}")
            self.stats['total_failed'] += 1
            self.failed_messages.append({
                'message': message_data,
                'failed_at': utc_now(),
                'error': str(e)
            })
            # 限制失败消息列表大小
            if len(self.failed_messages) > self._max_failed_messages:
                self.failed_messages = self.failed_messages[-self._max_failed_messages:]
    

    
    # Public API methods
    
    async def send_order_notification(self, order: Order, event_type: str):
        """
        Send order notification message.
        
        Args:
            order: Order object
            event_type: Type of event (created, filled, canceled, etc.)
        """
        try:
            formatted_message = format_order_message(order, event_type)
            await self._queue_message(formatted_message, 'order_notification')
            
        except Exception as e:
            logger.error(f"Error sending order notification: {e}")
    
    async def send_portfolio_update(self, portfolio: Portfolio):
        """
        Send portfolio update message.
        
        Args:
            portfolio: Portfolio object
        """
        try:
            formatted_message = format_portfolio_message(portfolio)
            await self._queue_message(formatted_message, 'portfolio_update')
            
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
            formatted_message = format_alert_message(message, alert_type)
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
            formatted_message = format_workflow_message(workflow_type, message, data)
            await self._queue_message(formatted_message, 'workflow_notification')
            
        except Exception as e:
            logger.error(f"Error sending workflow notification: {e}")
    
    async def send_error_alert(self, error: Exception, context: str = None):
        """
        Send error alert message.
        
        Args:
            error: Exception object
            context: Additional context information
        """
        try:
            error_message = f"{context}: {str(error)}" if context else str(error)
            formatted_message = format_alert_message(error_message, "error")
            await self._queue_message(formatted_message, 'error_alert')
            
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
            # Send message immediately to queue for processing
            await self._queue_message(message, message_type)
            logger.debug(f"Message queued: {message_type}")
            
        except Exception as e:
            logger.error(f"Error sending message: {e}")
    
    async def send_error(self, message: str, context: str = None):
        """
        Send an error message.
        
        Args:
            message: Error message
            context: Additional context information
        """
        try:
            error_message = f"*{context}*: {message}" if context else message
            formatted_message = format_alert_message(error_message, "error")
            await self._queue_message(formatted_message, 'error')
            
        except Exception as e:
            logger.error(f"Error sending error message: {e}")
    
    async def send_analysis_summary(self, analysis_text: str):
        """
        Send analysis summary message.
        
        Args:
            analysis_text: Analysis summary text
        """
        try:
            formatted_message = format_analysis_summary_message(analysis_text)
            await self._queue_message(formatted_message, 'analysis_summary')
            
        except Exception as e:
            logger.error(f"Error sending analysis summary: {e}")
    
    async def send_decision_summary(self, decision):
        """
        Send decision summary message.
        
        Args:
            decision: TradingDecision object or None
        """
        try:
            formatted_message = format_decision_summary_message(decision)
            await self._queue_message(formatted_message, 'decision_summary')
            
        except Exception as e:
            logger.error(f"Error sending decision summary: {e}")
    
    async def send_trade_execution(self, symbol: str, action: str, quantity: str, order_id: str):
        """
        Send trade execution notification.
        
        Args:
            symbol: Trading symbol
            action: Trade action (BUY/SELL)
            quantity: Quantity traded
            order_id: Order identifier
        """
        try:
            formatted_message = format_trade_execution_message(symbol, action, quantity, order_id)
            await self._queue_message(formatted_message, 'trade_execution')
            
        except Exception as e:
            logger.error(f"Error sending trade execution: {e}")
    
    async def send_workflow_complete(self):
        """
        Send workflow completion notification.
        """
        try:
            completion_message = f"""
✅ *Workflow Complete*

Trading analysis and execution workflow has completed successfully.

📅 *Time*: {format_for_display(utc_now())}
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
            formatted_message = format_tool_result_message(tool_name, tool_args, tool_result, success)
            await self._queue_message(formatted_message, 'tool_result')
            
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
            formatted_message = format_reasoning_summary_message(reasoning_text, tool_calls_count)
            await self._queue_message(formatted_message, 'reasoning_summary')
            
        except Exception as e:
            logger.error(f"Error sending reasoning summary: {e}")
    
    async def _queue_message(self, message: str, message_type: str):
        """Queue a message for processing."""
        message_data = {
            'text': message,
            'type': message_type,
            'timestamp': utc_now(),
            'retries': 0
        }
        
        # Add to queue
        await self.message_queue.put(message_data)
        self.stats['queue_size'] = self.message_queue.qsize()
        
        logger.debug(f"Message queued: {message_type}, Queue size: {self.stats['queue_size']}")
        
        # If processing is not started, start it
        if not self.is_processing:
            logger.info("Message processing not started, starting now...")
            await self.start_processing()
    
    # Statistics and utility methods
    
    def get_stats(self) -> Dict[str, Any]:
        """Get message manager statistics."""
        transport_available = False
        transport_info = "Unknown"
        
        try:
            if self.transport:
                if hasattr(self.transport, 'is_available'):
                    transport_available = self.transport.is_available()
                if hasattr(self.transport, 'get_transport_name'):
                    transport_info = self.transport.get_transport_name()
        except Exception as e:
            logger.debug(f"Error getting transport info: {e}")
        
        return {
            **self.stats,
            'queue_size': self.message_queue.qsize(),
            'is_processing': self.is_processing,
            'transport_available': transport_available,
            'transport_initialized': self.transport_initialized,
            'transport_info': transport_info
        }
    
    def get_failed_messages(self) -> List[Dict[str, Any]]:
        """Get list of failed messages."""
        return self.failed_messages.copy()
    
    def clear_failed_messages(self):
        """Clear the failed messages list."""
        self.failed_messages.clear()
        logger.info("Failed messages cleared")
    
    def get_queue_size(self) -> int:
        """Get current queue size."""
        return self.message_queue.qsize() 