"""
命令处理器基类

提供统一的命令处理接口和上下文。
命令处理器通过 trading_system 引用直接调用业务方法，不经过任何中间层。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from telegram import Update
from telegram.ext import ContextTypes

if TYPE_CHECKING:
    from src.trading_system import TradingSystem


@dataclass
class CommandContext:
    """命令执行上下文"""

    chat_id: str
    user_id: str
    username: Optional[str]
    message_text: str
    is_callback: bool = False

    @classmethod
    def from_update(cls, update: Update, is_callback: bool = False) -> "CommandContext":
        """从 Telegram Update 创建上下文"""
        if is_callback and update.callback_query:
            chat = update.callback_query.message.chat
            user = update.callback_query.from_user
            text = update.callback_query.data
        else:
            chat = update.effective_chat
            user = update.effective_user
            text = update.message.text if update.message else ""

        return cls(
            chat_id=str(chat.id),
            user_id=str(user.id) if user else "",
            username=user.username if user else None,
            message_text=text,
            is_callback=is_callback,
        )


class CommandHandler(ABC):
    """
    命令处理器基类

    子类实现具体的命令逻辑，通过 trading_system 直接调用业务方法。
    """

    def __init__(self, trading_system: "TradingSystem", authorized_chat_id: Optional[str] = None):
        self.trading_system = trading_system
        self.authorized_chat_id = authorized_chat_id

    def is_authorized(self, ctx: CommandContext) -> bool:
        """检查是否授权"""
        if not self.authorized_chat_id:
            return True
        return ctx.chat_id == self.authorized_chat_id

    @abstractmethod
    def get_commands(self) -> Dict[str, str]:
        """返回此处理器支持的命令 Dict[command_name, description]"""
        ...

    @abstractmethod
    def get_handlers(self) -> Dict[str, Callable]:
        """返回命令到处理函数的映射 Dict[command_name, handler_function]"""
        ...
