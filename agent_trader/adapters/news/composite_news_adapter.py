"""
组合新闻适配器 - 聚合多个新闻提供商

简单设计：
- 多个来源的新闻合并在一起
- 没有配置 API key 的提供商自动禁用
- 去重、按时间排序

配置示例:
    NEWS_PROVIDERS=tiingo,unusual_whales
"""

import asyncio
from agent_trader.utils.logging_config import get_logger
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone

from agent_trader.interfaces.news_api import NewsAPI
from agent_trader.models.trading_models import NewsItem
from config import settings

logger = get_logger(__name__)


def _check_api_key_configured(provider: str) -> bool:
    """检查提供商的 API key 是否已配置"""
    if provider == "tiingo":
        key = settings.tiingo_api_key
        return bool(key and key != "test_key")
    elif provider == "unusual_whales":
        key = settings.unusual_whales_api_key
        return bool(key)
    elif provider == "finnhub":
        key = settings.finnhub_api_key
        return bool(key)
    elif provider == "akshare":
        # AkShare is free, no API key needed
        return True
    elif provider == "alpaca":
        key = settings.alpaca_api_key
        return bool(key and key != "test_key")
    return False


class CompositeNewsAdapter(NewsAPI):
    """
    组合新闻适配器

    功能：
    - 聚合多个新闻提供商
    - 自动禁用未配置 API key 的提供商
    - 并发获取，去重合并
    - 按时间排序

    示例:
        adapter = CompositeNewsAdapter()
        news = await adapter.get_market_overview_news()
    """

    # 提供商注册表
    PROVIDER_REGISTRY = {
        "tiingo": "agent_trader.adapters.news.tiingo_news_adapter:TiingoNewsAdapter",
        "unusual_whales": "agent_trader.adapters.news.unusual_whales_adapter:UnusualWhalesAdapter",
        "finnhub": "agent_trader.adapters.news.finnhub_news_adapter:FinnhubNewsAdapter",
        "akshare": "agent_trader.adapters.news.akshare_news_adapter:AkShareNewsAdapter",
        "alpaca": "agent_trader.adapters.news.alpaca_news_adapter:AlpacaNewsAdapter",
    }

    def __init__(self, providers: Optional[List[str]] = None):
        """
        初始化组合新闻适配器

        Args:
            providers: 要使用的提供商列表，None 表示使用配置的提供商
        """
        self._adapters: Dict[str, NewsAPI] = {}

        # 获取提供商列表
        if providers is None:
            providers = settings.get_news_providers()

        # 初始化每个提供商（跳过未配置 API key 的）
        for provider_name in providers:
            if provider_name not in self.PROVIDER_REGISTRY:
                logger.warning(f"未知的新闻提供商: {provider_name}")
                continue

            # 检查 API key
            if not _check_api_key_configured(provider_name):
                logger.info(f"新闻提供商 {provider_name} 未配置 API key，已禁用")
                continue

            try:
                adapter = self._create_adapter(provider_name)
                self._adapters[provider_name] = adapter
                logger.info(f"已加载新闻提供商: {provider_name}")
            except Exception as e:
                logger.error(f"加载新闻提供商 {provider_name} 失败: {e}")

        if not self._adapters:
            logger.warning("没有可用的新闻提供商（请检查 API key 配置）")

    def _create_adapter(self, provider_name: str) -> NewsAPI:
        """创建适配器实例"""
        adapter_path = self.PROVIDER_REGISTRY[provider_name]
        module_path, class_name = adapter_path.rsplit(':', 1)
        module = __import__(module_path, fromlist=[class_name])
        adapter_class = getattr(module, class_name)
        return adapter_class()

    async def _gather_from_all(
        self,
        method_name: str,
        *args,
        **kwargs
    ) -> List[NewsItem]:
        """从所有适配器并发获取新闻"""
        if not self._adapters:
            return []

        async def fetch(name: str, adapter: NewsAPI):
            try:
                method = getattr(adapter, method_name)
                return await method(*args, **kwargs)
            except Exception as e:
                logger.error(f"从 {name} 获取新闻失败: {e}")
                return []

        tasks = [
            fetch(name, adapter)
            for name, adapter in self._adapters.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 合并结果
        all_news = []
        for result in results:
            if isinstance(result, list):
                all_news.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"获取新闻异常: {result}")

        # 去重并排序
        return self._deduplicate_and_sort(all_news)

    def _deduplicate_and_sort(self, news_items: List[NewsItem]) -> List[NewsItem]:
        """去重并按时间排序"""
        seen: Set[str] = set()
        unique = []

        for item in news_items:
            # 使用 URL 或标题作为去重键
            key = item.url or item.title
            if key not in seen:
                seen.add(key)
                unique.append(item)

        # 按发布时间降序排序（最新的在前）
        return sorted(
            unique,
            key=lambda x: x.published_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True
        )

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
        """获取新闻"""
        news = await self._gather_from_all(
            'get_news',
            symbols=symbols,
            tags=tags,
            sources=sources,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )
        return news[:limit]

    async def get_symbol_news(self, symbol: str, limit: int = 50) -> List[NewsItem]:
        """获取特定股票的新闻"""
        news = await self._gather_from_all('get_symbol_news', symbol, limit=limit)
        return news[:limit]

    async def get_sector_news(self, sector: str, limit: int = 50) -> List[NewsItem]:
        """获取行业新闻"""
        news = await self._gather_from_all('get_sector_news', sector, limit=limit)
        return news[:limit]

    async def get_market_overview_news(self, limit: int = 50) -> List[NewsItem]:
        """获取市场概览新闻"""
        news = await self._gather_from_all('get_market_overview_news', limit=limit)
        return news[:limit]

    async def search_news(self, query: str, limit: int = 50) -> List[NewsItem]:
        """搜索新闻"""
        news = await self._gather_from_all('search_news', query, limit=limit)
        return news[:limit]

    def get_provider_name(self) -> str:
        return "composite"

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": "Composite News Adapter",
            "type": "aggregator",
            "active_providers": list(self._adapters.keys()),
            "configured": len(self._adapters) > 0
        }
