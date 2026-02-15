"""
交易系统主协调器

职责：
- 系统生命周期管理（启动、停止）
- 统一的 public API（供 Telegram / FastAPI / Monitor 直接调用）
- 定时任务注册（具体调度能力由 SchedulerMixin 提供）
- Workflow 执行互斥

已拆分的服务：
- SchedulerMixin: APScheduler 管理（增删改查、guard、序列化、持久化）
- RiskManager: 风险管理（止损/止盈/日内限制）
- QueryHandler: 查询处理（状态/组合/订单）
- RealtimeMarketMonitor: 实时监控

架构说明：
- 不使用 EventSystem / pub-sub — 所有调用方直接调用 TradingSystem 的 public 方法
- APScheduler 通过 SchedulerMixin 注入，定时任务回调直接调用 self 的方法
- Workflow 执行通过 asyncio.Lock 保证互斥，通过 _pending_triggers 队列合并短时间内的多次触发
- 节流/去重由 APScheduler 内置机制处理（coalesce + max_instances + replace_existing）
- 任务持久化使用 SQLAlchemyJobStore，重启后恢复用户动态添加的任务
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from config import settings
from src.agents import WorkflowFactory
from src.interfaces.factory import (
    MessageTransportFactory,
    get_broker_api,
    get_market_data_api,
    get_news_api,
)
from src.messaging.message_manager import MessageManager
from src.models.trading_models import Order, OrderSide, OrderType, Portfolio, TimeInForce
from src.services.query_handler import QueryHandler
from src.services.realtime_monitor import RealtimeMarketMonitor
from src.services.risk_manager import RiskManager
from src.services.scheduler_mixin import SchedulerMixin
from src.utils.logging_config import get_logger
from src.utils.time_utils import parse_time_config
from src.utils.timezone import utc_now

logger = get_logger(__name__)


class TradingSystem(SchedulerMixin):

    def __init__(self) -> None:
        # ---- APScheduler (Managed by SchedulerMixin) ----
        self._init_scheduler()

        # ---- API Clients ----
        self.broker_api = get_broker_api()
        self.market_data_api = get_market_data_api()
        self.news_api = get_news_api()

        # ---- Message Manager ----
        transport = MessageTransportFactory.create_message_transport(trading_system=self)
        self.message_manager = MessageManager(transport=transport)

        logger.info("Broker Provider: %s", self.broker_api.get_provider_name())
        logger.info("Market Data Provider: %s", self.market_data_api.get_provider_name())
        logger.info("News Provider: %s", self.news_api.get_provider_name())
        logger.info("Message Transport: %s", self.message_manager.transport.get_transport_name())

        # ---- Workflow ----
        if not WorkflowFactory.is_supported(settings.workflow_type or "llm_portfolio"):
            logger.warning("Unknown workflow type: %s, using default", settings.workflow_type)

        self.trading_workflow = WorkflowFactory.create_workflow(
            message_manager=self.message_manager,
        )
        logger.info("Initialized with %s workflow", self.trading_workflow.get_workflow_type())

        # Inject TradingSystem reference into workflow (for LLM self-scheduling)
        self.trading_workflow._trading_system = self

        # ---- Realtime Monitor ----
        self.realtime_monitor = RealtimeMarketMonitor(trading_system=self)
        self.enable_realtime_monitoring = (
            self.trading_workflow.get_workflow_type()
            in ("llm_portfolio", "black_litterman", "cognitive_arbitrage")
        )

        # ---- Risk Manager ----
        self.risk_enabled = settings.risk_management_enabled
        self.risk_manager = (
            RiskManager(broker_api=self.broker_api, message_manager=self.message_manager)
            if self.risk_enabled
            else None
        )

        # ---- Query Handler ----
        self.query_handler = QueryHandler(
            broker_api=self.broker_api,
            message_manager=self.message_manager,
        )

        # ---- System State ----
        self.is_running: bool = False
        self.is_trading_enabled: bool = False
        self.is_shutting_down: bool = False
        self.last_portfolio_update: Optional[datetime] = None
        self.active_orders: List[Order] = []
        self._started_at: Optional[datetime] = None

        # ---- Workflow 互斥 + 排队 ----
        self._workflow_lock = asyncio.Lock()
        self._pending_triggers: List[Dict[str, Any]] = []  # 排队中的触发

        # ---- 每日统计 ----
        self.daily_stats: Dict[str, Any] = {
            "trades_executed": 0,
            "total_pnl": Decimal("0"),
            "start_equity": None,
            "last_update": None,
        }

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self, enable_trading: bool = True) -> bool:
        """启动交易系统"""
        if self.is_running:
            logger.warning("Trading system is already running")
            return False

        try:
            logger.info("Starting trading system...")

            # Message Manager
            await self.message_manager.start_processing()

            # Daily stats
            await self._initialize_daily_stats()

            # APScheduler
            self._start_scheduler()
            self._register_scheduled_jobs()

            # Realtime Monitor
            if self.enable_realtime_monitoring:
                logger.info("Starting realtime market monitoring...")
                portfolio = await self.get_portfolio()
                await self.realtime_monitor.start(portfolio)

            # System state
            self.is_running = True
            self.is_trading_enabled = enable_trading
            self._started_at = utc_now()

            logger.info("Trading system started (trading %s)", "enabled" if enable_trading else "disabled")

            # Startup notification
            market_status = "🟢 Open" if await self.is_market_open() else "🔴 Closed"
            await self.message_manager.send_message(
                f"🚀 **LLM Agent Trading System**\n\n"
                f"All components initialized successfully.\n\n"
                f"Trading: {'enabled' if enable_trading else 'disabled'}\n"
                f"Workflow: {self.trading_workflow.get_workflow_type()}\n"
                f"Market: {market_status}\n\n"
                f"Ready to trade! 📊"
            )

            return True

        except Exception as e:
            logger.error("Failed to start trading system: %s", e)
            await self.stop()
            raise

    async def stop(self) -> None:
        """优雅停止交易系统"""
        if not self.is_running:
            logger.warning("Trading system is not running")
            return

        try:
            logger.info("Stopping trading system...")
            self.is_shutting_down = True
            self.is_trading_enabled = False

            # APScheduler
            self._stop_scheduler()

            # Realtime Monitor
            if self.enable_realtime_monitoring and self.realtime_monitor.is_monitoring:
                logger.info("Stopping realtime market monitoring...")
                await self.realtime_monitor.stop()

            # Message Manager
            await self.message_manager.stop_processing()

            self.is_running = False
            self.is_shutting_down = False
            logger.info("Trading system stopped")

        except Exception as e:
            logger.error("Error stopping trading system: %s", e)

    # ------------------------------------------------------------------
    # Public API — Workflow 配置与切换
    # ------------------------------------------------------------------

    def get_workflow_config(self) -> Dict[str, Any]:
        """获取当前 workflow 的可编辑配置（透传给 workflow 实例）"""
        return self.trading_workflow.get_config()

    def update_workflow_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        运行时更新 workflow 配置（透传给 workflow 实例）。

        注意：仅修改内存中的值，重启后恢复为 env 中的默认值。
        """
        return self.trading_workflow.update_config(updates)

    async def switch_workflow(self, workflow_type: str) -> Dict[str, Any]:
        """
        切换到不同的 workflow 类型。

        注意：
        - 如果 workflow 正在执行，等待其完成
        - 重新创建 workflow 实例
        - 重新注入 _trading_system 引用
        """
        if not WorkflowFactory.is_supported(workflow_type):
            available = list(WorkflowFactory.get_available_workflows().keys())
            raise ValueError(f"Unknown workflow: {workflow_type}. Available: {available}")

        current_type = self.trading_workflow.get_workflow_type()
        if current_type == workflow_type:
            return {
                "success": True,
                "message": f"Already using {workflow_type}",
                "workflow_type": workflow_type,
            }

        # 等待当前 workflow 执行完毕
        async with self._workflow_lock:
            logger.info("Switching workflow: %s -> %s", current_type, workflow_type)

            # 更新 settings（内存级）
            settings.workflow_type = workflow_type

            # 创建新 workflow
            self.trading_workflow = WorkflowFactory.create_workflow(
                workflow_type=workflow_type,
                message_manager=self.message_manager,
            )
            self.trading_workflow._trading_system = self

            # 更新实时监控配置
            self.enable_realtime_monitoring = (
                workflow_type in ("llm_portfolio", "black_litterman", "cognitive_arbitrage")
            )

            logger.info("Workflow switched to %s", workflow_type)

            await self.message_manager.send_message(
                f"🔄 **Workflow Switched**\n\n"
                f"From: {current_type}\n"
                f"To: {workflow_type}",
                "info",
            )

            return {
                "success": True,
                "message": f"Switched to {workflow_type}",
                "workflow_type": workflow_type,
            }

    # ------------------------------------------------------------------
    # Public API — 交易控制（供 Telegram / FastAPI 直接调用）
    # ------------------------------------------------------------------

    async def enable_trading(self) -> None:
        """启用交易"""
        if not self.is_running:
            logger.error("Cannot enable trading: system is not running")
            return
        if self.is_trading_enabled:
            logger.debug("Trading is already enabled")
            return

        self.is_trading_enabled = True
        logger.info("✅ Trading operations enabled")
        await self.message_manager.send_system_alert(
            "✅ **Trading Enabled**\n\nTrading operations are now active.",
            "success",
        )

    async def disable_trading(self, reason: str = "Manual control") -> None:
        """禁用交易"""
        if not self.is_trading_enabled:
            logger.debug("Trading is already disabled")
            return

        self.is_trading_enabled = False
        logger.info("⏸️ Trading operations disabled: %s", reason)
        await self.message_manager.send_system_alert(
            f"⏸️ **Trading Disabled**\n\nReason: {reason}\n\nSystem continues monitoring.",
            "warning",
        )

    async def emergency_stop(self) -> None:
        """紧急停止 — 取消所有订单并平仓"""
        try:
            logger.warning("EMERGENCY STOP ACTIVATED")
            self.is_trading_enabled = False

            # 取消所有挂单
            orders = await self.get_active_orders()
            for order in orders:
                try:
                    if order.id:
                        await self.cancel_order(order.id)
                except Exception as e:
                    logger.error("Failed to cancel order %s: %s", order.id, e)

            # 平仓
            portfolio = await self.get_portfolio()
            for position in portfolio.positions:
                try:
                    qty = abs(position.quantity)
                    if qty == 0:
                        continue
                    side = "sell" if position.quantity > 0 else "buy"
                    await self._place_market_order(position.symbol, side, qty)
                except Exception as e:
                    logger.error("Failed to close position %s: %s", position.symbol, e)

            logger.warning("Emergency stop completed")
            await self.message_manager.send_message(
                "⛔ **EMERGENCY STOP COMPLETE**\n\n"
                "All trading operations have been stopped.",
            )

        except Exception as e:
            logger.error("Error during emergency stop: %s", e)
            raise

    # ------------------------------------------------------------------
    # Public API — Workflow 触发
    # ------------------------------------------------------------------

    async def trigger_workflow(
        self,
        trigger: str,
        context: Optional[Dict[str, Any]] = None,
        *,
        fire_and_forget: bool = True,
    ) -> None:
        """
        触发一次 workflow 执行。

        Args:
            trigger: 触发类型（daily_rebalance / manual_analysis / realtime / llm_scheduled / ...）
            context: 传递给 workflow 的上下文数据
            fire_and_forget: 是否使用 create_task 异步执行（默认 True，不阻塞调用方）
        """
        if fire_and_forget:
            asyncio.create_task(
                self._guarded_workflow_execution(trigger, context),
                name=f"workflow_{trigger}",
            )
        else:
            await self._guarded_workflow_execution(trigger, context)

    # LLM 自主调度 job_id 前缀
    _LLM_JOB_PREFIX = "llm_scheduled_"

    def schedule_llm_analysis(
        self,
        delay_seconds: float,
        reason: str,
    ) -> Dict[str, Any]:
        """
        LLM 自主调度分析 — 带上限控制。

        使用动态 job_id（基于时间戳），允许同时存在多个待执行的 LLM 调度。
        通过 max_pending_llm_jobs 配置项限制最大待执行数量，防止 LLM 无限制创建任务。

        Args:
            delay_seconds: 延迟秒数
            reason: 调度原因

        Returns:
            dict with "success", "job_id", "message"
        """
        max_pending = settings.max_pending_llm_jobs
        current_count = self.count_jobs_by_prefix(self._LLM_JOB_PREFIX)

        if current_count >= max_pending:
            existing = self.get_jobs_by_prefix(self._LLM_JOB_PREFIX)
            existing_desc = ", ".join(
                f"{j['id']} (next: {j['next_run_time'] or '?'})" for j in existing
            )
            msg = (
                f"LLM 调度已达上限 ({current_count}/{max_pending})，"
                f"拒绝新调度。已有调度: {existing_desc}"
            )
            logger.warning(msg)
            return {"success": False, "job_id": None, "message": msg}

        job_id = f"{self._LLM_JOB_PREFIX}{int(utc_now().timestamp() * 1000)}"
        success = self.add_delayed_job(
            job_id=job_id,
            func=self.trigger_workflow,
            delay_seconds=delay_seconds,
            kwargs={
                "trigger": "llm_scheduled",
                "context": {
                    "reason": reason,
                    "scheduled_by": "llm_agent",
                    "job_id": job_id,
                },
                "fire_and_forget": False,
            },
        )

        if success:
            return {
                "success": True,
                "job_id": job_id,
                "message": f"已安排 {delay_seconds / 3600:.1f} 小时后的分析 (job: {job_id})",
            }
        else:
            return {"success": False, "job_id": None, "message": "添加调度任务失败"}

    async def _guarded_workflow_execution(
        self,
        trigger: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Workflow 执行的完整守卫逻辑：前置检查 → 排队 → 互斥锁 → 执行 → 消费队列

        当 workflow 正在运行时，后续触发不会丢弃，而是放入 _pending_triggers 队列。
        当前 workflow 执行完毕后，会自动消费队列中的所有待处理触发，
        将它们的 context 合并后执行一次 workflow（避免短时间内重复执行）。

        节流/去重说明：
        - 定时任务（cron/interval）：由 APScheduler 的 coalesce=True + max_instances=1 处理
        - LLM 自主调度：动态 job_id + max_pending_llm_jobs 上限控制
        - 实时触发（realtime / manual）：通过 _pending_triggers 排队合并
        """

        if not self.is_trading_enabled:
            logger.info("Trading disabled, skipping %s", trigger)
            return

        if self.is_shutting_down:
            logger.info("System shutting down, skipping %s", trigger)
            return

        # 如果 workflow 正在运行，排队而不是丢弃
        if self._workflow_lock.locked():
            entry = {"trigger": trigger, "context": context, "queued_at": utc_now().isoformat()}
            self._pending_triggers.append(entry)
            logger.info("Workflow busy, queued trigger: %s (queue size: %d)", trigger, len(self._pending_triggers))
            return

        async with self._workflow_lock:
            # 执行当前触发
            await self._execute_workflow_once(trigger, context)

            # 消费队列：合并所有 pending triggers 并执行一次
            await self._drain_pending_triggers()

    async def _execute_workflow_once(
        self,
        trigger: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """执行一次 workflow（不含锁，由调用方保证互斥）"""
        try:
            logger.info("Starting workflow execution: %s", trigger)

            ctx = dict(context) if context else {}
            ctx.setdefault("trigger", trigger)
            ctx.setdefault("timestamp", utc_now().isoformat())

            await self.trading_workflow.run_workflow(ctx)

            logger.info("Workflow execution completed: %s", trigger)

        except Exception as e:
            logger.error("Workflow execution failed (%s): %s", trigger, e, exc_info=True)

    async def _drain_pending_triggers(self) -> None:
        """
        消费 _pending_triggers 队列。

        将队列中的所有 trigger 合并为一次 workflow 执行：
        - trigger 设为 "merged"
        - context 包含 merged_triggers 列表（每个元素含原始 trigger + context）
        - 如果队列中只有一个，则直接使用其原始 trigger 和 context

        必须在持有 _workflow_lock 的情况下调用。
        """
        if not self._pending_triggers:
            return

        # 一次性取出所有 pending
        pending = self._pending_triggers[:]
        self._pending_triggers.clear()

        logger.info("Draining %d pending triggers", len(pending))

        if len(pending) == 1:
            # 单个 pending，直接执行，不包装
            entry = pending[0]
            await self._execute_workflow_once(entry["trigger"], entry.get("context"))
        else:
            # 多个 pending，合并为一次执行
            merged_ctx: Dict[str, Any] = {
                "trigger": "merged",
                "merged_triggers": [
                    {
                        "trigger": e["trigger"],
                        "context": e.get("context"),
                        "queued_at": e.get("queued_at"),
                    }
                    for e in pending
                ],
                "merged_count": len(pending),
            }
            await self._execute_workflow_once("merged", merged_ctx)

        # 递归检查：执行期间可能又有新的 pending
        if self._pending_triggers:
            await self._drain_pending_triggers()

    # ------------------------------------------------------------------
    # Public API — 查询（供 Telegram / FastAPI 调用）
    # ------------------------------------------------------------------

    async def handle_query_status(self) -> None:
        """查询系统状态（结果通过 message_manager 发送）"""
        try:
            system_state = self.get_system_state()

            try:
                system_state["market_open"] = await self.is_market_open()
            except Exception:
                pass

            try:
                system_state["portfolio"] = await self.get_portfolio()
            except Exception:
                pass

            await self.query_handler.handle_status_query(system_state)
        except Exception as e:
            logger.error("Error handling status query: %s", e)

    async def handle_query_portfolio(self) -> None:
        """查询投资组合（结果通过 message_manager 发送）"""
        try:
            await self.query_handler.handle_portfolio_query()
        except Exception as e:
            logger.error("Error handling portfolio query: %s", e)

    async def handle_query_orders(self, status: str = "open") -> None:
        """查询订单（结果通过 message_manager 发送）"""
        try:
            await self.query_handler.handle_orders_query(status=status)
        except Exception as e:
            logger.error("Error handling orders query: %s", e)

    # ------------------------------------------------------------------
    # Public API — 数据获取
    # ------------------------------------------------------------------

    async def get_portfolio(self) -> Portfolio:
        """获取当前投资组合"""
        try:
            portfolio = await self.broker_api.get_portfolio()
            if portfolio is None:
                raise RuntimeError("Failed to get portfolio from broker API")
            self.last_portfolio_update = utc_now()
            return portfolio
        except Exception as e:
            logger.error("Error getting portfolio: %s", e)
            raise

    async def get_active_orders(self) -> List[Order]:
        """获取活跃订单"""
        try:
            orders = await self.broker_api.get_orders(status="open")
            self.active_orders = orders
            return orders
        except Exception as e:
            logger.error("Error getting active orders: %s", e)
            raise

    async def is_market_open(self) -> bool:
        """检查市场是否开放（async，通过 broker API 查询）"""
        try:
            return await self.broker_api.is_market_open()
        except Exception as e:
            logger.error("Error checking market status: %s", e)
            return False

    async def cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        try:
            success = await self.broker_api.cancel_order(order_id)
            if success:
                logger.info("Order %s cancelled", order_id)
            return success
        except Exception as e:
            logger.error("Error cancelling order %s: %s", order_id, e)
            raise

    # ------------------------------------------------------------------
    # System State（供 API 层使用）
    # ------------------------------------------------------------------

    def get_system_state(self) -> Dict[str, Any]:
        """获取完整的系统状态"""
        uptime = (utc_now() - self._started_at).total_seconds() if self._started_at else 0

        scheduler_status = self.get_scheduler_status()

        state: Dict[str, Any] = {
            "is_running": self.is_running,
            "is_trading_enabled": self.is_trading_enabled,
            "workflow_type": self.trading_workflow.get_workflow_type(),
            "workflow_locked": self._workflow_lock.locked(),
            "scheduler_jobs": scheduler_status.get("total_jobs", 0),
            "uptime_seconds": uptime,
        }

        # 实时监控
        if self.enable_realtime_monitoring:
            monitor_status = self.realtime_monitor.get_status()
            if isinstance(monitor_status, dict):
                state["realtime_monitor_active"] = monitor_status.get("is_monitoring", False)
                state["realtime_monitor"] = monitor_status
        else:
            state["realtime_monitor_active"] = False

        # 调度器详情
        state["scheduler"] = scheduler_status

        # 风控
        state["risk_events"] = (
            getattr(self.risk_manager, "risk_events", []) if self.risk_manager else []
        )

        # 每日统计
        state["daily_stats"] = {
            k: (float(v) if isinstance(v, Decimal) else v)
            for k, v in self.daily_stats.items()
        }

        return state

    # ------------------------------------------------------------------
    # Internal — 定时任务注册与回调
    # ------------------------------------------------------------------

    def _register_scheduled_jobs(self) -> None:
        """注册所有内置定时任务"""

        # 1. Daily rebalance
        rebalance_h, rebalance_m = parse_time_config(settings.rebalance_time)
        self.add_cron_job(
            job_id="daily_rebalance",
            func=self._scheduled_trigger_workflow,
            hour=rebalance_h,
            minute=rebalance_m,
            require_trading_day=True,
            kwargs={"trigger": "daily_rebalance"},
        )
        logger.info("Scheduled daily rebalance: %02d:%02d", rebalance_h, rebalance_m)

        # 2. EOD analysis
        eod_h, eod_m = parse_time_config(settings.eod_analysis_time)
        self.add_cron_job(
            job_id="eod_analysis",
            func=self._run_eod_analysis,
            hour=eod_h,
            minute=eod_m,
            require_trading_day=True,
        )
        logger.info("Scheduled EOD analysis: %02d:%02d", eod_h, eod_m)

        # 3. Portfolio check (interval, market hours only)
        self.add_interval_job(
            job_id="portfolio_check",
            func=self._scheduled_portfolio_check,
            minutes=settings.portfolio_check_interval,
            require_market_open=True,
        )
        logger.info("Scheduled portfolio check: every %dmin (market hours)", settings.portfolio_check_interval)

        # 4. Risk check (interval, market hours only)
        if self.risk_enabled:
            self.add_interval_job(
                job_id="risk_check",
                func=self._scheduled_risk_check,
                minutes=settings.risk_check_interval,
                require_market_open=True,
            )
            logger.info("Scheduled risk check: every %dmin (market hours)", settings.risk_check_interval)

    async def _scheduled_trigger_workflow(self, trigger: str = "unknown", **extra_context: Any) -> None:
        """APScheduler 回调：触发 workflow"""
        await self.trigger_workflow(trigger=trigger, context=extra_context or None, fire_and_forget=False)

    async def _scheduled_portfolio_check(self) -> None:
        """APScheduler 回调：组合检查"""
        try:
            portfolio = await self.get_portfolio()
            if self._should_alert_portfolio_change(portfolio):
                await self._send_portfolio_alert(portfolio)
        except Exception as e:
            logger.error("Portfolio check failed: %s", e)

    async def _scheduled_risk_check(self) -> None:
        """APScheduler 回调：风控检查"""
        try:
            await self._run_risk_checks()
        except Exception as e:
            logger.error("Risk check failed: %s", e)

    # ------------------------------------------------------------------
    # Internal — 业务逻辑
    # ------------------------------------------------------------------

    async def _run_risk_checks(self) -> None:
        """执行风控检查"""
        if not self.risk_enabled or not self.risk_manager:
            return

        try:
            portfolio = await self.get_portfolio()
            results = await self.risk_manager.run_risk_checks(portfolio)

            if results.get("daily_limit_breached"):
                await self.disable_trading(reason="Daily loss limit breached")

        except Exception as e:
            logger.error("Error in risk checks: %s", e)

    async def _run_eod_analysis(self) -> None:
        """收盘分析"""
        try:
            portfolio = await self.get_portfolio()

            now = utc_now()
            self.daily_stats["last_update"] = now
            if self.daily_stats["start_equity"] is None:
                self.daily_stats["start_equity"] = portfolio.equity

            day_pnl = portfolio.equity - self.daily_stats["start_equity"]
            daily_return = (
                day_pnl / self.daily_stats["start_equity"]
                if self.daily_stats["start_equity"]
                else Decimal("0")
            )

            summary = (
                f"📊 **End of Day Summary**\n\n"
                f"- Equity: ${portfolio.equity:,.2f}\n"
                f"- Day P&L: ${day_pnl:,.2f}\n"
                f"- Daily Return: {daily_return:.2%}\n"
                f"- Trades Executed: {self.daily_stats['trades_executed']}\n"
                f"- Active Positions: {len(portfolio.positions)}"
            )
            await self.message_manager.send_message(summary)

            # Reset for next day
            self.daily_stats["trades_executed"] = 0
            self.daily_stats["start_equity"] = portfolio.equity
            logger.info("End-of-day analysis completed")

        except Exception as e:
            logger.error("Error in EOD analysis: %s", e)

    async def _initialize_daily_stats(self) -> None:
        """初始化每日统计"""
        try:
            portfolio = await self.get_portfolio()
            self.daily_stats["start_equity"] = portfolio.equity
            self.daily_stats["last_update"] = utc_now()
        except Exception as e:
            logger.error("Error initializing daily stats: %s", e)

    async def _place_market_order(self, symbol: str, side: str, quantity: Decimal) -> Optional[Order]:
        """下市价单"""
        try:
            order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
            order = Order(
                symbol=symbol,
                side=order_side,
                order_type=OrderType.MARKET,
                quantity=quantity,
                time_in_force=TimeInForce.DAY,
            )
            order_id = await self.broker_api.submit_order(order)
            if order_id:
                return await self.broker_api.get_order(order_id)
            return None
        except Exception as e:
            logger.error("Error placing market order: %s", e)
            raise

    async def _send_portfolio_alert(self, portfolio: Portfolio) -> None:
        """发送组合告警"""
        try:
            await self.message_manager.send_portfolio_update(portfolio)
        except Exception as e:
            logger.error("Error sending portfolio alert: %s", e)

    def _should_alert_portfolio_change(self, portfolio: Portfolio) -> bool:
        """判断组合变动是否需要告警"""
        try:
            pnl_threshold = Decimal(str(settings.portfolio_pnl_alert_threshold))
            if abs(portfolio.day_pnl) > (portfolio.equity * pnl_threshold):
                return True

            loss_threshold = Decimal(str(settings.position_loss_alert_threshold))
            for position in portfolio.positions:
                if position.unrealized_pnl_percentage < -loss_threshold:
                    return True

            return False
        except Exception as e:
            logger.error("Error checking portfolio change: %s", e)
            return False
