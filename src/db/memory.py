"""
LangChain Memory 集成

使用 SQLAlchemy 持久化 Agent 的对话历史
"""

from src.utils.logging_config import get_logger
from datetime import datetime
from typing import List, Dict, Any, Optional
import json

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage
)
from langchain_core.chat_history import BaseChatMessageHistory

from .session import get_db, init_db
from .models import AgentMessage

logger = get_logger(__name__)


class SQLAgentMessageHistory(BaseChatMessageHistory):
    """
    基于 SQLAlchemy 的消息历史

    使用 Agent-Trader 的数据库存储对话历史
    """

    def __init__(self, session_id: str = "default"):
        """
        初始化

        Args:
            session_id: 会话 ID，用于区分不同的对话
        """
        self.session_id = session_id
        self._messages: List[BaseMessage] = []
        self._loaded = False

    async def _ensure_loaded(self):
        """确保消息已从数据库加载"""
        if self._loaded:
            return

        try:
            async with get_db() as db:
                from sqlalchemy import select
                query = (
                    select(AgentMessage)
                    .where(AgentMessage.session_id == self.session_id)
                    .order_by(AgentMessage.created_at)
                )
                result = await db.execute(query)
                db_messages = result.scalars().all()

                self._messages = []
                for msg in db_messages:
                    self._messages.append(self._db_to_langchain(msg))

            self._loaded = True
            logger.debug(f"加载 {len(self._messages)} 条历史消息")
        except Exception as e:
            logger.warning(f"加载消息历史失败: {e}")
            self._loaded = True  # 标记为已加载，避免重复尝试

    @property
    def messages(self) -> List[BaseMessage]:
        """获取消息列表（同步，使用缓存）"""
        return self._messages

    async def aget_messages(self) -> List[BaseMessage]:
        """异步获取消息列表"""
        await self._ensure_loaded()
        return self._messages

    def add_message(self, message: BaseMessage) -> None:
        """添加消息（同步版本，仅更新缓存）"""
        self._messages.append(message)
        # 注意：同步方法不保存到数据库，需要调用 async 版本

    async def aadd_messages(self, messages: List[BaseMessage]) -> None:
        """异步添加消息并持久化"""
        await self._ensure_loaded()

        try:
            async with get_db() as db:
                for message in messages:
                    self._messages.append(message)
                    db_msg = self._langchain_to_db(message)
                    db.add(db_msg)
                await db.flush()
            logger.debug(f"保存 {len(messages)} 条消息到数据库")
        except Exception as e:
            logger.error(f"保存消息失败: {e}")

    def clear(self) -> None:
        """清除消息（同步版本）"""
        self._messages = []

    async def aclear(self) -> None:
        """异步清除消息"""
        try:
            from sqlalchemy import delete
            async with get_db() as db:
                await db.execute(
                    delete(AgentMessage).where(
                        AgentMessage.session_id == self.session_id
                    )
                )
            self._messages = []
            logger.info(f"清除会话 {self.session_id} 的消息历史")
        except Exception as e:
            logger.error(f"清除消息历史失败: {e}")

    def _langchain_to_db(self, message: BaseMessage) -> AgentMessage:
        """转换 LangChain 消息为数据库模型"""
        role = self._get_role(message)
        content = message.content if isinstance(message.content, str) else json.dumps(message.content)

        additional_kwargs = None
        if hasattr(message, 'additional_kwargs') and message.additional_kwargs:
            additional_kwargs = message.additional_kwargs
        if hasattr(message, 'tool_calls') and message.tool_calls:
            additional_kwargs = additional_kwargs or {}
            additional_kwargs['tool_calls'] = [
                {'name': tc.get('name'), 'id': tc.get('id')}
                for tc in message.tool_calls
            ]

        return AgentMessage(
            session_id=self.session_id,
            role=role,
            content=content,
            additional_kwargs=additional_kwargs
        )

    def _db_to_langchain(self, db_msg: AgentMessage) -> BaseMessage:
        """转换数据库模型为 LangChain 消息"""
        role = db_msg.role
        content = db_msg.content
        kwargs = db_msg.additional_kwargs or {}

        if role == 'human':
            return HumanMessage(content=content)
        elif role == 'ai':
            return AIMessage(content=content, additional_kwargs=kwargs)
        elif role == 'system':
            return SystemMessage(content=content)
        elif role == 'tool':
            return ToolMessage(content=content, tool_call_id=kwargs.get('tool_call_id', ''))
        else:
            return HumanMessage(content=content)

    @staticmethod
    def _get_role(message: BaseMessage) -> str:
        """获取消息角色"""
        if isinstance(message, HumanMessage):
            return 'human'
        elif isinstance(message, AIMessage):
            return 'ai'
        elif isinstance(message, SystemMessage):
            return 'system'
        elif isinstance(message, ToolMessage):
            return 'tool'
        return 'human'


def get_agent_memory(session_id: str = "trading_agent") -> SQLAgentMessageHistory:
    """
    获取 Agent Memory 实例

    Args:
        session_id: 会话 ID

    Returns:
        SQLAgentMessageHistory 实例
    """
    return SQLAgentMessageHistory(session_id=session_id)

