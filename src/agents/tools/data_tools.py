"""
数据类 Agent Tools

提供投资组合状态、市场数据、新闻、价格等数据查询工具。
每个 create_xxx 函数接收 workflow 实例（WorkflowBase），返回 LangChain @tool 对象。
"""

import json
from typing import Dict, List, Any
from datetime import timedelta

from langchain.tools import tool

from src.utils.logging_config import get_logger
from src.utils.timezone import utc_now

logger = get_logger(__name__)


def create_data_tools(workflow) -> List[tuple]:
    """
    创建所有数据类 tools

    Args:
        workflow: WorkflowBase 子类实例

    Returns:
        [(tool_obj, "data"), ...] 可直接传给 ToolRegistry.register_many()
    """
    return [
        (_create_get_portfolio_status(workflow), "data"),
        (_create_get_market_data(workflow), "data"),
        (_create_get_latest_news(workflow), "data"),
        (_create_get_latest_price(workflow), "data"),
        (_create_get_historical_prices(workflow), "data"),
    ]


def _create_get_portfolio_status(wf):
    @tool
    async def get_portfolio_status() -> str:
        """获取当前投资组合状态，包括总资产、现金、持仓等信息"""
        try:
            await wf.message_manager.send_message("🔍 正在获取组合状态...", "info")

            portfolio = await wf.get_portfolio()
            if not portfolio:
                return "无法获取组合信息"

            positions_info = []
            for pos in portfolio.positions:
                if pos.quantity != 0:
                    pos_pct = float(
                        (pos.market_value / portfolio.equity * 100) if portfolio.equity > 0 else 0
                    )
                    positions_info.append({
                        "symbol": pos.symbol,
                        "quantity": float(pos.quantity),
                        "market_value": float(pos.market_value),
                        "percentage": pos_pct,
                        "unrealized_pnl": float(pos.unrealized_pnl),
                        "unrealized_pnl_pct": float(pos.unrealized_pnl_percentage),
                    })

            cash_pct = float(
                (portfolio.cash / portfolio.equity * 100) if portfolio.equity > 0 else 0
            )

            result = {
                "total_equity": float(portfolio.equity),
                "cash": float(portfolio.cash),
                "cash_percentage": cash_pct,
                "market_value": float(portfolio.market_value),
                "day_pnl": float(portfolio.day_pnl),
                "total_positions": len(positions_info),
                "positions": positions_info,
            }

            summary = f"💼 组合状态: ${portfolio.equity:,.2f} | 现金 {cash_pct:.1f}% | {len(positions_info)}个持仓"
            await wf.message_manager.send_message(summary, "info")

            return json.dumps(result, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"获取组合状态失败: {e}")
            return f"错误: {str(e)}"

    return get_portfolio_status


def _create_get_market_data(wf):
    @tool
    async def get_market_data() -> str:
        """获取市场概况，包括主要指数（SPY, QQQ等）的最新数据"""
        try:
            await wf.message_manager.send_message("📊 正在获取市场数据...", "info")
            market_data = await wf.get_market_data()
            await wf.message_manager.send_message("✅ 市场数据已获取", "info")
            return json.dumps(market_data, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"获取市场数据失败: {e}")
            return f"错误: {str(e)}"

    return get_market_data


