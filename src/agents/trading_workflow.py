import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Annotated, Union
from datetime import datetime, timedelta
from decimal import Decimal
from queue import Queue, Empty
import threading

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI
from langchain_deepseek import ChatDeepSeek
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
# from langgraph.prebuilt import ToolExecutor, ToolInvocation  # Not needed for current implementation
from langchain.tools import tool
from pydantic import BaseModel, Field

from config import settings
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


class TradingTools:
    """Tools for the trading agent"""
    
    def __init__(self, alpaca_api: AlpacaAPI, tiingo_api: TiingoAPI):
        self.alpaca_api = alpaca_api
        self.tiingo_api = tiingo_api
    
    @tool
    async def get_portfolio_info(self) -> str:
        """Get current portfolio information including positions and P&L"""
        try:
            portfolio = await self.alpaca_api.get_portfolio()
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
    async def get_market_data(self, symbol: str) -> str:
        """Get current market data for a symbol"""
        try:
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
    async def get_historical_data(self, symbol: str, days: int = 30) -> str:
        """Get historical price data for a symbol"""
        try:
            historical_data = await self.alpaca_api.get_market_data(symbol, limit=days)
            
            if not historical_data:
                return f"No historical data found for {symbol}"
            
            # Since get_market_data returns single data point, let's adjust this
            info = f"Market Data for {symbol}:\n"
            info += f"- Current Price: ${historical_data.price:.2f}\n"
            info += f"- Volume: {historical_data.volume:,}\n"
            
            return info
            
        except Exception as e:
            return f"Error getting historical data for {symbol}: {e}"
    
    @tool
    async def get_news(self, symbol: str = None, limit: int = 10) -> str:
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
    async def get_active_orders(self) -> str:
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
    async def cancel_order(self, order_id: str) -> str:
        """Cancel an order by ID"""
        try:
            success = await self.alpaca_api.cancel_order(order_id)
            
            if success:
                return f"Order {order_id} cancelled successfully"
            else:
                return f"Failed to cancel order {order_id}"
                
        except Exception as e:
            return f"Error cancelling order {order_id}: {e}"
    
    @tool
    async def check_market_status(self) -> str:
        """Check if the market is currently open"""
        try:
            is_open = await self.alpaca_api.is_market_open()
            
            if is_open:
                return "Market is currently OPEN"
            else:
                return "Market is currently CLOSED"
                
        except Exception as e:
            return f"Error checking market status: {e}"


class TelegramMessageQueue:
    """Message queue for Telegram notifications during workflow execution"""
    
    def __init__(self, telegram_bot=None):
        self.telegram_bot = telegram_bot
        self.message_queue = Queue()
        self.is_processing = False
        self._processor_task = None
    
    async def send_message(self, message: str, message_type: str = "info"):
        """Add message to queue for sending"""
        if not self.telegram_bot:
            logger.info(f"Telegram message ({message_type}): {message}")
            return
        
        emoji_map = {
            "info": "ℹ️",
            "success": "✅", 
            "warning": "⚠️",
            "error": "❌",
            "news": "📰",
            "analysis": "🔍",
            "decision": "🤔",
            "trade": "💼"
        }
        
        emoji = emoji_map.get(message_type, "📢")
        formatted_message = f"{emoji} {message}"
        
        # Add to queue
        self.message_queue.put({
            "message": formatted_message,
            "timestamp": datetime.now(),
            "type": message_type
        })
        
        # Start processor if not running
        if not self.is_processing:
            await self._start_processor()
    
    async def _start_processor(self):
        """Start processing messages from queue"""
        if self.is_processing:
            return
            
        self.is_processing = True
        
        try:
            while not self.message_queue.empty():
                try:
                    msg_data = self.message_queue.get_nowait()
                    await self.telegram_bot.send_message(
                        msg_data["message"], 
                        parse_mode="Markdown"
                    )
                    # Small delay to avoid flooding
                    await asyncio.sleep(1)
                except Empty:
                    break
                except Exception as e:
                    logger.error(f"Error sending Telegram message: {e}")
        finally:
            self.is_processing = False
    
    async def send_news_summary(self, news_items: List[Dict], limit: int = 5):
        """Send formatted news summary"""
        if not news_items:
            return
        
        message = "📰 **Latest Market News**\n\n"
        
        for i, news in enumerate(news_items[:limit], 1):
            message += f"**{i}.** {news['title'][:80]}{'...' if len(news['title']) > 80 else ''}\n"
            message += f"   *Source: {news['source']}*\n\n"
        
        if len(news_items) > limit:
            message += f"*...and {len(news_items) - limit} more articles*"
        
        await self.send_message(message, "news")
    
    async def send_analysis_summary(self, analysis: str):
        """Send formatted analysis summary"""
        if not analysis:
            return
        
        # Extract key points from analysis
        lines = analysis.split('\n')
        key_points = []
        
        for line in lines:
            line = line.strip()
            if line and (line.startswith('-') or line.startswith('•') or 
                        'sentiment' in line.lower() or 'trend' in line.lower() or
                        'risk' in line.lower() or 'opportunity' in line.lower()):
                key_points.append(line)
        
        message = "🔍 **Market Analysis Summary**\n\n"
        
        if key_points:
            for point in key_points[:5]:  # Limit to 5 key points
                message += f"• {point}\n"
        else:
            # Fallback to first few sentences
            sentences = analysis.split('.')[:3]
            for sentence in sentences:
                if sentence.strip():
                    message += f"• {sentence.strip()}.\n"
        
        if len(analysis) > 500:
            message += f"\n*Full analysis: {len(analysis)} characters*"
        
        await self.send_message(message, "analysis")
    
    async def send_decision_summary(self, decision: TradingDecision):
        """Send formatted trading decision"""
        if not decision:
            await self.send_message("**Decision:** HOLD - No trading action recommended", "decision")
            return
        
        message = f"🤔 **Trading Decision**\n\n"
        message += f"**Action:** {decision.action.upper()}\n"
        
        # Only show symbol and quantity for BUY/SELL decisions
        if decision.action.lower() in ["buy", "sell"]:
            message += f"**Symbol:** {decision.symbol or 'Not specified'}\n"
            if decision.quantity:
                message += f"**Quantity:** {decision.quantity}\n"
        
        message += f"**Confidence:** {decision.confidence:.1%}\n"
        
        # Truncate reasoning if too long
        reasoning = decision.reasoning[:200]
        if len(decision.reasoning) > 200:
            reasoning += "..."
        
        message += f"**Reasoning:** {reasoning}"
        
        await self.send_message(message, "decision")


