"""
Tool calling workflow implementation for trading decisions.

This module implements a dynamic workflow that uses LLM tool calling capabilities.
Instead of following a fixed sequence, the LLM decides which tools to call and when,
based on the current context and analysis needs.

This represents a more flexible and intelligent approach to trading workflows.
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta
from decimal import Decimal

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langchain_deepseek import ChatDeepSeek
from langchain_core.tools import tool
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, Field

from config import settings
from src.agents.workflow_base import WorkflowBase
from src.apis.alpaca_api import AlpacaAPI
from src.apis.tiingo_api import TiingoAPI
from src.models.trading_models import (
    Order, Portfolio, TradingDecision, OrderSide, OrderType, TimeInForce, TradingAction
)


logger = logging.getLogger(__name__)


class ToolCallingWorkflow(WorkflowBase):
    """
    Tool calling workflow implementation using LangChain tool binding.
    
    This workflow uses LLM tool calling capabilities to dynamically decide
    which tools to use and when. The LLM can call tools to:
    - Get portfolio information
    - Fetch market data
    - Get news
    - Check market status
    - Make trading decisions
    
    This provides a more flexible and intelligent approach compared to
    fixed sequential workflows.
    """
    
    def __init__(self, alpaca_api: AlpacaAPI, tiingo_api: TiingoAPI, telegram_bot=None):
        """Initialize the tool calling workflow."""
        super().__init__(alpaca_api, tiingo_api, telegram_bot)
        self.llm = self._create_llm_client()
        self.tools = self._create_tools()
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        self.max_iterations = 10  # Prevent infinite loops
        
    def _create_llm_client(self):
        """Create LLM client based on provider setting."""
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
    
    def _create_tools(self):
        """Create tools for the LLM to use."""
        
        @tool
        async def get_portfolio_info() -> str:
            """Get current portfolio information including positions and P&L"""
            try:
                portfolio = await self.get_portfolio()
                if not portfolio:
                    return "Error: Unable to retrieve portfolio information"
                
                info = f"""
Current Portfolio:
- Equity: ${portfolio.equity:,.2f}
- Cash: ${portfolio.cash:,.2f}
- Market Value: ${portfolio.market_value:,.2f}
- Day P&L: ${portfolio.day_pnl:,.2f}
- Total P&L: ${portfolio.total_pnl:,.2f}
- Buying Power: ${portfolio.buying_power:,.2f}
- Number of Positions: {len(portfolio.positions)}

Current Positions:
"""
                
                for position in portfolio.positions:
                    info += f"- {position.symbol}: {position.quantity} shares, "
                    info += f"Market Value: ${position.market_value:,.2f}, "
                    info += f"P&L: ${position.unrealized_pnl:,.2f} ({position.unrealized_pnl_percentage:.2%})\n"
                
                return info
                
            except Exception as e:
                return f"Error getting portfolio info: {e}"
        
        @tool
        async def get_market_data(symbol: str = "SPY") -> str:
            """Get current market data for a symbol or market overview"""
            try:
                if symbol.upper() == "SPY" or symbol.upper() == "OVERVIEW":
                    # Get market overview
                    market_data = await self.get_market_data()
                    return f"Market Overview:\n{json.dumps(market_data, indent=2)}"
                else:
                    # Get specific symbol data
                    market_data = await self.alpaca_api.get_market_data(symbol)
                    return f"""
Market Data for {symbol}:
- Current Price: ${market_data.price:.2f}
- Bid: ${market_data.bid:.2f}
- Ask: ${market_data.ask:.2f}
- Volume: {market_data.volume:,}
- Last Updated: {market_data.timestamp}
"""
            except Exception as e:
                return f"Error getting market data for {symbol}: {e}"
        
        @tool
        async def get_news(symbol: str = None, limit: int = 10) -> str:
            """Get recent news for a symbol or general market news"""
            try:
                if symbol:
                    news_items = await self.tiingo_api.get_symbol_news(symbol, limit=limit)
                else:
                    news_items = await self.tiingo_api.get_news(limit=limit)
                
                if not news_items:
                    return "No recent news found"
                
                news_info = f"Recent News ({len(news_items)} articles):\n\n"
                
                for i, news in enumerate(news_items[:limit], 1):
                    news_info += f"{i}. {news.title}\n"
                    news_info += f"   Source: {news.source}\n"
                    news_info += f"   Published: {news.published_at}\n"
                    news_info += f"   Summary: {news.description[:200]}...\n"
                    if news.symbols:
                        news_info += f"   Related Symbols: {', '.join(news.symbols)}\n"
                    news_info += "\n"
                
                return news_info
                
            except Exception as e:
                return f"Error getting news: {e}"
        
        @tool
        async def check_market_status() -> str:
            """Check if market is open and get trading session info"""
            try:
                is_open = await self.is_market_open()
                current_time = datetime.now()
                
                status = f"""
