"""
Telegram Transport - 纯消息发送层

职责单一：只负责消息发送，不处理命令
"""

import asyncio
from src.utils.logging_config import get_logger
from typing import Optional, Dict, Any
from datetime import datetime

from aiolimiter import AsyncLimiter
from telegram import Bot
from telegram.error import TelegramError

from src.interfaces.message_transport import MessageTransport, MessageFormat
from config import settings

logger = get_logger(__name__)

# Telegram 速率限制: 30 msg/sec per bot, 1 msg/sec per chat
# 保守设置: 2 msg/sec with burst of 3
_telegram_limiter = AsyncLimiter(2, 1)


class TelegramTransport(MessageTransport):
    """
    Telegram 消息传输层

    职责：
    - 发送消息到 Telegram
    - 处理速率限制
    - 处理 Markdown 格式错误
    - 自动重试

    不负责：
    - Bot 命令处理
    - 事件发布
    - 业务逻辑
    """

    def __init__(self, bot_token: str = None, chat_id: str = None):
        super().__init__()
        self.bot_token = bot_token or settings.telegram_bot_token
        self.chat_id = chat_id or settings.telegram_chat_id
        self.bot: Optional[Bot] = None

        # 统计
        self._stats = {
            'sent': 0,
            'failed': 0,
            'last_sent': None,
            'rate_limited': 0
        }

    async def initialize(self) -> bool:
        """初始化 Bot 连接"""
        if self._initialized:
            return True

        if not self._is_configured():
            logger.info("Telegram 未配置，跳过初始化")
            return False

        try:
            self.bot = Bot(token=self.bot_token)
            # 测试连接
            await self.bot.get_me()
            self._initialized = True
            logger.info("Telegram Transport 初始化成功")
            return True
        except Exception as e:
            logger.warning(f"Telegram 初始化失败: {e}")
            return False

    async def start(self) -> bool:
        """启动"""
        if not self._initialized:
            if not await self.initialize():
                return False
        self._started = True
        return True

    async def stop(self) -> bool:
        """停止"""
        self._started = False
        return True

    def is_available(self) -> bool:
        """检查是否可用"""
        return self._initialized and self._started and self.bot is not None

    def _is_configured(self) -> bool:
        """检查是否已配置"""
        return (
            self.bot_token and
            self.bot_token != "test_token" and
            self.chat_id and
            self.chat_id != "test_chat_id"
        )

    async def send_raw_message(
        self,
        content: str,
        format_type: MessageFormat = MessageFormat.MARKDOWN,
        **kwargs
    ) -> bool:
        """
        发送消息

        自动处理：
        - 速率限制
        - Markdown 解析错误回退
        - 消息过长截断
        """
        if not self.is_available():
            if not await self.initialize():
                return False

        target_chat_id = kwargs.get('chat_id') or self.chat_id
        if not target_chat_id:
            logger.error("未指定 chat_id")
            return False

        # 速率限制（直接使用 aiolimiter）
        async with _telegram_limiter:
            pass  # 获取令牌后继续

        # 尝试发送
        try:
            return await self._send_with_fallback(
                target_chat_id, content, format_type
            )
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            self._stats['failed'] += 1
            return False

    async def _send_with_fallback(
        self,
        chat_id: str,
        content: str,
        format_type: MessageFormat
    ) -> bool:
        """带回退的发送逻辑"""
        parse_mode = self._get_parse_mode(format_type)

        # 第一次尝试：使用指定格式
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=content,
                parse_mode=parse_mode
            )
            self._on_success()
            return True
        except TelegramError as e:
            error_msg = str(e)

            # Markdown 解析失败 → 回退到纯文本
            if "Can't parse entities" in error_msg and parse_mode:
                logger.debug("Markdown 解析失败，回退到纯文本")
                return await self._send_plain(chat_id, content)

            # 消息过长 → 截断
            if "too long" in error_msg.lower():
                return await self._send_truncated(chat_id, content)

            # 速率限制 → 等待重试
            if "Too Many Requests" in error_msg:
                await asyncio.sleep(5)
                return await self._send_plain(chat_id, content)

            raise

    async def _send_plain(self, chat_id: str, content: str) -> bool:
        """发送纯文本"""
        try:
            # 移除 Markdown 符号
            clean_content = self._strip_markdown(content)
            await self.bot.send_message(chat_id=chat_id, text=clean_content)
            self._on_success()
            return True
        except Exception as e:
            logger.error(f"纯文本发送也失败: {e}")
            return False

    async def _send_truncated(self, chat_id: str, content: str) -> bool:
        """发送截断的消息"""
        try:
            truncated = content[:4000] + "\n\n... (消息已截断)"
            await self.bot.send_message(chat_id=chat_id, text=truncated)
            self._on_success()
            return True
        except Exception:
            return False

    @staticmethod
    def _get_parse_mode(format_type: MessageFormat) -> Optional[str]:
        """转换格式类型"""
        mapping = {
            MessageFormat.MARKDOWN: "Markdown",
            MessageFormat.HTML: "HTML",
            MessageFormat.PLAIN_TEXT: None,
            MessageFormat.JSON: None
        }
        return mapping.get(format_type)

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """移除 Markdown 符号"""
        for char in ['*', '_', '`', '[', ']', '(', ')']:
            text = text.replace(char, '')
        return text

    def _on_success(self):
        """成功发送后更新统计"""
        self._stats['sent'] += 1
        self._stats['last_sent'] = datetime.now()

    # MessageTransport 接口方法

    def get_transport_name(self) -> str:
        return "Telegram"

    def get_transport_info(self) -> Dict[str, Any]:
        return {
            "name": "Telegram Transport",
            "initialized": self._initialized,
            "configured": self._is_configured(),
            "stats": self._stats
        }

    def get_rate_limits(self) -> Dict[str, Any]:
        return {
            "max_rate": 2,
            "time_period": 1,
            "rate_limited_count": self._stats.get('rate_limited', 0)
        }
