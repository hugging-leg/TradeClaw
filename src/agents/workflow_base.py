"""
Abstract base class for trading workflows.

This module provides the foundation for different trading workflow implementations
using the Factory pattern. It defines the common interface that all workflow
implementations must follow.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime

from src.apis.alpaca_api import AlpacaAPI
from src.apis.tiingo_api import TiingoAPI
from src.apis.telegram_message_queue import TelegramMessageQueue
from src.models.trading_models import TradingDecision, Portfolio


class WorkflowBase(ABC):
    """
    Abstract base class for trading workflows.
    
    This class defines the common interface that all workflow implementations
    must follow. It uses the Template Method pattern to provide a consistent
    structure while allowing different implementations for specific workflow logic.
    """
    
    def __init__(self, alpaca_api: AlpacaAPI, tiingo_api: TiingoAPI, telegram_bot=None):
        """
        Initialize the workflow with required APIs.
        
        Args:
            alpaca_api: Alpaca API client for trading operations
            tiingo_api: Tiingo API client for market data and news
            telegram_bot: Optional Telegram bot for notifications
        """
        self.alpaca_api = alpaca_api
        self.tiingo_api = tiingo_api
        self.telegram_bot = telegram_bot
        self.message_queue = TelegramMessageQueue(telegram_bot)
        
        # Common workflow state
        self.current_context = {}
        self.workflow_id = None
        self.start_time = None
        self.end_time = None
        
    @abstractmethod
    async def run_workflow(self, initial_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute the trading workflow.
        
        This is the main entry point for workflow execution. Each implementation
        should define its own execution logic while maintaining the same interface.
        
        Args:
            initial_context: Optional initial context for the workflow
            
        Returns:
            Dictionary containing the workflow results including:
            - decision: TradingDecision object or None
            - context: Updated context information
            - execution_time: Time taken for execution
            - workflow_type: Type of workflow executed
        """
        pass
    
    @abstractmethod
    async def initialize_workflow(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Initialize the workflow with given context.
        
        Args:
            context: Initial context for the workflow
            
        Returns:
            Updated context after initialization
        """
        pass
    
    @abstractmethod
    async def gather_data(self) -> Dict[str, Any]:
        """
        Gather necessary data for trading decisions.
        
        Returns:
            Dictionary containing gathered data:
            - portfolio: Current portfolio information
            - market_data: Market overview data
            - news: Recent news articles
            - additional_data: Any other relevant data
        """
        pass
    
    @abstractmethod
    async def make_decision(self, data: Dict[str, Any]) -> Optional[TradingDecision]:
        """
        Make a trading decision based on gathered data.
        
        Args:
            data: Data gathered from gather_data method
            
        Returns:
            TradingDecision object or None if no decision is made
        """
        pass
    
    @abstractmethod
    async def execute_decision(self, decision: Optional[TradingDecision]) -> Dict[str, Any]:
        """
        Execute the trading decision.
        
        Args:
            decision: TradingDecision object or None
            
        Returns:
            Dictionary containing execution results:
            - success: Boolean indicating success
            - order_id: Order ID if trade was executed
            - error: Error message if execution failed
        """
        pass
    
    # Common utility methods that can be used by all implementations
    
    async def get_portfolio(self) -> Optional[Portfolio]:
        """Get current portfolio information."""
        try:
            return await self.alpaca_api.get_portfolio()
        except Exception as e:
            await self.message_queue.send_error(f"Error getting portfolio: {e}", "Data Collection")
            return None
    
    async def get_market_data(self) -> Dict[str, Any]:
        """Get current market data."""
        try:
            return await self.tiingo_api.get_market_overview()
        except Exception as e:
            await self.message_queue.send_error(f"Error getting market data: {e}", "Data Collection")
            return {}
    
    async def get_news(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent news articles."""
        try:
            news_items = await self.tiingo_api.get_news(limit=limit)
            return [
                {
                    "title": item.title,
                    "description": item.description or "",
                    "source": item.source,
                    "published_at": item.published_at.isoformat(),
                    "symbols": item.symbols
                }
                for item in news_items
            ]
        except Exception as e:
            await self.message_queue.send_error(f"Error getting news: {e}", "Data Collection")
            return []
    
    async def is_market_open(self) -> bool:
        """Check if market is currently open."""
        try:
            return await self.alpaca_api.is_market_open()
        except Exception as e:
            await self.message_queue.send_error(f"Error checking market status: {e}", "Market Check")
            return False
    
    async def send_workflow_start_notification(self, workflow_type: str):
        """Send notification about workflow start."""
        message = f"🚀 **{workflow_type.title()} Workflow Started**\n\n"
        message += f"Starting AI trading analysis at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        await self.message_queue.send_message(message, "info")
    
    async def send_workflow_complete_notification(self, workflow_type: str, execution_time: float):
        """Send notification about workflow completion."""
        message = f"✅ **{workflow_type.title()} Workflow Complete**\n\n"
        message += f"Trading analysis completed in {execution_time:.2f} seconds."
        await self.message_queue.send_message(message, "success")
    
    def get_workflow_type(self) -> str:
        """Get the type of workflow (to be overridden by subclasses)."""
        return self.__class__.__name__.lower().replace('workflow', '')
    
    def _generate_workflow_id(self) -> str:
        """Generate a unique workflow ID."""
        return f"{self.get_workflow_type()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    def _update_context(self, new_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update current context with new data."""
        self.current_context.update(new_data)
        return self.current_context
    
    async def _handle_workflow_error(self, error: Exception, stage: str) -> Dict[str, Any]:
        """Handle workflow errors consistently."""
        error_message = f"Error in {stage}: {str(error)}"
        await self.message_queue.send_error(error_message, stage)
        
        return {
            "success": False,
            "error": error_message,
            "stage": stage,
            "workflow_type": self.get_workflow_type()
        } 