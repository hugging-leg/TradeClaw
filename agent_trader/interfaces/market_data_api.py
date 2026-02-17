"""
Abstract market data API interface for financial data operations.

This module defines the abstract interface that all market data implementations must follow,
enabling easy switching between different data providers (Tiingo, Alpha Vantage, Yahoo Finance, etc.).
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from datetime import datetime


class MarketDataAPI(ABC):
    """
    Abstract base class for market data API implementations.
    
    This interface defines the contract that all market data implementations must follow.
    It provides a unified way to access market data from different providers while maintaining
    the same interface across the system.
    """
    
    @abstractmethod
    async def get_market_overview(self) -> Dict[str, Any]:
        """
        Get market overview data including major indices.
        
        Returns:
            Dictionary containing market overview data for major indices
            Returns empty dict if operation fails
        """
        pass
    
    @abstractmethod
    async def get_eod_prices(self, symbol: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """
        Get end-of-day prices for a symbol.
        
        Args:
            symbol: Stock symbol
            start_date: Start date for data range
            end_date: End date for data range
            
        Returns:
            List of price data dictionaries
        """
        pass
    
    @abstractmethod
    async def get_intraday_prices(self, symbol: str, start_date: datetime, end_date: datetime, 
                                 resample_freq: str = '1min') -> List[Dict[str, Any]]:
        """
        Get intraday prices for a symbol.
        
        Args:
            symbol: Stock symbol
            start_date: Start date for data range
            end_date: End date for data range
            resample_freq: Resampling frequency (e.g., '1min', '5min', '1hour')
            
        Returns:
            List of intraday price data dictionaries
        """
        pass
    
    @abstractmethod
    async def get_latest_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get latest price for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dictionary containing latest price data or None if not available
        """
        pass
    
    @abstractmethod
    async def get_multiple_prices(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get latest prices for multiple symbols.
        
        Args:
            symbols: List of stock symbols
            
        Returns:
            Dictionary mapping symbols to their price data
        """
        pass
    
    @abstractmethod
    async def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dictionary containing symbol information or None if not found
        """
        pass
    
    @abstractmethod
    async def search_symbols(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search for symbols matching a query.
        
        Args:
            query: Search query
            limit: Maximum number of results to return
            
        Returns:
            List of matching symbol dictionaries
        """
        pass
    
    @abstractmethod
    async def get_market_status(self) -> Dict[str, Any]:
        """
        Get current market status (open/closed, hours, etc.).
        
        Returns:
            Dictionary containing market status information
        """
        pass
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """
        Get the name of the market data provider.
        
        Returns:
            String name of the provider (e.g., "Tiingo", "Alpha Vantage", "Yahoo Finance")
        """
        pass
    
    @abstractmethod
    def get_provider_info(self) -> Dict[str, Any]:
        """
        Get detailed information about the market data provider.
        
        Returns:
            Dictionary containing provider information, capabilities, rate limits, etc.
        """
        pass
    
    @abstractmethod
    def get_supported_exchanges(self) -> List[str]:
        """
        Get list of supported exchanges.
        
        Returns:
            List of exchange names supported by this provider
        """
        pass
    
    @abstractmethod
    def get_supported_asset_types(self) -> List[str]:
        """
        Get list of supported asset types.
        
        Returns:
            List of asset types supported (e.g., "stocks", "forex", "crypto", "bonds")
        """
        pass 