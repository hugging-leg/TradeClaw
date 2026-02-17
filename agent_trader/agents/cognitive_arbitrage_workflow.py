"""
认知套利 Workflow (Cognitive Arbitrage / Second-Order Momentum)

核心思想：
- 直接受益的股票已经被市场发现并涨过了
- 间接受益的股票（供应链、竞争、行业联动）反应较慢
- 买入间接受益的股票，利用时间差套利

架构：
- 使用 ReAct Agent 模式，LLM 自主分析新闻并决策交易
- CA 特有 tools: 查看/管理 CA 持仓、买入间接受益股票、卖出到期持仓
- 通用 tools: 新闻获取、价格查询、市场状态等（由基类 _init_agent 注入）
- 持仓跟踪使用 CAPosition 表（DB 持久化）

参考: cursor-is-great-for-finance/second_order_momentum
"""

import json
from typing import Any, Dict, List, Optional
from datetime import timedelta
from decimal import Decimal

from langchain.tools import tool
from sqlalchemy import select, update

from agent_trader.utils.logging_config import get_logger
from agent_trader.agents.workflow_base import WorkflowBase
from agent_trader.agents.workflow_factory import register_workflow
from agent_trader.db.session import get_db
from agent_trader.db.models import CAPosition
from agent_trader.models.trading_models import (
    Order, OrderSide, OrderType, TimeInForce
)
from agent_trader.utils.timezone import utc_now, ensure_utc, format_for_display

logger = get_logger(__name__)


# ============================================================
# CA 专用 Tools
# ============================================================

def create_ca_tools(workflow: "CognitiveArbitrageWorkflow") -> List[tuple]:
    """
    创建认知套利专用 tools。

    这些 tools 让 Agent 能够管理 CA 策略的持仓生命周期：
    - 查看当前 CA 持仓
    - 买入间接受益股票（带持仓期限跟踪）
    - 检查并卖出到期持仓
    """
    return [
        (_create_get_ca_positions(workflow), "ca_strategy"),   # wf unused but kept for pattern consistency
        (_create_buy_indirect_beneficiary(workflow), "ca_strategy"),
        (_create_sell_expired_positions(workflow), "ca_strategy"),
    ]


def _create_get_ca_positions(_wf):
    @tool
    async def get_ca_positions() -> str:
        """
        查看当前认知套利策略的所有持仓。

        返回每个持仓的股票代码、数量、买入价格、买入原因、传导链、
        目标卖出日期、持仓天数和当前状态。
        """
        try:
            async with get_db() as db:
                result = await db.execute(
                    select(CAPosition).where(CAPosition.status == 'open')
                )
                positions = list(result.scalars().all())

            if not positions:
                return json.dumps({"positions": [], "message": "当前没有 CA 持仓"})

            pos_list = []
            for p in positions:
                pos_list.append({
                    "ticker": p.ticker,
                    "quantity": p.quantity,
                    "buy_price": float(p.buy_price),
                    "buy_date": p.buy_date.isoformat() if p.buy_date else None,
                    "target_sell_date": p.target_sell_date.isoformat() if p.target_sell_date else None,
                    "holding_days": p.holding_days,
                    "reason": p.reason,
                    "chain": p.chain,
                    "score": p.score,
                })

            return json.dumps({
                "positions": pos_list,
                "total": len(pos_list),
            }, indent=2, ensure_ascii=False, default=str)

        except Exception as e:
            logger.error(f"获取 CA 持仓失败: {e}")
            return f"错误: {str(e)}"

    return get_ca_positions


