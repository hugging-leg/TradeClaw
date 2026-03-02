"""
Risk Rules Configuration

Configurable stop-loss / take-profit rule chains. Supports coexistence of
LLM analysis triggers and hard-coded rules.

Rule types:
- hard_stop_loss: Hard stop loss (close position immediately)
- hard_take_profit: Hard take profit (close position immediately)
- trailing_stop: Trailing stop loss
- llm_stop_loss: Trigger LLM analysis on loss threshold
- llm_take_profit: Trigger LLM analysis on profit threshold
- daily_loss_limit: Daily portfolio loss limit
- concentration_limit: Position concentration limit

Execution order: rules are evaluated in ascending priority order (lower number first).
A single position can match multiple rules, but once a "close" action fires, subsequent
rules are skipped for that position.

Config file: user_data/risk_rules.yaml
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field

from agent_trader.utils.logging_config import get_logger

logger = get_logger(__name__)


# ------------------------------------------------------------------
# Enums
# ------------------------------------------------------------------

class RuleType(str, Enum):
    HARD_STOP_LOSS = "hard_stop_loss"
    HARD_TAKE_PROFIT = "hard_take_profit"
    TRAILING_STOP = "trailing_stop"
    LLM_STOP_LOSS = "llm_stop_loss"
    LLM_TAKE_PROFIT = "llm_take_profit"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    CONCENTRATION_LIMIT = "concentration_limit"


class RuleAction(str, Enum):
    CLOSE = "close"          # Close position
    LLM_ANALYZE = "llm_analyze"  # Trigger LLM analysis
    ALERT = "alert"          # Alert only
    REDUCE = "reduce"        # Reduce position (by ratio)


# ------------------------------------------------------------------
# Pydantic Models
# ------------------------------------------------------------------

class RiskRule(BaseModel):
    """A single risk rule."""
    name: str = Field(..., description="Rule name (unique identifier)")
    type: RuleType = Field(..., description="Rule type")
    enabled: bool = Field(True, description="Whether the rule is enabled")
    priority: int = Field(100, description="Priority (lower number = evaluated first)")

    # Trigger condition
    threshold: float = Field(
        ..., description="Trigger threshold (ratio, e.g. 0.05 = 5%)"
    )

    # Action to take
    action: RuleAction = Field(
        RuleAction.CLOSE, description="Action when triggered"
    )

    # Optional parameters
    reduce_ratio: float = Field(
        0.5, description="Reduce ratio (only effective when action=reduce)"
    )
    symbols: Optional[List[str]] = Field(
        None, description="Applicable symbols (None = all)"
    )
    cooldown_seconds: int = Field(
        0, description="Cooldown time per symbol (seconds)"
    )
    description: Optional[str] = Field(None, description="Rule description")


class RiskRulesConfig(BaseModel):
    """Risk rules configuration file."""
    version: str = "1"
    rules: List[RiskRule] = Field(default_factory=list)


# ------------------------------------------------------------------
# Default Rules
# ------------------------------------------------------------------

def _default_rules() -> List[RiskRule]:
    """Default risk rules."""
    return [
        RiskRule(
            name="hard_stop_loss_5pct",
            type=RuleType.HARD_STOP_LOSS,
            enabled=True,
            priority=10,
            threshold=0.05,
            action=RuleAction.CLOSE,
            description="Close position when loss exceeds 5%",
        ),
        RiskRule(
            name="hard_take_profit_15pct",
            type=RuleType.HARD_TAKE_PROFIT,
            enabled=True,
            priority=10,
            threshold=0.15,
            action=RuleAction.CLOSE,
            description="Close position when profit exceeds 15%",
        ),
        RiskRule(
            name="llm_stop_loss_3pct",
            type=RuleType.LLM_STOP_LOSS,
            enabled=True,
            priority=50,
            threshold=0.03,
            action=RuleAction.LLM_ANALYZE,
            description="Trigger LLM analysis when loss exceeds 3%",
        ),
        RiskRule(
            name="llm_take_profit_10pct",
            type=RuleType.LLM_TAKE_PROFIT,
            enabled=True,
            priority=50,
            threshold=0.10,
            action=RuleAction.LLM_ANALYZE,
            description="Trigger LLM analysis when profit exceeds 10%",
        ),
        RiskRule(
            name="daily_loss_limit_10pct",
            type=RuleType.DAILY_LOSS_LIMIT,
            enabled=True,
            priority=5,
            threshold=0.10,
            action=RuleAction.ALERT,
            description="Alert when daily portfolio loss exceeds 10%",
        ),
        RiskRule(
            name="concentration_25pct",
            type=RuleType.CONCENTRATION_LIMIT,
            enabled=True,
            priority=80,
            threshold=0.25,
            action=RuleAction.ALERT,
            description="Alert when single position weight exceeds 25%",
        ),
    ]


# ------------------------------------------------------------------
# Manager
# ------------------------------------------------------------------

class RiskRulesManager:
    """
    Risk Rules Manager

    Responsibilities:
    - Load/save rules from YAML file
    - Provide CRUD operations for rules
    - Migrate legacy settings on first startup
    """

    def __init__(self, config_path: Optional[Path] = None):
        from config import settings
        self._config_path = config_path or (
            Path(settings.data_dir) / "risk_rules.yaml"
        )
        self._config: RiskRulesConfig = self._load()

    def _load(self) -> RiskRulesConfig:
        """Load configuration from YAML."""
        if self._config_path.exists():
            try:
                raw = yaml.safe_load(self._config_path.read_text(encoding="utf-8"))
                if raw:
                    config = RiskRulesConfig.model_validate(raw)
                    logger.info(
                        "Loaded %d risk rules from %s",
                        len(config.rules),
                        self._config_path,
                    )
                    return config
            except Exception as e:
                logger.error("Failed to load risk rules: %s", e)

        # First startup: migrate from settings + generate defaults
        return self._migrate_from_settings()

    def _migrate_from_settings(self) -> RiskRulesConfig:
        """Migrate stop-loss/take-profit settings from legacy .env config."""
        from config import settings

        rules = _default_rules()

        # Override defaults with values from settings
        sl_pct = settings.stop_loss_percentage
        tp_pct = settings.take_profit_percentage
        daily_limit = settings.daily_loss_limit_percentage
        concentration = settings.max_position_concentration

        # Normalize (if > 1, treat as percentage form)
        if sl_pct > 1:
            sl_pct /= 100
        if tp_pct > 1:
            tp_pct /= 100
        if daily_limit > 1:
            daily_limit /= 100
        if concentration > 1:
            concentration /= 100

        for rule in rules:
            if rule.name == "hard_stop_loss_5pct":
                rule.threshold = sl_pct
            elif rule.name == "hard_take_profit_15pct":
                rule.threshold = tp_pct
            elif rule.name == "daily_loss_limit_10pct":
                rule.threshold = daily_limit
            elif rule.name == "concentration_25pct":
                rule.threshold = concentration

        config = RiskRulesConfig(rules=rules)
        self._save(config)
        logger.info(
            "Migrated risk rules from settings -> %s (%d rules)",
            self._config_path,
            len(rules),
        )
        return config

    def _save(self, config: Optional[RiskRulesConfig] = None) -> None:
        """Save configuration to YAML."""
        config = config or self._config
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        data = config.model_dump(mode="json")
        self._config_path.write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_rules(self) -> List[Dict[str, Any]]:
        """Get all rules as dicts."""
        return [r.model_dump(mode="json") for r in self._config.rules]

    def get_enabled_rules(self) -> List[RiskRule]:
        """Get enabled rules sorted by priority."""
        return sorted(
            [r for r in self._config.rules if r.enabled],
            key=lambda r: r.priority,
        )

    def get_rule(self, name: str) -> Optional[RiskRule]:
        """Get a specific rule by name."""
        for r in self._config.rules:
            if r.name == name:
                return r
        return None

    def add_rule(self, rule_data: Dict[str, Any]) -> RiskRule:
        """Add a new rule."""
        rule = RiskRule.model_validate(rule_data)

        # Check name uniqueness
        if any(r.name == rule.name for r in self._config.rules):
            raise ValueError(f"Rule with name '{rule.name}' already exists")

        self._config.rules.append(rule)
        self._save()
        logger.info("Added risk rule: %s", rule.name)
        return rule

    def update_rule(self, name: str, updates: Dict[str, Any]) -> RiskRule:
        """Update an existing rule."""
        for i, r in enumerate(self._config.rules):
            if r.name == name:
                data = r.model_dump()
                data.update(updates)
                # Name cannot be changed
                data["name"] = name
                updated = RiskRule.model_validate(data)
                self._config.rules[i] = updated
                self._save()
                logger.info("Updated risk rule: %s", name)
                return updated
        raise ValueError(f"Rule '{name}' not found")

    def delete_rule(self, name: str) -> bool:
        """Delete a rule by name."""
        for i, r in enumerate(self._config.rules):
            if r.name == name:
                self._config.rules.pop(i)
                self._save()
                logger.info("Deleted risk rule: %s", name)
                return True
        return False

    def replace_all(self, rules_data: List[Dict[str, Any]]) -> List[RiskRule]:
        """Replace all rules at once."""
        rules = [RiskRule.model_validate(d) for d in rules_data]

        # Check name uniqueness
        names = [r.name for r in rules]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate rule names found")

        self._config.rules = rules
        self._save()
        logger.info("Replaced all risk rules (%d rules)", len(rules))
        return rules

    def reload(self) -> None:
        """Reload configuration from file."""
        self._config = self._load()


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_manager: Optional[RiskRulesManager] = None


def get_risk_rules_manager() -> RiskRulesManager:
    """Get the risk rules manager singleton."""
    global _manager
    if _manager is None:
        _manager = RiskRulesManager()
    return _manager
