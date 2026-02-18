"""
Backtest News Adapter — 包装真实 NewsAPI + 防止 Lookahead Bias

核心设计：
- 委托真实 NewsAPI（如 Tiingo）获取历史新闻
- **按时间窗口分批拉取**：每次请求时根据模拟时间确定 7 天窗口，
  只拉取该窗口内的新闻，避免一次性下载全量数据
- 所有返回的新闻严格 published_at ≤ utc_now()（回测模拟时间）
- 缓存按 (method, params, window_start) 组织，同一窗口只调用一次 API
- 回测结束后缓存自动释放（adapter 随 BacktestRunner 生命周期）

用法：
    real_news = get_news_api()  # 实盘 news adapter
    bt_news = BacktestNewsAdapter(real_news, backtest_start, backtest_end)
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from agent_trader.interfaces.news_api import NewsAPI
from agent_trader.models.trading_models import NewsItem
from agent_trader.utils.logging_config import get_logger
from agent_trader.utils.timezone import utc_now, UTC

logger = get_logger(__name__)

# 每个窗口的天数
_WINDOW_DAYS = 7
# 每个窗口拉取的最大新闻数
_WINDOW_LIMIT = 100


class BacktestNewsAdapter(NewsAPI):
    """
    回测专用 News 适配器 — 包装真实 API + 按窗口分批拉取 + 时间过滤

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

        # 窗口缓存: cache_key -> List[NewsItem]
        # cache_key = "method|params...|window=YYYY-MM-DD"
        self._cache: Dict[str, List[NewsItem]] = {}
        self._loading: Dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @staticmethod
    def _window_start(dt: datetime) -> datetime:
        """
        计算时间窗口的起始时间，对齐到周一。

        窗口 = [本周一 00:00, 下周一 00:00)，这样同一周内的所有调用
        都命中同一个缓存 key，避免重复 API 调用。
        """
        # 对齐到本周一 00:00 UTC
        monday = dt - timedelta(days=dt.weekday())
        return monday.replace(hour=0, minute=0, second=0, microsecond=0)

    @staticmethod
    def _make_cache_key(method: str, window: datetime, **kwargs) -> str:
        """生成缓存 key，包含窗口日期"""
        parts = [method]
        for k, v in sorted(kwargs.items()):
            if v is not None:
                parts.append(f"{k}={v}")
        parts.append(f"window={window.strftime('%Y-%m-%d')}")
        return "|".join(parts)

    def _filter_by_simulated_time(self, items: List[NewsItem], limit: int) -> List[NewsItem]:
        """
        过滤新闻：只返回 published_at ≤ 当前模拟时间的新闻。
        这是防止 lookahead bias 的核心。
        """
        now = utc_now()
        filtered = [
            item for item in items
            if item.published_at is not None and item.published_at <= now
        ]
        # 按发布时间降序（最新的在前）
        filtered.sort(key=lambda x: x.published_at, reverse=True)
        return filtered[:limit]

    async def _fetch_window(
        self,
        cache_key: str,
        fetch_fn,
    ) -> List[NewsItem]:
        """
        Lazy fetch + cache：首次查询该窗口时从真实 API 拉取，后续直接返回缓存。
        """
        if self._real_api is None:
            return []

        if cache_key in self._cache:
            return self._cache[cache_key]

        # 并发安全
        if cache_key not in self._loading:
            self._loading[cache_key] = asyncio.Lock()

        async with self._loading[cache_key]:
            if cache_key in self._cache:
                return self._cache[cache_key]

            try:
                items = await fetch_fn()
                self._cache[cache_key] = items
                logger.info(
                    "Cached %d news items (key: %s)",
                    len(items), cache_key[:80],
                )
                return items
            except Exception as e:
                logger.warning(
                    "Failed to fetch news for backtest (key=%s): %s",
                    cache_key[:40], e,
                )
                self._cache[cache_key] = []
                return []

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
        """获取新闻 — 按模拟时间的窗口分批拉取"""
        if self._real_api is None:
            return []

        now = utc_now()
        win_start = self._window_start(now)
        # 窗口结束 = 本周日 23:59（固定，保证同一周 API 参数一致）
        win_end = win_start + timedelta(days=_WINDOW_DAYS)

        symbols_key = ",".join(sorted(symbols)) if symbols else ""
        tags_key = ",".join(sorted(tags)) if tags else ""
        cache_key = self._make_cache_key(
            "get_news", win_start,
            symbols=symbols_key, tags=tags_key,
        )

        items = await self._fetch_window(
            cache_key,
            lambda: self._real_api.get_news(
                symbols=symbols,
                tags=tags,
                sources=sources,
                start_date=win_start,
                end_date=win_end,
                limit=_WINDOW_LIMIT,
            ),
        )

        # _filter_by_simulated_time 会确保只返回 ≤ now 的新闻
        return self._filter_by_simulated_time(items, limit)

    async def get_symbol_news(self, symbol: str, limit: int = 50) -> List[NewsItem]:
        """获取个股新闻"""
        if self._real_api is None:
            return []

        now = utc_now()
        win_start = self._window_start(now)
        win_end = win_start + timedelta(days=_WINDOW_DAYS)

        cache_key = self._make_cache_key(
            "get_symbol_news", win_start, symbol=symbol,
        )

        items = await self._fetch_window(
            cache_key,
            lambda: self._real_api.get_news(
                symbols=[symbol],
                start_date=win_start,
                end_date=win_end,
                limit=_WINDOW_LIMIT,
            ),
        )

        return self._filter_by_simulated_time(items, limit)

    async def get_sector_news(self, sector: str, limit: int = 50) -> List[NewsItem]:
        """获取行业新闻"""
        if self._real_api is None:
            return []

        now = utc_now()
        win_start = self._window_start(now)
        win_end = win_start + timedelta(days=_WINDOW_DAYS)

        cache_key = self._make_cache_key(
            "get_sector_news", win_start, sector=sector,
        )

        items = await self._fetch_window(
            cache_key,
            lambda: self._real_api.get_news(
                tags=[sector],
                start_date=win_start,
                end_date=win_end,
                limit=_WINDOW_LIMIT,
            ),
        )

        return self._filter_by_simulated_time(items, limit)

    async def get_market_overview_news(self, limit: int = 50) -> List[NewsItem]:
        """获取市场概览新闻"""
        if self._real_api is None:
            return []

        now = utc_now()
        win_start = self._window_start(now)
        win_end = win_start + timedelta(days=_WINDOW_DAYS)

        cache_key = self._make_cache_key("get_market_overview_news", win_start)

        items = await self._fetch_window(
            cache_key,
            lambda: self._real_api.get_news(
                start_date=win_start,
                end_date=win_end,
                limit=_WINDOW_LIMIT,
            ),
        )

        return self._filter_by_simulated_time(items, limit)

    async def search_news(self, query: str, limit: int = 50) -> List[NewsItem]:
        """搜索新闻"""
        if self._real_api is None:
            return []

        now = utc_now()
        win_start = self._window_start(now)

        cache_key = self._make_cache_key("search_news", win_start, query=query)

        items = await self._fetch_window(
            cache_key,
            lambda: self._real_api.search_news(query=query, limit=_WINDOW_LIMIT),
        )

        return self._filter_by_simulated_time(items, limit)

    def get_provider_name(self) -> str:
        real_name = self._real_api.get_provider_name() if self._real_api else "None"
        return f"Backtest ({real_name})"

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": "Backtest News Adapter",
            "type": "backtest",
            "real_provider": self._real_api.get_provider_name() if self._real_api else None,
            "window_days": _WINDOW_DAYS,
            "window_limit": _WINDOW_LIMIT,
            "cached_windows": len(self._cache),
            "cached_items": sum(len(v) for v in self._cache.values()),
            "backtest_range": (
                f"{self._start.strftime('%Y-%m-%d')} ~ {self._end.strftime('%Y-%m-%d')}"
                if self._start and self._end else "N/A"
            ),
        }
