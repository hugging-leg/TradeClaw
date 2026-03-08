"""
SubAgent 并行执行引擎

允许主 Agent 动态派生轻量级子 Agent 执行独立分析任务。
子 Agent 在同一进程内以独立的 LangGraph ReAct agent 运行，
通过 asyncio.gather 实现并行执行。

设计决策：
- 子 Agent 共享主 Agent 的 LLM client 和 store，但使用独立的 thread_id
- 子 Agent 仅继承只读工具（排除交易执行类工具），交易决策由主 Agent 自行执行
- 深度限制防止无限递归（子 Agent 不能再派生子 Agent）
- 每个子 Agent 有独立的 timeout 控制
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from config import settings
from agent_trader.utils.logging_config import get_logger
from agent_trader.utils.timezone import utc_now

if TYPE_CHECKING:
    from agent_trader.agents.workflow_base import WorkflowBase

logger = get_logger(__name__)

# 写操作工具名称 — 子 Agent 不继承这些工具
_WRITE_TOOL_NAMES = frozenset({
    "rebalance_portfolio",
    "adjust_position",
    # schedule tools — 子 Agent 不应创建调度
    "schedule_next_analysis",
    "cancel_scheduled_analysis",
    # subagent tools — 防止递归
    "spawn_subagent",
    "spawn_parallel_subagents",
})


@dataclass
class SubAgentTask:
    """子 Agent 任务描述"""
    task_id: str
    task: str  # 自然语言任务描述
    timeout_seconds: int = 600
    max_iterations: int = 100  # 子 Agent 的 recursion_limit（需要足够大以完成复杂分析）


@dataclass
class SubAgentResult:
    """子 Agent 执行结果"""
    task_id: str
    status: str  # "success" | "failed" | "timeout"
    output: str  # 子 Agent 最终文本输出
    tool_calls: List[str] = field(default_factory=list)
    duration_ms: int = 0
    error: Optional[str] = None


class SubAgentExecutor:
    """
    在同一进程内并行执行多个轻量级子 Agent。

    使用方法：
        executor = SubAgentExecutor(parent_workflow=wf, depth=1)
        results = await executor.run_subagents([
            SubAgentTask(task_id="t1", task="分析 NVDA 技术面"),
            SubAgentTask(task_id="t2", task="分析 NVDA 基本面"),
        ])
    """

    def __init__(
        self,
        parent_workflow: "WorkflowBase",
        depth: int = 1,
        group_parent_step_id: Optional[str] = None,
    ):
        self.parent = parent_workflow
        self._depth = depth
        self._max_depth = settings.subagent_max_depth
        self._max_parallel = settings.subagent_max_parallel
        # 所有 subagent group 步骤的父 ID（用于嵌套在 tool call 下）
        self._group_parent_step_id = group_parent_step_id

    def _get_readonly_tools(self) -> List[Any]:
        """
        从主 Agent 的工具列表中过滤出只读工具。

        排除交易执行类工具和子 Agent 工具（防止递归）。
        """
        readonly = []
        for tool_obj in self.parent.tools:
            name = getattr(tool_obj, "name", "")
            if name not in _WRITE_TOOL_NAMES:
                readonly.append(tool_obj)
        return readonly

    async def run_subagents(
        self,
        tasks: List[SubAgentTask],
    ) -> List[SubAgentResult]:
        """
        并行执行多个子 Agent，返回结果列表。

        Args:
            tasks: 子 Agent 任务列表

        Returns:
            与 tasks 顺序对应的结果列表
        """
        # 深度检查
        if self._depth >= self._max_depth:
            return [
                SubAgentResult(
                    task_id=t.task_id,
                    status="failed",
                    output="",
                    error=f"子 Agent 深度已达上限 ({self._depth}/{self._max_depth})，不能继续派生",
                )
                for t in tasks
            ]

        # 并行数限制
        if len(tasks) > self._max_parallel:
            logger.warning(
                "子 Agent 数量 (%d) 超过上限 (%d)，截断",
                len(tasks), self._max_parallel,
            )
            tasks = tasks[: self._max_parallel]

        # 并行执行
        coros = [self._run_single(task) for task in tasks]
        results = await asyncio.gather(*coros, return_exceptions=True)

        # 处理异常
        final_results: List[SubAgentResult] = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                final_results.append(
                    SubAgentResult(
                        task_id=tasks[i].task_id,
                        status="failed",
                        output="",
                        error=str(r),
                    )
                )
            else:
                final_results.append(r)

        return final_results

    async def _run_single(self, task: SubAgentTask) -> SubAgentResult:
        """
        执行单个子 Agent，并将其内部 thinking / tool_call 步骤
        作为嵌套子步骤发射到前端（通过 parent_step_id 关联）。
        """
        from langchain.agents import create_agent
        from langchain_core.messages import (
            HumanMessage, AIMessage, AIMessageChunk, ToolMessage,
        )
        import json as _json

        t0 = time.monotonic()

        # 发射子 Agent 组步骤（父步骤）
        group_step_id = self.parent.emit_step(
            "subagent",
            f"SubAgent: {task.task[:60]}",
            "running",
            input_data=task.task,
            parent_step_id=self._group_parent_step_id,
        )

        try:
            # 创建独立的子 Agent（共享 LLM + 只读工具）
            readonly_tools = self._get_readonly_tools()
            system_prompt = (
                f"你是一个专注的分析助手。你的唯一任务是:\n\n"
                f"{task.task}\n\n"
                f"请使用可用的工具收集信息，然后给出简洁、具体的分析结论。"
                f"不要执行任何交易操作，只做分析。"
                f"完成分析后直接输出结论。"
            )

            sub_agent = create_agent(
                self.parent.llm,
                readonly_tools,
                system_prompt=system_prompt,
                checkpointer=None,
                store=self.parent.store,
            )

            thread_id = f"subagent_{task.task_id}_{uuid.uuid4().hex[:8]}"
            config = {
                "configurable": {"thread_id": thread_id},
                "recursion_limit": task.max_iterations,
            }

            # 动态检测 LLM node 名称
            _model_nodes = {
                n for n in sub_agent.nodes
                if n not in ("__start__", "__end__", "tools")
            }

            final_text = ""
            tool_calls: List[str] = []
            # 子步骤追踪
            current_thinking_step_id: Optional[str] = None
            accumulated_tokens = ""
            pending_tool_steps: Dict[str, str] = {}  # tool_call_id -> child_step_id

            async def _stream():
                nonlocal final_text, tool_calls
                nonlocal current_thinking_step_id, accumulated_tokens
                nonlocal pending_tool_steps

                async for mode, chunk in sub_agent.astream(
                    {"messages": [HumanMessage(content=task.task)]},
                    config=config,
                    stream_mode=["messages", "updates"],
                ):
                    if mode == "messages":
                        ai_chunk, metadata = chunk
                        node = metadata.get("langgraph_node", "")

                        if node in _model_nodes and isinstance(ai_chunk, AIMessageChunk):
                            # 文本 token — 子 Agent 思考
                            if ai_chunk.content:
                                token_text = ai_chunk.content if isinstance(ai_chunk.content, str) else ""
                                if token_text:
                                    if current_thinking_step_id is None:
                                        current_thinking_step_id = self.parent.emit_step(
                                            "subagent_thinking",
                                            "SubAgent 思考中",
                                            "running",
                                            parent_step_id=group_step_id,
                                        )
                                        accumulated_tokens = ""
                                    accumulated_tokens += token_text

                            # Tool call chunk
                            if ai_chunk.tool_call_chunks:
                                for tc_chunk in ai_chunk.tool_call_chunks:
                                    if tc_chunk.get("name"):
                                        tool_name = tc_chunk["name"]
                                        tool_call_id = tc_chunk.get("id", "")
                                        child_step_id = self.parent.emit_step(
                                            "subagent_tool_call",
                                            tool_name,
                                            "pending",
                                            input_data=_json.dumps(
                                                tc_chunk.get("args", {}),
                                                ensure_ascii=False, default=str,
                                            )[:500] if tc_chunk.get("args") else None,
                                            parent_step_id=group_step_id,
                                        )
                                        if tool_call_id:
                                            pending_tool_steps[tool_call_id] = child_step_id

                    elif mode == "updates":
                        if not isinstance(chunk, dict):
                            continue

                        for node_name, update in chunk.items():
                            if node_name in _model_nodes:
                                msgs = update.get("messages", [])
                                for msg in msgs:
                                    if isinstance(msg, AIMessage):
                                        if msg.content:
                                            final_text = msg.content

                                        # 完成 thinking 子步骤
                                        if current_thinking_step_id:
                                            thinking_output = accumulated_tokens.strip() or final_text or None
                                            if msg.tool_calls:
                                                tc_names = [tc.get("name", "?") for tc in msg.tool_calls]
                                                suffix = f"\n\n→ 调用: {', '.join(tc_names)}"
                                                thinking_output = (thinking_output or "") + suffix
                                            self.parent.update_step(
                                                current_thinking_step_id, "completed",
                                                output_data=thinking_output,
                                                duration_ms=int((time.monotonic() - t0) * 1000),
                                            )
                                            current_thinking_step_id = None
                                            accumulated_tokens = ""

                                        # 记录 tool calls + 更新 pending
                                        if msg.tool_calls:
                                            for tc in msg.tool_calls:
                                                tool_name = tc.get("name", "unknown")
                                                tool_call_id = tc.get("id", "")
                                                tool_calls.append(tool_name)
                                                if tool_call_id in pending_tool_steps:
                                                    self.parent.update_step(
                                                        pending_tool_steps[tool_call_id],
                                                        "running",
                                                        input_data=_json.dumps(
                                                            tc.get("args", {}),
                                                            ensure_ascii=False, default=str,
                                                        )[:500],
                                                    )
                                                else:
                                                    child_step_id = self.parent.emit_step(
                                                        "subagent_tool_call",
                                                        tool_name,
                                                        "running",
                                                        input_data=_json.dumps(
                                                            tc.get("args", {}),
                                                            ensure_ascii=False, default=str,
                                                        )[:500],
                                                        parent_step_id=group_step_id,
                                                    )
                                                    pending_tool_steps[tool_call_id] = child_step_id

                            elif node_name == "tools":
                                msgs = update.get("messages", [])
                                for msg in msgs:
                                    if isinstance(msg, ToolMessage):
                                        tool_call_id = getattr(msg, "tool_call_id", "")
                                        content = msg.content if isinstance(msg.content, str) else str(msg.content)
                                        if tool_call_id in pending_tool_steps:
                                            self.parent.update_step(
                                                pending_tool_steps.pop(tool_call_id),
                                                "completed",
                                                output_data=content[:500],
                                            )

                # 关闭遗留的子步骤
                if current_thinking_step_id:
                    self.parent.update_step(current_thinking_step_id, "completed")
                for cid in pending_tool_steps.values():
                    self.parent.update_step(cid, "completed")

            await asyncio.wait_for(
                _stream(),
                timeout=task.timeout_seconds,
            )

            duration_ms = int((time.monotonic() - t0) * 1000)

            # 更新组步骤状态
            self.parent.update_step(
                group_step_id, "completed",
                output_data=final_text[:500] if final_text else "(无输出)",
                duration_ms=duration_ms,
            )

            return SubAgentResult(
                task_id=task.task_id,
                status="success",
                output=final_text,
                tool_calls=tool_calls,
                duration_ms=duration_ms,
            )

        except asyncio.TimeoutError:
            duration_ms = int((time.monotonic() - t0) * 1000)
            self.parent.update_step(
                group_step_id, "failed",
                error=f"超时 ({task.timeout_seconds}s)",
                duration_ms=duration_ms,
            )
            return SubAgentResult(
                task_id=task.task_id,
                status="timeout",
                output="",
                duration_ms=duration_ms,
                error=f"子 Agent 执行超时 ({task.timeout_seconds}s)",
            )

        except Exception as e:
            duration_ms = int((time.monotonic() - t0) * 1000)
            logger.error("子 Agent %s 执行失败: %s", task.task_id, e, exc_info=True)
            self.parent.update_step(
                group_step_id, "failed",
                error=str(e),
                duration_ms=duration_ms,
            )
            return SubAgentResult(
                task_id=task.task_id,
                status="failed",
                output="",
                duration_ms=duration_ms,
                error=str(e),
            )
