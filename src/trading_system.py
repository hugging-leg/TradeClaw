"""
交易系统主协调器

职责：
- 系统生命周期管理（启动、停止）
- 事件处理协调
- 调度管理（委托给 TradingScheduler）

已拆分的服务：
- RiskManager: 风险管理（止损/止盈/日内限制）
- QueryHandler: 查询处理（状态/组合/订单）
- RealtimeMarketMonitor: 实时监控
- TradingScheduler: 定时任务调度 (APScheduler)
"""

from src.utils.logging_config import get_logger
from typing import Dict, List, Any
from datetime import datetime
from decimal import Decimal

from src.messaging.message_manager import MessageManager
from src.interfaces.factory import get_broker_api, get_market_data_api, get_news_api, MessageTransportFactory
from src.events.event_system import event_system
# 导入 agents 模块（触发所有 workflow 的自动注册）
from src.agents import WorkflowFactory
from src.services.realtime_monitor import RealtimeMarketMonitor
from src.services.risk_manager import RiskManager
from src.services.query_handler import QueryHandler
from src.services.scheduler import TradingScheduler
from src.models.trading_models import (
    Order, Portfolio, TradingEvent, OrderSide, OrderType,
    TimeInForce
)
from src.utils.time_utils import parse_time_config
from src.utils.timezone import utc_now
from config import settings


logger = get_logger(__name__)