def _create_get_latest_news(wf):
    @tool
    async def get_latest_news(
        limit: int = 20,
        symbol: str = None,
        sector: str = None,
    ) -> str:
        """
        获取最新市场新闻，支持按股票代码或行业过滤

        Args:
            limit: 新闻数量，默认20条
            symbol: 可选，按股票代码过滤（如 AAPL, TSLA）
            sector: 可选，按行业过滤（如 Technology, Finance）
        """
        try:
            filter_desc = ""
            if symbol:
                filter_desc = f" (股票: {symbol})"
            elif sector:
                filter_desc = f" (行业: {sector})"

            await wf.message_manager.send_message(
                f"📰 正在获取最新{limit}条新闻{filter_desc}...", "info"
            )

            if symbol:
                news = await wf.news_api.get_symbol_news(symbol, limit=limit)
            elif sector:
                news = await wf.news_api.get_sector_news(sector, limit=limit)
            else:
                news = await wf.get_news(limit=limit)

            news_list = []
            titles = []
            for item in news[:limit]:
                if isinstance(item, dict):
                    title = item["title"]
                    source = item["source"]
                    published_at = item["published_at"]
                    symbols = item.get("symbols", [])
                else:
                    title = item.title
                    source = item.source
                    published_at = str(item.published_at)
                    symbols = item.symbols if hasattr(item, "symbols") else []

                news_list.append({
                    "title": title,
                    "source": source,
                    "published_at": published_at,
                    "symbols": symbols,
                })
                titles.append(f"• {title[:80]}..." if len(title) > 80 else f"• {title}")

            if titles:
                preview = "\n".join(titles[:5])
                more_text = f"\n... 还有 {len(titles) - 5} 条" if len(titles) > 5 else ""
                await wf.message_manager.send_message(
                    f"✅ 已获取{len(news_list)}条新闻{filter_desc}:\n\n{preview}{more_text}",
                    "info",
                )
            else:
                await wf.message_manager.send_message(
                    f"⚠️ 未找到相关新闻{filter_desc}", "warning"
                )

            return json.dumps(news_list, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"获取新闻失败: {e}")
            return f"错误: {str(e)}"

    return get_latest_news


def _create_get_latest_price(wf):
    @tool
    async def get_latest_price(symbol: str) -> str:
        """
        获取个股最新价格

        Args:
            symbol: 股票代码，如 AAPL
        """
        try:
            await wf.message_manager.send_message(f"🔎 正在查询 {symbol} 最新价格...", "info")

            price_data = await wf.market_data_api.get_latest_price(symbol)

            result = {
                "symbol": symbol,
                "latest_price": price_data if price_data else "无法获取",
            }

            if price_data:
                await wf.message_manager.send_message(
                    f"✅ {symbol}: ${price_data.get('close', 'N/A')}", "info"
                )

            return json.dumps(result, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"获取最新价格失败 {symbol}: {e}")
            return f"错误: {str(e)}"

    return get_latest_price


def _create_get_historical_prices(wf):
    @tool
    async def get_historical_prices(
        symbol: str,
        timeframe: str = "1Day",
        limit: int = 100,
    ) -> str:
        """
        获取个股历史价格数据（支持自定义时间框架）

        Args:
            symbol: 股票代码，如 AAPL, MSFT, SPY, QQQ
            timeframe: 时间框架，可选值："1Day", "1Hour", "30Min", "15Min", "5Min", "1Min"
            limit: 返回的K线数量，默认100条
        """
        try:
            if limit < 1 or limit > 1000:
                return "错误: limit必须在1-1000之间"

            await wf.message_manager.send_message(
                f"📈 正在获取 {symbol} 历史数据 ({limit}条, {timeframe})...", "info"
            )

            end_date = utc_now()
            if timeframe in ("1Day", "1Week", "1Month"):
                days_multiplier = {"1Day": 1, "1Week": 7, "1Month": 30}
                days_needed = limit * days_multiplier.get(timeframe, 1) + 30
                start_date = end_date - timedelta(days=days_needed)

                prices = await wf.market_data_api.get_eod_prices(
                    symbol=symbol, start_date=start_date, end_date=end_date
                )
            else:
                start_date = end_date - timedelta(days=min(limit // 100 + 5, 30))
                resample_map = {
                    "1Min": "1min", "5Min": "5min", "15Min": "15min",
                    "30Min": "30min", "1Hour": "1hour",
                }
                resample_freq = resample_map.get(timeframe, "1min")

                prices = await wf.market_data_api.get_intraday_prices(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    resample_freq=resample_freq,
                )

            if not prices:
                await wf.message_manager.send_message(
                    f"⚠️ 无法获取 {symbol} 的历史数据", "warning"
                )
                return json.dumps({
                    "success": False,
                    "message": f"无法获取{symbol}的历史数据",
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "limit": limit,
                }, indent=2, ensure_ascii=False)

            prices = prices[-limit:] if len(prices) > limit else prices
            return json.dumps(prices, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"获取历史价格失败 {symbol}: {e}")
            error_msg = f"错误: {str(e)}"
            await wf.message_manager.send_error(error_msg, f"获取{symbol}历史数据")
            return error_msg

    return get_historical_prices
