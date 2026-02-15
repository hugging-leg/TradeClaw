import asyncio
import json
from src.utils.logging_config import get_logger
from typing import Dict, List, Any, Optional, Annotated
from datetime import datetime, timedelta
from decimal import Decimal

from src.utils.timezone import utc_now, format_for_display

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain.tools import tool
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel, Field

from config import settings
from src.agents.workflow_base import WorkflowBase
from src.agents.workflow_factory import register_workflow
from src.interfaces.broker_api import BrokerAPI
from src.interfaces.market_data_api import MarketDataAPI
from src.interfaces.news_api import NewsAPI
from src.messaging.message_manager import MessageManager
from src.events.event_system import event_system
from src.models.trading_models import (
    Order, Portfolio, TradingDecision, OrderSide, OrderType,
    TimeInForce, Position
)
from src.utils.llm_utils import create_llm_client
from src.utils.db_utils import check_db_available, DB_AVAILABLE, get_trading_repository

logger = get_logger(__name__)


class RebalanceRequest(BaseModel):
    """重新平衡请求"""
    target_allocations: Dict[str, float] = Field(
        description="目标配置，格式: {'AAPL': 20.0, 'MSFT': 20.0, ...}，百分比总和应为100"
    )
    reason: str = Field(description="重新平衡的原因")


