"""
Tests for Cron Scheduling Enhancement

Tests the at/every/cron scheduling capabilities of the LLM agent,
including:
- schedule_llm_analysis (at mode - one-shot delay)
- schedule_llm_recurring (every/cron mode - recurring)
- Job limit enforcement (max_pending_llm_jobs shared across all types)
- Minimum interval enforcement for interval mode
- Cron expression validation
"""

import pytest
import pytz
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from datetime import datetime, timezone

from config import Settings


class TestSchedulingConfig:
    """Test new scheduling configuration fields."""

    def test_llm_min_interval_minutes_default(self):
        """Test default value for llm_min_interval_minutes."""
        from config import settings
        assert hasattr(settings, 'llm_min_interval_minutes')
        assert isinstance(settings.llm_min_interval_minutes, int)
        assert settings.llm_min_interval_minutes == 5

    def test_max_pending_llm_jobs_default(self):
        """Test max_pending_llm_jobs is still present."""
        from config import settings
        assert hasattr(settings, 'max_pending_llm_jobs')
        assert settings.max_pending_llm_jobs == 5


class TestScheduleLlmAnalysis:
    """Test TradingSystem.schedule_llm_analysis (at mode)."""

    def _make_ts(self, current_job_count=0, max_pending=5, add_job_success=True):
        """Create a mock TradingSystem with SchedulerMixin methods."""
        ts = Mock()
        ts._LLM_JOB_PREFIX = "llm_scheduled_"
        ts.count_jobs_by_prefix = Mock(return_value=current_job_count)
        ts.get_jobs_by_prefix = Mock(return_value=[])
        ts.add_delayed_job = Mock(return_value=add_job_success)

        # Bind the real method
        from agent_trader.trading_system import TradingSystem
        ts.schedule_llm_analysis = TradingSystem.schedule_llm_analysis.__get__(ts)
        ts._check_llm_job_limit = TradingSystem._check_llm_job_limit.__get__(ts)

        with patch('agent_trader.trading_system.settings') as mock_settings:
            mock_settings.max_pending_llm_jobs = max_pending
            result = ts.schedule_llm_analysis(delay_seconds=3600, reason="test")

        return result

    def test_schedule_success(self):
        """Test successful one-shot scheduling."""
        result = self._make_ts(current_job_count=0)
        assert result["success"] is True
        assert result["job_id"] is not None
        assert "job_id" in result

    def test_schedule_at_limit(self):
        """Test scheduling rejected when at limit."""
        result = self._make_ts(current_job_count=5, max_pending=5)
        assert result["success"] is False
        assert "上限" in result["message"]

    def test_schedule_add_job_failure(self):
        """Test scheduling when add_delayed_job fails."""
        result = self._make_ts(current_job_count=0, add_job_success=False)
        assert result["success"] is False


