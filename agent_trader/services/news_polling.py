"""
新闻轮询服务

当 WebSocket 实时新闻流不可用时（如未购买 API key），
通过定期轮询 REST 新闻 API 获取最新新闻，
经 LLM 评估后触发 workflow 分析。

设计：
- 复用 CompositeNewsAdapter（REST 轮询）
- 复用 NewsImportanceEvaluator（LLM 评估）
- 通过 TradingSystem.trigger_workflow() 触发分析
- 使用 seen-set 去重，避免重复评估
- 作为 APScheduler interval job 运行
"""

import asyncio
import hashlib
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from agent_trader.interfaces.factory import get_news_api
from agent_trader.models.trading_models import NewsItem
from agent_trader.services.realtime_monitor import NewsImportanceEvaluator
from agent_trader.interfaces.realtime_data_api import RealtimeNews
from agent_trader.utils.logging_config import get_logger
from agent_trader.utils.timezone import utc_now

logger = get_logger(__name__)

# 最多保留已处理新闻 hash（防止内存无限增长）
_MAX_SEEN = 5000


def _news_hash(item: NewsItem) -> str:
    """生成新闻去重 hash（基于 URL 或标题）"""
    key = item.url or item.title
    return hashlib.md5(key.encode("utf-8", errors="replace")).hexdigest()