class TradingSystem:
    """Main trading system orchestrator"""

    def __init__(self):
        # Initialize API clients using factories
        self.broker_api = get_broker_api()
        self.market_data_api = get_market_data_api()
        self.news_api = get_news_api()

        # Initialize event system first (needed by message transport)
        self.event_system = event_system

        # Initialize message manager with transport
        # Transport 会在 MessageManager.start_processing() 中自动初始化
        transport = MessageTransportFactory.create_message_transport(event_system=self.event_system)
        self.message_manager = MessageManager(transport=transport)

        # Log provider information
        logger.info(f"Broker Provider: {self.broker_api.get_provider_name()}")
        logger.info(f"Market Data Provider: {self.market_data_api.get_provider_name()}")
        logger.info(f"News Provider: {self.news_api.get_provider_name()}")
        logger.info(f"Message Transport: {self.message_manager.transport.get_transport_name()}")

        # Validate workflow configuration
        if not WorkflowFactory.is_supported(settings.workflow_type or 'llm_portfolio'):
            logger.warning(f"Unknown workflow type: {settings.workflow_type}, using default")

        # Initialize core components
        self.trading_workflow = WorkflowFactory.create_workflow(
            message_manager=self.message_manager
        )
        self.realtime_monitor = RealtimeMarketMonitor(trading_system=self)

        # 初始化 APScheduler 调度器
        self.scheduler = TradingScheduler(
            timezone=settings.trading_timezone,
            exchange=settings.exchange
        )

        # 初始化服务（拆分的功能模块）
        self.risk_enabled = settings.risk_management_enabled
        self.risk_manager = RiskManager(
            broker_api=self.broker_api,
            message_manager=self.message_manager
        ) if self.risk_enabled else None
        self.query_handler = QueryHandler(
            broker_api=self.broker_api,
            message_manager=self.message_manager
        )

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
        self.min_workflow_interval_minutes = settings.min_workflow_interval_minutes
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

            # Start message manager processing
            await self.message_manager.start_processing()

            # Initialize daily stats
            await self._initialize_daily_stats()

            # Start APScheduler and register scheduled jobs
            await self.scheduler.start()
            self._register_scheduled_jobs()

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

            # Stop APScheduler
            await self.scheduler.stop()

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

    def _register_scheduled_jobs(self):
        """
        Register all scheduled jobs with APScheduler

        所有定时任务通过 TradingScheduler 管理，不再使用自制调度。
        """
        # Parse rebalance time from settings (format: "HH:MM")
        rebalance_hour, rebalance_minute = parse_time_config(settings.rebalance_time)

        # 1. Daily rebalance - Cron job, only on trading days
        self.scheduler.add_cron_job(
            job_id='daily_rebalance',
            func=self._scheduled_daily_rebalance,
            hour=rebalance_hour,
            minute=rebalance_minute,
            require_trading_day=True,
            require_market_open=False
        )
        logger.info(f"Scheduled daily rebalance: {rebalance_hour:02d}:{rebalance_minute:02d} ET")

        # 2. EOD analysis - Cron job, after market close
        eod_hour, eod_minute = parse_time_config(settings.eod_analysis_time)
        self.scheduler.add_cron_job(
            job_id='eod_analysis',
            func=self._scheduled_eod_analysis,
            hour=eod_hour,
            minute=eod_minute,
            require_trading_day=True,
            require_market_open=False
        )
        logger.info(f"Scheduled EOD analysis: {eod_hour:02d}:{eod_minute:02d} ET")

        # 3. Portfolio check - Interval job, during market hours
        self.scheduler.add_interval_job(
            job_id='portfolio_check',
            func=self._scheduled_portfolio_check,
            minutes=self.portfolio_check_interval,
            require_market_open=True
        )
        logger.info(f"Scheduled portfolio check: every {self.portfolio_check_interval}min (market hours)")

        # 4. Risk check - Interval job, during market hours
        if self.risk_enabled:
            self.scheduler.add_interval_job(
                job_id='risk_check',
                func=self._scheduled_risk_check,
                minutes=self.risk_check_interval,
                require_market_open=True
            )
            logger.info(f"Scheduled risk check: every {self.risk_check_interval}min (market hours)")

    # === Scheduled Job Callbacks (called by APScheduler) ===

    async def _scheduled_daily_rebalance(self):
        """APScheduler callback: daily rebalance"""
        await self.event_system.publish(
            "trigger_workflow",
            {"trigger": "daily_rebalance"}
        )

    async def _scheduled_eod_analysis(self):
        """APScheduler callback: EOD analysis"""
        await self._run_eod_analysis()

    async def _scheduled_portfolio_check(self):
        """APScheduler callback: portfolio check"""
        try:
            if not await self.is_market_open():
                logger.debug("Market closed, skipping portfolio check")
                return

            portfolio = await self.get_portfolio()
            if self._should_alert_portfolio_change(portfolio):
                await self._send_portfolio_alert(portfolio)
        except Exception as e:
            logger.error(f"Portfolio check failed: {e}")

    async def _scheduled_risk_check(self):
        """APScheduler callback: risk check"""
        try:
            if await self.is_market_open():
                await self._run_risk_checks()
        except Exception as e:
            logger.error(f"Risk check failed: {e}")

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
        """Handle query_status event — delegate to QueryHandler"""
        try:
            # 构建系统状态上下文，传递给 QueryHandler
            system_state: Dict[str, Any] = {
                'is_running': self.is_running,
                'is_trading_enabled': self.is_trading_enabled,
                'workflow_type': self.trading_workflow.get_workflow_type(),
            }

            # 事件队列状态
            event_status = self.event_system.get_status()
            system_state['event_queue_size'] = event_status.get('queue_size', 0)

            # 调度器状态
            scheduler_status = self.scheduler.get_status()
            system_state['scheduler_jobs'] = scheduler_status.get('total_jobs', 0)

            # 实时监控状态
            if self.enable_realtime_monitoring:
                monitor_status = self.realtime_monitor.get_status()
                if monitor_status and isinstance(monitor_status, dict):
                    system_state['realtime_monitor_active'] = monitor_status.get('is_monitoring', False)

            # 预获取市场状态
            try:
                system_state['market_open'] = await self.is_market_open()
            except Exception:
                pass

            # 预获取组合信息
            try:
                system_state['portfolio'] = await self.get_portfolio()
            except Exception:
                pass

            await self.query_handler.handle_status_query(system_state)

        except Exception as e:
            logger.error(f"Error handling query_status event: {e}")

    async def _handle_query_portfolio(self, event: TradingEvent):
        """Handle query_portfolio event — delegate to QueryHandler"""
        try:
            await self.query_handler.handle_portfolio_query()
        except Exception as e:
            logger.error(f"Error handling query_portfolio event: {e}")

    async def _handle_query_orders(self, event: TradingEvent):
        """Handle query_orders event — delegate to QueryHandler"""
        try:
            status = event.data.get("status", "open") if event.data else "open"
            await self.query_handler.handle_orders_query(status=status)
        except Exception as e:
            logger.error(f"Error handling query_orders event: {e}")

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

            # Ensure timestamp is set (always UTC)
            if "timestamp" not in context:
                context["timestamp"] = utc_now().isoformat()

            # Execute workflow - all execution logic is in the workflow itself
            await self.trading_workflow.run_workflow(context)

            logger.info(f"Workflow execution completed: {trigger}")

        except Exception as e:
            logger.error(f"Workflow execution failed ({trigger}): {e}")
            raise

    async def _run_risk_checks(self):
        """Run risk management checks (委托给 RiskManager)"""
        if not self.risk_enabled or not self.risk_manager:
            logger.debug("风控模块未启用，跳过检查")
            return

        try:
            portfolio = await self.get_portfolio()
            results = await self.risk_manager.run_risk_checks(portfolio)

            # 如果触发日内限制，禁用交易
            if results.get("daily_limit_breached"):
                await self.event_system.publish(
                    "disable_trading",
                    {"reason": "Daily loss limit breached"}
                )

        except Exception as e:
            logger.error(f"Error in risk checks: {e}")

    async def _run_eod_analysis(self):
        """Run end-of-day analysis (internal method)"""
        try:
            portfolio = await self.get_portfolio()

            # Update daily stats
            now = utc_now()
            self.daily_stats['last_update'] = now
            if self.daily_stats['start_equity'] is None:
                self.daily_stats['start_equity'] = portfolio.equity

            # Calculate daily performance
            day_pnl = portfolio.equity - self.daily_stats['start_equity']
            daily_return = day_pnl / self.daily_stats['start_equity']

            # Create summary report
            summary = f"""
End of Day Summary:
- Equity: ${portfolio.equity:,.2f}
- Day P&L: ${day_pnl:,.2f}
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
            self.last_portfolio_update = utc_now()
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
            # Alert if day P&L exceeds configured threshold of equity
            pnl_threshold = Decimal(str(settings.portfolio_pnl_alert_threshold))
            if abs(portfolio.day_pnl) > (portfolio.equity * pnl_threshold):
                return True

            # Alert if any position has unrealized loss exceeding configured threshold
            loss_threshold = Decimal(str(settings.position_loss_alert_threshold))
            for position in portfolio.positions:
                if position.unrealized_pnl_percentage < -loss_threshold:
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

        Handles all workflow triggers:
        - daily_rebalance: Scheduled by APScheduler
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
                current_time = utc_now()
                last_execution = self.last_workflow_execution.get(trigger)

                if last_execution:
                    time_since_last = (current_time - last_execution).total_seconds() / 60  # minutes

                    # Check if we're within minimum interval (TOO SOON)
                    if time_since_last < self.min_workflow_interval_minutes:
                        # Too soon! Store event in throttled_events, don't execute
                        if trigger not in self.throttled_events:
                            self.throttled_events[trigger] = []

                        self.throttled_events[trigger].append(event)

                        # Limit throttled events list size
                        if len(self.throttled_events[trigger]) > 50:
                            self.throttled_events[trigger] = self.throttled_events[trigger][-50:]

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

                        # Schedule a delayed check via APScheduler if not already pending
                        if not self.pending_throttle_checks.get(trigger, False):
                            remaining_seconds = (self.min_workflow_interval_minutes - time_since_last) * 60
                            self.scheduler.add_delayed_job(
                                job_id=f'throttle_check_{trigger}',
                                func=self._execute_throttled_events,
                                delay_seconds=max(remaining_seconds, 1),
                                kwargs={'trigger': trigger}
                            )
                            self.pending_throttle_checks[trigger] = True
                            logger.info(f"Scheduled throttle check for {trigger} in {remaining_seconds:.0f}s")

                        # Don't execute now
                        return

                    # Time has passed! Check if there are throttled events to merge
                    throttled = self.throttled_events.get(trigger, [])

                    if throttled:
                        all_events = throttled + [event]
                        logger.info(f"📦 Merging {len(all_events)} events for {trigger}")

                        merge_msg = (
                            f"📦 **事件合并执行**\n\n"
                            f"触发器: {trigger}\n"
                            f"合并事件数: {len(all_events)}\n"
                            f"距上次执行: {time_since_last:.1f}分钟\n\n"
                            f"正在合并所有暂存事件的数据..."
                        )
                        await self.message_manager.send_message(merge_msg, "info")

                        # Merge data from ALL events
                        merged_data = self._merge_event_data(all_events)
                        event.data = merged_data

                        # Clear throttled events and pending check flag
                        self.throttled_events[trigger] = []
                        self.pending_throttle_checks[trigger] = False
            elif priority < self.throttle_priority_threshold:
                logger.info(f"⚡ High-priority event (priority={priority}), bypassing throttling")
            else:
                logger.debug(f"📋 Trigger '{trigger}' not in throttled list, executing normally")

            # === Execute Workflow ===
            await self._execute_workflow(trigger=trigger, event=event)

            # Update last execution time
            self.last_workflow_execution[trigger] = utc_now()

        except Exception as e:
            logger.error(f"Workflow trigger handling failed: {e}")

    async def _execute_throttled_events(self, trigger: str):
        """
        Execute throttled events (called by APScheduler delayed job)

        Args:
            trigger: The trigger type to check
        """
        try:
            self.pending_throttle_checks[trigger] = False
            throttled = self.throttled_events.get(trigger, [])

            if not throttled:
                logger.info(f"Throttle check for {trigger}: no throttled events found")
                return

            logger.info(f"📦 Throttle check triggered: merging {len(throttled)} throttled events for {trigger}")

            # Create a merged event
            merged_data = self._merge_event_data(throttled)
            merged_data["trigger"] = trigger

            merged_event = TradingEvent(
                event_type="trigger_workflow",
                data=merged_data
            )

            # Clear throttled events
            self.throttled_events[trigger] = []

            # Execute
            await self._execute_workflow(trigger=trigger, event=merged_event)
            self.last_workflow_execution[trigger] = utc_now()

        except Exception as e:
            logger.error(f"Error executing throttled events for {trigger}: {e}")

    def _merge_event_data(self, events: List[TradingEvent]) -> Dict[str, Any]:
        """
        Merge data from multiple workflow events

        Strategy: For each key, always collect values into a list for consistency

        Args:
            events: List of events to merge

        Returns:
            Merged data dictionary
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

        # For each key, always collect values as a list
        for key in all_keys:
            values = []
            for event in events:
                if event.data and key in event.data:
                    values.append(event.data[key])

            if values:
                # Always store as list for consistency
                merged[key] = values

        return merged

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
            self.daily_stats['last_update'] = utc_now()
        except Exception as e:
            logger.error(f"Error initializing daily stats: {e}")

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

    # 注意: 止损/止盈/组合风险处理已移至 RiskManager
    # 参见: src/services/risk_manager.py
