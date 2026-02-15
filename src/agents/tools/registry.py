"""
Tool Registry — 管理 Agent tools 的启用/禁用状态

设计：
- 每个 tool 注册时带有 name, category, enabled 状态
- Workflow 通过 registry.get_enabled_tools() 获取当前启用的 tools
- API 层可以通过 registry.set_enabled() 切换 tool 状态
- 状态保存在内存中（重启恢复默认值）
"""

from typing import Any
from dataclasses import dataclass

from src.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ToolEntry:
    """注册的 tool 条目"""
    name: str
    tool_obj: Any  # LangChain @tool 装饰后的对象
    category: str  # data, trading, analysis, system
    enabled: bool = True
    description: str = ""


class ToolRegistry:
    """
    Tool 注册表

    用法：
        registry = ToolRegistry()
        registry.register(tool_obj, category="data")
        enabled_tools = registry.get_enabled_tools()
    """

    def __init__(self):
        self._tools: dict[str, ToolEntry] = {}

    def register(self, tool_obj: Any, category: str = "data", enabled: bool = True) -> None:
        """
        注册一个 tool

        Args:
            tool_obj: LangChain @tool 装饰后的对象（有 .name, .description 属性）
            category: 分类（data, trading, analysis, system）
            enabled: 默认是否启用
        """
        name = getattr(tool_obj, "name", str(tool_obj))
        desc = getattr(tool_obj, "description", "")
        self._tools[name] = ToolEntry(
            name=name,
            tool_obj=tool_obj,
            category=category,
            enabled=enabled,
            description=desc,
        )
        logger.debug(f"Registered tool: {name} [{category}] enabled={enabled}")

    def register_many(self, tools: list[tuple[Any, str]], enabled: bool = True) -> None:
        """
        批量注册 tools

        Args:
            tools: [(tool_obj, category), ...]
            enabled: 默认是否启用
        """
        for tool_obj, category in tools:
            self.register(tool_obj, category=category, enabled=enabled)

    def get_enabled_tools(self) -> list[Any]:
        """获取所有已启用的 tool 对象列表"""
        return [entry.tool_obj for entry in self._tools.values() if entry.enabled]

    def get_all_entries(self) -> list[ToolEntry]:
        """获取所有 tool 条目（含状态）"""
        return list(self._tools.values())

    def set_enabled(self, name: str, enabled: bool) -> bool:
        """
        设置 tool 的启用状态

        Returns:
            True if tool found and updated, False otherwise
        """
        entry = self._tools.get(name)
        if not entry:
            return False
        entry.enabled = enabled
        logger.info(f"Tool '{name}' {'enabled' if enabled else 'disabled'}")
        return True

    def is_enabled(self, name: str) -> bool:
        """检查 tool 是否启用"""
        entry = self._tools.get(name)
        return entry.enabled if entry else False

    def get_metadata(self) -> list[dict]:
        """获取所有 tools 的元数据（供 API 使用）"""
        result = []
        for entry in self._tools.values():
            tool_info: dict = {
                "name": entry.name,
                "description": entry.description,
                "category": entry.category,
                "enabled": entry.enabled,
                "parameters": [],
            }

            # 从 args_schema 提取参数
            schema = getattr(entry.tool_obj, "args_schema", None)
            if schema:
                try:
                    json_schema = schema.model_json_schema()
                    props = json_schema.get("properties", {})
                    required = set(json_schema.get("required", []))
                    for param_name, param_info in props.items():
                        tool_info["parameters"].append({
                            "name": param_name,
                            "type": param_info.get("type", "string"),
                            "description": param_info.get("description", ""),
                            "required": param_name in required,
                        })
                except Exception:
                    pass

            result.append(tool_info)

        return result
