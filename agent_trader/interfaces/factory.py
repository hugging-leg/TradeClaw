"""
Factory classes for creating API implementations.

使用装饰器注册模式：
- 每个适配器使用 @register_xxx 装饰器自注册
- Factory 不需要硬编码适配器路径
- 新增适配器只需添加装饰器，无需修改 factory
"""

from agent_trader.utils.logging_config import get_logger
from typing import Dict, Optional, List, Type, Callable
from functools import wraps

from config import settings

logger = get_logger(__name__)


# ========== Broker Factory ==========

class BrokerFactory:
    """Broker API 工厂"""

    _registry: Dict[str, Type] = {}
    _initialized: bool = False

    @classmethod
    def _ensure_initialized(cls):
        """确保内置适配器已注册"""
        if cls._initialized:
            return
        cls._initialized = True
        # 导入内置适配器模块以触发装饰器注册
        try:
            import agent_trader.adapters.brokers.alpaca_adapter
            import agent_trader.adapters.brokers.ibkr_adapter
        except ImportError as e:
            logger.debug(f"部分 Broker 适配器导入失败: {e}")

    @classmethod
    def create_broker_api(cls, provider: Optional[str] = None):
        """创建 Broker API"""
        cls._ensure_initialized()
        provider_name = (provider or settings.broker_provider).lower()

        if provider_name not in cls._registry:
            raise ValueError(f"Unknown broker: {provider_name}. Available: {list(cls._registry.keys())}")

        logger.info(f"Creating {provider_name} broker API")
        return cls._registry[provider_name]()

    @classmethod
    def get_available_providers(cls) -> List[str]:
        cls._ensure_initialized()
        return list(cls._registry.keys())

    @classmethod
    def register(cls, name: str):
        """装饰器：注册 Broker 适配器"""
        def decorator(adapter_class: Type):
            cls._registry[name.lower()] = adapter_class
            logger.debug(f"Registered broker: {name}")
            return adapter_class
        return decorator


def register_broker(name: str):
    """装饰器：注册 Broker 适配器"""
    return BrokerFactory.register(name)


# ========== Market Data Factory ==========

class MarketDataFactory:
    """Market Data API 工厂"""

    _registry: Dict[str, Type] = {}
    _initialized: bool = False

    @classmethod
    def _ensure_initialized(cls):
        if cls._initialized:
            return
        cls._initialized = True
        try:
            import agent_trader.adapters.market_data.tiingo_market_data_adapter
        except ImportError as e:
            logger.debug(f"部分 MarketData 适配器导入失败: {e}")

    @classmethod
    def create_market_data_api(cls, provider: Optional[str] = None):
        """创建 Market Data API"""
        cls._ensure_initialized()
        provider_name = (provider or settings.market_data_provider).lower()

        if provider_name not in cls._registry:
            raise ValueError(f"Unknown market data provider: {provider_name}. Available: {list(cls._registry.keys())}")

        logger.info(f"Creating {provider_name} market data API")
        return cls._registry[provider_name]()

    @classmethod
    def get_available_providers(cls) -> List[str]:
        cls._ensure_initialized()
        return list(cls._registry.keys())

    @classmethod
    def register(cls, name: str):
        """装饰器：注册 MarketData 适配器"""
        def decorator(adapter_class: Type):
            cls._registry[name.lower()] = adapter_class
            logger.debug(f"Registered market data: {name}")
            return adapter_class
        return decorator


def register_market_data(name: str):
    """装饰器：注册 MarketData 适配器"""
    return MarketDataFactory.register(name)


# ========== Message Transport Factory ==========

class MessageTransportFactory:
    """Message Transport 工厂"""

    _registry: Dict[str, Type] = {}
    _initialized: bool = False

    @classmethod
    def _ensure_initialized(cls):
        if cls._initialized:
            return
        cls._initialized = True
        try:
            import agent_trader.adapters.transports.telegram.service
        except ImportError as e:
            logger.debug(f"部分 MessageTransport 适配器导入失败: {e}")

    @classmethod
    def create_message_transport(cls, provider: Optional[str] = None, trading_system=None, **kwargs):
        """创建 Message Transport"""
        cls._ensure_initialized()
        provider_name = (provider or settings.message_provider).lower()

        if provider_name not in cls._registry:
            raise ValueError(f"Unknown message transport: {provider_name}. Available: {list(cls._registry.keys())}")

        logger.info(f"Creating {provider_name} message transport")
        return cls._registry[provider_name](trading_system=trading_system, **kwargs)

    @classmethod
    def get_available_providers(cls) -> List[str]:
        cls._ensure_initialized()
        return list(cls._registry.keys())

    @classmethod
    def register(cls, name: str):
        """装饰器：注册 MessageTransport 适配器"""
        def decorator(adapter_class: Type):
            cls._registry[name.lower()] = adapter_class
            logger.debug(f"Registered message transport: {name}")
            return adapter_class
        return decorator


