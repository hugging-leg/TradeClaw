"""
交易控制命令

处理 /start, /stop, /emergency 等交易控制命令。
直接调用 TradingSystem 的 public API。
"""

from __future__ import annotations

from typing import Callable, Dict

from telegram import Update
from telegram.ext import ContextTypes

from agent_trader.utils.logging_config import get_logger

from .base import CommandContext, CommandHandler

logger = get_logger(__name__)


class TradingCommands(CommandHandler):
    """交易控制命令处理器"""

    def get_commands(self) -> Dict[str, str]:
        return {
            "start": "启用交易（恢复自动交易）",
            "stop": "禁用交易（暂停自动交易）",
            "emergency": "紧急停止（关闭所有仓位）",
        }

    def get_handlers(self) -> Dict[str, Callable]:
        return {
            "start": self.handle_start,
            "stop": self.handle_stop,
            "emergency": self.handle_emergency,
        }

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理 /start - 启用交易"""
        ctx = CommandContext.from_update(update)
        if not self.is_authorized(ctx):
            await update.message.reply_text("❌ 未授权访问")
            return

        try:
            await self.trading_system.enable_trading()
            logger.info(f"用户 {ctx.username or ctx.user_id} 启用了交易")
        except Exception as e:
            logger.error(f"启用交易失败: {e}")
            await update.message.reply_text("❌ 启用交易失败")

    async def handle_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理 /stop - 禁用交易"""
        ctx = CommandContext.from_update(update)
        if not self.is_authorized(ctx):
            await update.message.reply_text("❌ 未授权访问")
            return

        try:
            await self.trading_system.disable_trading(reason="Telegram 手动暂停")
            logger.info(f"用户 {ctx.username or ctx.user_id} 禁用了交易")
        except Exception as e:
            logger.error(f"禁用交易失败: {e}")
            await update.message.reply_text("❌ 禁用交易失败")

    async def handle_emergency(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理 /emergency - 紧急停止"""
        ctx = CommandContext.from_update(update)
        if not self.is_authorized(ctx):
            await update.message.reply_text("❌ 未授权访问")
            return

        try:
            await update.message.reply_text(
                "🚨 **紧急停止已触发**\n\n正在停止所有交易...",
                parse_mode="Markdown",
            )
            await self.trading_system.emergency_stop()
            logger.warning(f"用户 {ctx.username or ctx.user_id} 触发了紧急停止")
        except Exception as e:
            logger.error(f"紧急停止失败: {e}")
            await update.message.reply_text("❌ 紧急停止执行失败")
