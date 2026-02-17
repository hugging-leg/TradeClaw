"""
Trading Workflow 基类

提供所有 workflow 共享的能力：
- execute(): 模板方法 — 自动处理 DB 持久化、memory 保存、事件发射
- run_workflow(): 子类实现核心逻辑
- _run_agent(): 流式 Agent 执行 — 自动 emit tool call / LLM token 事件
- LLM / Agent / Tools 初始化（可选，子类调用 _init_agent）
- Long-term Memory（store-based recall / save）
- 实时事件流（SSE 推送给前端）
- 配置管理、统计、通知
"""

import asyncio
import json
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, Any, Optional, List

from agent_trader.interfaces.broker_api import BrokerAPI
from agent_trader.interfaces.market_data_api import MarketDataAPI
from agent_trader.interfaces.news_api import NewsAPI
from agent_trader.interfaces.factory import (
    get_broker_api, get_market_data_api, get_news_api
)
from agent_trader.messaging.message_manager import MessageManager
from agent_trader.models.trading_models import Portfolio
from agent_trader.utils.logging_config import get_logger
from agent_trader.utils.timezone import utc_now, format_for_display

if TYPE_CHECKING:
    from langgraph.store.base import BaseStore
    from langgraph.types import Checkpointer

logger = get_logger(__name__)

# Store namespace 前缀
_MEMORY_NS_PREFIX = "memories"


@dataclass
class AgentResult:
    """_run_agent() 的返回结果，包含 LLM 最终文本、tool 调用列表和原始 messages。"""
    text: str = ""
    tool_calls: List[str] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    messages: List[Any] = field(default_factory=list)
    duration_ms: int = 0


# ========== 事件广播器（全局单例，SSE endpoint 订阅） ==========

