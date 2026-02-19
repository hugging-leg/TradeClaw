"""
Backtest News Adapter — 包装真实 NewsAPI + 防止 Lookahead Bias

核心设计：
- 透传给真实 NewsAPI（如 Tiingo），不做缓存
- 每次调用时把 endDate 设为当前模拟时间 utc_now()，
  由 Tiingo 服务端保证不返回未来新闻（Tiingo 支持精确到秒的 endDate）
- startDate 设为模拟时间前 1 天，确保能拿到足够的新闻上下文
- 不做客户端过滤、不做缓存——简单可靠

用法：
    real_news = get_news_api()
    bt_news = BacktestNewsAdapter(real_news, backtest_start, backtest_end)
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from agent_trader.interfaces.news_api import NewsAPI
from agent_trader.models.trading_models import NewsItem
from agent_trader.utils.logging_config import get_logger
from agent_trader.utils.timezone import utc_now

logger = get_logger(__name__)


class BacktestNewsAdapter(NewsAPI):
    """
    回测专用 News 适配器 — 透传真实 API，用模拟时间作为 endDate 防止 lookahead。

    Args:
        real_news_api: 真实的 NewsAPI 实例（可选，为 None 时退化为空实现）
        backtest_start: 回测起始日期
        backtest_end: 回测结束日期
    """

    def __init__(
        self,
        real_news_api: Optional[NewsAPI] = None,
        backtest_start: Optional[datetime] = None,
        backtest_end: Optional[datetime] = None,
    ):
        self._real_api = real_news_api
        self._start = backtest_start
        self._end = backtest_end
        self._api_calls = 0

    # ------------------------------------------------------------------
    # NewsAPI 实现
    # ------------------------------------------------------------------

    async def get_news(
        self,
        symbols: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        sources: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[NewsItem]:
        if self._real_api is None:
            return []

        now = utc_now()
        # startDate: 模拟时间前 1 天（保证有足够上下文）
        sd = start_date or (now - timedelta(days=1))
        # endDate: 模拟时间（防止 lookahead，Tiingo 支持精确到秒）
        ed = end_date if (end_date and end_date <= now) else now

        self._api_calls += 1
        logger.debug("Backtest get_news: %s ~ %s, symbols=%s, limit=%d",
                      sd.isoformat(), ed.isoformat(), symbols, limit)

        return await self._real_api.get_news(
            symbols=symbols, tags=tags, sources=sources,
            start_date=sd, end_date=ed, limit=limit,
        )

    async def get_symbol_news(self, symbol: str, limit: int = 50) -> List[NewsItem]:
        if self._real_api is None:
            return []

        now = utc_now()
        sd = now - timedelta(days=1)

        self._api_calls += 1
        return await self._real_api.get_news(
            symbols=[symbol],
            start_date=sd, end_date=now,
            limit=limit,
        )

    async def get_sector_news(self, sector: str, limit: int = 50) -> List[NewsItem]:
        if self._real_api is None:
            return []

        now = utc_now()
        sd = now - timedelta(days=1)

        self._api_calls += 1
        return await self._real_api.get_news(
            tags=[sector],
            start_date=sd, end_date=now,
            limit=limit,
        )

    async def get_market_overview_news(self, limit: int = 50) -> List[NewsItem]:
        if self._real_api is None:
            return []

        now = utc_now()
        sd = now - timedelta(days=1)

        self._api_calls += 1
        return await self._real_api.get_news(
            start_date=sd, end_date=now,
            limit=limit,
        )

    async def search_news(self, query: str, limit: int = 50) -> List[NewsItem]:
        if self._real_api is None:
            return []

        self._api_calls += 1
        return await self._real_api.search_news(query=query, limit=limit)

    def get_provider_name(self) -> str:
        real_name = self._real_api.get_provider_name() if self._real_api else "None"
        return f"Backtest ({real_name})"

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": "Backtest News Adapter",
            "type": "backtest",
            "real_provider": self._real_api.get_provider_name() if self._real_api else None,
            "strategy": "passthrough with simulated endDate",
            "api_calls": self._api_calls,
            "backtest_range": (
                f"{self._start.strftime('%Y-%m-%d')} ~ {self._end.strftime('%Y-%m-%d')}"
                if self._start and self._end else "N/A"
            ),
        }