class NewsPollingService:
    """
    新闻轮询服务

    - 定期从 REST 新闻 API 获取新闻
    - LLM 评估重要性
    - 重要新闻触发 workflow 分析
    """

    def __init__(
        self,
        trading_system=None,
        poll_interval_minutes: int = 5,
        max_news_per_poll: int = 20,
    ):
        self.trading_system = trading_system
        self.poll_interval_minutes = poll_interval_minutes
        self.max_news_per_poll = max_news_per_poll

        # 去重集合
        self._seen_hashes: Set[str] = set()
        self._seen_queue: deque[str] = deque(maxlen=_MAX_SEEN)

        # 新闻适配器（延迟初始化，避免循环导入）
        self._news_api = None

        # LLM 评估器
        self._evaluator: Optional[NewsImportanceEvaluator] = None

        # 统计
        self.stats = {
            "total_polls": 0,
            "total_news_fetched": 0,
            "total_new_news": 0,
            "total_important": 0,
            "total_triggers": 0,
            "last_poll": None,
            "last_error": None,
        }

        logger.info(
            "NewsPollingService initialized (interval=%dm, max_per_poll=%d)",
            poll_interval_minutes,
            max_news_per_poll,
        )

    def _ensure_initialized(self):
        """延迟初始化组件"""
        if self._news_api is None:
            try:
                self._news_api = get_news_api()
                logger.info("News API initialized: %s", self._news_api.get_provider_name())
            except Exception as e:
                logger.error("Failed to initialize news API: %s", e)

        if self._evaluator is None:
            try:
                self._evaluator = NewsImportanceEvaluator()
            except Exception as e:
                logger.error("Failed to initialize NewsImportanceEvaluator: %s", e)

    def _mark_seen(self, h: str) -> bool:
        """标记为已处理，返回 True 如果是新的"""
        if h in self._seen_hashes:
            return False
        self._seen_hashes.add(h)
        self._seen_queue.append(h)
        # 淘汰最旧的
        if len(self._seen_hashes) > _MAX_SEEN:
            old = self._seen_queue.popleft()
            self._seen_hashes.discard(old)
        return True

    async def poll_once(self) -> Dict[str, Any]:
        """
        执行一次新闻轮询。

        流程：
        1. REST API 拉取新闻
        2. seen_hashes 去重
        3. LLM 逐条评估（0-10 打分）
        4. 所有重要新闻**聚合**后，只触发**一次** workflow

        Returns:
            轮询结果摘要
        """
        self._ensure_initialized()
        self.stats["total_polls"] += 1
        self.stats["last_poll"] = utc_now().isoformat()

        result: Dict[str, Any] = {
            "fetched": 0,
            "new": 0,
            "important": 0,
            "triggered": 0,
            "errors": [],
        }

        if not self._news_api:
            result["errors"].append("News API not available")
            return result

        # 1. 获取最新新闻
        try:
            news_items: List[NewsItem] = await self._news_api.get_market_overview_news(
                limit=self.max_news_per_poll,
            )
            result["fetched"] = len(news_items)
            self.stats["total_news_fetched"] += len(news_items)
        except Exception as e:
            logger.error("News poll failed: %s", e)
            result["errors"].append(str(e))
            self.stats["last_error"] = str(e)
            return result

        # 2. 过滤已处理的新闻
        new_items = []
        for item in news_items:
            h = _news_hash(item)
            if self._mark_seen(h):
                new_items.append(item)

        result["new"] = len(new_items)
        self.stats["total_new_news"] += len(new_items)

        if not new_items:
            logger.debug("No new news found in this poll")
            return result

        logger.info("News poll: %d fetched, %d new", result["fetched"], result["new"])

        # 3. LLM 评估每条新闻（先全部评估，收集重要新闻）
        if not self._evaluator or not self._evaluator.llm:
            logger.warning("News evaluator LLM not available, skipping evaluation")
            return result

        important_items: List[Dict[str, Any]] = []

        for item in new_items:
            try:
                rt_news = RealtimeNews(
                    id=_news_hash(item),
                    headline=item.title,
                    summary=item.description or "",
                    source=item.source,
                    url=item.url or "",
                    symbol=item.symbols[0] if item.symbols else "",
                    timestamp=item.published_at,
                )

                evaluation = await self._evaluator.evaluate(rt_news)

                if evaluation.get("is_important"):
                    result["important"] += 1
                    self.stats["total_important"] += 1
                    important_items.append({
                        "news": {
                            "headline": item.title,
                            "summary": item.description or "",
                            "source": item.source,
                            "url": item.url,
                            "symbols": item.symbols,
                            "published_at": (
                                item.published_at.isoformat()
                                if item.published_at
                                else None
                            ),
                        },
                        "evaluation": {
                            "score": evaluation.get("score", 0),
                            "is_important": True,
                            "reason": evaluation.get("reason"),
                            "urgency": evaluation.get("urgency"),
                            "affected_symbols": evaluation.get("affected_symbols", []),
                            "action_suggestion": evaluation.get("action_suggestion"),
                        },
                    })

            except Exception as e:
                logger.error("Error evaluating news '%s': %s", item.title[:50], e)
                result["errors"].append(f"Eval error: {e}")

        # 4. 聚合触发：所有重要新闻合并为一次 workflow 调用
        if important_items:
            await self._trigger_aggregated(important_items)
            result["triggered"] = 1
            self.stats["total_triggers"] += 1

        logger.info(
            "News poll complete: %d new, %d important, triggered=%s",
            result["new"],
            result["important"],
            "yes" if important_items else "no",
        )
        return result

    async def _trigger_aggregated(
        self,
        items: List[Dict[str, Any]],
    ) -> None:
        """将多条重要新闻聚合为一次 workflow 触发"""
        if not self.trading_system:
            logger.warning("TradingSystem not available, cannot trigger analysis")
            return

        # 按 score 降序排列，最重要的在前
        items.sort(key=lambda x: x["evaluation"].get("score", 0), reverse=True)

        if len(items) == 1:
            # 单条新闻：保持简洁的 context 结构
            context = items[0]
        else:
            # 多条新闻：聚合
            context = {
                "important_news_count": len(items),
                "news_items": items,
                "top_headline": items[0]["news"]["headline"],
                "max_score": items[0]["evaluation"].get("score", 0),
            }

        try:
            await self.trading_system.trigger_workflow(
                trigger="polling_news",
                context=context,
            )
            headlines = [it["news"]["headline"][:40] for it in items[:3]]
            logger.info(
                "Triggered workflow for %d important news: %s%s",
                len(items),
                ", ".join(headlines),
                "..." if len(items) > 3 else "",
            )
        except Exception as e:
            logger.error("Failed to trigger workflow: %s", e)

    def get_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        return {
            "poll_interval_minutes": self.poll_interval_minutes,
            "max_news_per_poll": self.max_news_per_poll,
            "seen_count": len(self._seen_hashes),
            "news_api_available": self._news_api is not None,
            "evaluator_available": (
                self._evaluator is not None and self._evaluator.llm is not None
            ),
            **self.stats,
        }


# ========== Module-level function for APScheduler ==========
# APScheduler 需要模块级函数才能被 pickle 序列化

async def _news_poll_job(**kwargs: Any) -> None:
    """
    APScheduler 回调：执行一次新闻轮询。

    通过全局 TradingSystem 实例获取 NewsPollingService。
    """
    try:
        from agent_trader.api.deps import _trading_system_instance
        ts = _trading_system_instance
        if ts is None:
            logger.warning("TradingSystem not initialized, skipping news poll")
            return

        service = getattr(ts, "_news_polling_service", None)
        if service is None:
            logger.warning("NewsPollingService not initialized, skipping")
            return

        await service.poll_once()
    except Exception as e:
        logger.error("News poll job failed: %s", e)
