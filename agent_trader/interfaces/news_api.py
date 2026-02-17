"""
Abstract news API interface for news providers.

This module provides a unified interface for news data across different providers,
using the adapter pattern to decouple the system from specific news APIs.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum

from agent_trader.models.trading_models import NewsItem


class NewsProvider(Enum):
    """Enum for supported news providers."""
    TIINGO = "tiingo"
    ALPHA_VANTAGE = "alpha_vantage"
    NEWS_API = "news_api"
    UNUSUAL_WHALES = "unusual_whales"
    CUSTOM = "custom"


class NewsAPI(ABC):
    """
    Abstract base class for news API implementations.
    
    This interface defines the standard methods that all news providers
    must implement, ensuring consistency across different news sources.
    """
    
    @abstractmethod
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
        pass
    
    @abstractmethod
    async def get_symbol_news(self, symbol: str, limit: int = 50) -> List[NewsItem]:
        """
        Get news for a specific stock symbol.
        
        Args:
            symbol: Stock symbol (e.g., "AAPL")
            limit: Maximum number of articles
            
        Returns:
            List of NewsItem objects
        """
        pass
    
    @abstractmethod
    async def get_sector_news(self, sector: str, limit: int = 50) -> List[NewsItem]:
        """
        Get news for a specific sector.
        
        Args:
            sector: Sector name (e.g., "Technology")
            limit: Maximum number of articles
            
        Returns:
            List of NewsItem objects
        """
        pass
    
    @abstractmethod
    async def get_market_overview_news(self, limit: int = 50) -> List[NewsItem]:
        """
        Get general market overview news.
        
        Args:
            limit: Maximum number of articles
            
        Returns:
            List of NewsItem objects
        """
        pass
    
    @abstractmethod
    async def search_news(self, query: str, limit: int = 50) -> List[NewsItem]:
        """
        Search news articles by keyword.
        
        Args:
            query: Search query
            limit: Maximum number of articles
            
        Returns:
            List of NewsItem objects
        """
        pass
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """
        Get the name of the news provider.
        
        Returns:
            Provider name as string
        """
        pass
    
    @abstractmethod
    def get_provider_info(self) -> Dict[str, Any]:
        """
        Get information about the news provider.
        
        Returns:
            Dictionary with provider information
        """
        pass 