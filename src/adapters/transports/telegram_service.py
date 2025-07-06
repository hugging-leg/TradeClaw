"""
Telegram Service - Message transport implementation.

This service handles message transmission and bot command processing
for Telegram integration with the trading system.
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, List, ClassVar
from decimal import Decimal
from datetime import datetime
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import TelegramError, Conflict, NetworkError, TimedOut

from src.interfaces.message_transport import MessageTransport, MessageFormat
from src.models.trading_models import Order, Portfolio, Position
from src.utils.telegram_utils import (
    fix_markdown_issues,
    clean_content_for_telegram,
    extract_byte_offset_from_error,
    get_problematic_content_area,
    escape_markdown_symbols
)
from src.utils.message_formatters import (
    format_order_message,
    format_portfolio_message,
    format_alert_message
)
from config import settings

logger = logging.getLogger(__name__)


class TelegramService(MessageTransport):
    """
    Telegram message transport with bot command handling.
    
    This service provides:
    - Message transmission capabilities (implementing MessageTransport)
    - Interactive command processing (/help, /status, etc.)
    - Rate limiting and connection management
    - User authorization
    - Conflict resolution for multiple instances
    """
    
    # Class variable to track active instances
    _active_instances: ClassVar[Dict[str, 'TelegramService']] = {}
    _instance_lock: ClassVar[asyncio.Lock] = asyncio.Lock()
    
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
        self.instance_id = f"{self.bot_token}_{self.chat_id}"
        
        self.bot = None
        self.application = None
        self.is_running = False
        self.is_initializing = False
        self.last_message_time = 0
        self.rate_limit_delay = 1.0  # seconds
        self.max_retries = 3
        self.retry_delay = 5.0  # seconds
        
        # Statistics
        self.message_stats = {
            'sent_count': 0,
            'error_count': 0,
            'last_sent': None,
            'last_error': None
        }
        
        # Command descriptions
        self.commands = {
            'start': 'Start the trading system',
            'stop': 'Stop the trading system',
            'help': 'Show available commands',
            'status': 'Get trading system status',
            'portfolio': 'Get current portfolio summary',
            'orders': 'Get active orders',
            'positions': 'Get current positions',
            'analyze': 'Manually trigger AI trading analysis',
            'emergency': 'Emergency stop all operations'
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
        
        # Check for existing instance
        async with self._instance_lock:
            if self.instance_id in self._active_instances:
                existing_instance = self._active_instances[self.instance_id]
                if existing_instance.is_running:
                    logger.info("Reusing existing Telegram service instance")
                    # Copy the existing bot and application
                    self.bot = existing_instance.bot
                    self.application = existing_instance.application
                    self.is_running = True
                    return True
                else:
                    # Remove the inactive instance
                    del self._active_instances[self.instance_id]
        
        self.is_initializing = True
        
        try:
            if not self.bot_token or self.bot_token == "test_token":
                logger.info("Telegram bot token not configured or is test token - running in mock mode")
                self.is_initializing = False
                return False  # Return False but don't treat as error
            
            if not self.chat_id or self.chat_id == "test_chat_id":
                logger.info("Telegram chat ID not configured or is test - running in mock mode")
                self.is_initializing = False
                return False  # Return False but don't treat as error
            
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
                        # Try to clear any existing instances
                        await self._clear_conflicts()
                        await asyncio.sleep(self.retry_delay)
                    else:
                        logger.warning("Failed to resolve Telegram bot conflict after multiple retries")
                        logger.warning("System will continue in mock mode without Telegram notifications")
                        return False
                        
                except (NetworkError, TimedOut) as e:
                    retry_count += 1
                    logger.warning(f"Network error connecting to Telegram (attempt {retry_count}/{self.max_retries}): {e}")
                    
                    if retry_count < self.max_retries:
                        await asyncio.sleep(self.retry_delay)
                    else:
                        logger.warning("Failed to connect to Telegram after multiple retries")
                        logger.warning("System will continue in mock mode without Telegram notifications")
                        return False
                        
                except Exception as e:
                    logger.warning(f"Unexpected error initializing Telegram service: {e}")
                    logger.warning("System will continue in mock mode without Telegram notifications")
                    return False
            
            # Register this instance
            async with self._instance_lock:
                self._active_instances[self.instance_id] = self
            
            logger.info("Telegram service initialized successfully")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to initialize Telegram service: {e}")
            logger.warning("System will continue in mock mode without Telegram notifications")
            return False
        finally:
            self.is_initializing = False
    
    async def _clear_conflicts(self):
        """Clear potential conflicts with existing bot instances."""
        try:
            # Try to delete webhook first
            await self.bot.delete_webhook()
            logger.info("Cleared existing webhook")
            
            # Close any existing sessions
            if hasattr(self.bot, '_request') and hasattr(self.bot._request, '_client'):
                await self.bot._request._client.aclose()
                
        except Exception as e:
            logger.debug(f"Error clearing conflicts: {e}")
    
    async def start(self) -> bool:
        """
        Start the Telegram service with conflict resolution.
        
        Returns:
            True if start successful, False otherwise
        """
        try:
            if self.is_running:
                logger.info("Telegram service is already running")
                return True
            
            if not self.application:
                if not await self.initialize():
                    logger.info("Telegram service not initialized - running in mock mode")
                    return False
            
            # Check if another instance is already running the same bot
            async with self._instance_lock:
                for instance_id, instance in self._active_instances.items():
                    if instance != self and instance.is_running and instance.bot_token == self.bot_token:
                        logger.warning("Another instance of the same bot is already running")
                        # Don't start another instance, but mark this as successful
                        self.is_running = True
                        return True
            
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
                        # Try to clear conflicts and restart
                        await self._clear_conflicts()
                        await asyncio.sleep(self.retry_delay)
                        
                        try:
                            if self.application:
                                await self.application.stop()
                                await self.application.shutdown()
                        except Exception as stop_error:
                            logger.debug(f"Error stopping application during retry: {stop_error}")
                    else:
                        logger.warning("Failed to resolve Telegram service conflict after multiple retries")
                        logger.warning("System will continue in mock mode without Telegram notifications")
                        return False
                        
                except Exception as e:
                    logger.warning(f"Error starting Telegram service: {e}")
                    logger.warning("System will continue in mock mode without Telegram notifications")
                    return False
            
            return False
            
        except Exception as e:
            logger.warning(f"Failed to start Telegram service: {e}")
            logger.warning("System will continue in mock mode without Telegram notifications")
            return False
    
    async def stop(self) -> bool:
        """
        Stop the Telegram service.
        
        Returns:
            True if stop successful, False otherwise
        """
        try:
            if not self.is_running:
                logger.info("Telegram service is not running")
                return True
            
            self.is_running = False
            
            # Remove from active instances
            async with self._instance_lock:
                if self.instance_id in self._active_instances:
                    del self._active_instances[self.instance_id]
            
            if self.application:
                try:
                    # Check if updater is actually running before stopping
                    if hasattr(self.application, 'updater') and self.application.updater.running:
                        await self.application.updater.stop()
                    
                    if hasattr(self.application, '_running') and self.application._running:
                        await self.application.stop()
                        await self.application.shutdown()
                        
                    logger.info("Telegram service stopped successfully")
                except Exception as e:
                    # Don't treat stop errors as critical since we're shutting down
                    logger.debug(f"Non-critical error stopping Telegram service: {e}")
            
            return True
            
        except Exception as e:
            logger.debug(f"Error stopping Telegram service: {e}")
            return False
    
    async def _handle_polling_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle polling errors."""
        error = context.error
        
        if isinstance(error, Conflict):
            logger.warning("Telegram polling conflict detected - will attempt auto-recovery")
            # Don't crash on conflicts, just log them
        elif isinstance(error, (NetworkError, TimedOut)):
            logger.debug("Network/timeout error in Telegram polling - will retry automatically")
        else:
            logger.warning(f"Telegram polling error: {error}")
    
    # MessageTransport Interface Implementation
    
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
                logger.debug("Telegram bot not initialized - running in mock mode")
                self.message_stats['error_count'] += 1
                return False
            
            # Rate limiting
            await self._rate_limit()
            
            target_chat_id = kwargs.get('chat_id') or self.chat_id
            if not target_chat_id or target_chat_id == "test_chat_id":
                logger.debug("No valid chat ID configured - running in mock mode")
                self.message_stats['error_count'] += 1
                return False
            
            # Convert format type to Telegram parse mode
            parse_mode_map = {
                MessageFormat.PLAIN_TEXT: None,
                MessageFormat.MARKDOWN: "Markdown",  # Use standard Markdown which supports *bold*
                MessageFormat.HTML: "HTML",
                MessageFormat.JSON: None  # Send as plain text
            }
            
            parse_mode = parse_mode_map.get(format_type)
            
            # First attempt - try with specified format
            try:
                await self.bot.send_message(
                    chat_id=target_chat_id,
                    text=content,
                    parse_mode=parse_mode
                )
                
                self.message_stats['sent_count'] += 1
                self.message_stats['last_sent'] = datetime.now()
                logger.debug(f"Message sent successfully to Telegram chat {target_chat_id}")
                return True
                
            except TelegramError as e:
                error_message = str(e)
                
                # Handle Markdown parsing errors
                if "Can't parse entities" in error_message and parse_mode == "Markdown":
                    # Extract more detailed error information
                    byte_offset = extract_byte_offset_from_error(error_message)
                    
                    # Log detailed error information for debugging
                    logger.warning(f"Markdown parsing failed at byte offset {byte_offset}: {e}")
                    if byte_offset is not None and byte_offset < len(content):
                        # Show problematic area
                        problematic_area = get_problematic_content_area(content, byte_offset)
                        logger.debug(f"Problematic content area: {problematic_area}")
                    
                    # Try intelligent markdown cleanup first
                    try:
                        cleaned_markdown = fix_markdown_issues(content)
                        if cleaned_markdown != content:
                            logger.info("Attempting with markdown fixes applied")
                            await self.bot.send_message(
                                chat_id=target_chat_id,
                                text=cleaned_markdown,
                                parse_mode="Markdown"
                            )
                            self.message_stats['sent_count'] += 1
                            self.message_stats['last_sent'] = datetime.now()
                            logger.info("Message sent successfully with markdown fixes")
                            return True
                    except Exception as fix_error:
                        logger.debug(f"Markdown fix attempt failed: {fix_error}")
                    
                    # Second attempt - try as plain text
                    try:
                        logger.info("Retrying as plain text")
                        await self.bot.send_message(
                            chat_id=target_chat_id,
                            text=content,
                            parse_mode=None
                        )
                        self.message_stats['sent_count'] += 1
                        self.message_stats['last_sent'] = datetime.now()
                        logger.info("Message sent successfully as plain text")
                        return True
                        
                    except Exception as retry_error:
                        logger.warning(f"Failed to send message even as plain text: {retry_error}")
                        
                        # Third attempt - try with cleaned content
                        try:
                            logger.info("Trying with cleaned content")
                            cleaned_content = clean_content_for_telegram(content)
                            await self.bot.send_message(
                                chat_id=target_chat_id,
                                text=cleaned_content,
                                parse_mode=None
                            )
                            self.message_stats['sent_count'] += 1
                            self.message_stats['last_sent'] = datetime.now()
                            logger.info("Message sent successfully with cleaned content")
                            return True
                            
                        except Exception as final_error:
                            logger.error(f"Failed to send message after all attempts: {final_error}")
                            self.message_stats['error_count'] += 1
                            self.message_stats['last_error'] = datetime.now()
                            return False
                
                # Handle other Telegram errors
                elif "Message is too long" in error_message:
                    logger.warning(f"Message too long, trying to truncate: {e}")
                    
                    # Try to truncate the message
                    try:
                        truncated_content = content[:4000] + "\n\n... (message truncated)"
                        await self.bot.send_message(
                            chat_id=target_chat_id,
                            text=truncated_content,
                            parse_mode=None
                        )
                        self.message_stats['sent_count'] += 1
                        self.message_stats['last_sent'] = datetime.now()
                        logger.debug(f"Truncated message sent to Telegram chat {target_chat_id}")
                        return True
                        
                    except Exception as truncate_error:
                        logger.error(f"Failed to send truncated message: {truncate_error}")
                        self.message_stats['error_count'] += 1
                        self.message_stats['last_error'] = datetime.now()
                        return False
                
                # Handle rate limiting
                elif "Too Many Requests" in error_message or "retry after" in error_message.lower():
                    logger.warning(f"Rate limited by Telegram: {e}")
                    self.message_stats['error_count'] += 1
                    self.message_stats['last_error'] = datetime.now()
                    return False
                
                # Handle other errors
                else:
                    logger.debug(f"Telegram API error: {e}")
                    self.message_stats['error_count'] += 1
                    self.message_stats['last_error'] = datetime.now()
                    return False
            
        except Exception as e:
            logger.debug(f"Error sending Telegram message: {e}")
            self.message_stats['error_count'] += 1
            self.message_stats['last_error'] = datetime.now()
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
            "description": "Telegram message transport with bot command handling",
            "status": {
                "initialized": bool(self.bot),
                "running": self.is_running,
                "bot_configured": bool(self.bot_token),
                "chat_configured": bool(self.chat_id),
                "trading_system_connected": self.trading_system is not None,
                "instance_id": self.instance_id
            },
            "commands": self.commands,
            "rate_limit_delay": self.rate_limit_delay,
            "message_stats": self.message_stats
        }
    
    # Bot command handling
    
    def _register_handlers(self):
        """Register command and message handlers."""
        
        # Command handlers
        self.application.add_handler(CommandHandler("start", self._handle_start))
        self.application.add_handler(CommandHandler("stop", self._handle_stop))
        self.application.add_handler(CommandHandler("help", self._handle_help))
        self.application.add_handler(CommandHandler("status", self._handle_status))
        self.application.add_handler(CommandHandler("portfolio", self._handle_portfolio))
        self.application.add_handler(CommandHandler("orders", self._handle_orders))
        self.application.add_handler(CommandHandler("positions", self._handle_positions))
        self.application.add_handler(CommandHandler("analyze", self._handle_analyze))
        self.application.add_handler(CommandHandler("emergency", self._handle_emergency))
        
        # Callback query handler for button interactions
        self.application.add_handler(CallbackQueryHandler(self._handle_callback_query))
        
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
        current_time = time.time()
        time_since_last = current_time - self.last_message_time
        
        if time_since_last < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - time_since_last)
        
        self.last_message_time = time.time()
    
    def _create_main_menu_keyboard(self) -> InlineKeyboardMarkup:
        """Create main menu keyboard with quick action buttons."""
        keyboard = [
            [
                InlineKeyboardButton("📊 Status", callback_data="status"),
                InlineKeyboardButton("💼 Portfolio", callback_data="portfolio")
            ],
            [
                InlineKeyboardButton("📈 Orders", callback_data="orders"),
                InlineKeyboardButton("🎯 Positions", callback_data="positions")
            ],
            [
                InlineKeyboardButton("🤖 Analyze", callback_data="analyze"),
                InlineKeyboardButton("❓ Help", callback_data="help")
            ],
            [
                InlineKeyboardButton("🚨 Emergency Stop", callback_data="emergency")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    def _create_refresh_keyboard(self, command: str) -> InlineKeyboardMarkup:
        """Create a refresh button for updates."""
        keyboard = [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{command}"),
                InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    def _create_confirmation_keyboard(self, action: str) -> InlineKeyboardMarkup:
        """Create confirmation buttons for important actions."""
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_{action}"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    async def _handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callback queries."""
        query = update.callback_query
        
        # Answer the callback query to stop the loading animation
        await query.answer()
        
        if not self._is_authorized(update):
            await query.edit_message_text("❌ Unauthorized access")
            return
        
        try:
            callback_data = query.data
            
            # Handle different callback actions
            if callback_data == "status":
                await self._handle_status_callback(query, context)
            elif callback_data == "portfolio":
                await self._handle_portfolio_callback(query, context)
            elif callback_data == "orders":
                await self._handle_orders_callback(query, context)
            elif callback_data == "positions":
                await self._handle_positions_callback(query, context)
            elif callback_data == "analyze":
                await self._handle_analyze_callback(query, context)
            elif callback_data == "help":
                await self._handle_help_callback(query, context)
            elif callback_data == "emergency":
                await self._handle_emergency_callback(query, context)
            elif callback_data == "main_menu":
                await self._handle_main_menu_callback(query, context)
            elif callback_data.startswith("refresh_"):
                command = callback_data.replace("refresh_", "")
                await self._handle_refresh_callback(query, context, command)
            elif callback_data.startswith("confirm_"):
                action = callback_data.replace("confirm_", "")
                await self._handle_confirm_callback(query, context, action)
            elif callback_data == "cancel":
                await query.edit_message_text("❌ **Action Cancelled**")
            else:
                await query.edit_message_text("❓ Unknown action")
                
        except Exception as e:
            logger.error(f"Error handling callback query: {e}")
            try:
                await query.edit_message_text("❌ Error processing button action")
            except Exception as edit_error:
                logger.debug(f"Could not edit message after callback error: {edit_error}")
    
    # Command handlers
    
    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command - start the trading system."""
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
            
            # Check if system is already running
            if self.trading_system.is_running:
                success = await self.send_message("ℹ️ **Trading System Already Running**\n\nThe system is currently active and operational.", update.effective_chat.id)
                if success:
                    # Show current status
                    await self._handle_status(update, context)
                else:
                    await update.message.reply_text("ℹ️ Trading System Already Running - The system is currently active and operational.")
                return
            
            # System is not running, start it
            success = await self.send_message("🚀 **Starting Trading System**\n\nInitializing...", update.effective_chat.id)
            if not success:
                await update.message.reply_text("🚀 Starting Trading System - Initializing...")
            
            # Start the trading system
            result = await self.trading_system.start()
            
            if result:
                # Send current status after starting
                await self._handle_status(update, context)
            else:
                await update.message.reply_text("❌ Failed to start trading system")
            
        except Exception as e:
            logger.error(f"Error handling start command: {e}")
            try:
                await update.message.reply_text("❌ Error starting trading system")
            except Exception as reply_error:
                logger.debug(f"Could not send error reply: {reply_error}")
    
    async def _handle_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stop command - stop the trading system."""
        if not self._is_authorized(update):
            await update.message.reply_text("❌ Unauthorized access")
            return
        
        try:
            if not self.trading_system:
                await update.message.reply_text("❌ Trading system not available")
                return
            
            # Send stopping message with proper markdown
            success = await self.send_message("⏹️ **Stopping Trading System**\n\nShutting down...", update.effective_chat.id)
            if not success:
                await update.message.reply_text("⏹️ Stopping Trading System - Shutting down...")
            
            # Stop the trading system
            await self.trading_system.stop()
            
            # Send success message with proper markdown
            success = await self.send_message("✅ **Trading System Stopped**\n\nSystem has been shut down successfully.", update.effective_chat.id)
            if not success:
                await update.message.reply_text("✅ Trading System Stopped - System has been shut down successfully.")
            
        except Exception as e:
            logger.error(f"Error handling stop command: {e}")
            try:
                await update.message.reply_text("❌ Error stopping trading system")
            except Exception as reply_error:
                logger.debug(f"Could not send error reply: {reply_error}")
    
    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        if not self._is_authorized(update):
            await update.message.reply_text("❌ Unauthorized access")
            return
        
        help_text = "🤖 **Available Commands:**\n\n"
        for command, description in self.commands.items():
            help_text += f"/{command} - {description}\n"
        
        help_text += "\n💡 **Tip:** Use the buttons below for quick access!"
        
        # Send help message with interactive buttons
        await update.message.reply_text(
            help_text.strip(),
            reply_markup=self._create_main_menu_keyboard(),
            parse_mode='Markdown'
        )
    
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
            
            # Check if there's an error in the status
            if "error" in status:
                await update.message.reply_text(f"❌ Error getting system status: {status['error']}")
                return
            
            # Get portfolio data if available
            portfolio = None
            try:
                portfolio = await self.trading_system.get_portfolio()
            except Exception as e:
                logger.warning(f"Could not get portfolio for status: {e}")
            
            # Build status text with correct keys
            status_text = f"""
📊 *Trading System Status*

🏃 *Running*: {("✅ Yes" if status.get('status') == 'running' else "❌ No")}
💰 *Trading Enabled*: {("✅ Yes" if status.get('trading_enabled', False) else "❌ No")}
🏪 *Market Open*: {("✅ Yes" if status.get('market_open', False) else "❌ No")}"""
            
            # Add scheduler status
            scheduler_info = status.get('scheduler', {})
            if scheduler_info:
                status_text += f"""
📅 *Scheduler*: {("✅ Running" if scheduler_info.get('actually_running', False) else "❌ Stopped")}
📋 *Scheduled Jobs*: {scheduler_info.get('total_jobs', 0)}"""
            
            status_text += """

📈 *Portfolio Summary*:"""
            
            if portfolio:
                status_text += f"""
• Total Equity: ${float(portfolio.equity):,.2f}
• Cash: ${float(portfolio.cash):,.2f}
• Day P&L: ${float(portfolio.day_pnl):,.2f}
• Positions: {len(portfolio.positions)}"""
            else:
                # Use status data if available
                status_text += f"""
• Total Equity: ${float(status.get('equity', 0)):,.2f}
• Day P&L: ${float(status.get('day_pnl', 0)):,.2f}
• Active Orders: {status.get('active_orders', 0)}
• Positions: {status.get('positions', 0)}"""
            
            status_text += f"""

🕒 *Last Update*: {status.get('last_update', 'N/A')}
            """
            
            # Send status message with refresh button
            await update.message.reply_text(
                status_text.strip(),
                reply_markup=self._create_refresh_keyboard("status"),
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error getting system status: {e}")
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
            
            if not portfolio:
                await update.message.reply_text("❌ Unable to retrieve portfolio")
                return
            
            portfolio_text = f"""
💼 *Portfolio Details*

💰 *Total Equity*: ${float(portfolio.equity):,.2f}
💵 *Cash*: ${float(portfolio.cash):,.2f}
📊 *Market Value*: ${float(portfolio.market_value):,.2f}
📈 *Day P&L*: ${float(portfolio.day_pnl):,.2f}
📊 *Total P&L*: ${float(portfolio.total_pnl):,.2f}

💪 *Buying Power*: ${float(portfolio.buying_power):,.2f}
📦 *Positions*: {len(portfolio.positions)}
            """
            
            if portfolio.positions:
                portfolio_text += "\n\n📋 *Current Positions:*\n"
                for position in portfolio.positions[:5]:  # Show first 5 positions
                    # Escape underscores in symbol names to prevent markdown parsing issues
                    safe_symbol = escape_markdown_symbols(str(position.symbol), "_")
                    portfolio_text += f"• {safe_symbol}: {position.quantity} shares\n"
                
                if len(portfolio.positions) > 5:
                    portfolio_text += f"• ... and {len(portfolio.positions) - 5} more positions\n"
            
            # Send portfolio message with refresh button
            await update.message.reply_text(
                portfolio_text.strip(),
                reply_markup=self._create_refresh_keyboard("portfolio"),
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error getting portfolio: {e}")
            await update.message.reply_text("❌ Error retrieving portfolio")
    
    async def _handle_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /orders command."""
        if not self._is_authorized(update):
            await update.message.reply_text("❌ Unauthorized access")
            return
        
        try:
            if not self.trading_system:
                await update.message.reply_text("❌ Trading system not available")
                return
            
            await update.message.reply_text("📋 Retrieving active orders...")
            
            orders = await self.trading_system.get_active_orders()
            
            if not orders:
                await update.message.reply_text("ℹ️ No active orders found")
                return
            
            orders_text = f"📋 *Active Orders* ({len(orders)}):\n\n"
            
            for order in orders:
                # Escape underscores in symbol names to prevent markdown parsing issues
                safe_symbol = escape_markdown_symbols(str(order.symbol), "_")
                orders_text += f"• {safe_symbol} - {order.side.value} {order.quantity} @ {order.order_type.value}\n"
            
            # Send orders message with refresh button
            await update.message.reply_text(
                orders_text.strip(),
                reply_markup=self._create_refresh_keyboard("orders"),
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error getting orders: {e}")
            await update.message.reply_text("❌ Error retrieving orders")
    
    async def _handle_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /positions command."""
        await update.message.reply_text(
            "📊 **Position Information**\n\nUse the Portfolio button below for detailed position information.",
            reply_markup=self._create_main_menu_keyboard(),
            parse_mode='Markdown'
        )
    
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
            
            # Send immediate confirmation with proper formatting
            await self.send_message("🤖 **AI Analysis Started**\n\nRunning intelligent trading analysis...\n\nWatch for detailed step-by-step updates below!", update.effective_chat.id)
            
            # Trigger manual analysis with cancellation handling
            try:
                result = await self.trading_system.run_manual_analysis()
                
                # Handle different result types
                if isinstance(result, dict):
                    if result.get("success"):
                        await self.send_message("✅ **Analysis Complete**\n\nAI analysis has been completed successfully!", update.effective_chat.id)
                    else:
                        message = result.get("message", "Analysis failed")
                        if "cancelled" in message.lower() or "shutting down" in message.lower():
                            await self.send_message("🔄 **Analysis Cancelled**\n\nSystem is shutting down. Please try again after restart.", update.effective_chat.id)
                        else:
                            await self.send_message(f"❌ **Analysis Failed**\n\n{message}", update.effective_chat.id)
                else:
                    # Fallback for unexpected result types
                    await self.send_message("✅ **Analysis Complete**\n\nAI analysis has been completed successfully!", update.effective_chat.id)
                    
            except asyncio.CancelledError:
                logger.info("Analysis command cancelled due to system shutdown")
                try:
                    await self.send_message("🔄 **Analysis Cancelled**\n\nSystem is shutting down. Please try again after restart.", update.effective_chat.id)
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
    
    async def _handle_emergency(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /emergency command."""
        if not self._is_authorized(update):
            await update.message.reply_text("❌ Unauthorized access")
            return
        
        try:
            if not self.trading_system:
                await update.message.reply_text("❌ Trading system not available")
                return
            
            await self.send_message("🚨 **EMERGENCY STOP INITIATED**\n\nStopping all trading operations immediately...", update.effective_chat.id)
            
            await self.trading_system.emergency_stop()
            await self.send_message("⛔ **EMERGENCY STOP COMPLETE**\n\nAll trading operations have been stopped.", update.effective_chat.id)
            
        except asyncio.CancelledError:
            logger.info("Emergency command cancelled due to system shutdown")
            return
        except Exception as e:
            logger.error(f"Error handling emergency command: {e}")
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
        
        if 'help' in message_text:
            await self._handle_help(update, context)
        elif 'status' in message_text:
            await self._handle_status(update, context)
        elif 'portfolio' in message_text:
            await self._handle_portfolio(update, context)
        elif 'analyze' in message_text or 'analysis' in message_text:
            await self._handle_analyze(update, context)
        else:
            await update.message.reply_text("🤖 I don't understand that command. Use /help to see available commands.")
    
    async def send_startup_message(self) -> bool:
        """Send startup notification with all available commands."""
        try:
            # Build the commands list from the commands dictionary
            commands_list = "\n".join([f"/{cmd} - {desc}" for cmd, desc in self.commands.items()])
            
            startup_message = f"""🚀 **LLM Trading Agent Started**

System is now running and ready for trading operations!

🤖 **Available Commands:**
{commands_list}

📊 **Quick Start:**
• Use /help to see detailed command information
• Use /status to check system status
• Use /analyze to run AI analysis

Ready to trade! 📊"""
            
            return await self.send_message(startup_message)
            
        except Exception as e:
            logger.error(f"Error sending startup message: {e}")
            return False
    
    async def send_system_started_notification(self) -> bool:
        """Send system started notification - this is called directly by trading system."""
        try:
            # Send system online message with all available commands
            startup_message = f"""🚀 **LLM Agent Trading System**

All components initialized successfully. Ready for trading operations!

🤖 **Available Commands:**
"""
            # Add all commands with descriptions
            for cmd, desc in self.commands.items():
                startup_message += f"/{cmd} - {desc}\n"
            
            startup_message += """
Ready to trade! Use /help for detailed information."""
            
            return await self.send_message(startup_message)
            
        except Exception as e:
            logger.error(f"Error sending system started notification: {e}")
            return False
    
    @classmethod
    async def cleanup_all_instances(cls):
        """Clean up all active instances."""
        async with cls._instance_lock:
            for instance in list(cls._active_instances.values()):
                try:
                    await instance.stop()
                except Exception as e:
                    logger.debug(f"Error stopping instance: {e}")
            cls._active_instances.clear()
    
    # High-level message sending methods for compatibility
    
    async def send_order_notification(self, order, event_type: str) -> bool:
        """
        Send order notification message.
        
        Args:
            order: Order object
            event_type: Type of event (created, filled, canceled, etc.)
            
        Returns:
            True if message sent successfully, False otherwise
        """
        try:
            formatted_message = format_order_message(order, event_type)
            return await self.send_message(formatted_message)
        except Exception as e:
            logger.error(f"Error sending order notification: {e}")
            return False
    
    async def send_portfolio_update(self, portfolio) -> bool:
        """
        Send portfolio update message.
        
        Args:
            portfolio: Portfolio object
            
        Returns:
            True if message sent successfully, False otherwise
        """
        try:
            formatted_message = format_portfolio_message(portfolio)
            return await self.send_message(formatted_message)
        except Exception as e:
            logger.error(f"Error sending portfolio update: {e}")
            return False
    
    async def send_system_alert(self, message: str, alert_type: str = "info") -> bool:
        """
        Send system alert message.
        
        Args:
            message: Alert message
            alert_type: Type of alert (info, warning, error, success)
            
        Returns:
            True if message sent successfully, False otherwise
        """
        try:
            formatted_message = format_alert_message(message, alert_type)
            return await self.send_message(formatted_message)
        except Exception as e:
            logger.error(f"Error sending system alert: {e}")
            return False

    # Callback handler functions for button interactions
    
    async def _handle_main_menu_callback(self, query, context):
        """Handle main menu button callback."""
        await query.edit_message_text(
            "🤖 **Trading System Menu**\n\nSelect an action:",
            reply_markup=self._create_main_menu_keyboard(),
            parse_mode='Markdown'
        )
    
    async def _handle_status_callback(self, query, context):
        """Handle status button callback."""
        if not self.trading_system:
            await query.edit_message_text(
                "❌ **Trading System Not Available**",
                reply_markup=self._create_refresh_keyboard("status"),
                parse_mode='Markdown'
            )
            return
        
        try:
            # Get system status
            is_running = self.trading_system.is_running
            is_trading_enabled = getattr(self.trading_system, 'is_trading_enabled', False)
            
            status_message = f"""📊 **Trading System Status**

🔄 **System**: {'🟢 Running' if is_running else '🔴 Stopped'}
💰 **Trading**: {'🟢 Enabled' if is_trading_enabled else '🔴 Disabled'}
⏰ **Last Update**: {datetime.now().strftime('%H:%M:%S')}"""
            
            await query.edit_message_text(
                status_message,
                reply_markup=self._create_refresh_keyboard("status"),
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error getting status via callback: {e}")
            await query.edit_message_text(
                "❌ **Error Getting Status**",
                reply_markup=self._create_refresh_keyboard("status"),
                parse_mode='Markdown'
            )
    
    async def _handle_portfolio_callback(self, query, context):
        """Handle portfolio button callback."""
        if not self.trading_system:
            await query.edit_message_text(
                "❌ **Trading System Not Available**",
                reply_markup=self._create_refresh_keyboard("portfolio"),
                parse_mode='Markdown'
            )
            return
        
        try:
            portfolio = await self.trading_system.get_portfolio()
            if portfolio:
                formatted_message = format_portfolio_message(portfolio)
                await query.edit_message_text(
                    formatted_message,
                    reply_markup=self._create_refresh_keyboard("portfolio"),
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text(
                    "❌ **Portfolio Not Available**",
                    reply_markup=self._create_refresh_keyboard("portfolio"),
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"Error getting portfolio via callback: {e}")
            await query.edit_message_text(
                "❌ **Error Getting Portfolio**",
                reply_markup=self._create_refresh_keyboard("portfolio"),
                parse_mode='Markdown'
            )
    
    async def _handle_orders_callback(self, query, context):
        """Handle orders button callback."""
        if not self.trading_system:
            await query.edit_message_text(
                "❌ **Trading System Not Available**",
                reply_markup=self._create_refresh_keyboard("orders"),
                parse_mode='Markdown'
            )
            return
        
        try:
            orders = await self.trading_system.get_active_orders()
            if orders:
                message = "📈 **Active Orders:**\n\n"
                for order in orders[:5]:  # Limit to 5 orders to avoid message too long
                    message += f"• {order.symbol}: {order.side.value} {order.quantity} @ {order.order_type.value}\n"
                if len(orders) > 5:
                    message += f"\n... and {len(orders) - 5} more orders"
            else:
                message = "📈 **Active Orders:**\n\nNo active orders found."
            
            await query.edit_message_text(
                message,
                reply_markup=self._create_refresh_keyboard("orders"),
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error getting orders via callback: {e}")
            await query.edit_message_text(
                "❌ **Error Getting Orders**",
                reply_markup=self._create_refresh_keyboard("orders"),
                parse_mode='Markdown'
            )
    
    async def _handle_positions_callback(self, query, context):
        """Handle positions button callback."""
        if not self.trading_system:
            await query.edit_message_text(
                "❌ **Trading System Not Available**",
                reply_markup=self._create_refresh_keyboard("positions"),
                parse_mode='Markdown'
            )
            return
        
        try:
            portfolio = await self.trading_system.get_portfolio()
            if portfolio and portfolio.positions:
                message = "🎯 **Current Positions:**\n\n"
                for position in portfolio.positions[:5]:  # Limit to 5 positions
                    pnl_emoji = "📈" if position.unrealized_pnl >= 0 else "📉"
                    message += f"{pnl_emoji} {position.symbol}: {position.quantity} shares\n"
                    message += f"   P&L: ${position.unrealized_pnl:.2f} ({position.unrealized_pnl_percentage:.2%})\n\n"
                if len(portfolio.positions) > 5:
                    message += f"... and {len(portfolio.positions) - 5} more positions"
            else:
                message = "🎯 **Current Positions:**\n\nNo open positions found."
            
            await query.edit_message_text(
                message,
                reply_markup=self._create_refresh_keyboard("positions"),
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error getting positions via callback: {e}")
            await query.edit_message_text(
                "❌ **Error Getting Positions**",
                reply_markup=self._create_refresh_keyboard("positions"),
                parse_mode='Markdown'
            )
    
    async def _handle_analyze_callback(self, query, context):
        """Handle analyze button callback."""
        if not self.trading_system:
            await query.edit_message_text(
                "❌ **Trading System Not Available**",
                parse_mode='Markdown'
            )
            return
        
        # Check if system is shutting down
        if hasattr(self.trading_system, 'is_shutting_down') and self.trading_system.is_shutting_down:
            await query.edit_message_text(
                "🔄 **System Shutting Down**\n\nPlease try again after restart.",
                parse_mode='Markdown'
            )
            return
        
        # Start analysis
        await query.edit_message_text(
            "🤖 **AI Analysis Started**\n\nRunning intelligent trading analysis...\n\nWatch for detailed step-by-step updates below!",
            parse_mode='Markdown'
        )
        
        try:
            result = await self.trading_system.run_manual_analysis()
            # The analysis progress will be sent via the message manager
            # Just update the button message with completion status
            if isinstance(result, dict) and result.get("success"):
                completion_keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
                await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(completion_keyboard))
        except Exception as e:
            logger.error(f"Error in analyze callback: {e}")
            await query.edit_message_text(
                "❌ **Analysis Failed**\n\nPlease try again.",
                reply_markup=self._create_main_menu_keyboard(),
                parse_mode='Markdown'
            )
    
    async def _handle_help_callback(self, query, context):
        """Handle help button callback."""
        help_text = "🤖 **Available Commands:**\n\n"
        for command, description in self.commands.items():
            help_text += f"/{command} - {description}\n"
        
        help_text += "\n💡 **Tip:** Use the buttons below for quick access!"
        
        await query.edit_message_text(
            help_text,
            reply_markup=self._create_main_menu_keyboard(),
            parse_mode='Markdown'
        )
    
    async def _handle_emergency_callback(self, query, context):
        """Handle emergency button callback with confirmation."""
        confirmation_keyboard = self._create_confirmation_keyboard("emergency")
        await query.edit_message_text(
            "🚨 **Emergency Stop Confirmation**\n\n⚠️ This will immediately stop all trading operations!\n\nAre you sure you want to proceed?",
            reply_markup=confirmation_keyboard,
            parse_mode='Markdown'
        )
    
    async def _handle_refresh_callback(self, query, context, command: str):
        """Handle refresh button callback."""
        # Map command to appropriate callback handler
        if command == "status":
            await self._handle_status_callback(query, context)
        elif command == "portfolio":
            await self._handle_portfolio_callback(query, context)
        elif command == "orders":
            await self._handle_orders_callback(query, context)
        elif command == "positions":
            await self._handle_positions_callback(query, context)
        else:
            await query.edit_message_text(
                "❓ **Unknown Command**",
                reply_markup=self._create_main_menu_keyboard(),
                parse_mode='Markdown'
            )
    
    async def _handle_confirm_callback(self, query, context, action: str):
        """Handle confirmation button callback."""
        if action == "emergency":
            if not self.trading_system:
                await query.edit_message_text("❌ **Trading System Not Available**", parse_mode='Markdown')
                return
            
            await query.edit_message_text(
                "🚨 **EMERGENCY STOP INITIATED**\n\nStopping all trading operations immediately...",
                parse_mode='Markdown'
            )
            
            try:
                await self.trading_system.emergency_stop()
                await query.edit_message_text(
                    "⛔ **EMERGENCY STOP COMPLETE**\n\nAll trading operations have been stopped.",
                    reply_markup=self._create_main_menu_keyboard(),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error in emergency stop: {e}")
                await query.edit_message_text(
                    "❌ **Error During Emergency Stop**",
                    reply_markup=self._create_main_menu_keyboard(),
                    parse_mode='Markdown'
                )
        else:
            await query.edit_message_text(
                "❓ **Unknown Action**",
                reply_markup=self._create_main_menu_keyboard(),
                parse_mode='Markdown'
            ) 