"""
系统类 Agent Tools

提供时间查询、市场状态检查、自主调度等系统级工具。
"""

import json
from typing import List
from datetime import timedelta

from langchain.tools import tool

from agent_trader.utils.logging_config import get_logger
from agent_trader.utils.timezone import utc_now

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
        (_create_get_scheduled_events(workflow), "system"),
        (_create_schedule_next_analysis(workflow), "system"),
        (_create_cancel_scheduled_analysis(workflow), "system"),
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


def _create_get_scheduled_events(wf):
    @tool
    async def get_scheduled_events() -> str:
        """
        查看当前所有已安排的调度事件，包括定时任务和LLM自主安排的分析。

        在安排新分析之前，务必先调用此工具查看已有调度，避免重复安排。

        Returns:
            所有调度事件列表（包括 job_id、类型、下次执行时间等）
        """
        try:
            ts = getattr(wf, '_trading_system', None)
            if ts is None:
                return json.dumps({
                    "success": False,
                    "message": "调度系统不可用（可能在回测模式下）",
                    "events": [],
                }, indent=2, ensure_ascii=False)

            all_jobs = ts.get_all_jobs()
            now = utc_now()

            # 分类：LLM 自主调度 vs 系统定时任务
            llm_jobs = []
            system_jobs = []
            for job in all_jobs:
                entry = {
                    "job_id": job["id"],
                    "trigger_type": job["trigger_type"],
                    "next_run_time": job["next_run_time"],
                    "trigger": job["trigger"],
                }
                if job["id"].startswith("llm_scheduled_"):
                    llm_jobs.append(entry)
                else:
                    system_jobs.append(entry)

            result = {
                "success": True,
                "current_time": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "total_events": len(all_jobs),
                "llm_scheduled": {
                    "count": len(llm_jobs),
                    "max_allowed": getattr(ts, '_LLM_JOB_PREFIX', None) and _get_max_pending(ts) or 5,
                    "jobs": llm_jobs,
                },
                "system_scheduled": {
                    "count": len(system_jobs),
                    "jobs": system_jobs,
                },
            }

            # 发送通知
            summary_parts = [f"📋 调度事件: {len(all_jobs)} 个"]
            if llm_jobs:
                summary_parts.append(f"  LLM自主调度: {len(llm_jobs)} 个")
                for j in llm_jobs:
                    summary_parts.append(f"    • {j['job_id']} → {j['next_run_time'] or '?'}")
            if system_jobs:
                summary_parts.append(f"  系统定时: {len(system_jobs)} 个")
            await wf.message_manager.send_message("\n".join(summary_parts), "info")

            return json.dumps(result, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"获取调度事件失败: {e}")
            return f"错误: {str(e)}"

    return get_scheduled_events


def _get_max_pending(ts) -> int:
    """获取 LLM 最大待执行任务数"""
    try:
        from config import settings as _settings
        return _settings.max_pending_llm_jobs
    except Exception:
        return 5


