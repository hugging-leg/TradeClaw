"""
Telegram Bot - 命令处理层

职责：管理 Bot 生命周期和命令路由
不负责：消息发送（使用 TelegramTransport）
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from telegram import Bot, BotCommand, Update
from telegram.error import Conflict, NetworkError
from telegram.ext import (
    Application,
    CommandHandler as TgCommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import settings
from agent_trader.utils.logging_config import get_logger

from .commands import AnalysisCommands, CommandHandler, QueryCommands, TradingCommands
from .transport import TelegramTransport

if TYPE_CHECKING:
    from agent_trader.trading_system import TradingSystem

logger = get_logger(__name__)


class TelegramBot:
    """
    Telegram Bot 管理器

    职责：
    - Bot 生命周期管理
    - 命令注册和路由
    - 冲突处理
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        trading_system: Optional["TradingSystem"] = None,
        transport: Optional[TelegramTransport] = None,
    ):
        self.bot_token = bot_token or settings.telegram_bot_token
        self.chat_id = chat_id or settings.telegram_chat_id
        self.trading_system = trading_system

        # 使用提供的 transport 或创建新的
        self.transport = transport or TelegramTransport(self.bot_token, self.chat_id)

        self.application: Optional[Application] = None
        self.is_running = False

        # 初始化命令处理器
        self.command_handlers: List[CommandHandler] = []
        if trading_system is not None:
            self.command_handlers = [
                TradingCommands(trading_system, self.chat_id),
                QueryCommands(trading_system, self.chat_id),
                AnalysisCommands(trading_system, self.chat_id),
            ]

    def _is_configured(self) -> bool:
        """检查是否配置"""
        return (
            bool(self.bot_token)
            and self.bot_token != "test_token"
            and bool(self.chat_id)
            and self.chat_id != "test_chat_id"
        )

    async def start(self) -> bool:
        """启动 Bot"""
        if self.is_running:
            logger.info("Telegram Bot 已在运行")
            return True

        if not self._is_configured():
            logger.info("Telegram 未配置，跳过启动")
            return False

        try:
            self.application = Application.builder().token(self.bot_token).build()

            self._register_commands()
            self.application.add_error_handler(self._handle_error)

            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling(drop_pending_updates=True)
            await self._set_bot_commands()

            self.is_running = True
            logger.info("Telegram Bot 启动成功")
            return True

        except Conflict as e:
            logger.warning(f"Telegram Bot 冲突: {e}")
            logger.warning("可能有另一个实例在运行，将以只发送消息模式运行")
            return False

        except Exception as e:
            logger.error(f"Telegram Bot 启动失败: {e}")
            return False

    async def stop(self) -> bool:
        """停止 Bot"""
        if not self.is_running:
            return True

        try:
            if self.application:
                if self.application.updater and self.application.updater.running:
                    await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()

            self.is_running = False
            logger.info("Telegram Bot 已停止")
            return True

        except Exception as e:
            logger.error(f"停止 Bot 时出错: {e}")
            return False

    def _register_commands(self) -> None:
        """注册所有命令处理器"""
        for handler in self.command_handlers:
            for cmd_name, cmd_handler in handler.get_handlers().items():
                self.application.add_handler(TgCommandHandler(cmd_name, cmd_handler))
                logger.debug(f"注册命令: /{cmd_name}")

        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_unknown_message)
        )

    async def _set_bot_commands(self) -> None:
        """设置 Bot 命令菜单"""
        try:
            commands = []
            for handler in self.command_handlers:
                for cmd, desc in handler.get_commands().items():
                    commands.append(BotCommand(cmd, desc))

            bot = Bot(self.bot_token)
            await bot.set_my_commands(commands)
            logger.debug("Bot 命令菜单已设置")
        except Exception as e:
            logger.debug(f"设置命令菜单失败: {e}")

    async def _handle_unknown_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理未知消息"""
        await update.message.reply_text("🤖 不理解这个命令。使用 /help 查看可用命令。")

    async def _handle_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理错误"""
        error = context.error
        if isinstance(error, Conflict):
            logger.warning("Telegram 轮询冲突")
        elif isinstance(error, NetworkError):
            logger.debug("Telegram 网络错误")
        else:
            logger.error(f"Telegram 错误: {error}")

    # ---- 便捷方法 ----

    async def send_message(self, text: str, chat_id: Optional[str] = None) -> bool:
        """发送消息"""
        return await self.transport.send_raw_message(content=text, chat_id=chat_id or self.chat_id)

    def get_status(self) -> Dict[str, Any]:
        """获取 Bot 状态"""
        return {
            "is_running": self.is_running,
            "configured": self._is_configured(),
            "transport": self.transport.get_transport_info(),
            "commands_count": sum(len(h.get_commands()) for h in self.command_handlers),
        }