class TestScheduleLlmRecurring:
    """Test TradingSystem.schedule_llm_recurring (every/cron mode)."""

    def _make_ts(self, current_job_count=0, max_pending=5, min_interval=5):
        """Create a mock TradingSystem with recurring scheduling support."""
        ts = Mock()
        ts._LLM_JOB_PREFIX = "llm_scheduled_"
        ts._tz = pytz.timezone("US/Eastern")
        ts._exchange = "XNYS"
        ts.count_jobs_by_prefix = Mock(return_value=current_job_count)
        ts.get_jobs_by_prefix = Mock(return_value=[])
        ts.add_interval_job = Mock(return_value=True)
        ts._add_job = Mock(return_value=True)

        from agent_trader.trading_system import TradingSystem
        ts.schedule_llm_recurring = TradingSystem.schedule_llm_recurring.__get__(ts)
        ts._check_llm_job_limit = TradingSystem._check_llm_job_limit.__get__(ts)

        return ts, max_pending, min_interval

    def test_interval_success(self):
        """Test successful interval scheduling."""
        ts, max_pending, min_interval = self._make_ts()
        with patch('agent_trader.trading_system.settings') as mock_s:
            mock_s.max_pending_llm_jobs = max_pending
            mock_s.llm_min_interval_minutes = min_interval
            result = ts.schedule_llm_recurring(
                schedule_kind="interval",
                reason="monitor volatility",
                interval_minutes=15,
            )
        assert result["success"] is True
        assert "job_id" in result

    def test_interval_below_minimum(self):
        """Test interval rejected when below minimum."""
        ts, max_pending, min_interval = self._make_ts()
        with patch('agent_trader.trading_system.settings') as mock_s:
            mock_s.max_pending_llm_jobs = max_pending
            mock_s.llm_min_interval_minutes = min_interval
            result = ts.schedule_llm_recurring(
                schedule_kind="interval",
                reason="too fast",
                interval_minutes=2,
            )
        assert result["success"] is False
        assert "最小间隔" in result["message"]

    def test_cron_success(self):
        """Test successful cron scheduling."""
        ts, max_pending, min_interval = self._make_ts()
        with patch('agent_trader.trading_system.settings') as mock_s:
            mock_s.max_pending_llm_jobs = max_pending
            mock_s.llm_min_interval_minutes = min_interval
            mock_s.trading_timezone = "US/Eastern"
            result = ts.schedule_llm_recurring(
                schedule_kind="cron",
                reason="daily check",
                cron_expr="0 9 * * mon-fri",
            )
        assert result["success"] is True

    def test_cron_empty_expression(self):
        """Test cron rejected with empty expression."""
        ts, max_pending, min_interval = self._make_ts()
        with patch('agent_trader.trading_system.settings') as mock_s:
            mock_s.max_pending_llm_jobs = max_pending
            mock_s.llm_min_interval_minutes = min_interval
            result = ts.schedule_llm_recurring(
                schedule_kind="cron",
                reason="bad cron",
                cron_expr="",
            )
        assert result["success"] is False

    def test_cron_invalid_expression(self):
        """Test cron rejected with invalid expression."""
        ts, max_pending, min_interval = self._make_ts()
        with patch('agent_trader.trading_system.settings') as mock_s:
            mock_s.max_pending_llm_jobs = max_pending
            mock_s.llm_min_interval_minutes = min_interval
            mock_s.trading_timezone = "US/Eastern"
            result = ts.schedule_llm_recurring(
                schedule_kind="cron",
                reason="bad cron",
                cron_expr="invalid",
            )
        assert result["success"] is False

    def test_unsupported_schedule_kind(self):
        """Test unsupported schedule_kind is rejected."""
        ts, max_pending, min_interval = self._make_ts()
        with patch('agent_trader.trading_system.settings') as mock_s:
            mock_s.max_pending_llm_jobs = max_pending
            mock_s.llm_min_interval_minutes = min_interval
            result = ts.schedule_llm_recurring(
                schedule_kind="weekly",
                reason="bad kind",
            )
        assert result["success"] is False
        assert "不支持" in result["message"]

    def test_shared_limit_with_at(self):
        """Test that recurring jobs share the same limit as at jobs."""
        ts, _, _ = self._make_ts(current_job_count=5, max_pending=5)
        with patch('agent_trader.trading_system.settings') as mock_s:
            mock_s.max_pending_llm_jobs = 5
            mock_s.llm_min_interval_minutes = 5
            result = ts.schedule_llm_recurring(
                schedule_kind="interval",
                reason="should fail",
                interval_minutes=15,
            )
        assert result["success"] is False
        assert "上限" in result["message"]


class TestScheduleToolInterface:
    """Test the schedule_next_analysis tool's at/every/cron interface."""

    def test_tool_has_schedule_kind_param(self):
        """Test that the tool accepts schedule_kind parameter."""
        from agent_trader.agents.tools.system_tools import _create_schedule_next_analysis

        wf = Mock()
        wf._trading_system = None
        wf.message_manager = AsyncMock()
        tool = _create_schedule_next_analysis(wf)

        # Check tool has the expected parameter
        schema = tool.args_schema
        if schema:
            fields = schema.model_fields if hasattr(schema, 'model_fields') else {}
            assert 'schedule_kind' in fields


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
