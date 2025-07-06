import asyncio
import logging
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
from decimal import Decimal

# No need to import adapters - factory handles lazy loading

from src.interfaces.broker_api import BrokerAPI
from src.interfaces.market_data_api import MarketDataAPI
from src.interfaces.news_api import NewsAPI
from src.messaging.message_manager import MessageManager
from src.interfaces.factory import get_broker_api, get_market_data_api, get_news_api, MessageTransportFactory
from src.events.event_system import EventSystem, event_system
from src.agents.workflow_factory import WorkflowFactory, validate_workflow_config
from src.scheduler.trading_scheduler import TradingScheduler
from src.models.trading_models import (
    Order, Portfolio, TradingEvent, OrderSide, OrderType, 
    TimeInForce, OrderStatus
)
from config import settings


logger = logging.getLogger(__name__)


class TradingSystem:
    """Main trading system orchestrator"""
    
    def __init__(self):
        # Initialize API clients using factories
        self.broker_api = get_broker_api()
        self.market_data_api = get_market_data_api()
        self.news_api = get_news_api()
        
        # Initialize message manager with transport
        # Create transport using factory
        transport = MessageTransportFactory.create_message_transport(trading_system=self)
        transport._needs_async_init = True
        self.message_manager = MessageManager(transport=transport)
        
        # Log provider information
        logger.info(f"Broker Provider: {self.broker_api.get_provider_name()}")
        logger.info(f"Market Data Provider: {self.market_data_api.get_provider_name()}")
        logger.info(f"News Provider: {self.news_api.get_provider_name()}")
        logger.info(f"Message Transport: {self.message_manager.transport.get_transport_name()}")
        
        # Validate workflow configuration
        if not validate_workflow_config():
            logger.warning("Workflow configuration validation failed, using default settings")
        
        # Initialize core components
        self.event_system = event_system
        self.trading_workflow = WorkflowFactory.create_workflow(
            message_manager=self.message_manager
        )
        self.scheduler = TradingScheduler(trading_system=self)
        
        # Log workflow type being used
        logger.info(f"Initialized with {self.trading_workflow.get_workflow_type()} workflow")
        
        # System state
        self.is_running = False
        self.is_trading_enabled = False
        self.is_shutting_down = False
        self.last_portfolio_update = None
        self.active_orders = []
        
        # Operation tracking for graceful shutdown
        self.ongoing_operations: Set[asyncio.Task] = set()
        self.shutdown_timeout = 30  # seconds
        
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
        
    def _track_operation(self, coro):
        """Track an async operation for graceful shutdown"""
        task = asyncio.create_task(coro)
        self.ongoing_operations.add(task)
        
        def cleanup_task(task):
            self.ongoing_operations.discard(task)
        
        task.add_done_callback(cleanup_task)
        return task

    async def start(self):
        """Start the trading system"""
        try:
            if self.is_running:
                logger.warning("Trading system is already running")
                return False  # Return False to indicate no action taken
            
            logger.info("Starting trading system...")
            
            # Start event system
            await self.event_system.start()
            
            # Initialize message transport if needed
            if hasattr(self.message_manager.transport, '_needs_async_init'):
                logger.info("Initializing message transport...")
                try:
                    if await self.message_manager.transport.initialize():
                        logger.info("Message transport initialized successfully")
                        if await self.message_manager.transport.start():
                            logger.info("Message transport started successfully")
                        else:
                            logger.warning("Message transport failed to start")
                    else:
                        logger.warning("Message transport failed to initialize")
                except Exception as e:
                    logger.warning(f"Message transport initialization failed: {e}")
            
            # Start message manager processing
            await self.message_manager.start_processing()
            
            # Start scheduler with force restart to ensure clean start
            logger.info("Starting scheduler...")
            self.scheduler.start(force_restart=True)
            
            # Initialize daily stats
            await self._initialize_daily_stats()
            
            # Set system state
            self.is_running = True
            self.is_trading_enabled = True
            
            # Send system started event - this will trigger _handle_system_started which sends the message
            await self.event_system.publish_system_event(
                "system_started",
                "Trading system started successfully"
            )
            
            # Don't send startup message here - it's handled by _handle_system_started event handler
            # This avoids duplicate messages
            
            logger.info("Trading system started successfully")
            return True  # Return True to indicate successful start
            
        except Exception as e:
            logger.error(f"Failed to start trading system: {e}")
            await self.stop()
            raise
    
    async def stop(self):
        """Stop the trading system"""
        try:
            logger.info("Stopping trading system...")
            
            # Set shutdown flag
            self.is_shutting_down = True
            
            # Disable trading
            self.is_trading_enabled = False
            
            # Wait for ongoing operations to complete
            if self.ongoing_operations:
                logger.info(f"Waiting for {len(self.ongoing_operations)} ongoing operations to complete...")
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*self.ongoing_operations, return_exceptions=True),
                        timeout=self.shutdown_timeout
                    )
                    logger.info("All ongoing operations completed")
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout waiting for operations to complete, forcing shutdown")
                    # Cancel remaining operations
                    for task in self.ongoing_operations:
                        if not task.done():
                            task.cancel()
                    # Wait a bit more for cancellation to propagate
                    try:
                        await asyncio.wait_for(
                            asyncio.gather(*self.ongoing_operations, return_exceptions=True),
                            timeout=5
                        )
                    except asyncio.TimeoutError:
                        logger.warning("Some operations did not respond to cancellation")
            
            # Stop scheduler
            self.scheduler.stop()
            
            # Note: We DON'T stop the message transport (Telegram service) so it can still receive commands like /start
            # Only stop the message manager's automated processing
            logger.info("Stopping message manager processing (keeping transport active for commands)")
            await self.message_manager.stop_processing()
            
            # Stop event system
            await self.event_system.stop()
            
            # Set system state
            self.is_running = False
            self.is_shutting_down = False
            
            # Don't send system_stopped event since event system is already stopped
            # The _handle_stop command in Telegram service will handle user notification
            
            logger.info("Trading system stopped (Telegram commands still available)")
            
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
                    if order.id:
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
                "Emergency stop completed"
            )
            
            logger.warning("Emergency stop completed")
            
        except Exception as e:
            logger.error(f"Error during emergency stop: {e}")
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
            
            # Extract decision from workflow result
            decision = None
            if isinstance(result, dict):
                decision = result.get('decision')
            else:
                # Handle legacy TradingState objects
                decision = getattr(result, 'decision', None)
            
            # Update daily stats if trade was executed
            if decision and hasattr(decision, 'action') and decision.action != "HOLD":
                self.daily_stats['trades_executed'] += 1
            
            # Send rebalancing completed event
            decision_action = decision.action.value if (decision and hasattr(decision, 'action') and hasattr(decision.action, 'value')) else 'HOLD'
            await self.event_system.publish_system_event(
                "daily_rebalance_completed",
                f"Daily rebalancing completed. Decision: {decision_action}"
            )
            
            logger.info("Daily rebalancing completed")
            
        except Exception as e:
            logger.error(f"Error in daily rebalancing: {e}")
            await self.event_system.publish_system_event(
                "daily_rebalance_error",
                f"Error in daily rebalancing: {e}",
                "error"
            )
    
    async def run_manual_analysis(self):
        """Manually trigger the LLM trading workflow"""
        try:
            if not self.is_trading_enabled:
                logger.info("Trading is disabled, skipping manual analysis")
                return {
                    "success": False,
                    "message": "Trading is currently disabled"
                }
            
            if self.is_shutting_down:
                logger.info("System is shutting down, skipping manual analysis")
                return {
                    "success": False,
                    "message": "System is shutting down"
                }
            
            logger.info("Starting manual LLM trading analysis")
            
            # Create a cancellation-safe workflow execution
            async def safe_workflow_execution():
                try:
                    # Run the trading workflow
                    result = await self.trading_workflow.run_workflow({
                        "trigger": "manual_analysis",
                        "timestamp": datetime.now().isoformat()
                    })
                    return result
                except asyncio.CancelledError:
                    logger.info("Manual analysis cancelled due to system shutdown")
                    raise
                except Exception as e:
                    logger.error(f"Error in workflow execution: {e}")
                    raise
            
            # Track the operation for graceful shutdown
            operation_task = self._track_operation(safe_workflow_execution())
            
            try:
                result = await operation_task
            except asyncio.CancelledError:
                logger.info("Manual analysis was cancelled")
                return {
                    "success": False,
                    "message": "Analysis was cancelled due to system shutdown"
                }
            
            # Handle both dict and TradingState object returns
            decision = None
            if hasattr(result, 'decision'):
                decision = result.decision
            elif isinstance(result, dict) and 'decision' in result:
                decision = result['decision']
            
            # Update daily stats if trade was executed
            if decision and hasattr(decision, 'action') and decision.action != "HOLD":
                self.daily_stats['trades_executed'] += 1
            
            # Send manual analysis completed event
            decision_action = decision.action if (decision and hasattr(decision, 'action')) else 'HOLD'
            await self.event_system.publish_system_event(
                "manual_analysis_completed",
                f"Manual analysis completed. Decision: {decision_action}"
            )
            
            logger.info("Manual analysis completed")
            
            return {
                "success": True,
                "result": result,
                "message": f"Analysis completed. Decision: {decision_action}"
            }
            
        except asyncio.CancelledError:
            logger.info("Manual analysis cancelled due to system shutdown")
            return {
                "success": False,
                "message": "Analysis was cancelled due to system shutdown"
            }
        except Exception as e:
            logger.error(f"Error in manual analysis: {e}")
            await self.event_system.publish_system_event(
                "manual_analysis_error",
                f"Error in manual analysis: {e}",
                "error"
            )
            return {
                "success": False,
                "message": f"Error during analysis: {str(e)}"
            }
    
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
            if portfolio.day_pnl <= -(portfolio.equity * Decimal('0.1')):  # 10% daily loss limit
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
            await self.message_manager.send_message(summary)
            
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
            portfolio = await self.broker_api.get_portfolio()
            if portfolio is None:
                raise Exception("Failed to get portfolio from broker API")
            self.last_portfolio_update = datetime.now()
            return portfolio
        except Exception as e:
            logger.error(f"Error getting portfolio: {e}")
            raise
    
    async def get_active_orders(self) -> List[Order]:
        """Get active orders"""
        try:
            orders = await self.broker_api.get_orders(status="open")
            self.active_orders = orders
            return orders
        except Exception as e:
            logger.error(f"Error getting active orders: {e}")
            raise
    
    async def is_market_open(self) -> bool:
        """Check if market is open"""
        try:
            return await self.broker_api.is_market_open()
        except Exception as e:
            logger.error(f"Error checking market status: {e}")
            return False
    
    async def get_status(self) -> Dict[str, Any]:
        """Get system status"""
        try:
            portfolio = await self.get_portfolio()
            active_orders = await self.get_active_orders()
            
            # Get scheduler status
            scheduler_status = self.scheduler.get_schedule_status()
            
            return {
                "status": "running" if self.is_running else "stopped",
                "trading_enabled": self.is_trading_enabled,
                "market_open": await self.is_market_open(),
                "equity": str(portfolio.equity),
                "day_pnl": str(portfolio.day_pnl),
                "active_orders": len(active_orders),
                "positions": len(portfolio.positions),
                "last_update": datetime.now().isoformat(),
                "scheduler": {
                    "is_running": scheduler_status.get("is_running", False),
                    "actually_running": scheduler_status.get("actually_running", False),
                    "total_jobs": scheduler_status.get("total_jobs", 0),
                    "next_run": scheduler_status.get("next_run")
                }
            }
        except Exception as e:
            logger.error(f"Error getting system status: {e}")
            return {"error": str(e)}
    
    async def send_portfolio_alert(self, portfolio: Portfolio):
        """Send portfolio alert"""
        try:
            await self.message_manager.send_portfolio_update(portfolio)
        except Exception as e:
            logger.error(f"Error sending portfolio alert: {e}")
    
    # Event handlers
    async def _handle_order_created(self, event: TradingEvent):
        """Handle order created event"""
        try:
            if event.data and 'order' in event.data:
                order = event.data['order']
                await self.message_manager.send_order_notification(order, "created")
                
                # Log order creation
                logger.info(f"Order created: {order.symbol} {order.side.value} {order.quantity}")
                
        except Exception as e:
            logger.error(f"Error handling order created event: {e}")
    
    async def _handle_order_filled(self, event: TradingEvent):
        """Handle order filled event"""
        try:
            if event.data and 'order' in event.data:
                order = event.data['order']
                await self.message_manager.send_order_notification(order, "filled")
                
                # Update portfolio after fill
                await self._update_portfolio()
                
                # Log order fill
                logger.info(f"Order filled: {order.symbol} {order.side.value} {order.quantity}")
                
        except Exception as e:
            logger.error(f"Error handling order filled event: {e}")
    
    async def _handle_order_canceled(self, event: TradingEvent):
        """Handle order canceled event"""
        try:
            if event.data and 'order' in event.data:
                order = event.data['order']
                await self.message_manager.send_order_notification(order, "canceled")
                
                # Log order cancellation
                logger.info(f"Order canceled: {order.symbol} {order.side.value} {order.quantity}")
                
        except Exception as e:
            logger.error(f"Error handling order canceled event: {e}")
    
    async def _handle_order_rejected(self, event: TradingEvent):
        """Handle order rejected event"""
        try:
            if event.data and 'order' in event.data:
                order = event.data['order']
                await self.message_manager.send_order_notification(order, "rejected")
                
                # Log order rejection
                logger.error(f"Order rejected: {order.symbol} {order.side.value} {order.quantity}")
                
        except Exception as e:
            logger.error(f"Error handling order rejected event: {e}")
    
    async def _handle_portfolio_updated(self, event: TradingEvent):
        """Handle portfolio updated event"""
        try:
            if event.data and 'portfolio' in event.data:
                portfolio = event.data['portfolio']
                await self.message_manager.send_portfolio_update(portfolio)
                
        except Exception as e:
            logger.error(f"Error handling portfolio updated event: {e}")
    
    async def _handle_system_started(self, event: TradingEvent):
        """Handle system started event"""
        try:
            # Send startup notification directly through telegram service instead of message manager
            transport = self.message_manager.transport
            try:
                # Try to call the new method if it exists (TelegramService)
                if hasattr(transport, 'send_system_started_notification'):
                    await transport.send_system_started_notification()  # type: ignore
                    return
            except Exception as e:
                logger.debug(f"Could not send startup notification via transport: {e}")
            
            # Fallback to message manager if telegram service method not available
            await self.message_manager.send_system_alert(
                "🚀 **LLM Agent Trading System**\n\nAll components initialized successfully. Ready for trading operations!", 
                "success"
            )
        except Exception as e:
            logger.error(f"Error handling system started event: {e}")
    
    async def _handle_system_stopped(self, event: TradingEvent):
        """Handle system stopped event"""
        try:
            await self.message_manager.send_system_alert(
                "Trading system stopped", 
                "info"
            )
        except Exception as e:
            logger.error(f"Error handling system stopped event: {e}")
    
    async def _handle_error(self, event: TradingEvent):
        """Handle error event"""
        try:
            error_message = event.data.get('message', 'Unknown error') if event.data else 'Unknown error'
            await self.message_manager.send_system_alert(
                f"System error: {error_message}", 
                "error"
            )
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
            order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
            
            order = Order(
                symbol=symbol,
                side=order_side,
                order_type=OrderType.MARKET,
                quantity=quantity,
                time_in_force=TimeInForce.DAY
            )
            
            order_id = await self.broker_api.submit_order(order)
            if order_id:
                # Get the full order details
                placed_order = await self.broker_api.get_order(order_id)
                if placed_order:
                    await self.event_system.publish_order_event(placed_order, "order_created")
                    return placed_order
            
            return None
            
        except Exception as e:
            logger.error(f"Error placing market order: {e}")
            raise
    
    async def _cancel_order(self, order_id: str):
        """Cancel an order"""
        try:
            success = await self.broker_api.cancel_order(order_id)
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
            if position.unrealized_pnl < 0:
                loss_percentage = abs(position.unrealized_pnl / position.market_value)
                
                if loss_percentage >= settings.stop_loss_percentage:
                    logger.warning(f"Triggering stop loss for {position.symbol}")
                    
                    # Place sell order
                    await self._place_market_order(
                        position.symbol,
                        "sell",
                        Decimal(str(position.qty))
                    )
                    
                    await self.message_manager.send_system_alert(
                        "warning",
                        f"Stop loss triggered for {position.symbol}. Loss: {loss_percentage:.2%}",
                        "risk_management"
                    )
                    
        except Exception as e:
            logger.error(f"Error handling stop loss: {e}")
    
    async def _handle_take_profit(self, position):
        """Handle take profit for a position"""
        try:
            if position.unrealized_pnl > 0:
                profit_percentage = position.unrealized_pnl / position.market_value
                
                if profit_percentage >= settings.take_profit_percentage:
                    logger.info(f"Triggering take profit for {position.symbol}")
                    
                    # Place sell order
                    await self._place_market_order(
                        position.symbol,
                        "sell",
                        Decimal(str(position.qty))
                    )
                    
                    await self.message_manager.send_system_alert(
                        "success",
                        f"Take profit triggered for {position.symbol}. Profit: {profit_percentage:.2%}",
                        "profit_taking"
                    )
                    
        except Exception as e:
            logger.error(f"Error handling take profit: {e}")
    
    async def _handle_portfolio_risk(self, portfolio: Portfolio):
        """Handle portfolio-level risk management"""
        try:
            # Check overall portfolio risk
            day_pnl_percentage = portfolio.day_pnl / portfolio.portfolio_value if portfolio.portfolio_value > 0 else 0
            
            if day_pnl_percentage < -0.05:  # 5% daily loss threshold
                logger.warning(f"Portfolio daily loss exceeds 5%: {day_pnl_percentage:.2%}")
                
                await self.message_manager.send_system_alert(
                    "warning",
                    f"Portfolio daily loss: {day_pnl_percentage:.2%}",
                    "portfolio_risk"
                )
                
                # Consider stopping trading or reducing position sizes
                if day_pnl_percentage < -0.10:  # 10% daily loss
                    await self.stop_trading()
                    
        except Exception as e:
            logger.error(f"Error handling portfolio risk: {e}") 