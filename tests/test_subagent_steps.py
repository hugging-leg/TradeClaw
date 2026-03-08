"""
Tests for SubAgent nested step emission (parent_step_id).

Verifies that:
- emit_step accepts and propagates parent_step_id
- SubAgent child steps are emitted with correct parent_step_id
- Frontend can reconstruct the parent-child hierarchy
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, Optional


def _make_workflow(workflow_id: str = "test-wf"):
    """Create a minimal concrete WorkflowBase instance for testing."""
    from agent_trader.agents.workflow_base import WorkflowBase

    # Create a concrete subclass to avoid abstract class issues
    class _TestWorkflow(WorkflowBase):
        def _default_config(self) -> Dict[str, Any]:
            return {}

        async def run_workflow(self, initial_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            return {}

    # Bypass __init__ by creating instance directly
    wf = object.__new__(_TestWorkflow)
    wf.workflow_id = workflow_id
    wf._current_steps = []
    return wf


class TestEmitStepParentId:
    """Test that emit_step correctly handles parent_step_id."""

    def test_emit_step_without_parent(self):
        """emit_step without parent_step_id should not include it in event."""
        wf = _make_workflow("test-wf-1")

        with patch('agent_trader.agents.workflow_base.event_broadcaster') as mock_bc:
            step_id = wf.emit_step("tool_call", "get_prices", "running")

            assert step_id == "test-wf-1-0"
            emitted = mock_bc.emit.call_args[0][0]
            assert emitted["event"] == "step"
            assert "parent_step_id" not in emitted["data"]

    def test_emit_step_with_parent(self):
        """emit_step with parent_step_id should include it in event."""
        wf = _make_workflow("test-wf-2")

        with patch('agent_trader.agents.workflow_base.event_broadcaster') as mock_bc:
            step_id = wf.emit_step(
                "subagent_thinking", "SubAgent 思考中", "running",
                parent_step_id="test-wf-2-parent",
            )

            assert step_id == "test-wf-2-0"
            emitted = mock_bc.emit.call_args[0][0]
            assert emitted["data"]["parent_step_id"] == "test-wf-2-parent"

    def test_emit_step_parent_stored_in_steps(self):
        """parent_step_id should be stored in _current_steps."""
        wf = _make_workflow("test-wf-3")

        with patch('agent_trader.agents.workflow_base.event_broadcaster'):
            parent_id = wf.emit_step("subagent", "SubAgent: Analysis", "running")

            child_id = wf.emit_step(
                "subagent_thinking", "Thinking...", "running",
                parent_step_id=parent_id,
            )

            assert len(wf._current_steps) == 2
            assert "parent_step_id" not in wf._current_steps[0]
            assert wf._current_steps[1]["parent_step_id"] == parent_id


class TestStepHierarchyReconstruction:
    """Test that parent-child hierarchy can be reconstructed from flat step list."""

    def test_group_children_by_parent(self):
        """Simulate frontend grouping logic."""
        steps = [
            {"id": "wf-0", "type": "llm_thinking", "name": "Thinking"},
            {"id": "wf-1", "type": "subagent", "name": "SubAgent: Tech Analysis"},
            {"id": "wf-2", "type": "subagent_thinking", "name": "SA Thinking", "parent_step_id": "wf-1"},
            {"id": "wf-3", "type": "subagent_tool_call", "name": "get_prices", "parent_step_id": "wf-1"},
            {"id": "wf-4", "type": "subagent", "name": "SubAgent: Fundamental"},
            {"id": "wf-5", "type": "subagent_thinking", "name": "SA Thinking 2", "parent_step_id": "wf-4"},
            {"id": "wf-6", "type": "llm_thinking", "name": "Final analysis"},
        ]

        # Reconstruct hierarchy (same logic as frontend)
        top_level = [s for s in steps if "parent_step_id" not in s]
        child_map: dict[str, list] = {}
        for s in steps:
            pid = s.get("parent_step_id")
            if pid:
                child_map.setdefault(pid, []).append(s)

        assert len(top_level) == 4  # thinking, subagent1, subagent2, final thinking
        assert len(child_map["wf-1"]) == 2  # thinking + tool_call
        assert len(child_map["wf-4"]) == 1  # thinking only
        assert "wf-0" not in child_map
        assert "wf-6" not in child_map


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
