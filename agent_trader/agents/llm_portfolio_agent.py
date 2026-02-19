"""
LLM Portfolio Agent

完全由 LLM 驱动的投资组合管理 Agent。
使用 ReAct Agent 模式，LLM 自主调用 tools 获取信息并决策。

Memory 架构：
- checkpointer (short-term): 单次 run 内的 ReAct 多步推理
- store (long-term): 跨 run 的投资记忆（持久化到 Postgres）
"""

import json
from typing import Dict, Any, Optional

from agent_trader.utils.logging_config import get_logger
from agent_trader.utils.timezone import utc_now, format_for_display
from agent_trader.agents.workflow_base import WorkflowBase
from agent_trader.agents.workflow_factory import register_workflow

logger = get_logger(__name__)

_LLM_PORTFOLIO_DEFAULT_SYSTEM_PROMPT = """\
你是一位专业的私募投资组合经理，负责管理美股以及ETF投资组合，争取达到sharpe ratio 3以上。

## 你的职责
1. 持续分析市场状况、新闻事件和组合配置
2. 基于分析自主决定是否需要调整组合
3. 决定目标仓位配置
4. 执行组合重新平衡

## 重要提示
- 你可以持有多只股票/ETF，你完全自主决策，根据市场情况灵活调整配置，做出理性、明智、专业的决策
- 只做主升不做调整，不炒毛票，多空ETF增强，严格分仓避免单票梭哈
- 杠杆ETF要考虑磨损，非特殊情况不要长期持有，但合适的使用可以带来高收益
- 重点关注美联储的消息，科技公司的消息，以及重大新闻事件
- 重点关注科技公司、金融公司和黄金，也可以思考如何对冲风险，市场不好时可以尝试买做空ETF

## 自主调度
- 分析完成后，如有需要，你可以使用schedule_next_analysis安排下一次分析时间（将作为workflow事件触发）
- 例如：预期有重要新闻（如FOMC会议、财报发布），可以提前安排分析，市场波动剧烈，可以安排更频繁的检查
- 每日例行分析默认开启，不需要手动安排
- 安排新分析前，可以先调用 get_scheduled_events 查看已有调度，避免重复安排。
- 如果已有类似时间或原因的调度，不要重复创建。可以使用 cancel_scheduled_analysis 取消不再需要的旧调度

## 现金仓位管理
- 百分比总和可以小于100%，剩余部分会自动保留为现金
- 可以根据市场情况灵活调整现金比例，如市场不确定时可以增加现金占比
"""


@register_workflow(
    "llm_portfolio",
    description="完全由 LLM 驱动的投资组合管理",
    features=["🆕 无硬编码规则", "ReAct Agent", "多工具协作", "可解释决策"],
    best_for="🌟 智能自适应组合管理（推荐）"
)
class LLMPortfolioAgent(WorkflowBase):
    """LLM 驱动的投资组合管理 Agent"""

    def _default_config(self) -> Dict[str, Any]:
        return {
            "system_prompt": _LLM_PORTFOLIO_DEFAULT_SYSTEM_PROMPT,
        }

    def __init__(self, **kwargs):
        session_id = kwargs.pop("session_id", "trading_agent")
        super().__init__(**kwargs)

        # 初始化 LLM + Tools + Agent（基类方法）
        self._init_agent(session_id=session_id)

        logger.info("LLM Portfolio Agent 已初始化")

    # ========== Workflow 执行 ==========

    async def run_workflow(self, initial_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        运行 LLM 驱动的组合管理 workflow。

        Agent 执行过程通过 _run_agent() 流式推送：
        - 每轮 ReAct 思考 → llm_thinking step（含 token 流）
        - 每次 tool call → tool_call step（含输入/输出）
        - 步骤列表完全由 Agent 动态生成，无 hardcode

        DB 持久化和统计更新由 execute() 模板方法自动处理。
        """
        context = initial_context or {}
        trigger = context.get("trigger", "manual")

        # 1. 构建分析提示（包含历史记忆）
        user_message = await self._build_analysis_prompt(context)

        # 2. 流式执行 Agent — 所有 LLM 思考和 tool call 自动 emit
        agent_result = await self._run_agent(user_message)

        # 3. 发送通知
        if agent_result.tool_calls:
            tools_msg = "**LLM调用的工具:**\n" + "\n".join(
                [f"🔧 {t}" for t in agent_result.tool_calls]
            )
            await self.message_manager.send_message(tools_msg, "info")

        if agent_result.text:
            self.emit_step(
                "decision", "LLM 分析结论", "completed",
                output_data=agent_result.text[:500],
            )
            await self.message_manager.send_message(
                f"💭 LLM分析结果:\n\n{agent_result.text}", "info"
            )

        # 4. 更新 long-term memory
        if agent_result.text:
            step_id = self.emit_step("notification", "保存分析记忆", "running")
            import time as _time
            t0 = _time.monotonic()
            summary_context = (
                f"**本次分析：**\n"
                f"- 时间: {format_for_display(utc_now(), '%Y-%m-%d %H:%M %Z')}\n"
                f"- 使用工具: {', '.join(agent_result.tool_calls) if agent_result.tool_calls else '无'}\n"
                f"- 分析结论: {agent_result.text[:1000]}\n"
            )
            summary = await self._generate_memory_summary(summary_context)
            await self._save_memory(summary, trigger, self.workflow_id)
            self.update_step(
                step_id, "completed",
                duration_ms=int((_time.monotonic() - t0) * 1000),
            )

        return {
            "success": True,
            "workflow_type": self.get_workflow_type(),
            "trigger": trigger,
            "llm_response": agent_result.text,
            "tool_calls": agent_result.tool_calls,
        }

    async def _build_analysis_prompt(self, context: Dict[str, Any]) -> str:
        """构建分析提示，包含历史记忆"""
        history_context = ""
        recalled = await self._recall_memories(limit=10)
        if recalled:
            history_context = f"""
**历史上下文摘要（你之前的分析和决策）：**
{recalled}

---
"""

        # 如果是用户直接发消息（chat），使用用户消息作为主指令
        user_message = context.get("user_message")
        if user_message:
            prompt = f"""{history_context}{user_message}"""
        else:
            context_str = json.dumps(context, indent=2, ensure_ascii=False, default=str)
            prompt = f"""{history_context}请分析当前市场和组合状况。如有必要，可以调仓。

当前触发上下文: {context_str}"""

        logger.info(f"Analysis prompt length: {len(prompt)} chars")
        return prompt