class TradingWorkflow:
    """LangGraph workflow for trading decisions"""
    
    def __init__(self, alpaca_api: AlpacaAPI, tiingo_api: TiingoAPI, telegram_bot=None):
        self.alpaca_api = alpaca_api
        self.tiingo_api = tiingo_api
        self.telegram_bot = telegram_bot
        self.tools = TradingTools(alpaca_api, tiingo_api)
        self.llm = create_llm_client()
        self.workflow = None
        self.message_queue = TelegramMessageQueue(telegram_bot)
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
    
    async def _gather_data(self, state: TradingState) -> TradingState:
        """Gather market data and portfolio information"""
        try:
            await self.message_queue.send_message("**Starting Data Collection**\n\nGathering portfolio, market data, and news...", "info")
            
            # Get portfolio
            portfolio = await self.alpaca_api.get_portfolio()
            state.portfolio = portfolio
            
            # Get market overview
            market_data = await self.tiingo_api.get_market_overview()
            state.market_data = market_data
            
            # Get recent news
            news = await self.tiingo_api.get_news(limit=20)
            state.news = [
                {
                    "title": item.title,
                    "description": item.description or "",
                    "source": item.source,
                    "published_at": item.published_at.isoformat(),
                    "symbols": item.symbols
                }
                for item in news
            ]
            
            # Add context
            state.context["market_open"] = await self.alpaca_api.is_market_open()
            state.context["timestamp"] = datetime.now().isoformat()
            
            state.messages.append({
                "role": "system",
                "content": "Data gathering completed. Portfolio, market data, and news have been collected."
            })
            
            # Send data summary to Telegram
            portfolio_msg = f"**Portfolio Status**\n\n• Equity: ${portfolio.equity:,.2f}\n• Cash: ${portfolio.cash:,.2f}\n• Day P&L: ${portfolio.day_pnl:,.2f}\n• Positions: {len(portfolio.positions)}"
            await self.message_queue.send_message(portfolio_msg, "info")
            
            # Send news summary
            await self.message_queue.send_news_summary(state.news, limit=3)
            
            return state
            
        except Exception as e:
            logger.error(f"Error gathering data: {e}")
            await self.message_queue.send_message(f"**Data Collection Error**\n\n{str(e)}", "error")
            state.messages.append({
                "role": "system",
                "content": f"Error gathering data: {e}"
            })
            return state
    
    async def _analyze_market(self, state: TradingState) -> TradingState:
        """Analyze market conditions and portfolio performance"""
        try:
            await self.message_queue.send_message("**Starting Market Analysis**\n\nAnalyzing market conditions and portfolio performance...", "info")
            
            # Prepare analysis prompt
            analysis_prompt = f"""
You are a professional trading analyst. Analyze the current market conditions and portfolio performance.

Current Portfolio:
- Equity: ${state.portfolio.equity:,.2f}
- Cash: ${state.portfolio.cash:,.2f}
- Day P&L: ${state.portfolio.day_pnl:,.2f}
- Total P&L: ${state.portfolio.total_pnl:,.2f}
- Positions: {len(state.portfolio.positions)}

Market Data:
{json.dumps(state.market_data, indent=2)}

Recent News Headlines:
{chr(10).join([f"- {news['title']}" for news in state.news[:10]])}

Market Status: {'OPEN' if state.context.get('market_open', False) else 'CLOSED'}

Please provide a comprehensive market analysis including:
1. Overall market sentiment
2. Key trends and patterns
3. Risk assessment
4. Portfolio performance evaluation
5. Potential opportunities or threats

Keep your analysis concise but thorough.
"""
            
            # Get analysis from LLM
            response = await self.llm.ainvoke([
                SystemMessage(content="You are an expert trading analyst."),
                HumanMessage(content=analysis_prompt)
            ])
            
            state.messages.append({
                "role": "assistant",
                "content": response.content
            })
            
            state.context["market_analysis"] = response.content
            
            # Send analysis summary to Telegram
            await self.message_queue.send_analysis_summary(response.content)
            
            return state
            
        except Exception as e:
            logger.error(f"Error analyzing market: {e}")
            await self.message_queue.send_message(f"**Market Analysis Error**\n\n{str(e)}", "error")
            state.messages.append({
                "role": "system",
                "content": f"Error analyzing market: {e}"
            })
            return state
    
    async def _make_decision(self, state: TradingState) -> TradingState:
        """Make trading decisions based on analysis"""
        try:
            await self.message_queue.send_message("**Making Trading Decision**\n\nEvaluating trading opportunities based on analysis...", "info")
            
            # Prepare decision prompt
            decision_prompt = f"""
Based on the market analysis, portfolio status, and current conditions, make trading decisions.

Portfolio Summary:
- Available Cash: ${state.portfolio.cash:,.2f}
- Buying Power: ${state.portfolio.buying_power:,.2f}
- Current Positions: {len(state.portfolio.positions)}

Market Analysis:
{state.context.get('market_analysis', 'No analysis available')}

Risk Management Rules:
- Maximum position size: {settings.max_position_size * 100}% of portfolio
- Stop loss: {settings.stop_loss_percentage * 100}%
- Take profit: {settings.take_profit_percentage * 100}%

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

IMPORTANT: 
- Always provide detailed reasoning, even for HOLD decisions
- For HOLD decisions, explain why no action is recommended
- Only recommend trades if you have high confidence and clear reasoning
- Be conservative and prioritize capital preservation
"""
            
            # Get decision from LLM
            response = await self.llm.ainvoke([
                SystemMessage(content="You are a professional trading advisor. Make conservative, well-reasoned trading decisions."),
                HumanMessage(content=decision_prompt)
            ])
            
            # Parse decision from response
            decision_text = response.content
            decision = self._parse_decision(decision_text)
            
            state.decision = decision
            state.messages.append({
                "role": "assistant",
                "content": decision_text
            })
            
            # Send decision to Telegram
            await self.message_queue.send_decision_summary(decision)
            
            return state
            
        except Exception as e:
            logger.error(f"Error making decision: {e}")
            await self.message_queue.send_message(f"**Decision Making Error**\n\n{str(e)}", "error")
            state.messages.append({
                "role": "system",
                "content": f"Error making decision: {e}"
            })
            return state
    
    async def _execute_trades(self, state: TradingState) -> TradingState:
        """Execute trading decisions"""
        try:
            if not state.decision or state.decision.action.lower() == "hold":
                await self.message_queue.send_message("**Trade Execution**\n\nNo trades to execute. Decision was to HOLD.", "trade")
                state.messages.append({
                    "role": "system",
                    "content": "No trades to execute. Decision was to HOLD."
                })
                return state
            
            # Check if market is open
            if not state.context.get("market_open", False):
                await self.message_queue.send_message("**Trade Execution**\n\nMarket is closed. Cannot execute trades at this time.", "warning")
                state.messages.append({
                    "role": "system",
                    "content": "Market is closed. Cannot execute trades."
                })
                return state
            
            await self.message_queue.send_message("**Executing Trade**\n\nSubmitting order to market...", "trade")
            
            # Execute the trade
            decision = state.decision
            
            if decision.action.lower() in ["buy", "sell"] and decision.symbol and decision.quantity:
                order = Order(
                    symbol=decision.symbol,
                    side=OrderSide.BUY if decision.action.lower() == "buy" else OrderSide.SELL,
                    order_type=OrderType.MARKET,  # Use market orders for simplicity
                    quantity=decision.quantity,
                    time_in_force=TimeInForce.DAY
                )
                
                order_id = await self.alpaca_api.submit_order(order)
                if order_id:
                    placed_order = await self.alpaca_api.get_order(order_id)
                    if placed_order:
                        success_msg = f"**Trade Executed**\n\n✅ {placed_order.symbol} {placed_order.side.value.upper()} {placed_order.quantity} shares\n📋 Order ID: {placed_order.id}"
                        await self.message_queue.send_message(success_msg, "success")
                        
                        state.messages.append({
                            "role": "system",
                            "content": f"Order executed: {placed_order.symbol} {placed_order.side.value.upper()} {placed_order.quantity} shares"
                        })
                        
                        # Store executed order in context
                        state.context["executed_order"] = {
                            "id": placed_order.id,
                            "symbol": placed_order.symbol,
                            "side": placed_order.side.value,
                            "quantity": str(placed_order.quantity),
                            "status": placed_order.status.value
                        }
                    else:
                        await self.message_queue.send_message(f"**Trade Status**\n\nOrder submitted but could not retrieve details.\nOrder ID: {order_id}", "warning")
                        state.messages.append({
                            "role": "system",
                            "content": f"Order submitted but could not retrieve details. Order ID: {order_id}"
                        })
                else:
                    await self.message_queue.send_message("**Trade Failed**\n\nFailed to submit order to market", "error")
                    state.messages.append({
                        "role": "system",
                        "content": "Failed to submit order"
                    })
            
            # Send workflow completion message
            await self.message_queue.send_message("**Workflow Complete**\n\n🎯 Trading analysis and execution cycle finished successfully!", "success")
            
            return state
            
        except Exception as e:
            logger.error(f"Error executing trades: {e}")
            await self.message_queue.send_message(f"**Trade Execution Error**\n\n{str(e)}", "error")
            state.messages.append({
                "role": "system",
                "content": f"Error executing trades: {e}"
            })
            return state
    
    def _parse_decision(self, decision_text: str) -> TradingDecision:
        """Parse trading decision from LLM response"""
        try:
            lines = decision_text.strip().split('\n')
            
            decision_data = {}
            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    decision_data[key.strip().lower()] = value.strip()
            
            action = decision_data.get('decision', 'hold').lower()  # Use lowercase for enum
            
            # Handle symbol - for HOLD decisions, ignore N/A or empty values
            symbol = decision_data.get('symbol', '')
            if symbol.upper() in ['N/A', 'NA', 'NONE', 'NULL'] or action.lower() == 'hold':
                symbol = None  # Set to None for HOLD decisions or N/A values
            
            quantity = None
            if 'quantity' in decision_data and action.lower() in ['buy', 'sell']:
                try:
                    quantity_str = decision_data['quantity']
                    if quantity_str.upper() not in ['N/A', 'NA', 'NONE', 'NULL']:
                        quantity = Decimal(str(quantity_str))
                except:
                    quantity = None
            
            reasoning = decision_data.get('reasoning', 'No specific reasoning provided')
            
            confidence = 0.5  # Default confidence
            if 'confidence' in decision_data:
                try:
                    confidence_str = decision_data['confidence']
                    confidence = float(confidence_str)
                    # Ensure confidence is between 0 and 1
                    confidence = max(0.0, min(1.0, confidence))
                except:
                    confidence = 0.5
            
            return TradingDecision(
                action=action,
                symbol=symbol,
                quantity=quantity,
                reasoning=reasoning,
                confidence=confidence
            )
            
        except Exception as e:
            logger.error(f"Error parsing decision: {e}")
            logger.error(f"Decision text was: {decision_text}")
            return TradingDecision(
                action="hold",  # Use lowercase for enum
                symbol=None,
                reasoning="Error parsing decision from LLM response",
                confidence=0.0
            )
    
    async def run_workflow(self, initial_context: Dict[str, Any] = None) -> TradingState:
        """Run the trading workflow"""
        try:
            # Initialize state
            initial_state = TradingState(
                messages=[],
                context=initial_context or {}
            )
            
            # Run the workflow
            final_state = await self.workflow.ainvoke(initial_state)
            
            return final_state
            
        except Exception as e:
            logger.error(f"Error running workflow: {e}")
            raise 