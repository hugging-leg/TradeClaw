"""
Tests for Memory Semantic Search Integration

Tests:
- Embedding config building (_build_index_config)
- Hybrid recall logic (_recall_memories with query)
- Backfill logic
- Memory API endpoints
- Config fields
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from dataclasses import dataclass
from typing import Any, Optional


# ========== Config Tests ==========


class TestEmbeddingConfig:
    """Test embedding configuration fields in Settings."""

    def test_embedding_fields_exist(self):
        """Test that embedding fields are present in Settings."""
        from config import settings

        assert hasattr(settings, "embedding_provider")
        assert hasattr(settings, "embedding_api_key")
        assert hasattr(settings, "embedding_base_url")
        assert hasattr(settings, "embedding_model")

    def test_embedding_fields_default_none(self):
        """Test that embedding fields default to None."""
        from config import Settings

        s = Settings(
            _env_file=None,
            alpaca_api_key="x",
            alpaca_secret_key="x",
        )
        assert s.embedding_provider is None
        assert s.embedding_api_key is None
        assert s.embedding_base_url is None
        assert s.embedding_model is None

    def test_embedding_fields_in_readable_settings(self):
        """Test that embedding fields appear in the API readable fields."""
        from agent_trader.api.routes.settings import _READABLE_FIELDS

        assert "embedding_provider" in _READABLE_FIELDS
        assert "embedding_base_url" in _READABLE_FIELDS
        assert "embedding_model" in _READABLE_FIELDS

    def test_embedding_api_key_is_write_only(self):
        """Test that embedding_api_key is write-only (not readable via API)."""
        from agent_trader.api.routes.settings import _WRITE_ONLY_FIELDS

        assert "embedding_api_key" in _WRITE_ONLY_FIELDS


# ========== MemoryManager Tests ==========


class TestBuildIndexConfig:
    """Test _build_index_config in MemoryManager."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_provider(self):
        """Should return None when EMBEDDING_PROVIDER is not set."""
        from agent_trader.memory.manager import MemoryManager

        mgr = MemoryManager(postgres_uri="postgresql://test:test@localhost/test")
        with patch("config.settings") as mock_settings:
            mock_settings.embedding_provider = None
            mock_settings.embedding_model = "text-embedding-v3"
            mock_settings.embedding_api_key = "sk-test"
            mock_settings.embedding_base_url = "https://example.com/v1"
            result = await mgr._build_index_config()
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_model(self):
        """Should return None when EMBEDDING_MODEL is missing."""
        from agent_trader.memory.manager import MemoryManager

        mgr = MemoryManager(postgres_uri="postgresql://test:test@localhost/test")
        with patch("config.settings") as mock_settings:
            mock_settings.embedding_provider = "openai"
            mock_settings.embedding_model = None
            mock_settings.embedding_api_key = "sk-test"
            mock_settings.embedding_base_url = "https://example.com/v1"
            result = await mgr._build_index_config()
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_provider(self):
        """Should return None for an unknown provider."""
        from agent_trader.memory.manager import MemoryManager

        mgr = MemoryManager(postgres_uri="postgresql://test:test@localhost/test")
        with patch("config.settings") as mock_settings:
            mock_settings.embedding_provider = "unknown_provider"
            mock_settings.embedding_model = "some-model"
            mock_settings.embedding_api_key = "sk-test"
            mock_settings.embedding_base_url = "https://example.com/v1"
            result = await mgr._build_index_config()
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_config_on_successful_probe(self):
        """Should return valid IndexConfig when probe succeeds."""
        from agent_trader.memory.manager import MemoryManager

        mgr = MemoryManager(postgres_uri="postgresql://test:test@localhost/test")

        # Mock the probe to return 1024 dims
        with patch("config.settings") as mock_settings, \
             patch("agent_trader.memory.manager._probe_embedding_dims", new_callable=AsyncMock) as mock_probe:
            mock_settings.embedding_provider = "openai"
            mock_settings.embedding_model = "text-embedding-v3"
            mock_settings.embedding_api_key = "sk-test"
            mock_settings.embedding_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            mock_probe.return_value = 1024

            result = await mgr._build_index_config()

        assert result is not None
        assert result["dims"] == 1024
        assert result["fields"] == ["text"]
        assert callable(result["embed"])

    @pytest.mark.asyncio
    async def test_returns_none_on_probe_failure(self):
        """Should return None if probe fails (e.g., invalid API key)."""
        from agent_trader.memory.manager import MemoryManager

        mgr = MemoryManager(postgres_uri="postgresql://test:test@localhost/test")

        with patch("config.settings") as mock_settings, \
             patch("agent_trader.memory.manager._probe_embedding_dims", new_callable=AsyncMock) as mock_probe:
            mock_settings.embedding_provider = "openai"
            mock_settings.embedding_model = "text-embedding-v3"
            mock_settings.embedding_api_key = "invalid-key"
            mock_settings.embedding_base_url = "https://example.com/v1"
            mock_probe.side_effect = Exception("401 Unauthorized")

            result = await mgr._build_index_config()

        assert result is None


