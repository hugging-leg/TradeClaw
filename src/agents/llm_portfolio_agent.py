"""
LLM驱动的投资组合管理Agent

设计理念：
- 完全由LLM决策，无硬编码规则
- 将rebalance、获取数据等作为tools提供给LLM
- LLM基于市场数据、新闻、仓位等信息自主分析
- LLM决定何时、如何调整组合
- LLM可以自主安排下一次分析时间

Tools提供给LLM：
1. get_portfolio_status - 获取当前组合状态
2. get_market_data - 获取市场数据
3. get_latest_news - 获取最新新闻
4. get_position_analysis - 分析持仓分布
5. get_latest_price - 获取个股最新价格
6. get_historical_prices - 获取历史K线数据（自定义时间框架和数量）
7. rebalance_portfolio - 执行组合重新平衡
8. schedule_next_analysis - 安排下一次分析时间（LLM自主调度）
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Annotated
from datetime import datetime, timedelta
from decimal import Decimal
import pytz

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI
from langchain_deepseek import ChatDeepSeek
from langchain.tools import tool
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

from config import settings
from src.agents.workflow_base import WorkflowBase
from src.interfaces.broker_api import BrokerAPI
from src.interfaces.market_data_api import MarketDataAPI
from src.interfaces.news_api import NewsAPI
from src.messaging.message_manager import MessageManager
from src.events.event_system import event_system
from src.models.trading_models import (
    Order, Portfolio, TradingDecision, OrderSide, OrderType, 
    TimeInForce, Position
)

logger = logging.getLogger(__name__)


def create_llm_client():
    """创建LLM客户端"""
    if settings.llm_provider.lower() == "deepseek":
        return ChatDeepSeek(
            model=settings.deepseek_model,
            api_key=settings.deepseek_api_key,
            temperature=0.1
        )
    else:
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.1
        )


class RebalanceRequest(BaseModel):
    """重新平衡请求"""
    target_allocations: Dict[str, float] = Field(
        description="目标配置，格式: {'AAPL': 20.0, 'MSFT': 20.0, ...}，百分比总和应为100"
    )
    reason: str = Field(description="重新平衡的原因")


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
                 message_manager: MessageManager = None):
        """初始化LLM Portfolio Agent"""
        super().__init__(broker_api, market_data_api, news_api, message_manager)
        
        self.llm = create_llm_client()
        self.event_system = event_system  # 用于LLM自主调度
        
        # 创建tools
        self.tools = self._create_tools()
        
        # 创建ReAct agent（不需要state_modifier参数）
        self.agent = create_react_agent(
            self.llm,
            self.tools
        )
        
        # 保存system prompt以便后续使用
        self.system_prompt = self._get_system_prompt()
        
        # Agent状态
        self.analysis_history = []
        self.last_analysis_time = None
        
        logger.info("LLM Portfolio Agent 已初始化（完全由LLM驱动，支持自主调度）")
    
    def _get_system_prompt(self) -> str:
        """获取系统提示"""
        return f"""你是一位专业的私募投资组合经理，负责管理美股以及ETF投资组合，争取达到sharpe ratio 3以上。

## 你的职责
1. 持续分析市场状况、新闻事件和组合配置
2. 基于分析自主决定是否需要调整组合
3. 决定目标仓位配置
4. 执行组合重新平衡

## 可用工具
除了你本身自带的工具，你还有以下工具可以使用：
- get_portfolio_status: 获取当前组合状态（持仓、市值、盈亏等）
- get_market_data: 获取市场概况（主要指数）
- get_latest_news: 获取最新市场新闻
- get_position_analysis: 分析当前持仓分布
- get_latest_price: 获取个股最新价格
- get_historical_prices: 获取个股历史K线数据（可选时间框架：1Day/1Hour/15Min/5Min等）
- rebalance_portfolio: 执行组合重新平衡（需要指定目标配置）
- schedule_next_analysis: 安排下一次分析时间（你可以自主决定何时再次分析）

