"""
Agent Tools 模块

按职责分类的 tools 体系:
- data_tools: 数据查询（组合、市场、新闻、价格）
- analysis_tools: 分析（持仓分析、BL 观点生成）
- trading_tools: 交易执行（组合重平衡、单仓位调整）
- system_tools: 系统（时间、市场状态、自主调度）

使用方式:
    from agent_trader.agents.tools import create_common_tools, ToolRegistry

    registry = ToolRegistry()
    registry.register_many(create_common_tools(workflow))
"""

from agent_trader.agents.tools.registry import ToolRegistry
from agent_trader.agents.tools.common import create_common_tools
from agent_trader.agents.tools.data_tools import create_data_tools
from agent_trader.agents.tools.analysis_tools import create_analysis_tools
from agent_trader.agents.tools.system_tools import create_system_tools
from agent_trader.agents.tools.trading_tools import create_trading_tools

__all__ = [
    "ToolRegistry",
    "create_common_tools",
    "create_data_tools",
    "create_analysis_tools",
    "create_system_tools",
    "create_trading_tools",
]
