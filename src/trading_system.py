import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from decimal import Decimal
import pytz

from src.interfaces.broker_api import BrokerAPI
from src.interfaces.market_data_api import MarketDataAPI
from src.interfaces.news_api import NewsAPI
from src.messaging.message_manager import MessageManager
from src.interfaces.factory import get_broker_api, get_market_data_api, get_news_api, MessageTransportFactory
from src.events.event_system import EventSystem, event_system
from src.agents.workflow_factory import WorkflowFactory, validate_workflow_config
from src.services.realtime_monitor import RealtimeMarketMonitor
from src.models.trading_models import (
    Order, Portfolio, TradingEvent, OrderSide, OrderType, 
    TimeInForce, OrderStatus
)
from src.utils.time_utils import (
    parse_time_config,
    calculate_next_trading_day_time,
    calculate_next_interval
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
        
        # Initialize event system first (needed by message transport)
        self.event_system = event_system
        
        # Initialize message manager with transport (pass event_system to transport)
        transport = MessageTransportFactory.create_message_transport(event_system=self.event_system)
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
        self.trading_workflow = WorkflowFactory.create_workflow(
            message_manager=self.message_manager
        )
        self.realtime_monitor = RealtimeMarketMonitor(trading_system=self)
        self.timezone = pytz.timezone('US/Eastern')  # Market timezone
        
        # Log workflow type being used
        logger.info(f"Initialized with {self.trading_workflow.get_workflow_type()} workflow")
        
        # Enable realtime monitoring for portfolio management workflows
        self.enable_realtime_monitoring = (
            self.trading_workflow.get_workflow_type() in ["balanced_portfolio", "llm_portfolio"]
        )
        
        # System state
        self.is_running = False
        self.is_trading_enabled = False
        self.is_shutting_down = False
        self.last_portfolio_update = None
        self.active_orders = []
        
        # Workflow execution tracking (for event throttling)
        self.last_workflow_execution: Dict[str, datetime] = {}  # trigger -> last execution time
        self.min_workflow_interval_minutes = 30  # Minimum interval between workflow executions
        self.throttle_priority_threshold = -7
        self.throttled_events: Dict[str, List[TradingEvent]] = {}  # trigger -> list of throttled events
        
        # Triggers that require throttling (only LLM self-scheduled for now)
        self.throttled_triggers = {"llm_scheduled"}  # Set of triggers to throttle
        
        # Track pending throttle check events to avoid duplicates
        self.pending_throttle_checks: Dict[str, bool] = {}  # trigger -> has_pending_check
        
        
        # Performance tracking
        self.daily_stats = {
            'trades_executed': 0,
            'total_pnl': Decimal('0'),
            'start_equity': None,
            'last_update': None
        }
        
        # Scheduling intervals (in minutes) - configurable via settings
        self.portfolio_check_interval = settings.portfolio_check_interval
        self.risk_check_interval = settings.risk_check_interval
        
        # Setup event handlers
        self._setup_event_handlers()
        
    def _setup_event_handlers(self):
        """Setup event handlers for workflow triggers"""
        
        # Unified workflow trigger handler
        self.event_system.register_handler("trigger_workflow", self._handle_workflow_trigger)
        
        # Trading control handlers
        self.event_system.register_handler("enable_trading", self._handle_enable_trading)
        self.event_system.register_handler("disable_trading", self._handle_disable_trading)
        
        # System control handlers (from Telegram commands)
        self.event_system.register_handler("emergency_stop", self._handle_emergency_stop)
        
        # Query handlers (from Telegram commands)
        self.event_system.register_handler("query_status", self._handle_query_status)
        self.event_system.register_handler("query_portfolio", self._handle_query_portfolio)
        self.event_system.register_handler("query_orders", self._handle_query_orders)
        
        # Other system event handlers
        self.event_system.register_handler("trigger_portfolio_check", self._handle_portfolio_check_trigger)
        self.event_system.register_handler("trigger_risk_check", self._handle_risk_check_trigger)
        self.event_system.register_handler("trigger_eod_analysis", self._handle_eod_analysis_trigger)

    async def start(self, enable_trading: bool = True):
        """
        Start the trading system
        
        Args:
            enable_trading: Whether to enable trading immediately (default: True)
        
        Returns:
            True if started successfully, False if already running
        """
        try:
            if self.is_running:
                logger.warning("Trading system is already running")
                return False
            
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
            
            # Initialize daily stats
            await self._initialize_daily_stats()
            
            # Initialize scheduled events (self-perpetuating event chains)
            await self._initialize_scheduled_events()
            
            # Start realtime monitoring if enabled
            if self.enable_realtime_monitoring:
                logger.info("Starting realtime market monitoring...")
                portfolio = await self.get_portfolio()
                await self.realtime_monitor.start(portfolio)
            
            # Set system state
            self.is_running = True
            self.is_trading_enabled = enable_trading
            
            logger.info(f"Trading system started (trading {'enabled' if enable_trading else 'disabled'})")
            
            # Send startup notification
            trading_status = "enabled" if enable_trading else "disabled"
            startup_message = f"""🚀 **LLM Agent Trading System**

All components initialized successfully.

Trading: {trading_status}
Workflow: {self.trading_workflow.get_workflow_type()}
Market: {'🟢 Open' if await self.is_market_open() else '🔴 Closed'}

Ready to trade! 📊"""
            
            await self.message_manager.send_message(startup_message)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start trading system: {e}")
            await self.stop()
            raise
    
    async def stop(self):
        """Stop the trading system gracefully"""
        try:
            if not self.is_running:
                logger.warning("Trading system is not running")
                return
            
            logger.info("Stopping trading system...")
            
            # Set shutdown flag to prevent new workflows
            self.is_shutting_down = True
            self.is_trading_enabled = False
            
            # Stop realtime monitoring
            if self.enable_realtime_monitoring and self.realtime_monitor.is_monitoring:
                logger.info("Stopping realtime market monitoring...")
                await self.realtime_monitor.stop()
            
            # Stop message manager processing (keep transport active for commands)
            logger.info("Stopping message manager processing (keeping transport active for commands)")
            await self.message_manager.stop_processing()
            
            # Stop event system (will finish processing current events)
            await self.event_system.stop()
            
            # Set system state
            self.is_running = False
            self.is_shutting_down = False
            
            logger.info("Trading system stopped (Telegram commands still available)")
            
        except Exception as e:
            logger.error(f"Error stopping trading system: {e}")

    async def _enable_trading(self):
        """Enable trading operations (internal method, called by event handler)"""
        if not self.is_running:
            logger.error("Cannot enable trading: system is not running")
            return
        
        if self.is_trading_enabled:
            logger.debug("Trading is already enabled")
            return
        
        self.is_trading_enabled = True
        logger.info("✅ Trading operations enabled")
    
    async def _disable_trading(self):
        """Disable trading operations (internal method, called by event handler)"""
        if not self.is_trading_enabled:
            logger.debug("Trading is already disabled")
            return
        
        self.is_trading_enabled = False
        logger.info("⏸️ Trading operations disabled")
    
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
            
            logger.warning("Emergency stop completed")
            
        except Exception as e:
            logger.error(f"Error during emergency stop: {e}")
            raise
    
    # === System Control Event Handlers (from Telegram) ===
    
    async def _handle_emergency_stop(self, event: TradingEvent):
        """Handle emergency_stop event from Telegram"""
        try:
            chat_id = event.data.get("chat_id") if event.data else None
            
            # Execute emergency stop
            await self.emergency_stop()
            
            await self.message_manager.send_message(
                "⛔ **EMERGENCY STOP COMPLETE**\n\n"
                "All trading operations have been stopped.",
                chat_id
            )
                
        except Exception as e:
            logger.error(f"Error handling emergency_stop event: {e}")
    
    # === Query Event Handlers (from Telegram) ===
    
    async def _handle_query_status(self, event: TradingEvent):
        """Handle query_status event from Telegram"""
        try:
            chat_id = event.data.get("chat_id") if event.data else None
            
            # Get portfolio data
            portfolio = None
            try:
                portfolio = await self.get_portfolio()
            except Exception as e:
                logger.warning(f"Could not get portfolio for status: {e}")
                await self.message_manager.send_message(
                    f"❌ Error getting portfolio: {e}",
                    chat_id
                )
                return
            
            # Get event system status
            event_status = self.event_system.get_status()
            queue_size = event_status.get('queue_size', 0)
            
            # Get throttle status
            total_throttled = sum(len(events) for events in self.throttled_events.values())
            throttle_details = []
            if total_throttled > 0:
                for trigger, events in self.throttled_events.items():
                    if events:
                        throttle_details.append(f"  • {trigger}: {len(events)} events")
            
            throttle_text = ""
            if total_throttled > 0:
                throttle_text = f"\n⏱️ **Throttled Events**: {total_throttled}\n" + "\n".join(throttle_details)
            
            # Get realtime monitor status
            monitor_status_text = ""
            if self.enable_realtime_monitoring:
                monitor_status = self.realtime_monitor.get_status()
                if monitor_status and isinstance(monitor_status, dict):
                    is_monitoring = monitor_status.get('is_monitoring', False)
                    monitor_status_text = f"\n📡 **Realtime Monitor**: {('✅ Active' if is_monitoring else '❌ Inactive')}"
            
            # Build status text
            status_text = f"""📊 **Trading System Status**

🏃 **Running**: {("✅ Yes" if self.is_running else "❌ No")}
💰 **Trading Enabled**: {("✅ Yes" if self.is_trading_enabled else "❌ No")}
🏪 **Market Open**: {("✅ Yes" if await self.is_market_open() else "❌ No")}
🤖 **Workflow**: {self.trading_workflow.get_workflow_type()}
📋 **Event Queue**: {queue_size} pending{throttle_text}{monitor_status_text}

📈 **Portfolio Summary**:
• Total Equity: ${float(portfolio.equity):,.2f}
• Cash: ${float(portfolio.cash):,.2f}
• Day P&L: ${float(portfolio.day_pnl):,.2f}
• Positions: {len(portfolio.positions)}"""
            
            await self.message_manager.send_message(status_text, chat_id)
                
        except Exception as e:
            logger.error(f"Error handling query_status event: {e}")
    
    async def _handle_query_portfolio(self, event: TradingEvent):
        """Handle query_portfolio event from Telegram"""
        try:
            chat_id = event.data.get("chat_id") if event.data else None
            
            portfolio = await self.get_portfolio()
            
            if not portfolio:
                await self.message_manager.send_message(
                    "❌ Unable to retrieve portfolio",
                    chat_id
                )
                return
            
            # Send formatted portfolio message
            await self.message_manager.send_portfolio_update(portfolio)
                
        except Exception as e:
            logger.error(f"Error handling query_portfolio event: {e}")
    
    async def _handle_query_orders(self, event: TradingEvent):
        """Handle query_orders event from Telegram"""
        try:
            chat_id = event.data.get("chat_id") if event.data else None
            
            orders = await self.get_active_orders()
            
            if not orders:
                await self.message_manager.send_message(
                    "ℹ️ No active orders found",
                    chat_id
                )
                return
            
            orders_text = f"📋 **Active Orders** ({len(orders)}):\n\n"
            
            for order in orders:
                orders_text += f"• {order.symbol} - {order.side.value} {order.quantity} @ {order.order_type.value}\n"
            
            await self.message_manager.send_message(orders_text.strip(), chat_id)
                
        except Exception as e:
            logger.error(f"Error handling query_orders event: {e}")
     
    async def _initialize_scheduled_events(self):
        """
        Initialize self-perpetuating event chains
        
        Publishes initial scheduled events. Each handler will schedule its next occurrence
        after executing, creating self-perpetuating event chains.
        """
        try:
            logger.info("Initializing scheduled events...")
            
            # Parse rebalance time from settings (format: "HH:MM")
            rebalance_hour, rebalance_minute = parse_time_config(settings.rebalance_time)
            
            # Schedule next daily rebalance
            next_rebalance = calculate_next_trading_day_time(
                hour=rebalance_hour, minute=rebalance_minute, timezone=self.timezone
            )
            await self.event_system.publish(
                "trigger_workflow",
                {"trigger": "daily_rebalance"},
                scheduled_time=next_rebalance
            )
            logger.info(f"Next daily rebalance: {next_rebalance} (configured: {settings.rebalance_time} ET)")
            
            # Schedule next EOD analysis
            next_eod = calculate_next_trading_day_time(
                hour=16, minute=5, timezone=self.timezone  # After market close
            )
            await self.event_system.publish("trigger_eod_analysis", scheduled_time=next_eod
            )
            logger.info(f"Next EOD analysis: {next_eod}")
            
            # Schedule next portfolio check (configurable interval during market hours)
            next_check = calculate_next_interval(
                interval_minutes=self.portfolio_check_interval,
                timezone=self.timezone
            )
            await self.event_system.publish("trigger_portfolio_check", scheduled_time=next_check
            )
            logger.info(f"Next portfolio check: {next_check} ({self.portfolio_check_interval}min interval)")
            
            # Schedule next risk check (configurable interval during market hours)
            next_risk = calculate_next_interval(
                interval_minutes=self.risk_check_interval,
                timezone=self.timezone
            )
            await self.event_system.publish("trigger_risk_check", scheduled_time=next_risk
            )
            logger.info(f"Next risk check: {next_risk} ({self.risk_check_interval}min interval)")
            
            logger.info("Scheduled events initialized")
            
        except Exception as e:
            logger.error(f"Error initializing scheduled events: {e}")
    
    
    async def _execute_workflow(self, trigger: str, event: TradingEvent = None):
        """
        Unified workflow execution method
        
        Args:
            trigger: Trigger type identifier (daily_rebalance, realtime_rebalance, manual_analysis)
            event: Optional TradingEvent containing context and historical data
        """
        try:
            if not self.is_trading_enabled:
                logger.info(f"Trading disabled, skipping {trigger}")
                return
            
            if self.is_shutting_down:
                logger.info(f"System shutting down, skipping {trigger}")
                return
            
            logger.info(f"Starting workflow execution: {trigger}")
            
            # Use event.data directly as context (already contains all info)
            context = event.data if (event and event.data) else {}
            
            # Ensure trigger is set
            if "trigger" not in context:
                context["trigger"] = trigger
            
            # Ensure timestamp is set
            if "timestamp" not in context:
                context["timestamp"] = datetime.now(self.timezone).isoformat()
            
            # Execute workflow - all execution logic is in the workflow itself
            await self.trading_workflow.run_workflow(context)
            
            logger.info(f"Workflow execution completed: {trigger}")
            
        except Exception as e:
            logger.error(f"Workflow execution failed ({trigger}): {e}")
            raise
    
    async def _run_risk_checks(self):
        """Run risk management checks (internal method)"""
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
    
    async def _run_eod_analysis(self):
        """Run end-of-day analysis (internal method)"""
        try:
            portfolio = await self.get_portfolio()
            
            # Update daily stats
            self.daily_stats['last_update'] = datetime.now(self.timezone)
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
    
    async def get_portfolio(self) -> Portfolio:
        """Get current portfolio"""
        try:
            portfolio = await self.broker_api.get_portfolio()
            if portfolio is None:
                raise Exception("Failed to get portfolio from broker API")
            self.last_portfolio_update = datetime.now(self.timezone)
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
    
    async def _send_portfolio_alert(self, portfolio: Portfolio):
        """Send portfolio alert (internal method)"""
        try:
            await self.message_manager.send_portfolio_update(portfolio)
        except Exception as e:
            logger.error(f"Error sending portfolio alert: {e}")
    
    def _should_alert_portfolio_change(self, portfolio: Portfolio) -> bool:
        """Check if portfolio change warrants an alert"""
        try:
            # Alert if day P&L exceeds 5% of equity
            if abs(portfolio.day_pnl) > (portfolio.equity * Decimal('0.05')):
                return True
            
            # Alert if any position has unrealized loss > 10%
            for position in portfolio.positions:
                if position.unrealized_pnl_percentage < Decimal('-0.1'):
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking portfolio change: {e}")
            return False
    
    # === Workflow Trigger Event Handlers ===
    
    async def _handle_workflow_trigger(self, event: TradingEvent):
        """
        Unified workflow trigger handler with event throttling and merging
        
        Features:
        - Throttles frequent workflow executions (minimum interval)
        - Merges context from multiple pending events
        - High-priority events bypass throttling
        - Auto-rescheduling based on trigger type
        
        Handles all workflow triggers:
        - daily_rebalance: Auto-reschedules to next trading day
        - realtime_rebalance: One-time execution
        - manual_analysis: One-time execution
        - llm_scheduled: One-time execution (scheduled by LLM agent)
        """
        try:
            # Extract trigger type from event data
            trigger = event.data.get("trigger", "unknown") if event.data else "unknown"
            priority = event.priority if hasattr(event, 'priority') else 0
            
            logger.info(f"Received workflow trigger: {trigger} (priority: {priority})")
            
            # === Event Throttling Logic ===
            # Only throttle specific triggers (e.g., llm_scheduled)
            # High-priority events (priority < 0) bypass throttling
            should_throttle = trigger in self.throttled_triggers and priority >= self.throttle_priority_threshold
            
            if should_throttle:
                current_time = datetime.now(pytz.UTC)
                last_execution = self.last_workflow_execution.get(trigger)
                
                if last_execution:
                    time_since_last = (current_time - last_execution).total_seconds() / 60  # minutes
                    
                    # Check if we're within minimum interval (TOO SOON)
                    if time_since_last < self.min_workflow_interval_minutes:
                        # Too soon! Store event in throttled_events, don't execute
                        if trigger not in self.throttled_events:
                            self.throttled_events[trigger] = []
                        
                        self.throttled_events[trigger].append(event)
                        
                        throttle_msg = (
                            f"⏱️ **事件节流**\n\n"
                            f"触发器: {trigger}\n"
                            f"距上次执行: {time_since_last:.1f}分钟\n"
                            f"最小间隔: {self.min_workflow_interval_minutes}分钟\n"
                            f"已暂存事件数: {len(self.throttled_events[trigger])}\n\n"
                            f"将在达到最小间隔后合并执行"
                        )
                        await self.message_manager.send_message(throttle_msg, "info")
                        
                        logger.info(
                            f"⏱️ Workflow throttling: Last execution {time_since_last:.1f}min ago. "
                            f"Storing event (total throttled: {len(self.throttled_events[trigger])}). "
                            f"Will merge and execute when interval passes."
                        )
                        
                        # Schedule a check event if not already pending
                        if not self.pending_throttle_checks.get(trigger, False):
                            check_time = last_execution + timedelta(minutes=self.min_workflow_interval_minutes)
                            await self.event_system.publish(
                                "trigger_workflow",
                                {
                                    "trigger": trigger,
                                    "throttle_check": True  # Mark as throttle check event
                                },
                                scheduled_time=check_time
                            )
                            self.pending_throttle_checks[trigger] = True
                            logger.info(f"Scheduled throttle check for {trigger} at {check_time.isoformat()}")
                        
                        # Don't execute now
                        return
                    
                    # Time has passed! Check if this is a throttle check event or normal event
                    throttled = self.throttled_events.get(trigger, [])
                    is_check_event = event.data.get("throttle_check", False) if event.data else False
                    
                    if is_check_event:
                        # This is a scheduled check event (no real data, just trigger)
                        if not throttled:
                            # No throttled events, nothing to do
                            logger.info(f"Throttle check for {trigger}: no throttled events found")
                            self.pending_throttle_checks[trigger] = False
                            return
                        
                        # Execute throttled events only
                        logger.info(f"📦 Throttle check triggered: merging {len(throttled)} throttled events")
                        all_events = throttled
                    else:
                        # Normal event that arrived after interval - merge with throttled
                        all_events = throttled + [event]  # Include current event
                    
                    if len(all_events) > 1:
                        merge_msg = (
                            f"📦 **事件合并执行**\n\n"
                            f"触发器: {trigger}\n"
                            f"合并事件数: {len(all_events)}\n"
                            f"距上次执行: {time_since_last:.1f}分钟\n\n"
                            f"正在合并所有暂存事件的数据..."
                        )
                        await self.message_manager.send_message(merge_msg, "info")
                        
                        logger.info(
                            f"📦 Time interval met ({time_since_last:.1f}min >= {self.min_workflow_interval_minutes}min). "
                            f"Merging {len(all_events)} events and executing once."
                        )
                        
                        # Merge data from ALL events (dynamic key merging)
                        merged_data = self._merge_event_data(all_events)
                        event.data = merged_data
                        
                        # Clear throttled events and pending check flag
                        self.throttled_events[trigger] = []
                        self.pending_throttle_checks[trigger] = False
                    else:
                        logger.info(
                            f"✅ Time interval met ({time_since_last:.1f}min >= {self.min_workflow_interval_minutes}min). "
                            f"Executing single event."
                        )
                        self.pending_throttle_checks[trigger] = False
            elif priority < self.throttle_priority_threshold:
                logger.info(f"⚡ High-priority event (priority={priority}), bypassing throttling")
            else:
                logger.debug(f"📋 Trigger '{trigger}' not in throttled list, executing normally")
            
            # === Execute Workflow ===
            await self._execute_workflow(trigger=trigger, event=event)
            
            # Update last execution time
            self.last_workflow_execution[trigger] = datetime.now(pytz.UTC)
            
            # === Auto-reschedule based on trigger type ===
            if self.is_running and trigger == "daily_rebalance":
                # Schedule next daily rebalance (self-perpetuating)
                rebalance_hour, rebalance_minute = parse_time_config(settings.rebalance_time)
                next_rebalance = calculate_next_trading_day_time(
                    hour=rebalance_hour, minute=rebalance_minute, timezone=self.timezone
                )
                await self.event_system.publish(
                    "trigger_workflow",
                    {"trigger": "daily_rebalance"},
                    scheduled_time=next_rebalance
                )
                logger.debug(f"Next daily rebalance scheduled: {next_rebalance}")
            
        except Exception as e:
            logger.error(f"Workflow trigger handling failed: {e}")
    
    def _merge_event_data(self, events: List[TradingEvent]) -> Dict[str, Any]:
        """
        Simply merge data from multiple workflow events
        
        Strategy: For each key, collect all values into a list
        
        Args:
            events: List of events to merge
        
        Returns:
            Merged data dictionary with all values as lists
        """
        if not events:
            return {}
        
        merged = {
            "merged": True,
            "merged_events_count": len(events)
        }
        
        # Collect all keys from all events
        all_keys = set()
        for event in events:
            if event.data:
                all_keys.update(event.data.keys())
        
        # For each key, collect all values into a list
        for key in all_keys:
            values = []
            for event in events:
                if event.data and key in event.data:
                    values.append(event.data[key])
            
            if values:
                # Store as list if multiple values, single value if only one
                merged[key] = values if len(values) > 1 else values[0]
        
        return merged
    
    async def _handle_portfolio_check_trigger(self, event: TradingEvent):
        """Handle portfolio check trigger - schedules next check at configured interval"""
        try:
            logger.debug("Received portfolio check trigger")
            
            if not await self.is_market_open():
                logger.debug("Market closed, skipping portfolio check")
            else:
                portfolio = await self.get_portfolio()
                if self._should_alert_portfolio_change(portfolio):
                    await self._send_portfolio_alert(portfolio)
            
            # Schedule next portfolio check (self-perpetuating)
            if self.is_running:
                next_check = calculate_next_interval(
                    interval_minutes=self.portfolio_check_interval,
                    timezone=self.timezone
                )
                await self.event_system.publish("trigger_portfolio_check", scheduled_time=next_check
                )
                logger.debug(f"Next portfolio check scheduled: {next_check} ({self.portfolio_check_interval}min)")
                
        except Exception as e:
            logger.error(f"Portfolio check trigger handling failed: {e}")
    
    async def _handle_risk_check_trigger(self, event: TradingEvent):
        """Handle risk check trigger - schedules next check at configured interval"""
        try:
            logger.debug("Received risk check trigger")
            
            if await self.is_market_open():
                await self._run_risk_checks()
            
            # Schedule next risk check (self-perpetuating)
            if self.is_running:
                next_check = calculate_next_interval(
                    interval_minutes=self.risk_check_interval,
                    timezone=self.timezone
                )
                await self.event_system.publish("trigger_risk_check", scheduled_time=next_check
                )
                logger.debug(f"Next risk check scheduled: {next_check} ({self.risk_check_interval}min)")
                
        except Exception as e:
            logger.error(f"Risk check trigger handling failed: {e}")
    
    async def _handle_eod_analysis_trigger(self, event: TradingEvent):
        """Handle EOD analysis trigger - schedules next trading day"""
        try:
            logger.info("Received EOD analysis trigger")
            await self._run_eod_analysis()
            
            # Schedule next EOD analysis (self-perpetuating)
            if self.is_running:
                next_eod = calculate_next_trading_day_time(hour=16, minute=5, timezone=self.timezone)
                await self.event_system.publish("trigger_eod_analysis", scheduled_time=next_eod
                )
                logger.debug(f"Next EOD analysis scheduled: {next_eod}")
                
        except Exception as e:
            logger.error(f"EOD analysis trigger handling failed: {e}")
    
    async def _handle_enable_trading(self, event: TradingEvent):
        """Handle enable trading event"""
        try:
            await self._enable_trading()
            await self.message_manager.send_system_alert(
                "✅ **Trading Enabled**\n\nTrading operations are now active.",
                "success"
            )
        except Exception as e:
            logger.error(f"Error handling enable trading event: {e}")
    
    async def _handle_disable_trading(self, event: TradingEvent):
        """Handle disable trading event"""
        try:
            await self._disable_trading()
            reason = event.data.get("reason", "Manual control") if event.data else "Manual control"
            await self.message_manager.send_system_alert(
                f"⏸️ **Trading Disabled**\n\nReason: {reason}\n\nSystem continues monitoring.",
                "warning"
            )
        except Exception as e:
            logger.error(f"Error handling disable trading event: {e}")
    
    
    async def _initialize_daily_stats(self):
        """Initialize daily statistics"""
        try:
            portfolio = await self.get_portfolio()
            self.daily_stats['start_equity'] = portfolio.equity
            self.daily_stats['last_update'] = datetime.now(self.timezone)
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
                await self.event_system.publish(
                    "order_canceled",
                    {"order_id": order_id, "message": f"Order {order_id} cancelled"}
                )
            return success
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            raise
    
    # Handlers that currently may not be used
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
                
                # Disable trading if daily loss exceeds 10%
                if day_pnl_percentage < -0.10:  # 10% daily loss
                    await self.event_system.publish("disable_trading", {"reason": "Daily loss exceeds 10%"})
                    
        except Exception as e:
            logger.error(f"Error handling portfolio risk: {e}") 