class TestHasSemanticSearch:
    """Test has_semantic_search property."""

    def test_false_when_no_index_config(self):
        from agent_trader.memory.manager import MemoryManager

        mgr = MemoryManager(postgres_uri="postgresql://test:test@localhost/test")
        mgr._index_config = None
        assert mgr.has_semantic_search is False

    def test_true_when_index_config_set(self):
        from agent_trader.memory.manager import MemoryManager

        mgr = MemoryManager(postgres_uri="postgresql://test:test@localhost/test")
        mgr._index_config = {"dims": 1024, "embed": lambda x: x, "fields": ["text"]}
        assert mgr.has_semantic_search is True


# ========== Hybrid Recall Tests ==========


@dataclass
class MockItem:
    """Mock LangGraph store search result item."""
    key: str
    value: dict
    namespace: tuple = ("memories", "test")
    score: Optional[float] = None


class TestHybridRecall:
    """Test _recall_memories hybrid (semantic + recent) strategy."""

    def _make_workflow(self, store, has_index=True):
        """Create a minimal WorkflowBase subclass for testing."""
        from agent_trader.agents.workflow_base import WorkflowBase

        class TestWorkflow(WorkflowBase):
            _workflow_metadata = {"type": "test_workflow"}

            def _default_config(self):
                return {}

            async def run_workflow(self, initial_context=None):
                return {"success": True}

        # Create with mocks
        mock_mm = MagicMock()
        wf = TestWorkflow.__new__(TestWorkflow)
        wf.store = store
        wf.checkpointer = None
        wf.broker_api = MagicMock()
        wf.market_data_api = MagicMock()
        wf.news_api = MagicMock()
        wf.message_manager = MagicMock()
        wf._config = {}
        wf.is_running = False
        wf.current_portfolio = None
        wf.supports_realtime_monitoring = True
        wf.stats = {}
        wf.llm = None
        wf.agent = None
        wf.tool_registry = None
        wf.tools = []
        wf.session_id = "test"
        wf.workflow_id = ""
        wf.start_time = None
        wf.end_time = None
        wf._current_trigger = ""
        wf._current_steps = []
        wf._user_message_queue = asyncio.Queue()
        wf._backtest_mode = False
        wf._strategy_positions_mem = []
        wf._strategy_pos_counter = 0

        # Set index_config on store mock
        if has_index:
            store.index_config = {"dims": 1024}
        else:
            store.index_config = None

        return wf

    @pytest.mark.asyncio
    async def test_fallback_to_time_based_when_no_query(self):
        """Without query, should use time-based retrieval only."""
        store = AsyncMock()
        items = [
            MockItem(key="m1", value={"date": "2025-01-01", "text": "Memory 1"}),
            MockItem(key="m2", value={"date": "2025-01-02", "text": "Memory 2"}),
        ]
        store.asearch = AsyncMock(return_value=items)

        wf = self._make_workflow(store, has_index=True)
        result = await wf._recall_memories(query="", limit=10)

        # Should call asearch once (no query)
        store.asearch.assert_called_once()
        assert "Memory 1" in result
        assert "Memory 2" in result

    @pytest.mark.asyncio
    async def test_fallback_when_no_index_config(self):
        """Without index_config, should use time-based retrieval even with query."""
        store = AsyncMock()
        items = [
            MockItem(key="m1", value={"date": "2025-01-01", "text": "Memory 1"}),
        ]
        store.asearch = AsyncMock(return_value=items)

        wf = self._make_workflow(store, has_index=False)
        result = await wf._recall_memories(query="trading", limit=10)

        # Should call asearch once (no semantic search)
        store.asearch.assert_called_once()
        assert "Memory 1" in result

    @pytest.mark.asyncio
    async def test_hybrid_deduplication(self):
        """Hybrid recall should deduplicate results from semantic + recent."""
        store = AsyncMock()

        semantic_items = [
            MockItem(key="m1", value={"date": "2025-01-01", "text": "Semantic hit"}),
            MockItem(key="m2", value={"date": "2025-01-02", "text": "Also semantic"}),
        ]
        recent_items = [
            MockItem(key="m2", value={"date": "2025-01-02", "text": "Also semantic"}),  # duplicate
            MockItem(key="m3", value={"date": "2025-01-03", "text": "Recent only"}),
        ]

        # First call = semantic, second call = recent
        store.asearch = AsyncMock(side_effect=[semantic_items, recent_items])

        wf = self._make_workflow(store, has_index=True)
        result = await wf._recall_memories(query="portfolio analysis", limit=10)

        # Should have 3 unique memories (m2 deduplicated)
        assert result.count("[") == 3  # 3 date markers
        assert "Semantic hit" in result
        assert "Also semantic" in result
        assert "Recent only" in result

    @pytest.mark.asyncio
    async def test_semantic_failure_falls_back(self):
        """If semantic search raises, should fall back to recent-only."""
        store = AsyncMock()

        recent_items = [
            MockItem(key="m1", value={"date": "2025-01-01", "text": "Fallback memory"}),
        ]

        # First call (semantic) raises, second call (recent) succeeds
        store.asearch = AsyncMock(side_effect=[Exception("Embedding error"), recent_items])

        wf = self._make_workflow(store, has_index=True)
        result = await wf._recall_memories(query="test query", limit=10)

        assert "Fallback memory" in result

    @pytest.mark.asyncio
    async def test_empty_store(self):
        """Should return empty string when store has no memories."""
        store = AsyncMock()
        store.asearch = AsyncMock(return_value=[])

        wf = self._make_workflow(store, has_index=True)
        result = await wf._recall_memories(query="anything", limit=10)

        assert result == ""