@register_workflow(
    "llm_portfolio",
    description="完全由 LLM 驱动的投资组合管理",
    features=["🆕 无硬编码规则", "ReAct Agent", "多工具协作", "可解释决策"],
    best_for="🌟 智能自适应组合管理（推荐）"
)
class LLMPortfolioAgent(WorkflowBase):
    """
    LLM驱动的投资组合管理Agent
    
    核心特点：
    - 无硬编码规则，完全由LLM决策
    - LLM可使用多个tools获取信息
    - LLM自主决定是否rebalance
    - 灵活、智能、可解释
    """
    
    def __init__(self, 
                 broker_api: BrokerAPI = None,
                 market_data_api: MarketDataAPI = None,
                 news_api: NewsAPI = None,
                 message_manager: MessageManager = None,
                 session_id: str = "trading_agent"):
        """初始化LLM Portfolio Agent"""
        super().__init__(broker_api, market_data_api, news_api, message_manager)
        
        self.llm = create_llm_client()
        self.event_system = event_system  # 用于LLM自主调度
        self.session_id = session_id
        
        # 创建tools
        self.tools = self._create_tools()
        
        # 创建 Memory（用于保存对话状态）
        self.memory = MemorySaver()
        
        # 创建ReAct agent with memory
        self.agent = create_react_agent(
            self.llm,
            self.tools,
            checkpointer=self.memory
        )
        
        # Agent 配置
        self.agent_config = {"recursion_limit": settings.llm_recursion_limit}
        
        # 保存system prompt以便后续使用
        self.system_prompt = self._get_system_prompt()
        
        # Agent状态（限制内存历史大小）
        self.analysis_history = []
        self._max_analysis_history = settings.llm_max_analysis_history
        self.last_analysis_time = None
        
        # 历史摘要
        self.history_summary = ""
        self.max_summary_tokens = settings.llm_max_summary_tokens
        
        # 数据持久化
        self._db_available = DB_AVAILABLE
        
        logger.info("LLM Portfolio Agent 已初始化（支持历史摘要和数据持久化）")
    
    def _get_system_prompt(self) -> str:
        """获取系统提示"""
        return f"""你是一位专业的私募投资组合经理，负责管理美股以及ETF投资组合，争取达到sharpe ratio 3以上。

## 你的职责
1. 持续分析市场状况、新闻事件和组合配置
2. 基于分析自主决定是否需要调整组合
3. 决定目标仓位配置
4. 执行组合重新平衡

## 重要提示
- 你可以持有多只股票/ETF，你完全自主决策，根据市场情况灵活调整配置，做出理性、明智、专业的决策
- 只做主升不做调整，不炒毛票，多空ETF增强，严格分仓避免单票梭哈
- 杠杆ETF要考虑磨损，非特殊情况不要长期持有，但合适的使用可以带来高收益
- 重点关注美联储的消息，科技公司的消息，以及重大新闻事件
- 重点关注科技公司、金融公司和黄金，也可以思考如何对冲风险，市场不好时可以尝试买做空ETF

## 自主调度
- 分析完成后，如有需要，你可以使用schedule_next_analysis安排下一次分析时间（将作为workflow事件触发）
- 例如：预期有重要新闻（如FOMC会议、财报发布），可以提前安排分析，市场波动剧烈，可以安排更频繁的检查
- 每日例行分析默认开启，不需要手动安排。

## 现金仓位管理
- 百分比总和可以小于100%，剩余部分会自动保留为现金
- 可以根据市场情况灵活调整现金比例，如市场不确定时可以增加现金占比
"""
    
    def _create_tools(self) -> List:
        """创建提供给LLM的工具"""
        
        @tool
        async def get_portfolio_status() -> str:
            """获取当前投资组合状态，包括总资产、现金、持仓等信息"""
            try:
                # 实时通知
                await self.message_manager.send_message("🔍 正在获取组合状态...", "info")
                
                portfolio = await self.get_portfolio()
                if not portfolio:
                    return "无法获取组合信息"
                
                positions_info = []
                for pos in portfolio.positions:
                    if pos.quantity != 0:
                        pos_pct = float((pos.market_value / portfolio.equity * 100) if portfolio.equity > 0 else 0)
                        positions_info.append({
                            "symbol": pos.symbol,
                            "quantity": float(pos.quantity),
                            "market_value": float(pos.market_value),
                            "percentage": pos_pct,
                            "unrealized_pnl": float(pos.unrealized_pnl),
                            "unrealized_pnl_pct": float(pos.unrealized_pnl_percentage)
                        })
                
                cash_pct = float((portfolio.cash / portfolio.equity * 100) if portfolio.equity > 0 else 0)
                
                result = {
                    "total_equity": float(portfolio.equity),
                    "cash": float(portfolio.cash),
                    "cash_percentage": cash_pct,
                    "market_value": float(portfolio.market_value),
                    "day_pnl": float(portfolio.day_pnl),
                    "total_positions": len(positions_info),
                    "positions": positions_info
                }
                
                # 发送摘要
                summary = f"💼 组合状态: ${portfolio.equity:,.2f} | 现金 {cash_pct:.1f}% | {len(positions_info)}个持仓"
                await self.message_manager.send_message(summary, "info")
                
                return json.dumps(result, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"获取组合状态失败: {e}")
                return f"错误: {str(e)}"
        
        @tool
        async def get_market_data() -> str:
            """获取市场概况，包括主要指数（SPY, QQQ等）的最新数据"""
            try:
                await self.message_manager.send_message("📊 正在获取市场数据...", "info")
                market_data = await self.get_market_data()
                await self.message_manager.send_message("✅ 市场数据已获取", "info")
                return json.dumps(market_data, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"获取市场数据失败: {e}")
                return f"错误: {str(e)}"
        
        @tool
        async def get_latest_news(
            limit: int = 20,
            symbol: str = None,
            sector: str = None
        ) -> str:
            """
            获取最新市场新闻，支持按股票代码或行业过滤
            
            Args:
                limit: 新闻数量，默认20条
                symbol: 可选，按股票代码过滤（如 AAPL, TSLA）
                sector: 可选，按行业过滤（如 Technology, Finance）
            """
            try:
                # 构建提示消息
                filter_desc = ""
                if symbol:
                    filter_desc = f" (股票: {symbol})"
                elif sector:
                    filter_desc = f" (行业: {sector})"
                
                await self.message_manager.send_message(
                    f"📰 正在获取最新{limit}条新闻{filter_desc}...", 
                    "info"
                )
                
                # 根据参数获取新闻
                if symbol:
                    news = await self.news_api.get_symbol_news(symbol, limit=limit)
                elif sector:
                    news = await self.news_api.get_sector_news(sector, limit=limit)
                else:
                    news = await self.get_news(limit=limit)
                
                news_list = []
                titles = []
                for item in news[:limit]:
                    # NewsItem 可能是对象或字典，统一处理
                    if isinstance(item, dict):
                        title = item["title"]
                        source = item["source"]
                        published_at = item["published_at"]
                        symbols = item.get("symbols", [])
                    else:
                        # 处理 NewsItem 对象
                        title = item.title
                        source = item.source
                        published_at = str(item.published_at)
                        symbols = item.symbols if hasattr(item, 'symbols') else []
                    
                    news_list.append({
                        "title": title,
                        "source": source,
                        "published_at": published_at,
                        "symbols": symbols
                    })
                    # 收集标题用于显示
                    titles.append(f"• {title[:80]}..." if len(title) > 80 else f"• {title}")
                
                # 发送新闻标题摘要（最多显示前5条）
                if titles:
                    preview = "\n".join(titles[:5])
                    more_text = f"\n... 还有 {len(titles)-5} 条" if len(titles) > 5 else ""
                    await self.message_manager.send_message(
                        f"✅ 已获取{len(news_list)}条新闻{filter_desc}:\n\n{preview}{more_text}",
                        "info"
                    )
                else:
                    await self.message_manager.send_message(
                        f"⚠️ 未找到相关新闻{filter_desc}",
                        "warning"
                    )
                
                return json.dumps(news_list, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"获取新闻失败: {e}")
                return f"错误: {str(e)}"
        
        @tool
        async def get_position_analysis() -> str:
            """分析当前持仓分布，包括各仓位占比、集中度等"""
            try:
                await self.message_manager.send_message("🔬 正在分析持仓分布...", "info")
                
                portfolio = await self.get_portfolio()
                if not portfolio or portfolio.equity <= 0:
                    return "组合为空或无法获取"
                
                analysis = {
                    "total_positions": 0,
                    "position_details": [],
                    "concentration": {
                        "largest_position_pct": 0.0,
                        "top3_concentration": 0.0
                    }
                }
                
                positions_with_pct = []
                for pos in portfolio.positions:
                    if pos.quantity != 0:
                        pct = (pos.market_value / portfolio.equity) * 100
                        positions_with_pct.append({
                            "symbol": pos.symbol,
                            "percentage": float(pct),
                            "market_value": float(pos.market_value),
                            "pnl_pct": float(pos.unrealized_pnl_percentage)
                        })
                
                # 按市值排序
                positions_with_pct.sort(key=lambda x: x["market_value"], reverse=True)
                
                analysis["total_positions"] = len(positions_with_pct)
                analysis["position_details"] = positions_with_pct
                
                if positions_with_pct:
                    analysis["concentration"]["largest_position_pct"] = positions_with_pct[0]["percentage"]
                    top3 = sum(p["percentage"] for p in positions_with_pct[:3])
                    analysis["concentration"]["top3_concentration"] = top3
                
                await self.message_manager.send_message(
                    f"✅ 分析完成: {len(positions_with_pct)}个仓位, 最大{analysis['concentration']['largest_position_pct']:.1f}%",
                    "info"
                )
                
                return json.dumps(analysis, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"分析持仓失败: {e}")
                return f"错误: {str(e)}"
        
        @tool
        async def get_latest_price(symbol: str) -> str:
            """
            获取个股最新价格
            
            Args:
                symbol: 股票代码，如 AAPL
            """
            try:
                await self.message_manager.send_message(f"🔎 正在查询 {symbol} 最新价格...", "info")
                
                # 获取最新价格
                price_data = await self.market_data_api.get_latest_price(symbol)
                
                result = {
                    "symbol": symbol,
                    "latest_price": price_data if price_data else "无法获取"
                }
                
                if price_data:
                    await self.message_manager.send_message(
                        f"✅ {symbol}: ${price_data.get('close', 'N/A')}",
                        "info"
                    )
                
                return json.dumps(result, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"获取最新价格失败 {symbol}: {e}")
                return f"错误: {str(e)}"
        
        @tool
        async def get_historical_prices(
            symbol: str,
            timeframe: str = "1Day",
            limit: int = 100
        ) -> str:
            """
            获取个股历史价格数据（支持自定义时间框架）
            
            Args:
                symbol: 股票代码，如 AAPL, MSFT, SPY, QQQ
                timeframe: 时间框架，可选值："1Day", "1Hour", "30Min", "15Min", "5Min", "1Min"
                limit: 返回的K线数量，默认100条
            
            Returns:
                历史价格数据的JSON字符串，包含时间戳、ohlcv
            """
            try:
                from datetime import datetime, timedelta
                
                # 参数验证
                if limit < 1 or limit > 1000:
                    return "错误: limit必须在1-1000之间"
                
                await self.message_manager.send_message(
                    f"📈 正在获取 {symbol} 历史数据 ({limit}条, {timeframe})...",
                    "info"
                )
                
                # 根据 timeframe 计算日期范围
                end_date = utc_now()
                if timeframe in ["1Day", "1Week", "1Month"]:
                    # 日线/周线/月线用 EOD 接口
                    days_multiplier = {"1Day": 1, "1Week": 7, "1Month": 30}
                    days_needed = limit * days_multiplier.get(timeframe, 1) + 30
                    start_date = end_date - timedelta(days=days_needed)
                    
                    prices = await self.market_data_api.get_eod_prices(
                        symbol=symbol,
                        start_date=start_date,
                        end_date=end_date
                    )
                else:
                    # 分钟/小时线用 Intraday 接口
                    # 分钟数据最多回溯几天
                    start_date = end_date - timedelta(days=min(limit // 100 + 5, 30))
                    resample_map = {"1Min": "1min", "5Min": "5min", "15Min": "15min", "30Min": "30min", "1Hour": "1hour"}
                    resample_freq = resample_map.get(timeframe, "1min")
                    
                    prices = await self.market_data_api.get_intraday_prices(
                        symbol=symbol,
                        start_date=start_date,
                        end_date=end_date,
                        resample_freq=resample_freq
                    )
                
                if not prices:
                    await self.message_manager.send_message(
                        f"⚠️ 无法获取 {symbol} 的历史数据",
                        "warning"
                    )
                    return json.dumps({
                        "success": False,
                        "message": f"无法获取{symbol}的历史数据",
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "limit": limit
                    }, indent=2, ensure_ascii=False)
                
                # 只返回最近 limit 条
                prices = prices[-limit:] if len(prices) > limit else prices
                return json.dumps(prices, indent=2, ensure_ascii=False)
                
            except Exception as e:
                logger.error(f"获取历史价格失败 {symbol}: {e}")
                error_msg = f"错误: {str(e)}"
                await self.message_manager.send_error(error_msg, f"获取{symbol}历史数据")
                return error_msg
        
        @tool
        async def rebalance_portfolio(
            target_allocations: Dict[str, float],
            reason: str
        ) -> str:
            """
            执行组合重新平衡
            
            Args:
                target_allocations: 目标配置，例如 {"AAPL": 25.0, "MSFT": 25.0, "GOOGL": 25.0, "AMZN": 25.0}
                                   - 只需指定股票/ETF的百分比，不要包含现金或"CASH"避免同名股票混淆
                                   - 百分比总和可以小于100%，剩余部分自动为现金
                                   - 例如: {"AAPL": 30, "MSFT": 30} 表示30%+30%+40%现金
                reason: 重新平衡的原因说明
            
            Returns:
                执行结果
            """
            try:
                # 检查市场状态
                market_open = await self.is_market_open()
                if not market_open:
                    warning_msg = "⚠️ 市场未开放，无法执行交易。交易计划已保存，将在下次市场开放时执行。"
                    await self.message_manager.send_message(warning_msg, "warning")
                    return json.dumps({
                        "success": False,
                        "message": "市场未开放，无法执行交易",
                        "market_open": False,
                        "target_allocations": target_allocations,
                        "reason": reason
                    }, indent=2, ensure_ascii=False)
                
                # 过滤掉可能的现金关键词
                cash_keywords = ['CASH', 'USD', 'DOLLAR', '现金', '美元']
                filtered_allocations = {
                    k: v for k, v in target_allocations.items() 
                    if k.upper() not in cash_keywords
                }
                
                if len(filtered_allocations) != len(target_allocations):
                    removed = set(target_allocations.keys()) - set(filtered_allocations.keys())
                    logger.info(f"移除了现金关键词: {removed}")
                    target_allocations = filtered_allocations
                
                # 验证配置：总和应该≤100%
                total_pct = sum(target_allocations.values())
                if total_pct > 100:
                    return f"错误: 目标配置总和为{total_pct}%，不能超过100%"
                
                # 计算现金比例
                cash_pct = 100 - total_pct
                
                # 获取当前组合
                portfolio = await self.get_portfolio()
                if not portfolio:
                    return "错误: 无法获取组合信息"
                
                # 通知开始重新平衡
                allocation_lines = [f"- {sym}: {pct:.1f}%" for sym, pct in target_allocations.items()]
                if cash_pct > 0:
                    allocation_lines.append(f"- 💵 现金: {cash_pct:.1f}%")
                
                await self.message_manager.send_message(
                    f"🔄 **LLM发起组合重新平衡**\n\n"
                    f"原因: {reason}\n\n"
                    f"目标配置:\n" + "\n".join(allocation_lines),
                    "warning"
                )
                
                # 计算需要执行的交易
                trades = await self._calculate_rebalance_trades(
                    portfolio, 
                    target_allocations
                )
                
                if not trades:
                    no_trade_msg = "✅ 经计算，所有仓位都在阈值范围内，无需调整"
                    await self.message_manager.send_message(no_trade_msg, "info")
                    return json.dumps({
                        "success": True,
                        "message": "无需调整",
                        "trades": []
                    }, indent=2, ensure_ascii=False)
                
                # 执行交易
                results = await self._execute_rebalance_trades(trades)
                
                # 返回结果
                success_count = sum(1 for r in results if r["success"])
                result_msg = f"重新平衡完成: {success_count}/{len(results)} 笔交易成功"
                
                await self.message_manager.send_message(
                    f"✅ {result_msg}",
                    "success" if success_count == len(results) else "warning"
                )
                
                return json.dumps({
                    "success": True,
                    "message": result_msg,
                    "trades": results
                }, indent=2, ensure_ascii=False, default=str)  # 添加default=str处理UUID等对象
                
            except Exception as e:
                logger.error(f"重新平衡失败: {e}")
                error_msg = f"错误: {str(e)}"
                await self.message_manager.send_error(error_msg, "重新平衡")
                return error_msg
        
        @tool
        async def get_current_time() -> str:
            """
            获取当前日期和时间（UTC时间）
            
            Returns:
                当前日期时间信息
            """
            try:
                now_utc = datetime.now(pytz.UTC)
                
                result = {
                    "current_time_utc": now_utc.strftime('%Y-%m-%d %H:%M:%S %Z'),
                }
                
                await self.message_manager.send_message(
                    f"🕐 当前时间: {result['current_time_utc']}",
                    "info"
                )
                
                return json.dumps(result, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"获取当前时间失败: {e}")
                return f"错误: {str(e)}"
        
        @tool
        async def check_market_status() -> str:
            """
            检查市场是否开放
            
            Returns:
                市场开放状态信息
            """
            try:
                await self.message_manager.send_message("🏪 正在检查市场状态...", "info")
                
                is_open = await self.is_market_open()
                now_utc = datetime.now(pytz.UTC)
                
                result = {
                    "market_open": is_open,
                    "checked_at": now_utc.strftime('%Y-%m-%d %H:%M:%S UTC'),
                }
                
                status_emoji = "🟢" if is_open else "🔴"
                await self.message_manager.send_message(
                    f"{status_emoji} 市场状态: {'Open' if is_open else 'Closed'}",
                    "info"
                )
                
                return json.dumps(result, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"检查市场状态失败: {e}")
                return f"错误: {str(e)}"
        
        @tool
        async def adjust_position(
            symbol: str,
            target_percentage: float,
            reason: str
        ) -> str:
            """
            调整单个股票/ETF的仓位到指定百分比
            
            Args:
                symbol: 股票代码，如 AAPL, MSFT
                target_percentage: 目标百分比（0-100），例如 20.0 表示调整到总资产的20%
                reason: 调整原因说明
            
            Returns:
                调整结果
            """
            try:
                # 检查市场状态
                market_open = await self.is_market_open()
                if not market_open:
                    warning_msg = "⚠️ 市场未开放，无法执行交易"
                    await self.message_manager.send_message(warning_msg, "warning")
                    return json.dumps({
                        "success": False,
                        "message": "市场未开放，无法执行交易",
                        "market_open": False
                    }, indent=2, ensure_ascii=False)
                
                # 参数验证
                if target_percentage < 0 or target_percentage > 100:
                    return "错误: target_percentage必须在0-100之间"
                
                # 获取当前组合
                portfolio = await self.get_portfolio()
                if not portfolio:
                    return "错误: 无法获取组合信息"
                
                # 通知开始调整
                await self.message_manager.send_message(
                    f"🔧 **调整单个仓位**\n\n"
                    f"股票: {symbol}\n"
                    f"目标仓位: {target_percentage:.1f}%\n"
                    f"原因: {reason}",
                    "warning"
                )
                
                # 计算目标市值
                target_value = portfolio.equity * Decimal(str(target_percentage / 100))
                
                # 获取当前持仓
                current_position = None
                for pos in portfolio.positions:
                    if pos.symbol == symbol and pos.quantity != 0:
                        current_position = pos
                        break
                
                current_value = current_position.market_value if current_position else Decimal('0')
                current_pct = (current_value / portfolio.equity * 100) if portfolio.equity > 0 else Decimal('0')
                
                value_diff = target_value - current_value
                
                # 最小调整阈值
                MIN_VALUE_THRESHOLD = Decimal('20')
                if abs(value_diff) < MIN_VALUE_THRESHOLD:
                    no_change_msg = f"✅ {symbol} 当前仓位 {float(current_pct):.1f}%，与目标 {target_percentage:.1f}% 接近，无需调整"
                    await self.message_manager.send_message(no_change_msg, "info")
                    return json.dumps({
                        "success": True,
                        "message": "无需调整",
                        "symbol": symbol,
                        "current_percentage": float(current_pct),
                        "target_percentage": target_percentage
                    }, indent=2, ensure_ascii=False)
                
                # 获取当前价格
                price_data = await self.market_data_api.get_latest_price(symbol)
                if not price_data:
                    return f"错误: 无法获取{symbol}价格"
                
                current_price = Decimal(str(price_data['close']))
                if current_price <= 0:
                    return f"错误: {symbol}价格无效"
                
                # 计算需要交易的股数
                shares_to_trade = value_diff / current_price
                
                if abs(shares_to_trade) < 1:
                    no_change_msg = f"✅ {symbol} 调整幅度过小（<1股），无需交易"
                    await self.message_manager.send_message(no_change_msg, "info")
                    return json.dumps({
                        "success": True,
                        "message": "调整幅度过小，无需交易",
                        "symbol": symbol,
                        "current_percentage": float(current_pct),
                        "target_percentage": target_percentage
                    }, indent=2, ensure_ascii=False)
                
                # 构建交易
                action = "BUY" if shares_to_trade > 0 else "SELL"
                shares = abs(int(shares_to_trade))
                
                trade = {
                    "symbol": symbol,
                    "action": action,
                    "shares": shares,
                    "price": float(current_price),
                    "target_pct": target_percentage,
                    "current_pct": float(current_pct)
                }
                
                # 执行交易
                result = await self._execute_single_trade(trade)
                
                if result["success"]:
                    success_msg = f"✅ {symbol} 仓位调整成功: {action} {shares}股"
                    await self.message_manager.send_message(success_msg, "success")
                else:
                    error_msg = f"❌ {symbol} 仓位调整失败: {result.get('error', '未知错误')}"
                    await self.message_manager.send_message(error_msg, "error")
                
                return json.dumps({
                    "success": result["success"],
                    "symbol": symbol,
                    "action": action,
                    "shares": shares,
                    "current_percentage": float(current_pct),
                    "target_percentage": target_percentage,
                    "order_id": result.get("order_id"),
                    "error": result.get("error")
                }, indent=2, ensure_ascii=False, default=str)
                
            except Exception as e:
                logger.error(f"调整仓位失败 {symbol}: {e}")
                error_msg = f"错误: {str(e)}"
                await self.message_manager.send_error(error_msg, f"调整{symbol}仓位")
                return error_msg
        
        @tool
        async def schedule_next_analysis(
            hours_from_now: float,
            reason: str,
            priority: int = 0
        ) -> str:
            """
            安排下一次组合分析时间（LLM自主调度）
            
            Args:
                hours_from_now: 多少小时后执行，可以是小数（如0.5表示30分钟，2.5表示2.5小时）
                reason: 安排原因，例如"预期FOMC会议结果公布"、"等待财报发布"、"市场波动监控"等
                priority: 优先级（-10-10，数字越小优先级越高），默认0为普通优先级
            
            Returns:
                调度结果
            """
            try:
                # 计算执行时间 (使用UTC时区以避免timezone比较问题)
                scheduled_time = datetime.now(pytz.UTC) + timedelta(hours=hours_from_now)
                
                # 通知
                await self.message_manager.send_message(
                    f"⏰ **LLM自主调度**\n\n"
                    f"安排时间: {scheduled_time.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                    f"距离现在: {hours_from_now:.1f}小时\n"
                    f"原因: {reason}\n"
                    f"优先级: {priority}",
                    "info"
                )
                
                # 发布事件
                await self.event_system.publish(
                    "trigger_workflow",
                    {
                        "trigger": "llm_scheduled",
                        "context": {
                            "reason": reason,
                            "scheduled_by": "llm_agent"
                        }
                    },
                    scheduled_time=scheduled_time,
                    priority=priority
                )
                
                logger.info(f"LLM Scheduled Analysis: {scheduled_time.isoformat()} - {reason}")
                
                return json.dumps({
                    "success": True,
                    "scheduled_time": scheduled_time.isoformat(),
                    "hours_from_now": hours_from_now,
                    "reason": reason,
                    "message": f"已安排{hours_from_now:.1f}小时后的分析"
                }, indent=2, ensure_ascii=False)
                
            except Exception as e:
                logger.error(f"安排下一次分析失败: {e}")
                return f"错误: {str(e)}"
        
        return [
            get_portfolio_status,
            get_market_data,
            get_latest_news,
            get_position_analysis,
            get_latest_price,
            get_historical_prices,
            get_current_time,
            check_market_status,
            adjust_position,
            rebalance_portfolio,
            schedule_next_analysis
        ]
    
    async def _calculate_rebalance_trades(
        self, 
        portfolio: Portfolio, 
        target_allocations: Dict[str, float]
    ) -> List[Dict[str, Any]]:
        """计算需要执行的交易"""
        trades = []
        
        # 最小调整阈值：市值差异小于$20或比例差异小于1%则不调整
        MIN_VALUE_THRESHOLD = Decimal('20')
        MIN_PCT_THRESHOLD = Decimal('1.0')
        
        # 获取当前持仓
        current_positions = {pos.symbol: pos for pos in portfolio.positions if pos.quantity != 0}
        
        # 计算可用资金（现金 + 需要卖出的仓位市值）
        available_cash = portfolio.cash
        
        # 先计算所有卖出订单，累加可用资金
        sell_value = Decimal('0')
        for symbol, position in current_positions.items():
            if symbol not in target_allocations:
                sell_value += position.market_value
            else:
                target_value = portfolio.equity * Decimal(str(target_allocations[symbol] / 100))
                if position.market_value > target_value:
                    sell_value += (position.market_value - target_value)
        
        available_for_buy = available_cash + sell_value
        
        # 计算目标市值
        for symbol, target_pct in target_allocations.items():
            target_value = portfolio.equity * Decimal(str(target_pct / 100))
            
            current_position = current_positions.get(symbol)
            current_value = current_position.market_value if current_position else Decimal('0')
            current_pct = (current_value / portfolio.equity * 100) if portfolio.equity > 0 else Decimal('0')
            
            value_diff = target_value - current_value
            pct_diff = abs(target_pct - float(current_pct))
            
            # 检查是否超过调整阈值
            if abs(value_diff) < MIN_VALUE_THRESHOLD and pct_diff < float(MIN_PCT_THRESHOLD):
                logger.info(f"{symbol} 无需调整: 差异${value_diff:.2f} ({pct_diff:.1f}%) < 阈值")
                continue
            
            # 获取当前价格
            price_data = await self.market_data_api.get_latest_price(symbol)
            if not price_data:
                logger.warning(f"无法获取{symbol}价格，跳过")
                continue
            
            current_price = Decimal(str(price_data['close']))
            if current_price <= 0:
                continue
            
            shares_to_trade = value_diff / current_price
            
            if abs(shares_to_trade) >= 1:
                action = "BUY" if shares_to_trade > 0 else "SELL"
                shares = abs(int(shares_to_trade))
                
                # 对于买入订单，检查是否有足够资金
                if action == "BUY":
                    estimated_cost = shares * current_price
                    if estimated_cost > available_for_buy * Decimal('0.95'):  # 留5%余地
                        # 调整为可负担的股数
                        shares = int((available_for_buy * Decimal('0.95')) / current_price)
                        if shares < 1:
                            logger.warning(f"资金不足，跳过{symbol}买入")
                            continue
                        available_for_buy -= shares * current_price
                
                trades.append({
                    "symbol": symbol,
                    "action": action,
                    "shares": shares,
                    "price": float(current_price),
                    "target_pct": target_pct,
                    "current_pct": float(current_pct),
                    "pct_diff": pct_diff
                })
        
        # 清仓不在目标配置中的股票
        for symbol, position in current_positions.items():
            if symbol not in target_allocations and position.quantity > 0:
                trades.append({
                    "symbol": symbol,
                    "action": "SELL",
                    "shares": abs(int(position.quantity)),
                    "price": 0,  # 市价
                    "target_pct": 0,
                    "current_pct": float((position.market_value / portfolio.equity * 100)),
                    "pct_diff": float((position.market_value / portfolio.equity * 100))
                })
        
        return trades
    
    async def _execute_rebalance_trades(self, trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """执行重新平衡交易"""
        results = []
        
        # 先卖出
        sell_trades = [t for t in trades if t["action"] == "SELL"]
        for trade in sell_trades:
            result = await self._execute_single_trade(trade)
            results.append(result)
            if result["success"]:
                await asyncio.sleep(1)
        
        # 再买入
        buy_trades = [t for t in trades if t["action"] == "BUY"]
        for trade in buy_trades:
            result = await self._execute_single_trade(trade)
            results.append(result)
            if result["success"]:
                await asyncio.sleep(1)
        
        return results
    
    async def _execute_single_trade(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        """执行单笔交易"""
        try:
            order = Order(
                symbol=trade["symbol"],
                side=OrderSide.BUY if trade["action"] == "BUY" else OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=Decimal(str(trade["shares"])),
                time_in_force=TimeInForce.DAY
            )
            
            order_id = await self.broker_api.submit_order(order)
            
            if order_id:
                return {
                    "success": True,
                    "symbol": trade["symbol"],
                    "action": trade["action"],
                    "shares": trade["shares"],
                    "order_id": str(order_id)  # 转换为字符串
                }
            else:
                return {
                    "success": False,
                    "symbol": trade["symbol"],
                    "action": trade["action"],
                    "error": "订单提交失败"
                }
        except Exception as e:
            return {
                "success": False,
                "symbol": trade["symbol"],
                "action": trade["action"],
                "error": str(e)
            }
    
    async def run_workflow(self, initial_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        运行LLM驱动的组合管理workflow
        
        Args:
            initial_context: 初始上下文（可选）
        
        Returns:
            执行结果
        """
        try:
            self.workflow_id = self._generate_workflow_id()
            self.start_time = utc_now()
            
            context = initial_context or {}
            trigger = context.get("trigger", "manual")
            
            await self.send_workflow_start_notification(f"Agent trader ({trigger})")
            
            # 构建初始提示
            user_message = self._build_analysis_prompt(context)
            
            # 每次分析使用独立的 thread_id，避免历史消息累积
            unique_thread_id = f"{self.session_id}_{self.workflow_id}"
            config = {
                "configurable": {"thread_id": unique_thread_id},
                "recursion_limit": settings.llm_recursion_limit
            }
            
            result = await self.agent.ainvoke(
                {
                    "messages": [
                        SystemMessage(content=self.system_prompt),
                        HumanMessage(content=user_message)
                    ]
                },
                config=config
            )
            
            # 提取LLM的分析和决策
            messages = result.get("messages", [])
            final_response = ""
            tool_calls_summary = []
            trades_executed = []
            
            # 分析消息历史，提取工具调用信息
            for msg in messages:
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        tool_name = tool_call.get('name', 'unknown')
                        tool_calls_summary.append(tool_name)
                elif hasattr(msg, 'content') and msg.content:
                    if isinstance(msg, AIMessage):
                        final_response = msg.content
            
            # 发送工具调用摘要
            if tool_calls_summary:
                tools_msg = "**LLM调用的工具:**\n" + "\n".join([f"🔧 {t}" for t in tool_calls_summary])
                await self.message_manager.send_message(tools_msg, "info")
            
            # 发送LLM的最终分析
            if final_response:
                await self.message_manager.send_message(
                    f"💭 LLM分析结果:\n\n{final_response}",
                    "info"
                )
            
            # 计算执行时间
            self.end_time = utc_now()
            execution_time = (self.end_time - self.start_time).total_seconds()
            
            # 保存到数据库
            await self._save_analysis_to_db(
                trigger=trigger,
                context=context,
                response=final_response,
                tool_calls=tool_calls_summary,
                execution_time=execution_time
            )
            
            # 记录到内存历史
            self.last_analysis_time = utc_now()
            self.analysis_history.append({
                "timestamp": self.last_analysis_time.isoformat(),
                "trigger": trigger,
                "response": final_response
            })
            # 限制内存历史大小
            if len(self.analysis_history) > self._max_analysis_history:
                self.analysis_history = self.analysis_history[-self._max_analysis_history:]
            
            # 更新历史摘要（类似 Cursor summarize）
            if final_response:
                await self._update_history_summary(final_response, tool_calls_summary)
            
            await self.send_workflow_complete_notification("LLM组合分析", execution_time)
            
            return {
                "success": True,
                "workflow_type": "llm_portfolio_agent",
                "workflow_id": self.workflow_id,
                "trigger": trigger,
                "llm_response": final_response,
                "tool_calls": tool_calls_summary,
                "execution_time": execution_time
            }
            
        except Exception as e:
            logger.error(f"LLM Portfolio Agent错误: {e}")
            # 保存错误到数据库
            await self._save_analysis_to_db(
                trigger=context.get("trigger", "unknown") if context else "unknown",
                context=context,
                response=None,
                tool_calls=[],
                execution_time=0,
                success=False,
                error_message=str(e)
            )
            return await self._handle_workflow_error(e, "LLM组合分析")
    
    async def _save_analysis_to_db(
        self,
        trigger: str,
        context: Optional[Dict],
        response: Optional[str],
        tool_calls: List[str],
        execution_time: float,
        success: bool = True,
        error_message: Optional[str] = None
    ):
        """保存分析结果到数据库"""
        if not self._db_available:
            return
        
        try:
            TradingRepository = get_trading_repository()
            if TradingRepository:
                await TradingRepository.save_analysis(
                    trigger=trigger,
                    workflow_id=self.workflow_id,
                    analysis_type="portfolio",
                    input_context=context,
                    output_response=response,
                    tool_calls=tool_calls,
                    execution_time_seconds=execution_time,
                    success=success,
                    error_message=error_message
                )
        except Exception as e:
            logger.warning(f"保存分析历史失败: {e}")
    
    async def _update_history_summary(self, current_analysis: str, tool_calls: List[str]):
        """
        更新历史摘要
        
        将当前分析结果整合到历史摘要中，保留关键信息，控制长度
        """
        try:
            # 构建摘要更新 prompt
            summary_prompt = f"""请将以下内容整合为简洁的投资历史摘要（限制500字以内）：

**之前的历史摘要：**
{self.history_summary if self.history_summary else "无（首次分析）"}

**本次分析：**
- 时间: {format_for_display(utc_now(), '%Y-%m-%d %H:%M %Z')}
- 使用工具: {', '.join(tool_calls) if tool_calls else '无'}
- 分析结论: {current_analysis[:1000] if current_analysis else '无'}

请生成更新后的摘要，重点保留：
1. 最近的交易决策及原因
2. 当前持仓策略和配置
3. 重要的市场观点和判断
4. 需要持续关注的风险/机会
5. 已安排的后续分析计划

只输出摘要内容，不要其他说明。"""

            response = await asyncio.to_thread(
                lambda: self.llm.invoke(summary_prompt).content
            )
            
            # 更新摘要
            self.history_summary = response.strip()[:2000]  # 限制长度
            logger.debug(f"历史摘要已更新: {len(self.history_summary)} 字符")
            
        except Exception as e:
            logger.warning(f"更新历史摘要失败: {e}")
    
    def _build_analysis_prompt(self, context: Dict[str, Any]) -> str:
        """构建分析提示，包含历史摘要"""
        
        # 历史上下文
        history_context = ""
        if self.history_summary:
            history_context = f"""
**历史上下文摘要（你之前的分析和决策）：**
{self.history_summary}

---
"""
        
        # 当前 context
        context_str = json.dumps(context, indent=2, ensure_ascii=False, default=str)
        
        prompt = f"""{history_context}请分析当前市场和组合状况。如有必要，可以调仓。

当前触发上下文: {context_str}"""
        
        logger.info(f"Analysis prompt length: {len(prompt)} chars")
        
        return prompt
