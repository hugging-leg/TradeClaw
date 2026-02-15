"""
Tiingo market data adapter implementing the MarketDataAPI interface.

This adapter wraps the Tiingo API to provide a unified interface for market data operations.
"""

import asyncio
import requests
from src.utils.logging_config import get_logger
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from src.interfaces.market_data_api import MarketDataAPI
from src.interfaces.factory import register_market_data
from src.utils.timezone import utc_now, to_trading_tz, get_trading_timezone
from src.utils.time_utils import is_market_open as check_market_open
from config import settings

logger = get_logger(__name__)


@register_market_data("tiingo")
class TiingoMarketDataAdapter(MarketDataAPI):
    """Tiingo market data adapter implementing MarketDataAPI interface"""
    
    def __init__(self):
        self.base_url = "https://api.tiingo.com"
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Token {settings.tiingo_api_key}'
        }
        logger.info("Tiingo market data adapter initialized successfully")
    
    async def get_market_overview(self) -> Dict[str, Any]:
        """Get market overview data including major indices"""
        try:
            # Get major indices data
            indices = ['SPY', 'QQQ', 'IWM', 'DIA']  # S&P 500, NASDAQ, Russell 2000, Dow Jones
            market_data = {}
            
            for symbol in indices:
                response = requests.get(
                    f"{self.base_url}/tiingo/daily/{symbol}/prices",
                    headers=self.headers,
                    params={'columns': 'open,high,low,close,volume', 'limit': 1}
                )
                response.raise_for_status()
                
                data = response.json()
                if data:
                    market_data[symbol] = {
                        'open': data[0]['open'],
                        'high': data[0]['high'],
                        'low': data[0]['low'],
                        'close': data[0]['close'],
                        'volume': data[0]['volume'],
                        'date': data[0]['date']
                    }
            
            return market_data
            
        except Exception as e:
            logger.error(f"Failed to get market overview: {e}")
            return {}
    
    async def get_eod_prices(self, symbol: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Get end-of-day prices for a symbol"""
        try:
            params = {
                'startDate': start_date.strftime('%Y-%m-%d'),
                'endDate': end_date.strftime('%Y-%m-%d'),
                'columns': 'open,high,low,close,volume,adjClose'
            }
            
            response = requests.get(
                f"{self.base_url}/tiingo/daily/{symbol}/prices",
                headers=self.headers,
                params=params
            )
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Failed to get EOD prices for {symbol}: {e}")
            return []
    
    async def get_intraday_prices(self, symbol: str, start_date: datetime, end_date: datetime, 
                                 resample_freq: str = '1min') -> List[Dict[str, Any]]:
        """Get intraday prices for a symbol"""
        try:
            params = {
                'startDate': start_date.strftime('%Y-%m-%d'),
                'endDate': end_date.strftime('%Y-%m-%d'),
                'resampleFreq': resample_freq,
                'columns': 'open,high,low,close,volume'
            }
            
            response = requests.get(
                f"{self.base_url}/iex/{symbol}/prices",
                headers=self.headers,
                params=params
            )
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Failed to get intraday prices for {symbol}: {e}")
            return []
    
    async def get_latest_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get latest price for a symbol"""
        try:
            response = requests.get(
                f"{self.base_url}/tiingo/daily/{symbol}/prices",
                headers=self.headers,
                params={'columns': 'open,high,low,close,volume,adjClose', 'limit': 1}
            )
            response.raise_for_status()
            
            data = response.json()
            if data:
                return {
                    'symbol': symbol,
                    'open': data[0]['open'],
                    'high': data[0]['high'],
                    'low': data[0]['low'],
                    'close': data[0]['close'],
                    'volume': data[0]['volume'],
                    'adj_close': data[0]['adjClose'],
                    'date': data[0]['date']
                }
            return None
            
        except Exception as e:
            logger.error(f"Failed to get latest price for {symbol}: {e}")
            return None
    
    async def get_multiple_prices(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get latest prices for multiple symbols"""
        try:
            results = {}
            
            # Process symbols in batches to avoid rate limiting
            for symbol in symbols:
                price_data = await self.get_latest_price(symbol)
                if price_data:
                    results[symbol] = price_data
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(0.1)
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to get multiple prices: {e}")
            return {}
    
    async def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a symbol"""
        try:
            response = requests.get(
                f"{self.base_url}/tiingo/daily/{symbol}",
                headers=self.headers
            )
            response.raise_for_status()
            
            data = response.json()
            if data:
                return {
                    'symbol': data['ticker'],
                    'name': data['name'],
                    'description': data['description'],
                    'start_date': data['startDate'],
                    'end_date': data['endDate'],
                    'exchange': data['exchangeCode']
                }
            return None
            
        except Exception as e:
            logger.error(f"Failed to get symbol info for {symbol}: {e}")
            return None
    
    async def search_symbols(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for symbols matching a query"""
        try:
            # Tiingo doesn't have a direct search endpoint, but we can try to get info
            # This is a simplified implementation
            symbols = []
            
            # Try the query as a direct symbol
            symbol_info = await self.get_symbol_info(query.upper())
            if symbol_info:
                symbols.append(symbol_info)
            
            return symbols[:limit]
            
        except Exception as e:
            logger.error(f"Failed to search symbols for query '{query}': {e}")
            return []
    
    async def get_market_status(self) -> Dict[str, Any]:
        """Get current market status"""
        try:
            # Use exchange_calendars for accurate market status (handles holidays)
            is_open = check_market_open()
            now_trading = to_trading_tz(utc_now())
            tz_name = str(get_trading_timezone())
            
            return {
                'is_open': is_open,
                'market_hours': {
                    'open': settings.rebalance_time,
                    'close': settings.eod_analysis_time.split(':')[0] + ':00',
                    'timezone': tz_name
                },
                'current_time': now_trading.isoformat(),
                'next_open': None,
                'next_close': None
            }
            
        except Exception as e:
            logger.error(f"Failed to get market status: {e}")
            return {}
    
    def get_provider_name(self) -> str:
        """Get the name of the market data provider"""
        return "Tiingo"
    
    def get_provider_info(self) -> Dict[str, Any]:
        """Get detailed information about the market data provider"""
        return {
            "name": "Tiingo",
            "type": "market_data",
            "description": "Financial data API for stocks, ETFs, and mutual funds",
            "website": "https://tiingo.com",
            "features": [
                "Real-time and historical stock prices",
                "Fundamental data",
                "News data",
                "Crypto data",
                "Forex data",
                "RESTful API"
            ],
            "supported_assets": ["stocks", "etfs", "mutual_funds", "crypto", "forex"],
            "supported_exchanges": ["NYSE", "NASDAQ", "AMEX", "OTC"],
            "data_coverage": {
                "stocks": "US markets",
                "history": "1962 to present",
                "intraday": "Last 2 years",
                "fundamentals": "10+ years"
            },
            "rate_limits": {
                "free_tier": "1000 requests/day",
                "paid_tier": "Varies by plan"
            },
            "pricing": {
                "free": "Limited access",
                "starter": "$10/month",
                "power": "$30/month",
                "enterprise": "Custom pricing"
            }
        }
    
    def get_supported_exchanges(self) -> List[str]:
        """Get list of supported exchanges"""
        return [
            "NYSE",
            "NASDAQ", 
            "AMEX",
            "OTC",
            "BATS",
            "IEX"
        ]
    
    def get_supported_asset_types(self) -> List[str]:
        """Get list of supported asset types"""
        return [
            "stocks",
            "etfs", 
            "mutual_funds",
            "crypto",
            "forex"
        ] 