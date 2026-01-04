"""
认知套利 Workflow (Cognitive Arbitrage / Second-Order Momentum)

核心思想：
- 直接受益的股票已经被市场发现并涨过了
- 间接受益的股票（供应链、竞争、行业联动）反应较慢
- 买入间接受益评分最高的股票，利用时间差套利

流程：
1. 检查并卖出到期持仓
2. 获取市场新闻
3. LLM 分析每条新闻，识别直接/间接受益/受损的股票
4. 累积评分（只关注间接受益）
5. LLM 决定持仓时间
6. 买入评分最高的间接受益股票

参考: cursor-is-great-for-finance/second_order_momentum
"""

import asyncio
import json
import re
from src.utils.logging_config import get_logger
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from decimal import Decimal
from dataclasses import dataclass, field

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select, update
from src.agents.workflow_base import WorkflowBase
from src.agents.workflow_factory import register_workflow
from src.db.session import get_db
from src.db.models import CAPosition
from src.interfaces.broker_api import BrokerAPI
from src.interfaces.market_data_api import MarketDataAPI
from src.interfaces.news_api import NewsAPI
from src.messaging.message_manager import MessageManager
from src.models.trading_models import (
    TradingDecision, TradingAction, Order, OrderSide, OrderType, TimeInForce
)
from src.utils.llm_utils import create_llm_client

logger = get_logger(__name__)


# ============================================================
# 配置
# ============================================================

SCORING_CONFIG = {
    "direct_min_score": 7,
    "direct_max_score": 10,
    "indirect_multiplier": 1.5,
    "min_confidence": 3,
    "score_window_days": 7,
}

TRADING_CONFIG = {
    "top_k": 3,
    "default_holding_days": 7,
    "min_holding_days": 3,
    "max_holding_days": 14,
    "position_size_pct": 0.10,
    "max_positions": 5,
}


# ============================================================
# 数据模型
# ============================================================

@dataclass
class ScoreRecord:
    """评分记录"""
    score: float
    score_type: str
    reason: str
    chain: str
    news_title: str
    date: str


@dataclass
class TickerScore:
    """股票评分"""
    ticker: str
    total_score: float = 0
    records: List[ScoreRecord] = field(default_factory=list)


# ============================================================
# LLM 分析提示
# ============================================================

NEWS_ANALYSIS_PROMPT = """你是一个专业的股票分析师，分析新闻对股票的正面和负面影响。

## 任务
分析这条新闻，找出：
1. **直接受益/受损**的股票（新闻直接相关）
2. **间接受益/受损**的股票（供应链、竞争、行业联动等）

## 评分规则
- **直接影响**：7-10 分（正面为正，负面为负）
- **间接影响**：1-6 分（正面为正，负面为负）

## 输出格式（严格 JSON）
```json
{
  "direct_benefits": [{"ticker": "XXX", "relevance": 8, "reason": "利好原因"}],
  "direct_negatives": [{"ticker": "XXX", "relevance": -8, "reason": "利空原因"}],
  "indirect_benefits": [{"ticker": "XXX", "confidence": 4, "reason": "间接利好", "chain": "传导链"}],
  "indirect_negatives": [{"ticker": "XXX", "confidence": -4, "reason": "间接利空", "chain": "传导链"}]
}
```

注意：只输出美股代码，只输出 JSON。
"""

HOLDING_DECISION_PROMPT = """你是一个专业的交易员，根据买入原因决定最佳持仓时间。

## 买入信息
股票: {ticker}
间接受益原因: {reason}
传导链: {chain}
评分: {score}

## 决定持仓天数
考虑因素：
- 传导链越长，市场反应越慢，持仓时间越长
- 评分越高，信心越足，可以持仓更久
- 避免过长持仓导致风险

## 输出格式（严格 JSON）
```json
{{
  "holding_days": 7,
  "reasoning": "分析原因"
}}
```

holding_days 范围: {min_days} - {max_days} 天
只输出 JSON。
"""


# ============================================================
# 认知套利 Workflow
# ============================================================