def _create_buy_indirect_beneficiary(wf):
    @tool
    async def buy_indirect_beneficiary(
        ticker: str,
        reason: str,
        chain: str,
        confidence_score: float,
        holding_days: int,
    ) -> str:
        """
        买入间接受益股票（认知套利策略核心操作）。

        当你通过新闻分析发现某只股票是某个事件的间接受益者时，使用此工具买入。
        系统会自动跟踪持仓并在到期时提醒卖出。

        Args:
            ticker: 股票代码，如 AAPL, MSFT
            reason: 间接受益的原因分析
            chain: 传导链描述（如 "AI芯片需求增长 → 台积电代工增加 → ASML光刻机订单增长"）
            confidence_score: 置信度评分（1-10），越高越有信心
            holding_days: 计划持仓天数（3-30天），根据传导链长度和市场反应速度决定
        """
        try:
            # 参数校验
            holding_days = max(3, min(30, holding_days))
            confidence_score = max(1.0, min(10.0, confidence_score))

            # 检查市场状态
            market_open = await wf.is_market_open()
            if not market_open:
                return json.dumps({
                    "success": False,
                    "message": "市场未开放，无法执行交易",
                }, ensure_ascii=False)

            # 检查是否已有该持仓
            async with get_db() as db:
                existing = await db.execute(
                    select(CAPosition).where(
                        CAPosition.ticker == ticker.upper(),
                        CAPosition.status == 'open'
                    )
                )
                if existing.scalar_one_or_none():
                    return json.dumps({
                        "success": False,
                        "message": f"已持有 {ticker} 的 CA 持仓，不重复买入",
                    }, ensure_ascii=False)

            # 获取组合和价格
            portfolio = await wf.get_portfolio()
            if not portfolio:
                return json.dumps({"success": False, "message": "无法获取组合信息"})

            quote = await wf.market_data_api.get_latest_price(ticker.upper())
            if not quote:
                return json.dumps({"success": False, "message": f"无法获取 {ticker} 价格"})

            price = float(quote.get('close', 0) or quote.get('adj_close', 0))
            if price <= 0:
                return json.dumps({"success": False, "message": f"{ticker} 价格无效"})

            # 计算仓位大小（总资产的 10%）
            position_value = float(portfolio.equity) * 0.10
            quantity = int(position_value / price)
            if quantity <= 0:
                return json.dumps({"success": False, "message": "资金不足，无法买入"})

            # 提交订单
            order = Order(
                symbol=ticker.upper(),
                side=OrderSide.BUY,
                quantity=Decimal(quantity),
                order_type=OrderType.MARKET,
                time_in_force=TimeInForce.DAY,
            )
            order_id = await wf.broker_api.submit_order(order)

            if not order_id:
                return json.dumps({"success": False, "message": "订单提交失败"})

            # 记录持仓到数据库
            target_sell_date = utc_now() + timedelta(days=holding_days)
            async with get_db() as db:
                position = CAPosition(
                    ticker=ticker.upper(),
                    quantity=quantity,
                    buy_price=Decimal(str(price)),
                    buy_date=utc_now(),
                    target_sell_date=target_sell_date,
                    holding_days=holding_days,
                    reason=reason,
                    chain=chain,
                    score=confidence_score,
                    status='open',
                )
                db.add(position)

            await wf.message_manager.send_message(
                f"✅ CA 买入 {ticker.upper()}\n"
                f"📊 数量: {quantity} 股 @ ${price:.2f}\n"
                f"⏱️ 持仓计划: {holding_days} 天\n"
                f"📅 目标卖出: {target_sell_date.strftime('%Y-%m-%d')}\n"
                f"💡 原因: {reason[:80]}\n"
                f"🔗 传导链: {chain[:80]}",
                "success",
            )

            return json.dumps({
                "success": True,
                "ticker": ticker.upper(),
                "quantity": quantity,
                "price": price,
                "holding_days": holding_days,
                "target_sell_date": target_sell_date.isoformat(),
                "order_id": str(order_id),
            }, indent=2, ensure_ascii=False, default=str)

        except Exception as e:
            logger.error(f"CA 买入 {ticker} 失败: {e}")
            return f"错误: {str(e)}"

    return buy_indirect_beneficiary


