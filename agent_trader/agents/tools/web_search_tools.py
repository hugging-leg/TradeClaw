"""
Web Search Agent Tools — SearXNG + Trafilatura

通过自建 SearXNG 实例进行网络搜索，使用 Trafilatura 提取网页正文。
替代 Tavily/SerpAPI 等付费搜索提供商。

架构：
- SearXNG: 自建元搜索引擎，聚合 Google/Bing/DuckDuckGo 等
- Trafilatura: 网页正文提取（去除广告/导航/页脚等噪音）
- 两个 Tool:
  1. web_search: 搜索并返回摘要列表（快速概览）
  2. web_read: 读取指定 URL 的正文（深入阅读）
"""

import json
import asyncio
from typing import List, Optional
from urllib.parse import urlencode

import aiohttp
import trafilatura

from langchain.tools import tool

from agent_trader.utils.logging_config import get_logger
from config import settings

logger = get_logger(__name__)

# SearXNG 默认地址
_DEFAULT_SEARXNG_URL = "http://localhost:8080"


def _get_searxng_url() -> str:
    """获取 SearXNG base URL"""
    return getattr(settings, "searxng_base_url", None) or _DEFAULT_SEARXNG_URL


async def _searxng_search(
    query: str,
    *,
    categories: str = "general",
    language: str = "en",
    time_range: Optional[str] = None,
    limit: int = 10,
) -> List[dict]:
    """
    调用 SearXNG JSON API 执行搜索。

    Args:
        query: 搜索关键词
        categories: 搜索类别 (general, news, science, ...)
        language: 语言
        time_range: 时间范围 (day, week, month, year, None)
        limit: 最大结果数

    Returns:
        [{"title": ..., "url": ..., "snippet": ..., "engine": ...}, ...]
    """
    base_url = _get_searxng_url()
    params = {
        "q": query,
        "format": "json",
        "categories": categories,
        "language": language,
        "pageno": 1,
    }
    if time_range:
        params["time_range"] = time_range

    url = f"{base_url}/search?{urlencode(params)}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    logger.error("SearXNG returned status %d for query: %s", resp.status, query)
                    return []
                data = await resp.json()
    except asyncio.TimeoutError:
        logger.error("SearXNG request timed out for query: %s", query)
        return []
    except Exception as e:
        logger.error("SearXNG request failed: %s", e)
        return []

    results = []
    for item in data.get("results", [])[:limit]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("content", ""),
            "engine": ", ".join(item.get("engines", [])),
            "published_date": item.get("publishedDate", ""),
        })

    return results


async def _fetch_and_extract(url: str, *, max_chars: int = 5000) -> str:
    """
    获取 URL 内容并用 Trafilatura 提取正文。

    Args:
        url: 目标 URL
        max_chars: 最大返回字符数

    Returns:
        提取的正文文本，失败时返回错误信息
    """
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            }
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=15),
                headers=headers,
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    return f"[HTTP {resp.status}] 无法获取页面"
                html = await resp.text()
    except asyncio.TimeoutError:
        return "[超时] 页面加载超时"
    except Exception as e:
        return f"[错误] 获取页面失败: {e}"

    # Trafilatura 是 CPU 密集型，放到线程池执行
    try:
        text = await asyncio.to_thread(
            trafilatura.extract,
            html,
            include_comments=False,
            include_tables=True,
            favor_recall=True,
        )
    except Exception as e:
        return f"[解析错误] Trafilatura 提取失败: {e}"

    if not text:
        return "[空内容] 无法从页面提取有效文本"

    # 截断过长的内容
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n... [已截断，原文共 {len(text)} 字符]"

    return text


# ============================================================
# LangChain Tools
# ============================================================


def create_web_search_tools(workflow) -> List[tuple]:
    """
    创建 Web 搜索类 tools

    Args:
        workflow: WorkflowBase 子类实例

    Returns:
        [(tool_obj, "web_search"), ...] 可直接传给 ToolRegistry.register_many()
    """
    tools = []

    # 检查 SearXNG 是否配置
    searxng_url = _get_searxng_url()
    if not searxng_url:
        logger.info("SearXNG 未配置 (SEARXNG_BASE_URL)，web search tools 未注册")
        return tools

    tools.append((_create_web_search(workflow), "web_search"))
    tools.append((_create_web_read(workflow), "web_search"))

    logger.info("Web search tools registered (SearXNG: %s)", searxng_url)
    return tools


