"""
系统类 Agent Tools

提供时间查询、市场状态检查、自主调度等系统级工具。
"""

import json
from typing import List
from datetime import timedelta

from langchain.tools import tool

from agent_trader.utils.logging_config import get_logger
from agent_trader.utils.timezone import utc_now, to_trading_tz

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
        (_create_spawn_subagent(workflow), "system"),
        (_create_spawn_parallel_subagents(workflow), "system"),
    ]


def _create_get_current_time(wf):
    @tool
    async def get_current_time() -> str:
        """
        获取当前日期和时间（含 UTC 和美东时间、星期信息）

        Returns:
            当前日期时间信息（UTC、美东时间 ET、星期几）
        """
        try:
            now_utc = utc_now()
            now_et = to_trading_tz(now_utc)

            # 星期名称映射
            weekday_names = [
                "Monday", "Tuesday", "Wednesday", "Thursday",
                "Friday", "Saturday", "Sunday",
            ]
            weekday_name = weekday_names[now_et.weekday()]
            is_weekend = now_et.weekday() >= 5

            result = {
                "current_time_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S %Z"),
                "current_time_et": now_et.strftime("%Y-%m-%d %H:%M:%S %Z"),
                "weekday": weekday_name,
                "is_weekend": is_weekend,
            }

            await wf.message_manager.send_message(
                f"🕐 当前时间: {result['current_time_et']} ({weekday_name})"
                f" | UTC: {result['current_time_utc']}",
                "info",
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
            所有调度事件列表（包括 job_id、类型、trigger_type、下次执行时间等）
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
                    "trigger": job["trigger"],
                    "trigger_args": job.get("trigger_args", {}),
                    "next_run_time": job["next_run_time"],
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
                    "max_allowed": _get_max_pending(ts),
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
                    kind = j['trigger_type']
                    summary_parts.append(f"    • [{kind}] {j['job_id']} → {j['next_run_time'] or '?'}")
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
        schedule_kind: str,
        reason: str,
        hours_from_now: float = 0,
        interval_minutes: float = 0,
        cron_expression: str = "",
        require_trading_day: bool = True,
        require_market_open: bool = False,
        priority: int = 0,
    ) -> str:
        """
        安排下一次组合分析时间（LLM自主调度），支持三种调度模式。

        重要：调用前请先使用 get_scheduled_events 查看已有调度，避免重复安排！
        如果已有类似时间的调度，可以先用 cancel_scheduled_analysis 取消旧的再安排新的。

        Args:
            schedule_kind: 调度模式 —
                "at": 一次性延迟执行（需指定 hours_from_now）
                "every": 周期性重复执行（需指定 interval_minutes）
                "cron": Cron 表达式调度（需指定 cron_expression）
            reason: 安排原因，例如"预期FOMC会议结果公布"、"等待财报发布"、"市场波动监控"等
            hours_from_now: [at模式] 多少小时后执行，可以是小数（如0.5表示30分钟）
            interval_minutes: [every模式] 每隔多少分钟执行一次（最小5分钟）
            cron_expression: [cron模式] 标准5字段cron表达式（minute hour day month day_of_week）
                例如: "*/15 9-16 * * mon-fri" 表示交易时间每15分钟执行
                      "0 9 * * mon-fri" 表示每个工作日9点执行
                      "30 10,14 * * *" 表示每天10:30和14:30执行
            require_trading_day: 是否仅在交易日执行（默认True）
            require_market_open: 是否仅在市场开放时执行（默认False）
            priority: 优先级（-10-10，数字越小优先级越高），默认0为普通优先级

        Returns:
            调度结果（包含当前已有的 LLM 调度数量）
        """
        try:
            ts = getattr(wf, '_trading_system', None)
            if ts is None:
                logger.warning("TradingSystem not available, cannot schedule analysis")
                return json.dumps({
                    "success": False,
                    "message": "调度系统不可用（可能在回测模式下）",
                }, indent=2, ensure_ascii=False)

            result: dict = {}

            if schedule_kind == "at":
                # 一次性延迟
                if hours_from_now <= 0:
                    return json.dumps({
                        "success": False,
                        "message": "at 模式需要 hours_from_now > 0",
                    }, indent=2, ensure_ascii=False)

                delay_seconds = hours_from_now * 3600
                result = ts.schedule_llm_analysis(
                    delay_seconds=delay_seconds,
                    reason=reason,
                )
                scheduled_time = utc_now() + timedelta(hours=hours_from_now)
                time_desc = f"{hours_from_now:.1f}小时后"

            elif schedule_kind == "every":
                # 周期性重复
                if interval_minutes <= 0:
                    return json.dumps({
                        "success": False,
                        "message": "every 模式需要 interval_minutes > 0",
                    }, indent=2, ensure_ascii=False)

                result = ts.schedule_llm_recurring(
                    schedule_kind="interval",
                    reason=reason,
                    interval_minutes=interval_minutes,
                    require_trading_day=require_trading_day,
                    require_market_open=require_market_open,
                )
                scheduled_time = None
                time_desc = f"每{interval_minutes}分钟"

            elif schedule_kind == "cron":
                # Cron 表达式
                if not cron_expression.strip():
                    return json.dumps({
                        "success": False,
                        "message": "cron 模式需要 cron_expression 非空",
                    }, indent=2, ensure_ascii=False)

                result = ts.schedule_llm_recurring(
                    schedule_kind="cron",
                    reason=reason,
                    cron_expr=cron_expression,
                    require_trading_day=require_trading_day,
                    require_market_open=require_market_open,
                )
                scheduled_time = None
                time_desc = f"cron({cron_expression})"

            else:
                return json.dumps({
                    "success": False,
                    "message": f"不支持的 schedule_kind: {schedule_kind}，可选: at, every, cron",
                }, indent=2, ensure_ascii=False)

            if not result.get("success"):
                # 返回失败原因，并附上已有调度信息
                existing = ts.get_jobs_by_prefix(ts._LLM_JOB_PREFIX)
                result["existing_llm_schedules"] = [
                    {"job_id": j["id"], "trigger_type": j["trigger_type"], "next_run_time": j["next_run_time"]}
                    for j in existing
                ]
                return json.dumps(result, indent=2, ensure_ascii=False)

            # 通知
            time_str = scheduled_time.strftime('%Y-%m-%d %H:%M:%S UTC') if scheduled_time else time_desc
            await wf.message_manager.send_message(
                f"⏰ **LLM自主调度** [{schedule_kind}]\n\n"
                f"调度: {time_desc}\n"
                f"原因: {reason}",
                "info",
            )

            logger.info("LLM Scheduled Analysis [%s]: %s - %s", schedule_kind, time_desc, reason)

            # 返回结果，包含当前 LLM 调度总数
            pending_count = ts.count_jobs_by_prefix(ts._LLM_JOB_PREFIX)

            return json.dumps({
                "success": True,
                "schedule_kind": schedule_kind,
                "job_id": result.get("job_id"),
                "scheduled_time": scheduled_time.isoformat() if scheduled_time else None,
                "schedule_description": time_desc,
                "reason": reason,
                "message": result.get("message", f"已安排调度: {time_desc}"),
                "current_llm_pending_count": pending_count,
                "max_allowed": _get_max_pending(ts),
            }, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"安排分析调度失败: {e}")
            return f"错误: {str(e)}"

    return schedule_next_analysis


