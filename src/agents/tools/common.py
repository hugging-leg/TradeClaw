"""
通用 Agent Tools — 聚合层

将各分类 tools 统一暴露给 workflow 使用。
Workflow 在初始化时调用 create_common_tools(self) 获取所有通用 tools，
或按需调用 create_xxx_tools(self) 获取特定分类。
"""

from typing import List

from src.agents.tools.data_tools import create_data_tools
from src.agents.tools.analysis_tools import create_analysis_tools
from src.agents.tools.system_tools import create_system_tools
from src.agents.tools.trading_tools import create_trading_tools


def create_common_tools(workflow) -> List[tuple]:
    """
    创建所有通用 tools（数据 + 分析 + 系统 + 交易）

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
    return tools
