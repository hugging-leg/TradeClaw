"""
Tiingo News API Adapter.

This module provides a Tiingo-specific implementation of the NewsAPI interface,
adapting the Tiingo API for news data to the standardized news interface.
"""

import requests
from src.utils.logging_config import get_logger
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from src.interfaces.news_api import NewsAPI, NewsProvider
from src.interfaces.factory import register_news
from src.models.trading_models import NewsItem
from src.utils.timezone import utc_now
from config import settings


logger = get_logger(__name__)


@register_news("tiingo")
class TiingoNewsAdapter(NewsAPI):
    """
    Tiingo News API adapter implementing the NewsAPI interface.
    
    This adapter provides access to Tiingo's news data through the
    standardized NewsAPI interface, allowing seamless integration
    with different news providers.
    """
    
    def __init__(self):
        """Initialize the Tiingo News adapter."""
        self.base_url = "https://api.tiingo.com"
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Token {settings.tiingo_api_key}'
        }
        
        # Validate configuration
        if not settings.tiingo_api_key:
            logger.warning("Tiingo API key not configured")
    
    async def get_news(self, 
                      symbols: Optional[List[str]] = None,
                      tags: Optional[List[str]] = None,
                      sources: Optional[List[str]] = None,
                      start_date: Optional[datetime] = None,
                      end_date: Optional[datetime] = None,
                      limit: int = 100) -> List[NewsItem]:
        """
        Get news articles based on various filters.
        
        Args:
            symbols: Optional list of stock symbols to filter
            tags: Optional list of tags/categories to filter
            sources: Optional list of news sources to filter
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering
            limit: Maximum number of articles to return
            
        Returns:
            List of NewsItem objects
        """
        try:
            # Default to last 24 hours if no date range provided
            if not start_date:
                start_date = utc_now() - timedelta(days=1)
            if not end_date:
                end_date = utc_now()
            
            params = {
                'startDate': start_date.strftime('%Y-%m-%d'),
                'endDate': end_date.strftime('%Y-%m-%d'),
                'limit': limit,
                'sortBy': 'publishedDate'
            }
            
            # Add filters
            if symbols:
                params['tickers'] = ','.join(symbols)
            if tags:
                params['tags'] = ','.join(tags)
            if sources:
                params['sources'] = ','.join(sources)
            
            response = requests.get(
                f"{self.base_url}/tiingo/news",
                headers=self.headers,
                params=params
            )
            response.raise_for_status()
            
            news_data = response.json()
            news_items = []
            
            for item in news_data:
                news_item = self._parse_news_item(item)
                if news_item:
                    news_items.append(news_item)
            
            logger.info(f"Retrieved {len(news_items)} news articles from Tiingo")
            return news_items
            
        except Exception as e:
            logger.error(f"Failed to get news from Tiingo: {e}")
            return []  # Return empty list instead of raising exception
    
    async def get_symbol_news(self, symbol: str, limit: int = 50) -> List[NewsItem]:
        """
        Get news for a specific stock symbol.
        
        Args:
            symbol: Stock symbol (e.g., "AAPL")
            limit: Maximum number of articles
            
        Returns:
            List of NewsItem objects
        """
        try:
            return await self.get_news(symbols=[symbol], limit=limit)
        except Exception as e:
            logger.error(f"Failed to get news for symbol {symbol}: {e}")
            return []
    
    async def get_sector_news(self, sector: str, limit: int = 50) -> List[NewsItem]:
        """
        Get news for a specific sector.
        
        Args:
            sector: Sector name (e.g., "Technology")
            limit: Maximum number of articles
            
        Returns:
            List of NewsItem objects
        """
        try:
            return await self.get_news(tags=[sector], limit=limit)
        except Exception as e:
            logger.error(f"Failed to get sector news for {sector}: {e}")
            return []
    
    async def get_market_overview_news(self, limit: int = 50) -> List[NewsItem]:
        """
        Get general market overview news.
        
        Args:
            limit: Maximum number of articles
            
        Returns:
            List of NewsItem objects
        """
        try:
            # Get general market news without specific filters
            return await self.get_news(limit=limit)
        except Exception as e:
            logger.error(f"Failed to get market overview news: {e}")
            return []
    
    async def search_news(self, query: str, limit: int = 50) -> List[NewsItem]:
        """
        Search news articles by keyword.
        
        Args:
            query: Search query
            limit: Maximum number of articles
            
        Returns:
            List of NewsItem objects
        """
        try:
            params = {
                'q': query,
                'limit': limit,
                'sortBy': 'publishedDate',
                'startDate': (utc_now() - timedelta(days=7)).strftime('%Y-%m-%d'),
                'endDate': utc_now().strftime('%Y-%m-%d')
            }
            
            response = requests.get(
                f"{self.base_url}/tiingo/news",
                headers=self.headers,
                params=params
            )
            response.raise_for_status()
            
            news_data = response.json()
            news_items = []
            
            for item in news_data:
                # Filter by keyword match in title or description
                if (query.lower() in item.get('title', '').lower() or 
                    query.lower() in item.get('description', '').lower()):
                    news_item = self._parse_news_item(item)
                    if news_item:
                        news_items.append(news_item)
            
            logger.info(f"Found {len(news_items)} news articles for query '{query}'")
            return news_items
            
        except Exception as e:
            logger.error(f"Failed to search news for query '{query}': {e}")
            return []
    
    def get_provider_name(self) -> str:
        """
        Get the name of the news provider.
        
        Returns:
            Provider name as string
        """
        return "Tiingo"
    
    def get_provider_info(self) -> Dict[str, Any]:
        """
        Get information about the news provider.
        
        Returns:
            Dictionary with provider information
        """
        return {
            'name': 'Tiingo',
            'provider': NewsProvider.TIINGO.value,
            'base_url': self.base_url,
            'configured': bool(settings.tiingo_api_key),
            'features': [
                'Symbol-based filtering',
                'Tag-based filtering',
                'Source-based filtering',
                'Date range filtering',
                'Keyword search',
                'Historical news data'
            ],
            'rate_limits': {
                'requests_per_hour': 1000,  # Tiingo's typical rate limit
                'requests_per_day': 50000
            },
            'supported_markets': ['US', 'Global'],
            'data_sources': [
                'Reuters',
                'Bloomberg',
                'MarketWatch',
                'Yahoo Finance',
                'Various Financial News Outlets'
            ]
        }
    
    def _parse_news_item(self, item: Dict[str, Any]) -> Optional[NewsItem]:
        """
        Parse a news item from Tiingo API response.
        
        Args:
            item: Raw news item from Tiingo API
            
        Returns:
            NewsItem object or None if parsing fails
        """
        try:
            # Ensure description is never None
            description = item.get('description') or item.get('summary') or ""
            if not description:
                description = f"News article from {item.get('source', 'Unknown source')}"
            
            # Parse published date
            published_date = item.get('publishedDate', '')
            if published_date:
                try:
                    published_at = datetime.fromisoformat(published_date.replace('Z', '+00:00'))
                except ValueError:
                    published_at = utc_now()
            else:
                published_at = utc_now()
            
            news_item = NewsItem(
                title=item.get('title', 'No Title'),
                description=description,
                url=item.get('url', ''),
                source=item.get('source', 'Unknown'),
                published_at=published_at,
                symbols=item.get('tickers', [])
            )
            
            return news_item
            
        except Exception as e:
            logger.error(f"Failed to parse news item: {e}")
            return None
    
    async def get_crypto_news(self, limit: int = 50) -> List[NewsItem]:
        """
        Get cryptocurrency news.
        
        Args:
            limit: Maximum number of articles
            
        Returns:
            List of NewsItem objects
        """
        try:
            return await self.get_news(tags=['Cryptocurrency'], limit=limit)
        except Exception as e:
            logger.error(f"Failed to get crypto news: {e}")
            return [] 