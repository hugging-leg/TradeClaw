import asyncio
import logging
from typing import Dict, Callable, Any, Optional
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from config import settings
from src.models.trading_models import Order, Portfolio, TradingEvent
from decimal import Decimal


logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram bot for notifications and manual control"""
    
    def __init__(self, trading_system=None):
        self.bot = Bot(token=settings.telegram_bot_token)
        self.chat_id = settings.telegram_chat_id
        self.trading_system = trading_system
        self.application = None
        self.is_running = False
        self.command_handlers = {}
        
    async def initialize(self):
        """Initialize the bot application"""
        self.application = Application.builder().token(settings.telegram_bot_token).build()
        
        # Add command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("stop", self.stop_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("portfolio", self.portfolio_command))
        self.application.add_handler(CommandHandler("orders", self.orders_command))
        self.application.add_handler(CommandHandler("analyze", self.analyze_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("emergency_stop", self.emergency_stop_command))
        
        # Add callback query handler for inline keyboards
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        
        logger.info("Telegram bot initialized")
    
    async def start_bot(self):
        """Start the bot"""
        if not self.application:
            await self.initialize()
        
        self.is_running = True
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        # Send startup message
        await self.send_message("🤖 Trading Bot Started!\n\nUse /help to see available commands.")
        
        logger.info("Telegram bot started")
    
    async def stop_bot(self):
        """Stop the bot"""
        if self.application and self.is_running:
            self.is_running = False
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            logger.info("Telegram bot stopped")
    
    async def send_message(self, message: str, parse_mode: str = None, reply_markup=None):
        """Send a message to the configured chat"""
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
    
    async def send_order_notification(self, order: Order, event_type: str):
        """Send order notification"""
        try:
            emoji_map = {
                "order_created": "📝",
                "order_filled": "✅",
                "order_canceled": "❌",
                "order_rejected": "🚫"
            }
            
            emoji = emoji_map.get(event_type, "📈")
            
            message = f"{emoji} **{event_type.replace('_', ' ').title()}**\n\n"
            message += f"**Symbol:** {order.symbol}\n"
            message += f"**Side:** {order.side.value.upper()}\n"
            message += f"**Quantity:** {order.quantity}\n"
            message += f"**Type:** {order.order_type.value.upper()}\n"
            
            if order.price:
                message += f"**Price:** ${order.price:.2f}\n"
            
            if order.filled_price and order.filled_quantity:
                message += f"**Filled:** {order.filled_quantity} @ ${order.filled_price:.2f}\n"
            
            message += f"**Status:** {order.status.value.upper()}\n"
            message += f"**Time:** {order.created_at or 'N/A'}\n"
            
            await self.send_message(message, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Failed to send order notification: {e}")
    
    async def send_portfolio_update(self, portfolio: Portfolio):
        """Send portfolio update notification"""
        try:
            message = "📊 **Portfolio Update**\n\n"
            message += f"**Equity:** ${portfolio.equity:,.2f}\n"
            message += f"**Cash:** ${portfolio.cash:,.2f}\n"
            message += f"**Market Value:** ${portfolio.market_value:,.2f}\n"
            message += f"**Day P&L:** ${portfolio.day_pnl:,.2f}\n"
            message += f"**Total P&L:** ${portfolio.total_pnl:,.2f}\n"
            message += f"**Buying Power:** ${portfolio.buying_power:,.2f}\n"
            message += f"**Positions:** {len(portfolio.positions)}\n"
            
            if portfolio.positions:
                message += "\n**Current Positions:**\n"
                for pos in portfolio.positions[:5]:  # Show first 5 positions
                    pnl_emoji = "📈" if pos.unrealized_pnl > 0 else "📉"
                    message += f"{pnl_emoji} {pos.symbol}: {pos.quantity} @ ${pos.unrealized_pnl:,.2f}\n"
                
                if len(portfolio.positions) > 5:
                    message += f"... and {len(portfolio.positions) - 5} more positions\n"
            
            await self.send_message(message, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Failed to send portfolio update: {e}")
    
    async def send_alert(self, alert_type: str, message: str):
        """Send alert notification"""
        try:
            emoji_map = {
                "error": "🚨",
                "warning": "⚠️",
                "info": "ℹ️",
                "success": "✅"
            }
            
            emoji = emoji_map.get(alert_type, "📢")
            alert_message = f"{emoji} **{alert_type.upper()}**\n\n{message}"
            
            await self.send_message(alert_message, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
    
    # Command handlers
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        if self.trading_system:
            await self.trading_system.start_trading()
            await update.message.reply_text("🚀 Trading system started!")
        else:
            await update.message.reply_text("❌ Trading system not available")
    
    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stop command"""
        if self.trading_system:
            await self.trading_system.stop_trading()
            await update.message.reply_text("🛑 Trading system stopped!")
        else:
            await update.message.reply_text("❌ Trading system not available")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        try:
            if self.trading_system:
                status = await self.trading_system.get_status()
                message = f"📊 **Trading System Status**\n\n"
                message += f"**Status:** {status.get('status', 'Unknown')}\n"
                message += f"**Market Open:** {status.get('market_open', 'Unknown')}\n"
                message += f"**Active Orders:** {status.get('active_orders', 0)}\n"
                message += f"**Last Update:** {status.get('last_update', 'Unknown')}\n"
                
                await update.message.reply_text(message, parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ Trading system not available")
                
        except Exception as e:
            await update.message.reply_text(f"❌ Error getting status: {e}")
    
    async def portfolio_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /portfolio command"""
        try:
            if self.trading_system:
                portfolio = await self.trading_system.get_portfolio()
                await self.send_portfolio_update(portfolio)
            else:
                await update.message.reply_text("❌ Trading system not available")
                
        except Exception as e:
            await update.message.reply_text(f"❌ Error getting portfolio: {e}")
    
    async def orders_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /orders command"""
        try:
            if self.trading_system:
                orders = await self.trading_system.get_active_orders()
                
                if not orders:
                    await update.message.reply_text("📋 No active orders")
                    return
                
                message = "📋 **Active Orders**\n\n"
                for order in orders[:10]:  # Show first 10 orders
                    message += f"**{order.symbol}** - {order.side.value.upper()}\n"
                    message += f"Qty: {order.quantity} @ ${order.price or 'Market'}\n"
                    message += f"Status: {order.status.value.upper()}\n\n"
                
                await update.message.reply_text(message, parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ Trading system not available")
                
        except Exception as e:
            await update.message.reply_text(f"❌ Error getting orders: {e}")
    
    async def analyze_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /analyze command - manually trigger LLM trading workflow"""
        try:
            if not self.trading_system:
                await update.message.reply_text("❌ Trading system not available")
                return
            
            # Send initial message
            await update.message.reply_text("🤖 Starting LLM trading analysis...")
            
            # Run the manual analysis
            result = await self.trading_system.run_manual_analysis()
            
            if result["success"]:
                # Create detailed response message
                analysis_result = result.get("result")
                message = "✅ **Analysis Complete**\n\n"
                
                # Handle both TradingState object and dict formats
                decision = None
                if analysis_result:
                    if hasattr(analysis_result, 'decision'):
                        decision = analysis_result.decision
                    elif isinstance(analysis_result, dict) and 'decision' in analysis_result:
                        decision = analysis_result['decision']
                
                if decision and hasattr(decision, 'action'):
                    message += f"**Decision:** {decision.action.upper()}\n"
                    message += f"**Symbol:** {decision.symbol or 'N/A'}\n"
                    message += f"**Confidence:** {decision.confidence:.2%}\n"
                    message += f"**Reasoning:** {decision.reasoning[:200]}{'...' if len(decision.reasoning) > 200 else ''}\n"
                    
                    if decision.quantity:
                        message += f"**Quantity:** {decision.quantity}\n"
                    if hasattr(decision, 'price') and decision.price:
                        message += f"**Target Price:** ${decision.price:.2f}\n"
                else:
                    message += "**Decision:** HOLD\n"
                    message += "**Reasoning:** No trading opportunity found or analysis incomplete\n"
                
                message += f"\n**Triggered:** Manual analysis"
                
                await update.message.reply_text(message, parse_mode="Markdown")
            else:
                await update.message.reply_text(f"❌ Analysis failed: {result['message']}")
                
        except Exception as e:
            await update.message.reply_text(f"❌ Error running analysis: {e}")
            logger.error(f"Error in analyze_command: {e}")
    
    async def emergency_stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /emergency_stop command"""
        keyboard = [
            [InlineKeyboardButton("🚨 CONFIRM EMERGENCY STOP", callback_data="emergency_stop_confirm")],
            [InlineKeyboardButton("❌ Cancel", callback_data="emergency_stop_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🚨 **EMERGENCY STOP**\n\n"
            "This will:\n"
            "• Stop all trading\n"
            "• Cancel all open orders\n"
            "• Close all positions\n\n"
            "Are you sure?",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """🤖 *Trading Bot Commands*

*Basic Controls:*
/start - Start trading system
/stop - Stop trading system
/status - Get system status

*Information:*
/portfolio - View portfolio
/orders - View active orders

*Trading:*
/analyze - Manually trigger LLM trading analysis

*Emergency:*
/emergency\\_stop - Emergency stop (cancel all orders & close positions)

*Other:*
/help - Show this help message

*Note:* This bot will automatically send notifications for:
- Order executions
- Portfolio updates
- System alerts"""
        
        await update.message.reply_text(help_text, parse_mode="Markdown")
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "emergency_stop_confirm":
            if self.trading_system:
                await self.trading_system.emergency_stop()
                await query.edit_message_text("🚨 EMERGENCY STOP ACTIVATED!")
            else:
                await query.edit_message_text("❌ Trading system not available")
        
        elif query.data == "emergency_stop_cancel":
            await query.edit_message_text("❌ Emergency stop cancelled")
    
    def set_trading_system(self, trading_system):
        """Set the trading system reference"""
        self.trading_system = trading_system 