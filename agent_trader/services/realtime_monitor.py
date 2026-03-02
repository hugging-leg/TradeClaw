"""
实时市场监控服务

使用工厂模式获取实时数据提供商，在检测到重大事件时触发重新平衡：
- 价格剧烈波动（如±5%）
- 突发新闻（由 LLM 判断重要性）

设计原则：
- 工厂模式：可切换不同数据提供商
- LLM 判断：使用独立的 LLM 评估新闻重要性
- 避免过度交易（设置冷却期）
"""

import asyncio
from agent_trader.utils.logging_config import get_logger
from typing import Dict, List, Any, Optional
from decimal import Decimal

from agent_trader.utils.timezone import utc_now
from config import settings

from agent_trader.interfaces.factory import get_realtime_data_api
from agent_trader.interfaces.realtime_data_api import RealtimeTrade, RealtimeNews
from agent_trader.models.trading_models import Portfolio
from agent_trader.utils.llm_utils import create_news_llm_client

logger = get_logger(__name__)


class PriceTracker:
    """价格跟踪器"""

    def __init__(self, symbol: str, initial_price: Decimal):
        self.symbol = symbol
        self.initial_price = initial_price
        self.current_price = initial_price
        self.high_price = initial_price
        self.low_price = initial_price
        self.last_update = utc_now()

    def update(self, price: Decimal):
        self.current_price = price
        self.high_price = max(self.high_price, price)
        self.low_price = min(self.low_price, price)
        self.last_update = utc_now()

    def get_change_percentage(self) -> Decimal:
        if self.initial_price == 0:
            return Decimal('0')
        return ((self.current_price - self.initial_price) / self.initial_price) * 100

    def get_volatility(self) -> Decimal:
        if self.initial_price == 0:
            return Decimal('0')
        return ((self.high_price - self.low_price) / self.initial_price) * 100


class NewsImportanceEvaluator:
    """
    新闻重要性评估器

    使用 LLM 对新闻进行 0-10 重要性打分。
    调用方根据可配置的阈值（news_importance_threshold）决定是否触发 workflow。
    每条新闻只分析一次，不依赖当前持仓。
    """

    PROMPT_TEMPLATE = """You are a financial news analyst. Score the following news article on a scale of 0-10 for investment importance.

Headline: {headline}
Summary: {summary}
Source: {source}
Related symbols: {symbols}

**Scoring guide:**
- **9-10**: Market-moving events (FOMC rate decision, major earnings shock, bankruptcy, M&A of large-cap)
- **7-8**: Significant events (CEO resignation, FDA ruling, major lawsuit, sector-wide policy change)
- **5-6**: Moderate events (analyst upgrade/downgrade on major stock, notable product launch, supply chain disruption)
- **3-4**: Minor events (routine earnings in-line, general market commentary, minor partnership)
- **0-2**: Noise (opinion pieces, rehashed news, clickbait, routine daily summary)

Respond in JSON only:
{{
    "score": <integer 0-10>,
    "reason": "one sentence explaining the score",
    "urgency": "high/medium/low",
    "affected_symbols": ["list of relevant tickers"],
    "action_suggestion": "buy/sell/hold/analyze"
}}"""

    def __init__(self):
        self.llm = None
        self._init_llm()

    def _init_llm(self):
        """初始化新闻过滤 LLM（独立于主 agent，可用便宜模型）"""
        try:
            self.llm = create_news_llm_client()
            logger.info("新闻过滤 LLM 已初始化")
        except Exception as e:
            logger.error(f"初始化新闻过滤 LLM 失败: {e}")

    async def evaluate(self, news: RealtimeNews) -> Dict[str, Any]:
        """
        评估新闻重要性（每条新闻只调用一次）

        Returns:
            {
                "score": int (0-10),
                "is_important": bool (score >= threshold),
                "reason": str,
                "urgency": str,
                "affected_symbols": List[str],
                "action_suggestion": str
            }
        """
        if not self.llm:
            logger.warning("LLM 未初始化，跳过新闻评估")
            return {
                "score": 0,
                "is_important": False,
                "reason": "LLM unavailable",
                "urgency": "low",
                "affected_symbols": [],
                "action_suggestion": "hold"
            }

        try:
            # 处理 symbols（可能是单个或列表）
            symbols = news.symbol if isinstance(news.symbol, str) else ", ".join(news.symbol) if news.symbol else "N/A"

            prompt = self.PROMPT_TEMPLATE.format(
                headline=news.headline,
                summary=news.summary[:500] if news.summary else "No summary",
                source=news.source,
                symbols=symbols
            )

            response = await asyncio.to_thread(
                lambda: self.llm.invoke(prompt).content
            )

            # 解析 JSON 响应
            import json
            response = response.strip()
            if response.startswith("```"):
                response = response.split("\n", 1)[1]
            if response.endswith("```"):
                response = response.rsplit("\n", 1)[0]
            response = response.strip()

            result = json.loads(response)

            # 确保 score 字段存在且合法
            score = int(result.get("score", 0))
            score = max(0, min(10, score))
            result["score"] = score

            # 根据阈值判断 is_important（向后兼容）
            threshold = getattr(settings, "news_importance_threshold", 7)
            result["is_important"] = score >= threshold

            # 确保必要字段存在
            result.setdefault("affected_symbols", [news.symbol] if news.symbol else [])
            result.setdefault("action_suggestion", "analyze")
            result.setdefault("urgency", "high" if score >= 9 else "medium" if score >= 6 else "low")

            logger.info(
                "新闻评估: %s... → score=%d/%d (threshold=%d) %s",
                news.headline[:50], score, 10, threshold,
                "✓ IMPORTANT" if result["is_important"] else "✗ skip",
            )
            return result

        except Exception as e:
            logger.error(f"评估新闻重要性失败: {e}")
            return {
                "score": 0,
                "is_important": False,
                "reason": f"Error: {e}",
                "urgency": "low",
                "affected_symbols": [],
                "action_suggestion": "hold"
            }


