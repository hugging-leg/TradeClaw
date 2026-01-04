"""
命令处理器基类

提供统一的命令处理接口和上下文
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Callable, Awaitable
from telegram import Update
from telegram.ext import ContextTypes


@dataclass
class CommandContext:
    """命令执行上下文"""
    chat_id: str
    user_id: str
    username: Optional[str]
    message_text: str
    is_callback: bool = False  # 是否来自按钮回调
    
    @classmethod
    def from_update(cls, update: Update, is_callback: bool = False) -> 'CommandContext':
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
            is_callback=is_callback
        )


class CommandHandler(ABC):
    """
    命令处理器基类
    
    子类实现具体的命令逻辑，通过事件系统与业务层通信
    """
    
    def __init__(self, event_system, authorized_chat_id: str = None):
        """
        Args:
            event_system: 事件系统实例
            authorized_chat_id: 授权的 chat_id，None 表示允许所有
        """
        self.event_system = event_system
        self.authorized_chat_id = authorized_chat_id
    
    def is_authorized(self, ctx: CommandContext) -> bool:
        """检查是否授权"""
        if not self.authorized_chat_id:
            return True
        return ctx.chat_id == self.authorized_chat_id
    
    async def publish_event(self, event_type: str, data: Dict[str, Any] = None):
        """发布事件到事件系统"""
        if self.event_system:
            await self.event_system.publish(event_type, data or {})
    
    @abstractmethod
    def get_commands(self) -> Dict[str, str]:
        """
        返回此处理器支持的命令
        
        Returns:
            Dict[command_name, description]
        """
        pass
    
    @abstractmethod
    def get_handlers(self) -> Dict[str, Callable]:
        """
        返回命令到处理函数的映射
        
        Returns:
            Dict[command_name, handler_function]
        """
        pass

