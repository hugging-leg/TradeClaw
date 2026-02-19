"""
认知套利 Workflow (Cognitive Arbitrage / Second-Order Momentum)

核心思想：
- 直接受益的股票已经被市场发现并涨过了
- 间接受益的股票（供应链、竞争、行业联动）反应较慢
- 买入间接受益的股票，利用时间差套利

架构（分析 vs 执行分离）：
- LLM 负责：分析新闻 → 识别间接受益 → 输出结构化买入信号 JSON
- 代码负责：到期持仓自动卖出、校验买入信号、执行交易、记录持仓
- LLM 只做分析（它擅长的），交易执行由代码保证可靠性

参考: cursor-is-great-for-finance/second_order_momentum
"""

import json
import time as _time
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from decimal import Decimal

from agent_trader.utils.logging_config import get_logger
from agent_trader.agents.workflow_base import WorkflowBase
from agent_trader.agents.workflow_factory import register_workflow
from agent_trader.models.trading_models import (
    Order, OrderSide, OrderType, TimeInForce
)
from agent_trader.utils.timezone import utc_now, ensure_utc, format_for_display

logger = get_logger(__name__)

# ============================================================
# 默认 System Prompt
# ============================================================

_CA_DEFAULT_SYSTEM_PROMPT = """\
你是一位专业的认知套利分析师，专注于利用新闻传导的时间差发现套利机会。

## 核心策略：认知套利 / 二阶动量
- 当重大新闻发生时，直接受益的股票会被市场迅速发现并涨过
- 但间接受益的股票（供应链上下游、竞争对手、行业联动）反应较慢
- 你的目标是发现这些间接受益的机会

## 你的职责（仅分析，不执行交易）
1. 使用工具获取最新新闻、市场数据和组合状态
2. 分析每条重要新闻的间接受益/受损关系
3. 输出结构化的买入信号（交易执行由系统自动完成）

## 分析框架
对每条重要新闻，思考：
- **直接受益者**是谁？（这些已经涨过了，不买）
- **间接受益者**是谁？（供应链、竞争、行业联动）
- **传导链**是什么？（越清晰越好，如 "AI芯片需求增长 → 台积电代工增加 → ASML光刻机订单增长"）
- **市场需要多久反应**？（决定建议持仓时间）

## 输出格式
分析完成后，你**必须**在回复末尾输出一个 JSON 代码块，格式如下：

```json
{
  "buy_signals": [
    {
      "ticker": "ASML",
      "reason": "AI芯片需求爆发，台积电扩产，ASML作为光刻机独家供应商将间接受益",
      "chain": "AI芯片需求增长 → 台积电代工扩产 → ASML光刻机订单增长",
      "confidence": 7.5,
      "holding_days": 10
    }
  ],
  "market_summary": "简要总结当前市场环境和你的整体判断"
}
```

## 规则
- `confidence` 范围 1-10，低于 5 的不要输出（说明你自己都没信心）
- `holding_days` 范围 3-30，与传导链长度成正比
- 如果没有好的机会，`buy_signals` 可以为空数组 `[]`
- 同一只股票不要重复推荐（系统会检查现有持仓）
- 传导链要清晰可解释，不能是模糊的关联
- 你可以使用所有可用的工具来辅助分析

## 重要
- 你**不需要**也**不能**执行交易，只需输出分析结论
- 到期持仓的卖出由系统自动处理，你不需要关心
- 专注于发现高质量的间接受益机会
"""

# ============================================================
# 认知套利 Workflow
# ============================================================

