"""
Unusual Whales API 适配器

Unusual Whales 提供：
- 异常期权活动 (Options Flow)
- 暗池交易数据 (Dark Pool)
- 国会议员交易 (Congress Trading)
- 内部人交易 (Insider Trading)
- 新闻和警报

API 文档: https://docs.unusualwhales.com/
"""

import asyncio
from src.utils.logging_config import get_logger
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from decimal import Decimal
from dataclasses import dataclass, field
from enum import Enum

import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
from src.interfaces.news_api import NewsAPI
from src.interfaces.factory import register_news
from src.models.trading_models import NewsItem

logger = get_logger(__name__)


class FlowSentiment(str, Enum):
    """期权流向情绪"""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class OptionsFlow:
    """期权异常活动"""
    symbol: str
    strike: Decimal
    expiry: datetime
    contract_type: str  # call / put
    sentiment: FlowSentiment
    premium: Decimal
    volume: int
    open_interest: int
    timestamp: datetime
    unusual_score: float = 0.0


@dataclass
class DarkPoolTrade:
    """暗池交易"""
    symbol: str
    price: Decimal
    volume: int
    notional: Decimal
    timestamp: datetime
    exchange: str = ""


@dataclass
class CongressTrade:
    """国会议员交易"""
    symbol: str
    politician: str
    party: str
    trade_type: str  # buy / sell
    amount_range: str  # e.g., "$1,001 - $15,000"
    filed_date: datetime
    traded_date: Optional[datetime] = None