@register_workflow(
    "cognitive_arbitrage",
    description="认知套利/二阶动量策略",
    features=["📰 LLM 分析新闻", "🔗 识别间接受益", "⏱️ LLM 决定持仓时间"],
    best_for="利用新闻传导时间差的套利机会"
)
class CognitiveArbitrageWorkflow(WorkflowBase):
    """认知套利工作流"""

    def __init__(
        self,
        broker_api: BrokerAPI = None,
        market_data_api: MarketDataAPI = None,
        news_api: NewsAPI = None,
        message_manager: MessageManager = None,
        news_limit: int = 20,
    ):
        super().__init__(broker_api, market_data_api, news_api, message_manager)

        self.llm = create_llm_client()
        self.news_limit = news_limit

        # 评分表
        self.ticker_scores: Dict[str, TickerScore] = {}

        # 已分析过的新闻 ID
        self.analyzed_news_ids: set = set()

        logger.info("认知套利 Workflow 已初始化")

    # ==================== 持仓管理（数据库） ====================

    async def _get_open_positions(self) -> List[CAPosition]:
        """获取所有未平仓持仓"""
        async with get_db() as db:
            result = await db.execute(
                select(CAPosition).where(CAPosition.status == 'open')
            )
            return list(result.scalars().all())

    async def _get_position(self, ticker: str) -> Optional[CAPosition]:
        """获取指定股票的持仓"""
        async with get_db() as db:
            result = await db.execute(
                select(CAPosition).where(
                    CAPosition.ticker == ticker,
                    CAPosition.status == 'open'
                )
            )
            return result.scalar_one_or_none()

    async def _add_position(
        self,
        ticker: str,
        quantity: int,
        buy_price: float,
        target_sell_date: datetime,
        holding_days: int,
        reason: str,
        chain: str,
        score: float
    ):
        """添加持仓记录到数据库"""
        async with get_db() as db:
            position = CAPosition(
                ticker=ticker,
                quantity=quantity,
                buy_price=Decimal(str(buy_price)),
                buy_date=datetime.now(),
                target_sell_date=target_sell_date,
                holding_days=holding_days,
                reason=reason,
                chain=chain,
                score=score,
                status='open'
            )
            db.add(position)
            logger.info(f"已记录持仓: {ticker} x{quantity}")

    async def _close_position(
        self,
        ticker: str,
        sold_price: float,
        pnl: float
    ):
        """平仓（更新状态为已卖出）"""
        async with get_db() as db:
            await db.execute(
                update(CAPosition)
                .where(CAPosition.ticker == ticker, CAPosition.status == 'open')
                .values(
                    status='sold',
                    sold_price=Decimal(str(sold_price)),
                    sold_at=datetime.now(),
                    pnl=Decimal(str(pnl))
                )
            )
            logger.info(f"已平仓: {ticker}, PnL: {pnl:.2f}")

    # ==================== 卖出检查 ====================

    async def _check_and_sell_expired(self) -> List[str]:
        """检查并卖出到期持仓"""
        today = datetime.now()
        sold_tickers = []

        # 从数据库获取所有未平仓持仓
        positions = await self._get_open_positions()

        for pos in positions:
            if today >= pos.target_sell_date:
                logger.info(f"持仓到期，准备卖出: {pos.ticker}")

                try:
                    # 获取当前持仓数量（从 broker）
                    portfolio = await self.get_portfolio()
                    actual_qty = 0
                    for p in portfolio.positions:
                        if p.symbol == pos.ticker and p.quantity > 0:
                            actual_qty = int(p.quantity)
                            break

                    if actual_qty <= 0:
                        logger.warning(f"{pos.ticker} 实际持仓为 0，标记为已取消")
                        await self._cancel_position(pos.ticker)
                        continue

                    # 获取当前价格
                    quote = await self.market_data_api.get_latest_price(pos.ticker)
                    current_price = float(quote.get('close', 0)) if quote else 0
                    buy_price = float(pos.buy_price)

                    # 计算盈亏
                    pnl = (current_price - buy_price) * actual_qty
                    pnl_pct = (current_price - buy_price) / buy_price * 100

                    # 提交卖出订单
                    order = Order(
                        symbol=pos.ticker,
                        side=OrderSide.SELL,
                        quantity=Decimal(actual_qty),
                        order_type=OrderType.MARKET,
                        time_in_force=TimeInForce.DAY
                    )
                    order_id = await self.broker_api.submit_order(order)

                    if order_id:
                        sold_tickers.append(pos.ticker)
                        await self._close_position(pos.ticker, current_price, pnl)

                        pnl_emoji = "📈" if pnl >= 0 else "📉"
                        await self.message_manager.send_message(
                            f"{pnl_emoji} 卖出 {pos.ticker}\n"
                            f"📊 数量: {actual_qty} 股\n"
                            f"💰 买入: ${buy_price:.2f} → 卖出: ${current_price:.2f}\n"
                            f"📈 盈亏: ${pnl:+,.2f} ({pnl_pct:+.2f}%)\n"
                            f"⏱️ 持仓: {pos.holding_days} 天",
                            "success" if pnl >= 0 else "warning"
                        )
                        logger.info(f"卖出成功: {pos.ticker}, 盈亏: ${pnl:+,.2f}")
                    else:
                        logger.error(f"卖出失败: {pos.ticker}")

                except Exception as e:
                    logger.error(f"卖出 {pos.ticker} 失败: {e}")

        return sold_tickers

    async def _cancel_position(self, ticker: str):
        """取消持仓（实际未持有）"""
        async with get_db() as db:
            await db.execute(
                update(CAPosition)
                .where(CAPosition.ticker == ticker, CAPosition.status == 'open')
                .values(status='cancelled')
            )
            logger.info(f"持仓已取消: {ticker}")

    # ==================== 新闻分析 ====================

    async def _analyze_news_with_llm(self, news: Dict) -> Dict:
        """用 LLM 分析单条新闻"""
        title = news.get('title', '') or ''
        description = (news.get('description', '') or '')[:500]
        tickers = news.get('symbols', []) or news.get('tickers', []) or []

        user_prompt = f"""分析新闻：
标题: {title}
摘要: {description}
相关股票: {', '.join(t.upper() for t in tickers[:10])}
"""

        try:
            response = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: self.llm.invoke([
                    SystemMessage(content=NEWS_ANALYSIS_PROMPT),
                    HumanMessage(content=user_prompt)
                ])
            )

            json_match = re.search(r'\{[\s\S]*\}', response.content)
            if json_match:
                result = json.loads(json_match.group())
                result["_news_title"] = title[:80]
                return result
            return {"direct_benefits": [], "indirect_benefits": []}
        except Exception as e:
            logger.warning(f"分析新闻失败: {e}")
            return {"direct_benefits": [], "indirect_benefits": []}

    async def _decide_holding_days(
        self, ticker: str, reason: str, chain: str, score: float
    ) -> int:
        """让 LLM 决定持仓时间"""
        prompt = HOLDING_DECISION_PROMPT.format(
            ticker=ticker,
            reason=reason,
            chain=chain,
            score=score,
            min_days=TRADING_CONFIG["min_holding_days"],
            max_days=TRADING_CONFIG["max_holding_days"]
        )

        try:
            response = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: self.llm.invoke([HumanMessage(content=prompt)])
            )

            json_match = re.search(r'\{[\s\S]*\}', response.content)
            if json_match:
                result = json.loads(json_match.group())
                days = result.get("holding_days", TRADING_CONFIG["default_holding_days"])
                # 限制范围
                days = max(TRADING_CONFIG["min_holding_days"], 
                          min(TRADING_CONFIG["max_holding_days"], days))
                logger.info(f"LLM 决定 {ticker} 持仓 {days} 天: {result.get('reasoning', '')[:50]}")
                return days
        except Exception as e:
            logger.warning(f"LLM 决定持仓时间失败: {e}")

        return TRADING_CONFIG["default_holding_days"]

    def _update_scores(self, news: Dict, analysis: Dict, date: datetime):
        """更新评分表"""
        news_title = news.get("title", "")[:80]
        date_str = date.isoformat()

        seen_direct = set()
        seen_indirect = set()

        def add_score(ticker: str, score: float, score_type: str, reason: str, chain: str = ""):
            ticker = ticker.upper()
            if ticker not in self.ticker_scores:
                self.ticker_scores[ticker] = TickerScore(ticker=ticker)

            self.ticker_scores[ticker].total_score += score
            self.ticker_scores[ticker].records.append(ScoreRecord(
                score=score, score_type=score_type, reason=reason,
                chain=chain, news_title=news_title, date=date_str
            ))

        # 直接受益
        for item in analysis.get("direct_benefits", []):
            ticker = item.get("ticker", "").upper()
            if not ticker or ticker in seen_direct:
                continue
            seen_direct.add(ticker)
            raw = abs(item.get("relevance", 8))
            score = min(SCORING_CONFIG["direct_max_score"], 
                       max(SCORING_CONFIG["direct_min_score"], raw))
            add_score(ticker, score, "direct_positive", item.get("reason", ""))

        # 间接受益 - 这是我们要买的
        for item in analysis.get("indirect_benefits", []):
            ticker = item.get("ticker", "").upper()
            confidence = abs(item.get("confidence", 0))
            if not ticker or confidence < SCORING_CONFIG["min_confidence"] or ticker in seen_indirect:
                continue
            seen_indirect.add(ticker)
            score = confidence * SCORING_CONFIG["indirect_multiplier"]
            add_score(ticker, score, "indirect_positive", 
                     item.get("reason", ""), item.get("chain", ""))

        # 间接受损
        for item in analysis.get("indirect_negatives", []):
            ticker = item.get("ticker", "").upper()
            confidence = abs(item.get("confidence", 0))
            if not ticker or confidence < SCORING_CONFIG["min_confidence"] or ticker in seen_indirect:
                continue
            seen_indirect.add(ticker)
            score = -confidence * SCORING_CONFIG["indirect_multiplier"]
            add_score(ticker, score, "indirect_negative",
                     item.get("reason", ""), item.get("chain", ""))

    def _clean_old_scores(self, current_date: datetime):
        """清理过期评分"""
        cutoff = current_date - timedelta(days=SCORING_CONFIG["score_window_days"])

        for ticker in list(self.ticker_scores.keys()):
            ts = self.ticker_scores[ticker]
            ts.records = [r for r in ts.records if datetime.fromisoformat(r.date) >= cutoff]
            ts.total_score = sum(r.score for r in ts.records)
            if not ts.records:
                del self.ticker_scores[ticker]

    def _get_top_indirect_tickers(self, k: int) -> List[tuple]:
        """获取间接受益评分最高的股票"""
        candidates = []

        for ticker, ts in self.ticker_scores.items():
            indirect_score = sum(
                r.score for r in ts.records
                if "indirect" in r.score_type and r.score > 0
            )
            if indirect_score > 0:
                records = [r for r in ts.records if "indirect" in r.score_type and r.score > 0]
                candidates.append((ticker, indirect_score, records))

        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:k]

    # ==================== 主流程 ====================

    async def run_workflow(self, trigger_reason: str = "scheduled", **kwargs) -> TradingDecision:
        """执行认知套利工作流"""
        current_date = datetime.now()

        await self.message_manager.send_message("🧠 认知套利分析开始", "info")

        # 1. 检查并卖出到期持仓
        sold = await self._check_and_sell_expired()
        if sold:
            await self.message_manager.send_message(
                f"📤 已卖出 {len(sold)} 只到期持仓: {sold}", "info"
            )

        # 2. 获取组合
        portfolio = await self.get_portfolio()
        if not portfolio:
            return TradingDecision(
                action=TradingAction.HOLD, symbol="N/A",
                reasoning="无法获取组合信息", confidence=Decimal("0.0")
            )

        # 3. 获取新闻
        try:
            news_list = await self.news_api.get_market_overview_news(limit=self.news_limit)
            news_list = [
                {
                    "id": getattr(n, 'id', None) or hash(n.title),
                    "title": n.title,
                    "description": n.description,
                    "symbols": n.symbols,
                }
                for n in news_list
            ]
        except Exception as e:
            logger.error(f"获取新闻失败: {e}")
            return TradingDecision(
                action=TradingAction.HOLD, symbol="N/A",
                reasoning=f"获取新闻失败: {e}", confidence=Decimal("0.0")
            )

        # 4. 分析新闻
        news_to_analyze = [n for n in news_list if n["id"] not in self.analyzed_news_ids]

        if news_to_analyze:
            await self.message_manager.send_message(
                f"📰 分析 {len(news_to_analyze)} 条新闻...", "info"
            )

            direct_found = 0
            indirect_found = 0

            for news in news_to_analyze:
                analysis = await self._analyze_news_with_llm(news)
                self._update_scores(news, analysis, current_date)
                self.analyzed_news_ids.add(news["id"])

                direct_found += len(analysis.get("direct_benefits", []))
                indirect_found += len(analysis.get("indirect_benefits", []))

            await self.message_manager.send_message(
                f"✅ 发现: {direct_found} 直接, {indirect_found} 间接", "info"
            )

        # 5. 清理过期评分
        self._clean_old_scores(current_date)

        # 6. 获取候选股票
        top_tickers = self._get_top_indirect_tickers(TRADING_CONFIG["top_k"] * 2)

        if not top_tickers:
            return TradingDecision(
                action=TradingAction.HOLD, symbol="N/A",
                reasoning="没有发现间接受益机会", confidence=Decimal("0.0")
            )

        # 7. 筛选要买入的
        held_symbols = [p.symbol for p in portfolio.positions if p.quantity > 0]
        tracked_positions = await self._get_open_positions()
        tracked_symbols = [p.ticker for p in tracked_positions]
        current_count = len(tracked_symbols)

        to_buy = []
        for ticker, score, records in top_tickers:
            if ticker not in held_symbols and ticker not in tracked_symbols:
                if current_count + len(to_buy) < TRADING_CONFIG["max_positions"]:
                    to_buy.append((ticker, score, records))
                    if len(to_buy) >= TRADING_CONFIG["top_k"]:
                        break

        if not to_buy:
            await self.message_manager.send_message("📭 没有新的买入机会", "info")
            return TradingDecision(
                action=TradingAction.HOLD, symbol="N/A",
                reasoning="候选股票都已持有或仓位已满", confidence=Decimal("0.5")
            )

        # 8. 执行买入
        total_equity = float(portfolio.equity)
        position_value = total_equity * TRADING_CONFIG["position_size_pct"]

        orders_placed = []
        for ticker, score, records in to_buy:
            try:
                # 获取价格
                quote = await self.market_data_api.get_latest_price(ticker)
                if not quote:
                    continue
                price = float(quote.get('close', 0) or quote.get('adj_close', 0))
                if price <= 0:
                    continue

                # 计算数量
                quantity = int(position_value / price)
                if quantity <= 0:
                    continue

                # LLM 决定持仓时间
                reason = records[0].reason if records else ""
                chain = records[0].chain if records else ""
                holding_days = await self._decide_holding_days(ticker, reason, chain, score)

                # 提交订单
                order = Order(
                    symbol=ticker, side=OrderSide.BUY,
                    quantity=Decimal(quantity), order_type=OrderType.MARKET,
                    time_in_force=TimeInForce.DAY
                )
                order_id = await self.broker_api.submit_order(order)

                if order_id:
                    # 记录持仓到数据库
                    target_sell_date = datetime.now() + timedelta(days=holding_days)

                    await self._add_position(
                        ticker=ticker,
                        quantity=quantity,
                        buy_price=price,
                        target_sell_date=target_sell_date,
                        holding_days=holding_days,
                        reason=reason,
                        chain=chain,
                        score=score
                    )

                    orders_placed.append((ticker, quantity, price, score, holding_days))

                    await self.message_manager.send_message(
                        f"✅ 买入 {ticker}\n"
                        f"📊 数量: {quantity} 股 @ ${price:.2f}\n"
                        f"⏱️ 持仓计划: {holding_days} 天\n"
                        f"📅 目标卖出: {target_sell_date.strftime('%Y-%m-%d')}\n"
                        f"💡 原因: {reason[:50]}",
                        "success"
                    )

            except Exception as e:
                logger.error(f"买入 {ticker} 失败: {e}")

        # 9. 返回结果
        if orders_placed:
            best = orders_placed[0]
            return TradingDecision(
                action=TradingAction.BUY, symbol=best[0],
                quantity=Decimal(best[1]), price=Decimal(str(best[2])),
                reasoning=f"买入 {len(orders_placed)} 只: {[t[0] for t in orders_placed]}",
                confidence=Decimal(str(min(0.9, best[3] / 20)))
            )

        return TradingDecision(
            action=TradingAction.HOLD, symbol="N/A",
            reasoning="无法执行买入", confidence=Decimal("0.0")
        )
