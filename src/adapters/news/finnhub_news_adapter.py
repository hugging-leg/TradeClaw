"""
Finnhub 新闻适配器

实现 NewsAPI 接口，提供 Finnhub 新闻服务。

API 文档: https://finnhub.io/docs/api/company-news
"""

from src.utils.logging_config import get_logger
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

import aiohttp

from config import settings
from src.interfaces.news_api import NewsAPI
from src.interfaces.factory import register_news
from src.models.trading_models import NewsItem
from src.utils.timezone import utc_now

logger = get_logger(__name__)


@register_news("finnhub")
class FinnhubNewsAdapter(NewsAPI):
    """Finnhub 新闻适配器"""

    API_URL = "https://finnhub.io/api/v1"

    def __init__(self):
        self.api_key = settings.finnhub_api_key

        if not self.api_key:
            logger.warning("Finnhub API key 未配置，FinnhubNewsAdapter 已禁用")
            self.is_enabled = False
        else:
            self.is_enabled = True
            logger.info("Finnhub 新闻适配器已初始化")

    async def get_news(
        self,
        symbols: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        sources: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 20
    ) -> List[NewsItem]:
        """获取新闻"""
        if not self.is_enabled:
            return []

        try:
            if symbols:
                all_news = []
                for symbol in symbols[:5]:
                    news = await self._get_company_news(symbol, limit // max(len(symbols), 1) + 1)
                    all_news.extend(news)
                return sorted(all_news, key=lambda x: x.published_at, reverse=True)[:limit]
            else:
                return await self._get_market_news("general", limit)

        except Exception as e:
            logger.error(f"获取 Finnhub 新闻失败: {e}")
            return []

    async def _get_company_news(self, symbol: str, limit: int) -> List[NewsItem]:
        """获取公司新闻"""
        from_date = (utc_now() - timedelta(days=7)).strftime("%Y-%m-%d")
        to_date = utc_now().strftime("%Y-%m-%d")

        url = f"{self.API_URL}/company-news"
        params = {
            "symbol": symbol,
            "from": from_date,
            "to": to_date,
            "token": self.api_key
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return [
                            NewsItem(
                                title=item["headline"],
                                description=item.get("summary", ""),
                                source=item["source"],
                                url=item["url"],
                                published_at=datetime.fromtimestamp(item["datetime"]),
                                symbols=[symbol]
                            )
                            for item in data[:limit]
                        ]
                    else:
                        logger.error(f"Finnhub API 错误: {resp.status}")
                        return []
        except Exception as e:
            logger.error(f"获取公司新闻失败: {e}")
            return []

    async def _get_market_news(self, category: str, limit: int) -> List[NewsItem]:
        """获取市场新闻"""
        url = f"{self.API_URL}/news"
        params = {
            "category": category,
            "token": self.api_key
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return [
                            NewsItem(
                                title=item["headline"],
                                description=item.get("summary", ""),
                                source=item["source"],
                                url=item["url"],
                                published_at=datetime.fromtimestamp(item["datetime"]),
                                symbols=[]
                            )
                            for item in data[:limit]
                        ]
                    else:
                        logger.error(f"Finnhub API 错误: {resp.status}")
                        return []
        except Exception as e:
            logger.error(f"获取市场新闻失败: {e}")
            return []

    async def get_symbol_news(self, symbol: str, limit: int = 10) -> List[NewsItem]:
        """获取特定股票新闻"""
        if not self.is_enabled:
            return []
        return await self._get_company_news(symbol, limit)

    async def get_market_overview_news(self, limit: int = 20) -> List[NewsItem]:
        """获取市场概览新闻"""
        if not self.is_enabled:
            return []
        return await self._get_market_news("general", limit)

    async def get_sector_news(self, sector: str, limit: int = 10) -> List[NewsItem]:
        """获取行业新闻"""
        if not self.is_enabled:
            return []
        return await self._get_market_news("general", limit)

    async def search_news(self, query: str, limit: int = 50) -> List[NewsItem]:
        """搜索新闻（Finnhub 不支持，返回空）"""
        return []

    def get_provider_name(self) -> str:
        return "Finnhub"

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": "Finnhub",
            "enabled": self.is_enabled,
            "api_url": self.API_URL,
            "features": ["company_news", "market_news", "sentiment", "insider_trades"]
        }

    async def get_sentiment(self, symbol: str) -> Dict[str, Any]:
        """获取新闻情绪"""
        if not self.is_enabled:
            return {}

        url = f"{self.API_URL}/news-sentiment"
        params = {"symbol": symbol, "token": self.api_key}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    return {}
        except Exception as e:
            logger.error(f"获取情绪数据失败: {e}")
            return {}

    async def get_insider_trades(self, symbol: str) -> Dict[str, Any]:
        """获取内部交易"""
        if not self.is_enabled:
            return {}

        url = f"{self.API_URL}/stock/insider-transactions"
        params = {"symbol": symbol, "token": self.api_key}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    return {}
        except Exception as e:
            logger.error(f"获取内部交易数据失败: {e}")
            return {}
