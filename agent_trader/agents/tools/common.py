"""
通用 Agent Tools — 聚合层

将各分类 tools 统一暴露给 workflow 使用。
Workflow 在初始化时调用 create_common_tools(self) 获取所有通用 tools，
或按需调用 create_xxx_tools(self) 获取特定分类。
"""

from typing import List

from agent_trader.agents.tools.data_tools import create_data_tools
from agent_trader.agents.tools.analysis_tools import create_analysis_tools
from agent_trader.agents.tools.system_tools import create_system_tools
from agent_trader.agents.tools.trading_tools import create_trading_tools
from agent_trader.agents.tools.web_search_tools import create_web_search_tools


def create_common_tools(workflow) -> List[tuple]:
    """
    创建所有通用 tools（数据 + 分析 + 系统 + 交易 + Web 搜索）

    Args:
        workflow: WorkflowBase 子类实例

    Returns:
        [(tool_obj, category), ...] 可直接传给 ToolRegistry.register_many()
    """
    tools: List[tuple] = []
    tools.extend(create_data_tools(workflow))
    tools.extend(create_analysis_tools(workflow))
    tools.extend(create_system_tools(workflow))
    tools.extend(create_trading_tools(workflow))
    tools.extend(create_web_search_tools(workflow))
    return tools
