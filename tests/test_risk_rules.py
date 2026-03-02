"""
Tests for Risk Rules Configuration System

Tests the configurable risk rule chain including:
- RiskRule and RiskRulesConfig models
- RiskRulesManager loading, saving, CRUD
- Default rule creation and migration
"""

import pytest
import yaml
from pathlib import Path

from agent_trader.config.risk_rules import (
    RiskRule,
    RiskRulesConfig,
    RiskRulesManager,
    RuleType,
    RuleAction,
    _default_rules,
)


class TestRuleEnums:
    """Test RuleType and RuleAction enums"""

    def test_rule_types(self):
        assert RuleType.HARD_STOP_LOSS.value == "hard_stop_loss"
        assert RuleType.HARD_TAKE_PROFIT.value == "hard_take_profit"
        assert RuleType.TRAILING_STOP.value == "trailing_stop"
        assert RuleType.LLM_STOP_LOSS.value == "llm_stop_loss"
        assert RuleType.LLM_TAKE_PROFIT.value == "llm_take_profit"
        assert RuleType.DAILY_LOSS_LIMIT.value == "daily_loss_limit"
        assert RuleType.CONCENTRATION_LIMIT.value == "concentration_limit"

    def test_rule_actions(self):
        assert RuleAction.CLOSE.value == "close"
        assert RuleAction.LLM_ANALYZE.value == "llm_analyze"
        assert RuleAction.ALERT.value == "alert"
        assert RuleAction.REDUCE.value == "reduce"


class TestRiskRule:
    """Test RiskRule Pydantic model"""

    def test_rule_creation(self):
        rule = RiskRule(
            name="test_sl",
            type=RuleType.HARD_STOP_LOSS,
            threshold=0.05,
            action=RuleAction.CLOSE,
        )
        assert rule.name == "test_sl"
        assert rule.type == RuleType.HARD_STOP_LOSS
        assert rule.threshold == 0.05
        assert rule.action == RuleAction.CLOSE
        assert rule.enabled is True
        assert rule.priority == 100

    def test_rule_with_symbols(self):
        rule = RiskRule(
            name="test_tp",
            type=RuleType.HARD_TAKE_PROFIT,
            threshold=0.15,
            action=RuleAction.CLOSE,
            symbols=["AAPL", "MSFT"],
        )
        assert rule.symbols == ["AAPL", "MSFT"]

    def test_rule_with_custom_priority(self):
        rule = RiskRule(
            name="high_priority",
            type=RuleType.DAILY_LOSS_LIMIT,
            threshold=0.10,
            action=RuleAction.ALERT,
            priority=5,
        )
        assert rule.priority == 5

    def test_rule_with_reduce_action(self):
        rule = RiskRule(
            name="reduce_rule",
            type=RuleType.CONCENTRATION_LIMIT,
            threshold=0.25,
            action=RuleAction.REDUCE,
            reduce_ratio=0.3,
        )
        assert rule.action == RuleAction.REDUCE
        assert rule.reduce_ratio == 0.3

    def test_llm_analyze_rule(self):
        rule = RiskRule(
            name="llm_sl",
            type=RuleType.LLM_STOP_LOSS,
            threshold=0.03,
            action=RuleAction.LLM_ANALYZE,
        )
        assert rule.action == RuleAction.LLM_ANALYZE


class TestRiskRulesConfig:
    """Test RiskRulesConfig model"""

    def test_config_creation(self):
        config = RiskRulesConfig(
            rules=[
                RiskRule(name="sl", type=RuleType.HARD_STOP_LOSS, threshold=0.05, action=RuleAction.CLOSE),
                RiskRule(name="tp", type=RuleType.HARD_TAKE_PROFIT, threshold=0.15, action=RuleAction.CLOSE),
            ]
        )
        assert config.version == "1"
        assert len(config.rules) == 2

    def test_empty_config(self):
        config = RiskRulesConfig()
        assert len(config.rules) == 0


