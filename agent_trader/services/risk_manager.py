"""
风险管理服务

职责：
- 基于可配置规则链执行止损/止盈检测
- 组合风险监控
- 日内损失限制
- 仓位集中度检查
- 触发 LLM 分析（规则链中的 llm_analyze 动作）

设计：
- 独立于 TradingSystem，可单独测试
- 通过依赖注入获取 broker_api 和 message_manager
- 规则从 YAML 配置加载，支持运行时动态修改
- LLM 规则和硬编码规则共存，按优先级执行
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set
from decimal import Decimal

from agent_trader.config.risk_rules import (
    RiskRule,
    RuleAction,
    RuleType,
    get_risk_rules_manager,
)
from agent_trader.interfaces.broker_api import BrokerAPI
from agent_trader.messaging.message_manager import MessageManager
from agent_trader.models.trading_models import (
    Order,
    OrderSide,
    OrderType,
    Portfolio,
    Position,
    TimeInForce,
)
from agent_trader.utils.logging_config import get_logger
from agent_trader.utils.timezone import utc_now

logger = get_logger(__name__)


class RiskManager:
    """
    风险管理服务

    功能：
    - 基于可配置规则链执行止损/止盈
    - 支持 LLM 分析触发（与硬编码规则共存）
    - 日内损失限制
    - 仓位集中度检查
    - 风险报告生成
    """

    def __init__(
        self,
        broker_api: BrokerAPI,
        message_manager: MessageManager,
        # 保留旧参数签名以兼容现有调用
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
        daily_loss_limit_pct: Optional[float] = None,
        max_position_concentration: Optional[float] = None,
    ):
        self.broker_api = broker_api
        self.message_manager = message_manager

        # 规则管理器
        self._rules_mgr = get_risk_rules_manager()

        # LLM 分析回调（由 TradingSystem 注入）
        self._llm_trigger_callback: Optional[
            Callable[..., Coroutine[Any, Any, None]]
        ] = None

        # 冷却追踪：{(rule_name, symbol): last_triggered_time}
        self._cooldowns: Dict[tuple, datetime] = {}

        # 已触发 LLM 分析的 symbol 集合（同一次 check 内去重）
        self._llm_triggered_symbols: Set[str] = set()

        # 统计（限制最大事件数避免内存泄漏）
        self.risk_events: List[Dict[str, Any]] = []
        self._max_risk_events = 200
        self.last_check: Optional[datetime] = None

        # 向后兼容：暴露旧属性（从规则中读取）
        self.stop_loss_pct = self._get_threshold_from_rules(
            RuleType.HARD_STOP_LOSS, 0.05
        )
        self.take_profit_pct = self._get_threshold_from_rules(
            RuleType.HARD_TAKE_PROFIT, 0.15
        )
        self.daily_loss_limit_pct = self._get_threshold_from_rules(
            RuleType.DAILY_LOSS_LIMIT, 0.10
        )
        self.max_position_concentration = self._get_threshold_from_rules(
            RuleType.CONCENTRATION_LIMIT, 0.25
        )

        logger.info(
            "RiskManager initialized with %d rules (%d enabled)",
            len(self._rules_mgr.get_rules()),
            len(self._rules_mgr.get_enabled_rules()),
        )

    def _get_threshold_from_rules(
        self, rule_type: RuleType, default: float
    ) -> float:
        """从规则中获取第一个匹配类型的阈值"""
        for rule in self._rules_mgr.get_enabled_rules():
            if rule.type == rule_type:
                return rule.threshold
        return default

    def set_llm_trigger_callback(
        self,
        callback: Callable[..., Coroutine[Any, Any, None]],
    ) -> None:
        """设置 LLM 分析触发回调"""
        self._llm_trigger_callback = callback

    def _is_cooled_down(self, rule: RiskRule, symbol: str) -> bool:
        """检查规则冷却"""
        if rule.cooldown_seconds <= 0:
            return True
        key = (rule.name, symbol)
        last = self._cooldowns.get(key)
        if last is None:
            return True
        elapsed = (utc_now() - last).total_seconds()
        return elapsed >= rule.cooldown_seconds

    def _mark_triggered(self, rule: RiskRule, symbol: str) -> None:
        """标记规则已触发（用于冷却）"""
        if rule.cooldown_seconds > 0:
            self._cooldowns[(rule.name, symbol)] = utc_now()

    def _rule_applies_to_symbol(self, rule: RiskRule, symbol: str) -> bool:
        """检查规则是否适用于指定股票"""
        if rule.symbols is None:
            return True
        return symbol in rule.symbols

    # ------------------------------------------------------------------
    # 主检查逻辑
    # ------------------------------------------------------------------

    async def run_risk_checks(self, portfolio: Portfolio) -> Dict[str, Any]:
        """
        执行全面风险检查（基于可配置规则链）

        Args:
            portfolio: 当前组合

        Returns:
            风险检查结果
        """
        self.last_check = utc_now()
        self._llm_triggered_symbols.clear()

        results: Dict[str, Any] = {
            "timestamp": self.last_check.isoformat(),
            "stop_loss_triggered": [],
            "take_profit_triggered": [],
            "llm_analysis_triggered": [],
            "daily_limit_breached": False,
            "concentration_warnings": [],
            "actions_taken": [],
            "rules_evaluated": 0,
        }

        try:
            enabled_rules = self._rules_mgr.get_enabled_rules()
            results["rules_evaluated"] = len(enabled_rules)

            # 已平仓的 symbol（同一次 check 内跳过）
            closed_symbols: Set[str] = set()

            for rule in enabled_rules:
                # ---- 组合级规则 ----
                if rule.type == RuleType.DAILY_LOSS_LIMIT:
                    await self._check_daily_loss(rule, portfolio, results)
                    continue

                # ---- 仓位级规则 ----
                for position in portfolio.positions:
                    if position.quantity == 0:
                        continue
                    symbol = position.symbol
                    if symbol in closed_symbols:
                        continue
                    if not self._rule_applies_to_symbol(rule, symbol):
                        continue
                    if not self._is_cooled_down(rule, symbol):
                        continue

                    triggered = await self._evaluate_position_rule(
                        rule, position, portfolio, results
                    )
                    if triggered and rule.action == RuleAction.CLOSE:
                        closed_symbols.add(symbol)

            # 记录事件
            if any([
                results["stop_loss_triggered"],
                results["take_profit_triggered"],
                results["llm_analysis_triggered"],
                results["daily_limit_breached"],
                results["concentration_warnings"],
            ]):
                self.risk_events.append(results)
                if len(self.risk_events) > self._max_risk_events:
                    self.risk_events = self.risk_events[-self._max_risk_events:]

            return results

        except Exception as e:
            logger.error("风险检查失败: %s", e)
            return {"error": str(e)}

    async def _evaluate_position_rule(
        self,
        rule: RiskRule,
        position: Position,
        portfolio: Portfolio,
        results: Dict[str, Any],
    ) -> bool:
        """
        评估单条仓位级规则

        Returns:
            是否触发
        """
        symbol = position.symbol
        pnl_pct = float(position.unrealized_pnl_percentage)

        triggered = False

        if rule.type in (RuleType.HARD_STOP_LOSS, RuleType.LLM_STOP_LOSS):
            # 止损：亏损超过阈值
            if pnl_pct <= -rule.threshold:
                triggered = True

        elif rule.type in (RuleType.HARD_TAKE_PROFIT, RuleType.LLM_TAKE_PROFIT):
            # 止盈：盈利超过阈值
            if pnl_pct >= rule.threshold:
                triggered = True

        elif rule.type == RuleType.TRAILING_STOP:
            # 追踪止损（简化：基于当前 PnL）
            if pnl_pct <= -rule.threshold:
                triggered = True

        elif rule.type == RuleType.CONCENTRATION_LIMIT:
            # 仓位集中度
            if portfolio.equity > 0:
                concentration = float(position.market_value / portfolio.equity)
                if concentration > rule.threshold:
                    triggered = True
                    results["concentration_warnings"].append({
                        "symbol": symbol,
                        "concentration": concentration,
                        "rule": rule.name,
                    })

        if not triggered:
            return False

        # 执行动作
        self._mark_triggered(rule, symbol)

        if rule.action == RuleAction.CLOSE:
            action = await self._execute_close(rule, position)
            if action:
                results["actions_taken"].append(action)
                if "stop_loss" in rule.type.value:
                    results["stop_loss_triggered"].append(symbol)
                elif "take_profit" in rule.type.value:
                    results["take_profit_triggered"].append(symbol)

        elif rule.action == RuleAction.REDUCE:
            action = await self._execute_reduce(rule, position)
            if action:
                results["actions_taken"].append(action)

        elif rule.action == RuleAction.LLM_ANALYZE:
            # 同一次 check 内同一 symbol 只触发一次 LLM
            if symbol not in self._llm_triggered_symbols:
                self._llm_triggered_symbols.add(symbol)
                await self._trigger_llm_analysis(rule, position)
                results["llm_analysis_triggered"].append({
                    "symbol": symbol,
                    "rule": rule.name,
                    "pnl_pct": pnl_pct,
                })

        elif rule.action == RuleAction.ALERT:
            await self._send_alert(rule, position, pnl_pct)

        return True

    # ------------------------------------------------------------------
    # 动作执行
    # ------------------------------------------------------------------

    async def _execute_close(
        self, rule: RiskRule, position: Position
    ) -> Optional[Dict[str, Any]]:
        """执行平仓"""
        try:
            action_type = (
                "stop_loss" if "stop_loss" in rule.type.value else "take_profit"
            )
            emoji = "🔴" if action_type == "stop_loss" else "🟢"

            logger.warning(
                "触发 %s (%s): %s, PnL=%.2f%%",
                rule.name,
                action_type,
                position.symbol,
                float(position.unrealized_pnl_percentage) * 100,
            )

            await self.message_manager.send_message(
                f"{emoji} **{rule.name}**\n\n"
                f"股票: {position.symbol}\n"
                f"PnL: {position.unrealized_pnl_percentage:.2%}\n"
                f"数量: {position.quantity}\n"
                f"正在平仓...",
                message_type="warning",
            )

            side = OrderSide.SELL if position.quantity > 0 else OrderSide.BUY
            order = Order(
                symbol=position.symbol,
                side=side,
                order_type=OrderType.MARKET,
                quantity=abs(position.quantity),
                time_in_force=TimeInForce.DAY,
            )
            order_id = await self.broker_api.submit_order(order)

            if order_id:
                await self.message_manager.send_message(
                    f"✅ 订单已提交: {position.symbol} (order: {order_id})",
                    message_type="info",
                )
                return {
                    "type": action_type,
                    "rule": rule.name,
                    "symbol": position.symbol,
                    "order_id": order_id,
                }

        except Exception as e:
            logger.error("平仓执行失败 %s (%s): %s", position.symbol, rule.name, e)
            await self.message_manager.send_error(
                f"平仓执行失败: {position.symbol} ({rule.name}) - {e}"
            )
        return None

    async def _execute_reduce(
        self, rule: RiskRule, position: Position
    ) -> Optional[Dict[str, Any]]:
        """执行减仓"""
        try:
            reduce_qty = abs(position.quantity) * Decimal(str(rule.reduce_ratio))
            reduce_qty = max(reduce_qty, Decimal("1"))  # 至少减 1 股

            logger.info(
                "触发减仓 (%s): %s, 减仓 %.0f 股 (%.0f%%)",
                rule.name,
                position.symbol,
                reduce_qty,
                rule.reduce_ratio * 100,
            )

            await self.message_manager.send_message(
                f"⚠️ **{rule.name} - 减仓**\n\n"
                f"股票: {position.symbol}\n"
                f"PnL: {position.unrealized_pnl_percentage:.2%}\n"
                f"减仓: {reduce_qty} 股 ({rule.reduce_ratio:.0%})",
                message_type="warning",
            )

            side = OrderSide.SELL if position.quantity > 0 else OrderSide.BUY
            order = Order(
                symbol=position.symbol,
                side=side,
                order_type=OrderType.MARKET,
                quantity=reduce_qty,
                time_in_force=TimeInForce.DAY,
            )
            order_id = await self.broker_api.submit_order(order)

            if order_id:
                return {
                    "type": "reduce",
                    "rule": rule.name,
                    "symbol": position.symbol,
                    "order_id": order_id,
                    "reduce_qty": float(reduce_qty),
                }

        except Exception as e:
            logger.error("减仓执行失败 %s (%s): %s", position.symbol, rule.name, e)
        return None

    async def _trigger_llm_analysis(
        self, rule: RiskRule, position: Position
    ) -> None:
        """触发 LLM 分析"""
        logger.info(
            "触发 LLM 分析 (%s): %s, PnL=%.2f%%",
            rule.name,
            position.symbol,
            float(position.unrealized_pnl_percentage) * 100,
        )

        context = {
            "trigger": "risk_rule",
            "rule_name": rule.name,
            "rule_type": rule.type.value,
            "symbol": position.symbol,
            "pnl_pct": float(position.unrealized_pnl_percentage),
            "quantity": float(position.quantity),
            "market_value": float(position.market_value),
            "threshold": rule.threshold,
        }

        if self._llm_trigger_callback:
            try:
                await self._llm_trigger_callback(
                    trigger="risk_llm_analysis",
                    context=context,
                )
            except Exception as e:
                logger.error("LLM 分析触发失败: %s", e)
        else:
            # 仅发送告警
            await self.message_manager.send_message(
                f"🤖 **{rule.name} - LLM 分析建议**\n\n"
                f"股票: {position.symbol}\n"
                f"PnL: {position.unrealized_pnl_percentage:.2%}\n"
                f"建议进行 LLM 分析决策",
                message_type="info",
            )

    async def _send_alert(
        self, rule: RiskRule, position: Position, pnl_pct: float
    ) -> None:
        """发送告警"""
        await self.message_manager.send_message(
            f"⚠️ **{rule.name}**\n\n"
            f"股票: {position.symbol}\n"
            f"PnL: {pnl_pct:.2%}\n"
            f"阈值: {rule.threshold:.2%}\n"
            f"{rule.description or ''}",
            message_type="warning",
        )

    async def _check_daily_loss(
        self,
        rule: RiskRule,
        portfolio: Portfolio,
        results: Dict[str, Any],
    ) -> None:
        """检查日内损失限制"""
        if portfolio.equity <= 0:
            return
        daily_loss_pct = float(portfolio.day_pnl / portfolio.equity)
        if daily_loss_pct <= -rule.threshold:
            results["daily_limit_breached"] = True
            logger.critical(
                "日内损失限制突破 (%s)! 亏损: %.2f%%",
                rule.name,
                daily_loss_pct * 100,
            )
            await self.message_manager.send_message(
                f"🚨 **{rule.name}**\n\n"
                f"当日亏损: {daily_loss_pct:.2%}\n"
                f"限制: {rule.threshold:.2%}\n\n"
                f"建议停止交易并审查策略",
                message_type="error",
            )

    # ------------------------------------------------------------------
    # 向后兼容方法
    # ------------------------------------------------------------------

    async def _execute_stop_loss(
        self, position: Position
    ) -> Optional[Dict[str, Any]]:
        """向后兼容：执行止损"""
        rule = RiskRule(
            name="legacy_stop_loss",
            type=RuleType.HARD_STOP_LOSS,
            threshold=self.stop_loss_pct,
            action=RuleAction.CLOSE,
        )
        return await self._execute_close(rule, position)

    async def _execute_take_profit(
        self, position: Position
    ) -> Optional[Dict[str, Any]]:
        """向后兼容：执行止盈"""
        rule = RiskRule(
            name="legacy_take_profit",
            type=RuleType.HARD_TAKE_PROFIT,
            threshold=self.take_profit_pct,
            action=RuleAction.CLOSE,
        )
        return await self._execute_close(rule, position)

    async def _handle_daily_limit_breach(
        self, portfolio: Portfolio, daily_loss_pct: float
    ) -> None:
        """向后兼容：处理日内损失限制突破"""
        await self.message_manager.send_message(
            f"🚨 **日内损失限制突破**\n\n"
            f"当日亏损: {daily_loss_pct:.2%}\n"
            f"限制: {self.daily_loss_limit_pct:.2%}\n\n"
            f"建议停止交易并审查策略",
            message_type="error",
        )

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_risk_summary(self) -> Dict[str, Any]:
        """获取风险摘要"""
        return {
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "daily_loss_limit_pct": self.daily_loss_limit_pct,
            "max_position_concentration": self.max_position_concentration,
            "rules_count": len(self._rules_mgr.get_rules()),
            "enabled_rules_count": len(self._rules_mgr.get_enabled_rules()),
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "recent_events": self.risk_events[-10:] if self.risk_events else [],
        }

    def clear_events(self) -> None:
        """清除事件历史"""
        self.risk_events = []