def _create_sell_expired_positions(wf):
    @tool
    async def sell_expired_positions() -> str:
        """
        检查并卖出所有到期的 CA 持仓。

        自动扫描所有 open 状态的 CA 持仓，对已超过目标卖出日期的持仓执行市价卖出，
        并计算盈亏。
        """
        try:
            today = utc_now()
            sold_results = []

            async with get_db() as db:
                result = await db.execute(
                    select(CAPosition).where(CAPosition.status == 'open')
                )
                positions = list(result.scalars().all())

            if not positions:
                return json.dumps({"sold": [], "message": "没有 CA 持仓"})

            portfolio = await wf.get_portfolio()
            if not portfolio:
                return json.dumps({"sold": [], "message": "无法获取组合信息"})

            for pos in positions:
                sell_date = ensure_utc(pos.target_sell_date)
                if today < sell_date:
                    continue

                # 查找实际持仓
                actual_qty = 0
                for p in portfolio.positions:
                    if p.symbol == pos.ticker and p.quantity > 0:
                        actual_qty = int(p.quantity)
                        break

                if actual_qty <= 0:
                    # 实际未持有，标记取消
                    async with get_db() as db:
                        await db.execute(
                            update(CAPosition)
                            .where(CAPosition.ticker == pos.ticker, CAPosition.status == 'open')
                            .values(status='cancelled')
                        )
                    sold_results.append({
                        "ticker": pos.ticker, "status": "cancelled",
                        "reason": "实际持仓为 0",
                    })
                    continue

                # 获取当前价格
                quote = await wf.market_data_api.get_latest_price(pos.ticker)
                current_price = float(quote.get('close', 0)) if quote else 0
                buy_price = float(pos.buy_price)
                pnl = (current_price - buy_price) * actual_qty
                pnl_pct = (current_price - buy_price) / buy_price * 100 if buy_price > 0 else 0

                # 提交卖出订单
                order = Order(
                    symbol=pos.ticker,
                    side=OrderSide.SELL,
                    quantity=Decimal(actual_qty),
                    order_type=OrderType.MARKET,
                    time_in_force=TimeInForce.DAY,
                )
                order_id = await wf.broker_api.submit_order(order)

                if order_id:
                    async with get_db() as db:
                        await db.execute(
                            update(CAPosition)
                            .where(CAPosition.ticker == pos.ticker, CAPosition.status == 'open')
                            .values(
                                status='sold',
                                sold_price=Decimal(str(current_price)),
                                sold_at=utc_now(),
                                pnl=Decimal(str(pnl)),
                            )
                        )

                    pnl_emoji = "📈" if pnl >= 0 else "📉"
                    await wf.message_manager.send_message(
                        f"{pnl_emoji} CA 卖出 {pos.ticker}\n"
                        f"📊 数量: {actual_qty} 股\n"
                        f"💰 买入: ${buy_price:.2f} → 卖出: ${current_price:.2f}\n"
                        f"📈 盈亏: ${pnl:+,.2f} ({pnl_pct:+.2f}%)\n"
                        f"⏱️ 持仓: {pos.holding_days} 天",
                        "success" if pnl >= 0 else "warning",
                    )

                    sold_results.append({
                        "ticker": pos.ticker,
                        "status": "sold",
                        "quantity": actual_qty,
                        "buy_price": buy_price,
                        "sell_price": current_price,
                        "pnl": round(pnl, 2),
                        "pnl_pct": round(pnl_pct, 2),
                    })
                else:
                    sold_results.append({
                        "ticker": pos.ticker,
                        "status": "failed",
                        "reason": "订单提交失败",
                    })

            return json.dumps({
                "sold": sold_results,
                "total_expired": len(sold_results),
            }, indent=2, ensure_ascii=False, default=str)

        except Exception as e:
            logger.error(f"卖出到期持仓失败: {e}")
            return f"错误: {str(e)}"

    return sell_expired_positions


# ============================================================
# 认知套利 Workflow
# ============================================================

