"""
风险管理服务

职责：
- 止损/止盈检测
- 组合风险监控
- 日内损失限制
- 仓位集中度检查

设计：
- 独立于 TradingSystem，可单独测试
- 通过依赖注入获取 broker_api 和 message_manager
"""

from src.utils.logging_config import get_logger
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal

from src.interfaces.broker_api import BrokerAPI
from src.messaging.message_manager import MessageManager
from src.models.trading_models import Portfolio, Position, Order, OrderSide, OrderType, TimeInForce
from config import settings

logger = get_logger(__name__)


class RiskManager:
    """
    风险管理服务

    功能：
    - 止损检测和执行
    - 止盈检测和执行
    - 日内损失限制
    - 仓位集中度检查
    - 风险报告生成
    """

    def __init__(
        self,
        broker_api: BrokerAPI,
        message_manager: MessageManager,
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
        daily_loss_limit_pct: Optional[float] = None,
        max_position_concentration: Optional[float] = None
    ):
        """
        初始化风险管理器

        Args:
            broker_api: 交易接口
            message_manager: 消息管理器
            stop_loss_pct: 止损百分比（默认从配置读取）
            take_profit_pct: 止盈百分比（默认从配置读取）
            daily_loss_limit_pct: 日内损失限制（默认从配置读取）
            max_position_concentration: 最大单仓位占比（默认从配置读取）
        """
        self.broker_api = broker_api
        self.message_manager = message_manager

        # 从配置读取，支持覆盖
        # 自动规范化：如果 > 1 则视为百分比形式（如 5 -> 0.05）
        self.stop_loss_pct = self._normalize_pct(stop_loss_pct or settings.stop_loss_percentage)
        self.take_profit_pct = self._normalize_pct(take_profit_pct or settings.take_profit_percentage)
        self.daily_loss_limit_pct = self._normalize_pct(daily_loss_limit_pct or settings.daily_loss_limit_percentage)
        self.max_position_concentration = self._normalize_pct(max_position_concentration or settings.max_position_concentration)

        # 统计
        self.risk_events: List[Dict[str, Any]] = []
        self.last_check: Optional[datetime] = None

        logger.info(
            f"RiskManager 初始化: 止损={self.stop_loss_pct:.1%}, "
            f"止盈={self.take_profit_pct:.1%}, 日内限制={self.daily_loss_limit_pct:.1%}"
        )

    @staticmethod
    def _normalize_pct(value: float) -> float:
        """规范化百分比值：如果 > 1 则视为百分比形式（如 5 -> 0.05）"""
        if value > 1:
            return value / 100
        return value

    async def run_risk_checks(self, portfolio: Portfolio) -> Dict[str, Any]:
        """
        执行全面风险检查

        Args:
            portfolio: 当前组合

        Returns:
            风险检查结果
        """
        self.last_check = datetime.now()
        results = {
            "timestamp": self.last_check.isoformat(),
            "stop_loss_triggered": [],
            "take_profit_triggered": [],
            "daily_limit_breached": False,
            "concentration_warnings": [],
            "actions_taken": []
        }

        try:
            # 1. 检查止损/止盈
            for position in portfolio.positions:
                if position.quantity == 0:
                    continue

                pnl_pct = float(position.unrealized_pnl_percentage)

                # 止损
                if pnl_pct <= -self.stop_loss_pct:
                    results["stop_loss_triggered"].append(position.symbol)
                    action = await self._execute_stop_loss(position)
                    if action:
                        results["actions_taken"].append(action)

                # 止盈
                elif pnl_pct >= self.take_profit_pct:
                    results["take_profit_triggered"].append(position.symbol)
                    action = await self._execute_take_profit(position)
                    if action:
                        results["actions_taken"].append(action)

            # 2. 检查日内损失限制
            if portfolio.equity > 0:
                daily_loss_pct = float(portfolio.day_pnl / portfolio.equity)
                if daily_loss_pct <= -self.daily_loss_limit_pct:
                    results["daily_limit_breached"] = True
                    await self._handle_daily_limit_breach(portfolio, daily_loss_pct)

            # 3. 检查仓位集中度
            for position in portfolio.positions:
                if position.quantity == 0:
                    continue
                concentration = float(position.market_value / portfolio.equity)
                if concentration > self.max_position_concentration:
                    results["concentration_warnings"].append({
                        "symbol": position.symbol,
                        "concentration": concentration
                    })

            # 记录事件
            if any([
                results["stop_loss_triggered"],
                results["take_profit_triggered"],
                results["daily_limit_breached"],
                results["concentration_warnings"]
            ]):
                self.risk_events.append(results)

            return results

        except Exception as e:
            logger.error(f"风险检查失败: {e}")
            return {"error": str(e)}

    async def _execute_stop_loss(self, position: Position) -> Optional[Dict[str, Any]]:
        """执行止损"""
        try:
            logger.warning(
                f"触发止损: {position.symbol}, "
                f"亏损 {position.unrealized_pnl_percentage:.2%}"
            )

            # 发送通知
            await self.message_manager.send_message(
                f"🔴 **止损触发**\n\n"
                f"股票: {position.symbol}\n"
                f"亏损: {position.unrealized_pnl_percentage:.2%}\n"
                f"数量: {position.quantity}\n"
                f"正在平仓...",
                message_type="warning"
            )

            # 平仓
            side = OrderSide.SELL if position.quantity > 0 else OrderSide.BUY
            order = await self.broker_api.submit_order(
                symbol=position.symbol,
                side=side,
                quantity=abs(position.quantity),
                order_type=OrderType.MARKET,
                time_in_force=TimeInForce.DAY
            )

            if order:
                await self.message_manager.send_message(
                    f"✅ 止损订单已提交: {position.symbol}\n"
                    f"订单ID: {order.id}",
                    message_type="info"
                )
                return {
                    "type": "stop_loss",
                    "symbol": position.symbol,
                    "order_id": order.id
                }

        except Exception as e:
            logger.error(f"止损执行失败 {position.symbol}: {e}")
            await self.message_manager.send_error(
                f"止损执行失败: {position.symbol} - {e}"
            )

        return None

    async def _execute_take_profit(self, position: Position) -> Optional[Dict[str, Any]]:
        """执行止盈"""
        try:
            logger.info(
                f"触发止盈: {position.symbol}, "
                f"盈利 {position.unrealized_pnl_percentage:.2%}"
            )

            # 发送通知
            await self.message_manager.send_message(
                f"🟢 **止盈触发**\n\n"
                f"股票: {position.symbol}\n"
                f"盈利: {position.unrealized_pnl_percentage:.2%}\n"
                f"数量: {position.quantity}\n"
                f"正在平仓...",
                message_type="info"
            )

            # 平仓
            side = OrderSide.SELL if position.quantity > 0 else OrderSide.BUY
            order = await self.broker_api.submit_order(
                symbol=position.symbol,
                side=side,
                quantity=abs(position.quantity),
                order_type=OrderType.MARKET,
                time_in_force=TimeInForce.DAY
            )

            if order:
                await self.message_manager.send_message(
                    f"✅ 止盈订单已提交: {position.symbol}\n"
                    f"订单ID: {order.id}",
                    message_type="info"
                )
                return {
                    "type": "take_profit",
                    "symbol": position.symbol,
                    "order_id": order.id
                }

        except Exception as e:
            logger.error(f"止盈执行失败 {position.symbol}: {e}")
            await self.message_manager.send_error(
                f"止盈执行失败: {position.symbol} - {e}"
            )

        return None

    async def _handle_daily_limit_breach(
        self,
        portfolio: Portfolio,
        daily_loss_pct: float
    ):
        """处理日内损失限制突破"""
        logger.critical(
            f"日内损失限制突破! 亏损: {daily_loss_pct:.2%}"
        )

        await self.message_manager.send_message(
            f"🚨 **日内损失限制突破**\n\n"
            f"当日亏损: {daily_loss_pct:.2%}\n"
            f"限制: {self.daily_loss_limit_pct:.2%}\n\n"
            f"建议停止交易并审查策略",
            message_type="error"
        )

    def get_risk_summary(self) -> Dict[str, Any]:
        """获取风险摘要"""
        return {
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "daily_loss_limit_pct": self.daily_loss_limit_pct,
            "max_position_concentration": self.max_position_concentration,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "recent_events": self.risk_events[-10:] if self.risk_events else []
        }

    def clear_events(self):
        """清除事件历史"""
        self.risk_events = []

