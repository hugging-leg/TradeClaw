"""
Abstract news API interface and factory for news providers.

This module provides a unified interface for news data across different providers,
using the adapter pattern to decouple the system from specific news APIs.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timedelta
from enum import Enum
import logging

from src.models.trading_models import NewsItem
from config import settings


logger = logging.getLogger(__name__)


class NewsProvider(Enum):
    """Enum for supported news providers."""
    TIINGO = "tiingo"
    ALPHA_VANTAGE = "alpha_vantage"
    NEWS_API = "news_api"
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


class NewsFactory:
    """
    Factory class for creating news API instances.
    
    This factory creates different news providers based on configuration
    and provides a unified interface for news data access.
    """
    
    _provider_registry: Dict[NewsProvider, type] = {}
    
    @classmethod
    def register_provider(cls, provider: NewsProvider, provider_class: type):
        """
        Register a new news provider.
        
        Args:
            provider: Provider enum value
            provider_class: Class implementing NewsAPI interface
        """
        cls._provider_registry[provider] = provider_class
        logger.info(f"Registered news provider: {provider.value}")
    
    @classmethod
    def create_news_api(cls, provider: Optional[Union[str, NewsProvider]] = None) -> NewsAPI:
        """
        Create a news API instance based on provider.
        
        Args:
            provider: Optional provider override. If not provided, 
                     uses NEWS_PROVIDER from settings
            
        Returns:
            NewsAPI instance
            
        Raises:
            ValueError: If provider is not supported
            RuntimeError: If provider creation fails
        """
        try:
            # Determine provider
            if provider is None:
                provider_name = getattr(settings, 'news_provider', 'tiingo')
            elif isinstance(provider, str):
                provider_name = provider
            else:
                provider_name = provider.value
            
            # Get provider enum
            try:
                provider_enum = NewsProvider(provider_name.lower())
            except ValueError:
                raise ValueError(f"Unsupported news provider: {provider_name}")
            
            # Get provider class
            if provider_enum not in cls._provider_registry:
                raise ValueError(f"News provider not registered: {provider_enum.value}")
            
            provider_class = cls._provider_registry[provider_enum]
            
            # Create and return provider instance
            news_api = provider_class()
            logger.info(f"Created news API: {provider_enum.value}")
            return news_api
            
        except Exception as e:
            logger.error(f"Failed to create news API: {e}")
            raise RuntimeError(f"News API creation failed: {e}")
    
    @classmethod
    def get_available_providers(cls) -> List[str]:
        """
        Get list of available news providers.
        
        Returns:
            List of provider names
        """
        return [provider.value for provider in cls._provider_registry.keys()]
    
    @classmethod
    def validate_provider_config(cls, provider: Union[str, NewsProvider]) -> bool:
        """
        Validate if a provider is properly configured.
        
        Args:
            provider: Provider to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            if isinstance(provider, str):
                provider_enum = NewsProvider(provider.lower())
            else:
                provider_enum = provider
            
            if provider_enum not in cls._provider_registry:
                return False
            
            # Create instance to test configuration
            provider_class = cls._provider_registry[provider_enum]
            test_instance = provider_class()
            
            # Basic configuration validation
            info = test_instance.get_provider_info()
            return info.get('configured', False)
            
        except Exception as e:
            logger.error(f"Provider validation failed: {e}")
            return False


def get_news_api(provider: Optional[Union[str, NewsProvider]] = None) -> NewsAPI:
    """
    Convenience function to get a news API instance.
    
    Args:
        provider: Optional provider override
        
    Returns:
        NewsAPI instance
    """
    return NewsFactory.create_news_api(provider) 