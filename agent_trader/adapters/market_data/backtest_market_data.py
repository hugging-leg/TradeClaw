"""
Backtest Market Data Adapter — 历史数据 + 防止 Lookahead Bias

实现 MarketDataAPI 接口，核心规则：
- 使用 lazy cache：首次查询某 symbol 时从真实 MarketDataAPI 拉取全量历史数据
- 所有返回数据严格 ≤ simulated_now（通过 utc_now() 获取模拟时间）
- 不注册到 MarketDataFactory（回测专用，由 BacktestRunner 手动创建）
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from agent_trader.interfaces.market_data_api import MarketDataAPI
from agent_trader.utils.logging_config import get_logger
from agent_trader.utils.timezone import utc_now, UTC

logger = get_logger(__name__)


class BacktestMarketDataAdapter(MarketDataAPI):
    """
    回测专用 MarketData 适配器

    Args:
        real_market_data: 真实的 MarketDataAPI 实例（用于拉取历史数据）
        backtest_start: 回测起始日期
        backtest_end: 回测结束日期
        index_symbols: 市场概览指数 symbol 列表
    """

    def __init__(
        self,
        real_market_data: MarketDataAPI,
        backtest_start: datetime,
        backtest_end: datetime,
        index_symbols: Optional[List[str]] = None,
    ):
        self._real_api = real_market_data
        self._start = backtest_start
        self._end = backtest_end
        self._index_symbols = index_symbols or ["SPY", "QQQ", "IWM", "DIA"]

        # Lazy cache: symbol -> List[Dict] (sorted by date asc)
        self._cache: Dict[str, List[Dict[str, Any]]] = {}
        self._loading: Dict[str, asyncio.Lock] = {}

    async def _ensure_cached(self, symbol: str) -> List[Dict[str, Any]]:
        """
        确保 symbol 的历史数据已缓存。
        首次查询时从真实 API 拉取 [backtest_start - 365d, backtest_end] 范围的数据。
        """
        if symbol in self._cache:
            return self._cache[symbol]

        # 并发安全：同一 symbol 只拉取一次
        if symbol not in self._loading:
            self._loading[symbol] = asyncio.Lock()

        async with self._loading[symbol]:
            if symbol in self._cache:
                return self._cache[symbol]

            # 多拉一年的历史数据，供 Agent 查询历史价格
            fetch_start = self._start - timedelta(days=365)
            fetch_end = self._end + timedelta(days=5)

            logger.info("Fetching historical data for %s: %s ~ %s",
                        symbol, fetch_start.strftime("%Y-%m-%d"), fetch_end.strftime("%Y-%m-%d"))

            try:
                data = await self._real_api.get_eod_prices(symbol, fetch_start, fetch_end)
                if not data:
                    logger.warning("No historical data for %s", symbol)
                    self._cache[symbol] = []
                    return []

                # 确保按日期升序
                data.sort(key=lambda d: d.get("date", ""))
                self._cache[symbol] = data
                logger.info("Cached %d bars for %s", len(data), symbol)
                return data

            except Exception as e:
                logger.error("Failed to fetch historical data for %s: %s", symbol, e)
                self._cache[symbol] = []
                return []

    def _filter_by_date(self, data: List[Dict[str, Any]], end_date: datetime) -> List[Dict[str, Any]]:
        """过滤数据，只返回 date ≤ end_date 的记录（防止 lookahead bias）"""
        cutoff = end_date.strftime("%Y-%m-%d")
        return [d for d in data if str(d.get("date", ""))[:10] <= cutoff]

    # ------------------------------------------------------------------
    # MarketDataAPI 实现
    # ------------------------------------------------------------------

    async def get_market_overview(self) -> Dict[str, Any]:
        """返回当日主要指数数据"""
        now = utc_now()
        result = {}
        for symbol in self._index_symbols:
            data = await self._ensure_cached(symbol)
            filtered = self._filter_by_date(data, now)
            if filtered:
                latest = filtered[-1]
                result[symbol] = {
                    "open": latest.get("open"),
                    "high": latest.get("high"),
                    "low": latest.get("low"),
                    "close": latest.get("close") or latest.get("adjClose"),
                    "volume": latest.get("volume"),
                    "date": latest.get("date"),
                }
        return result

    async def get_eod_prices(
        self, symbol: str, start_date: datetime, end_date: datetime
    ) -> List[Dict[str, Any]]:
        """获取 EOD 价格，end_date 被 clamp 到 simulated_now"""
        now = utc_now()
        effective_end = min(end_date, now)

        data = await self._ensure_cached(symbol)
        filtered = self._filter_by_date(data, effective_end)

        # 再按 start_date 过滤
        start_str = start_date.strftime("%Y-%m-%d")
        return [d for d in filtered if str(d.get("date", ""))[:10] >= start_str]

    async def get_intraday_prices(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        resample_freq: str = "1min",
    ) -> List[Dict[str, Any]]:
        """回测不支持分钟级数据，退化为 EOD 数据"""
        logger.debug("Intraday not available in backtest, falling back to EOD for %s", symbol)
        return await self.get_eod_prices(symbol, start_date, end_date)

    async def get_latest_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取 ≤ simulated_now 的最新价格"""
        now = utc_now()
        data = await self._ensure_cached(symbol)
        filtered = self._filter_by_date(data, now)

        if not filtered:
            return None

        latest = filtered[-1]
        return {
            "symbol": symbol,
            "open": latest.get("open"),
            "high": latest.get("high"),
            "low": latest.get("low"),
            "close": latest.get("close") or latest.get("adjClose"),
            "volume": latest.get("volume"),
            "adj_close": latest.get("adjClose") or latest.get("close"),
            "date": latest.get("date"),
        }

    async def get_multiple_prices(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        results = {}
        for symbol in symbols:
            price = await self.get_latest_price(symbol)
            if price:
                results[symbol] = price
        return results

    async def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """简化实现"""
        return {
            "symbol": symbol,
            "name": symbol,
            "description": f"Backtest data for {symbol}",
        }

    async def search_symbols(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """回测中不支持搜索"""
        return []

    async def get_market_status(self) -> Dict[str, Any]:
        """回测中市场始终开放"""
        return {
            "is_open": True,
            "current_time": utc_now().isoformat(),
            "mode": "backtest",
        }

    def get_provider_name(self) -> str:
        return "Backtest (Historical)"

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": "Backtest Market Data",
            "type": "backtest",
            "real_provider": self._real_api.get_provider_name(),
            "cached_symbols": list(self._cache.keys()),
            "backtest_range": f"{self._start.strftime('%Y-%m-%d')} ~ {self._end.strftime('%Y-%m-%d')}",
        }

    def get_supported_exchanges(self) -> List[str]:
        return self._real_api.get_supported_exchanges()

    def get_supported_asset_types(self) -> List[str]:
        return self._real_api.get_supported_asset_types()

    # ------------------------------------------------------------------
    # 回测专用辅助方法
    # ------------------------------------------------------------------

    async def get_price_on_date(self, symbol: str, date: datetime) -> Optional[Dict[str, Any]]:
        """
        获取指定日期的价格数据（供 PaperBroker 撮合用）。

        返回该日期当天的 OHLCV，如果该日没有数据则返回最近的前一个交易日数据。
        """
        data = await self._ensure_cached(symbol)
        filtered = self._filter_by_date(data, date)
        if not filtered:
            return None
        return filtered[-1]
