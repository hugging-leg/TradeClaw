"""
Workflow Factory - 使用装饰器自动注册

新增 Workflow 只需：

```python
from src.agents.workflow_factory import register_workflow

@register_workflow("my_workflow", description="...", features=[...])
class MyWorkflow(WorkflowBase):
    ...
```

无需修改任何 factory 代码。
"""

from src.utils.logging_config import get_logger
from typing import Dict, Any, Type, Optional, Callable

from config import settings
from src.interfaces.broker_api import BrokerAPI
from src.interfaces.market_data_api import MarketDataAPI
from src.interfaces.news_api import NewsAPI
from src.messaging.message_manager import MessageManager
from src.interfaces.factory import (
    get_broker_api, get_market_data_api, get_news_api
)
from src.agents.workflow_base import WorkflowBase


logger = get_logger(__name__)


# ============================================================
# 全局 Workflow 注册表
# ============================================================

_WORKFLOW_REGISTRY: Dict[str, Type[WorkflowBase]] = {}


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
            "deprecated": deprecated
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
        **kwargs
    ) -> WorkflowBase:
        """创建 Workflow 实例"""
        try:
            type_str = workflow_type or getattr(settings, 'workflow_type', 'llm_portfolio')

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
                "deprecated": meta.get("deprecated", False)
            }
        return result

    @classmethod
    def is_supported(cls, workflow_type: str) -> bool:
        """检查 workflow 是否支持"""
        return workflow_type in _WORKFLOW_REGISTRY


def get_workflow_choices() -> list[str]:
    """获取可用 workflow 类型列表"""
    return list(_WORKFLOW_REGISTRY.keys())
