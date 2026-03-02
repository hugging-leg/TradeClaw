"""
Alpaca News Adapter

Implements the NewsAPI interface using the Alpaca News REST API.
API Docs: https://docs.alpaca.markets/reference/news-3

Requires ALPACA_API_KEY and ALPACA_SECRET_KEY to be configured.
"""

from agent_trader.utils.logging_config import get_logger
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone

import aiohttp

from config import settings
from agent_trader.interfaces.news_api import NewsAPI
from agent_trader.interfaces.factory import register_news
from agent_trader.models.trading_models import NewsItem
from agent_trader.utils.timezone import utc_now

logger = get_logger(__name__)

# Alpaca News API base URL (data API v1beta1)
ALPACA_NEWS_URL = "https://data.alpaca.markets/v1beta1/news"


@register_news("alpaca")
class AlpacaNewsAdapter(NewsAPI):
    """Alpaca News adapter using the Alpaca Data API."""

    def __init__(self):
        self.api_key = settings.alpaca_api_key
        self.secret_key = settings.alpaca_secret_key

        if not self.api_key or self.api_key == "test_key":
            logger.warning("Alpaca API key not configured, AlpacaNewsAdapter disabled")
            self.is_enabled = False
        else:
            self.is_enabled = True
            logger.info("Alpaca news adapter initialized")

    def _headers(self) -> Dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Accept": "application/json",
        }

    def _parse_article(self, article: Dict[str, Any]) -> NewsItem:
        """Parse an Alpaca news article into a NewsItem."""
        published_str = article.get("created_at") or article.get("updated_at", "")
        published_at = utc_now()
        if published_str:
            try:
                # Alpaca returns ISO 8601 format
                published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                published_at = utc_now()

        return NewsItem(
            title=article.get("headline", ""),
            description=article.get("summary", ""),
            source=article.get("source", "alpaca"),
            url=article.get("url", ""),
            published_at=published_at,
            symbols=article.get("symbols", []),
        )

    async def _fetch_news(
        self,
        symbols: Optional[List[str]] = None,
        limit: int = 20,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> List[NewsItem]:
        """Fetch news from Alpaca News API."""
        if not self.is_enabled:
            return []

        params: Dict[str, Any] = {
            "limit": min(limit, 50),  # Alpaca max is 50 per page
            "sort": "desc",
        }

        if symbols:
            params["symbols"] = ",".join(symbols)

        if start:
            params["start"] = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        if end:
            params["end"] = end.strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    ALPACA_NEWS_URL,
                    headers=self._headers(),
                    params=params,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        articles = data.get("news", [])
                        return [self._parse_article(a) for a in articles[:limit]]
                    else:
                        body = await resp.text()
                        logger.error(
                            "Alpaca News API error: status=%d body=%s",
                            resp.status,
                            body[:200],
                        )
                        return []
        except Exception as e:
            logger.error("Failed to fetch Alpaca news: %s", e)
            return []

    # ---- NewsAPI interface ----

    async def get_news(
        self,
        symbols: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        sources: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 20,
    ) -> List[NewsItem]:
        """Get news articles, optionally filtered by symbols."""
        return await self._fetch_news(
            symbols=symbols,
            limit=limit,
            start=start_date,
            end=end_date,
        )

    async def get_symbol_news(self, symbol: str, limit: int = 20) -> List[NewsItem]:
        """Get news for a specific symbol."""
        return await self._fetch_news(symbols=[symbol], limit=limit)

    async def get_sector_news(self, sector: str, limit: int = 20) -> List[NewsItem]:
        """Get sector news (Alpaca doesn't support sector filter, returns general news)."""
        return await self._fetch_news(limit=limit)

    async def get_market_overview_news(self, limit: int = 20) -> List[NewsItem]:
        """Get general market news."""
        return await self._fetch_news(limit=limit)

    async def search_news(self, query: str, limit: int = 50) -> List[NewsItem]:
        """Search news (Alpaca doesn't support free-text search, returns empty)."""
        return []

    def get_provider_name(self) -> str:
        return "Alpaca"

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": "Alpaca",
            "enabled": self.is_enabled,
            "api_url": ALPACA_NEWS_URL,
            "features": ["company_news", "market_news"],
        }
