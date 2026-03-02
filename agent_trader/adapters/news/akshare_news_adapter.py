"""
AkShare 新闻适配器

使用 AkShare（免费、无需 API key）获取中国 A 股及全球财经新闻。
AkShare 底层抓取东方财富、新浪财经等数据源。

特点：
- 完全免费，无需 API key
- 支持 A 股、港股、美股新闻
- 数据源：东方财富（stock_news_em）、新浪财经等

安装：pip install akshare

注意：
- AkShare 是同步库，需要在 asyncio.to_thread() 中运行
- 部分接口有反爬限制，需要适当控制请求频率
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agent_trader.interfaces.factory import register_news
from agent_trader.interfaces.news_api import NewsAPI
from agent_trader.models.trading_models import NewsItem
from agent_trader.utils.logging_config import get_logger
from agent_trader.utils.timezone import utc_now

logger = get_logger(__name__)


def _try_import_akshare():
    """尝试导入 akshare，未安装时返回 None"""
    try:
        import akshare as ak
        return ak
    except ImportError:
        return None


def _parse_datetime(dt_str: str) -> datetime:
    """解析 AkShare 返回的日期时间字符串"""
    if not dt_str:
        return utc_now()

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y%m%d%H%M%S",
        "%Y%m%d",
    ):
        try:
            dt = datetime.strptime(str(dt_str), fmt)
            return dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return utc_now()


@register_news("akshare")
class AkShareNewsAdapter(NewsAPI):
    """
    AkShare 新闻适配器

    免费获取中国 A 股及全球财经新闻。
    无需 API key，适合作为默认新闻源。
    """

    def __init__(self):
        self._ak = _try_import_akshare()
        if self._ak is None:
            logger.warning(
                "akshare 未安装，AkShareNewsAdapter 已禁用。"
                "请运行: pip install akshare"
            )
            self.is_enabled = False
        else:
            self.is_enabled = True
            logger.info("AkShare 新闻适配器已初始化（免费，无需 API key）")

    # ------------------------------------------------------------------
    # 内部方法（同步，需在 to_thread 中调用）
    # ------------------------------------------------------------------

    def _fetch_stock_news_em(self, symbol: str, limit: int) -> List[NewsItem]:
        """
        获取个股新闻（东方财富）

        akshare 接口：stock_news_em(symbol)
        返回 DataFrame: columns = ['关键词', '新闻标题', '新闻内容', '发布时间',
                                    '文章来源', '新闻链接']
        """
        try:
            df = self._ak.stock_news_em(symbol=symbol)
            if df is None or df.empty:
                return []

            items = []
            for _, row in df.head(limit).iterrows():
                items.append(
                    NewsItem(
                        title=str(row.get("新闻标题", "")),
                        description=str(row.get("新闻内容", ""))[:500],
                        source=str(row.get("文章来源", "东方财富")),
                        url=str(row.get("新闻链接", "")),
                        published_at=_parse_datetime(str(row.get("发布时间", ""))),
                        symbols=[symbol],
                    )
                )
            return items
        except Exception as e:
            logger.error("AkShare stock_news_em(%s) 失败: %s", symbol, e)
            return []

    def _fetch_financial_news(self, limit: int) -> List[NewsItem]:
        """
        获取全球财经快讯（东方财富 7x24）

        akshare 接口：stock_info_global_em()
        返回 DataFrame: columns = ['时间', '内容']
        """
        try:
            df = self._ak.stock_info_global_em()
            if df is None or df.empty:
                return []

            items = []
            for _, row in df.head(limit).iterrows():
                content = str(row.get("内容", ""))
                # 7x24 快讯通常没有标题，用内容前 80 字符作标题
                title = content[:80] + ("..." if len(content) > 80 else "")
                items.append(
                    NewsItem(
                        title=title,
                        description=content,
                        source="东方财富7x24",
                        url="",
                        published_at=_parse_datetime(str(row.get("时间", ""))),
                        symbols=[],
                    )
                )
            return items
        except Exception as e:
            logger.error("AkShare stock_info_global_em 失败: %s", e)
            return []

    def _fetch_cls_telegraph(self, limit: int) -> List[NewsItem]:
        """
        获取财联社电报（cls_telegraph）

        akshare 接口：stock_info_global_cls()
        返回 DataFrame: columns = ['标题', '内容', '发布日期', '发布时间']
        """
        try:
            df = self._ak.stock_info_global_cls()
            if df is None or df.empty:
                return []

            items = []
            for _, row in df.head(limit).iterrows():
                title = str(row.get("标题", ""))
                content = str(row.get("内容", ""))
                if not title:
                    title = content[:80] + ("..." if len(content) > 80 else "")

                pub_date = str(row.get("发布日期", ""))
                pub_time = str(row.get("发布时间", ""))
                dt_str = f"{pub_date} {pub_time}".strip()

                items.append(
                    NewsItem(
                        title=title,
                        description=content,
                        source="财联社",
                        url="",
                        published_at=_parse_datetime(dt_str),
                        symbols=[],
                    )
                )
            return items
        except Exception as e:
            logger.debug("AkShare stock_info_global_cls 失败（可能接口变更）: %s", e)
            return []

    # ------------------------------------------------------------------
    # NewsAPI 接口实现（异步）
    # ------------------------------------------------------------------

    async def get_news(
        self,
        symbols: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        sources: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50,
    ) -> List[NewsItem]:
        """获取新闻"""
        if not self.is_enabled:
            return []

        items: List[NewsItem] = []

        if symbols:
            for symbol in symbols[:5]:  # 限制并发数
                news = await asyncio.to_thread(
                    self._fetch_stock_news_em, symbol, limit // max(len(symbols), 1) + 1
                )
                items.extend(news)
        else:
            items = await asyncio.to_thread(self._fetch_financial_news, limit)

        return sorted(
            items,
            key=lambda x: x.published_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )[:limit]

    async def get_symbol_news(self, symbol: str, limit: int = 50) -> List[NewsItem]:
        """获取特定股票新闻"""
        if not self.is_enabled:
            return []
        return await asyncio.to_thread(self._fetch_stock_news_em, symbol, limit)

    async def get_sector_news(self, sector: str, limit: int = 50) -> List[NewsItem]:
        """获取行业新闻（AkShare 暂不直接支持，返回全球快讯）"""
        if not self.is_enabled:
            return []
        return await asyncio.to_thread(self._fetch_financial_news, limit)

    async def get_market_overview_news(self, limit: int = 50) -> List[NewsItem]:
        """获取市场概览新闻"""
        if not self.is_enabled:
            return []

        # 并发获取多个来源
        results = await asyncio.gather(
            asyncio.to_thread(self._fetch_financial_news, limit),
            asyncio.to_thread(self._fetch_cls_telegraph, limit // 2),
            return_exceptions=True,
        )

        items: List[NewsItem] = []
        for result in results:
            if isinstance(result, list):
                items.extend(result)
            elif isinstance(result, Exception):
                logger.debug("AkShare 部分来源获取失败: %s", result)

        return sorted(
            items,
            key=lambda x: x.published_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )[:limit]

    async def search_news(self, query: str, limit: int = 50) -> List[NewsItem]:
        """搜索新闻（AkShare 不支持关键词搜索，返回全球快讯并在客户端过滤）"""
        if not self.is_enabled:
            return []

        items = await asyncio.to_thread(self._fetch_financial_news, limit * 2)

        # 简单的关键词过滤
        query_lower = query.lower()
        filtered = [
            item
            for item in items
            if query_lower in item.title.lower()
            or query_lower in (item.description or "").lower()
        ]
        return filtered[:limit]

    def get_provider_name(self) -> str:
        return "AkShare"

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": "AkShare",
            "type": "free",
            "enabled": self.is_enabled,
            "features": [
                "stock_news_em",
                "global_financial_news",
                "cls_telegraph",
            ],
            "description": "免费中国 A 股及全球财经新闻（东方财富、财联社）",
            "requires_api_key": False,
        }