@register_workflow(
    "cognitive_arbitrage",
    description="认知套利/二阶动量策略",
    features=["📰 LLM 分析新闻", "🔗 识别间接受益", "⏱️ 自动持仓管理", "🤖 分析与执行分离"],
    best_for="利用新闻传导时间差的套利机会"
)
class CognitiveArbitrageWorkflow(WorkflowBase):
    """
    认知套利 Agent — 分析与执行分离

    流程：
    1. [代码] 自动卖出到期持仓
    2. [LLM]  使用通用 tools 分析新闻、查看持仓，输出结构化买入信号
    3. [代码] 解析买入信号 → 校验 → 执行交易 → 记录持仓

    持仓管理通过基类的 get_strategy_positions / add_strategy_position /
    update_strategy_position 接口，实盘写 DB，回测用内存，自动隔离。
    """

    def _default_config(self) -> Dict[str, Any]:
        return {
            "system_prompt": _CA_DEFAULT_SYSTEM_PROMPT,
            "max_ca_positions": 5,          # 最大同时持有 CA 持仓数
            "position_size_pct": 0.10,      # 每笔 CA 仓位占总资产的比例
            "min_confidence": 5.0,          # 最低置信度阈值 (1-10)
            "min_holding_days": 3,          # 最短持仓天数
            "max_holding_days": 30,         # 最长持仓天数
        }

    def __init__(self, **kwargs):
        session_id = kwargs.pop("session_id", "cognitive_arbitrage")
        super().__init__(**kwargs)

        # 初始化 LLM + 通用 Tools + Agent（基类方法）
        # 不注册 CA 专用 tools — 交易执行由代码驱动
        self._init_agent(session_id=session_id)

        logger.info("认知套利 Agent 已初始化（分析与执行分离模式）")

    # ========== Workflow 执行 ==========

    async def run_workflow(self, initial_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        运行认知套利 workflow。

        流程：
        1. [代码] 自动卖出到期持仓
        2. [LLM]  分析新闻，输出结构化买入信号
        3. [代码] 解析并执行买入信号
        """
        context = initial_context or {}
        trigger = context.get("trigger", "manual")

        # ---- Step 1: 代码自动卖出到期持仓 ----
        sold_results = await self._sell_expired_positions()

        # ---- Step 2: LLM 分析 ----
        user_message = await self._build_analysis_prompt(context, sold_results)
        agent_result = await self._run_agent(user_message)

        # 检测 LLM 返回空结果（可能是额度不足、模型不可用等）
        if not agent_result.text and not agent_result.tool_calls:
            logger.warning(
                "CA workflow: LLM 返回空结果 (text=%r, tools=%d, duration=%dms)",
                agent_result.text, len(agent_result.tool_calls), agent_result.duration_ms,
            )
            return {
                "success": False,
                "error": "LLM returned empty response — possibly out of quota or model unavailable",
                "workflow_type": self.get_workflow_type(),
                "trigger": trigger,
                "llm_response": "",
                "tool_calls": [],
                "sold_positions": sold_results,
                "buy_results": [],
            }

        # 发送通知
        if agent_result.tool_calls:
            tools_msg = "**调用的工具:**\n" + "\n".join(
                [f"🔧 {t}" for t in agent_result.tool_calls]
            )
            await self.message_manager.send_message(tools_msg, "info")

        # ---- Step 3: 解析买入信号并执行 ----
        buy_results = []
        if agent_result.text:
            self.emit_step(
                "decision", "CA 分析结论", "completed",
                output_data=agent_result.text[:500],
            )

            signals = self._parse_buy_signals(agent_result.text)
            logger.info(
                "CA 分析完成: 解析到 %d 个买入信号 (text_len=%d)",
                len(signals), len(agent_result.text),
            )
            for sig in signals:
                logger.info(
                    "  信号: %s confidence=%.1f holding=%dd reason=%s",
                    sig["ticker"], sig["confidence"], sig["holding_days"],
                    sig["reason"][:80],
                )

            if signals:
                buy_results = await self._execute_buy_signals(signals)
                logger.info("CA 买入执行结果: %s", buy_results)
            else:
                logger.info("CA: 无有效买入信号（可能 LLM 未输出 JSON 或置信度不足）")

            await self.message_manager.send_message(
                f"🧠 认知套利分析结果:\n\n{agent_result.text}", "info"
            )

        # ---- Step 4: 保存记忆 ----
        if agent_result.text:
            step_id = self.emit_step("notification", "保存分析记忆", "running")
            t0 = _time.monotonic()

            sold_summary = ""
            if sold_results:
                sold_tickers = [r["ticker"] for r in sold_results]
                sold_summary = f"- 已卖出到期持仓: {', '.join(sold_tickers)}\n"

            buy_summary = ""
            if buy_results:
                bought = [r["ticker"] for r in buy_results if r.get("success")]
                if bought:
                    buy_summary = f"- 新买入: {', '.join(bought)}\n"

            summary_context = (
                f"**认知套利分析：**\n"
                f"- 时间: {format_for_display(utc_now(), '%Y-%m-%d %H:%M %Z')}\n"
                f"{sold_summary}"
                f"{buy_summary}"
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
            "sold_positions": sold_results,
            "buy_results": buy_results,
        }

    # ========== 到期持仓自动卖出（代码驱动） ==========

    async def _sell_expired_positions(self) -> List[Dict[str, Any]]:
        """
        扫描并卖出所有到期的 CA 持仓。

        完全由代码驱动，不依赖 LLM。
        使用基类的 get_strategy_positions / update_strategy_position 接口。
        """
        step_id = self.emit_step("ca_sell_check", "检查到期持仓", "running")
        t0 = _time.monotonic()

        try:
            today = utc_now()
            sold_results = []

            # 查询所有 open 的策略持仓
            positions = await self.get_strategy_positions(status='open')

            if not positions:
                self.update_step(
                    step_id, "completed",
                    output_data="没有 CA 持仓",
                    duration_ms=int((_time.monotonic() - t0) * 1000),
                )
                return []

            # 检查市场状态
            market_open = await self.is_market_open()

            expired = []
            active_info = []
            for pos in positions:
                sell_date_str = pos.get("target_sell_date")
                if not sell_date_str:
                    continue
                sell_date = ensure_utc(
                    datetime.fromisoformat(sell_date_str)
                    if isinstance(sell_date_str, str) else sell_date_str
                )
                if today >= sell_date:
                    expired.append(pos)
                else:
                    days_left = (sell_date - today).days
                    active_info.append(f"{pos['ticker']}(还剩{days_left}天)")

            if not expired:
                info = f"当前{len(positions)}个CA持仓，无到期: {', '.join(active_info)}"
                self.update_step(
                    step_id, "completed",
                    output_data=info,
                    duration_ms=int((_time.monotonic() - t0) * 1000),
                )
                return []

            if not market_open:
                info = f"有{len(expired)}个到期持仓，但市场未开放，跳过卖出"
                self.update_step(
                    step_id, "completed",
                    output_data=info,
                    duration_ms=int((_time.monotonic() - t0) * 1000),
                )
                return []

            # 获取实际组合
            portfolio = await self.get_portfolio()

            for pos in expired:
                ticker = pos["ticker"]
                pos_id = pos["id"]
                sell_step_id = self.emit_step(
                    "ca_sell", f"卖出到期持仓: {ticker}", "running"
                )
                sell_t0 = _time.monotonic()

                try:
                    # 查找实际持仓数量
                    actual_qty = 0
                    if portfolio:
                        for p in portfolio.positions:
                            if p.symbol == ticker and p.quantity > 0:
                                actual_qty = int(p.quantity)
                                break

                    if actual_qty <= 0:
                        # 实际未持有，标记取消
                        await self.update_strategy_position(
                            pos_id, status='cancelled'
                        )
                        sold_results.append({
                            "ticker": ticker, "status": "cancelled",
                            "reason": "实际持仓为 0",
                        })
                        self.update_step(
                            sell_step_id, "completed",
                            output_data=f"{ticker}: 实际未持有，已取消",
                            duration_ms=int((_time.monotonic() - sell_t0) * 1000),
                        )
                        continue

                    # 获取当前价格
                    quote = await self.market_data_api.get_latest_price(ticker)
                    current_price = float(quote.get('close', 0)) if quote else 0
                    buy_price = float(pos["buy_price"])
                    pnl = (current_price - buy_price) * actual_qty
                    pnl_pct = ((current_price - buy_price) / buy_price * 100) if buy_price > 0 else 0

                    # 提交卖出订单
                    order = Order(
                        symbol=ticker,
                        side=OrderSide.SELL,
                        quantity=Decimal(actual_qty),
                        order_type=OrderType.MARKET,
                        time_in_force=TimeInForce.DAY,
                    )
                    order_id = await self.broker_api.submit_order(order)

                    if order_id:
                        await self.update_strategy_position(
                            pos_id,
                            status='sold',
                            sold_price=current_price,
                            sold_at=utc_now().isoformat(),
                            pnl=round(pnl, 2),
                        )

                        pnl_emoji = "📈" if pnl >= 0 else "📉"
                        msg = (
                            f"{pnl_emoji} CA 到期卖出 {ticker}\n"
                            f"📊 数量: {actual_qty} 股\n"
                            f"💰 买入: ${buy_price:.2f} → 卖出: ${current_price:.2f}\n"
                            f"📈 盈亏: ${pnl:+,.2f} ({pnl_pct:+.2f}%)\n"
                            f"⏱️ 持仓: {pos.get('holding_days', '?')} 天\n"
                            f"💡 原因: {(pos.get('reason') or '')[:80]}"
                        )
                        await self.message_manager.send_message(msg, "success" if pnl >= 0 else "warning")

                        sold_results.append({
                            "ticker": ticker, "status": "sold",
                            "quantity": actual_qty, "buy_price": buy_price,
                            "sell_price": current_price,
                            "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2),
                        })
                        self.update_step(
                            sell_step_id, "completed",
                            output_data=f"{ticker}: 卖出 {actual_qty}股, PnL ${pnl:+,.2f} ({pnl_pct:+.2f}%)",
                            duration_ms=int((_time.monotonic() - sell_t0) * 1000),
                        )
                    else:
                        sold_results.append({
                            "ticker": ticker, "status": "failed",
                            "reason": "订单提交失败",
                        })
                        self.update_step(
                            sell_step_id, "failed",
                            error=f"{ticker}: 订单提交失败",
                            duration_ms=int((_time.monotonic() - sell_t0) * 1000),
                        )

                except Exception as e:
                    logger.error(f"卖出 {ticker} 失败: {e}")
                    sold_results.append({
                        "ticker": ticker, "status": "error", "reason": str(e),
                    })
                    self.update_step(
                        sell_step_id, "failed", error=str(e),
                        duration_ms=int((_time.monotonic() - sell_t0) * 1000),
                    )

            # 更新汇总 step
            summary = f"到期检查完成: {len(sold_results)}笔处理"
            self.update_step(
                step_id, "completed",
                output_data=summary,
                duration_ms=int((_time.monotonic() - t0) * 1000),
            )
            return sold_results

        except Exception as e:
            logger.error(f"到期持仓检查失败: {e}")
            self.update_step(
                step_id, "failed", error=str(e),
                duration_ms=int((_time.monotonic() - t0) * 1000),
            )
            return []

    # ========== 解析 LLM 买入信号 ==========

    def _parse_buy_signals(self, llm_text: str) -> List[Dict[str, Any]]:
        """
        从 LLM 输出中解析结构化买入信号。

        支持两种格式：
        1. ```json ... ``` 代码块
        2. 裸 JSON 对象
        """
        import re

        # 尝试从 ```json ... ``` 代码块提取
        json_blocks = re.findall(r'```(?:json)?\s*\n?(.*?)\n?```', llm_text, re.DOTALL)

        for block in json_blocks:
            try:
                data = json.loads(block.strip())
                if isinstance(data, dict) and "buy_signals" in data:
                    signals = data["buy_signals"]
                    if isinstance(signals, list):
                        return self._validate_signals(signals)
            except (json.JSONDecodeError, KeyError):
                continue

        # Fallback: 尝试找裸 JSON（从 { 到 } 的最外层匹配）
        try:
            # 找最后一个 JSON 对象（通常在末尾）
            last_brace = llm_text.rfind('}')
            if last_brace >= 0:
                # 向前找匹配的 {
                depth = 0
                for i in range(last_brace, -1, -1):
                    if llm_text[i] == '}':
                        depth += 1
                    elif llm_text[i] == '{':
                        depth -= 1
                    if depth == 0:
                        candidate = llm_text[i:last_brace + 1]
                        data = json.loads(candidate)
                        if isinstance(data, dict) and "buy_signals" in data:
                            return self._validate_signals(data["buy_signals"])
                        break
        except (json.JSONDecodeError, KeyError):
            pass

        logger.warning("无法从 LLM 输出中解析买入信号")
        return []

    def _validate_signals(self, signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """校验并清洗买入信号"""
        valid = []
        for sig in signals:
            if not isinstance(sig, dict):
                continue

            ticker = sig.get("ticker", "").strip().upper()
            if not ticker:
                continue

            confidence = float(sig.get("confidence", 0))
            if confidence < self._config["min_confidence"]:
                logger.info(f"跳过 {ticker}: 置信度 {confidence} < {self._config['min_confidence']}")
                continue

            holding_days = int(sig.get("holding_days", 10))
            holding_days = max(self._config["min_holding_days"], min(self._config["max_holding_days"], holding_days))

            valid.append({
                "ticker": ticker,
                "reason": str(sig.get("reason", ""))[:500],
                "chain": str(sig.get("chain", ""))[:500],
                "confidence": confidence,
                "holding_days": holding_days,
            })

        return valid

    # ========== 执行买入信号（代码驱动） ==========

    async def _execute_buy_signals(self, signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        根据 LLM 分析结果执行买入。

        代码负责：仓位计算、重复检查、市场状态检查、下单、记录持仓。
        使用基类的策略持仓管理接口，自动适配实盘/回测。
        """
        if not signals:
            return []

        step_id = self.emit_step(
            "ca_buy", f"执行买入信号 ({len(signals)}个)", "running"
        )
        t0 = _time.monotonic()

        results = []

        try:
            # 检查市场状态
            market_open = await self.is_market_open()
            if not market_open:
                self.update_step(
                    step_id, "completed",
                    output_data="市场未开放，买入信号已记录但不执行",
                    duration_ms=int((_time.monotonic() - t0) * 1000),
                )

                await self.message_manager.send_message(
                    "市场未开放，买入信号已记录但不执行",
                    "info",
                )
                return []

            # 获取当前策略持仓
            open_positions = await self.get_strategy_positions(status='open')
            open_tickers = {p["ticker"] for p in open_positions}
            open_count = len(open_positions)

            # 获取组合
            portfolio = await self.get_portfolio()
            if not portfolio:
                self.update_step(
                    step_id, "failed", error="无法获取组合信息",
                    duration_ms=int((_time.monotonic() - t0) * 1000),
                )
                return []

            for sig in signals:
                ticker = sig["ticker"]

                # 检查持仓上限
                if open_count >= self._config["max_ca_positions"]:
                    logger.info(f"跳过 {ticker}: CA 持仓已达上限 {self._config['max_ca_positions']}")
                    results.append({
                        "ticker": ticker, "success": False,
                        "reason": f"CA 持仓已达上限 ({self._config['max_ca_positions']})",
                    })
                    continue

                # 检查是否已持有
                if ticker in open_tickers:
                    logger.info(f"跳过 {ticker}: 已持有 CA 持仓")
                    results.append({
                        "ticker": ticker, "success": False,
                        "reason": "已持有 CA 持仓",
                    })
                    continue

                # 获取价格
                try:
                    quote = await self.market_data_api.get_latest_price(ticker)
                    if not quote:
                        results.append({
                            "ticker": ticker, "success": False,
                            "reason": "无法获取价格",
                        })
                        continue

                    price = float(quote.get('close', 0) or quote.get('adj_close', 0))
                    if price <= 0:
                        results.append({
                            "ticker": ticker, "success": False,
                            "reason": "价格无效",
                        })
                        continue
                except Exception as e:
                    results.append({
                        "ticker": ticker, "success": False,
                        "reason": f"获取价格失败: {e}",
                    })
                    continue

                # 计算仓位
                position_value = float(portfolio.equity) * self._config["position_size_pct"]
                quantity = int(position_value / price)
                if quantity <= 0:
                    results.append({
                        "ticker": ticker, "success": False,
                        "reason": "资金不足",
                    })
                    continue

                # 提交订单
                try:
                    order = Order(
                        symbol=ticker,
                        side=OrderSide.BUY,
                        quantity=Decimal(quantity),
                        order_type=OrderType.MARKET,
                        time_in_force=TimeInForce.DAY,
                    )
                    order_id = await self.broker_api.submit_order(order)

                    if not order_id:
                        results.append({
                            "ticker": ticker, "success": False,
                            "reason": "订单提交失败",
                        })
                        continue

                    # 记录策略持仓（通过基类接口）
                    target_sell_date = utc_now() + timedelta(days=sig["holding_days"])
                    pos_id = await self.add_strategy_position(
                        ticker=ticker,
                        quantity=quantity,
                        buy_price=price,
                        buy_date=utc_now(),
                        target_sell_date=target_sell_date,
                        holding_days=sig["holding_days"],
                        reason=sig["reason"],
                        metadata={
                            "chain": sig["chain"],
                            "score": sig["confidence"],
                            "order_id": str(order_id),
                        },
                    )

                    open_tickers.add(ticker)
                    open_count += 1

                    await self.message_manager.send_message(
                        f"✅ CA 买入 {ticker}\n"
                        f"📊 数量: {quantity} 股 @ ${price:.2f}\n"
                        f"⏱️ 持仓计划: {sig['holding_days']} 天\n"
                        f"📅 目标卖出: {target_sell_date.strftime('%Y-%m-%d')}\n"
                        f"🎯 置信度: {sig['confidence']}/10\n"
                        f"💡 原因: {sig['reason'][:80]}\n"
                        f"🔗 传导链: {sig['chain'][:80]}",
                        "success",
                    )

                    results.append({
                        "ticker": ticker, "success": True,
                        "quantity": quantity, "price": price,
                        "holding_days": sig["holding_days"],
                        "order_id": str(order_id),
                        "position_id": pos_id,
                    })

                except Exception as e:
                    logger.error(f"CA 买入 {ticker} 失败: {e}")
                    results.append({
                        "ticker": ticker, "success": False,
                        "reason": str(e),
                    })

            # 更新 step
            bought = [r["ticker"] for r in results if r.get("success")]
            skipped = [r["ticker"] for r in results if not r.get("success")]
            summary_parts = []
            if bought:
                summary_parts.append(f"买入: {', '.join(bought)}")
            if skipped:
                summary_parts.append(f"跳过: {', '.join(skipped)}")
            summary = "; ".join(summary_parts) if summary_parts else "无操作"

            self.update_step(
                step_id, "completed",
                output_data=summary,
                duration_ms=int((_time.monotonic() - t0) * 1000),
            )
            return results

        except Exception as e:
            logger.error(f"执行买入信号失败: {e}")
            self.update_step(
                step_id, "failed", error=str(e),
                duration_ms=int((_time.monotonic() - t0) * 1000),
            )
            return results

    # ========== Prompt 构建 ==========

    async def _build_analysis_prompt(
        self,
        context: Dict[str, Any],
        sold_results: List[Dict[str, Any]],
    ) -> str:
        """构建分析提示，包含历史记忆和到期卖出结果"""

        # 历史记忆
        history_context = ""
        recalled = await self._recall_memories(limit=10)
        if recalled:
            history_context = f"""
**历史上下文摘要（你之前的认知套利分析）：**
{recalled}

---
"""

        # 到期卖出结果
        sold_context = ""
        if sold_results:
            sold_lines = []
            for r in sold_results:
                if r["status"] == "sold":
                    sold_lines.append(
                        f"- {r['ticker']}: 卖出 {r.get('quantity', '?')}股, "
                        f"PnL ${r.get('pnl', 0):+,.2f} ({r.get('pnl_pct', 0):+.2f}%)"
                    )
                elif r["status"] == "cancelled":
                    sold_lines.append(f"- {r['ticker']}: 已取消 ({r.get('reason', '')})")
                else:
                    sold_lines.append(f"- {r['ticker']}: {r['status']} ({r.get('reason', '')})")

            sold_context = f"""
**刚刚自动处理的到期持仓：**
{chr(10).join(sold_lines)}

---
"""

        # 当前 CA 持仓信息（通过基类接口）
        ca_positions_context = ""
        try:
            positions = await self.get_strategy_positions(status='open')

            if positions:
                pos_lines = []
                for p in positions:
                    sell_date_str = p.get("target_sell_date")
                    if sell_date_str:
                        sell_date = ensure_utc(
                            datetime.fromisoformat(sell_date_str)
                            if isinstance(sell_date_str, str) else sell_date_str
                        )
                        days_left = (sell_date - utc_now()).days
                    else:
                        days_left = "?"
                    meta = p.get("metadata") or {}
                    score = meta.get("score", "?")
                    pos_lines.append(
                        f"- {p['ticker']}: {p['quantity']}股 @ ${float(p['buy_price']):.2f}, "
                        f"还剩{days_left}天, 置信度{score}/10"
                    )
                ca_positions_context = f"""
**当前 CA 持仓 ({len(positions)}/{self._config["max_ca_positions"]})：**
{chr(10).join(pos_lines)}

---
"""
            else:
                ca_positions_context = f"""
**当前无 CA 持仓 (0/{self._config["max_ca_positions"]})**

---
"""
        except Exception as e:
            logger.warning(f"获取 CA 持仓信息失败: {e}")

        # 如果是用户直接发消息（chat），使用用户消息作为主指令
        user_message = context.get("user_message")
        if user_message:
            return f"{history_context}{sold_context}{ca_positions_context}{user_message}"

        context_str = json.dumps(context, indent=2, ensure_ascii=False, default=str)

        return f"""{history_context}{sold_context}{ca_positions_context}请执行认知套利分析。

获取最新新闻，分析是否有间接受益的套利机会。
记住：在回复末尾输出结构化的 JSON 买入信号（即使为空也要输出）。

当前触发上下文: {context_str}"""
