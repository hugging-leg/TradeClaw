"""
Tests for SubAgent Parallel Execution Engine

Tests the SubAgent system including:
- SubAgentExecutor creation and tool filtering
- Depth limit enforcement
- Parallel limit enforcement
- SubAgentTask / SubAgentResult dataclasses
- Write tool exclusion
"""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from dataclasses import asdict

from agent_trader.agents.subagent import (
    SubAgentExecutor,
    SubAgentTask,
    SubAgentResult,
    _WRITE_TOOL_NAMES,
)


class TestSubAgentDataclasses:
    """Test SubAgentTask and SubAgentResult dataclasses."""

    def test_subagent_task_defaults(self):
        """Test SubAgentTask default values."""
        task = SubAgentTask(task_id="t1", task="Analyze NVDA")
        assert task.task_id == "t1"
        assert task.task == "Analyze NVDA"
        assert task.timeout_seconds == 600
        assert task.max_iterations == 100

    def test_subagent_task_custom(self):
        """Test SubAgentTask with custom values."""
        task = SubAgentTask(
            task_id="t2",
            task="Deep analysis",
            timeout_seconds=300,
            max_iterations=50,
        )
        assert task.timeout_seconds == 300
        assert task.max_iterations == 50

    def test_subagent_result_success(self):
        """Test SubAgentResult for success case."""
        result = SubAgentResult(
            task_id="t1",
            status="success",
            output="NVDA looks bullish",
            tool_calls=["get_market_data", "get_historical_prices"],
            duration_ms=5000,
        )
        assert result.status == "success"
        assert result.error is None
        assert len(result.tool_calls) == 2

    def test_subagent_result_failure(self):
        """Test SubAgentResult for failure case."""
        result = SubAgentResult(
            task_id="t1",
            status="failed",
            output="",
            error="LLM API error",
            duration_ms=1000,
        )
        assert result.status == "failed"
        assert result.error is not None


class TestWriteToolExclusion:
    """Test that write tools are correctly excluded."""

    def test_write_tool_names_defined(self):
        """Test that _WRITE_TOOL_NAMES contains expected tools."""
        assert "rebalance_portfolio" in _WRITE_TOOL_NAMES
        assert "adjust_position" in _WRITE_TOOL_NAMES
        assert "schedule_next_analysis" in _WRITE_TOOL_NAMES
        assert "spawn_subagent" in _WRITE_TOOL_NAMES
        assert "spawn_parallel_subagents" in _WRITE_TOOL_NAMES

    def test_readonly_tools_filter(self):
        """Test that SubAgentExecutor correctly filters out write tools."""
        # Create mock workflow with tools
        wf = Mock()
        mock_tools = []
        for name in ["get_market_data", "get_portfolio_status", "rebalance_portfolio",
                      "spawn_subagent", "get_latest_news"]:
            t = Mock()
            t.name = name
            mock_tools.append(t)
        wf.tools = mock_tools

        with patch('agent_trader.agents.subagent.settings') as mock_s:
            mock_s.subagent_max_depth = 2
            mock_s.subagent_max_parallel = 5
            executor = SubAgentExecutor(parent_workflow=wf, depth=1)

        readonly = executor._get_readonly_tools()
        readonly_names = {t.name for t in readonly}

        assert "get_market_data" in readonly_names
        assert "get_portfolio_status" in readonly_names
        assert "get_latest_news" in readonly_names
        assert "rebalance_portfolio" not in readonly_names
        assert "spawn_subagent" not in readonly_names


class TestSubAgentExecutorLimits:
    """Test SubAgentExecutor depth and parallel limits."""

    def _make_executor(self, depth=1, max_depth=2, max_parallel=5):
        """Create a SubAgentExecutor with specified limits."""
        wf = Mock()
        wf.tools = []
        wf.llm = Mock()
        wf.store = Mock()
        wf.emit_step = Mock(return_value="step-1")
        wf.update_step = Mock()

        with patch('agent_trader.agents.subagent.settings') as mock_s:
            mock_s.subagent_max_depth = max_depth
            mock_s.subagent_max_parallel = max_parallel
            executor = SubAgentExecutor(parent_workflow=wf, depth=depth)

        return executor

    @pytest.mark.asyncio
    async def test_depth_limit_exceeded(self):
        """Test that exceeding depth limit returns failure."""
        executor = self._make_executor(depth=2, max_depth=2)

        tasks = [SubAgentTask(task_id="t1", task="test")]
        results = await executor.run_subagents(tasks)

        assert len(results) == 1
        assert results[0].status == "failed"
        assert "深度" in results[0].error

    @pytest.mark.asyncio
    async def test_parallel_limit_truncation(self):
        """Test that tasks exceeding parallel limit are truncated."""
        executor = self._make_executor(depth=1, max_depth=3, max_parallel=2)

        tasks = [
            SubAgentTask(task_id=f"t{i}", task=f"task {i}")
            for i in range(5)
        ]

        # Mock _run_single to avoid actual agent execution
        async def mock_run_single(task):
            return SubAgentResult(
                task_id=task.task_id,
                status="success",
                output="done",
                duration_ms=100,
            )

        executor._run_single = mock_run_single
        results = await executor.run_subagents(tasks)

        # Should only execute max_parallel tasks
        assert len(results) == 2


class TestSubAgentConfig:
    """Test subagent configuration settings."""

    def test_subagent_max_depth_default(self):
        """Test default value for subagent_max_depth."""
        from config import settings
        assert hasattr(settings, 'subagent_max_depth')
        assert settings.subagent_max_depth == 2

    def test_subagent_max_parallel_default(self):
        """Test default value for subagent_max_parallel."""
        from config import settings
        assert hasattr(settings, 'subagent_max_parallel')
        assert settings.subagent_max_parallel == 5

    def test_subagent_default_timeout(self):
        """Test default value for subagent_default_timeout."""
        from config import settings
        assert hasattr(settings, 'subagent_default_timeout')
        assert settings.subagent_default_timeout == 600


class TestSubAgentToolRegistration:
    """Test that subagent tools are registered in system_tools."""

    def test_spawn_subagent_tool_created(self):
        """Test spawn_subagent tool is created."""
        from agent_trader.agents.tools.system_tools import create_system_tools

        wf = Mock()
        wf._trading_system = None
        wf.message_manager = AsyncMock()
        wf.tools = []
        wf.llm = Mock()
        wf.store = Mock()
        wf.emit_step = Mock()
        wf.update_step = Mock()

        tools = create_system_tools(wf)
        tool_names = [t[0].name for t in tools]

        assert "spawn_subagent" in tool_names
        assert "spawn_parallel_subagents" in tool_names

    def test_tools_in_system_category(self):
        """Test subagent tools are in 'system' category."""
        from agent_trader.agents.tools.system_tools import create_system_tools

        wf = Mock()
        wf._trading_system = None
        wf.message_manager = AsyncMock()

        tools = create_system_tools(wf)
        subagent_tools = [
            (name, cat) for (t, cat) in tools
            if (name := getattr(t, 'name', '')) in ('spawn_subagent', 'spawn_parallel_subagents')
        ]
        for name, cat in subagent_tools:
            assert cat == "system"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
