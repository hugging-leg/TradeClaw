import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Annotated
from datetime import datetime, timedelta
from decimal import Decimal

from langchain.schema import HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolExecutor, ToolInvocation
from langchain.tools import tool
from pydantic import BaseModel, Field

from config import settings
from src.apis.alpaca_api import AlpacaAPI
from src.apis.tiingo_api import TiingoAPI
from src.models.trading_models import (
    Order, Portfolio, TradingDecision, OrderSide, OrderType, TimeInForce
)


logger = logging.getLogger(__name__)


class TradingState(BaseModel):
    """State for the trading workflow"""
    messages: Annotated[List[Dict], add_messages]
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
    def get_portfolio_info(self) -> str:
        """Get current portfolio information including positions and P&L"""
        try:
            portfolio = self.alpaca_api.get_portfolio()
            
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
    def get_market_data(self, symbol: str) -> str:
        """Get current market data for a symbol"""
        try:
            market_data = self.alpaca_api.get_market_data(symbol)
            
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
    def get_historical_data(self, symbol: str, days: int = 30) -> str:
        """Get historical price data for a symbol"""
        try:
            historical_data = self.alpaca_api.get_historical_data(symbol, limit=days)
            
            if not historical_data:
                return f"No historical data found for {symbol}"
            
            recent_data = historical_data[-5:]  # Last 5 days
            
            info = f"Recent Historical Data for {symbol}:\n"
            for data in recent_data:
                info += f"- {data['timestamp'].date()}: Open=${data['open']:.2f}, "
                info += f"High=${data['high']:.2f}, Low=${data['low']:.2f}, "
                info += f"Close=${data['close']:.2f}, Volume={data['volume']:,}\n"
            
            # Calculate basic statistics
            closes = [data['close'] for data in historical_data]
            avg_price = sum(closes) / len(closes)
            price_change = ((closes[-1] - closes[0]) / closes[0]) * 100
            
            info += f"\nStatistics over {days} days:\n"
            info += f"- Average Close: ${avg_price:.2f}\n"
            info += f"- Price Change: {price_change:.2f}%\n"
            
            return info
            
        except Exception as e:
            return f"Error getting historical data for {symbol}: {e}"
    
    @tool
    def get_news(self, symbol: str = None, limit: int = 10) -> str:
        """Get recent news for a symbol or general market news"""
        try:
            if symbol:
                news_items = self.tiingo_api.get_symbol_news(symbol, limit=limit)
            else:
                news_items = self.tiingo_api.get_news(limit=limit)
            
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
    def place_order(self, symbol: str, side: str, quantity: int, order_type: str = "market", price: float = None) -> str:
        """Place a trading order"""
        try:
            order = Order(
                symbol=symbol,
                side=OrderSide(side.lower()),
                order_type=OrderType(order_type.lower()),
                quantity=Decimal(str(quantity)),
                price=Decimal(str(price)) if price else None,
                time_in_force=TimeInForce.DAY
            )
            
            placed_order = self.alpaca_api.place_order(order)
            
            return f"""
Order placed successfully:
- Order ID: {placed_order.id}
- Symbol: {placed_order.symbol}
- Side: {placed_order.side.value.upper()}
- Quantity: {placed_order.quantity}
- Type: {placed_order.order_type.value.upper()}
- Price: ${placed_order.price:.2f}" if placed_order.price else "Market"
- Status: {placed_order.status.value.upper()}
"""
        except Exception as e:
            return f"Error placing order: {e}"
    
    @tool
    def get_active_orders(self) -> str:
        """Get all active orders"""
        try:
            orders = self.alpaca_api.get_orders(status="open")
            
            if not orders:
                return "No active orders"
            
            orders_info = f"Active Orders ({len(orders)}):\n\n"
            
            for order in orders:
                orders_info += f"- {order.symbol} {order.side.value.upper()} {order.quantity} "
                orders_info += f"@ ${order.price:.2f} if order.price else 'Market'}"
                orders_info += f" (Status: {order.status.value.upper()})\n"
            
            return orders_info
            
        except Exception as e:
            return f"Error getting active orders: {e}"
    
    @tool
    def cancel_order(self, order_id: str) -> str:
        """Cancel an order by ID"""
        try:
            success = self.alpaca_api.cancel_order(order_id)
            
            if success:
                return f"Order {order_id} cancelled successfully"
            else:
                return f"Failed to cancel order {order_id}"
                
        except Exception as e:
            return f"Error cancelling order {order_id}: {e}"
    
    @tool
    def check_market_status(self) -> str:
        """Check if the market is currently open"""
        try:
            is_open = self.alpaca_api.is_market_open()
            
            if is_open:
                return "Market is currently OPEN"
            else:
                return "Market is currently CLOSED"
                
        except Exception as e:
            return f"Error checking market status: {e}"


