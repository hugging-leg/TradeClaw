"""
Trading Agents 模块

导入此模块时，所有内置 workflow 通过自动发现注册，
外部 workflow（user_data/agents/*.py）在 TradingSystem.start() 中加载。
"""

from agent_trader.agents.workflow_factory import (
    WorkflowFactory,
    register_workflow,
    get_registered_workflows,
    get_workflow_choices,
    discover_builtin_workflows,
    discover_external_workflows,
    reload_external_workflows,
)
from agent_trader.agents.workflow_base import WorkflowBase

# 自动发现并注册内置 workflow
discover_builtin_workflows()

__all__ = [
    # Factory
    "WorkflowFactory",
    "register_workflow",
    "get_registered_workflows",
    "get_workflow_choices",
    "discover_builtin_workflows",
    "discover_external_workflows",
    "reload_external_workflows",
    # Base
    "WorkflowBase",
]
