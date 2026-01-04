"""
Telegram Service

组合 TelegramTransport（消息发送）和 TelegramBot（命令处理）
"""

from src.utils.logging_config import get_logger
from typing import Dict, Any

from src.interfaces.message_transport import MessageTransport, MessageFormat
from src.interfaces.factory import register_message_transport
from .transport import TelegramTransport
from .bot import TelegramBot
from config import settings

logger = get_logger(__name__)


@register_message_transport("telegram")
class TelegramService(MessageTransport):
    """
    Telegram 服务

    组合 TelegramTransport（消息发送）和 TelegramBot（命令处理）
    继承 MessageTransport 基类，使用其标准初始化流程
    """

    def __init__(
        self,
        bot_token: str = None,
        chat_id: str = None,
        event_system=None
    ):
        # 调用基类初始化
        super().__init__()

        self.bot_token = bot_token or settings.telegram_bot_token
        self.chat_id = chat_id or settings.telegram_chat_id
        self.event_system = event_system

        # 内部组件
        self.transport = TelegramTransport(self.bot_token, self.chat_id)
        self.bot = TelegramBot(
            self.bot_token,
            self.chat_id,
            event_system,
            self.transport
        )

    async def initialize(self) -> bool:
        """初始化服务"""
        result = await self.transport.initialize()
        if result:
            self._initialized = True
        return result

    async def start(self) -> bool:
        """启动服务（包括 Bot 命令处理）"""
        # 启动 transport
        if not await self.transport.start():
            logger.warning("Transport 启动失败，将以只发送模式运行")

        # 启动 bot（如果有 event_system）
        if self.event_system:
            if not await self.bot.start():
                logger.warning("Bot 启动失败，将只处理消息发送")

        self._started = True
        return True

    async def stop(self) -> bool:
        """停止服务"""
        await self.bot.stop()
        await self.transport.stop()
        self._started = False
        return True

    # ========== MessageTransport 接口实现 ==========

    async def send_raw_message(
        self,
        content: str,
        format_type: MessageFormat = MessageFormat.MARKDOWN,
        **kwargs
    ) -> bool:
        """发送消息"""
        return await self.transport.send_raw_message(content, format_type, **kwargs)

    def is_available(self) -> bool:
        """检查是否可用"""
        return self._initialized and self._started and self.transport.is_available()

    def get_transport_name(self) -> str:
        return "Telegram"

    def get_transport_info(self) -> Dict[str, Any]:
        base_info = super().get_transport_info()
        base_info.update({
            "transport": self.transport.get_transport_info(),
            "bot": self.bot.get_status()
        })
        return base_info

    def get_rate_limits(self) -> Dict[str, Any]:
        return self.transport.get_rate_limits()

    # ========== 便捷方法 ==========

    async def send_message(self, message: str, chat_id: str = None) -> bool:
        """发送消息（便捷方法）"""
        return await self.transport.send_raw_message(
            content=message,
            format_type=MessageFormat.MARKDOWN,
            chat_id=chat_id
        )

