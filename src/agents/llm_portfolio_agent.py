"""
LLM驱动的投资组合管理Agent

设计理念：
- 完全由LLM决策，无硬编码规则
- 将rebalance、获取数据等作为tools提供给LLM
- LLM基于市场数据、新闻、仓位等信息自主分析
- LLM决定何时、如何调整组合

Tools提供给LLM：
1. get_portfolio_status - 获取当前组合状态
2. get_market_data - 获取市场数据
3. get_latest_news - 获取最新新闻
4. get_position_analysis - 分析持仓分布
5. rebalance_portfolio - 执行组合重新平衡
6. get_stock_info - 获取个股详细信息
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Annotated
from datetime import datetime, timedelta
from decimal import Decimal

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
        
        logger.info("LLM Portfolio Agent 已初始化（完全由LLM驱动）")
    
    def _get_system_prompt(self) -> str:
        """获取系统提示"""
        return f"""你是一位专业的私募投资组合经理，负责管理美股以及ETF投资组合。

## 你的职责
1. 持续分析市场状况、新闻事件和组合配置
2. 基于分析自主决定是否需要调整组合
3. 决定目标仓位配置（不需要遵循固定规则）
4. 执行组合重新平衡

## 可用工具
除了你本身，你还有以下工具可以使用：
- get_portfolio_status: 获取当前组合状态（持仓、市值、盈亏等）
- get_market_data: 获取市场概况（主要指数）
- get_latest_news: 获取最新市场新闻
- get_position_analysis: 分析当前持仓分布
- get_stock_info: 获取个股详细信息
- rebalance_portfolio: 执行组合重新平衡（需要指定目标配置）

## 决策原则
1. **自主分析**: 你可以自由决定何时调整组合，无需遵循固定规则
2. **风险分散**: 考虑适当分散风险，但具体配置由你决定
3. **响应市场**: 关注重大新闻、市场变化，及时调整策略
4. **理性决策**: 基于数据和分析，避免情绪化决策
5. **成本意识**: 避免过度频繁交易

## 当前任务
分析当前市场和组合状况，决定是否需要调整。如果需要调整，使用rebalance_portfolio工具执行。

