"""
分析类 Agent Tools

提供持仓分析、Black-Litterman 优化等专业金融分析工具。
"""

import json
from typing import Dict, List, Any

from langchain.tools import tool

from agent_trader.utils.logging_config import get_logger

logger = get_logger(__name__)


def create_analysis_tools(workflow) -> List[tuple]:
    """
    创建所有分析类 tools

    Args:
        workflow: WorkflowBase 子类实例

    Returns:
        [(tool_obj, "analysis"), ...] 可直接传给 ToolRegistry.register_many()
    """
    tools = [
        (_create_get_position_analysis(workflow), "analysis"),
    ]

    # BL 优化工具仅在 pypfopt 可用时注册
    bl_tool = _create_bl_generate_views(workflow)
    if bl_tool is not None:
        tools.append((bl_tool, "analysis"))

    return tools


def _create_get_position_analysis(wf):
    @tool
    async def get_position_analysis() -> str:
        """分析当前持仓分布，包括各仓位占比、集中度等"""
        try:
            await wf.message_manager.send_message("🔬 正在分析持仓分布...", "info")

            portfolio = await wf.get_portfolio()
            if not portfolio or portfolio.equity <= 0:
                return "组合为空或无法获取"

            analysis: Dict[str, Any] = {
                "total_positions": 0,
                "position_details": [],
                "concentration": {
                    "largest_position_pct": 0.0,
                    "top3_concentration": 0.0,
                },
            }

            positions_with_pct = []
            for pos in portfolio.positions:
                if pos.quantity != 0:
                    pct = (pos.market_value / portfolio.equity) * 100
                    positions_with_pct.append({
                        "symbol": pos.symbol,
                        "percentage": float(pct),
                        "market_value": float(pos.market_value),
                        "pnl_pct": float(pos.unrealized_pnl_percentage),
                    })

            positions_with_pct.sort(key=lambda x: x["market_value"], reverse=True)

            analysis["total_positions"] = len(positions_with_pct)
            analysis["position_details"] = positions_with_pct

            if positions_with_pct:
                analysis["concentration"]["largest_position_pct"] = positions_with_pct[0]["percentage"]
                top3 = sum(p["percentage"] for p in positions_with_pct[:3])
                analysis["concentration"]["top3_concentration"] = top3

            await wf.message_manager.send_message(
                f"✅ 分析完成: {len(positions_with_pct)}个仓位, "
                f"最大{analysis['concentration']['largest_position_pct']:.1f}%",
                "info",
            )

            return json.dumps(analysis, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"分析持仓失败: {e}")
            return f"错误: {str(e)}"

    return get_position_analysis


def _create_bl_generate_views(wf):
    """
    创建 BL 投资观点生成工具。

    此工具将 LLM 的观点写入 workflow 实例的 _current_views / _current_confidences /
    _current_reasoning 属性，供 BL 优化流程后续使用。

    仅当 workflow 具有这些属性时才注册（即 BlackLittermanWorkflow）。
    """
    # 检查 workflow 是否支持 BL 观点接收
    # 用 class 属性判断比 isinstance 更松耦合
    if not hasattr(type(wf), '_current_views'):
        # 不是 BL workflow，不注册此 tool
        # 但如果 wf 实例上有这个属性也算（在 __init__ 中设置的）
        if not hasattr(wf, '_current_views'):
            return None

    @tool
    async def generate_investment_views(
        views: Dict[str, float],
        view_confidences: Dict[str, float],
        reasoning: str,
    ) -> str:
        """
        生成投资观点（Black-Litterman 模型使用）

        Args:
            views: 预期超额收益，如 {"AAPL": 0.15, "TLT": -0.05}
            view_confidences: 置信度，如 {"AAPL": 0.8, "TLT": 0.6}
            reasoning: 分析推理过程

        Returns:
            观点确认信息
        """
        try:
            wf._current_views = views
            wf._current_confidences = view_confidences
            wf._current_reasoning = reasoning

            await wf.message_manager.send_message(
                f"💡 **投资观点已生成**\n\n"
                f"观点数量: {len(views)}\n"
                f"分析: {reasoning[:200]}...",
                "info",
            )

            return json.dumps({
                "success": True,
                "views_count": len(views),
                "views": views,
                "confidences": view_confidences,
            }, indent=2)

        except Exception as e:
            return f"生成观点失败: {e}"

    return generate_investment_views
