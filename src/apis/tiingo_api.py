import requests
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from config import settings
from src.models.trading_models import NewsItem


logger = logging.getLogger(__name__)


class TiingoAPI:
    """Tiingo API wrapper for news and market data"""
    
    def __init__(self):
        self.base_url = "https://api.tiingo.com"
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Token {settings.tiingo_api_key}'
        }
        
    def get_news(self, 
                 symbols: Optional[List[str]] = None,
                 tags: Optional[List[str]] = None,
                 sources: Optional[List[str]] = None,
                 start_date: Optional[datetime] = None,
                 end_date: Optional[datetime] = None,
                 limit: int = 100) -> List[NewsItem]:
        """Get news articles"""
        try:
            # Default to last 24 hours if no date range provided
            if not start_date:
                start_date = datetime.now() - timedelta(days=1)
            if not end_date:
                end_date = datetime.now()
            
            params = {
                'startDate': start_date.strftime('%Y-%m-%d'),
                'endDate': end_date.strftime('%Y-%m-%d'),
                'limit': limit,
                'sortBy': 'publishedDate'
            }
            
            if symbols:
                params['tickers'] = ','.join(symbols)
            if tags:
                params['tags'] = ','.join(tags)
            if sources:
                params['sources'] = ','.join(sources)
            
            response = requests.get(
                f"{self.base_url}/tiingo/news",
                headers=self.headers,
                params=params
            )
            response.raise_for_status()
            
            news_data = response.json()
            news_items = []
            
            for item in news_data:
                news_item = NewsItem(
                    title=item.get('title', ''),
                    description=item.get('description', ''),
                    url=item.get('url', ''),
                    source=item.get('source', ''),
                    published_at=datetime.fromisoformat(item.get('publishedDate', '').replace('Z', '+00:00')),
                    symbols=item.get('tickers', [])
                )
                news_items.append(news_item)
            
            logger.info(f"Retrieved {len(news_items)} news articles")
            return news_items
            
        except Exception as e:
            logger.error(f"Failed to get news: {e}")
            raise
    
    def get_market_overview(self) -> Dict[str, Any]:
        """Get market overview data"""
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
            raise
    
    def get_symbol_news(self, symbol: str, limit: int = 50) -> List[NewsItem]:
        """Get news for a specific symbol"""
        try:
            return self.get_news(symbols=[symbol], limit=limit)
        except Exception as e:
            logger.error(f"Failed to get news for {symbol}: {e}")
            raise
    
    def get_sector_news(self, sector: str, limit: int = 50) -> List[NewsItem]:
        """Get news for a specific sector"""
        try:
            return self.get_news(tags=[sector], limit=limit)
        except Exception as e:
            logger.error(f"Failed to get sector news for {sector}: {e}")
            raise
    
    def get_crypto_news(self, limit: int = 50) -> List[NewsItem]:
        """Get cryptocurrency news"""
        try:
            return self.get_news(tags=['Cryptocurrency'], limit=limit)
        except Exception as e:
            logger.error(f"Failed to get crypto news: {e}")
            raise
    
    def get_eod_prices(self, symbol: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
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
            raise
    
    def get_intraday_prices(self, symbol: str, start_date: datetime, end_date: datetime, 
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
            raise
    
    def search_news_by_keyword(self, keyword: str, limit: int = 50) -> List[NewsItem]:
        """Search news articles by keyword"""
        try:
            params = {
                'q': keyword,
                'limit': limit,
                'sortBy': 'publishedDate',
                'startDate': (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
                'endDate': datetime.now().strftime('%Y-%m-%d')
            }
            
            response = requests.get(
                f"{self.base_url}/tiingo/news",
                headers=self.headers,
                params=params
            )
            response.raise_for_status()
            
            news_data = response.json()
            news_items = []
            
            for item in news_data:
                if keyword.lower() in item.get('title', '').lower() or keyword.lower() in item.get('description', '').lower():
                    news_item = NewsItem(
                        title=item.get('title', ''),
                        description=item.get('description', ''),
                        url=item.get('url', ''),
                        source=item.get('source', ''),
                        published_at=datetime.fromisoformat(item.get('publishedDate', '').replace('Z', '+00:00')),
                        symbols=item.get('tickers', [])
                    )
                    news_items.append(news_item)
            
            logger.info(f"Found {len(news_items)} news articles for keyword '{keyword}'")
            return news_items
            
        except Exception as e:
            logger.error(f"Failed to search news for keyword '{keyword}': {e}")
            raise 