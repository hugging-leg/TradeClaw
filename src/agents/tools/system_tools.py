"""
系统类 Agent Tools

提供时间查询、市场状态检查、自主调度等系统级工具。
"""

import json
from typing import List
from datetime import timedelta

from langchain.tools import tool

from src.utils.logging_config import get_logger
from src.utils.timezone import utc_now

logger = get_logger(__name__)


def create_system_tools(workflow) -> List[tuple]:
    """
    创建所有系统类 tools

    Args:
        workflow: WorkflowBase 子类实例

    Returns:
        [(tool_obj, "system"), ...] 可直接传给 ToolRegistry.register_many()
    """
    return [
        (_create_get_current_time(workflow), "system"),
        (_create_check_market_status(workflow), "system"),
        (_create_schedule_next_analysis(workflow), "system"),
    ]


def _create_get_current_time(wf):
    @tool
    async def get_current_time() -> str:
        """
        获取当前日期和时间（UTC时间）

        Returns:
            当前日期时间信息
        """
        try:
            now_utc = utc_now()

            result = {
                "current_time_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S %Z"),
            }

            await wf.message_manager.send_message(
                f"🕐 当前时间: {result['current_time_utc']}", "info"
            )

            return json.dumps(result, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"获取当前时间失败: {e}")
            return f"错误: {str(e)}"

    return get_current_time


def _create_check_market_status(wf):
    @tool
    async def check_market_status() -> str:
        """
        检查市场是否开放

        Returns:
            市场开放状态信息
        """
        try:
            await wf.message_manager.send_message("🏪 正在检查市场状态...", "info")

            is_open = await wf.is_market_open()
            now_utc = utc_now()

            result = {
                "market_open": is_open,
                "checked_at": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
            }

            status_emoji = "🟢" if is_open else "🔴"
            await wf.message_manager.send_message(
                f"{status_emoji} 市场状态: {'Open' if is_open else 'Closed'}", "info"
            )

            return json.dumps(result, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"检查市场状态失败: {e}")
            return f"错误: {str(e)}"

    return check_market_status


def _create_schedule_next_analysis(wf):
    @tool
    async def schedule_next_analysis(
        hours_from_now: float,
        reason: str,
        priority: int = 0,
    ) -> str:
        """
        安排下一次组合分析时间（LLM自主调度）

        Args:
            hours_from_now: 多少小时后执行，可以是小数（如0.5表示30分钟，2.5表示2.5小时）
            reason: 安排原因，例如"预期FOMC会议结果公布"、"等待财报发布"、"市场波动监控"等
            priority: 优先级（-10-10，数字越小优先级越高），默认0为普通优先级

        Returns:
            调度结果
        """
        try:
            scheduled_time = utc_now() + timedelta(hours=hours_from_now)
            delay_seconds = hours_from_now * 3600

            # 通知
            await wf.message_manager.send_message(
                f"⏰ **LLM自主调度**\n\n"
                f"安排时间: {scheduled_time.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                f"距离现在: {hours_from_now:.1f}小时\n"
                f"原因: {reason}\n"
                f"优先级: {priority}",
                "info",
            )

            # 通过 TradingSystem 添加延迟任务（带上限控制）
            ts = getattr(wf, '_trading_system', None)

            if ts is not None:
                result = ts.schedule_llm_analysis(
                    delay_seconds=delay_seconds,
                    reason=reason,
                )
                if not result["success"]:
                    return json.dumps(result, indent=2, ensure_ascii=False)
            else:
                logger.warning("TradingSystem not available, cannot schedule delayed analysis")
                result = {}

            logger.info("LLM Scheduled Analysis: %s - %s", scheduled_time.isoformat(), reason)

            return json.dumps({
                "success": True,
                "job_id": result.get("job_id") if ts else None,
                "scheduled_time": scheduled_time.isoformat(),
                "hours_from_now": hours_from_now,
                "reason": reason,
                "message": f"已安排{hours_from_now:.1f}小时后的分析",
            }, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"安排下一次分析失败: {e}")
            return f"错误: {str(e)}"

    return schedule_next_analysis
