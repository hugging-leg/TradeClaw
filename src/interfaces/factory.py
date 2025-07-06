"""
Factory classes for creating API implementations.

This module provides factory classes that manage the creation of different API adapters,
enabling easy switching between different providers and implementations.
"""

import logging
from typing import Dict, Any, Optional, Type, List
from enum import Enum

from config import settings

logger = logging.getLogger(__name__)


class BrokerProvider(Enum):
    """Enumeration of available broker providers"""
    ALPACA = "alpaca"
    INTERACTIVE_BROKERS = "interactive_brokers"
    TD_AMERITRADE = "td_ameritrade"
    SCHWAB = "schwab"


class MarketDataProvider(Enum):
    """Enumeration of available market data providers"""
    TIINGO = "tiingo"
    ALPHA_VANTAGE = "alpha_vantage"
    YAHOO_FINANCE = "yahoo_finance"
    POLYGON = "polygon"
    FINNHUB = "finnhub"


class MessageTransportProvider(Enum):
    """Enumeration of available message transport providers"""
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    EMAIL = "email"


class BrokerFactory:
    """Factory for creating broker API implementations"""
    
    _registry: Dict[BrokerProvider, str] = {
        BrokerProvider.ALPACA: "src.adapters.brokers.alpaca_adapter:AlpacaBrokerAdapter",
        # Add more providers as they're implemented
    }
    
    @classmethod
    def create_broker_api(cls, provider: Optional[str] = None):
        """
        Create a broker API implementation.
        
        Args:
            provider: Optional provider name, defaults to config setting
            
        Returns:
            BrokerAPI implementation instance
        """
        try:
            # Determine provider
            provider_name = provider or getattr(settings, 'broker_provider', 'alpaca')
            provider_enum = BrokerProvider(provider_name.lower())
            
            # Get implementation class
            module_path = cls._registry.get(provider_enum)
            if not module_path:
                raise ValueError(f"Unsupported broker provider: {provider_name}")
            
            # Import and instantiate
            module_name, class_name = module_path.split(':')
            module = __import__(module_name, fromlist=[class_name])
            adapter_class = getattr(module, class_name)
            
            logger.info(f"Creating {provider_name} broker API")
            return adapter_class()
            
        except Exception as e:
            logger.error(f"Failed to create broker API: {e}")
            raise RuntimeError(f"Broker API creation failed: {e}") from e
    
    @classmethod
    def get_available_providers(cls) -> List[str]:
        """Get list of available broker providers"""
        return [provider.value for provider in BrokerProvider]
    
    @classmethod
    def register_provider(cls, provider: BrokerProvider, implementation_path: str):
        """Register a new broker provider"""
        cls._registry[provider] = implementation_path
        logger.info(f"Registered broker provider: {provider.value}")


class MarketDataFactory:
    """Factory for creating market data API implementations"""
    
    _registry: Dict[MarketDataProvider, str] = {
        MarketDataProvider.TIINGO: "src.adapters.market_data.tiingo_market_data_adapter:TiingoMarketDataAdapter",
        # Add more providers as they're implemented
    }
    
    @classmethod
    def create_market_data_api(cls, provider: Optional[str] = None):
        """
        Create a market data API implementation.
        
        Args:
            provider: Optional provider name, defaults to config setting
            
        Returns:
            MarketDataAPI implementation instance
        """
        try:
            # Determine provider
            provider_name = provider or getattr(settings, 'market_data_provider', 'tiingo')
            provider_enum = MarketDataProvider(provider_name.lower())
            
            # Get implementation class
            module_path = cls._registry.get(provider_enum)
            if not module_path:
                raise ValueError(f"Unsupported market data provider: {provider_name}")
            
            # Import and instantiate
            module_name, class_name = module_path.split(':')
            module = __import__(module_name, fromlist=[class_name])
            adapter_class = getattr(module, class_name)
            
            logger.info(f"Creating {provider_name} market data API")
            return adapter_class()
            
        except Exception as e:
            logger.error(f"Failed to create market data API: {e}")
            raise RuntimeError(f"Market data API creation failed: {e}") from e
    
    @classmethod
    def get_available_providers(cls) -> List[str]:
        """Get list of available market data providers"""
        return [provider.value for provider in MarketDataProvider]
    
    @classmethod
    def register_provider(cls, provider: MarketDataProvider, implementation_path: str):
        """Register a new market data provider"""
        cls._registry[provider] = implementation_path
        logger.info(f"Registered market data provider: {provider.value}")