@register_news("unusual_whales")
class UnusualWhalesAdapter(NewsAPI):
    """
    Unusual Whales API 适配器

    功能：
    - 获取异常期权活动（大单、sweep 等）
    - 获取暗池交易
    - 获取国会/内部人交易
    - 转换为 NewsItem 格式供 LLM 分析

    使用：
        adapter = UnusualWhalesAdapter()
        flows = await adapter.get_options_flow("AAPL")
        news = await adapter.get_market_overview_news()
    """

    BASE_URL = "https://api.unusualwhales.com"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.unusual_whales_api_key
        self._session: Optional[aiohttp.ClientSession] = None

        if not self.api_key:
            logger.warning("Unusual Whales API key 未配置")

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 HTTP 会话"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
            )
        return self._session

    async def close(self):
        """关闭 HTTP 会话"""
        if self._session and not self._session.closed:
            await self._session.close()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    async def _request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """发送 API 请求"""
        if not self.api_key:
            raise ValueError("Unusual Whales API key 未配置")

        session = await self._get_session()
        url = f"{self.BASE_URL}{endpoint}"

        try:
            async with session.get(url, params=params) as response:
                if response.status == 401:
                    raise ValueError("API key 无效")
                elif response.status == 429:
                    raise RuntimeError("API 速率限制")
                elif response.status != 200:
                    text = await response.text()
                    raise RuntimeError(f"API 错误 {response.status}: {text}")

                return await response.json()

        except aiohttp.ClientError as e:
            logger.error(f"HTTP 请求失败: {e}")
            raise

    # === 期权流向 ===

    async def get_options_flow(
        self,
        symbol: Optional[str] = None,
        limit: int = 50,
        min_premium: Optional[Decimal] = None
    ) -> List[OptionsFlow]:
        """
        获取异常期权活动

        Args:
            symbol: 股票代码（可选，不填获取全市场）
            limit: 返回数量
            min_premium: 最小权利金过滤

        Returns:
            期权流向列表
        """
        try:
            params = {"limit": limit}
            if symbol:
                params["symbol"] = symbol
            if min_premium:
                params["min_premium"] = str(min_premium)

            data = await self._request("/api/stock/flow", params)

            flows = []
            for item in data.get("data", []):
                try:
                    flows.append(OptionsFlow(
                        symbol=item.get("ticker", ""),
                        strike=Decimal(str(item.get("strike", 0))),
                        expiry=datetime.fromisoformat(item.get("expiry", "")),
                        contract_type=item.get("type", "call"),
                        sentiment=FlowSentiment(item.get("sentiment", "neutral")),
                        premium=Decimal(str(item.get("premium", 0))),
                        volume=int(item.get("volume", 0)),
                        open_interest=int(item.get("open_interest", 0)),
                        timestamp=datetime.fromisoformat(item.get("executed_at", "")),
                        unusual_score=float(item.get("unusual_score", 0))
                    ))
                except Exception as e:
                    logger.debug(f"解析期权流向失败: {e}")

            return flows

        except Exception as e:
            logger.error(f"获取期权流向失败: {e}")
            return []

    # === 暗池数据 ===

    async def get_dark_pool(
        self,
        symbol: Optional[str] = None,
        limit: int = 50
    ) -> List[DarkPoolTrade]:
        """
        获取暗池交易数据

        Args:
            symbol: 股票代码（可选）
            limit: 返回数量

        Returns:
            暗池交易列表
        """
        try:
            params = {"limit": limit}
            if symbol:
                params["symbol"] = symbol

            data = await self._request("/api/stock/dark-pool", params)

            trades = []
            for item in data.get("data", []):
                try:
                    trades.append(DarkPoolTrade(
                        symbol=item.get("ticker", ""),
                        price=Decimal(str(item.get("price", 0))),
                        volume=int(item.get("volume", 0)),
                        notional=Decimal(str(item.get("notional", 0))),
                        timestamp=datetime.fromisoformat(item.get("executed_at", "")),
                        exchange=item.get("exchange", "")
                    ))
                except Exception as e:
                    logger.debug(f"解析暗池交易失败: {e}")

            return trades

        except Exception as e:
            logger.error(f"获取暗池数据失败: {e}")
            return []

    # === 国会交易 ===

    async def get_congress_trades(
        self,
        limit: int = 50
    ) -> List[CongressTrade]:
        """
        获取国会议员交易

        Returns:
            国会交易列表
        """
        try:
            data = await self._request("/api/congress/trades", {"limit": limit})

            trades = []
            for item in data.get("data", []):
                try:
                    trades.append(CongressTrade(
                        symbol=item.get("ticker", ""),
                        politician=item.get("politician", ""),
                        party=item.get("party", ""),
                        trade_type=item.get("type", ""),
                        amount_range=item.get("amount", ""),
                        filed_date=datetime.fromisoformat(item.get("filed_date", "")),
                        traded_date=datetime.fromisoformat(item["traded_date"]) if item.get("traded_date") else None
                    ))
                except Exception as e:
                    logger.debug(f"解析国会交易失败: {e}")

            return trades

        except Exception as e:
            logger.error(f"获取国会交易失败: {e}")
            return []

    # === NewsAPI 接口实现 ===

    async def get_news(
        self,
        symbols: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        sources: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[NewsItem]:
        """获取新闻（转换期权流向为新闻格式）"""
        all_news = []

        # 获取期权流向并转换为新闻
        if symbols:
            for symbol in symbols[:5]:  # 限制并发
                flows = await self.get_options_flow(symbol, limit=limit // len(symbols))
                all_news.extend(self._flows_to_news(flows))
        else:
            flows = await self.get_options_flow(limit=limit)
            all_news.extend(self._flows_to_news(flows))

        return all_news[:limit]

    async def get_symbol_news(self, symbol: str, limit: int = 50) -> List[NewsItem]:
        """获取特定股票的异常活动"""
        flows = await self.get_options_flow(symbol, limit=limit)
        dark_pool = await self.get_dark_pool(symbol, limit=limit // 2)

        news = self._flows_to_news(flows)
        news.extend(self._dark_pool_to_news(dark_pool))

        return news[:limit]

    async def get_sector_news(self, sector: str, limit: int = 50) -> List[NewsItem]:
        """获取行业新闻（暂不支持）"""
        return []

    async def get_market_overview_news(self, limit: int = 50) -> List[NewsItem]:
        """获取市场概览（期权流向 + 暗池 + 国会交易）"""
        all_news = []

        # 并发获取
        flows, dark_pool, congress = await asyncio.gather(
            self.get_options_flow(limit=limit // 3),
            self.get_dark_pool(limit=limit // 3),
            self.get_congress_trades(limit=limit // 3),
            return_exceptions=True
        )

        if isinstance(flows, list):
            all_news.extend(self._flows_to_news(flows))
        if isinstance(dark_pool, list):
            all_news.extend(self._dark_pool_to_news(dark_pool))
        if isinstance(congress, list):
            all_news.extend(self._congress_to_news(congress))

        # 按时间排序
        all_news.sort(key=lambda x: x.published_at, reverse=True)

        return all_news[:limit]

    async def search_news(self, query: str, limit: int = 50) -> List[NewsItem]:
        """搜索（按股票代码搜索）"""
        return await self.get_symbol_news(query.upper(), limit=limit)

    def get_provider_name(self) -> str:
        return "unusual_whales"

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": "Unusual Whales",
            "type": "alternative_data",
            "features": [
                "options_flow",
                "dark_pool",
                "congress_trades",
                "insider_trading"
            ],
            "api_configured": bool(self.api_key)
        }

    # === 转换辅助方法 ===

    def _flows_to_news(self, flows: List[OptionsFlow]) -> List[NewsItem]:
        """将期权流向转换为新闻格式"""
        news = []
        for flow in flows:
            sentiment_emoji = "🟢" if flow.sentiment == FlowSentiment.BULLISH else "🔴" if flow.sentiment == FlowSentiment.BEARISH else "⚪"
            title = (
                f"{sentiment_emoji} {flow.symbol} 异常期权活动: "
                f"{flow.contract_type.upper()} ${flow.strike} "
                f"(${flow.premium:,.0f} 权利金)"
            )
            description = (
                f"到期日: {flow.expiry.strftime('%Y-%m-%d')}, "
                f"成交量: {flow.volume:,}, OI: {flow.open_interest:,}, "
                f"异常分数: {flow.unusual_score:.1f}"
            )
            news.append(NewsItem(
                title=title,
                description=description,
                source="Unusual Whales",
                published_at=flow.timestamp,
                url="https://unusualwhales.com/flow",
                symbols=[flow.symbol]
            ))
        return news

    def _dark_pool_to_news(self, trades: List[DarkPoolTrade]) -> List[NewsItem]:
        """将暗池交易转换为新闻格式"""
        news = []
        for trade in trades:
            title = (
                f"🏦 {trade.symbol} 暗池交易: "
                f"{trade.volume:,} 股 @ ${trade.price:.2f} "
                f"(${trade.notional:,.0f})"
            )
            news.append(NewsItem(
                title=title,
                description=f"交易所: {trade.exchange}",
                source="Unusual Whales - Dark Pool",
                published_at=trade.timestamp,
                url="https://unusualwhales.com/dark-pool",
                symbols=[trade.symbol]
            ))
        return news

    def _congress_to_news(self, trades: List[CongressTrade]) -> List[NewsItem]:
        """将国会交易转换为新闻格式"""
        news = []
        for trade in trades:
            emoji = "🟢" if trade.trade_type.lower() == "buy" else "🔴"
            title = (
                f"🏛️ 国会交易: {trade.politician} ({trade.party}) "
                f"{emoji} {trade.trade_type.upper()} {trade.symbol}"
            )
            description = f"金额范围: {trade.amount_range}"
            news.append(NewsItem(
                title=title,
                description=description,
                source="Unusual Whales - Congress",
                published_at=trade.filed_date,
                url="https://unusualwhales.com/congress",
                symbols=[trade.symbol]
            ))
        return news

