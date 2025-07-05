"""
Sequential workflow implementation for trading decisions.

This module implements a fixed-step workflow that follows a predefined sequence:
1. Data gathering (portfolio, market data, news)
2. Market analysis using LLM
3. Decision making using LLM
4. Trade execution

This represents the original workflow logic that was in trading_workflow.py
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from decimal import Decimal

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI
from langchain_deepseek import ChatDeepSeek
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain.tools import tool
from pydantic import BaseModel, Field

from config import settings
from src.agents.workflow_base import WorkflowBase
from src.apis.alpaca_api import AlpacaAPI
from src.apis.tiingo_api import TiingoAPI
from src.models.trading_models import (
    Order, Portfolio, TradingDecision, OrderSide, OrderType, TimeInForce, TradingAction
)


logger = logging.getLogger(__name__)


def create_llm_client():
    """
    Factory function to create LLM client based on provider setting.
    
    Returns:
        Chat client instance configured for the specified provider
    """
    if settings.llm_provider.lower() == "deepseek":
        return ChatDeepSeek(
            model=settings.deepseek_model,
            api_key=settings.deepseek_api_key,
            temperature=0.1
        )
    elif settings.llm_provider.lower() == "openai":
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.1
        )
    else:
        logger.warning(f"Unknown LLM provider: {settings.llm_provider}. Defaulting to OpenAI.")
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.1
        )


class TradingState(BaseModel):
    """State for the trading workflow"""
    messages: List[Dict[str, str]] = Field(default_factory=list)
    portfolio: Optional[Portfolio] = None
    market_data: Dict[str, Any] = Field(default_factory=dict)
    news: List[Dict[str, Any]] = Field(default_factory=list)
    decision: Optional[TradingDecision] = None
    context: Dict[str, Any] = Field(default_factory=dict)


class SequentialWorkflow(WorkflowBase):
    """
    Sequential workflow implementation using LangGraph.
    
    This workflow follows a fixed sequence of steps:
    1. Data gathering - collect portfolio, market data, and news
    2. Market analysis - LLM analyzes current market conditions
    3. Decision making - LLM makes trading decisions based on analysis
    4. Trade execution - execute approved trades
    
    This is the original workflow logic that provides a structured,
    predictable execution path.
    """
    
    def __init__(self, alpaca_api: AlpacaAPI, tiingo_api: TiingoAPI, telegram_bot=None):
        """Initialize the sequential workflow."""
        super().__init__(alpaca_api, tiingo_api, telegram_bot)
        self.llm = create_llm_client()
        self.workflow = None
        self._build_workflow()
    
    def _build_workflow(self):
        """Build the LangGraph workflow"""
        workflow = StateGraph(TradingState)
        
        # Add nodes
        workflow.add_node("gather_data", self._gather_data)
        workflow.add_node("analyze_market", self._analyze_market)
        workflow.add_node("make_decision", self._make_decision)
        workflow.add_node("execute_trades", self._execute_trades)
        
        # Add edges
        workflow.add_edge("gather_data", "analyze_market")
        workflow.add_edge("analyze_market", "make_decision")
        workflow.add_edge("make_decision", "execute_trades")
        workflow.add_edge("execute_trades", END)
        
        # Set entry point
        workflow.set_entry_point("gather_data")
        
        self.workflow = workflow.compile()
    
    async def run_workflow(self, initial_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute the sequential trading workflow.
        
        Args:
            initial_context: Optional initial context for the workflow
            
        Returns:
            Dictionary containing workflow results
        """
        try:
            self.workflow_id = self._generate_workflow_id()
            self.start_time = datetime.now()
            
            # Send start notification
            await self.send_workflow_start_notification("Sequential")
            
            # Initialize context
            context = initial_context or {}
            await self.initialize_workflow(context)
            
            # Create initial state
            initial_state = TradingState(
                context=context,
                messages=[{
                    "role": "system",
                    "content": "Starting trading workflow analysis"
                }]
            )
            
            # Execute the workflow
            result = await self.workflow.ainvoke(initial_state)
            
            # Calculate execution time
            self.end_time = datetime.now()
            execution_time = (self.end_time - self.start_time).total_seconds()
            
            # Send completion notification
            await self.send_workflow_complete_notification("Sequential", execution_time)
            
            return {
                "success": True,
                "decision": result.decision,
                "context": result.context,
                "execution_time": execution_time,
                "workflow_type": "sequential",
                "workflow_id": self.workflow_id
            }
            
        except Exception as e:
            logger.error(f"Error in sequential workflow: {e}")
            return await self._handle_workflow_error(e, "Workflow Execution")
    
    async def initialize_workflow(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Initialize the workflow with given context."""
        # Set default context values
        context.setdefault("trigger", "manual")
        context.setdefault("timestamp", datetime.now().isoformat())
        context.setdefault("workflow_type", "sequential")
        
        return self._update_context(context)
    
    async def gather_data(self) -> Dict[str, Any]:
        """Gather necessary data for trading decisions."""
        data = {
            "portfolio": await self.get_portfolio(),
            "market_data": await self.get_market_data(),
            "news": await self.get_news(),
            "market_open": await self.is_market_open()
        }
        return data
    
    async def make_decision(self, data: Dict[str, Any]) -> Optional[TradingDecision]:
        """Make a trading decision based on gathered data."""
        # This is implemented in the _make_decision method that's part of the LangGraph workflow
        # For the base class interface, we'll return None as this is handled by the workflow
        return None
    
    async def execute_decision(self, decision: Optional[TradingDecision]) -> Dict[str, Any]:
        """Execute the trading decision."""
        # This is implemented in the _execute_trades method that's part of the LangGraph workflow
        # For the base class interface, we'll return a basic response
        return {"success": False, "message": "Use workflow execution"}
    
    # LangGraph workflow methods
    
    async def _gather_data(self, state: TradingState) -> TradingState:
        """Gather market data and portfolio information"""
        try:
            await self.message_queue.send_message("**Starting Data Collection**\n\nGathering portfolio, market data, and news...", "info")
            
            # Get portfolio
            portfolio = await self.get_portfolio()
            state.portfolio = portfolio
            
            # Get market overview
            market_data = await self.get_market_data()
            state.market_data = market_data
            
            # Get recent news
            news = await self.get_news(limit=20)
            state.news = news
            
            # Send portfolio summary
            if portfolio:
                portfolio_msg = f"📊 **Portfolio Status**\n\n"
                portfolio_msg += f"• **Equity**: ${portfolio.equity:,.2f}\n"
                portfolio_msg += f"• **Cash**: ${portfolio.cash:,.2f}\n"
                portfolio_msg += f"• **Day P&L**: ${portfolio.day_pnl:,.2f}\n"
                portfolio_msg += f"• **Positions**: {len(portfolio.positions)}"
                
                await self.message_queue.send_portfolio_summary(portfolio_msg)
            
            # Send news summary
            if news:
                await self.message_queue.send_news_summary(news, limit=5)
            
            return state
            
        except Exception as e:
            logger.error(f"Error in data gathering: {e}")
            await self.message_queue.send_error(f"Error gathering data: {e}", "Data Collection")
            return state
    
    async def _analyze_market(self, state: TradingState) -> TradingState:
        """Analyze market conditions"""
        try:
            await self.message_queue.send_message("**Market Analysis**\n\nAnalyzing current market conditions...", "info")
            
            # Prepare analysis prompt
            analysis_prompt = self._create_analysis_prompt(state)
            
            # Get LLM analysis
            analysis_response = await self.llm.ainvoke([
                SystemMessage(content="You are an expert financial analyst. Provide a comprehensive market analysis."),
                HumanMessage(content=analysis_prompt)
            ])
            
            analysis_content = analysis_response.content
            
            # Store analysis in state
            state.context["market_analysis"] = analysis_content
            
            # Send analysis summary
            await self.message_queue.send_analysis_summary(analysis_content)
            
            return state
            
        except Exception as e:
            logger.error(f"Error in market analysis: {e}")
            await self.message_queue.send_error(f"Error in market analysis: {e}", "Market Analysis")
            return state
    
    async def _make_decision(self, state: TradingState) -> TradingState:
        """Make trading decision"""
        try:
            await self.message_queue.send_message("**Decision Making**\n\nGenerating trading decision...", "info")
            
            # Prepare decision prompt
            decision_prompt = self._create_decision_prompt(state)
            
            # Get LLM decision
            decision_response = await self.llm.ainvoke([
                SystemMessage(content="You are an expert trading advisor. Make conservative, well-reasoned trading decisions."),
                HumanMessage(content=decision_prompt)
            ])
            
            decision_content = decision_response.content
            
            # Parse decision
            decision = self._parse_decision(decision_content)
            state.decision = decision
            
            # Send decision summary
            await self.message_queue.send_decision_summary(decision)
            
            return state
            
        except Exception as e:
            logger.error(f"Error in decision making: {e}")
            await self.message_queue.send_error(f"Error in decision making: {e}", "Decision Making")
            return state
    
    async def _execute_trades(self, state: TradingState) -> TradingState:
        """Execute trading decisions"""
        try:
            decision = state.decision
            
            if not decision or decision.action == TradingAction.HOLD:
                await self.message_queue.send_message("**No Trade Execution**\n\nDecision is HOLD - no trades to execute.", "info")
                return state
            
            # Check if market is open
            if not await self.is_market_open():
                await self.message_queue.send_message("**Market Closed**\n\nMarket is closed - trades will be queued for next session.", "warning")
                return state
            
            await self.message_queue.send_message("**Executing Trades**\n\nProcessing trading orders...", "info")
            
            # Execute the trade
            if decision.action in [TradingAction.BUY, TradingAction.SELL]:
                order_side = OrderSide.BUY if decision.action == TradingAction.BUY else OrderSide.SELL
                
                order = Order(
                    symbol=decision.symbol,
                    side=order_side,
                    order_type=OrderType.MARKET,
                    quantity=decision.quantity or Decimal("1"),
                    time_in_force=TimeInForce.DAY
                )
                
                order_id = await self.alpaca_api.submit_order(order)
                
                if order_id:
                    await self.message_queue.send_trade_execution(
                        decision.symbol,
                        decision.action.value,
                        str(decision.quantity or 1),
                        order_id
                    )
                    state.context["order_id"] = order_id
                    state.context["trade_executed"] = True
                else:
                    await self.message_queue.send_error("Failed to submit order", "Trade Execution")
                    state.context["trade_executed"] = False
            
            await self.message_queue.send_workflow_complete()
            
            return state
            
        except Exception as e:
            logger.error(f"Error in trade execution: {e}")
            await self.message_queue.send_error(f"Error in trade execution: {e}", "Trade Execution")
            return state
    
    def _create_analysis_prompt(self, state: TradingState) -> str:
        """Create market analysis prompt"""
        portfolio = state.portfolio
        market_data = state.market_data
        news = state.news
        
        prompt = f"""
Analyze the current market conditions based on the following data:

PORTFOLIO INFORMATION:
- Current Equity: ${portfolio.equity:,.2f}
- Available Cash: ${portfolio.cash:,.2f}
- Day P&L: ${portfolio.day_pnl:,.2f}
- Total Positions: {len(portfolio.positions)}

MARKET DATA:
{json.dumps(market_data, indent=2)}

RECENT NEWS ({len(news)} articles):
"""
        
        for i, article in enumerate(news[:10], 1):
            prompt += f"\n{i}. {article['title']}"
            prompt += f"\n   Source: {article['source']}"
            prompt += f"\n   Description: {article['description'][:200]}..."
            if article['symbols']:
                prompt += f"\n   Related Symbols: {', '.join(article['symbols'][:3])}"
            prompt += "\n"
        
        prompt += """

Please analyze:
1. Overall market sentiment
2. Key trends affecting the market
3. Risk factors to consider
4. Opportunities in the current market
5. Sector-specific insights

Provide a comprehensive analysis that will inform trading decisions.
"""
        
        return prompt
    
    def _create_decision_prompt(self, state: TradingState) -> str:
        """Create decision-making prompt"""
        portfolio = state.portfolio
        analysis = state.context.get("market_analysis", "No analysis available")
        
        prompt = f"""
Based on the market analysis and current portfolio, make a trading decision.

CURRENT PORTFOLIO:
- Equity: ${portfolio.equity:,.2f}
- Cash: ${portfolio.cash:,.2f}
- Day P&L: ${portfolio.day_pnl:,.2f}
- Positions: {len(portfolio.positions)}

MARKET ANALYSIS:
{analysis}

TRADING PARAMETERS:
- Maximum position size: {settings.max_position_size}% of portfolio
- Stop loss: {settings.stop_loss_percentage}%
- Take profit: {settings.take_profit_percentage}%
- Risk tolerance: Conservative

Please provide trading decisions in the following format:
DECISION: [BUY/SELL/HOLD]
SYMBOL: [Stock symbol if BUY/SELL, or N/A if HOLD]
QUANTITY: [Number of shares if BUY/SELL, or N/A if HOLD]
REASONING: [Always provide detailed reasoning regardless of decision]
CONFIDENCE: [Confidence level 0.0-1.0]

Consider:
1. Current market conditions
2. Portfolio diversification
3. Risk management
4. News impact
5. Technical indicators from historical data

IMPORTANT: Only recommend trades if you have high confidence and clear reasoning.
Be conservative and prioritize capital preservation. When in doubt, choose HOLD.
"""
        
        return prompt
    
    def _parse_decision(self, decision_text: str) -> TradingDecision:
        """Parse LLM decision response into TradingDecision object"""
        try:
            # Parse the decision text
            decision_data = {}
            lines = decision_text.strip().split('\n')
            
            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    decision_data[key.strip().lower()] = value.strip()
            
            # Extract decision components
            action = decision_data.get('decision', 'HOLD').lower()
            
            # Handle symbol - for HOLD decisions, use placeholder since symbol is required
            symbol = decision_data.get('symbol', '')
            if symbol.upper() in ['N/A', 'NA', 'NONE', 'NULL'] or action.lower() == 'hold':
                symbol = ""  # Use empty string for HOLD decisions or N/A values
            
            # Handle quantity
            quantity = None
            if action.lower() in ['buy', 'sell']:
                quantity_str = decision_data.get('quantity', '0')
                if quantity_str.upper() not in ['N/A', 'NA', 'NONE', 'NULL']:
                    try:
                        quantity = Decimal(quantity_str)
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid quantity: {quantity_str}")
                        quantity = None
            
            # Handle reasoning
            reasoning = decision_data.get('reasoning', 'No reasoning provided')
            
            # Handle confidence
            confidence = 0.5  # Default confidence
            confidence_str = decision_data.get('confidence', '0.5')
            try:
                confidence = float(confidence_str)
                confidence = max(0.0, min(1.0, confidence))  # Clamp between 0 and 1
            except (ValueError, TypeError):
                logger.warning(f"Invalid confidence: {confidence_str}")
                confidence = 0.5
            
            return TradingDecision(
                action=TradingAction(action),
                symbol=symbol,
                quantity=quantity,
                reasoning=reasoning,
                confidence=Decimal(str(confidence))
            )
            
        except Exception as e:
            logger.error(f"Error parsing decision: {e}")
            return TradingDecision(
                action=TradingAction.HOLD,
                symbol="",
                reasoning="Error parsing decision from LLM response",
                confidence=Decimal('0.0')
            ) 