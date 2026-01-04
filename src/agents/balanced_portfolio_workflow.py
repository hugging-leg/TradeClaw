"""
均衡组合策略工作流 - Balanced Portfolio Workflow

该工作流实现以下策略：
1. 将投资组合分散到约5-6个股票（每个约18%仓位）
2. 根据以下条件触发重新平衡：
   - 每天定时（如每天9:30）
   - 仓位百分比偏离超过阈值（如±3%）
   - 突发新闻事件
   - 市场重大变动

设计原则：
- 保持组合平衡，降低单一股票风险
- 动态调整以应对市场变化
- 基于LLM分析做出明智的股票选择
"""

import asyncio
import json
from src.utils.logging_config import get_logger
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
from decimal import Decimal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from config import settings
from src.agents.workflow_base import WorkflowBase
from src.agents.workflow_factory import register_workflow
from src.utils.llm_utils import create_llm_client
from src.interfaces.broker_api import BrokerAPI
from src.interfaces.market_data_api import MarketDataAPI
from src.interfaces.news_api import NewsAPI
from src.messaging.message_manager import MessageManager
from src.models.trading_models import (
    Order, Portfolio, TradingDecision, OrderSide, OrderType, 
    TimeInForce, TradingAction, Position
)

logger = get_logger(__name__)




class PortfolioTarget(BaseModel):
    """目标组合配置"""
    symbol: str
    target_percentage: Decimal  # 目标百分比
    current_percentage: Decimal = Decimal('0')  # 当前百分比
    action: str = "HOLD"  # BUY, SELL, HOLD
    shares_to_trade: Decimal = Decimal('0')  # 需要交易的股数


class RebalanceDecision(BaseModel):
    """重新平衡决策"""
    should_rebalance: bool = False
    reason: str = ""
    targets: List[PortfolioTarget] = Field(default_factory=list)
    total_adjustments: int = 0


