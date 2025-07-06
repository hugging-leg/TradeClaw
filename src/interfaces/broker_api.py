"""
Abstract broker API interface for trading operations.

This module defines the abstract interface that all broker implementations must follow,
enabling easy switching between different brokers (Alpaca, Interactive Brokers, etc.).
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime

from src.models.trading_models import Order, Portfolio, Position


class BrokerAPI(ABC):
    """
    Abstract base class for broker API implementations.
    
    This interface defines the contract that all broker implementations must follow.
    It provides a unified way to interact with different brokers while maintaining
    the same interface across the system.
    """
    
    @abstractmethod
    async def get_account(self) -> Optional[Dict[str, Any]]:
        """
        Get account information.
        
        Returns:
            Dictionary containing account information including equity, cash, buying power, etc.
            Returns None if operation fails.
        """
        pass
    
    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """
        Get current positions.
        
        Returns:
            List of Position objects representing current holdings.
            Returns empty list if no positions or operation fails.
        """
        pass
    
    @abstractmethod
    async def get_portfolio(self) -> Optional[Portfolio]:
        """
        Get current portfolio information.
        
        Returns:
            Portfolio object containing complete portfolio information.
            Returns None if operation fails.
        """
        pass
    
    @abstractmethod
    async def submit_order(self, order: Order) -> Optional[str]:
        """
        Submit a new order.
        
        Args:
            order: Order object containing order details
            
        Returns:
            Order ID if successful, None if failed
        """
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an existing order.
        
        Args:
            order_id: ID of the order to cancel
            
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def get_orders(self, status: Optional[str] = None) -> List[Order]:
        """
        Get list of orders.
        
        Args:
            status: Optional filter by order status
            
        Returns:
            List of Order objects
        """
        pass
    
    @abstractmethod
    async def get_order(self, order_id: str) -> Optional[Order]:
        """
        Get specific order by ID.
        
        Args:
            order_id: ID of the order to retrieve
            
        Returns:
            Order object if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def get_market_data(self, symbol: str, timeframe: str = "1Day", limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get market data for a symbol.
        
        Args:
            symbol: Stock symbol
            timeframe: Data timeframe (1Day, 1Hour, etc.)
            limit: Maximum number of data points
            
        Returns:
            List of market data dictionaries
        """
        pass
    
    @abstractmethod
    async def is_market_open(self) -> bool:
        """
        Check if market is currently open.
        
        Returns:
            True if market is open, False otherwise
        """
        pass
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """
        Get the name of the broker provider.
        
        Returns:
            String name of the provider (e.g., "Alpaca", "Interactive Brokers")
        """
        pass
    
    @abstractmethod
    def get_provider_info(self) -> Dict[str, Any]:
        """
        Get detailed information about the broker provider.
        
        Returns:
            Dictionary containing provider information, capabilities, etc.
        """
        pass 