class EventBroadcaster:
    """
    全局事件广播器。

    后端 workflow 通过 emit() 发送事件，
    SSE endpoint 通过 subscribe() 获取事件流。
    支持多个并发订阅者。
    """

    def __init__(self):
        self._subscribers: List[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        """创建一个新的订阅队列"""
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """移除订阅"""
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    def emit(self, event: Dict[str, Any]) -> None:
        """向所有订阅者广播事件（非阻塞，队列满则丢弃旧事件）"""
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # 丢弃最旧的事件，腾出空间
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass


# 全局单例
event_broadcaster = EventBroadcaster()


class WorkflowBase(ABC):
    """
    Trading Workflow 基类

    对于 Agent-based workflow（使用了 _init_agent 的），子类只需实现：
    - _get_system_prompt(): 返回 system prompt 字符串
    - _build_prompt(context): 构建给 Agent 的 user message（含记忆召回等）
    - _post_agent(agent_result, context): 可选，Agent 执行完后的额外操作

    execute() 模板方法自动处理：
    - 通知（开始/完成）
    - Agent 流式执行（_run_agent）
    - 结果通知和 decision step
    - Long-term memory 保存
    - DB 持久化
    - SSE 事件广播

    子类无需手动调用 emit_step / send_notification / _save_memory 等。

    对于非 Agent workflow，可以 override run_workflow() 自定义全流程。
    """

    def __init__(
        self,
        broker_api: BrokerAPI = None,
        market_data_api: MarketDataAPI = None,
        news_api: NewsAPI = None,
        message_manager: MessageManager = None,
        checkpointer: "Optional[Checkpointer]" = None,
        store: "Optional[BaseStore]" = None,
    ):
        if message_manager is None:
            raise ValueError("MessageManager is required")

        self.broker_api = broker_api or get_broker_api()
        self.market_data_api = market_data_api or get_market_data_api()
        self.news_api = news_api or get_news_api()
        self.message_manager = message_manager

        # LangGraph memory（由 MemoryManager 注入）
        self.checkpointer = checkpointer
        self.store = store

        # 状态
        self.is_running = False
        self.current_portfolio: Optional[Portfolio] = None

        # 能力声明（子类可覆盖）
        self.supports_realtime_monitoring: bool = True

        # 统计（启动时从 DB 恢复，见 load_stats_from_db）
        self.stats: Dict[str, Any] = {
            'total_runs': 0,
            'successful_runs': 0,
            'failed_runs': 0,
            'last_run': None,
            'last_error': None,
        }

        # LLM / Agent 相关（_init_agent 后设置）
        self.llm = None
        self.agent = None
        self.tool_registry = None
        self.tools: List = []
        self.system_prompt: Optional[str] = None
        self.session_id: str = "default"

        # Workflow run 状态
        self.workflow_id: str = ""
        self.start_time = None
        self.end_time = None
        self._current_trigger: str = ""

        # 当前执行的步骤列表（用于 SSE 推送和 DB 保存）
        self._current_steps: List[Dict[str, Any]] = []

        # 用户消息队列（运行中追加 prompt）
        self._user_message_queue: asyncio.Queue[str] = asyncio.Queue()

        logger.info(f"Initialized {self.__class__.__name__}")

    # ========== 模板方法：execute() ==========

    async def execute(
        self,
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        执行 workflow 的完整流程（模板方法）。

        自动处理（子类无需关心）：
        - workflow_id / start_time / end_time
        - 开始/完成通知
        - SSE 事件广播（workflow_start / workflow_complete / workflow_error）
        - DB 持久化（_save_analysis_to_db）

        子类实现 run_workflow() 控制业务逻辑（Agent 调用、记忆、emit_step 等）。

        Returns:
            run_workflow() 返回的 result dict
        """
        self.workflow_id = self._generate_workflow_id()
        self.start_time = utc_now()
        self._current_steps = []

        context = initial_context or {}
        trigger = context.get("trigger", "manual")
        self._current_trigger = trigger  # 保存 trigger 供 snapshot 使用
        workflow_name = self.get_workflow_type()

        # 广播 workflow 开始（SSE）
        event_broadcaster.emit({
            "event": "workflow_start",
            "data": {
                "workflow_id": self.workflow_id,
                "workflow_type": workflow_name,
                "trigger": trigger,
                "timestamp": self.start_time.isoformat(),
            },
        })

        # 开始通知
        await self.send_notification(
            f"🚀 **{workflow_name} Started** ({trigger})\n\n"
            f"Starting at {format_for_display(self.start_time)}",
            "info",
        )

        # 如果是 chat 触发，显示用户消息作为第一个步骤
        user_message = context.get("user_message")
        if user_message:
            self.emit_step(
                "user_message",
                user_message[:80] + ("..." if len(user_message) > 80 else ""),
                "completed",
                output_data=user_message,
            )

        success = False
        error_msg: Optional[str] = None
        result: Dict[str, Any] = {}

        try:
            result = await self.run_workflow(initial_context)
            success = result.get("success", True)
            if not success:
                error_msg = result.get("error")
        except Exception as e:
            success = False
            error_msg = str(e)
            logger.error(f"Workflow execution failed: {e}", exc_info=True)
            result = await self._handle_workflow_error(e, self.get_workflow_type())

        # 计算执行时间
        self.end_time = utc_now()
        execution_time = (self.end_time - self.start_time).total_seconds()

        # 完成通知
        if success:
            await self.send_notification(
                f"✅ **{workflow_name} Complete**\n\n"
                f"Completed in {execution_time:.2f}s",
                "success",
            )
        else:
            await self.send_notification(
                f"❌ **{workflow_name} Failed**\n\n"
                f"Error: {error_msg}",
                "error",
            )

        # DB 持久化（对子类透明）
        await self._save_analysis_to_db(
            trigger=trigger,
            workflow_id=self.workflow_id,
            analysis_type=workflow_name,
            input_context=context,
            output_response=result.get("llm_response") or result.get("error"),
            tool_calls=result.get("tool_calls"),
            trades_executed=result.get("trades_executed"),
            execution_time_seconds=execution_time,
            success=success,
            error_message=error_msg,
        )

        # 广播 workflow 完成（SSE）
        event_broadcaster.emit({
            "event": "workflow_complete",
            "data": {
                "workflow_id": self.workflow_id,
                "workflow_type": workflow_name,
                "trigger": trigger,
                "success": success,
                "error": error_msg,
                "duration_ms": int(execution_time * 1000),
                "steps": self._current_steps,
                "timestamp": self.end_time.isoformat(),
            },
        })

        # 注入执行时间到 result（方便调用方使用）
        result["execution_time"] = execution_time
        result["workflow_id"] = self.workflow_id
        return result

    # ========== 实时事件发射 ==========

    def emit_step(
        self,
        step_type: str,
        name: str,
        status: str = "running",
        *,
        input_data: Optional[str] = None,
        output_data: Optional[str] = None,
        error: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> str:
        """
        发射一个执行步骤事件（实时推送到前端）。

        Args:
            step_type: 步骤类型（任意字符串，常见: llm_thinking / tool_call / decision / notification / user_message）
            name: 步骤名称（人类可读）
            status: 状态 (running / completed / failed)
            input_data: 输入摘要
            output_data: 输出摘要
            error: 错误信息
            duration_ms: 耗时（毫秒）

        Returns:
            step_id（用于后续更新同一 step 的状态）
        """
        step_id = f"{self.workflow_id}-{len(self._current_steps)}"
        step = {
            "id": step_id,
            "type": step_type,
            "name": name,
            "status": status,
            "timestamp": utc_now().isoformat(),
            "input": input_data,
            "output": output_data,
            "error": error,
            "duration_ms": duration_ms,
        }
        self._current_steps.append(step)

        event_broadcaster.emit({
            "event": "step",
            "data": {
                "workflow_id": self.workflow_id,
                **step,
            },
        })
        return step_id

    def update_step(
        self,
        step_id: str,
        status: str,
        *,
        input_data: Optional[str] = None,
        output_data: Optional[str] = None,
        error: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> None:
        """更新已发射的步骤状态"""
        # 更新本地记录
        for step in self._current_steps:
            if step["id"] == step_id:
                step["status"] = status
                if input_data is not None:
                    step["input"] = input_data
                if output_data is not None:
                    step["output"] = output_data
                if error is not None:
                    step["error"] = error
                if duration_ms is not None:
                    step["duration_ms"] = duration_ms
                break

        event_broadcaster.emit({
            "event": "step_update",
            "data": {
                "workflow_id": self.workflow_id,
                "id": step_id,
                "status": status,
                "input": input_data,
                "output": output_data,
                "error": error,
                "duration_ms": duration_ms,
                "timestamp": utc_now().isoformat(),
            },
        })

    # ========== LLM / Agent 初始化（子类按需调用） ==========

    def _init_agent(self, session_id: str = "default") -> None:
        """
        初始化 LLM + Tools + Agent。

        前提：子类已设置 self.system_prompt（通过 _get_system_prompt()）。
        """
        from langchain.agents import create_agent
        from agent_trader.utils.llm_utils import create_llm_client
        from agent_trader.agents.tools.registry import ToolRegistry
        from agent_trader.agents.tools.common import create_common_tools

        self.session_id = session_id
        self.llm = create_llm_client()

        # Tools
        self.tool_registry = ToolRegistry()
        all_tools = create_common_tools(self)
        self.tool_registry.register_many(all_tools)
        self.tools = self.tool_registry.get_enabled_tools()

        # Agent
        self.agent = create_agent(
            self.llm,
            self.tools,
            system_prompt=self.system_prompt,
            checkpointer=self.checkpointer,
            store=self.store,
        )

    def rebuild_agent(self) -> None:
        """重建 Agent（tool 启用/禁用变更后，或 system_prompt 更新后调用）。"""
        if self.tool_registry is None or self.llm is None:
            return

        from langchain.agents import create_agent

        self.tools = self.tool_registry.get_enabled_tools()
        self.agent = create_agent(
            self.llm,
            self.tools,
            system_prompt=self.system_prompt,
            checkpointer=self.checkpointer,
            store=self.store,
        )
        logger.info(f"Agent rebuilt with {len(self.tools)} tools")

    # ========== 流式 Agent 执行 ==========

    @property
    def chat_queue_size(self) -> int:
        """当前消息队列中待处理的消息数量"""
        return self._user_message_queue.qsize()

    def enqueue_user_message(self, message: str) -> None:
        """
        向正在运行的 Agent 追加用户消息（线程安全）。

        消息会在当前 ReAct 循环结束后被消费，Agent 将继续处理。
        如果 Agent 未在运行，消息会在下次 _run_agent 调用时被消费。
        """
        self._user_message_queue.put_nowait(message)
        # 发射 user_message step（前端即时反馈 + 记录到 _current_steps）
        self.emit_step(
            "user_message",
            message[:80] + ("..." if len(message) > 80 else ""),
            "completed",
            output_data=message,
        )
        logger.info("User message enqueued (queue size: %d)", self._user_message_queue.qsize())

    def get_queued_messages(self) -> List[str]:
        """获取当前队列中的所有待处理消息（不消费）。"""
        # asyncio.Queue 没有 peek，通过内部 _queue 读取（只读安全）
        return list(self._user_message_queue._queue)

    def clear_message_queue(self) -> int:
        """清空消息队列，返回被清除的消息数量。"""
        count = 0
        while not self._user_message_queue.empty():
            try:
                self._user_message_queue.get_nowait()
                count += 1
            except asyncio.QueueEmpty:
                break
        if count > 0:
            logger.info("Cleared %d queued messages", count)
        return count

    def cancel_queued_message(self, index: int) -> Optional[str]:
        """
        取消队列中指定位置的消息。

        Args:
            index: 0-based 索引

        Returns:
            被取消的消息内容，如果索引无效则返回 None
        """
        queue = self._user_message_queue
        items = list(queue._queue)
        if index < 0 or index >= len(items):
            return None
        removed = items.pop(index)
        queue._queue.clear()
        for item in items:
            queue._queue.append(item)
        logger.info("Cancelled queued message at index %d: %s", index, removed[:80])
        return removed

    def get_live_execution_snapshot(self) -> Optional[Dict[str, Any]]:
        """
        获取当前正在执行的 workflow 快照。

        如果 workflow 正在运行，返回当前执行的完整状态（包括已完成的步骤）。
        如果没有运行中的 workflow，返回 None。

        用于 SSE 客户端连接时恢复实时状态（replay）。
        """
        if not self.is_running or not self.workflow_id:
            return None

        return {
            "workflow_id": self.workflow_id,
            "workflow_type": self.get_workflow_type(),
            "trigger": self._current_trigger or "unknown",
            "status": "running",
            "started_at": self.start_time.isoformat() if self.start_time else None,
            "steps": list(self._current_steps),
            "chat_queue_size": self._user_message_queue.qsize(),
        }

    async def _run_agent(
        self,
        prompt: str,
        *,
        thread_id: Optional[str] = None,
    ) -> AgentResult:
        """
        流式执行 Agent（替代 ainvoke），自动 emit 每个步骤的事件。

        使用 LangGraph 的 astream(stream_mode=["messages", "updates"]) 实现：
        - "messages" mode: 逐 token 发射 LLM 输出（前端可做打字机效果）
        - "updates" mode: 每个 node 完成后发射更新（agent/tools 交替）

        支持运行中追加用户消息：
        - 每轮 astream 结束后检查 _user_message_queue
        - 如果有新消息，作为 HumanMessage 继续 stream（同一个 thread_id）
        - 前端看到 user_message step + 新的 thinking/tool 步骤

        Args:
            prompt: 用户/系统的输入 prompt
            thread_id: LangGraph thread_id（用于 checkpointer），默认自动生成

        Returns:
            AgentResult: 包含最终文本、tool 调用列表和原始 messages
        """
        from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, AIMessageChunk

        if self.agent is None:
            raise RuntimeError("Agent not initialized. Call _init_agent() first.")

        tid = thread_id or f"{self.session_id}_{self.workflow_id}"
        config = {
            "configurable": {
                "thread_id": tid,
            },
            "recursion_limit": self._get_recursion_limit(),
        }

        t0 = time.monotonic()

        # 状态追踪
        final_text = ""
        tool_calls: List[str] = []
        tool_results: List[Dict[str, Any]] = []
        all_messages: List[Any] = []

        # 动态检测 LLM node 名称（create_agent 用 "model"，create_react_agent 用 "agent"）
        _model_nodes = {
            n for n in self.agent.nodes
            if n not in ("__start__", "__end__", "tools")
        }

        # --- 消息循环：初始 prompt + 队列中的追加消息 ---
        current_input: Any = {"messages": [HumanMessage(content=prompt)]}

        while True:
            # 当前 agent 思考步骤（用于 token 流式更新）
            current_thinking_step_id: Optional[str] = None
            accumulated_tokens = ""
            # 当前正在等待结果的 tool call step ids
            pending_tool_steps: Dict[str, str] = {}  # tool_call_id -> step_id

            async for mode, chunk in self.agent.astream(
                current_input,
                config=config,
                stream_mode=["messages", "updates"],
            ):
                if mode == "messages":
                    ai_chunk, metadata = chunk
                    node = metadata.get("langgraph_node", "")

                    # 只处理 LLM node 的输出
                    if node in _model_nodes and isinstance(ai_chunk, AIMessageChunk):
                        # 文本 token
                        if ai_chunk.content:
                            token_text = ai_chunk.content if isinstance(ai_chunk.content, str) else ""
                            if token_text:
                                # 首次收到 token，创建 thinking step
                                if current_thinking_step_id is None:
                                    current_thinking_step_id = self.emit_step(
                                        "llm_thinking", "Agent 思考中", "running"
                                    )
                                    accumulated_tokens = ""

                                accumulated_tokens += token_text
                                # 发射 token 事件（前端打字机效果）
                                self._emit_token(current_thinking_step_id, token_text, accumulated_tokens)

                        # Tool call chunk（agent 决定调用 tool）
                        if ai_chunk.tool_call_chunks:
                            for tc_chunk in ai_chunk.tool_call_chunks:
                                if tc_chunk.get("name"):
                                    tool_name = tc_chunk["name"]
                                    tool_call_id = tc_chunk.get("id", "")
                                    # 创建 tool call step（pending 状态）
                                    step_id = self.emit_step(
                                        "tool_call", tool_name, "pending",
                                        input_data=json.dumps(
                                            tc_chunk.get("args", {}),
                                            ensure_ascii=False, default=str
                                        )[:500] if tc_chunk.get("args") else None,
                                    )
                                    if tool_call_id:
                                        pending_tool_steps[tool_call_id] = step_id

                elif mode == "updates":
                    # updates 是 {node_name: state_update} 的 dict
                    if not isinstance(chunk, dict):
                        continue

                    for node_name, update in chunk.items():
                        if node_name in _model_nodes:
                            # LLM node 完成一轮思考
                            msgs = update.get("messages", [])
                            for msg in msgs:
                                all_messages.append(msg)

                                if isinstance(msg, AIMessage):
                                    if msg.content:
                                        final_text = msg.content

                                    # 完成当前 thinking step
                                    if current_thinking_step_id:
                                        # 使用完整的 accumulated_tokens 作为输出
                                        thinking_output = accumulated_tokens.strip() or final_text or None

                                        # 如果有 tool calls，追加调用信息
                                        if msg.tool_calls:
                                            tc_names = [tc.get("name", "?") for tc in msg.tool_calls]
                                            suffix = f"\n\n→ 调用工具: {', '.join(tc_names)}"
                                            thinking_output = (thinking_output or "") + suffix

                                        self.update_step(
                                            current_thinking_step_id, "completed",
                                            output_data=thinking_output,
                                            duration_ms=int((time.monotonic() - t0) * 1000),
                                        )
                                        current_thinking_step_id = None
                                        accumulated_tokens = ""

                                    # 记录 tool calls
                                    if msg.tool_calls:
                                        for tc in msg.tool_calls:
                                            tool_name = tc.get("name", "unknown")
                                            tool_call_id = tc.get("id", "")
                                            tool_calls.append(tool_name)

                                            # 更新 pending tool step 的 input（现在有完整 args）
                                            if tool_call_id in pending_tool_steps:
                                                self.update_step(
                                                    pending_tool_steps[tool_call_id],
                                                    "running",
                                                    input_data=json.dumps(
                                                        tc.get("args", {}),
                                                        ensure_ascii=False, default=str
                                                    )[:500],
                                                )
                                            else:
                                                # 没有从 messages mode 捕获到的 chunk，直接创建
                                                step_id = self.emit_step(
                                                    "tool_call", tool_name, "running",
                                                    input_data=json.dumps(
                                                        tc.get("args", {}),
                                                        ensure_ascii=False, default=str
                                                    )[:500],
                                                )
                                                pending_tool_steps[tool_call_id] = step_id

                        elif node_name == "tools":
                            # Tools node 完成 — 包含 ToolMessage 结果
                            msgs = update.get("messages", [])
                            for msg in msgs:
                                all_messages.append(msg)
                                if isinstance(msg, ToolMessage):
                                    tool_call_id = getattr(msg, "tool_call_id", "")
                                    tool_name = getattr(msg, "name", "tool")
                                    content = msg.content if isinstance(msg.content, str) else str(msg.content)

                                    tool_results.append({
                                        "name": tool_name,
                                        "result": content[:1000],
                                    })

                                    # 更新对应的 tool step 为 completed
                                    if tool_call_id in pending_tool_steps:
                                        self.update_step(
                                            pending_tool_steps.pop(tool_call_id),
                                            "completed",
                                            output_data=content[:500],
                                        )

            # 关闭本轮 pending steps
            if current_thinking_step_id:
                self.update_step(current_thinking_step_id, "completed")
            for step_id in pending_tool_steps.values():
                self.update_step(step_id, "completed")

            # --- 检查用户消息队列 ---
            # 使用同一个 thread_id，checkpointer 会自动恢复上下文
            if self._user_message_queue.empty():
                break  # 没有排队消息，结束

            queued_msg = self._user_message_queue.get_nowait()
            logger.info("Processing queued user message: %s", queued_msg[:80])

            # 注意: user_message step 已在 enqueue_user_message() 中发射
            # 这里不再重复发射，直接继续 stream

            # 继续 stream — checkpointer 保持了完整对话历史
            current_input = {"messages": [HumanMessage(content=queued_msg)]}
            # 继续 while 循环

        total_duration = int((time.monotonic() - t0) * 1000)

        return AgentResult(
            text=final_text,
            tool_calls=tool_calls,
            tool_results=tool_results,
            messages=all_messages,
            duration_ms=total_duration,
        )

    def _get_recursion_limit(self) -> int:
        """获取 Agent 递归限制"""
        from config import settings as _s
        return _s.llm_recursion_limit

    def _emit_token(self, step_id: str, token: str, accumulated: str) -> None:
        """
        发射 LLM token 事件（增量推送，前端可做打字机效果）。

        这是一个独立的 SSE 事件类型 "llm_token"，不同于 step/step_update。
        前端可以选择是否消费此事件。
        """
        event_broadcaster.emit({
            "event": "llm_token",
            "data": {
                "workflow_id": self.workflow_id,
                "step_id": step_id,
                "token": token,
                "accumulated_length": len(accumulated),
            },
        })

    # ========== Long-term Memory (Store) ==========

    def _get_memory_namespace(self) -> tuple:
        """获取当前 workflow 的 store namespace"""
        return (_MEMORY_NS_PREFIX, self.get_workflow_type())

    async def _recall_memories(self, limit: int = 10) -> str:
        """从 store 中检索历史记忆，返回格式化的上下文字符串。"""
        namespace = self._get_memory_namespace()
        memories = await self.store.asearch(namespace, limit=limit)
        if memories:
            lines = []
            for m in memories:
                val = m.value
                date = val.get("date", "unknown")
                text = val.get("text", "")
                lines.append(f"[{date}] {text}")
            return "\n".join(lines)
        return ""

    async def _save_memory(self, summary: str, trigger: str, workflow_id: str) -> None:
        """将本次分析摘要保存到 store（long-term memory）"""
        namespace = self._get_memory_namespace()
        memory_id = str(uuid.uuid4())
        await self.store.aput(
            namespace,
            memory_id,
            {
                "text": summary,
                "trigger": trigger,
                "date": format_for_display(utc_now(), "%Y-%m-%d %H:%M %Z"),
                "workflow_id": workflow_id,
            },
        )
        logger.debug("Memory saved to store: %s (%d chars)", memory_id, len(summary))

    async def _generate_memory_summary(self, context_text: str) -> str:
        """使用 LLM 生成本次分析的记忆摘要。"""
        if self.llm is None:
            return context_text[:500]

        summary_prompt = f"""请将以下内容整合为简洁的投资历史摘要（限制500字以内）：

{context_text}

请生成更新后的摘要，重点保留：
1. 最近的交易决策及原因
2. 当前持仓策略和配置
3. 重要的市场观点和判断
4. 需要持续关注的风险/机会
5. 已安排的后续分析计划

只输出摘要内容，不要其他说明。"""

        try:
            response = await asyncio.to_thread(
                lambda: self.llm.invoke(summary_prompt).content
            )
            summary = response.strip()[:2000]
            logger.debug(f"Generated memory summary: {len(summary)} chars")
            return summary
        except Exception as e:
            logger.warning(f"生成摘要失败: {e}")
            return context_text[:500]

    # ========== DB 持久化 ==========

    async def _save_analysis_to_db(
        self,
        trigger: str,
        workflow_id: str,
        analysis_type: str,
        input_context: Optional[Dict] = None,
        output_response: Optional[str] = None,
        tool_calls: Optional[List[str]] = None,
        trades_executed: Optional[List] = None,
        execution_time_seconds: float = 0,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        """保存分析结果到数据库（通用方法，由 execute() 自动调用）"""
        try:
            from agent_trader.utils.db_utils import DB_AVAILABLE, get_trading_repository
            if not DB_AVAILABLE:
                return
            TradingRepository = get_trading_repository()
            if TradingRepository:
                await TradingRepository.save_analysis(
                    trigger=trigger,
                    workflow_id=workflow_id,
                    analysis_type=analysis_type,
                    input_context=input_context,
                    output_response=output_response,
                    tool_calls=tool_calls or [],
                    trades_executed=trades_executed,
                    execution_time_seconds=execution_time_seconds,
                    success=success,
                    error_message=error_message,
                )
        except Exception as e:
            logger.warning(f"保存分析历史失败: {e}")

    async def load_stats_from_db(self) -> None:
        """从 analysis_history 表恢复历史统计"""
        try:
            from agent_trader.db.repository import TradingRepository
            db_stats = await TradingRepository.get_workflow_stats()
            self.stats.update(db_stats)
            logger.info(
                "Loaded workflow stats from DB: total=%d success=%d failed=%d",
                db_stats["total_runs"],
                db_stats["successful_runs"],
                db_stats["failed_runs"],
            )
        except Exception as e:
            logger.warning("Failed to load workflow stats from DB: %s", e)

    # ========== 抽象方法 ==========

    @abstractmethod
    async def run_workflow(
        self,
        initial_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        执行工作流核心逻辑（子类实现）。

        注意：
        - workflow_id / start_time 已由 execute() 设置
        - DB 持久化和 memory 保存由 execute() 自动处理
        - 可通过 self.emit_step() 发射实时步骤事件

        Args:
            initial_context: 初始上下文字典

        Returns:
            执行结果字典，应包含:
                - success: bool
            - 可选: llm_response, tool_calls, trades_executed, error
        """
        ...

    def get_workflow_type(self) -> str:
        """获取工作流类型"""
        meta = getattr(self, '_workflow_metadata', {})
        return meta.get('type', self.__class__.__name__.lower())

    # ========== 配置管理 ==========

    def get_config(self) -> Dict[str, Any]:
        """
        获取该 workflow 的可编辑配置。

        基类提供通用 Agent 配置（llm_model, llm_recursion_limit）。
        子类通过 super().get_config() 继承，再追加自身特有配置。
        """
        from config import settings as _s
        meta = getattr(self, '_workflow_metadata', {})
        config: Dict[str, Any] = {
            "workflow_type": self.get_workflow_type(),
            "name": meta.get("description", self.get_workflow_type()),
            "system_prompt": self.system_prompt,
        }
        # Agent 通用配置（仅当 workflow 使用了 Agent 时才展示）
        if self.agent is not None:
            config["llm_model"] = _s.llm_model
            config["llm_recursion_limit"] = _s.llm_recursion_limit
        return config

    def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """更新该 workflow 的配置（运行时）"""
        from config import settings as _s

        if "system_prompt" in updates and updates["system_prompt"] is not None:
            self.system_prompt = updates["system_prompt"]
            self.rebuild_agent()
            logger.info("Agent rebuilt after system_prompt update")

        # Agent 通用配置
        if "llm_model" in updates:
            _s.llm_model = updates["llm_model"]
        if "llm_recursion_limit" in updates:
            _s.llm_recursion_limit = updates["llm_recursion_limit"]

        return self.get_config()

    # ========== 通用工具方法 ==========

    async def get_portfolio(self) -> Optional[Portfolio]:
        """获取当前组合"""
        try:
            return await self.broker_api.get_portfolio()
        except Exception as e:
            logger.error(f"获取组合失败: {e}")
            return None

    async def get_market_data(self) -> Dict[str, Any]:
        """获取市场数据"""
        try:
            return await self.market_data_api.get_market_overview()
        except Exception as e:
            logger.error(f"获取市场数据失败: {e}")
            return {}

    async def get_news(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取新闻"""
        try:
            news_items = await self.news_api.get_market_overview_news(limit=limit)
            return [
                {
                    "title": item.title,
                    "description": item.description or "",
                    "source": item.source,
                    "published_at": item.published_at.isoformat(),
                    "symbols": item.symbols
                }
                for item in news_items
            ]
        except Exception as e:
            logger.error(f"获取新闻失败: {e}")
            return []

    async def is_market_open(self) -> bool:
        """检查市场是否开盘"""
        try:
            return await self.broker_api.is_market_open()
        except Exception as e:
            logger.error(f"检查市场状态失败: {e}")
            return False

    async def send_notification(self, message: str, msg_type: str = "info"):
        """发送通知"""
        await self.message_manager.send_message(message, msg_type)

    def update_stats(self, success: bool, error: Optional[str] = None):
        """更新统计"""
        self.stats['total_runs'] += 1
        self.stats['last_run'] = utc_now().isoformat()

        if success:
            self.stats['successful_runs'] += 1
        else:
            self.stats['failed_runs'] += 1
            self.stats['last_error'] = error

    # ========== 工作流生命周期方法 ==========

    def _generate_workflow_id(self) -> str:
        """生成工作流 ID"""
        return f"{self.get_workflow_type()}_{utc_now().strftime('%Y%m%d_%H%M%S')}"

    async def _handle_workflow_error(self, error: Exception, stage: str) -> Dict[str, Any]:
        """处理工作流错误"""
        error_message = f"Error in {stage}: {str(error)}"
        logger.error(error_message)
        await self.message_manager.send_error(error_message, stage)

        return {
            "success": False,
            "error": error_message,
            "stage": stage,
            "workflow_type": self.get_workflow_type()
        }
