"""
Tool calling workflow implementation for trading decisions.

This module implements a dynamic workflow that uses LLM tool calling capabilities.
Instead of following a fixed sequence, the LLM decides which tools to call and when,
based on the current context and analysis needs.

This represents a more flexible and intelligent approach to trading workflows.
"""

import asyncio
import json
from src.utils.logging_config import get_logger
from typing import Dict, List, Any, Optional, Union, Callable
from datetime import datetime, timedelta
from decimal import Decimal

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_core.runnables import RunnableLambda
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
    Order, Portfolio, TradingDecision, OrderSide, OrderType, TimeInForce, TradingAction,
    Position, MarketData, NewsItem
)


logger = get_logger(__name__)


@register_workflow(
    "tool_calling",
    description="Dynamic tool-calling workflow",
    features=["动态工具选择", "LLM 驱动决策", "灵活执行顺序"],
    best_for="自适应智能交易分析"
)
class ToolCallingWorkflow(WorkflowBase):
    """
    Advanced AI trading workflow using tool-calling LLM capabilities.
    
    This workflow leverages LLM tool-calling functionality to make more
    sophisticated trading decisions based on multiple data sources
    and complex analysis patterns.
    """
    
    def __init__(self, 
                 broker_api: BrokerAPI = None,
                 market_data_api: MarketDataAPI = None,
                 news_api: NewsAPI = None,
                 message_manager: MessageManager = None):
        """
        Initialize the tool-calling workflow.
        
        Args:
            broker_api: Broker API for trading operations
            market_data_api: Market data API for market information
            news_api: News API for news data
            message_manager: Message manager for notifications
        """
        super().__init__(broker_api, market_data_api, news_api, message_manager)
        
        # Tool-calling specific configuration
        self.max_function_calls = getattr(settings, 'max_function_calls', 10)
        self.analysis_timeout = getattr(settings, 'analysis_timeout_seconds', 300)
        self.confidence_threshold = getattr(settings, 'confidence_threshold', 0.7)
        
        # Initialize LLM first
        self.llm = self._create_llm_client()
        
        # Available tools for LLM
        self.available_tools = self._register_tools()
        self.tools = self.available_tools
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        
        logger.info("Initialized ToolCallingWorkflow with advanced AI capabilities")
        self.max_iterations = 64  # Prevent infinite loops
        
    def _create_llm_client(self):
        """Create LLM client."""
        return create_llm_client()
    
    def _register_tools(self):
        """Register and return available tools for the LLM."""
        try:
            tools = self._create_tools()
            logger.info(f"Registered {len(tools)} tools for LLM")
            return tools
        except Exception as e:
            logger.error(f"Error registering tools: {e}")
            return []
    
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
                if symbol.upper() == "OVERVIEW":
                    # Get market overview
                    market_data = await self.get_market_data()
                    return f"Market Overview:\n{json.dumps(market_data, indent=2)}"
                else:
                    # Get specific symbol data using market_data_api
                    quote = await self.market_data_api.get_latest_price(symbol)
                    if not quote:
                        return f"No market data available for {symbol}"
                    return f"""
Market Data for {symbol}:
- Close: ${quote.get('close', 0):.2f}
- Open: ${quote.get('open', 0):.2f}
- High: ${quote.get('high', 0):.2f}
- Low: ${quote.get('low', 0):.2f}
- Volume: {quote.get('volume', 0):,}
- Date: {quote.get('date', 'N/A')}
"""
            except Exception as e:
                return f"Error getting market data for {symbol}: {e}"
        
        @tool
        async def get_news(symbol: str = None, limit: int = 10) -> str:
            """Get recent news for a symbol or general market news"""
            try:
                if symbol:
                    news_items = await self.news_api.get_symbol_news(symbol, limit=limit)
                else:
                    news_items = await self.news_api.get_market_overview_news(limit=limit)
                
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
                orders = await self.broker_api.get_orders(status="open")
                
                if not orders:
                    return "No active orders"
                
                orders_info = f"Active Orders ({len(orders)}):\n\n"
                
                for order in orders:
                    price_str = f"${order.price:.2f}" if order.price else "Market"
                    orders_info += f"- {order.symbol} {order.side.value.upper()} {order.quantity} "
                    orders_info += f"@ {price_str}"
                    orders_info += f" (Status: {order.status.value.upper()})\n"
                ro
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
        
        @tool
        async def finish_analysis(analysis_summary: str, final_decision: str) -> str:
            """Finish the trading analysis with final decision and reasoning"""
            try:
                # This tool signals that the analysis is complete
                return f"""
ANALYSIS COMPLETE

Final Summary: {analysis_summary}

Decision: {final_decision}

The trading analysis has been completed. The system will now process the final decision.
"""
            except Exception as e:
                return f"Error finishing analysis: {e}"
        
        return [
            get_portfolio_info,
            get_market_data,
            get_news,
            check_market_status,
            get_active_orders,
            make_trading_decision,
            finish_analysis
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
            
            # Initialize context
            context = initial_context or {}
            context.setdefault("trigger", "manual")
            context.setdefault("timestamp", datetime.now().isoformat())
            context.setdefault("workflow_type", "tool_calling")
            
            # Execute the interactive workflow (this will send its own start notification)
            result = await self._execute_interactive_workflow(context)
            
            # Calculate execution time
            self.end_time = datetime.now()
            execution_time = (self.end_time - self.start_time).total_seconds()
            
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
        """Execute interactive workflow with dynamic tool calling."""
        
        # Send enhanced workflow start notification
        await self.message_manager.send_message(f"""
🤖 **AI Trading Analysis Engine**

🎯 **Workflow**: Tool Calling AI
📊 **Available Tools**: {len(self.tools)}
⚙️ **Max Iterations**: {self.max_iterations}
⏱️ **Analysis Timeout**: {self.analysis_timeout}s

🧠 The AI will intelligently select and use tools to analyze market conditions...
        """.strip(), "info")
        
        # Initialize messages and tracking
        messages = [
            SystemMessage(content=self._get_system_prompt()),
            HumanMessage(content=self._get_initial_prompt(context))
        ]
        
        tool_calls = []
        decision = None
        analysis_complete = False  # Flag to track when analysis is complete
        
        # Start interactive loop
        for iteration in range(self.max_iterations):
            try:
                # Send iteration notification
                await self.message_manager.send_message(f"🔄 **Analysis Step {iteration + 1}**", "info")
                
                # Get LLM response with cancellation handling
                try:
                    response = await asyncio.wait_for(
                        self.llm_with_tools.ainvoke(messages),
                        timeout=120  # 2 minutes timeout per LLM call
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"LLM call timed out in iteration {iteration}")
                    await self.message_manager.send_error("AI analysis timed out", "Tool Execution")
                    break
                except asyncio.CancelledError:
                    logger.info(f"LLM call cancelled in iteration {iteration}")
                    # Return partial results if available
                    return {
                        "decision": decision,
                        "context": context,
                        "tool_calls": tool_calls,
                        "execution_result": {"success": False, "message": "Cancelled during LLM call"},
                        "iterations": iteration,
                        "cancelled": True
                    }
                
                # Check if LLM wants to use tools
                if response.tool_calls:
                    
                    # Add AI message to conversation
                    messages.append(response)
                    
                    # Execute tool calls
                    for tool_call in response.tool_calls:
                        tool_name = tool_call["name"]
                        tool_args = tool_call["args"]
                        tool_call_id = tool_call["id"]
                        
                        logger.info(f"Executing tool: {tool_name} with args: {tool_args}")
                        
                        # Find and execute the tool with cancellation handling
                        try:
                            tool_result = await asyncio.wait_for(
                                self._execute_tool(tool_name, tool_args),
                                timeout=30  # 30 seconds timeout per tool call
                            )
                        except asyncio.TimeoutError:
                            tool_result = f"Error executing {tool_name}: Tool call timed out"
                        except asyncio.CancelledError:
                            logger.info(f"Tool call {tool_name} cancelled")
                            return {
                                "decision": decision,
                                "context": context,
                                "tool_calls": tool_calls,
                                "execution_result": {"success": False, "message": "Cancelled during tool execution"},
                                "iterations": iteration,
                                "cancelled": True
                            }
                        
                        # Check if tool execution was successful
                        tool_success = not tool_result.startswith("Error executing")
                        
                        # Send simple tool execution notification (without results)
                        status_emoji = "✅" if tool_success else "❌"
                        await self.message_manager.send_message(f"   {status_emoji} `{tool_name}` executed", "info")
                        
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
                            "result": tool_result[:500] + "..." if len(tool_result) > 500 else tool_result,
                            "success": tool_success
                        })
                        
                        # Check if finish_analysis was called
                        if tool_name == "finish_analysis":
                            # Extract decision from the finish_analysis arguments
                            final_decision = tool_args.get("final_decision", "")
                            analysis_summary = tool_args.get("analysis_summary", "")
                            
                            # Parse the decision from the arguments
                            decision = self._parse_decision(final_decision)
                            
                            # Send only reasoning summary (no separate decision summary to avoid redundancy)
                            await self.message_manager.send_reasoning_summary(
                                reasoning_text=f"Analysis Summary: {analysis_summary}\n\nFinal Decision: {final_decision}",
                                tool_calls_count=len(tool_calls)
                            )
                            
                            # Mark analysis as complete
                            analysis_complete = True
                            logger.info("Analysis marked as complete via finish_analysis tool")
                            break  # Break out of tool execution loop
                    
                    # Check if analysis is complete after tool execution
                    if analysis_complete:
                        logger.info("Breaking out of main analysis loop - finish_analysis was called")
                        break  # Break out of main iteration loop
                        
                else:
                    # No tools called, prompt LLM to continue or finish
                    await self.message_manager.send_message("🤔 **Awaiting Decision**\n\nAI is thinking... Please use tools to gather more information or call `finish_analysis` when ready.", "info")
                    
                    # Add a message to guide the LLM
                    guidance_message = HumanMessage(content="""
Please continue your analysis by either:
1. Using available tools to gather more information, OR
2. Calling the 'finish_analysis' tool with your final analysis summary and decision

Remember: You must explicitly call 'finish_analysis' to complete the analysis.
""")
                    messages.append(guidance_message)
                    
            except asyncio.CancelledError:
                logger.info(f"Interactive workflow cancelled in iteration {iteration}")
                return {
                    "decision": decision,
                    "context": context,
                    "tool_calls": tool_calls,
                    "execution_result": {"success": False, "message": "Workflow cancelled"},
                    "iterations": iteration,
                    "cancelled": True
                }
            except Exception as e:
                logger.error(f"Error in iteration {iteration}: {e}")
                await self.message_manager.send_error(f"Error in analysis step {iteration}: {e}", "Tool Execution")
                break
        
        # Check if we reached max iterations without calling finish_analysis
        if decision is None and not analysis_complete:
            await self.message_manager.send_message("⚠️ **Analysis Timeout**\n\nMaximum iterations reached without explicit finish. Defaulting to HOLD decision.", "warning")
            # Create a default HOLD decision
            decision = TradingDecision(
                action=TradingAction.HOLD,
                symbol="",
                reasoning="Analysis reached maximum iterations without explicit completion via finish_analysis tool",
                confidence=Decimal('0.0')
            )
        # Note: Removed redundant "Analysis Complete" message as it's already sent in the workflow summary
        
        # Execute the decision if trading is enabled
        try:
            execution_result = await asyncio.wait_for(
                self.execute_decision(decision),
                timeout=60  # 1 minute timeout for trade execution
            )
        except asyncio.TimeoutError:
            execution_result = {"success": False, "message": "Trade execution timed out"}
        except asyncio.CancelledError:
            logger.info("Trade execution cancelled")
            execution_result = {"success": False, "message": "Trade execution cancelled"}
        
        # Send comprehensive workflow completion summary (only this one notification)
        await self._send_workflow_summary(tool_calls, decision, execution_result, iteration + 1)
        
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
    
    def _get_system_prompt(self) -> str:
        """Get the system prompt for the LLM."""
        return """
You are an expert trading AI assistant with access to various tools to gather market information and make trading decisions on stocks and ETFs.

Your goal is to:
1. Gather relevant information about current market conditions using available tools
2. Analyze portfolio and market data comprehensively  
3. Make well-informed trading decisions
4. Provide clear reasoning for your recommendations

IMPORTANT WORKFLOW RULES:
- Use the available tools to collect data and information
- Continue using tools until you have sufficient information for a decision
- When you are ready to conclude your analysis, you MUST call the 'finish_analysis' tool
- The 'finish_analysis' tool requires two parameters:
  * analysis_summary: A comprehensive summary of your analysis
  * final_decision: Your trading decision in the format "DECISION: [BUY/SELL/HOLD], SYMBOL: [symbol], QUANTITY: [amount], REASONING: [reasoning], CONFIDENCE: [0.0-1.0]"

Do not attempt to end the analysis without calling 'finish_analysis'. The system will only process your decision when you explicitly use this tool.

Try to find alpha and identify profitable opportunities.
"""
    
    def _get_initial_prompt(self, context: Dict[str, Any]) -> str:
        """Get the initial user prompt for the LLM."""
        return f"""
Please analyze the current market conditions and make a trading decision.

Context: {json.dumps(context, indent=2)}

Please start by gathering the information you need to make an informed decision.
"""

    async def execute_decision(self, decision: Optional[TradingDecision]) -> Dict[str, Any]:
        """Execute the trading decision."""
        try:
            if not decision or decision.action == TradingAction.HOLD:
                await self.message_manager.send_message("**No Trade Execution**\n\nDecision is HOLD - no trades to execute.", "info")
                return {"success": True, "message": "No trade executed (HOLD decision)"}
            
            # Check if market is open
            if not await self.is_market_open():
                await self.message_manager.send_message("**Market Closed**\n\nMarket is closed - trades will be queued for next session.", "warning")
                return {"success": True, "message": "Trade queued - market closed"}
            
            await self.message_manager.send_message("**Executing Trades**\n\nProcessing trading orders...", "info")
            
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
                
                order_id = await self.broker_api.submit_order(order)
                
                if order_id:
                    await self.message_manager.send_trade_execution(
                        decision.symbol,
                        decision.action.value,
                        str(decision.quantity or 1),
                        order_id
                    )
                    
                    await self.message_manager.send_workflow_complete()
                    
                    return {
                        "success": True,
                        "order_id": order_id,
                        "message": f"Order executed: {decision.action.value} {decision.symbol}"
                    }
                else:
                    await self.message_manager.send_error("Failed to submit order", "Trade Execution")
                    return {"success": False, "message": "Failed to submit order"}
            
            return {"success": False, "message": "Invalid trading action"}
            
        except Exception as e:
            logger.error(f"Error in trade execution: {e}")
            await self.message_manager.send_error(f"Error in trade execution: {e}", "Trade Execution")
            return {"success": False, "message": f"Error: {e}"}
    
    def _parse_decision(self, decision_text: str) -> Optional[TradingDecision]:
        """Parse LLM decision response into TradingDecision object."""
        try:
            # Parse the decision text - handle both formats:
            # Format 1: "DECISION: BUY\nSYMBOL: SPY\n..."  (newline separated)
            # Format 2: "BUY, SYMBOL: SPY, QUANTITY: 100, ..." (comma separated)
            decision_data = {}
            text = decision_text.strip()
            
            # Check if it's comma-separated format
            if ', ' in text and not '\n' in text:
                # Handle comma-separated format: "HOLD, SYMBOL: N/A, QUANTITY: N/A, ..."
                parts = text.split(', ')
                
                # First part might be just the decision without key
                first_part = parts[0].strip()
                if ':' not in first_part and first_part.upper() in ['BUY', 'SELL', 'HOLD']:
                    decision_data['decision'] = first_part
                    parts = parts[1:]  # Skip first part
                else:
                    # First part has key:value format
                    if ':' in first_part:
                        key, value = first_part.split(':', 1)
                        decision_data[key.strip().lower()] = value.strip()
                        parts = parts[1:]
                
                # Parse remaining parts
                for part in parts:
                    if ':' in part:
                        key, value = part.split(':', 1)
                        decision_data[key.strip().lower()] = value.strip()
            else:
                # Handle newline-separated format: "DECISION: BUY\nSYMBOL: SPY\n..."
                lines = text.split('\n')
                for line in lines:
                    if ':' in line:
                        key, value = line.split(':', 1)
                        decision_data[key.strip().lower()] = value.strip()
            
            # Extract decision components
            action_raw = decision_data.get('decision', 'HOLD').strip()
            action_upper = action_raw.upper()  # Use uppercase for validation
            action = action_raw.lower()  # Convert to lowercase for TradingAction enum
            
            # Validate action
            if action_upper not in ['BUY', 'SELL', 'HOLD']:
                logger.warning(f"Invalid action '{action_raw}', defaulting to HOLD")
                action = 'hold'
            elif action_upper == 'HOLD':
                action = 'hold'
            elif action_upper == 'BUY':
                action = 'buy'
            elif action_upper == 'SELL':
                action = 'sell'
            
            # Handle symbol
            symbol = decision_data.get('symbol', '')
            if symbol.upper() in ['N/A', 'NA', 'NONE', 'NULL'] or action == 'hold':
                symbol = ""
            
            # Handle quantity
            quantity = None
            if action in ['buy', 'sell']:
                quantity_str = decision_data.get('quantity', '0')
                if quantity_str.upper() not in ['N/A', 'NA', 'NONE', 'NULL']:
                    try:
                        # Extract numeric part if there are extra characters
                        import re
                        numeric_match = re.search(r'(\d+(?:\.\d+)?)', quantity_str)
                        if numeric_match:
                            quantity = Decimal(numeric_match.group(1))
                        else:
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
                # Extract numeric part if there are extra characters
                import re
                numeric_match = re.search(r'(\d+(?:\.\d+)?)', confidence_str)
                if numeric_match:
                    confidence = float(numeric_match.group(1))
                else:
                    confidence = float(confidence_str)
                confidence = max(0.0, min(1.0, confidence))
            except (ValueError, TypeError):
                logger.warning(f"Invalid confidence: {confidence_str}")
                confidence = 0.5
            
            logger.info(f"Parsed decision: action={action}, symbol={symbol}, quantity={quantity}, confidence={confidence}")
            
            return TradingDecision(
                action=TradingAction(action),
                symbol=symbol,
                quantity=quantity,
                reasoning=reasoning,
                confidence=Decimal(str(confidence))
            )
            
        except Exception as e:
            logger.error(f"Error parsing decision: '{decision_text}' - {e}")
            return TradingDecision(
                action=TradingAction.HOLD,
                symbol="",
                reasoning="Error parsing decision from LLM response",
                confidence=Decimal('0.0')
            )

    async def _send_workflow_summary(self, tool_calls: List[Dict[str, Any]], decision: Optional[TradingDecision], execution_result: Dict[str, Any], iterations: int):
        """Send comprehensive workflow completion summary."""
        try:
            # Count successful vs failed tools
            successful_tools = sum(1 for tc in tool_calls if tc.get('success', True))
            failed_tools = len(tool_calls) - successful_tools
            
            # Get decision status with emoji
            decision_emoji = {
                "BUY": "📈", 
                "SELL": "📉", 
                "HOLD": "⏸️"
            }.get(decision.action.value if decision else "HOLD", "⏸️")
            
            # Get execution status emoji
            execution_emoji = "✅" if execution_result.get('success') else "❌"
            
            # Create unique tools list for display
            unique_tools = list(set(tc['name'] for tc in tool_calls))
            
            summary_message = f"""
🎯 **AI Analysis Complete**

📊 **Analysis Summary**:
• Steps completed: {iterations}
• Tools executed: {len(tool_calls)} ({successful_tools} ✅, {failed_tools} ❌)
• Tools used: {', '.join(unique_tools)}

{decision_emoji} **Decision**: {decision.action.value if decision else 'HOLD'}
{execution_emoji} **Execution**: {'Success' if execution_result.get('success') else 'Failed/Skipped'}

💡 **Status**: Trading analysis workflow completed successfully
            """
            
            await self.message_manager.send_message(summary_message.strip(), "success")
            
        except Exception as e:
            logger.error(f"Error sending workflow summary: {e}")
            await self.message_manager.send_error(f"Error generating workflow summary: {e}", "Workflow Summary") 
