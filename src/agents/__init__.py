"""
Trading Agents 模块

导入此模块时，所有 workflow 会通过 @register_workflow 装饰器自动注册。
"""

# 导入 factory (提供 WorkflowFactory, register_workflow)
from src.agents.workflow_factory import (
    WorkflowFactory,
    register_workflow,
    get_registered_workflows,
    get_workflow_choices,
)

# 导入所有 workflow 类（触发装饰器注册）
from src.agents.workflow_base import WorkflowBase
from src.agents.llm_portfolio_agent import LLMPortfolioAgent
from src.agents.black_litterman_workflow import BlackLittermanWorkflow
from src.agents.cognitive_arbitrage_workflow import CognitiveArbitrageWorkflow

__all__ = [
    # Factory
    "WorkflowFactory",
    "register_workflow",
    "get_registered_workflows",
    "get_workflow_choices",
    # Base
    "WorkflowBase",
    # Workflows
    "LLMPortfolioAgent",
    "BlackLittermanWorkflow",
    "CognitiveArbitrageWorkflow",
]
