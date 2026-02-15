"""
查询处理服务

职责：
- 处理系统状态查询
- 处理组合查询
- 处理订单查询
- 格式化响应

设计：
- 独立于 TradingSystem
- 处理来自 Telegram 等渠道的查询请求
"""

from src.utils.logging_config import get_logger
from typing import Dict, Any, List, Optional

from src.interfaces.broker_api import BrokerAPI
from src.messaging.message_manager import MessageManager
from src.models.trading_models import Portfolio

logger = get_logger(__name__)


class QueryHandler:
    """
    查询处理服务

    功能：
    - 系统状态查询
    - 组合信息查询
    - 订单状态查询
    - 格式化并发送响应
    """

    def __init__(
        self,
        broker_api: BrokerAPI,
        message_manager: MessageManager
    ):
        self.broker_api = broker_api
        self.message_manager = message_manager

    async def handle_status_query(
        self,
        system_state: Dict[str, Any]
    ) -> str:
        """
        处理系统状态查询

        Args:
            system_state: 系统状态字典，包含:
                - is_running: bool
                - is_trading_enabled: bool
                - workflow_type: str
                - market_open: bool (optional)
                - scheduler_jobs: int (optional)
                - realtime_monitor_active: bool (optional)
                - portfolio: Portfolio (optional, pre-fetched)

        Returns:
            格式化的状态消息
        """
        try:
            # 使用预获取的市场状态，或自行获取
            market_open = system_state.get('market_open')
            if market_open is None:
                try:
                    market_open = await self.broker_api.is_market_open()
                except Exception:
                    market_open = None

            # 使用预获取的组合信息，或自行获取
            portfolio = system_state.get('portfolio')
            if portfolio is None:
                try:
                    portfolio = await self.broker_api.get_portfolio()
                except Exception:
                    portfolio = None

            # 构建状态消息
            status_lines = [
                "📊 **Trading System Status**\n",
                f"🏃 **Running**: {'✅ Yes' if system_state.get('is_running') else '❌ No'}",
                f"💰 **Trading Enabled**: {'✅ Yes' if system_state.get('is_trading_enabled') else '❌ No'}",
            ]

            if market_open is not None:
                status_lines.append(f"🏪 **Market Open**: {'✅ Yes' if market_open else '❌ No'}")

            workflow_type = system_state.get('workflow_type', 'unknown')
            status_lines.append(f"🤖 **Workflow**: {workflow_type}")

            # 实时监控状态
            realtime_monitor_active = system_state.get('realtime_monitor_active')
            if realtime_monitor_active is not None:
                monitor_text = '✅ Active' if realtime_monitor_active else '❌ Inactive'
                status_lines.append(f"📡 **Realtime Monitor**: {monitor_text}")

            # 调度器状态
            scheduler_jobs = system_state.get('scheduler_jobs')
            if scheduler_jobs is not None:
                status_lines.append(f"⏰ **Scheduler**: {scheduler_jobs} jobs")

            # 组合概览
            if portfolio:
                status_lines.extend([
                    "",
                    "📈 **Portfolio Summary**:",
                    f"• Total Equity: ${float(portfolio.equity):,.2f}",
                    f"• Cash: ${float(portfolio.cash):,.2f}",
                    f"• Day P&L: ${float(portfolio.day_pnl):,.2f}",
                    f"• Positions: {len(portfolio.positions)}"
                ])

            status_msg = "\n".join(status_lines)
            await self.message_manager.send_message(status_msg, message_type="info")
            return status_msg

        except Exception as e:
            logger.error(f"状态查询失败: {e}")
            error_msg = f"❌ 状态查询失败: {e}"
            await self.message_manager.send_error(error_msg)
            return error_msg

    async def handle_portfolio_query(self) -> str:
        """
        处理组合查询

        Returns:
            格式化的组合消息
        """
        try:
            portfolio = await self.broker_api.get_portfolio()

            if not portfolio:
                msg = "⚠️ 无法获取组合信息"
                await self.message_manager.send_message(msg, message_type="warning")
                return msg

            # 构建组合消息
            lines = [
                "📈 **投资组合**\n",
                f"总权益: ${portfolio.equity:,.2f}",
                f"现金: ${portfolio.cash:,.2f}",
                f"持仓价值: ${portfolio.equity - portfolio.cash:,.2f}",
                f"当日盈亏: ${portfolio.day_pnl:,.2f}",
                ""
            ]

            # 添加持仓详情
            active_positions = [p for p in portfolio.positions if p.quantity != 0]
            if active_positions:
                lines.append("📋 **持仓明细**")
                for pos in active_positions:
                    pnl_emoji = "🟢" if pos.unrealized_pnl >= 0 else "🔴"
                    lines.append(
                        f"{pnl_emoji} {pos.symbol}: {pos.quantity} 股 "
                        f"@ ${pos.current_price:,.2f} "
                        f"({pos.unrealized_pnl_percentage:+.2%})"
                    )
            else:
                lines.append("📋 暂无持仓")

            portfolio_msg = "\n".join(lines)
            await self.message_manager.send_message(portfolio_msg, message_type="info")
            return portfolio_msg

        except Exception as e:
            logger.error(f"组合查询失败: {e}")
            error_msg = f"❌ 组合查询失败: {e}"
            await self.message_manager.send_error(error_msg)
            return error_msg

    async def handle_orders_query(self, status: str = "open") -> str:
        """
        处理订单查询

        Args:
            status: 订单状态过滤（open, closed, all）

        Returns:
            格式化的订单消息
        """
        try:
            orders = await self.broker_api.get_orders(status=status)

            if not orders:
                msg = f"📋 暂无{status}订单"
                await self.message_manager.send_message(msg, message_type="info")
                return msg

            # 构建订单消息
            lines = [f"📋 **{status.upper()} 订单**\n"]

            for order in orders[:10]:  # 限制显示数量
                status_emoji = {
                    "filled": "✅",
                    "partially_filled": "🟡",
                    "pending": "⏳",
                    "cancelled": "❌",
                    "rejected": "🚫"
                }.get(order.status.value if hasattr(order.status, 'value') else str(order.status), "❓")

                lines.append(
                    f"{status_emoji} {order.symbol} {order.side.value if hasattr(order.side, 'value') else order.side} "
                    f"{order.quantity} @ {order.order_type.value if hasattr(order.order_type, 'value') else order.order_type}"
                )

            if len(orders) > 10:
                lines.append(f"\n... 还有 {len(orders) - 10} 个订单")

            orders_msg = "\n".join(lines)
            await self.message_manager.send_message(orders_msg, message_type="info")
            return orders_msg

        except Exception as e:
            logger.error(f"订单查询失败: {e}")
            error_msg = f"❌ 订单查询失败: {e}"
            await self.message_manager.send_error(error_msg)
            return error_msg

