import asyncio
import json
from typing import Dict, List, Any, Optional

from langchain_core.messages import HumanMessage, AIMessage
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver

from config import settings

from src.utils.logging_config import get_logger
from src.utils.timezone import utc_now, format_for_display

from src.agents.tools.registry import ToolRegistry
from src.agents.tools.common import create_common_tools
from src.agents.workflow_base import WorkflowBase
from src.agents.workflow_factory import register_workflow
from src.interfaces.broker_api import BrokerAPI
from src.interfaces.market_data_api import MarketDataAPI
from src.interfaces.news_api import NewsAPI
from src.messaging.message_manager import MessageManager
from src.utils.llm_utils import create_llm_client
from src.utils.db_utils import DB_AVAILABLE, get_trading_repository

logger = get_logger(__name__)


@register_workflow(
    "llm_portfolio",
    description="完全由 LLM 驱动的投资组合管理",
    features=["🆕 无硬编码规则", "ReAct Agent", "多工具协作", "可解释决策"],
    best_for="🌟 智能自适应组合管理（推荐）"
)
class LLMPortfolioAgent(WorkflowBase):
    """
    LLM驱动的投资组合管理Agent
    
    核心特点：
    - 无硬编码规则，完全由LLM决策
    - LLM可使用多个tools获取信息
    - LLM自主决定是否rebalance
    - 灵活、智能、可解释
    """
    
    def __init__(self,
                 broker_api: BrokerAPI = None,
                 market_data_api: MarketDataAPI = None,
                 news_api: NewsAPI = None,
                 message_manager: MessageManager = None,
                 session_id: str = "trading_agent"):
        """初始化LLM Portfolio Agent"""
        super().__init__(broker_api, market_data_api, news_api, message_manager)
        
        self.llm = create_llm_client()
        self.session_id = session_id
        
        # Tool Registry: 统一管理 tools 的启用/禁用
        self.tool_registry = ToolRegistry()
        self._register_tools()
        self.tools = self.tool_registry.get_enabled_tools()
        
        # 创建 Memory（用于保存对话状态）
        self.memory = MemorySaver()
        
        # 保存system prompt以便后续使用
        self.system_prompt = self._get_system_prompt()
        
        # 创建 Agent（system_prompt 在创建时注入，ainvoke 时无需重复传递）
        self.agent = create_agent(
            self.llm,
            self.tools,
            system_prompt=self.system_prompt,
            checkpointer=self.memory,
        )
        
        # Agent 配置
        self.agent_config = {"recursion_limit": settings.llm_recursion_limit}
        
        # Agent状态（限制内存历史大小）
        self.analysis_history = []
        self._max_analysis_history = settings.llm_max_analysis_history
        self.last_analysis_time = None
        
        # 历史摘要
        self.history_summary = ""
        self.max_summary_tokens = settings.llm_max_summary_tokens
        
        # 数据持久化
        self._db_available = DB_AVAILABLE
        
        logger.info("LLM Portfolio Agent 已初始化（支持历史摘要和数据持久化）")
    
    def _get_system_prompt(self) -> str:
        """获取系统提示"""
        return f"""你是一位专业的私募投资组合经理，负责管理美股以及ETF投资组合，争取达到sharpe ratio 3以上。

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
- 每日例行分析默认开启，不需要手动安排。

## 现金仓位管理
- 百分比总和可以小于100%，剩余部分会自动保留为现金
- 可以根据市场情况灵活调整现金比例，如市场不确定时可以增加现金占比
"""
    
    def _register_tools(self) -> None:
        """注册所有 tools 到 ToolRegistry"""
        # create_common_tools 返回所有分类的 tools（数据、分析、交易、系统）
        all_tools = create_common_tools(self)
        self.tool_registry.register_many(all_tools)

    def rebuild_agent(self) -> None:
        """
        当 tool 启用/禁用状态变更后，重新构建 agent。
        前端 toggle tool 后应调用此方法。
        """
        self.tools = self.tool_registry.get_enabled_tools()
        self.agent = create_agent(
            self.llm,
            self.tools,
            system_prompt=self.system_prompt,
            checkpointer=self.memory,
        )
        logger.info(f"Agent rebuilt with {len(self.tools)} tools")

    # ========== 配置管理 ==========

    def get_config(self) -> Dict[str, Any]:
        config = super().get_config()
        config.update({
            "llm_model": settings.llm_model,
            "llm_recursion_limit": settings.llm_recursion_limit,
            "llm_max_analysis_history": settings.llm_max_analysis_history,
            "llm_max_summary_tokens": settings.llm_max_summary_tokens,
        })
        return config

    def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        # LLM 参数（运行时修改 settings，不持久化）
        for field in ("llm_model", "llm_recursion_limit", "llm_max_analysis_history", "llm_max_summary_tokens"):
            if field in updates:
                setattr(settings, field, updates[field])

        if "llm_max_analysis_history" in updates:
            self._max_analysis_history = updates["llm_max_analysis_history"]
        if "llm_max_summary_tokens" in updates:
            self.max_summary_tokens = updates["llm_max_summary_tokens"]

        return super().update_config(updates)

    async def run_workflow(self, initial_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        运行LLM驱动的组合管理workflow
        
        Args:
            initial_context: 初始上下文（可选）
        
        Returns:
            执行结果
        """
        try:
            self.workflow_id = self._generate_workflow_id()
            self.start_time = utc_now()
            
            context = initial_context or {}
            trigger = context.get("trigger", "manual")
            
            await self.send_workflow_start_notification(f"Agent trader ({trigger})")
            
            # 构建初始提示
            user_message = self._build_analysis_prompt(context)
            
            # 每次分析使用独立的 thread_id，避免历史消息累积
            unique_thread_id = f"{self.session_id}_{self.workflow_id}"
            config = {
                "configurable": {"thread_id": unique_thread_id},
                "recursion_limit": settings.llm_recursion_limit
            }
            
            result = await self.agent.ainvoke(
                {"messages": [HumanMessage(content=user_message)]},
                config=config,
            )
            
            # 提取LLM的分析和决策
            messages = result.get("messages", [])
            final_response = ""
            tool_calls_summary = []
            
            # 分析消息历史，提取工具调用信息
            for msg in messages:
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        tool_name = tool_call.get('name', 'unknown')
                        tool_calls_summary.append(tool_name)
                elif hasattr(msg, 'content') and msg.content:
                    if isinstance(msg, AIMessage):
                        final_response = msg.content
            
            # 发送工具调用摘要
            if tool_calls_summary:
                tools_msg = "**LLM调用的工具:**\n" + "\n".join([f"🔧 {t}" for t in tool_calls_summary])
                await self.message_manager.send_message(tools_msg, "info")
            
            # 发送LLM的最终分析
            if final_response:
                await self.message_manager.send_message(
                    f"💭 LLM分析结果:\n\n{final_response}",
                    "info"
                )
            
            # 计算执行时间
            self.end_time = utc_now()
            execution_time = (self.end_time - self.start_time).total_seconds()
            
            # 保存到数据库
            await self._save_analysis_to_db(
                trigger=trigger,
                context=context,
                response=final_response,
                tool_calls=tool_calls_summary,
                execution_time=execution_time
            )
            
            # 记录到内存历史
            self.last_analysis_time = utc_now()
            self.analysis_history.append({
                "timestamp": self.last_analysis_time.isoformat(),
                "trigger": trigger,
                "response": final_response
            })
            # 限制内存历史大小
            if len(self.analysis_history) > self._max_analysis_history:
                self.analysis_history = self.analysis_history[-self._max_analysis_history:]
            
            # 更新历史摘要（类似 Cursor summarize）
            if final_response:
                await self._update_history_summary(final_response, tool_calls_summary)
            
            await self.send_workflow_complete_notification("LLM组合分析", execution_time)
            
            return {
                "success": True,
                "workflow_type": "llm_portfolio_agent",
                "workflow_id": self.workflow_id,
                "trigger": trigger,
                "llm_response": final_response,
                "tool_calls": tool_calls_summary,
                "execution_time": execution_time
            }
            
        except Exception as e:
            logger.error(f"LLM Portfolio Agent错误: {e}")
            # 保存错误到数据库
            await self._save_analysis_to_db(
                trigger=context.get("trigger", "unknown") if context else "unknown",
                context=context,
                response=None,
                tool_calls=[],
                execution_time=0,
                success=False,
                error_message=str(e)
            )
            return await self._handle_workflow_error(e, "LLM组合分析")
    
    async def _save_analysis_to_db(
        self,
        trigger: str,
        context: Optional[Dict],
        response: Optional[str],
        tool_calls: List[str],
        execution_time: float,
        success: bool = True,
        error_message: Optional[str] = None
    ):
        """保存分析结果到数据库"""
        if not self._db_available:
            return
        
        try:
            TradingRepository = get_trading_repository()
            if TradingRepository:
                await TradingRepository.save_analysis(
                    trigger=trigger,
                    workflow_id=self.workflow_id,
                    analysis_type="portfolio",
                    input_context=context,
                    output_response=response,
                    tool_calls=tool_calls,
                    execution_time_seconds=execution_time,
                    success=success,
                    error_message=error_message
                )
        except Exception as e:
            logger.warning(f"保存分析历史失败: {e}")
    
    async def _update_history_summary(self, current_analysis: str, tool_calls: List[str]):
        """
        更新历史摘要
        
        将当前分析结果整合到历史摘要中，保留关键信息，控制长度
        """
        try:
            # 构建摘要更新 prompt
            summary_prompt = f"""请将以下内容整合为简洁的投资历史摘要（限制500字以内）：

**之前的历史摘要：**
{self.history_summary if self.history_summary else "无（首次分析）"}

**本次分析：**
- 时间: {format_for_display(utc_now(), '%Y-%m-%d %H:%M %Z')}
- 使用工具: {', '.join(tool_calls) if tool_calls else '无'}
- 分析结论: {current_analysis[:1000] if current_analysis else '无'}

请生成更新后的摘要，重点保留：
1. 最近的交易决策及原因
2. 当前持仓策略和配置
3. 重要的市场观点和判断
4. 需要持续关注的风险/机会
5. 已安排的后续分析计划

只输出摘要内容，不要其他说明。"""

            response = await asyncio.to_thread(
                lambda: self.llm.invoke(summary_prompt).content
            )
            
            # 更新摘要
            self.history_summary = response.strip()[:2000]  # 限制长度
            logger.debug(f"历史摘要已更新: {len(self.history_summary)} 字符")
            
        except Exception as e:
            logger.warning(f"更新历史摘要失败: {e}")
    
    def _build_analysis_prompt(self, context: Dict[str, Any]) -> str:
        """构建分析提示，包含历史摘要"""
        
        # 历史上下文
        history_context = ""
        if self.history_summary:
            history_context = f"""
**历史上下文摘要（你之前的分析和决策）：**
{self.history_summary}

---
"""
        
        # 当前 context
        context_str = json.dumps(context, indent=2, ensure_ascii=False, default=str)
        
        prompt = f"""{history_context}请分析当前市场和组合状况。如有必要，可以调仓。

当前触发上下文: {context_str}"""
        
        logger.info(f"Analysis prompt length: {len(prompt)} chars")
        
        return prompt