def register_message_transport(name: str):
    """装饰器：注册 MessageTransport 适配器"""
    return MessageTransportFactory.register(name)


# ========== News Factory ==========

class NewsFactory:
    """News API 工厂"""

    _registry: Dict[str, Type] = {}
    _initialized: bool = False

    @classmethod
    def _ensure_initialized(cls):
        if cls._initialized:
            return
        cls._initialized = True
        try:
            import agent_trader.adapters.news.tiingo_news_adapter
            import agent_trader.adapters.news.unusual_whales_adapter
            import agent_trader.adapters.news.finnhub_news_adapter
            import agent_trader.adapters.news.akshare_news_adapter
        except ImportError as e:
            logger.debug(f"部分 News 适配器导入失败: {e}")

    @classmethod
    def create_news_api(cls, providers: Optional[List[str]] = None):
        """创建 News API"""
        cls._ensure_initialized()

        if providers is None:
            providers = settings.get_news_providers()
        if not providers:
            providers = ["tiingo"]

        # 单个提供商
        if len(providers) == 1:
            provider_name = providers[0].lower()
            if provider_name not in cls._registry:
                raise ValueError(f"Unknown news provider: {provider_name}. Available: {list(cls._registry.keys())}")
            logger.info(f"Creating {provider_name} news API")
            return cls._registry[provider_name]()

        # 多个提供商：使用 CompositeNewsAdapter
        logger.info(f"Creating composite news API: {providers}")
        from agent_trader.adapters.news.composite_news_adapter import CompositeNewsAdapter
        return CompositeNewsAdapter(providers=providers)

    @classmethod
    def get_available_providers(cls) -> List[str]:
        cls._ensure_initialized()
        return list(cls._registry.keys())

    @classmethod
    def register(cls, name: str):
        """装饰器：注册 News 适配器"""
        def decorator(adapter_class: Type):
            cls._registry[name.lower()] = adapter_class
            logger.debug(f"Registered news provider: {name}")
            return adapter_class
        return decorator


def register_news(name: str):
    """装饰器：注册 News 适配器"""
    return NewsFactory.register(name)


# ========== Realtime Data Factory ==========

class RealtimeDataFactory:
    """实时数据 API 工厂"""

    _registry: Dict[str, Type] = {}
    _initialized: bool = False

    @classmethod
    def _ensure_initialized(cls):
        if cls._initialized:
            return
        cls._initialized = True
        try:
            import agent_trader.adapters.realtime.finnhub_realtime
        except ImportError as e:
            logger.debug(f"部分 Realtime 适配器导入失败: {e}")

    @classmethod
    def create_realtime_api(cls, provider: Optional[str] = None):
        """Create realtime data API. Returns None if no provider is configured."""
        cls._ensure_initialized()
        provider_name = (provider or settings.realtime_data_provider).strip().lower()

        if not provider_name:
            logger.info("No realtime data provider configured (realtime_data_provider is empty)")
            return None

        if provider_name not in cls._registry:
            raise ValueError(f"Unknown realtime provider: {provider_name}. Available: {list(cls._registry.keys())}")

        logger.info(f"Creating {provider_name} realtime data API")
        return cls._registry[provider_name]()

    @classmethod
    def get_available_providers(cls) -> List[str]:
        cls._ensure_initialized()
        return list(cls._registry.keys())

    @classmethod
    def register(cls, name: str):
        """装饰器：注册 Realtime 适配器"""
        def decorator(adapter_class: Type):
            cls._registry[name.lower()] = adapter_class
            logger.debug(f"Registered realtime provider: {name}")
            return adapter_class
        return decorator


def register_realtime(name: str):
    """装饰器：注册 Realtime 适配器"""
    return RealtimeDataFactory.register(name)


# ========== 便捷函数 ==========

def get_broker_api(provider: Optional[str] = None):
    """创建 Broker API"""
    return BrokerFactory.create_broker_api(provider)


def get_market_data_api(provider: Optional[str] = None):
    """创建 Market Data API"""
    return MarketDataFactory.create_market_data_api(provider)


def get_message_transport(provider: Optional[str] = None, **kwargs):
    """创建 Message Transport"""
    return MessageTransportFactory.create_message_transport(provider, **kwargs)


def get_news_api(providers: Optional[List[str]] = None):
    """创建 News API"""
    return NewsFactory.create_news_api(providers)


def get_realtime_data_api(provider: Optional[str] = None):
    """创建实时数据 API"""
    return RealtimeDataFactory.create_realtime_api(provider)