def _create_web_search(wf):
    @tool
    async def web_search(
        query: str,
        category: str = "general",
        time_range: str = "",
        max_results: int = 8,
    ) -> str:
        """
        搜索互联网获取最新信息。使用多个搜索引擎聚合结果。

        适用场景：
        - 查找最新新闻、事件背景
        - 研究公司动态、行业趋势
        - 了解宏观经济政策（如 FOMC、CPI 数据）
        - 获取 Tiingo/Finnhub 新闻源未覆盖的信息

        Args:
            query: 搜索关键词，如 "NVIDIA earnings Q4 2024" 或 "Federal Reserve interest rate decision"
            category: 搜索类别。可选值: "general"（通用）, "news"（新闻）。默认 "general"
            time_range: 时间范围过滤。可选值: ""（不限）, "day"（24小时）, "week"（一周）, "month"（一月）。默认不限
            max_results: 最大返回结果数，默认8条

        Returns:
            搜索结果列表（标题、URL、摘要）的 JSON
        """
        try:
            if max_results < 1:
                max_results = 1
            elif max_results > 20:
                max_results = 20

            await wf.message_manager.send_message(
                f"🔍 正在搜索: {query}" + (f" [{category}]" if category != "general" else ""),
                "info",
            )

            results = await _searxng_search(
                query,
                categories=category,
                time_range=time_range or None,
                limit=max_results,
            )

            if not results:
                await wf.message_manager.send_message("⚠️ 未找到搜索结果", "warning")
                return json.dumps({
                    "success": False,
                    "query": query,
                    "message": "未找到搜索结果，请尝试不同的关键词",
                    "results": [],
                }, ensure_ascii=False)

            # 构建摘要
            titles = [f"• {r['title'][:80]}" for r in results[:5]]
            preview = "\n".join(titles)
            more = f"\n... 共 {len(results)} 条结果" if len(results) > 5 else ""
            await wf.message_manager.send_message(
                f"✅ 找到 {len(results)} 条结果:\n\n{preview}{more}",
                "info",
            )

            return json.dumps({
                "success": True,
                "query": query,
                "total": len(results),
                "results": results,
            }, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error("web_search failed: %s", e)
            return f"搜索失败: {e}"

    return web_search


def _create_web_read(wf):
    @tool
    async def web_read(
        url: str,
        max_chars: int = 5000,
    ) -> str:
        """
        读取并提取指定网页的正文内容。自动去除广告、导航栏等噪音。

        适用场景：
        - 深入阅读 web_search 返回的某个结果
        - 阅读新闻全文、研报、博客文章
        - 获取搜索结果摘要不够详细时的完整信息

        Args:
            url: 要读取的网页 URL
            max_chars: 最大返回字符数，默认5000。设置更大的值可获取更完整的内容

        Returns:
            提取的网页正文内容
        """
        try:
            if max_chars < 500:
                max_chars = 500
            elif max_chars > 20000:
                max_chars = 20000

            await wf.message_manager.send_message(
                f"📖 正在读取: {url[:80]}...",
                "info",
            )

            text = await _fetch_and_extract(url, max_chars=max_chars)

            if text.startswith("["):
                # 错误信息
                await wf.message_manager.send_message(f"⚠️ {text}", "warning")
                return json.dumps({
                    "success": False,
                    "url": url,
                    "error": text,
                }, ensure_ascii=False)

            char_count = len(text)
            await wf.message_manager.send_message(
                f"✅ 已提取 {char_count} 字符的正文内容",
                "info",
            )

            return json.dumps({
                "success": True,
                "url": url,
                "char_count": char_count,
                "content": text,
            }, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error("web_read failed for %s: %s", url, e)
            return f"读取失败: {e}"

    return web_read