@register_workflow(
    "cognitive_arbitrage",
    description="认知套利/二阶动量策略",
    features=["📰 LLM 分析新闻", "🔗 识别间接受益", "⏱️ LLM 决定持仓时间", "🤖 ReAct Agent"],
    best_for="利用新闻传导时间差的套利机会"
)
class CognitiveArbitrageWorkflow(WorkflowBase):
    """
    认知套利 Agent

    使用 ReAct Agent 模式，LLM 自主：
    1. 检查到期持仓并卖出
    2. 获取并分析市场新闻
    3. 识别间接受益/受损的股票
    4. 决定是否买入以及持仓时间
    """

    def __init__(self, **kwargs):
        session_id = kwargs.pop("session_id", "cognitive_arbitrage")
        super().__init__(**kwargs)

        self.system_prompt = self._get_system_prompt()

        # 初始化 LLM + Tools + Agent（基类方法）
        self._init_agent(session_id=session_id)

        # 注册 CA 专用 tools
        ca_tools = create_ca_tools(self)
        self.tool_registry.register_many(ca_tools)
        self.tools = self.tool_registry.get_enabled_tools()
        self.rebuild_agent()

        logger.info("认知套利 Agent 已初始化")

    def _get_system_prompt(self) -> str:
        return """你是一位专业的认知套利交易员，专注于利用新闻传导的时间差进行套利。

## 核心策略：认知套利 / 二阶动量
- 当重大新闻发生时，直接受益的股票会被市场迅速发现并涨过
- 但间接受益的股票（供应链上下游、竞争对手、行业联动）反应较慢
- 你的目标是发现这些间接受益的机会，在市场完全反应前买入

## 工作流程
每次分析时，你应该：
1. **先检查到期持仓**：调用 sell_expired_positions 卖出到期的持仓
2. **查看当前 CA 持仓**：调用 get_ca_positions 了解当前持仓情况
3. **获取最新新闻**：调用 get_latest_news 获取市场新闻
4. **分析间接受益**：对每条重要新闻，思考：
   - 哪些公司是直接受益者？（这些已经涨过了，不买）
   - 哪些公司是间接受益者？（供应链、竞争、行业联动）
   - 传导链是什么？（越清晰越好）
   - 市场需要多久才能反应？（决定持仓时间）
5. **决策买入**：对有信心的间接受益股票，调用 buy_indirect_beneficiary 买入

## 决策原则
- 只买间接受益，不买直接受益（直接受益已被市场 price in）
- 传导链要清晰可解释（不能是模糊的关联）
- 置信度评分要诚实（1-10，低于 5 的不要买）
- 持仓时间与传导链长度成正比（链越长，市场反应越慢）
- 注意仓位管理，不要过度集中

## 持仓管理
- 每个 CA 持仓有目标卖出日期，到期自动卖出
- 同一只股票不重复建仓
- 总 CA 持仓不宜超过 5 个

## 重要提示
- 你可以查看组合状态、获取价格等（通用工具都可用）
- 分析要有深度，不要浅尝辄止
- 如果没有好的机会，不买也是正确的决策
"""

    # ========== Workflow 执行 ==========

    async def run_workflow(self, initial_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        运行认知套利 Agent。

        Agent 执行过程通过 _run_agent() 流式推送：
        - 每轮 ReAct 思考 → llm_thinking step（含 token 流）
        - 每次 tool call → tool_call step（含输入/输出）
        - 步骤列表完全由 Agent 动态生成，无 hardcode
        """
        context = initial_context or {}
        trigger = context.get("trigger", "manual")

        # 构建分析提示（包含历史记忆）
        user_message = await self._build_analysis_prompt(context)

        # 流式执行 Agent
        agent_result = await self._run_agent(user_message)

        # 发送通知
        if agent_result.tool_calls:
            tools_msg = "**调用的工具:**\n" + "\n".join(
                [f"🔧 {t}" for t in agent_result.tool_calls]
            )
            await self.message_manager.send_message(tools_msg, "info")

        if agent_result.text:
            self.emit_step(
                "decision", "CA 分析结论", "completed",
                output_data=agent_result.text[:500],
            )
            await self.message_manager.send_message(
                f"🧠 认知套利分析结果:\n\n{agent_result.text}", "info"
            )

        # 保存记忆
        if agent_result.text:
            step_id = self.emit_step("notification", "保存分析记忆", "running")
            import time as _time
            t0 = _time.monotonic()
            summary_context = (
                f"**认知套利分析：**\n"
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
**历史上下文摘要（你之前的认知套利分析和交易）：**
{recalled}

---
"""

        # 如果是用户直接发消息（chat），使用用户消息作为主指令
        user_message = context.get("user_message")
        if user_message:
            return f"""{history_context}{user_message}"""

        context_str = json.dumps(context, indent=2, ensure_ascii=False, default=str)

        return f"""{history_context}请执行认知套利分析。

按照你的工作流程：先检查到期持仓，再查看当前持仓，然后获取新闻并分析间接受益机会。

当前触发上下文: {context_str}"""
