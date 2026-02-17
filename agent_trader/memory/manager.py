"""
MemoryManager — 统一管理 LangGraph checkpointer 和 store

职责：
- 使用 PostgreSQL 提供 checkpointer (short-term) 和 store (long-term)
- 管理连接生命周期

使用方式：
    manager = MemoryManager(postgres_uri=settings.postgres_uri)
    await manager.initialize()
    # manager.checkpointer / manager.store 注入到 workflow
    await manager.close()
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore

from agent_trader.utils.logging_config import get_logger

logger = get_logger(__name__)


class MemoryManager:
    """
    统一管理 LangGraph checkpointer (short-term) 和 store (long-term)。

    使用 AsyncPostgresSaver + AsyncPostgresStore 持久化到 PostgreSQL。
    """

    def __init__(self, postgres_uri: str):
        if not postgres_uri:
            raise ValueError(
                "postgres_uri is required. "
                "Set POSTGRES_URI in .env or environment variables."
            )
        self._postgres_uri = postgres_uri
        self._checkpointer: AsyncPostgresSaver | None = None
        self._store: AsyncPostgresStore | None = None

        # async context managers（__aenter__ / __aexit__）
        self._checkpointer_cm: AbstractAsyncContextManager[Any] | None = None
        self._store_cm: AbstractAsyncContextManager[Any] | None = None

    async def initialize(self) -> None:
        """初始化 checkpointer 和 store（连接 PostgreSQL 并创建 schema）"""
        logger.info("Initializing PostgreSQL memory backend...")

        self._checkpointer_cm = AsyncPostgresSaver.from_conn_string(
            self._postgres_uri
        )
        self._checkpointer = await self._checkpointer_cm.__aenter__()

        self._store_cm = AsyncPostgresStore.from_conn_string(
            self._postgres_uri
        )
        self._store = await self._store_cm.__aenter__()

        # 首次运行时创建 schema（幂等操作）
        await self._checkpointer.setup()
        await self._store.setup()

        logger.info("PostgreSQL memory backend initialized (checkpointer + store)")

    @property
    def checkpointer(self) -> AsyncPostgresSaver:
        """LangGraph checkpointer (short-term, thread-level)"""
        if self._checkpointer is None:
            raise RuntimeError("MemoryManager not initialized. Call initialize() first.")
        return self._checkpointer

    @property
    def store(self) -> AsyncPostgresStore:
        """LangGraph store (long-term, cross-thread)"""
        if self._store is None:
            raise RuntimeError("MemoryManager not initialized. Call initialize() first.")
        return self._store

    async def close(self) -> None:
        """释放连接资源"""
        errors = []
        for name, cm in [("store", self._store_cm), ("checkpointer", self._checkpointer_cm)]:
            if cm is not None:
                try:
                    await cm.__aexit__(None, None, None)
                except Exception as e:
                    errors.append(f"{name}: {e}")

        self._checkpointer = None
        self._store = None
        self._checkpointer_cm = None
        self._store_cm = None

        if errors:
            logger.warning("Errors closing PostgreSQL memory connections: %s", "; ".join(errors))
        else:
            logger.info("PostgreSQL memory connections closed")