Market Status:
- Current Time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}
- Market Open: {'Yes' if is_open else 'No'}
- Session: {'Regular Trading' if is_open else 'Market Closed'}
"""
                
                if not is_open:
                    status += "\nNote: Orders placed now will be queued for the next trading session."
                
                return status
                
            except Exception as e:
                return f"Error checking market status: {e}"
        
        @tool
        async def get_active_orders() -> str:
            """Get all active orders"""
            try:
                orders = await self.alpaca_api.get_orders(status="open")
                
                if not orders:
                    return "No active orders"
                
                orders_info = f"Active Orders ({len(orders)}):\n\n"
                
                for order in orders:
                    price_str = f"${order.price:.2f}" if order.price else "Market"
                    orders_info += f"- {order.symbol} {order.side.value.upper()} {order.quantity} "
                    orders_info += f"@ {price_str}"
                    orders_info += f" (Status: {order.status.value.upper()})\n"
                
                return orders_info
                
            except Exception as e:
                return f"Error getting active orders: {e}"
        
        @tool
        async def make_trading_decision(analysis_summary: str) -> str:
            """Make a trading decision based on analysis summary"""
            try:
                # This tool helps the LLM structure its final decision
                decision_prompt = f"""
Based on the following analysis, make a trading decision:

{analysis_summary}

TRADING PARAMETERS:
- Maximum position size: {settings.max_position_size}% of portfolio
- Stop loss: {settings.stop_loss_percentage}%
- Take profit: {settings.take_profit_percentage}%
- Risk tolerance: Conservative

Please provide your decision in the following format:
DECISION: [BUY/SELL/HOLD]
SYMBOL: [Stock symbol if BUY/SELL, or N/A if HOLD]
QUANTITY: [Number of shares if BUY/SELL, or N/A if HOLD]
REASONING: [Detailed reasoning for the decision]
CONFIDENCE: [Confidence level 0.0-1.0]