class RealtimeMarketMonitor:
    """
    实时市场监控服务

    功能：
    - 监控持仓股票的实时价格变动
    - 检测价格剧烈波动（仅针对持仓）
    - LLM 评估所有新闻重要性（每条只分析一次，不限于持仓）
    - 发现潜在投资机会
    - 触发 workflow 分析
    """

    # 主要市场 ETF（用于获取广泛的市场新闻覆盖，从配置读取）

    def __init__(
        self,
        trading_system=None,
        price_change_threshold: float = None,
        volatility_threshold: float = None
    ):
        self.trading_system = trading_system

        # Get realtime data adapter via factory (returns None if not configured)
        try:
            self.adapter = get_realtime_data_api()
            if self.adapter:
                logger.info("Realtime data provider: %s", self.adapter.get_provider_name())
            else:
                logger.info("No realtime data provider configured; price monitoring disabled")
        except Exception as e:
            logger.error("Failed to create realtime data adapter: %s", e)
            self.adapter = None

        # 新闻重要性评估器
        self.news_evaluator = NewsImportanceEvaluator()

        # 阈值配置
        self.price_change_threshold = Decimal(str(
            price_change_threshold or settings.price_change_threshold
        ))
        self.volatility_threshold = Decimal(str(
            volatility_threshold or settings.volatility_threshold
        ))

        # 状态
        self.price_trackers: Dict[str, PriceTracker] = {}  # 仅持仓股票（价格监控）
        self.is_monitoring = False
        self.monitor_task = None

        # 注册处理器
        if self.adapter:
            self.adapter.register_trade_handler(self._handle_trade)
            self.adapter.register_news_handler(self._handle_news)

        logger.info("实时市场监控服务已初始化")

    async def start(self, portfolio: Optional[Portfolio] = None):
        """启动监控服务"""
        try:
            if self.is_monitoring:
                logger.warning("监控服务已在运行")
                return

            if not self.adapter:
                logger.warning("实时数据适配器不可用，监控服务无法启动")
                return

            logger.info("启动实时市场监控服务")
            self.is_monitoring = True

            if not self.adapter.is_connected:
                await self.adapter.connect()

            # 获取持仓股票
            position_symbols = []
            if portfolio and portfolio.positions:
                position_symbols = [pos.symbol for pos in portfolio.positions if pos.quantity != 0]

            # 1. 交易监控：仅持仓股票
            if position_symbols:
                await self._subscribe_trades(position_symbols, portfolio)

            # 2. 新闻监控：持仓 + 主要 ETF（获取市场广泛覆盖）
            # Finnhub WebSocket 需要指定 symbol，所以订阅持仓 + 主要 ETF
            news_symbols = set(position_symbols) | set(settings.get_market_etfs())
            await self._subscribe_news(list(news_symbols))

            self.monitor_task = asyncio.create_task(self.adapter.start())
            logger.info(f"监控服务启动成功: 价格监控 {len(position_symbols)} 只, 新闻监控 {len(news_symbols)} 只")

        except Exception as e:
            logger.error(f"启动监控服务失败: {e}")
            self.is_monitoring = False

    async def stop(self):
        """停止监控服务"""
        try:
            logger.info("停止实时市场监控服务")
            self.is_monitoring = False

            if self.adapter:
                await self.adapter.stop()

            if self.monitor_task:
                self.monitor_task.cancel()
                try:
                    await self.monitor_task
                except asyncio.CancelledError:
                    pass

            logger.info("监控服务已停止")

        except Exception as e:
            logger.error(f"停止监控服务时出错: {e}")

    async def _subscribe_trades(self, symbols: List[str], portfolio: Optional[Portfolio] = None):
        """订阅交易数据（仅持仓股票，用于价格监控）"""
        try:
            if self.adapter and hasattr(self.adapter, 'subscribe_trades'):
                await self.adapter.subscribe_trades(symbols)
            elif self.adapter:
                await self.adapter.subscribe(symbols)

            if portfolio:
                for position in portfolio.positions:
                    if position.symbol in symbols and position.quantity != 0:
                        current_price = position.market_value / abs(position.quantity) if position.quantity != 0 else Decimal('0')
                        self.price_trackers[position.symbol] = PriceTracker(
                            symbol=position.symbol,
                            initial_price=current_price
                        )

            logger.info(f"已订阅交易: {symbols}")

        except Exception as e:
            logger.error(f"订阅交易失败: {e}")

    async def _subscribe_news(self, symbols: List[str]):
        """订阅新闻"""
        try:
            if self.adapter and hasattr(self.adapter, 'subscribe_news'):
                await self.adapter.subscribe_news(symbols)
                logger.info(f"已订阅新闻: {symbols}")
            else:
                logger.warning("适配器不支持单独订阅新闻")

        except Exception as e:
            logger.error(f"订阅新闻失败: {e}")

    async def unsubscribe_symbols(self, symbols: List[str]):
        """取消订阅（交易和新闻）"""
        try:
            if self.adapter:
                await self.adapter.unsubscribe(symbols)

            for symbol in symbols:
                if symbol in self.price_trackers:
                    del self.price_trackers[symbol]

        except Exception as e:
            logger.error(f"取消订阅失败: {e}")

    async def _handle_trade(self, trade: RealtimeTrade):
        """处理成交数据"""
        try:
            if trade.symbol in self.price_trackers:
                tracker = self.price_trackers[trade.symbol]
                tracker.update(trade.price)
                await self._check_price_triggers(tracker)

        except Exception as e:
            logger.error(f"处理成交数据时出错: {e}")

    async def _handle_news(self, news: RealtimeNews):
        """
        处理新闻数据

        每条新闻只调用一次 LLM 评估（0-10 打分），不限于持仓股票。
        score >= news_importance_threshold 的新闻触发 agent workflow。
        """
        try:
            logger.debug(f"收到新闻: {news.headline[:50]}...")

            # 每条新闻只调用一次 LLM 评估
            evaluation = await self.news_evaluator.evaluate(news)

            if evaluation.get("is_important"):
                await self._publish_event(
                    trigger="breaking_news",
                    context={
                        "news": {
                            "headline": news.headline,
                            "summary": news.summary,
                            "source": news.source,
                            "url": news.url,
                            "symbol": news.symbol,
                            "published_at": news.timestamp.isoformat() if news.timestamp else None
                        },
                        "evaluation": {
                            "score": evaluation.get("score", 0),
                            "is_important": evaluation.get("is_important"),
                            "reason": evaluation.get("reason"),
                            "urgency": evaluation.get("urgency"),
                            "affected_symbols": evaluation.get("affected_symbols", []),
                            "action_suggestion": evaluation.get("action_suggestion")
                        }
                    }
                )
            else:
                logger.debug(
                    "新闻评分不足，跳过: score=%d, reason=%s",
                    evaluation.get("score", 0), evaluation.get("reason"),
                )

        except Exception as e:
            logger.error(f"处理新闻数据时出错: {e}")

    async def _check_price_triggers(self, tracker: PriceTracker):
        """检查价格触发器（仅监控持仓股票）"""
        try:
            change_pct = abs(tracker.get_change_percentage())
            volatility = tracker.get_volatility()

            if change_pct >= self.price_change_threshold:
                await self._publish_event(
                    trigger="price_change",
                    context={
                        "symbol": tracker.symbol,
                        "change_percentage": float(change_pct),
                        "current_price": float(tracker.current_price),
                        "initial_price": float(tracker.initial_price),
                        "direction": "up" if tracker.current_price > tracker.initial_price else "down"
                    }
                )
                return

            if volatility >= self.volatility_threshold:
                await self._publish_event(
                    trigger="high_volatility",
                    context={
                        "symbol": tracker.symbol,
                        "volatility": float(volatility),
                        "high_price": float(tracker.high_price),
                        "low_price": float(tracker.low_price),
                        "current_price": float(tracker.current_price)
                    }
                )

        except Exception as e:
            logger.error(f"检查触发器时出错: {e}")

    async def _publish_event(self, trigger: str, context: Dict[str, Any]):
        """
        触发 workflow 执行

        Monitor 只负责检测和触发，节流由 TradingSystem 处理。

        Args:
            trigger: 触发类型（breaking_news, price_change, high_volatility）
            context: 上下文信息
        """
        try:
            logger.info(f"触发 workflow: {trigger}")

            if self.trading_system and hasattr(self.trading_system, 'trigger_workflow'):
                await self.trading_system.trigger_workflow(
                    trigger=trigger,
                    context=context,
                )
            else:
                logger.warning("trading_system 不可用")

        except Exception as e:
            logger.error(f"触发 workflow 失败: {e}")

    def update_portfolio_positions(self, portfolio: Portfolio):
        """更新监控的组合持仓"""
        try:
            current_symbols = {pos.symbol for pos in portfolio.positions if pos.quantity != 0}
            monitored_symbols = set(self.price_trackers.keys())

            symbols_to_add = current_symbols - monitored_symbols
            symbols_to_remove = monitored_symbols - current_symbols

            if symbols_to_add:
                asyncio.create_task(self._subscribe_trades(list(symbols_to_add), portfolio))

            if symbols_to_remove:
                asyncio.create_task(self.unsubscribe_symbols(list(symbols_to_remove)))

        except Exception as e:
            logger.error(f"更新组合持仓失败: {e}")

    def get_monitored_symbols(self) -> List[str]:
        return list(self.price_trackers.keys())

    def get_price_changes(self) -> Dict[str, Dict[str, Any]]:
        changes = {}
        for symbol, tracker in self.price_trackers.items():
            changes[symbol] = {
                "current_price": float(tracker.current_price),
                "initial_price": float(tracker.initial_price),
                "change_percentage": float(tracker.get_change_percentage()),
                "volatility": float(tracker.get_volatility()),
                "high_price": float(tracker.high_price),
                "low_price": float(tracker.low_price),
                "last_update": tracker.last_update.isoformat()
            }
        return changes

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_monitoring": self.is_monitoring,
            "adapter_status": self.adapter.get_status() if self.adapter else None,
            "monitored_symbols": self.get_monitored_symbols(),
            "price_trackers_count": len(self.price_trackers),
            "thresholds": {
                "price_change": float(self.price_change_threshold),
                "volatility": float(self.volatility_threshold)
            }
        }
