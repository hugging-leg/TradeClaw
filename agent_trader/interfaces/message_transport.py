"""
Abstract message transport interface for low-level message delivery.

This module defines the abstract interface for message transport implementations,
focusing purely on message delivery without business logic.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from enum import Enum


class MessageFormat(Enum):
    """Supported message formats"""
    PLAIN_TEXT = "plain_text"
    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"


class MessageTransport(ABC):
    """
    Abstract base class for message transport implementations.

    设计原则：
    - 所有 transport 都需要异步初始化
    - 调用顺序: initialize() -> start() -> send_raw_message() -> stop()
    - 使用方不需要检查任何内部标志
    """

    def __init__(self):
        """初始化基类状态"""
        self._initialized = False
        self._started = False

    @property
    def is_initialized(self) -> bool:
        """是否已初始化"""
        return self._initialized

    @property
    def is_started(self) -> bool:
        """是否已启动"""
        return self._started

    @abstractmethod
    async def send_raw_message(
        self,
        content: str,
        format_type: MessageFormat = MessageFormat.PLAIN_TEXT,
        **kwargs
    ) -> bool:
        """
        Send a raw message.

        Args:
            content: Raw message content
            format_type: Message format (plain_text, markdown, html, json)
            **kwargs: Transport-specific parameters

        Returns:
            True if message was sent successfully, False otherwise
        """
        pass

    async def initialize(self) -> bool:
        """
        Initialize the transport service.

        子类应调用 super().initialize() 或设置 self._initialized = True

        Returns:
            True if initialization successful, False otherwise
        """
        self._initialized = True
        return True

    async def start(self) -> bool:
        """
        Start the transport service.

        子类应调用 super().start() 或设置 self._started = True

        Returns:
            True if start successful, False otherwise
        """
        self._started = True
        return True

    async def stop(self) -> bool:
        """
        Stop the transport service.

        Returns:
            True if stop successful, False otherwise
        """
        self._started = False
        return True

    def is_available(self) -> bool:
        """
        Check if the transport is available and ready to send messages.

        默认实现：已初始化且已启动

        Returns:
            True if available, False otherwise
        """
        return self._initialized and self._started

    @abstractmethod
    def get_transport_name(self) -> str:
        """
        Get the name of the transport provider.

        Returns:
            String name of the transport (e.g., "Telegram", "Discord", "SMTP")
        """
        pass

    def get_transport_info(self) -> Dict[str, Any]:
        """
        Get detailed information about the transport provider.

        Returns:
            Dictionary containing transport information, capabilities, etc.
        """
        return {
            "name": self.get_transport_name(),
            "initialized": self._initialized,
            "started": self._started,
            "available": self.is_available()
        }

    def get_rate_limits(self) -> Dict[str, Any]:
        """
        Get rate limit information for this transport.

        Returns:
            Dictionary containing rate limit information
        """
        return {} 