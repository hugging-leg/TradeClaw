"""
分析命令

处理 /analyze 等分析相关命令。
直接调用 TradingSystem 的 public API。
"""

from __future__ import annotations

from typing import Callable, Dict

from telegram import Update
from telegram.ext import ContextTypes

from agent_trader.utils.logging_config import get_logger

from .base import CommandContext, CommandHandler

logger = get_logger(__name__)


class AnalysisCommands(CommandHandler):
    """分析命令处理器"""

    def get_commands(self) -> Dict[str, str]:
        return {
            "analyze": "手动触发 AI 分析",
        }

    def get_handlers(self) -> Dict[str, Callable]:
        return {
            "analyze": self.handle_analyze,
        }

    async def handle_analyze(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理 /analyze - 手动触发分析"""
        ctx = CommandContext.from_update(update)
        if not self.is_authorized(ctx):
            await update.message.reply_text("❌ 未授权访问")
            return

        try:
            await update.message.reply_text(
                "🤖 **AI 分析已启动**\n\n正在执行智能交易分析...\n请稍候查看分析结果。",
                parse_mode="Markdown",
            )

            await self.trading_system.trigger_workflow(
                trigger="manual_analysis",
                context={
                    "source": "telegram",
                    "chat_id": ctx.chat_id,
                    "user": ctx.username or ctx.user_id,
                },
            )

            logger.info(f"用户 {ctx.username or ctx.user_id} 触发了手动分析")

        except Exception as e:
            logger.error(f"触发分析失败: {e}")
            await update.message.reply_text("❌ 启动分析失败")