def _create_schedule_next_analysis(wf):
    @tool
    async def schedule_next_analysis(
        hours_from_now: float,
        reason: str,
        priority: int = 0,
    ) -> str:
        """
        安排下一次组合分析时间（LLM自主调度）

        重要：调用前请先使用 get_scheduled_events 查看已有调度，避免重复安排！
        如果已有类似时间的调度，可以先用 cancel_scheduled_analysis 取消旧的再安排新的。

        Args:
            hours_from_now: 多少小时后执行，可以是小数（如0.5表示30分钟，2.5表示2.5小时）
            reason: 安排原因，例如"预期FOMC会议结果公布"、"等待财报发布"、"市场波动监控"等
            priority: 优先级（-10-10，数字越小优先级越高），默认0为普通优先级

        Returns:
            调度结果（包含当前已有的 LLM 调度数量）
        """
        try:
            scheduled_time = utc_now() + timedelta(hours=hours_from_now)
            delay_seconds = hours_from_now * 3600

            # 通过 TradingSystem 添加延迟任务（带上限控制）
            ts = getattr(wf, '_trading_system', None)

            if ts is not None:
                result = ts.schedule_llm_analysis(
                    delay_seconds=delay_seconds,
                    reason=reason,
                )
                if not result["success"]:
                    # 返回失败原因，并附上已有调度信息
                    existing = ts.get_jobs_by_prefix(ts._LLM_JOB_PREFIX)
                    result["existing_llm_schedules"] = [
                        {"job_id": j["id"], "next_run_time": j["next_run_time"]}
                        for j in existing
                    ]
                    return json.dumps(result, indent=2, ensure_ascii=False)
            else:
                logger.warning("TradingSystem not available, cannot schedule delayed analysis")
                result = {}

            # 通知
            await wf.message_manager.send_message(
                f"⏰ **LLM自主调度**\n\n"
                f"安排时间: {scheduled_time.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                f"距离现在: {hours_from_now:.1f}小时\n"
                f"原因: {reason}",
                "info",
            )

            logger.info("LLM Scheduled Analysis: %s - %s", scheduled_time.isoformat(), reason)

            # 返回结果，包含当前 LLM 调度总数
            pending_count = 0
            if ts:
                pending_count = ts.count_jobs_by_prefix(ts._LLM_JOB_PREFIX)

            return json.dumps({
                "success": True,
                "job_id": result.get("job_id") if ts else None,
                "scheduled_time": scheduled_time.isoformat(),
                "hours_from_now": hours_from_now,
                "reason": reason,
                "message": f"已安排{hours_from_now:.1f}小时后的分析",
                "current_llm_pending_count": pending_count,
                "max_allowed": _get_max_pending(ts) if ts else 5,
            }, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"安排下一次分析失败: {e}")
            return f"错误: {str(e)}"

    return schedule_next_analysis


def _create_cancel_scheduled_analysis(wf):
    @tool
    async def cancel_scheduled_analysis(job_id: str) -> str:
        """
        取消一个已安排的LLM分析调度。

        只能取消 LLM 自主安排的调度（以 "llm_scheduled_" 开头的 job_id），不能取消系统定时任务。
        使用 get_scheduled_events 查看可取消的 job_id。

        Args:
            job_id: 要取消的调度任务ID（必须以 "llm_scheduled_" 开头）

        Returns:
            取消结果
        """
        try:
            ts = getattr(wf, '_trading_system', None)
            if ts is None:
                return json.dumps({
                    "success": False,
                    "message": "调度系统不可用",
                }, indent=2, ensure_ascii=False)

            # 安全检查：只允许取消 LLM 自主调度的任务
            if not job_id.startswith("llm_scheduled_"):
                return json.dumps({
                    "success": False,
                    "message": f"只能取消 LLM 自主调度的任务（llm_scheduled_* 开头），不能取消系统任务: {job_id}",
                }, indent=2, ensure_ascii=False)

            # 检查任务是否存在
            job_info = ts.get_job_info(job_id)
            if not job_info:
                return json.dumps({
                    "success": False,
                    "message": f"任务不存在或已执行完毕: {job_id}",
                }, indent=2, ensure_ascii=False)

            success = ts.remove_job(job_id)

            if success:
                await wf.message_manager.send_message(
                    f"🗑️ 已取消调度: {job_id}", "info"
                )

                # 返回剩余的 LLM 调度
                remaining = ts.get_jobs_by_prefix(ts._LLM_JOB_PREFIX)
                return json.dumps({
                    "success": True,
                    "cancelled_job_id": job_id,
                    "message": f"已取消调度 {job_id}",
                    "remaining_llm_schedules": [
                        {"job_id": j["id"], "next_run_time": j["next_run_time"]}
                        for j in remaining
                    ],
                    "remaining_count": len(remaining),
                }, indent=2, ensure_ascii=False)
            else:
                return json.dumps({
                    "success": False,
                    "message": f"取消任务失败: {job_id}",
                }, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"取消调度失败: {e}")
            return f"错误: {str(e)}"

    return cancel_scheduled_analysis