IMPORTANT: Only recommend trades if you have high confidence and clear reasoning.
Be conservative and prioritize capital preservation.
"""
                
                return decision_prompt
                
            except Exception as e:
                return f"Error in decision making: {e}"
        
        return [
            get_portfolio_info,
            get_market_data,
            get_news,
            check_market_status,
            get_active_orders,
            make_trading_decision
        ]
    
    async def run_workflow(self, initial_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute the tool calling workflow.
        
        Args:
            initial_context: Optional initial context for the workflow
            
        Returns:
            Dictionary containing workflow results
        """
        try:
            self.workflow_id = self._generate_workflow_id()
            self.start_time = datetime.now()
            
            # Send start notification
            await self.send_workflow_start_notification("Tool Calling")
            
            # Initialize context
            context = initial_context or {}
            await self.initialize_workflow(context)
            
            # Execute the interactive workflow
            result = await self._execute_interactive_workflow(context)
            
            # Calculate execution time
            self.end_time = datetime.now()
            execution_time = (self.end_time - self.start_time).total_seconds()
            
            # Send completion notification
            await self.send_workflow_complete_notification("Tool Calling", execution_time)
            
            return {
                "success": True,
                "decision": result.get("decision"),
                "context": result.get("context", {}),
                "execution_time": execution_time,
                "workflow_type": "tool_calling",
                "workflow_id": self.workflow_id,
                "tool_calls": result.get("tool_calls", [])
            }
            
        except Exception as e:
            logger.error(f"Error in tool calling workflow: {e}")
            return await self._handle_workflow_error(e, "Workflow Execution")
    
    async def _execute_interactive_workflow(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the interactive tool calling workflow."""
        
        # Initial system message
        system_message = SystemMessage(content="""
You are an expert trading AI assistant with access to tools to gather information and make trading decisions.

Your goal is to:
1. Gather relevant information about the current market conditions
2. Analyze the portfolio and market data
3. Make informed trading decisions
4. Provide clear reasoning for your recommendations

You have access to the following tools:
- get_portfolio_info: Get current portfolio status
- get_market_data: Get market data for specific symbols or overview
- get_news: Get recent market news
- check_market_status: Check if market is open
- get_active_orders: Get current open orders
- make_trading_decision: Structure your final trading decision

Start by gathering the necessary information, then provide your analysis and decision.
Be conservative and prioritize capital preservation.
""")
        
        # Initial user message
        user_message = HumanMessage(content=f"""
Please analyze the current market conditions and make a trading decision.

Context: {json.dumps(context, indent=2)}

Please start by gathering the information you need to make an informed decision.
""")
        
        messages = [system_message, user_message]
        tool_calls = []
        decision = None
        
        await self.message_queue.send_message("🔧 **Starting Tool-Based Analysis**\n\nLetting AI decide which tools to use...", "info")
        
        # Interactive loop
        for iteration in range(self.max_iterations):
            try:
                # Get LLM response
                response = await self.llm_with_tools.ainvoke(messages)
                
                # Check if LLM wants to use tools
                if response.tool_calls:
                    await self.message_queue.send_message(f"🔧 **Tool Calls** (Iteration {iteration + 1})\n\nExecuting {len(response.tool_calls)} tool call(s)...", "info")
                    
                    # Add AI message to conversation
                    messages.append(response)
                    
                    # Execute tool calls
                    for tool_call in response.tool_calls:
                        tool_name = tool_call["name"]
                        tool_args = tool_call["args"]
                        tool_call_id = tool_call["id"]
                        
                        logger.info(f"Executing tool: {tool_name} with args: {tool_args}")
                        
                        # Find and execute the tool
                        tool_result = await self._execute_tool(tool_name, tool_args)
                        
                        # Add tool result to conversation
                        tool_message = ToolMessage(
                            content=tool_result,
                            tool_call_id=tool_call_id
                        )
                        messages.append(tool_message)
                        
                        # Track tool calls
                        tool_calls.append({
                            "name": tool_name,
                            "args": tool_args,
                            "result": tool_result[:500] + "..." if len(tool_result) > 500 else tool_result
                        })
                        
                        # Send tool execution notification
                        await self.message_queue.send_message(f"✅ **Tool Executed**: {tool_name}\n\nGathered data successfully", "info")
                else:
                    # No more tools to call, LLM has provided final analysis
                    final_response = response.content
                    
                    # Try to parse a decision from the response
                    decision = self._parse_decision(final_response)
                    
                    # Send analysis summary
                    await self.message_queue.send_analysis_summary(final_response)
                    
                    # Send decision summary
                    await self.message_queue.send_decision_summary(decision)
                    
                    break
                    
            except Exception as e:
                logger.error(f"Error in iteration {iteration}: {e}")
                await self.message_queue.send_error(f"Error in iteration {iteration}: {e}", "Tool Execution")
                break
        
        # Execute the decision if trading is enabled
        execution_result = await self.execute_decision(decision)
        
        return {
            "decision": decision,
            "context": context,
            "tool_calls": tool_calls,
            "execution_result": execution_result,
            "iterations": iteration + 1
        }
    
    async def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """Execute a specific tool by name."""
        for tool in self.tools:
            if tool.name == tool_name:
                try:
                    # Call the tool with arguments
                    result = await tool.ainvoke(tool_args)
                    return str(result)
                except Exception as e:
                    return f"Error executing {tool_name}: {e}"
        
        return f"Tool {tool_name} not found"
    
    # Implementation of abstract methods
    
    async def initialize_workflow(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Initialize the workflow with given context."""
        context.setdefault("trigger", "manual")
        context.setdefault("timestamp", datetime.now().isoformat())
        context.setdefault("workflow_type", "tool_calling")
        
        return self._update_context(context)
    
    async def gather_data(self) -> Dict[str, Any]:
        """Gather necessary data for trading decisions."""
        # In tool calling workflow, data gathering is handled by the LLM
        # This method is part of the abstract interface
        return {
            "method": "tool_calling",
            "note": "Data gathering is handled dynamically by LLM tool calls"
        }
    
    async def make_decision(self, data: Dict[str, Any]) -> Optional[TradingDecision]:
        """Make a trading decision based on gathered data."""
        # In tool calling workflow, decision making is handled by the LLM
        # This method is part of the abstract interface
        return None
    
    async def execute_decision(self, decision: Optional[TradingDecision]) -> Dict[str, Any]:
        """Execute the trading decision."""
        try:
            if not decision or decision.action == TradingAction.HOLD:
                await self.message_queue.send_message("**No Trade Execution**\n\nDecision is HOLD - no trades to execute.", "info")
                return {"success": True, "message": "No trade executed (HOLD decision)"}
            
            # Check if market is open
            if not await self.is_market_open():
                await self.message_queue.send_message("**Market Closed**\n\nMarket is closed - trades will be queued for next session.", "warning")
                return {"success": True, "message": "Trade queued - market closed"}
            
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
                    
                    await self.message_queue.send_workflow_complete()
                    
                    return {
                        "success": True,
                        "order_id": order_id,
                        "message": f"Order executed: {decision.action.value} {decision.symbol}"
                    }
                else:
                    await self.message_queue.send_error("Failed to submit order", "Trade Execution")
                    return {"success": False, "message": "Failed to submit order"}
            
            return {"success": False, "message": "Invalid trading action"}
            
        except Exception as e:
            logger.error(f"Error in trade execution: {e}")
            await self.message_queue.send_error(f"Error in trade execution: {e}", "Trade Execution")
            return {"success": False, "message": f"Error: {e}"}
    
    def _parse_decision(self, decision_text: str) -> Optional[TradingDecision]:
        """Parse LLM decision response into TradingDecision object."""
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
            
            # Handle symbol
            symbol = decision_data.get('symbol', '')
            if symbol.upper() in ['N/A', 'NA', 'NONE', 'NULL'] or action.lower() == 'hold':
                symbol = ""
            
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
                confidence = max(0.0, min(1.0, confidence))
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