# ========== Backfill Tests ==========


class TestBackfillEmbeddings:
    """Test backfill_embeddings in MemoryManager."""

    @pytest.mark.asyncio
    async def test_backfill_skipped_without_index(self):
        """Should return 0 when no index config."""
        from agent_trader.memory.manager import MemoryManager

        mgr = MemoryManager(postgres_uri="postgresql://test:test@localhost/test")
        mgr._index_config = None
        mgr._store = AsyncMock()

        count = await mgr.backfill_embeddings()
        assert count == 0

    @pytest.mark.asyncio
    async def test_backfill_reputs_existing_memories(self):
        """Should re-put all existing memories to trigger embedding."""
        from agent_trader.memory.manager import MemoryManager

        mgr = MemoryManager(postgres_uri="postgresql://test:test@localhost/test")
        mgr._index_config = {"dims": 1024, "embed": lambda x: x, "fields": ["text"]}

        mock_store = AsyncMock()
        mock_items = [
            MockItem(key="m1", value={"text": "First memory", "date": "2025-01-01"}),
            MockItem(key="m2", value={"text": "Second memory", "date": "2025-01-02"}),
        ]
        mock_store.asearch = AsyncMock(return_value=mock_items)
        mock_store.aput = AsyncMock()
        mgr._store = mock_store

        count = await mgr.backfill_embeddings()

        assert count == 2
        assert mock_store.aput.call_count == 2

    @pytest.mark.asyncio
    async def test_backfill_handles_error_gracefully(self):
        """Should return 0 on error without crashing."""
        from agent_trader.memory.manager import MemoryManager

        mgr = MemoryManager(postgres_uri="postgresql://test:test@localhost/test")
        mgr._index_config = {"dims": 1024, "embed": lambda x: x, "fields": ["text"]}

        mock_store = AsyncMock()
        mock_store.asearch = AsyncMock(side_effect=Exception("DB connection error"))
        mgr._store = mock_store

        count = await mgr.backfill_embeddings()
        assert count == 0

    @pytest.mark.asyncio
    async def test_backfill_empty_store(self):
        """Should return 0 when store is empty."""
        from agent_trader.memory.manager import MemoryManager

        mgr = MemoryManager(postgres_uri="postgresql://test:test@localhost/test")
        mgr._index_config = {"dims": 1024, "embed": lambda x: x, "fields": ["text"]}

        mock_store = AsyncMock()
        mock_store.asearch = AsyncMock(return_value=[])
        mgr._store = mock_store

        count = await mgr.backfill_embeddings()
        assert count == 0


# ========== Docker Image Tests ==========


class TestDockerImages:
    """Test that docker-compose files use pgvector image."""

    def test_compose_prod_uses_pgvector(self):
        """docker-compose.yml should use pgvector/pgvector:pg16."""
        import os
        compose_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "docker-compose.yml",
        )
        with open(compose_path) as f:
            content = f.read()
        assert "pgvector/pgvector:pg16" in content
        assert "postgres:16-alpine" not in content

    def test_compose_dev_uses_pgvector(self):
        """docker-compose.dev.yml should use pgvector/pgvector:pg16."""
        import os
        compose_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "docker-compose.dev.yml",
        )
        with open(compose_path) as f:
            content = f.read()
        assert "pgvector/pgvector:pg16" in content
        assert "postgres:16-alpine" not in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
