import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from decimal import Decimal

from src.apis.alpaca_api import AlpacaAPI
from src.apis.tiingo_api import TiingoAPI
from src.apis.telegram_bot import TelegramBot
from src.events.event_system import EventSystem, event_system
from src.agents.trading_workflow import TradingWorkflow
from src.scheduler.trading_scheduler import TradingScheduler
from src.models.trading_models import Order, Portfolio, TradingEvent
from config import settings


logger = logging.getLogger(__name__)


class TradingSystem:
    """Main trading system orchestrator"""
    
    def __init__(self):
        # Initialize API clients
        self.alpaca_api = AlpacaAPI()
        self.tiingo_api = TiingoAPI()
        self.telegram_bot = TelegramBot(trading_system=self)
        
        # Initialize core components
        self.event_system = event_system
        self.trading_workflow = TradingWorkflow(self.alpaca_api, self.tiingo_api)
        self.scheduler = TradingScheduler(trading_system=self)
        
        # System state
        self.is_running = False
        self.is_trading_enabled = False
        self.last_portfolio_update = None
        self.active_orders = []
        
        # Performance tracking
        self.daily_stats = {
            'trades_executed': 0,
            'total_pnl': Decimal('0'),
            'start_equity': None,
            'last_update': None
        }
        
        # Setup event handlers
        self._setup_event_handlers()
        
    def _setup_event_handlers(self):
        """Setup event handlers for the trading system"""
        
        # Order event handlers
        self.event_system.register_handler("order_created", self._handle_order_created)
        self.event_system.register_handler("order_filled", self._handle_order_filled)
        self.event_system.register_handler("order_canceled", self._handle_order_canceled)
        self.event_system.register_handler("order_rejected", self._handle_order_rejected)
        
        # Portfolio event handlers
        self.event_system.register_handler("portfolio_updated", self._handle_portfolio_updated)
        
        # System event handlers
        self.event_system.register_handler("system_started", self._handle_system_started)
        self.event_system.register_handler("system_stopped", self._handle_system_stopped)
        self.event_system.register_handler("error", self._handle_error)
        
    async def start(self):
        """Start the trading system"""
        try:
            if self.is_running:
                logger.warning("Trading system is already running")
                return
            
            logger.info("Starting trading system...")
            
            # Start event system
            await self.event_system.start()
            
            # Start Telegram bot
            await self.telegram_bot.start_bot()
            
            # Start scheduler
            self.scheduler.start()
            
            # Initialize daily stats
            await self._initialize_daily_stats()
            
            # Set system state
            self.is_running = True
            self.is_trading_enabled = True
            
            # Send system started event
            await self.event_system.publish_system_event(
                "system_started",
                "Trading system started successfully"
            )
            
            logger.info("Trading system started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start trading system: {e}")
            await self.stop()
            raise
    
    async def stop(self):
        """Stop the trading system"""
        try:
            logger.info("Stopping trading system...")
            
            # Disable trading
            self.is_trading_enabled = False
            
            # Stop scheduler
            self.scheduler.stop()
            
            # Stop Telegram bot
            await self.telegram_bot.stop_bot()
            
            # Stop event system
            await self.event_system.stop()
            
            # Set system state
            self.is_running = False
            
            # Send system stopped event
            await self.event_system.publish_system_event(
                "system_stopped",
                "Trading system stopped"
            )
            
            logger.info("Trading system stopped")
            
        except Exception as e:
            logger.error(f"Error stopping trading system: {e}")
    
    async def start_trading(self):
        """Start trading operations"""
        try:
            if not self.is_running:
                await self.start()
            
            self.is_trading_enabled = True
            
            await self.event_system.publish_system_event(
                "trading_started",
                "Trading operations started"
            )
            
            logger.info("Trading operations started")
            
        except Exception as e:
            logger.error(f"Failed to start trading: {e}")
            raise
    
    async def stop_trading(self):
        """Stop trading operations"""
        try:
            self.is_trading_enabled = False
            
            await self.event_system.publish_system_event(
                "trading_stopped",
                "Trading operations stopped"
            )
            
            logger.info("Trading operations stopped")
            
        except Exception as e:
            logger.error(f"Failed to stop trading: {e}")
            raise
    
    async def emergency_stop(self):
        """Emergency stop - cancel all orders and close positions"""
        try:
            logger.warning("EMERGENCY STOP ACTIVATED")
            
            # Disable trading
            self.is_trading_enabled = False
            
            # Cancel all open orders
            orders = await self.get_active_orders()
            for order in orders:
                try:
                    await self._cancel_order(order.id)
                except Exception as e:
                    logger.error(f"Failed to cancel order {order.id}: {e}")
            
            # Close all positions (simplified - in practice you'd want more sophisticated logic)
            portfolio = await self.get_portfolio()
            for position in portfolio.positions:
                try:
                    if position.quantity > 0:
                        # Close long position
                        await self._place_market_order(position.symbol, "sell", abs(position.quantity))
                    elif position.quantity < 0:
                        # Close short position
                        await self._place_market_order(position.symbol, "buy", abs(position.quantity))
                except Exception as e:
                    logger.error(f"Failed to close position {position.symbol}: {e}")
            
            await self.event_system.publish_system_event(
                "emergency_stop",
                "Emergency stop activated - all orders cancelled and positions closed",
                "error"
            )
            
            logger.warning("Emergency stop completed")
            
        except Exception as e:
            logger.error(f"Error in emergency stop: {e}")
            raise
    
    async def run_daily_rebalance(self):
        """Run daily portfolio rebalancing"""
        try:
            if not self.is_trading_enabled:
                logger.info("Trading is disabled, skipping rebalancing")
                return
            
            logger.info("Starting daily rebalancing workflow")
            
            # Run the trading workflow
            result = await self.trading_workflow.run_workflow({
                "trigger": "daily_rebalance",
                "timestamp": datetime.now().isoformat()
            })
            
            # Update daily stats
            if result.decision and result.decision.action != "HOLD":
                self.daily_stats['trades_executed'] += 1
            
            # Send rebalancing completed event
            await self.event_system.publish_system_event(
                "daily_rebalance_completed",
                f"Daily rebalancing completed. Decision: {result.decision.action if result.decision else 'HOLD'}"
            )
            
            logger.info("Daily rebalancing completed")
            
        except Exception as e:
            logger.error(f"Error in daily rebalancing: {e}")
            await self.event_system.publish_system_event(
                "daily_rebalance_error",
                f"Error in daily rebalancing: {e}",
                "error"
            )
    
    async def run_risk_checks(self):
        """Run risk management checks"""
        try:
            portfolio = await self.get_portfolio()
            
            # Check for positions with large losses
            for position in portfolio.positions:
                if position.unrealized_pnl_percentage <= -settings.stop_loss_percentage:
                    await self._handle_stop_loss(position)
                
                elif position.unrealized_pnl_percentage >= settings.take_profit_percentage:
                    await self._handle_take_profit(position)
            
            # Check overall portfolio risk
            if portfolio.day_pnl <= -(portfolio.equity * 0.1):  # 10% daily loss limit
                await self._handle_portfolio_risk(portfolio)
            
        except Exception as e:
            logger.error(f"Error in risk checks: {e}")
    
    async def run_eod_analysis(self):
        """Run end-of-day analysis"""
        try:
            portfolio = await self.get_portfolio()
            
            # Update daily stats
            self.daily_stats['last_update'] = datetime.now()
            if self.daily_stats['start_equity'] is None:
                self.daily_stats['start_equity'] = portfolio.equity
            
            # Calculate daily performance
            daily_return = (portfolio.equity - self.daily_stats['start_equity']) / self.daily_stats['start_equity']
            
            # Create summary report
            summary = f"""
End of Day Summary:
- Equity: ${portfolio.equity:,.2f}
- Day P&L: ${portfolio.day_pnl:,.2f}
- Daily Return: {daily_return:.2%}
- Trades Executed: {self.daily_stats['trades_executed']}
- Active Positions: {len(portfolio.positions)}
"""
            
            # Send EOD report
            await self.telegram_bot.send_message(summary)
            
            # Reset daily stats for next day
            self.daily_stats['trades_executed'] = 0
            self.daily_stats['start_equity'] = portfolio.equity
            
            logger.info("End-of-day analysis completed")
            
        except Exception as e:
            logger.error(f"Error in EOD analysis: {e}")
    
    async def cleanup_old_data(self):
        """Clean up old data and logs"""
        try:
            # This is a placeholder for cleanup operations
            # In practice, you'd clean up old log files, database entries, etc.
            logger.info("Daily cleanup completed")
            
        except Exception as e:
            logger.error(f"Error in daily cleanup: {e}")
    
    async def get_portfolio(self) -> Portfolio:
        """Get current portfolio"""
        try:
            portfolio = self.alpaca_api.get_portfolio()
            self.last_portfolio_update = datetime.now()
            return portfolio
        except Exception as e:
            logger.error(f"Error getting portfolio: {e}")
            raise
    
    async def get_active_orders(self) -> List[Order]:
        """Get active orders"""
        try:
            orders = self.alpaca_api.get_orders(status="open")
            self.active_orders = orders
            return orders
        except Exception as e:
            logger.error(f"Error getting active orders: {e}")
            raise
    
    async def is_market_open(self) -> bool:
        """Check if market is open"""
        try:
            return self.alpaca_api.is_market_open()
        except Exception as e:
            logger.error(f"Error checking market status: {e}")
            return False
    
    async def get_status(self) -> Dict[str, Any]:
        """Get system status"""
        try:
            portfolio = await self.get_portfolio()
            active_orders = await self.get_active_orders()
            
            return {
                "status": "running" if self.is_running else "stopped",
                "trading_enabled": self.is_trading_enabled,
                "market_open": await self.is_market_open(),
                "equity": str(portfolio.equity),
                "day_pnl": str(portfolio.day_pnl),
                "active_orders": len(active_orders),
                "positions": len(portfolio.positions),
                "last_update": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting system status: {e}")
            return {"error": str(e)}
    
    async def send_portfolio_alert(self, portfolio: Portfolio):
        """Send portfolio alert"""
        try:
            await self.telegram_bot.send_portfolio_update(portfolio)
        except Exception as e:
            logger.error(f"Error sending portfolio alert: {e}")
    
    # Event handlers
    async def _handle_order_created(self, event: TradingEvent):
        """Handle order created event"""
        try:
            order_data = event.data
            order = Order(
                id=order_data.get("order_id"),
                symbol=order_data.get("symbol"),
                side=order_data.get("side"),
                quantity=Decimal(order_data.get("quantity", "0")),
                price=Decimal(order_data.get("price", "0")) if order_data.get("price") else None,
                status=order_data.get("status")
            )
            
            await self.telegram_bot.send_order_notification(order, "order_created")
            
        except Exception as e:
            logger.error(f"Error handling order created event: {e}")
    
    async def _handle_order_filled(self, event: TradingEvent):
        """Handle order filled event"""
        try:
            order_data = event.data
            order = Order(
                id=order_data.get("order_id"),
                symbol=order_data.get("symbol"),
                side=order_data.get("side"),
                quantity=Decimal(order_data.get("quantity", "0")),
                filled_quantity=Decimal(order_data.get("filled_quantity", "0")),
                filled_price=Decimal(order_data.get("filled_price", "0")) if order_data.get("filled_price") else None,
                status=order_data.get("status")
            )
            
            await self.telegram_bot.send_order_notification(order, "order_filled")
            
            # Update portfolio
            await self._update_portfolio()
            
        except Exception as e:
            logger.error(f"Error handling order filled event: {e}")
    
    async def _handle_order_canceled(self, event: TradingEvent):
        """Handle order canceled event"""
        try:
            order_data = event.data
            order = Order(
                id=order_data.get("order_id"),
                symbol=order_data.get("symbol"),
                side=order_data.get("side"),
                quantity=Decimal(order_data.get("quantity", "0")),
                status=order_data.get("status")
            )
            
            await self.telegram_bot.send_order_notification(order, "order_canceled")
            
        except Exception as e:
            logger.error(f"Error handling order canceled event: {e}")
    
    async def _handle_order_rejected(self, event: TradingEvent):
        """Handle order rejected event"""
        try:
            order_data = event.data
            order = Order(
                id=order_data.get("order_id"),
                symbol=order_data.get("symbol"),
                side=order_data.get("side"),
                quantity=Decimal(order_data.get("quantity", "0")),
                status=order_data.get("status")
            )
            
            await self.telegram_bot.send_order_notification(order, "order_rejected")
            
        except Exception as e:
            logger.error(f"Error handling order rejected event: {e}")
    
    async def _handle_portfolio_updated(self, event: TradingEvent):
        """Handle portfolio updated event"""
        try:
            # Portfolio update handling is done in the specific methods
            pass
        except Exception as e:
            logger.error(f"Error handling portfolio updated event: {e}")
    
    async def _handle_system_started(self, event: TradingEvent):
        """Handle system started event"""
        try:
            message = event.data.get("message", "System started")
            await self.telegram_bot.send_alert("success", message)
        except Exception as e:
            logger.error(f"Error handling system started event: {e}")
    
    async def _handle_system_stopped(self, event: TradingEvent):
        """Handle system stopped event"""
        try:
            message = event.data.get("message", "System stopped")
            await self.telegram_bot.send_alert("info", message)
        except Exception as e:
            logger.error(f"Error handling system stopped event: {e}")
    
    async def _handle_error(self, event: TradingEvent):
        """Handle error event"""
        try:
            message = event.data.get("message", "System error")
            await self.telegram_bot.send_alert("error", message)
        except Exception as e:
            logger.error(f"Error handling error event: {e}")
    
    # Helper methods
    async def _initialize_daily_stats(self):
        """Initialize daily statistics"""
        try:
            portfolio = await self.get_portfolio()
            self.daily_stats['start_equity'] = portfolio.equity
            self.daily_stats['last_update'] = datetime.now()
        except Exception as e:
            logger.error(f"Error initializing daily stats: {e}")
    
    async def _update_portfolio(self):
        """Update portfolio and publish event"""
        try:
            portfolio = await self.get_portfolio()
            await self.event_system.publish_portfolio_event(portfolio)
        except Exception as e:
            logger.error(f"Error updating portfolio: {e}")
    
    async def _place_market_order(self, symbol: str, side: str, quantity: Decimal):
        """Place a market order"""
        try:
            order = Order(
                symbol=symbol,
                side=side,
                order_type="market",
                quantity=quantity,
                time_in_force="day"
            )
            
            placed_order = self.alpaca_api.place_order(order)
            await self.event_system.publish_order_event(placed_order, "order_created")
            
            return placed_order
            
        except Exception as e:
            logger.error(f"Error placing market order: {e}")
            raise
    
    async def _cancel_order(self, order_id: str):
        """Cancel an order"""
        try:
            success = self.alpaca_api.cancel_order(order_id)
            if success:
                await self.event_system.publish_system_event(
                    "order_canceled",
                    f"Order {order_id} cancelled"
                )
            return success
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            raise
    
    async def _handle_stop_loss(self, position):
        """Handle stop loss for a position"""
        try:
            logger.warning(f"Stop loss triggered for {position.symbol}")
            
            # Place market order to close position
            side = "sell" if position.quantity > 0 else "buy"
            await self._place_market_order(position.symbol, side, abs(position.quantity))
            
            await self.telegram_bot.send_alert(
                "warning",
                f"Stop loss triggered for {position.symbol}. Position closed."
            )
            
        except Exception as e:
            logger.error(f"Error handling stop loss for {position.symbol}: {e}")
    
    async def _handle_take_profit(self, position):
        """Handle take profit for a position"""
        try:
            logger.info(f"Take profit triggered for {position.symbol}")
            
            # Place market order to close position
            side = "sell" if position.quantity > 0 else "buy"
            await self._place_market_order(position.symbol, side, abs(position.quantity))
            
            await self.telegram_bot.send_alert(
                "success",
                f"Take profit triggered for {position.symbol}. Position closed."
            )
            
        except Exception as e:
            logger.error(f"Error handling take profit for {position.symbol}: {e}")
    
    async def _handle_portfolio_risk(self, portfolio: Portfolio):
        """Handle portfolio risk management"""
        try:
            logger.warning("Portfolio risk threshold exceeded")
            
            # This is a simplified example - in practice you'd want more sophisticated risk management
            await self.telegram_bot.send_alert(
                "warning",
                f"Portfolio risk threshold exceeded. Day P&L: ${portfolio.day_pnl:,.2f}"
            )
            
            # Optionally disable trading
            # self.is_trading_enabled = False
            
        except Exception as e:
            logger.error(f"Error handling portfolio risk: {e}") 