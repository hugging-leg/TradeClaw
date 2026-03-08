"""
MemoryManager — 统一管理 LangGraph checkpointer 和 store

职责：
- 使用 PostgreSQL 提供 checkpointer (short-term) 和 store (long-term)
- 管理连接生命周期
- 可选：配置 embedding 以启用语义搜索（需要 pgvector 扩展）
- 启动时自动探测 embedding 维度，用户无需手动配置 dims

使用方式：
    manager = MemoryManager(postgres_uri=settings.postgres_uri)
    await manager.initialize()
    # manager.checkpointer / manager.store 注入到 workflow
    await manager.close()
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Any, Optional

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore

from agent_trader.utils.logging_config import get_logger

logger = get_logger(__name__)


async def _probe_embedding_dims(
    api_key: str,
    base_url: str,
    model: str,
) -> int:
    """
    Send a tiny probe request to the embedding API and return the vector
    dimension. This avoids requiring users to know / configure dims manually.
    """
    from openai import AsyncOpenAI

    client_kwargs: dict[str, Any] = {}
    if api_key:
        client_kwargs["api_key"] = api_key
    if base_url:
        client_kwargs["base_url"] = base_url

    client = AsyncOpenAI(**client_kwargs)
    resp = await client.embeddings.create(model=model, input=["probe"])
    dims = len(resp.data[0].embedding)
    await client.close()
    return dims


def _make_embed_fn(
    api_key: str,
    base_url: str,
    model: str,
):
    """Create an async embedding function for LangGraph IndexConfig."""
    from openai import AsyncOpenAI

    client_kwargs: dict[str, Any] = {}
    if api_key:
        client_kwargs["api_key"] = api_key
    if base_url:
        client_kwargs["base_url"] = base_url

    _client = AsyncOpenAI(**client_kwargs)
    _model = model

    async def _aembed(texts: list[str]) -> list[list[float]]:
        resp = await _client.embeddings.create(model=_model, input=texts)
        return [e.embedding for e in resp.data]

    return _aembed


class MemoryManager:
    """
    统一管理 LangGraph checkpointer (short-term) 和 store (long-term)。

    使用 AsyncPostgresSaver + AsyncPostgresStore 持久化到 PostgreSQL。
    当 EMBEDDING_* 环境变量配置后，自动启用 pgvector 语义搜索。
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

        # Index config (set during initialize)
        self._index_config: dict | None = None

    async def _build_index_config(self) -> Optional[dict]:
        """
        Read EMBEDDING_* settings and build a LangGraph ``IndexConfig`` dict.

        Returns ``None`` if embedding is not configured, which means the store
        will work in time-based mode only (no semantic search).

        Automatically probes the embedding API to detect vector dimensions.
        """
        from config import settings

        provider = (settings.embedding_provider or "").strip().lower()
        if not provider:
            return None

        model = settings.embedding_model
        if not model:
            logger.warning(
                "EMBEDDING_PROVIDER is set to '%s' but EMBEDDING_MODEL is missing. "
                "Semantic search disabled.",
                provider,
            )
            return None

        api_key = settings.embedding_api_key or ""
        base_url = settings.embedding_base_url or ""

        if provider != "openai":
            logger.warning(
                "Unknown EMBEDDING_PROVIDER '%s'. Supported: 'openai'. "
                "Semantic search disabled.",
                provider,
            )
            return None

        # Auto-probe dims
        try:
            dims = await _probe_embedding_dims(api_key, base_url, model)
            logger.info(
                "Embedding auto-probe: model=%s dims=%d base_url=%s",
                model, dims, base_url or "(default)",
            )
        except Exception as e:
            logger.error(
                "Failed to probe embedding dimensions (model=%s, base_url=%s): %s. "
                "Semantic search disabled.",
                model, base_url, e,
            )
            return None

        embed_fn = _make_embed_fn(api_key, base_url, model)

        return {
            "dims": dims,
            "embed": embed_fn,
            "fields": ["text"],  # only embed the 'text' field of stored memories
        }

    async def initialize(self) -> None:
        """初始化 checkpointer 和 store（连接 PostgreSQL 并创建 schema）"""
        logger.info("Initializing PostgreSQL memory backend...")

        self._checkpointer_cm = AsyncPostgresSaver.from_conn_string(
            self._postgres_uri
        )
        self._checkpointer = await self._checkpointer_cm.__aenter__()

        # Build embedding index config (returns None if not configured)
        self._index_config = await self._build_index_config()

        store_kwargs: dict[str, Any] = {}
        if self._index_config is not None:
            store_kwargs["index"] = self._index_config

        self._store_cm = AsyncPostgresStore.from_conn_string(
            self._postgres_uri,
            **store_kwargs,
        )
        self._store = await self._store_cm.__aenter__()

        # 首次运行时创建 schema（幂等操作）
        await self._checkpointer.setup()
        await self._store.setup()

        if self._index_config:
            logger.info(
                "PostgreSQL memory backend initialized with semantic search "
                "(dims=%d, fields=%s)",
                self._index_config["dims"],
                self._index_config.get("fields", ["$"]),
            )
        else:
            logger.info(
                "PostgreSQL memory backend initialized (time-based only, no semantic search)"
            )

    @property
    def has_semantic_search(self) -> bool:
        """Whether the store is configured for semantic search."""
        return self._index_config is not None

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

    async def backfill_embeddings(self) -> int:
        """
        Backfill embeddings for existing memories that were stored before
        semantic search was enabled.

        Works by searching for all items in the 'memories' namespace prefix
        and re-putting them (with the same key) to trigger embedding generation.

        Returns:
            Number of memories backfilled.
        """
        if not self._index_config or self._store is None:
            return 0

        try:
            # Search all memories (time-based, no query)
            all_memories = await self._store.asearch(
                ("memories",), limit=1000
            )
            if not all_memories:
                logger.info("No existing memories to backfill.")
                return 0

            count = 0
            for item in all_memories:
                # Re-put the item to trigger embedding generation.
                # LangGraph will skip if embedding already exists for the same content.
                await self._store.aput(
                    item.namespace,
                    item.key,
                    item.value,
                )
                count += 1

            logger.info("Backfilled embeddings for %d existing memories.", count)
            return count
        except Exception as e:
            logger.warning("Failed to backfill embeddings: %s", e)
            return 0

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
        self._index_config = None

        if errors:
            logger.warning("Errors closing PostgreSQL memory connections: %s", "; ".join(errors))
        else:
            logger.info("PostgreSQL memory connections closed")