## 重要提示
- 你完全自主决策
- 注意分仓，避免单票梭哈
- 只做主升不做调整
- 杠杆ETF要考虑磨损，非特殊情况不要长期持有
- 你可以持有2-10只股票/ETF，具体数量由你决定
- 你可以根据市场情况灵活调整配置
- 充分利用工具获取信息，做出明智决策
"""
    
    def _create_tools(self) -> List:
        """创建提供给LLM的工具"""
        
        @tool
        async def get_portfolio_status() -> str:
            """获取当前投资组合状态，包括总资产、现金、持仓等信息"""
            try:
                portfolio = await self.get_portfolio()
                if not portfolio:
                    return "无法获取组合信息"
                
                positions_info = []
                for pos in portfolio.positions:
                    if pos.quantity != 0:
                        positions_info.append({
                            "symbol": pos.symbol,
                            "quantity": float(pos.quantity),
                            "market_value": float(pos.market_value),
                            "unrealized_pnl": float(pos.unrealized_pnl),
                            "unrealized_pnl_pct": float(pos.unrealized_pnl_percentage)
                        })
                
                result = {
                    "total_equity": float(portfolio.equity),
                    "cash": float(portfolio.cash),
                    "market_value": float(portfolio.market_value),
                    "day_pnl": float(portfolio.day_pnl),
                    "total_positions": len(positions_info),
                    "positions": positions_info
                }
                
                return json.dumps(result, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"获取组合状态失败: {e}")
                return f"错误: {str(e)}"
        
        @tool
        async def get_market_data() -> str:
            """获取市场概况，包括主要指数（SPY, QQQ等）的最新数据"""
            try:
                market_data = await self.get_market_data()
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
                news = await self.get_news(limit=limit)
                news_list = []
                for item in news[:limit]:
                    news_list.append({
                        "title": item["title"],
                        "source": item["source"],
                        "published_at": item["published_at"],
                        "symbols": item.get("symbols", [])
                    })
                
                return json.dumps(news_list, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"获取新闻失败: {e}")
                return f"错误: {str(e)}"
        
        @tool
        async def get_position_analysis() -> str:
            """分析当前持仓分布，包括各仓位占比、集中度等"""
            try:
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
                
                return json.dumps(analysis, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"分析持仓失败: {e}")
                return f"错误: {str(e)}"
        
        @tool
        async def get_stock_info(symbol: str) -> str:
            """
            获取个股详细信息
            
            Args:
                symbol: 股票代码，如 AAPL
            """
            try:
                # 获取最新价格
                price_data = await self.market_data_api.get_latest_price(symbol)
                
                # 获取股票信息
                info = await self.market_data_api.get_symbol_info(symbol)
                
                result = {
                    "symbol": symbol,
                    "price_data": price_data if price_data else "无法获取",
                    "info": info if info else "无法获取"
                }
                
                return json.dumps(result, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"获取股票信息失败 {symbol}: {e}")
                return f"错误: {str(e)}"
        
        @tool
        async def rebalance_portfolio(
            target_allocations: Dict[str, float],
            reason: str
        ) -> str:
            """
            执行组合重新平衡
            
            Args:
                target_allocations: 目标配置，例如 {"AAPL": 25.0, "MSFT": 25.0, "GOOGL": 25.0, "AMZN": 25.0}
                                   百分比总和应接近100
                reason: 重新平衡的原因说明
            
            Returns:
                执行结果
            """
            try:
                # 验证配置
                total_pct = sum(target_allocations.values())
                if abs(total_pct - 100) > 5:
                    return f"错误: 目标配置总和为{total_pct}%，应接近100%"
                
                # 获取当前组合
                portfolio = await self.get_portfolio()
                if not portfolio:
                    return "错误: 无法获取组合信息"
                
                # 通知开始重新平衡
                await self.message_manager.send_message(
                    f"🔄 **LLM发起组合重新平衡**\n\n"
                    f"原因: {reason}\n\n"
                    f"目标配置:\n" + 
                    "\n".join([f"- {sym}: {pct:.1f}%" for sym, pct in target_allocations.items()]),
                    "warning"
                )
                
                # 计算需要执行的交易
                trades = await self._calculate_rebalance_trades(
                    portfolio, 
                    target_allocations
                )
                
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
                }, indent=2, ensure_ascii=False)
                
            except Exception as e:
                logger.error(f"重新平衡失败: {e}")
                error_msg = f"错误: {str(e)}"
                await self.message_manager.send_error(error_msg, "重新平衡")
                return error_msg
        
        return [
            get_portfolio_status,
            get_market_data,
            get_latest_news,
            get_position_analysis,
            get_stock_info,
            rebalance_portfolio
        ]
    
    async def _calculate_rebalance_trades(
        self, 
        portfolio: Portfolio, 
        target_allocations: Dict[str, float]
    ) -> List[Dict[str, Any]]:
        """计算需要执行的交易"""
        trades = []
        
        # 获取当前持仓
        current_positions = {pos.symbol: pos for pos in portfolio.positions if pos.quantity != 0}
        
        # 计算目标市值
        for symbol, target_pct in target_allocations.items():
            target_value = portfolio.equity * Decimal(str(target_pct / 100))
            
            current_position = current_positions.get(symbol)
            current_value = current_position.market_value if current_position else Decimal('0')
            
            value_diff = target_value - current_value
            
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
                trades.append({
                    "symbol": symbol,
                    "action": action,
                    "shares": abs(int(shares_to_trade)),
                    "price": float(current_price),
                    "target_pct": target_pct
                })
        
        # 清仓不在目标配置中的股票
        for symbol, position in current_positions.items():
            if symbol not in target_allocations and position.quantity > 0:
                trades.append({
                    "symbol": symbol,
                    "action": "SELL",
                    "shares": abs(int(position.quantity)),
                    "price": 0,  # 市价
                    "target_pct": 0
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
                    "order_id": order_id
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
            
            # 让LLM agent运行（它会自主使用tools）
            # 在messages中加入SystemMessage和HumanMessage
            result = await self.agent.ainvoke({
                "messages": [
                    SystemMessage(content=self.system_prompt),
                    HumanMessage(content=user_message)
                ]
            })
            
            # 提取LLM的分析和决策
            messages = result.get("messages", [])
            final_response = ""
            if messages:
                final_response = messages[-1].content if hasattr(messages[-1], 'content') else str(messages[-1])
            
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
