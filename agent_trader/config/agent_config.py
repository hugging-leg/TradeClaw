"""
Agent 配置管理器

管理 user_data/agents/{workflow_type}.yaml 的读写和向后兼容迁移。

每个 workflow 类型一个 YAML 文件，存储该 workflow 的所有可编辑参数。

加载优先级：
    代码 _default_config() (最低) → YAML 文件覆盖 → 运行时 update_config() (最高)

用法：
    mgr = AgentConfigManager(data_dir="./user_data")
    config = mgr.load("llm_portfolio", defaults={"system_prompt": "...", ...})
    mgr.save("llm_portfolio", config)
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from agent_trader.utils.logging_config import get_logger

logger = get_logger(__name__)


class AgentConfigManager:
    """
    Agent 配置管理器

    - 每个 workflow_type 对应 user_data/agents/{workflow_type}.yaml
    - load() 合并默认值和 YAML 文件
    - save() 写回 YAML
    - 线程安全
    """

    def __init__(self, data_dir: str = "./user_data"):
        self._data_dir = Path(data_dir) / "agents"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _yaml_path(self, workflow_type: str) -> Path:
        """获取 workflow 的 YAML 文件路径"""
        return self._data_dir / f"{workflow_type}.yaml"

    def load(
        self,
        workflow_type: str,
        defaults: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        加载 workflow 配置。

        合并逻辑：defaults → YAML 覆盖
        如果 YAML 不存在，返回 defaults 的副本。

        Args:
            workflow_type: workflow 类型标识
            defaults: _default_config() 的返回值

        Returns:
            合并后的配置字典
        """
        result = dict(defaults)
        yaml_path = self._yaml_path(workflow_type)

        if yaml_path.exists():
            try:
                with open(yaml_path, "r", encoding="utf-8") as f:
                    saved = yaml.safe_load(f) or {}
                if isinstance(saved, dict):
                    # 只覆盖 defaults 中已有的 key + llm_model
                    for key, value in saved.items():
                        if key in result or key == "llm_model":
                            result[key] = value
                    logger.debug(
                        "Agent config loaded for %s: %d fields from YAML",
                        workflow_type, len(saved),
                    )
            except Exception as e:
                logger.warning(
                    "Failed to load agent config for %s: %s", workflow_type, e
                )
        return result

    def save(self, workflow_type: str, config: Dict[str, Any]) -> None:
        """
        保存 workflow 配置到 YAML。

        Args:
            workflow_type: workflow 类型标识
            config: 要保存的配置字典（只保存非 None 值）
        """
        with self._lock:
            yaml_path = self._yaml_path(workflow_type)
            # 过滤掉只读的元数据字段
            skip_keys = {"workflow_type", "name"}
            data = {
                k: v for k, v in config.items()
                if k not in skip_keys and v is not None
            }
            self._data_dir.mkdir(parents=True, exist_ok=True)
            with open(yaml_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    data, f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )
            logger.info("Agent config saved for %s → %s", workflow_type, yaml_path)

    def exists(self, workflow_type: str) -> bool:
        """检查 workflow 的 YAML 配置是否存在"""
        return self._yaml_path(workflow_type).exists()

    def delete(self, workflow_type: str) -> bool:
        """删除 workflow 的 YAML 配置"""
        yaml_path = self._yaml_path(workflow_type)
        if yaml_path.exists():
            yaml_path.unlink()
            logger.info("Agent config deleted: %s", yaml_path)
            return True
        return False

    def list_configs(self) -> list[str]:
        """列出所有已保存配置的 workflow 类型"""
        return [
            p.stem for p in self._data_dir.glob("*.yaml")
            if p.is_file()
        ]

    def migrate_from_env(
        self,
        workflow_type: str,
        defaults: Dict[str, Any],
        env_overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        从 .env 迁移配置到 YAML（如果 YAML 不存在）。

        Args:
            workflow_type: workflow 类型标识
            defaults: _default_config() 的返回值
            env_overrides: 从 .env settings 中提取的覆盖值

        Returns:
            合并后的配置
        """
        yaml_path = self._yaml_path(workflow_type)
        if yaml_path.exists():
            return self.load(workflow_type, defaults)

        config = dict(defaults)
        if env_overrides:
            for key, value in env_overrides.items():
                if key in config and value is not None:
                    config[key] = value

        # 只有当有实质性配置时才写入
        if config:
            self.save(workflow_type, config)
            logger.info(
                "Migrated agent config for %s from .env → %s",
                workflow_type, yaml_path,
            )
        return config


# ============================================================
# Singleton
# ============================================================

_agent_config_mgr: Optional[AgentConfigManager] = None
_agent_config_lock = threading.Lock()


def get_agent_config_manager() -> AgentConfigManager:
    """获取全局 Agent 配置管理器单例"""
    global _agent_config_mgr
    if _agent_config_mgr is None:
        with _agent_config_lock:
            if _agent_config_mgr is None:
                from config import settings
                _agent_config_mgr = AgentConfigManager(data_dir=settings.data_dir)
    return _agent_config_mgr