class TestDefaultRules:
    """Test default rule generation"""

    def test_default_rules_count(self):
        rules = _default_rules()
        assert len(rules) == 6

    def test_default_rules_types(self):
        rules = _default_rules()
        types = {r.type for r in rules}
        assert RuleType.HARD_STOP_LOSS in types
        assert RuleType.HARD_TAKE_PROFIT in types
        assert RuleType.LLM_STOP_LOSS in types
        assert RuleType.LLM_TAKE_PROFIT in types
        assert RuleType.DAILY_LOSS_LIMIT in types
        assert RuleType.CONCENTRATION_LIMIT in types

    def test_default_rules_all_enabled(self):
        rules = _default_rules()
        assert all(r.enabled for r in rules)


class TestRiskRulesManager:
    """Test RiskRulesManager"""

    @pytest.fixture
    def tmp_config_path(self, tmp_path):
        return tmp_path / "risk_rules.yaml"

    @pytest.fixture
    def sample_config_data(self):
        return {
            "version": "1",
            "rules": [
                {
                    "name": "custom_sl",
                    "type": "hard_stop_loss",
                    "threshold": 0.03,
                    "action": "close",
                    "enabled": True,
                    "priority": 10,
                },
                {
                    "name": "custom_tp",
                    "type": "hard_take_profit",
                    "threshold": 0.20,
                    "action": "close",
                    "enabled": True,
                    "priority": 10,
                },
                {
                    "name": "llm_trigger",
                    "type": "llm_stop_loss",
                    "threshold": 0.02,
                    "action": "llm_analyze",
                    "enabled": True,
                    "priority": 50,
                },
            ],
        }

    def test_load_from_yaml(self, tmp_config_path, sample_config_data):
        """Test loading rules from YAML"""
        with open(tmp_config_path, "w") as f:
            yaml.safe_dump(sample_config_data, f)

        manager = RiskRulesManager(config_path=tmp_config_path)
        rules = manager.get_rules()
        assert len(rules) == 3

    def test_get_enabled_rules_sorted(self, tmp_config_path, sample_config_data):
        """Test getting enabled rules sorted by priority"""
        with open(tmp_config_path, "w") as f:
            yaml.safe_dump(sample_config_data, f)

        manager = RiskRulesManager(config_path=tmp_config_path)
        enabled = manager.get_enabled_rules()
        assert len(enabled) == 3
        # Should be sorted by priority
        priorities = [r.priority for r in enabled]
        assert priorities == sorted(priorities)

    def test_get_rule_by_name(self, tmp_config_path, sample_config_data):
        """Test getting a specific rule by name"""
        with open(tmp_config_path, "w") as f:
            yaml.safe_dump(sample_config_data, f)

        manager = RiskRulesManager(config_path=tmp_config_path)
        rule = manager.get_rule("custom_sl")
        assert rule is not None
        assert rule.name == "custom_sl"
        assert rule.type == RuleType.HARD_STOP_LOSS

    def test_get_rule_not_found(self, tmp_config_path, sample_config_data):
        """Test getting a rule that doesn't exist"""
        with open(tmp_config_path, "w") as f:
            yaml.safe_dump(sample_config_data, f)

        manager = RiskRulesManager(config_path=tmp_config_path)
        rule = manager.get_rule("nonexistent")
        assert rule is None

    def test_add_rule(self, tmp_config_path, sample_config_data):
        """Test adding a new rule"""
        with open(tmp_config_path, "w") as f:
            yaml.safe_dump(sample_config_data, f)

        manager = RiskRulesManager(config_path=tmp_config_path)
        new_rule = manager.add_rule({
            "name": "new_alert",
            "type": "daily_loss_limit",
            "threshold": 0.08,
            "action": "alert",
        })
        assert new_rule.name == "new_alert"
        assert len(manager.get_rules()) == 4

    def test_add_duplicate_rule_raises(self, tmp_config_path, sample_config_data):
        """Test that adding a duplicate rule raises ValueError"""
        with open(tmp_config_path, "w") as f:
            yaml.safe_dump(sample_config_data, f)

        manager = RiskRulesManager(config_path=tmp_config_path)
        with pytest.raises(ValueError, match="already exists"):
            manager.add_rule({
                "name": "custom_sl",
                "type": "hard_stop_loss",
                "threshold": 0.10,
                "action": "close",
            })

    def test_update_rule(self, tmp_config_path, sample_config_data):
        """Test updating an existing rule"""
        with open(tmp_config_path, "w") as f:
            yaml.safe_dump(sample_config_data, f)

        manager = RiskRulesManager(config_path=tmp_config_path)
        updated = manager.update_rule("custom_sl", {"threshold": 0.10, "enabled": False})
        assert updated.threshold == 0.10
        assert updated.enabled is False
        assert updated.name == "custom_sl"

    def test_update_rule_not_found(self, tmp_config_path, sample_config_data):
        """Test updating a rule that doesn't exist"""
        with open(tmp_config_path, "w") as f:
            yaml.safe_dump(sample_config_data, f)

        manager = RiskRulesManager(config_path=tmp_config_path)
        with pytest.raises(ValueError, match="not found"):
            manager.update_rule("nonexistent", {"threshold": 0.10})

    def test_delete_rule(self, tmp_config_path, sample_config_data):
        """Test deleting a rule"""
        with open(tmp_config_path, "w") as f:
            yaml.safe_dump(sample_config_data, f)

        manager = RiskRulesManager(config_path=tmp_config_path)
        assert manager.delete_rule("custom_sl") is True
        assert len(manager.get_rules()) == 2
        assert manager.get_rule("custom_sl") is None

    def test_delete_rule_not_found(self, tmp_config_path, sample_config_data):
        """Test deleting a rule that doesn't exist"""
        with open(tmp_config_path, "w") as f:
            yaml.safe_dump(sample_config_data, f)

        manager = RiskRulesManager(config_path=tmp_config_path)
        assert manager.delete_rule("nonexistent") is False

    def test_replace_all(self, tmp_config_path, sample_config_data):
        """Test replacing all rules"""
        with open(tmp_config_path, "w") as f:
            yaml.safe_dump(sample_config_data, f)

        manager = RiskRulesManager(config_path=tmp_config_path)
        new_rules = [
            {"name": "only_rule", "type": "hard_stop_loss", "threshold": 0.05, "action": "close"},
        ]
        result = manager.replace_all(new_rules)
        assert len(result) == 1
        assert len(manager.get_rules()) == 1

    def test_replace_all_duplicate_names_raises(self, tmp_config_path, sample_config_data):
        """Test that replace_all raises on duplicate names"""
        with open(tmp_config_path, "w") as f:
            yaml.safe_dump(sample_config_data, f)

        manager = RiskRulesManager(config_path=tmp_config_path)
        with pytest.raises(ValueError, match="Duplicate"):
            manager.replace_all([
                {"name": "dup", "type": "hard_stop_loss", "threshold": 0.05, "action": "close"},
                {"name": "dup", "type": "hard_take_profit", "threshold": 0.15, "action": "close"},
            ])

    def test_migration_creates_defaults(self, tmp_path):
        """Test that migration creates default rules when no config exists"""
        config_path = tmp_path / "nonexistent_risk_rules.yaml"
        manager = RiskRulesManager(config_path=config_path)

        rules = manager.get_rules()
        assert len(rules) == 6
        assert config_path.exists()

    def test_persistence(self, tmp_config_path, sample_config_data):
        """Test that changes persist to disk"""
        with open(tmp_config_path, "w") as f:
            yaml.safe_dump(sample_config_data, f)

        # Make changes
        manager = RiskRulesManager(config_path=tmp_config_path)
        manager.add_rule({
            "name": "persisted_rule",
            "type": "daily_loss_limit",
            "threshold": 0.05,
            "action": "alert",
        })

        # Reload and verify
        manager2 = RiskRulesManager(config_path=tmp_config_path)
        rule = manager2.get_rule("persisted_rule")
        assert rule is not None
        assert rule.threshold == 0.05


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