class MessageTransportFactory:
    """Factory for creating message transport implementations"""
    
    _registry: Dict[MessageTransportProvider, str] = {
        MessageTransportProvider.TELEGRAM: "src.adapters.transports.telegram_service:TelegramService",
        # Add more providers as they're implemented
    }
    
    @classmethod
    def create_message_transport(cls, provider: Optional[str] = None, trading_system=None, **kwargs):
        """
        Create a message transport implementation.
        
        Args:
            provider: Optional provider name, defaults to config setting
            trading_system: TradingSystem instance (if not provided, will create one)
            **kwargs: Additional arguments passed to the transport constructor
            
        Returns:
            MessageTransport implementation instance
        """
        try:
            # Determine provider
            provider_name = provider or getattr(settings, 'message_provider', 'telegram')
            provider_enum = MessageTransportProvider(provider_name.lower())
            
            # Get implementation class
            module_path = cls._registry.get(provider_enum)
            if not module_path:
                raise ValueError(f"Unsupported message transport provider: {provider_name}")
            
            # Import and instantiate
            module_name, class_name = module_path.split(':')
            module = __import__(module_name, fromlist=[class_name])
            transport_class = getattr(module, class_name)
            
            logger.info(f"Creating {provider_name} message transport")
            return transport_class(trading_system=trading_system, **kwargs)
            
        except Exception as e:
            logger.error(f"Failed to create message transport: {e}")
            raise RuntimeError(f"Message transport creation failed: {e}") from e
    
    @classmethod
    def get_available_providers(cls) -> List[str]:
        """Get list of available message transport providers"""
        return [provider.value for provider in MessageTransportProvider]
    
    @classmethod
    def register_provider(cls, provider: MessageTransportProvider, implementation_path: str):
        """Register a new message transport provider"""
        cls._registry[provider] = implementation_path
        logger.info(f"Registered message transport provider: {provider.value}")


class NewsFactory:
    """Factory for creating news API implementations"""
    
    _registry: Dict[str, str] = {
        "tiingo": "src.adapters.news.tiingo_news_adapter:TiingoNewsAdapter",
        # Add more providers as they're implemented
    }
    
    @classmethod
    def create_news_api(cls, provider: Optional[str] = None):
        """
        Create a news API implementation.
        
        Args:
            provider: Optional provider name, defaults to config setting
            
        Returns:
            NewsAPI implementation instance
        """
        try:
            # Determine provider
            provider_name = provider or getattr(settings, 'news_provider', 'tiingo')
            
            # Get implementation class
            module_path = cls._registry.get(provider_name.lower())
            if not module_path:
                raise ValueError(f"Unsupported news provider: {provider_name}")
            
            # Import and instantiate
            module_name, class_name = module_path.split(':')
            module = __import__(module_name, fromlist=[class_name])
            adapter_class = getattr(module, class_name)
            
            logger.info(f"Creating {provider_name} news API")
            return adapter_class()
            
        except Exception as e:
            logger.error(f"Failed to create news API: {e}")
            raise RuntimeError(f"News API creation failed: {e}") from e
    
    @classmethod
    def get_available_providers(cls) -> List[str]:
        """Get list of available news providers"""
        return list(cls._registry.keys())
    
    @classmethod
    def register_provider(cls, provider: str, implementation_path: str):
        """Register a new news provider"""
        cls._registry[provider] = implementation_path
        logger.info(f"Registered news provider: {provider}")


# Convenience functions for easy API creation
def get_broker_api(provider: Optional[str] = None):
    """Convenience function to create a broker API"""
    return BrokerFactory.create_broker_api(provider)


def get_market_data_api(provider: Optional[str] = None):
    """Convenience function to create a market data API"""
    return MarketDataFactory.create_market_data_api(provider)


def get_message_transport(provider: Optional[str] = None, **kwargs):
    """Convenience function to create a message transport"""
    return MessageTransportFactory.create_message_transport(provider, **kwargs)


def get_news_api(provider: Optional[str] = None):
    """Convenience function to create a news API"""
    return NewsFactory.create_news_api(provider) 