## 当前任务
分析当前市场和组合状况，决定是否需要调整。如果需要调整，使用rebalance_portfolio工具执行。

## 重要提示
- 你可以持有多只股票/ETF，你完全自主决策，根据市场情况灵活调整配置，做出理性、明智、专业的决策
- 注意分仓，避免单票梭哈，只做主升不做调整
- 杠杆ETF要考虑磨损，非特殊情况不要长期持有，但合适的使用可以带来高收益
- 重点关注美联储的消息，科技公司的消息，以及重大新闻事件
- 重点关注科技公司、金融公司和黄金，也可以思考如何对冲风险
- **如果rebalance_portfolio返回market_open=false，说明市场休市，立即停止所有工具调用，只返回"市场休市，分析暂停"**

## 自主调度
- 分析完成后，如有需要，你可以使用schedule_next_analysis安排下一次分析时间
- 例如：预期有重要新闻（如FOMC会议、财报发布），可以提前安排分析，市场波动剧烈，可以安排更频繁的检查
- 你可以根据市场情况和自己的判断，灵活安排下一次分析的时间

## 现金仓位管理
- **重要**: 调用rebalance_portfolio时，只指定股票/ETF的目标百分比，不要包含"CASH"或"现金"，因为可能会出现混淆
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
        async def get_latest_news(limit: int = 20) -> str:
            """
            获取最新市场新闻
            
            Args:
                limit: 新闻数量，默认20条
            """
            try:
                await self.message_manager.send_message(f"📰 正在获取最新{limit}条新闻...", "info")
                news = await self.get_news(limit=limit)
                news_list = []
                for item in news[:limit]:
                    news_list.append({
                        "title": item["title"],
                        "source": item["source"],
                        "published_at": item["published_at"],
                        "symbols": item.get("symbols", [])
                    })
                
                await self.message_manager.send_message(f"✅ 已获取{len(news_list)}条新闻", "info")
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
                timeframe: 时间框架，可选值："1Day", "1Hour", "30Min", "15Min", "5Min", "1Min", "1Week", "1Month"
                limit: 返回的K线数量，默认100条
            
            Returns:
                历史价格数据的JSON字符串，包含时间戳、ohlcv
            """
            try:
                # 参数验证
                if limit < 1 or limit > 1000:
                    return "错误: limit必须在1-1000之间"
                
                valid_timeframes = ["1Min", "5Min", "15Min", "30Min", "1Hour", "1Day", "1Week", "1Month"]
                if timeframe not in valid_timeframes:
                    return f"错误: timeframe必须是以下之一: {', '.join(valid_timeframes)}"
                
                await self.message_manager.send_message(
                    f"📈 正在获取 {symbol} 历史数据 ({limit}条, {timeframe})...",
                    "info"
                )
                
                # 使用broker API获取市场数据
                prices = await self.broker_api.get_market_data(
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=limit
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
                                   - 只需指定股票/ETF的百分比，不要包含现金
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
                priority: 优先级（0-10，数字越小优先级越高），默认0为普通优先级
            
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
                await self.event_system.schedule_next_analysis(
                    scheduled_time=scheduled_time,
                    reason=reason,
                    priority=priority,
                    context={"scheduled_by": "llm_agent"}
                )
                
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
        
        # 最小调整阈值：市值差异小于$100或比例差异小于2%则不调整
        MIN_VALUE_THRESHOLD = Decimal('100')
        MIN_PCT_THRESHOLD = Decimal('2.0')
        
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
            self.start_time = datetime.now()
            
            context = initial_context or {}
            trigger = context.get("trigger", "manual")
            
            await self.send_workflow_start_notification(f"LLM组合分析 ({trigger})")
            
            # 构建初始提示
            user_message = self._build_analysis_prompt(context)
            
            # 通知开始分析
            await self.message_manager.send_message(
                "🤖 **LLM Agent 开始分析**\n\n"
                f"触发: {trigger}\n"
                "LLM将自主调用工具进行分析...",
                "info"
            )
            
            result = await self.agent.ainvoke({
                "messages": [
                    SystemMessage(content=self.system_prompt),
                    HumanMessage(content=user_message)
                ]
            })
            
            # 提取LLM的分析和决策
            messages = result.get("messages", [])
            final_response = ""
            tool_calls_summary = []
            
            # 分析消息历史，提取工具调用信息
            for msg in messages:
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        tool_name = tool_call.get('name', 'unknown')
                        tool_calls_summary.append(f"🔧 {tool_name}")
                elif hasattr(msg, 'content') and msg.content:
                    if isinstance(msg, AIMessage):
                        final_response = msg.content
            
            # 发送工具调用摘要
            if tool_calls_summary:
                tools_msg = "**LLM调用的工具:**\n" + "\n".join(tool_calls_summary)
                await self.message_manager.send_message(tools_msg, "info")
            
            # 发送LLM的最终分析（不转义，直接发送原始文本）
            if final_response:
                await self.message_manager.send_message(
                    f"💭 LLM分析结果:\n\n{final_response}",
                    "info"
                )
            
            # 记录分析历史
            self.last_analysis_time = datetime.now()
            self.analysis_history.append({
                "timestamp": self.last_analysis_time.isoformat(),
                "trigger": trigger,
                "response": final_response
            })
            
            # 计算执行时间
            self.end_time = datetime.now()
            execution_time = (self.end_time - self.start_time).total_seconds()
            
            await self.send_workflow_complete_notification("LLM组合分析", execution_time)
            
            return {
                "success": True,
                "workflow_type": "llm_portfolio_agent",
                "workflow_id": self.workflow_id,
                "trigger": trigger,
                "llm_response": final_response,
                "execution_time": execution_time
            }
            
        except Exception as e:
            logger.error(f"LLM Portfolio Agent错误: {e}")
            return await self._handle_workflow_error(e, "LLM组合分析")
    
    def _build_analysis_prompt(self, context: Dict[str, Any]) -> str:
        """构建分析提示"""
        trigger = context.get("trigger", "manual")
        
        prompt = f"## 当前任务\n\n触发原因: {trigger}\n\n"
        
        if trigger == "daily_rebalance":
            prompt += "这是每日定时分析。请全面分析当前组合状况，判断是否需要调整。\n"
        elif trigger == "breaking_news":
            news_event = context.get("news_event", {})
            prompt += f"检测到突发新闻: {news_event.get('title', 'N/A')}\n"
            prompt += "请分析这条新闻对组合的影响，决定是否需要调整。\n"
        elif trigger == "price_change":
            market_event = context.get("market_event", {})
            prompt += f"检测到价格变动: {market_event.get('symbol', 'N/A')} "
            prompt += f"变化{market_event.get('change_percentage', 0):.1f}%\n"
            prompt += "请分析是否需要调整组合。\n"
        else:
            prompt += "请分析当前市场和组合状况。\n"
        
        return prompt
    
    async def initialize_workflow(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """初始化workflow"""
        context.setdefault("trigger", "manual")
        context.setdefault("timestamp", datetime.now().isoformat())
        context.setdefault("workflow_type", "llm_portfolio_agent")
        return self._update_context(context)
    
    async def gather_data(self) -> Dict[str, Any]:
        """收集数据（LLM会通过tools自己获取）"""
        # TODO: Deprecate this method, current align with abstract class
        return {}
    
    async def make_decision(self, data: Dict[str, Any]) -> Optional[TradingDecision]:
        """LLM自己做决策"""
        return None
    
    async def execute_decision(self, decision: Optional[TradingDecision]) -> Dict[str, Any]:
        """LLM通过tools执行"""
        return {"success": False, "message": "Use run_workflow instead"}
    
    def get_workflow_type(self) -> str:
        """获取workflow类型"""
        return "llm_portfolio_agent"