@register_workflow(
    "balanced_portfolio",
    description="均衡组合策略工作流",
    features=["自动再平衡", "仓位偏离检测", "LLM 选股"],
    best_for="分散化组合管理",
    deprecated=True  # 推荐使用 llm_portfolio
)
class BalancedPortfolioWorkflow(WorkflowBase):
    """
    均衡组合策略工作流
    
    核心策略：
    - 目标持仓数：5-6只股票
    - 每只股票目标仓位：约18% (100% / 5.5)
    - 重新平衡阈值：±3%（即15%-21%范围内为正常）
    """
    
    # 策略参数
    TARGET_POSITIONS = 5  # 目标持仓数量
    TARGET_PERCENTAGE = Decimal('18')  # 目标百分比 (约18%)
    REBALANCE_THRESHOLD = Decimal('3')  # 重新平衡阈值 (±3%)
    MIN_PERCENTAGE = TARGET_PERCENTAGE - REBALANCE_THRESHOLD  # 15%
    MAX_PERCENTAGE = TARGET_PERCENTAGE + REBALANCE_THRESHOLD  # 21%
    MAX_POSITIONS = 6  # 最大持仓数
    
    def __init__(self, 
                 broker_api: BrokerAPI = None,
                 market_data_api: MarketDataAPI = None,
                 news_api: NewsAPI = None,
                 message_manager: MessageManager = None):
        """初始化均衡组合工作流"""
        super().__init__(broker_api, market_data_api, news_api, message_manager)
        
        self.llm = create_llm_client()
        self.last_rebalance_time = None
        self.rebalance_history = []
        
        logger.info(f"初始化均衡组合工作流 - 目标: {self.TARGET_POSITIONS}只股票，每只约{self.TARGET_PERCENTAGE}%仓位")
    
    async def run_workflow(self, initial_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        执行均衡组合工作流
        
        Args:
            initial_context: 初始上下文，可包含：
                - trigger: 触发原因 (daily_rebalance, position_drift, breaking_news, market_event)
                - news_event: 新闻事件数据（如果是新闻触发）
                - market_event: 市场事件数据（如果是市场事件触发）
        
        Returns:
            包含重新平衡决策和执行结果的字典
        """
        try:
            self.workflow_id = self._generate_workflow_id()
            self.start_time = datetime.now()
            
            context = initial_context or {}
            trigger = context.get("trigger", "manual")
            
            await self.send_workflow_start_notification(f"均衡组合分析 ({trigger})")
            
            # 1. 收集数据
            await self.message_manager.send_message("📊 **收集组合数据**\n\n分析当前持仓和市场状况...", "info")
            data = await self.gather_data()
            
            if not data.get("portfolio"):
                raise Exception("无法获取组合数据")
            
            # 2. 分析是否需要重新平衡
            await self.message_manager.send_message("⚖️ **评估平衡状态**\n\n检查是否需要重新平衡...", "info")
            rebalance_decision = await self._should_rebalance(data, context)
            
            # 3. 如果需要，执行重新平衡
            execution_results = []
            if rebalance_decision.should_rebalance:
                await self.message_manager.send_message(
                    f"🔄 **开始重新平衡**\n\n原因: {rebalance_decision.reason}\n需要调整{rebalance_decision.total_adjustments}个仓位",
                    "warning"
                )
                execution_results = await self._execute_rebalance(rebalance_decision, data)
            else:
                await self.message_manager.send_message(
                    f"✅ **组合平衡良好**\n\n{rebalance_decision.reason}",
                    "success"
                )
            
            # 4. 更新历史记录
            self.last_rebalance_time = datetime.now()
            self.rebalance_history.append({
                "timestamp": self.last_rebalance_time.isoformat(),
                "trigger": trigger,
                "rebalanced": rebalance_decision.should_rebalance,
                "reason": rebalance_decision.reason,
                "executions": len(execution_results)
            })
            
            # 计算执行时间
            self.end_time = datetime.now()
            execution_time = (self.end_time - self.start_time).total_seconds()
            
            await self.send_workflow_complete_notification("均衡组合分析", execution_time)
            
            return {
                "success": True,
                "workflow_type": "balanced_portfolio",
                "workflow_id": self.workflow_id,
                "trigger": trigger,
                "rebalance_decision": rebalance_decision.dict(),
                "execution_results": execution_results,
                "execution_time": execution_time
            }
            
        except Exception as e:
            logger.error(f"均衡组合工作流错误: {e}")
            return await self._handle_workflow_error(e, "均衡组合执行")

    async def gather_data(self) -> Dict[str, Any]:
        """收集必要数据"""
        portfolio = await self.get_portfolio()
        market_data = await self.get_market_data()
        news = await self.get_news(limit=20)
        market_open = await self.is_market_open()
        
        # 分析当前持仓情况
        position_analysis = self._analyze_current_positions(portfolio)
        
        return {
            "portfolio": portfolio,
            "market_data": market_data,
            "news": news,
            "market_open": market_open,
            "position_analysis": position_analysis
        }
    
    def _analyze_current_positions(self, portfolio: Portfolio) -> Dict[str, Any]:
        """分析当前持仓分布"""
        if not portfolio or portfolio.equity <= 0:
            return {
                "total_positions": 0,
                "positions": [],
                "is_balanced": False,
                "imbalance_score": 0
            }
        
        positions_data = []
        imbalance_score = Decimal('0')
        
        for position in portfolio.positions:
            if position.quantity == 0:
                continue
            
            percentage = (position.market_value / portfolio.equity) * 100
            deviation = abs(percentage - self.TARGET_PERCENTAGE)
            is_balanced = self.MIN_PERCENTAGE <= percentage <= self.MAX_PERCENTAGE
            
            positions_data.append({
                "symbol": position.symbol,
                "quantity": position.quantity,
                "market_value": position.market_value,
                "percentage": percentage,
                "target_percentage": self.TARGET_PERCENTAGE,
                "deviation": deviation,
                "is_balanced": is_balanced,
                "unrealized_pnl": position.unrealized_pnl,
                "unrealized_pnl_pct": position.unrealized_pnl_percentage
            })
            
            imbalance_score += deviation
        
        # 排序：按市值从大到小
        positions_data.sort(key=lambda x: x["market_value"], reverse=True)
        
        return {
            "total_positions": len(positions_data),
            "positions": positions_data,
            "is_balanced": imbalance_score < (self.REBALANCE_THRESHOLD * len(positions_data)),
            "imbalance_score": float(imbalance_score),
            "too_many_positions": len(positions_data) > self.MAX_POSITIONS
        }
    
    async def _should_rebalance(self, data: Dict[str, Any], context: Dict[str, Any]) -> RebalanceDecision:
        """
        判断是否需要重新平衡
        
        重新平衡条件：
        1. 定时触发（每日）- 检查是否偏离
        2. 仓位偏离超过阈值
        3. 突发新闻
        4. 市场重大事件
        """
        trigger = context.get("trigger", "manual")
        portfolio = data["portfolio"]
        position_analysis = data["position_analysis"]
        
        # 1. 检查持仓数量
        if position_analysis["total_positions"] == 0:
            return RebalanceDecision(
                should_rebalance=True,
                reason="组合为空，需要建立初始持仓",
                total_adjustments=self.TARGET_POSITIONS
            )
        
        # 2. 检查持仓数量是否过多
        if position_analysis["too_many_positions"]:
            return RebalanceDecision(
                should_rebalance=True,
                reason=f"持仓数量过多（{position_analysis['total_positions']}>{self.MAX_POSITIONS}），需要减仓",
                total_adjustments=position_analysis["total_positions"] - self.TARGET_POSITIONS
            )
        
        # 3. 检查仓位是否失衡
        if not position_analysis["is_balanced"]:
            imbalance_score = position_analysis["imbalance_score"]
            return RebalanceDecision(
                should_rebalance=True,
                reason=f"仓位失衡（偏离度: {imbalance_score:.1f}%），需要重新平衡",
                total_adjustments=sum(1 for p in position_analysis["positions"] if not p["is_balanced"])
            )
        
        # 4. 检查是否有突发新闻触发
        if trigger == "breaking_news":
            news_event = context.get("news_event")
            if news_event:
                return RebalanceDecision(
                    should_rebalance=True,
                    reason=f"突发新闻触发: {news_event.get('title', 'N/A')[:50]}...",
                    total_adjustments=1
                )
        
        # 5. 检查是否有市场重大事件
        if trigger == "market_event":
            market_event = context.get("market_event")
            if market_event:
                return RebalanceDecision(
                    should_rebalance=True,
                    reason=f"市场事件触发: {market_event.get('description', 'N/A')[:50]}...",
                    total_adjustments=1
                )
        
        # 不需要重新平衡
        return RebalanceDecision(
            should_rebalance=False,
            reason=f"组合平衡良好：{position_analysis['total_positions']}只股票，平均偏离度{position_analysis['imbalance_score']:.1f}%"
        )
    
    async def _execute_rebalance(self, decision: RebalanceDecision, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        执行重新平衡操作
        
        步骤：
        1. 使用LLM分析市场和新闻，选择目标股票
        2. 计算每只股票的目标仓位
        3. 生成交易指令
        4. 执行交易
        """
        portfolio = data["portfolio"]
        
        # 1. 让LLM选择目标股票
        target_symbols = await self._select_target_stocks(data, self.TARGET_POSITIONS)
        
        if not target_symbols:
            await self.message_manager.send_error("LLM未能选择目标股票", "选股失败")
            return []
        
        # 2. 计算目标仓位
        targets = await self._calculate_targets(portfolio, target_symbols)
        
        # 3. 发送重新平衡计划
        await self._send_rebalance_plan(targets)
        
        # 4. 检查市场是否开放
        if not data.get("market_open", False):
            await self.message_manager.send_message("⚠️ **市场未开放**\n\n交易将在市场开放时执行", "warning")
            return []
        
        # 5. 执行交易
        execution_results = await self._execute_trades(targets, portfolio)
        
        return execution_results
    
    async def _select_target_stocks(self, data: Dict[str, Any], count: int) -> List[str]:
        """使用LLM选择目标股票"""
        try:
            portfolio = data["portfolio"]
            market_data = data["market_data"]
            news = data["news"]
            position_analysis = data["position_analysis"]
            
            # 构建选股提示
            prompt = self._create_stock_selection_prompt(
                portfolio, market_data, news, position_analysis, count
            )
            
            # 调用LLM
            response = await self.llm.ainvoke([
                SystemMessage(content="你是一位专业的投资组合经理，擅长基于市场分析选择优质股票。"),
                HumanMessage(content=prompt)
            ])
            
            # 解析LLM响应
            symbols = self._parse_stock_selection(response.content)
            
            logger.info(f"LLM选择的目标股票: {symbols}")
            return symbols[:count]
            
        except Exception as e:
            logger.error(f"选择目标股票失败: {e}")
            # 降级方案：保留当前持仓
            return [p["symbol"] for p in data["position_analysis"]["positions"][:count]]
    
    def _create_stock_selection_prompt(self, portfolio: Portfolio, market_data: Dict, 
                                      news: List[Dict], position_analysis: Dict, count: int) -> str:
        """创建股票选择提示"""
        prompt = f"""
请基于以下信息，为均衡投资组合选择{count}只优质美股：

## 当前组合状况
- 总资产: ${portfolio.equity:,.2f}
- 可用现金: ${portfolio.cash:,.2f}
- 当前持仓: {position_analysis['total_positions']}只

当前持仓详情：
"""
        for pos in position_analysis["positions"]:
            prompt += f"- {pos['symbol']}: {pos['percentage']:.1f}% (目标{pos['target_percentage']:.0f}%), "
            prompt += f"盈亏: {pos['unrealized_pnl_pct']:.2f}%\n"
        
        prompt += f"\n## 市场概况\n{json.dumps(market_data, indent=2, ensure_ascii=False)}\n"
        
        prompt += f"\n## 最新新闻 (前10条)\n"
        for i, article in enumerate(news[:10], 1):
            prompt += f"{i}. {article['title']}\n"
            if article.get('symbols'):
                prompt += f"   相关: {', '.join(article['symbols'][:3])}\n"
        
        prompt += f"""

## 选股要求
1. 选择{count}只股票，构建均衡组合
2. 考虑行业分散化，降低集中风险
3. 优先考虑基本面良好、成长性强的公司
4. 关注最新新闻对股票的影响
5. 可以保留当前表现良好的持仓
6. 避免选择高风险或波动过大的股票

## 输出格式
严格按照以下格式输出（每行一个股票代码）：
SYMBOL: AAPL
SYMBOL: MSFT
SYMBOL: GOOGL
...

同时简要说明选择理由（不超过2行）：
REASONING: [简要说明整体选股逻辑]
"""
        return prompt
    
    def _parse_stock_selection(self, response: str) -> List[str]:
        """解析LLM的选股响应"""
        symbols = []
        lines = response.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if line.startswith('SYMBOL:'):
                symbol = line.split(':', 1)[1].strip().upper()
                # 验证股票代码格式
                if symbol and symbol.isalnum() and len(symbol) <= 5:
                    symbols.append(symbol)
        
        return symbols
    
    async def _calculate_targets(self, portfolio: Portfolio, target_symbols: List[str]) -> List[PortfolioTarget]:
        """计算目标仓位"""
        targets = []
        target_value_per_stock = portfolio.equity / len(target_symbols)
        
        # 获取当前持仓
        current_positions = {pos.symbol: pos for pos in portfolio.positions if pos.quantity != 0}
        
        for symbol in target_symbols:
            current_position = current_positions.get(symbol)
            current_value = current_position.market_value if current_position else Decimal('0')
            current_pct = (current_value / portfolio.equity * 100) if portfolio.equity > 0 else Decimal('0')
            
            target_pct = self.TARGET_PERCENTAGE
            value_diff = target_value_per_stock - current_value
            
            # 获取当前价格来计算需要交易的股数
            price_data = await self.market_data_api.get_latest_price(symbol)
            if not price_data:
                logger.warning(f"无法获取{symbol}的价格，跳过")
                continue
            
            current_price = Decimal(str(price_data.get('close', 0)))
            if current_price <= 0:
                logger.warning(f"{symbol}价格无效，跳过")
                continue
            
            shares_to_trade = value_diff / current_price
            
            # 确定操作类型
            action = "HOLD"
            if abs(shares_to_trade) >= 1:  # 至少交易1股
                action = "BUY" if shares_to_trade > 0 else "SELL"
                shares_to_trade = abs(shares_to_trade).quantize(Decimal('1'))  # 取整
            else:
                shares_to_trade = Decimal('0')
            
            targets.append(PortfolioTarget(
                symbol=symbol,
                target_percentage=target_pct,
                current_percentage=current_pct,
                action=action,
                shares_to_trade=shares_to_trade
            ))
        
        # 处理需要清仓的持仓
        for symbol, position in current_positions.items():
            if symbol not in target_symbols and position.quantity > 0:
                targets.append(PortfolioTarget(
                    symbol=symbol,
                    target_percentage=Decimal('0'),
                    current_percentage=(position.market_value / portfolio.equity * 100),
                    action="SELL",
                    shares_to_trade=abs(position.quantity)
                ))
        
        return targets
    
    async def _send_rebalance_plan(self, targets: List[PortfolioTarget]):
        """发送重新平衡计划"""
        message = "📋 **重新平衡计划**\n\n"
        
        buy_orders = [t for t in targets if t.action == "BUY"]
        sell_orders = [t for t in targets if t.action == "SELL"]
        hold_orders = [t for t in targets if t.action == "HOLD"]
        
        if buy_orders:
            message += "**买入订单:**\n"
            for target in buy_orders:
                message += f"- {target.symbol}: 买入{target.shares_to_trade}股 "
                message += f"(目标{target.target_percentage}%)\n"
        
        if sell_orders:
            message += "\n**卖出订单:**\n"
            for target in sell_orders:
                message += f"- {target.symbol}: 卖出{target.shares_to_trade}股 "
                message += f"(当前{target.current_percentage:.1f}%)\n"
        
        if hold_orders:
            message += "\n**保持不变:**\n"
            for target in hold_orders:
                message += f"- {target.symbol}: {target.current_percentage:.1f}% (平衡)\n"
        
        await self.message_manager.send_message(message, "info")
    
    async def _execute_trades(self, targets: List[PortfolioTarget], portfolio: Portfolio) -> List[Dict[str, Any]]:
        """执行交易"""
        results = []
        
        # 先执行卖出订单（释放资金）
        sell_targets = [t for t in targets if t.action == "SELL"]
        for target in sell_targets:
            result = await self._execute_single_trade(target, "SELL")
            results.append(result)
            if result["success"]:
                await asyncio.sleep(1)  # 避免下单过快
        
        # 再执行买入订单
        buy_targets = [t for t in targets if t.action == "BUY"]
        for target in buy_targets:
            result = await self._execute_single_trade(target, "BUY")
            results.append(result)
            if result["success"]:
                await asyncio.sleep(1)
        
        # 发送执行摘要
        await self._send_execution_summary(results)
        
        return results
    
    async def _execute_single_trade(self, target: PortfolioTarget, action: str) -> Dict[str, Any]:
        """执行单个交易"""
        try:
            order = Order(
                symbol=target.symbol,
                side=OrderSide.BUY if action == "BUY" else OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=target.shares_to_trade,
                time_in_force=TimeInForce.DAY
            )
            
            order_id = await self.broker_api.submit_order(order)
            
            if order_id:
                logger.info(f"订单已提交: {action} {target.shares_to_trade} {target.symbol}")
                return {
                    "success": True,
                    "symbol": target.symbol,
                    "action": action,
                    "quantity": float(target.shares_to_trade),
                    "order_id": order_id
                }
            else:
                logger.error(f"订单提交失败: {action} {target.symbol}")
                return {
                    "success": False,
                    "symbol": target.symbol,
                    "action": action,
                    "error": "订单提交失败"
                }
                
        except Exception as e:
            logger.error(f"执行交易错误 {target.symbol}: {e}")
            return {
                "success": False,
                "symbol": target.symbol,
                "action": action,
                "error": str(e)
            }
    
    async def _send_execution_summary(self, results: List[Dict[str, Any]]):
        """发送执行摘要"""
        success_count = sum(1 for r in results if r["success"])
        failed_count = len(results) - success_count
        
        message = f"✅ **交易执行完成**\n\n"
        message += f"成功: {success_count} | 失败: {failed_count}\n\n"
        
        if failed_count > 0:
            message += "**失败订单:**\n"
            for result in results:
                if not result["success"]:
                    message += f"- {result['symbol']} {result['action']}: {result.get('error', 'Unknown')}\n"
        
        await self.message_manager.send_message(message, "info")
