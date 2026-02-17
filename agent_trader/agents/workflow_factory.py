"""
Workflow Factory - 使用装饰器自动注册 + 外部插件发现

内置 Workflow：
    agent_trader/agents/ 下的 *_workflow.py / *_agent.py

外部 Workflow 插件：
    放在 user_data/agents/*.py 中，使用 @register_workflow 装饰器即可。

    ```python
    from agent_trader.agents.workflow_factory import register_workflow
    from agent_trader.agents.workflow_base import WorkflowBase

    @register_workflow("my_workflow", description="...", features=[...])
    class MyWorkflow(WorkflowBase):
        async def run_workflow(self, initial_context=None):
            ...
    ```

无需修改任何 factory 代码。
"""

import importlib
import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Any, Type, Optional, Callable

from config import settings
from agent_trader.utils.logging_config import get_logger
from agent_trader.interfaces.broker_api import BrokerAPI
from agent_trader.interfaces.market_data_api import MarketDataAPI
from agent_trader.interfaces.news_api import NewsAPI
from agent_trader.messaging.message_manager import MessageManager
from agent_trader.interfaces.factory import (
    get_broker_api, get_market_data_api, get_news_api
)
from agent_trader.agents.workflow_base import WorkflowBase

if TYPE_CHECKING:
    from langgraph.store.base import BaseStore
    from langgraph.types import Checkpointer


logger = get_logger(__name__)


# ============================================================
# 全局 Workflow 注册表
# ============================================================

_WORKFLOW_REGISTRY: Dict[str, Type[WorkflowBase]] = {}

# 内置 workflow 类型名称集合（discover_builtin_workflows 注册的）
_BUILTIN_TYPES: set[str] = set()


def register_workflow(
    workflow_type: str,
    description: str = "",
    features: Optional[list] = None,
    best_for: str = "",
    deprecated: bool = False
) -> Callable[[Type[WorkflowBase]], Type[WorkflowBase]]:
    """
    装饰器：注册 Workflow 类

    使用:
        @register_workflow("my_workflow", description="我的工作流")
        class MyWorkflow(WorkflowBase):
            ...

    Args:
        workflow_type: 工作流类型名称
        description: 描述
        features: 特性列表
        best_for: 最适合的场景
        deprecated: 是否已弃用
    """
    def decorator(cls: Type[WorkflowBase]) -> Type[WorkflowBase]:
        if not issubclass(cls, WorkflowBase):
            raise TypeError(f"{cls.__name__} must inherit from WorkflowBase")

        # 存储元数据
        cls._workflow_metadata = {
            "type": workflow_type,
            "description": description or (cls.__doc__ or "").strip().split('\n')[0],
            "features": features or [],
            "best_for": best_for,
            "deprecated": deprecated,
        }

        # 注册
        _WORKFLOW_REGISTRY[workflow_type] = cls
        logger.debug(f"Registered workflow: {workflow_type} -> {cls.__name__}")

        return cls

    return decorator


def get_registered_workflows() -> Dict[str, Type[WorkflowBase]]:
    """获取所有已注册的 Workflow"""
    return _WORKFLOW_REGISTRY.copy()


# ============================================================
# WorkflowFactory
# ============================================================

class WorkflowFactory:
    """Workflow 工厂"""

    @classmethod
    def create_workflow(
        cls,
        workflow_type: Optional[str] = None,
        broker_api: BrokerAPI = None,
        market_data_api: MarketDataAPI = None,
        news_api: NewsAPI = None,
        message_manager: MessageManager = None,
        checkpointer: "Optional[Checkpointer]" = None,
        store: "Optional[BaseStore]" = None,
        **kwargs
    ) -> WorkflowBase:
        """创建 Workflow 实例"""
        try:
            type_str = workflow_type or settings.workflow_type

            if type_str not in _WORKFLOW_REGISTRY:
                available = list(_WORKFLOW_REGISTRY.keys())
                raise ValueError(f"Unknown workflow: {type_str}. Available: {available}")

            if broker_api is None:
                broker_api = get_broker_api()
            if market_data_api is None:
                market_data_api = get_market_data_api()
            if news_api is None:
                news_api = get_news_api()
            if message_manager is None:
                raise ValueError("message_manager is required")

            workflow_class = _WORKFLOW_REGISTRY[type_str]
            workflow = workflow_class(
                broker_api=broker_api,
                market_data_api=market_data_api,
                news_api=news_api,
                message_manager=message_manager,
                checkpointer=checkpointer,
                store=store,
                **kwargs
            )

            logger.info(f"Created workflow: {type_str} ({workflow_class.__name__})")
            return workflow

        except Exception as e:
            logger.error(f"Failed to create workflow: {e}")
            raise

    @classmethod
    def get_available_workflows(cls) -> Dict[str, Dict[str, Any]]:
        """获取可用 workflows 信息"""
        result = {}
        for type_str, workflow_class in _WORKFLOW_REGISTRY.items():
            meta = getattr(workflow_class, '_workflow_metadata', {})
            result[type_str] = {
                "name": type_str.replace('_', ' ').title(),
                "class": workflow_class.__name__,
                "description": meta.get("description", ""),
                "features": meta.get("features", []),
                "best_for": meta.get("best_for", ""),
                "deprecated": meta.get("deprecated", False),
                "builtin": type_str in _BUILTIN_TYPES,
            }
        return result

    @classmethod
    def is_supported(cls, workflow_type: str) -> bool:
        """检查 workflow 是否支持"""
        return workflow_type in _WORKFLOW_REGISTRY