class TradingWorkflow:
    """LangGraph workflow for trading decisions"""
    
    def __init__(self, alpaca_api: AlpacaAPI, tiingo_api: TiingoAPI):
        self.alpaca_api = alpaca_api
        self.tiingo_api = tiingo_api
        self.tools = TradingTools(alpaca_api, tiingo_api)
        self.llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.1  # Lower temperature for more consistent trading decisions
        )
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
    
    async def _gather_data(self, state: TradingState) -> TradingState:
        """Gather market data and portfolio information"""
        try:
            # Get portfolio
            portfolio = self.alpaca_api.get_portfolio()
            state.portfolio = portfolio
            
            # Get market overview
            market_data = self.tiingo_api.get_market_overview()
            state.market_data = market_data
            
            # Get recent news
            news = self.tiingo_api.get_news(limit=20)
            state.news = [
                {
                    "title": item.title,
                    "description": item.description,
                    "source": item.source,
                    "published_at": item.published_at.isoformat(),
                    "symbols": item.symbols
                }
                for item in news
            ]
            
            # Add context
            state.context["market_open"] = self.alpaca_api.is_market_open()
            state.context["timestamp"] = datetime.now().isoformat()
            
            state.messages.append({
                "role": "system",
                "content": "Data gathering completed. Portfolio, market data, and news have been collected."
            })
            
            return state
            
        except Exception as e:
            logger.error(f"Error gathering data: {e}")
            state.messages.append({
                "role": "system",
                "content": f"Error gathering data: {e}"
            })
            return state
    
    async def _analyze_market(self, state: TradingState) -> TradingState:
        """Analyze market conditions and portfolio performance"""
        try:
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
            
            return state
            
        except Exception as e:
            logger.error(f"Error analyzing market: {e}")
            state.messages.append({
                "role": "system",
                "content": f"Error analyzing market: {e}"
            })
            return state
    
    async def _make_decision(self, state: TradingState) -> TradingState:
        """Make trading decisions based on analysis"""
        try:
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
SYMBOL: [Stock symbol if applicable]
QUANTITY: [Number of shares if applicable]
REASONING: [Detailed reasoning for the decision]
CONFIDENCE: [Confidence level 0.0-1.0]

Consider:
1. Current market conditions
2. Portfolio diversification
3. Risk management
4. News impact
5. Technical indicators from historical data

Only recommend trades if you have high confidence and clear reasoning.
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
            
            return state
            
        except Exception as e:
            logger.error(f"Error making decision: {e}")
            state.messages.append({
                "role": "system",
                "content": f"Error making decision: {e}"
            })
            return state
    
    async def _execute_trades(self, state: TradingState) -> TradingState:
        """Execute trading decisions"""
        try:
            if not state.decision or state.decision.action.upper() == "HOLD":
                state.messages.append({
                    "role": "system",
                    "content": "No trades to execute. Decision was to HOLD."
                })
                return state
            
            # Check if market is open
            if not state.context.get("market_open", False):
                state.messages.append({
                    "role": "system",
                    "content": "Market is closed. Cannot execute trades."
                })
                return state
            
            # Execute the trade
            decision = state.decision
            
            if decision.action.upper() in ["BUY", "SELL"] and decision.symbol and decision.quantity:
                order = Order(
                    symbol=decision.symbol,
                    side=OrderSide.BUY if decision.action.upper() == "BUY" else OrderSide.SELL,
                    order_type=OrderType.MARKET,  # Use market orders for simplicity
                    quantity=decision.quantity,
                    time_in_force=TimeInForce.DAY
                )
                
                placed_order = self.alpaca_api.place_order(order)
                
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
            
            return state
            
        except Exception as e:
            logger.error(f"Error executing trades: {e}")
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
            
            action = decision_data.get('decision', 'HOLD').upper()
            symbol = decision_data.get('symbol', '')
            quantity = None
            
            if 'quantity' in decision_data:
                try:
                    quantity = Decimal(str(decision_data['quantity']))
                except:
                    quantity = None
            
            reasoning = decision_data.get('reasoning', 'No reasoning provided')
            
            confidence = 0.5  # Default confidence
            if 'confidence' in decision_data:
                try:
                    confidence = float(decision_data['confidence'])
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
            return TradingDecision(
                action="HOLD",
                symbol="",
                reasoning="Error parsing decision",
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