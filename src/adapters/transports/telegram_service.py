"""
Telegram Service - Combined transport and bot handler functionality.

This service handles both outgoing message transmission and incoming command processing
for Telegram integration with the trading system.
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, List
from decimal import Decimal
from datetime import datetime
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError, Conflict, NetworkError, TimedOut

from src.interfaces.message_transport import MessageTransport, MessageFormat
from src.models.trading_models import Order, Portfolio, Position
from config import settings

logger = logging.getLogger(__name__)


class TelegramService(MessageTransport):
    """
    Combined Telegram service for both message transport and bot command handling.
    
    This service provides:
    - Message transmission capabilities (implementing MessageTransport)
    - Interactive command processing (/help, /status, etc.)
    - Rate limiting and connection management
    - User authorization
    - Conflict resolution for multiple instances
    """
    
    def __init__(self, 
                 bot_token: str = None, 
                 chat_id: str = None,
                 trading_system=None):
        """
        Initialize Telegram service.
        
        Args:
            bot_token: Telegram bot token (defaults to settings)
            chat_id: Authorized chat ID (defaults to settings)
            trading_system: Reference to TradingSystem instance
        """
        self.bot_token = bot_token or settings.telegram_bot_token
        self.chat_id = chat_id or settings.telegram_chat_id
        self.trading_system = trading_system
        
        self.bot = None
        self.application = None
        self.is_running = False
        self.is_initializing = False
        self.last_message_time = 0
        self.rate_limit_delay = 1.0  # seconds
        self.max_retries = 3
        self.retry_delay = 5.0  # seconds
        
        # Command descriptions
        self.commands = {
            'start': 'Start the bot and get welcome message',
            'help': 'Show available commands',
            'status': 'Get trading system status',
            'portfolio': 'Get current portfolio summary',
            'orders': 'Get active orders',
            'positions': 'Get current positions',
            'analyze': 'Manually trigger AI trading analysis',
            'start_trading': 'Start trading operations',
            'stop_trading': 'Stop trading operations',
            'emergency_stop': 'Emergency stop all operations'
        }
    
    async def initialize(self) -> bool:
        """
        Initialize the Telegram service with conflict resolution.
        
        Returns:
            True if initialization successful, False otherwise
        """
        if self.is_initializing:
            logger.warning("Telegram service is already initializing")
            return False
        
        self.is_initializing = True
        
        try:
            if not self.bot_token or self.bot_token == "test_token":
                logger.warning("Telegram bot token not configured or is test token - Telegram service will be disabled")
                return False
            
            # Create bot and application
            self.bot = Bot(token=self.bot_token)
            self.application = Application.builder().token(self.bot_token).build()
            
            # Register command handlers
            self._register_handlers()
            
            # Test connection and handle conflicts
            retry_count = 0
            while retry_count < self.max_retries:
                try:
                    # Test bot connection
                    await self.bot.get_me()
                    logger.info("Telegram bot connection test successful")
                    break
                    
                except Conflict as e:
                    retry_count += 1
                    logger.warning(f"Telegram bot conflict detected (attempt {retry_count}/{self.max_retries}): {e}")
                    
                    if retry_count < self.max_retries:
                        logger.info(f"Waiting {self.retry_delay} seconds before retry...")
                        await asyncio.sleep(self.retry_delay)
                        
                        # Try to clear existing webhook if any
                        try:
                            await self.bot.delete_webhook()
                            logger.info("Cleared existing webhook")
                        except Exception as webhook_error:
                            logger.debug(f"Could not clear webhook: {webhook_error}")
                        
                        # Wait a bit more for other instances to timeout
                        await asyncio.sleep(self.retry_delay)
                    else:
                        logger.error("Failed to resolve Telegram bot conflict after multiple retries")
                        logger.error("Please ensure no other instances of the bot are running")
                        return False
                        
                except (NetworkError, TimedOut) as e:
                    retry_count += 1
                    logger.warning(f"Network error connecting to Telegram (attempt {retry_count}/{self.max_retries}): {e}")
                    
                    if retry_count < self.max_retries:
                        await asyncio.sleep(self.retry_delay)
                    else:
                        logger.error("Failed to connect to Telegram after multiple retries")
                        return False
                        
                except Exception as e:
                    logger.error(f"Unexpected error initializing Telegram service: {e}")
                    return False
            
            logger.info("Telegram service initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Telegram service: {e}")
            return False
        finally:
            self.is_initializing = False
    
    async def start(self) -> bool:
        """
        Start the Telegram service with conflict resolution.
        
        Returns:
            True if start successful, False otherwise
        """
        try:
            if self.is_running:
                logger.warning("Telegram service is already running")
                return True
            
            if not self.application:
                if not await self.initialize():
                    return False
            
            # Start the application with retry logic
            retry_count = 0
            while retry_count < self.max_retries:
                try:
                    await self.application.initialize()
                    await self.application.start()
                    
                    # Start polling with conflict handling
                    await self.application.updater.start_polling(
                        drop_pending_updates=True  # Drop old updates to avoid conflicts
                    )
                    
                    self.is_running = True
                    logger.info("Telegram service started successfully - ready for messages and commands")
                    return True
                    
                except Conflict as e:
                    retry_count += 1
                    logger.warning(f"Conflict starting Telegram service (attempt {retry_count}/{self.max_retries}): {e}")
                    
                    if retry_count < self.max_retries:
                        logger.info(f"Waiting {self.retry_delay} seconds before retry...")
                        await asyncio.sleep(self.retry_delay)
                        
                        # Try to stop and restart
                        try:
                            await self.application.stop()
                            await self.application.shutdown()
                        except Exception as stop_error:
                            logger.debug(f"Error stopping application during retry: {stop_error}")
                        
                        # Reinitialize
                        if not await self.initialize():
                            return False
                    else:
                        logger.error("Failed to start Telegram service due to persistent conflicts")
                        logger.error("Please check for other running instances and restart the system")
                        return False
                        
                except Exception as e:
                    logger.error(f"Error starting Telegram service: {e}")
                    return False
                    
            return False
            
        except Exception as e:
            logger.error(f"Failed to start Telegram service: {e}")
            return False
    
    async def stop(self) -> bool:
        """
        Stop the Telegram service gracefully.
        
        Returns:
            True if stop successful, False otherwise
        """
        try:
            if not self.is_running:
                logger.debug("Telegram service is not running")
                return True
            
            self.is_running = False
            
            if self.application:
                try:
                    # Stop polling first
                    await self.application.updater.stop()
                    logger.debug("Telegram updater stopped")
                    
                    # Stop application
                    await self.application.stop()
                    logger.debug("Telegram application stopped")
                    
                    # Shutdown application
                    await self.application.shutdown()
                    logger.debug("Telegram application shutdown complete")
                    
                except Exception as e:
                    logger.warning(f"Error during Telegram service shutdown: {e}")
                    # Continue with cleanup even if there are errors
            
            # Clear references
            self.application = None
            self.bot = None
            
            logger.info("Telegram service stopped successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping Telegram service: {e}")
            return False
    
    async def _handle_polling_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle polling errors"""
        error = context.error
        
        if isinstance(error, Conflict):
            logger.warning(f"Telegram polling conflict: {error}")
            logger.warning("Another bot instance might be running. Consider restarting the system.")
        elif isinstance(error, (NetworkError, TimedOut)):
            logger.warning(f"Telegram network error: {error}")
        else:
            logger.error(f"Telegram polling error: {error}")
    
    # MessageTransport interface implementation
    
    async def send_raw_message(self, 
                              content: str, 
                              format_type: MessageFormat = MessageFormat.PLAIN_TEXT,
                              **kwargs) -> bool:
        """
        Send a raw message via Telegram.
        
        Args:
            content: Message content
            format_type: Message format (plain_text, markdown, html, json)
            **kwargs: Additional parameters (chat_id, etc.)
            
        Returns:
            True if message sent successfully, False otherwise
        """
        try:
            if not self.bot:
                logger.debug("Telegram bot not initialized - message not sent")
                return False
            
            # Rate limiting
            await self._rate_limit()
            
            target_chat_id = kwargs.get('chat_id') or self.chat_id
            if not target_chat_id or target_chat_id == "test_chat_id":
                logger.debug("No valid chat ID configured for message sending")
                return False
            
            # Convert format type to Telegram parse mode
            parse_mode_map = {
                MessageFormat.PLAIN_TEXT: None,
                MessageFormat.MARKDOWN: "Markdown",
                MessageFormat.HTML: "HTML",
                MessageFormat.JSON: None  # Send as plain text
            }
            
            parse_mode = parse_mode_map.get(format_type, "Markdown")
            
            try:
                await self.bot.send_message(
                    chat_id=target_chat_id,
                    text=content,
                    parse_mode=parse_mode
                )
                
                logger.debug(f"Raw message sent to Telegram chat {target_chat_id}")
                return True
                
            except TelegramError as e:
                # If Markdown parsing fails, try sending as plain text
                if "Can't parse entities" in str(e) and parse_mode == "Markdown":
                    logger.warning(f"Markdown parsing failed, retrying as plain text: {e}")
                    try:
                        await self.bot.send_message(
                            chat_id=target_chat_id,
                            text=content,
                            parse_mode=None
                        )
                        logger.debug(f"Raw message sent as plain text to Telegram chat {target_chat_id}")
                        return True
                    except Exception as retry_error:
                        logger.error(f"Failed to send message even as plain text: {retry_error}")
                        return False
                else:
                    logger.error(f"Telegram API error: {e}")
                    return False
            
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False
    
    async def send_message(self, message: str, chat_id: str = None) -> bool:
        """
        Send a message via Telegram (convenience method).
        
        Args:
            message: Message content
            chat_id: Target chat ID (defaults to configured chat_id)
            
        Returns:
            True if message sent successfully, False otherwise
        """
        return await self.send_raw_message(
            content=message, 
            format_type=MessageFormat.MARKDOWN,
            chat_id=chat_id
        )
    
    def is_available(self) -> bool:
        """
        Check if the transport is available and ready to send messages.
        
        Returns:
            True if available, False otherwise
        """
        return (
            bool(self.bot_token) and 
            self.bot_token != "test_token" and
            bool(self.chat_id) and 
            self.chat_id != "test_chat_id" and
            bool(self.bot) and 
            self.is_running
        )
    
    def get_rate_limits(self) -> Dict[str, Any]:
        """
        Get rate limit information for this transport.
        
        Returns:
            Dictionary containing rate limit information
        """
        return {
            "provider": "Telegram",
            "rate_limit_delay": self.rate_limit_delay,
            "messages_per_second": 1.0 / self.rate_limit_delay if self.rate_limit_delay > 0 else float('inf'),
            "messages_per_minute": 60.0 / self.rate_limit_delay if self.rate_limit_delay > 0 else float('inf'),
            "burst_limit": 1,  # Telegram allows 1 message at a time
            "daily_limit": None,  # No daily limit enforced by our implementation
            "description": "Telegram Bot API rate limits with anti-flood protection"
        }
    
    def get_transport_name(self) -> str:
        """Get the transport name."""
        return "Telegram"
    
    def get_transport_info(self) -> Dict[str, Any]:
        """Get transport information."""
        return {
            "name": "Telegram Service",
            "type": "combined_transport_bot",
            "description": "Combined Telegram message transport and bot command handler",
            "status": {
                "initialized": bool(self.bot),
                "running": self.is_running,
                "bot_configured": bool(self.bot_token),
                "chat_configured": bool(self.chat_id),
                "trading_system_connected": self.trading_system is not None
            },
            "commands": self.commands,
            "rate_limit_delay": self.rate_limit_delay
        }
    
    # Bot command handling
    
    def _register_handlers(self):
        """Register command and message handlers."""
        
        # Command handlers
        self.application.add_handler(CommandHandler("start", self._handle_start))
        self.application.add_handler(CommandHandler("help", self._handle_help))
        self.application.add_handler(CommandHandler("status", self._handle_status))
        self.application.add_handler(CommandHandler("portfolio", self._handle_portfolio))
        self.application.add_handler(CommandHandler("orders", self._handle_orders))
        self.application.add_handler(CommandHandler("positions", self._handle_positions))
        self.application.add_handler(CommandHandler("analyze", self._handle_analyze))
        self.application.add_handler(CommandHandler("start_trading", self._handle_start_trading))
        self.application.add_handler(CommandHandler("stop_trading", self._handle_stop_trading))
        self.application.add_handler(CommandHandler("emergency_stop", self._handle_emergency_stop))
        
        # Message handler for non-commands
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
        
        # Error handler
        self.application.add_error_handler(self._handle_polling_error)
    
    def _is_authorized(self, update: Update) -> bool:
        """Check if the user is authorized to use the bot."""
        if not self.chat_id:
            return True  # If no chat ID configured, allow all
        
        return str(update.effective_chat.id) == str(self.chat_id)
    
    async def _rate_limit(self):
        """Apply rate limiting to prevent flooding."""
        import time
        current_time = time.time()
        time_since_last = current_time - self.last_message_time
        
        if time_since_last < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - time_since_last)
        
        self.last_message_time = time.time()
    
    # Command handlers
    
    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        if not self._is_authorized(update):
            await update.message.reply_text("❌ Unauthorized access")
            return
        
        welcome_text = f"""
🤖 **LLM Trading Agent Bot**

Welcome to your personal trading assistant! I can help you monitor and control your trading system.

Use /help to see available commands.

📊 **Current Status**: {("🟢 Active" if self.trading_system and self.trading_system.is_running else "🔴 Inactive")}

⚠️ **Important**: This bot controls real trading operations. Use with caution.
        """
        
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
    
    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        if not self._is_authorized(update):
            await update.message.reply_text("❌ Unauthorized access")
            return
        
        help_text = "🤖 **Available Commands:**\n\n"
        
        for command, description in self.commands.items():
            help_text += f"/{command} - {description}\n"
        
        help_text += "\n📱 **Quick Actions:**\n"
        help_text += "/status - Quick system overview\n"
        help_text += "/portfolio - Current holdings\n"
        help_text += "/emergency_stop - Immediate stop\n"
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def _handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        if not self._is_authorized(update):
            await update.message.reply_text("❌ Unauthorized access")
            return
        
        try:
            if not self.trading_system:
                await update.message.reply_text("❌ Trading system not available")
                return
            
            status = await self.trading_system.get_status()
            
            status_text = f"""
📊 **Trading System Status**

🔄 **System**: {status.get('status', 'Unknown').upper()}
📈 **Trading**: {'🟢 Enabled' if status.get('trading_enabled') else '🔴 Disabled'}
🏪 **Market**: {'🟢 Open' if status.get('market_open') else '🔴 Closed'}

💰 **Portfolio**:
• Equity: ${float(status.get('equity', 0)):,.2f}
• Day P&L: ${float(status.get('day_pnl', 0)):,.2f}
• Active Orders: {status.get('active_orders', 0)}
• Positions: {status.get('positions', 0)}

📅 **Last Update**: {status.get('last_update', 'Unknown')}
            """
            
            await update.message.reply_text(status_text, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error handling status command: {e}")
            await update.message.reply_text("❌ Error retrieving system status")
    
    async def _handle_portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /portfolio command."""
        if not self._is_authorized(update):
            await update.message.reply_text("❌ Unauthorized access")
            return
        
        try:
            if not self.trading_system:
                await update.message.reply_text("❌ Trading system not available")
                return
            
            portfolio = await self.trading_system.get_portfolio()
            
            portfolio_text = f"""
💼 **Portfolio Summary**

💰 **Total Value**: ${float(portfolio.equity):,.2f}
📈 **Cash**: ${float(portfolio.cash):,.2f}
📊 **Market Value**: ${float(portfolio.market_value):,.2f}
📈 **Day P&L**: ${float(portfolio.day_pnl):,.2f} ({float(portfolio.day_pnl)/float(portfolio.equity)*100:.2f}%)
📊 **Total P&L**: ${float(portfolio.total_pnl):,.2f}

**Positions** ({len(portfolio.positions)}):
            """
            
            for position in portfolio.positions[:10]:  # Show top 10 positions
                pnl_pct = float(position.unrealized_pnl_percentage) * 100
                pnl_emoji = "📈" if position.unrealized_pnl > 0 else "📉" if position.unrealized_pnl < 0 else "➡️"
                
                portfolio_text += f"""
{pnl_emoji} **{position.symbol}**: {position.quantity} shares
   Value: ${float(position.market_value):,.2f}
   P&L: ${float(position.unrealized_pnl):,.2f} ({pnl_pct:.2f}%)
                """
            
            if len(portfolio.positions) > 10:
                portfolio_text += f"\n... and {len(portfolio.positions) - 10} more positions"
            
            await update.message.reply_text(portfolio_text, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error handling portfolio command: {e}")
            await update.message.reply_text("❌ Error retrieving portfolio information")
    
    async def _handle_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /orders command."""
        if not self._is_authorized(update):
            await update.message.reply_text("❌ Unauthorized access")
            return
        
        try:
            if not self.trading_system:
                await update.message.reply_text("❌ Trading system not available")
                return
            
            orders = await self.trading_system.get_active_orders()
            
            if not orders:
                await update.message.reply_text("📋 No active orders")
                return
            
            orders_text = f"📋 **Active Orders** ({len(orders)}):\n\n"
            
            for order in orders:
                price_str = f"${float(order.price):,.2f}" if order.price else "Market"
                orders_text += f"""
🔄 **{order.symbol}** {order.side.value.upper()}
   Qty: {order.quantity} @ {price_str}
   Status: {order.status.value.upper()}
   ID: {order.id or 'N/A'}
                """
            
            await update.message.reply_text(orders_text, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error handling orders command: {e}")
            await update.message.reply_text("❌ Error retrieving active orders")
    
    async def _handle_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /positions command."""
        # This is similar to portfolio but focuses only on positions
        await self._handle_portfolio(update, context)
    
    async def _handle_analyze(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /analyze command - manually trigger AI trading analysis."""
        if not self._is_authorized(update):
            await update.message.reply_text("❌ Unauthorized access")
            return
        
        try:
            if not self.trading_system:
                await update.message.reply_text("❌ Trading system not available")
                return
            
            # Check if system is shutting down
            if hasattr(self.trading_system, 'is_shutting_down') and self.trading_system.is_shutting_down:
                await update.message.reply_text("🔄 System is shutting down, please try again after restart")
                return
            
            # Send immediate confirmation
            await update.message.reply_text("🤖 *AI Analysis Started*\n\nRunning intelligent trading analysis...\n\nThis may take a few moments.")
            
            # Trigger manual analysis with cancellation handling
            try:
                result = await self.trading_system.run_manual_analysis()
                
                # Handle different result types
                if isinstance(result, dict):
                    if result.get("success"):
                        await update.message.reply_text("✅ *Analysis Complete*\n\nAI analysis has been completed. Check the trading notifications for results.")
                    else:
                        message = result.get("message", "Analysis failed")
                        if "cancelled" in message.lower() or "shutting down" in message.lower():
                            await update.message.reply_text("🔄 *Analysis Cancelled*\n\nSystem is shutting down. Please try again after restart.")
                        else:
                            await update.message.reply_text(f"❌ *Analysis Failed*\n\n{message}")
                else:
                    # Fallback for unexpected result types
                    await update.message.reply_text("✅ *Analysis Complete*\n\nAI analysis has been completed. Check the trading notifications for results.")
                    
            except asyncio.CancelledError:
                logger.info("Analysis command cancelled due to system shutdown")
                try:
                    await update.message.reply_text("🔄 *Analysis Cancelled*\n\nSystem is shutting down. Please try again after restart.")
                except Exception as e:
                    logger.debug(f"Could not send cancellation message: {e}")
                return
            
        except asyncio.CancelledError:
            logger.info("Analysis command handler cancelled due to system shutdown")
            return
        except Exception as e:
            logger.error(f"Error handling analyze command: {e}")
            try:
                await update.message.reply_text("❌ Error running AI analysis")
            except Exception as reply_error:
                logger.debug(f"Could not send error reply: {reply_error}")
    
    async def _handle_start_trading(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start_trading command."""
        if not self._is_authorized(update):
            await update.message.reply_text("❌ Unauthorized access")
            return
        
        try:
            if not self.trading_system:
                await update.message.reply_text("❌ Trading system not available")
                return
            
            # Check if system is shutting down
            if hasattr(self.trading_system, 'is_shutting_down') and self.trading_system.is_shutting_down:
                await update.message.reply_text("🔄 System is shutting down, command not available")
                return
            
            await self.trading_system.start_trading()
            await update.message.reply_text("✅ Trading operations started")
            
        except asyncio.CancelledError:
            logger.info("Start trading command cancelled due to system shutdown")
            return
        except Exception as e:
            logger.error(f"Error handling start trading command: {e}")
            try:
                await update.message.reply_text("❌ Error starting trading operations")
            except Exception as reply_error:
                logger.debug(f"Could not send error reply: {reply_error}")
    
    async def _handle_stop_trading(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stop_trading command."""
        if not self._is_authorized(update):
            await update.message.reply_text("❌ Unauthorized access")
            return
        
        try:
            if not self.trading_system:
                await update.message.reply_text("❌ Trading system not available")
                return
            
            # Check if system is shutting down
            if hasattr(self.trading_system, 'is_shutting_down') and self.trading_system.is_shutting_down:
                await update.message.reply_text("🔄 System is shutting down, command not available")
                return
            
            await self.trading_system.stop_trading()
            await update.message.reply_text("🛑 Trading operations stopped")
            
        except asyncio.CancelledError:
            logger.info("Stop trading command cancelled due to system shutdown")
            return
        except Exception as e:
            logger.error(f"Error handling stop trading command: {e}")
            try:
                await update.message.reply_text("❌ Error stopping trading operations")
            except Exception as reply_error:
                logger.debug(f"Could not send error reply: {reply_error}")
    
    async def _handle_emergency_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /emergency_stop command."""
        if not self._is_authorized(update):
            await update.message.reply_text("❌ Unauthorized access")
            return
        
        try:
            if not self.trading_system:
                await update.message.reply_text("❌ Trading system not available")
                return
            
            # Emergency stop should work even during shutdown
            await self.trading_system.emergency_stop()
            await update.message.reply_text("🚨 EMERGENCY STOP ACTIVATED - All operations halted")
            
        except asyncio.CancelledError:
            logger.info("Emergency stop command cancelled due to system shutdown")
            return
        except Exception as e:
            logger.error(f"Error handling emergency stop command: {e}")
            try:
                await update.message.reply_text("❌ Error executing emergency stop")
            except Exception as reply_error:
                logger.debug(f"Could not send error reply: {reply_error}")
    
    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle non-command messages."""
        if not self._is_authorized(update):
            await update.message.reply_text("❌ Unauthorized access")
            return
        
        message_text = update.message.text.lower()
        
        # Simple keyword responses
        if any(word in message_text for word in ['hello', 'hi', 'hey']):
            await update.message.reply_text("👋 Hello! Use /help to see available commands.")
        elif any(word in message_text for word in ['status', 'how']):
            await self._handle_status(update, context)
        elif any(word in message_text for word in ['portfolio', 'positions']):
            await self._handle_portfolio(update, context)
        elif any(word in message_text for word in ['help', 'commands']):
            await self._handle_help(update, context)
        else:
            await update.message.reply_text("🤔 I didn't understand that. Use /help to see available commands.")
    
    # Extended message capabilities for trading notifications
    
    async def send_order_notification(self, order: Order, event_type: str) -> bool:
        """Send order notification message."""
        try:
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

📊 **Symbol**: {order.symbol}
📈 **Side**: {order.side.value.upper()}
📦 **Quantity**: {order.quantity}
💰 **Type**: {order.order_type.value.upper()}
"""
            
            if order.price:
                message += f"💵 **Price**: ${float(order.price):,.2f}\n"
            
            if order.filled_quantity and order.filled_quantity > 0:
                message += f"✅ **Filled**: {order.filled_quantity}\n"
            
            if order.filled_price:
                message += f"💲 **Fill Price**: ${float(order.filled_price):,.2f}\n"
            
            if order.id:
                message += f"🔢 **Order ID**: {order.id}\n"
            
            return await self.send_message(message)
            
        except Exception as e:
            logger.error(f"Error sending order notification: {e}")
            return False
    
    async def send_portfolio_update(self, portfolio: Portfolio) -> bool:
        """Send portfolio update message."""
        try:
            day_pnl_pct = (float(portfolio.day_pnl) / float(portfolio.equity)) * 100
            pnl_emoji = "📈" if portfolio.day_pnl > 0 else "📉" if portfolio.day_pnl < 0 else "➡️"
            
            message = f"""
💼 **Portfolio Update**

💰 **Total Equity**: ${float(portfolio.equity):,.2f}
{pnl_emoji} **Day P&L**: ${float(portfolio.day_pnl):,.2f} ({day_pnl_pct:.2f}%)
📊 **Market Value**: ${float(portfolio.market_value):,.2f}
💵 **Cash**: ${float(portfolio.cash):,.2f}
📈 **Total P&L**: ${float(portfolio.total_pnl):,.2f}

📦 **Positions**: {len(portfolio.positions)}
            """
            
            return await self.send_message(message)
            
        except Exception as e:
            logger.error(f"Error sending portfolio update: {e}")
            return False
    
    async def send_system_alert(self, message: str, alert_type: str = "info") -> bool:
        """Send system alert message."""
        try:
            emoji_map = {
                'info': 'ℹ️',
                'warning': '⚠️',
                'error': '🚨',
                'success': '✅'
            }
            
            emoji = emoji_map.get(alert_type, 'ℹ️')
            title = alert_type.upper()
            
            alert_message = f"""
{emoji} **{title}**

{message}

📅 **Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """
            
            return await self.send_message(alert_message)
            
        except Exception as e:
            logger.error(f"Error sending system alert: {e}")
            return False
    
    async def send_startup_message(self) -> bool:
        """Send startup notification with available commands."""
        try:
            startup_message = """🚀 *LLM Trading Agent Started*

System is now running and ready for trading operations!

🤖 *Available Commands:*
"""
            
            # Add command list
            for command, description in self.commands.items():
                startup_message += f"/{command} - {description}\n"
            
            startup_message += """
📊 *Quick Start:*
• /status - Check system status
• /portfolio - View current holdings
• /analyze - Run AI analysis
• /help - Show detailed help

⚠️ *Important:* Set up your API keys and configure the system before trading!

💡 *Tip:* Use /analyze to manually trigger AI trading analysis based on current market conditions.
"""
            
            return await self.send_message(startup_message)
            
        except Exception as e:
            logger.error(f"Error sending startup message: {e}")
            return False 