def get_workflow_choices() -> list[str]:
    """获取可用 workflow 类型列表"""
    return list(_WORKFLOW_REGISTRY.keys())


# ============================================================
# Workflow 自动发现
# ============================================================

def discover_builtin_workflows() -> None:
    """
    自动发现并导入 agent_trader/agents/ 下的内置 workflow 模块。

    扫描规则：*_workflow.py, *_agent.py（排除 workflow_base.py 和 workflow_factory.py）
    """
    before = set(_WORKFLOW_REGISTRY.keys())

    agents_dir = Path(__file__).parent
    for pattern in ("*_workflow.py", "*_agent.py"):
        for py_file in agents_dir.glob(pattern):
            module_name = py_file.stem
            if module_name in ("workflow_base", "workflow_factory"):
                continue
            full_module = f"agent_trader.agents.{module_name}"
            try:
                importlib.import_module(full_module)
            except Exception as e:
                logger.error("Failed to load built-in workflow %s: %s", full_module, e)

    # 标记内置 workflow
    _BUILTIN_TYPES.update(_WORKFLOW_REGISTRY.keys() - before)


def discover_external_workflows(agents_dir: str) -> int:
    """
    扫描外部目录（如 user_data/agents/），动态导入带 @register_workflow 的 workflow。

    外部文件可使用 from agent_trader.xxx 导入项目内任何模块。

    Args:
        agents_dir: 外部 workflow 目录路径

    Returns:
        新发现的 workflow 数量
    """
    import sys

    path = Path(agents_dir)
    if not path.is_dir():
        logger.debug("External agents directory not found: %s (skipped)", agents_dir)
        return 0

    before = set(_WORKFLOW_REGISTRY.keys())

    for py_file in sorted(path.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        module_name = f"external_workflow_{py_file.stem}"

        # 如果已经加载过，先卸载以支持热更新
        if module_name in sys.modules:
            del sys.modules[module_name]

        try:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                logger.warning("Cannot load external workflow: %s", py_file)
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            logger.info("Loaded external workflow: %s", py_file.name)
        except Exception as e:
            logger.error("Failed to load external workflow %s: %s", py_file.name, e)

    new_count = len(_WORKFLOW_REGISTRY.keys() - before)
    return new_count


def reload_external_workflows() -> Dict[str, Any]:
    """
    热重载外部 workflow：清除非内置的注册，重新扫描 user_data/agents/。

    Returns:
        {"loaded": [...], "removed": [...], "total": N}
    """
    # 记录旧的外部 workflow
    old_external = {k for k in _WORKFLOW_REGISTRY if k not in _BUILTIN_TYPES}

    # 清除所有外部注册
    for k in old_external:
        del _WORKFLOW_REGISTRY[k]

    # 重新扫描
    agents_dir = str(Path(settings.data_dir) / "agents")
    discover_external_workflows(agents_dir)

    # 计算变化
    new_external = {k for k in _WORKFLOW_REGISTRY if k not in _BUILTIN_TYPES}
    loaded = sorted(new_external)
    removed = sorted(old_external - new_external)

    logger.info(
        "Reloaded external workflows: loaded=%s, removed=%s",
        loaded, removed,
    )

    return {
        "loaded": loaded,
        "removed": removed,
        "total": len(_WORKFLOW_REGISTRY),
    }