def _create_cancel_scheduled_analysis(wf):
    @tool
    async def cancel_scheduled_analysis(job_id: str) -> str:
        """
        取消一个已安排的LLM分析调度（支持一次性和重复调度）。

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
                trigger_type = job_info.get("trigger_type", "unknown")
                await wf.message_manager.send_message(
                    f"🗑️ 已取消调度 [{trigger_type}]: {job_id}", "info"
                )

                # 返回剩余的 LLM 调度
                remaining = ts.get_jobs_by_prefix(ts._LLM_JOB_PREFIX)
                return json.dumps({
                    "success": True,
                    "cancelled_job_id": job_id,
                    "cancelled_trigger_type": trigger_type,
                    "message": f"已取消调度 {job_id} (类型: {trigger_type})",
                    "remaining_llm_schedules": [
                        {"job_id": j["id"], "trigger_type": j["trigger_type"], "next_run_time": j["next_run_time"]}
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


# ---------------------------------------------------------------------------
# SubAgent tools
# ---------------------------------------------------------------------------

def _create_spawn_subagent(wf):
    @tool
    async def spawn_subagent(task: str, timeout_seconds: int = 600) -> str:
        """
        派生一个子 Agent 执行特定分析任务。

        子 Agent 拥有与你相同的只读工具（行情、新闻、记忆、代码执行等），
        但不能执行交易操作。适用于需要独立深入分析的子任务。
        结果将作为文本返回给你，由你做最终决策。

        Args:
            task: 子 Agent 要执行的任务描述（自然语言，越具体越好）
            timeout_seconds: 超时时间（秒），默认 600

        Returns:
            子 Agent 的分析结果文本
        """
        try:
            from agent_trader.agents.subagent import SubAgentExecutor, SubAgentTask
            import uuid as _uuid

            # 创建包裹步骤，子 Agent 组步骤嵌套在其下
            wrapper_step_id = wf.emit_step(
                "subagent", f"SubAgent 分析: {task[:50]}", "running",
                input_data=task,
            )

            # 设置抑制标志：
            # 1. 阻止主 Agent 的 _run_agent 流循环将子 Agent token 发射为顶级步骤
            # 2. 静默 Telegram 等通知，避免子 Agent 工具调用导致消息泛滥
            wf._subagent_running = True
            wf.message_manager.muted = True
            try:
                executor = SubAgentExecutor(
                    parent_workflow=wf, depth=1,
                    group_parent_step_id=wrapper_step_id,
                )
                task_obj = SubAgentTask(
                    task_id=_uuid.uuid4().hex[:8],
                    task=task,
                    timeout_seconds=timeout_seconds,
                )
                results = await executor.run_subagents([task_obj])
            finally:
                wf._subagent_running = False
                wf.message_manager.muted = False

            result = results[0]

            output = {
                "task": task,
                "status": result.status,
                "output": result.output or "(无输出)",
                "tool_calls": result.tool_calls,
                "duration_ms": result.duration_ms,
            }
            if result.error:
                output["error"] = result.error

            wf.update_step(
                wrapper_step_id,
                "completed" if result.status == "success" else "failed",
                output_data=(result.output or "")[:500],
                duration_ms=result.duration_ms,
            )

            return json.dumps(output, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"派生子 Agent 失败: {e}", exc_info=True)
            wf._subagent_running = False
            wf.message_manager.muted = False
            return json.dumps({
                "task": task,
                "status": "failed",
                "error": str(e),
            }, indent=2, ensure_ascii=False)

    return spawn_subagent


def _create_spawn_parallel_subagents(wf):
    @tool
    async def spawn_parallel_subagents(tasks: List[str], timeout_seconds: int = 600) -> str:
        """
        并行派生多个子 Agent 执行不同的分析任务。所有子 Agent 同时运行。

        每个子 Agent 拥有与你相同的只读工具，但不能执行交易操作。
        适用于需要多角度分析同一问题的场景，例如同时分析技术面、基本面和情绪面。

        Args:
            tasks: 任务描述列表，每个字符串对应一个子 Agent（最多5个）
            timeout_seconds: 每个子 Agent 的超时时间（秒），默认 600

        Returns:
            所有子 Agent 的分析结果汇总
        """
        try:
            from agent_trader.agents.subagent import SubAgentExecutor, SubAgentTask
            import uuid as _uuid
            import time as _time

            t0 = _time.monotonic()

            # 创建包裹步骤，所有子 Agent 组步骤嵌套在其下
            wrapper_step_id = wf.emit_step(
                "subagent",
                "并行分析",
                "running",
                input_data="\n".join(f"- {t[:80]}" for t in tasks),
            )

            # 设置抑制标志：
            # 1. 阻止主 Agent 的 _run_agent 流循环将子 Agent token 发射为顶级步骤
            # 2. 静默 Telegram 等通知，避免子 Agent 工具调用导致消息泛滥
            wf._subagent_running = True
            wf.message_manager.muted = True
            try:
                executor = SubAgentExecutor(
                    parent_workflow=wf, depth=1,
                    group_parent_step_id=wrapper_step_id,
                )
                task_objs = [
                    SubAgentTask(
                        task_id=_uuid.uuid4().hex[:8],
                        task=t,
                        timeout_seconds=timeout_seconds,
                    )
                    for t in tasks
                ]
                results = await executor.run_subagents(task_objs)
            finally:
                wf._subagent_running = False
                wf.message_manager.muted = False

            output = {
                "total_tasks": len(tasks),
                "completed": sum(1 for r in results if r.status == "success"),
                "failed": sum(1 for r in results if r.status == "failed"),
                "timeout": sum(1 for r in results if r.status == "timeout"),
                "results": [],
            }
            for r in results:
                entry = {
                    "task_id": r.task_id,
                    "status": r.status,
                    "output": r.output or "(无输出)",
                    "tool_calls": r.tool_calls,
                    "duration_ms": r.duration_ms,
                }
                if r.error:
                    entry["error"] = r.error
                output["results"].append(entry)

            duration_ms = int((_time.monotonic() - t0) * 1000)
            all_ok = all(r.status == "success" for r in results)
            wf.update_step(
                wrapper_step_id,
                "completed" if all_ok else "failed",
                output_data=f"{output['completed']}/{output['total_tasks']} 完成",
                duration_ms=duration_ms,
            )

            return json.dumps(output, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"并行派生子 Agent 失败: {e}", exc_info=True)
            wf._subagent_running = False
            wf.message_manager.muted = False
            return json.dumps({
                "status": "failed",
                "error": str(e),
            }, indent=2, ensure_ascii=False)

    return spawn_parallel_subagents
