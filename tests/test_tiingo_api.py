"""
Unit tests for Tiingo API.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from decimal import Decimal
from datetime import datetime, timezone
import aiohttp
from src.apis.tiingo_api import TiingoAPI
from src.models.trading_models import NewsItem
from config import Settings


class TestTiingoAPI:
    """Test TiingoAPI class."""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = Mock(spec=Settings)
        settings.tiingo_api_key = "test_tiingo_key"
        return settings
    
    @pytest.fixture
    def tiingo_api(self, mock_settings):
        """Create TiingoAPI instance with mocked dependencies."""
        with patch('src.apis.tiingo_api.settings', mock_settings):
            api = TiingoAPI()
            return api
    
    def test_tiingo_api_initialization(self, tiingo_api):
        """Test TiingoAPI initialization."""
        assert tiingo_api.api_key == "test_tiingo_key"
        assert tiingo_api.base_url == "https://api.tiingo.com"
    
    @pytest.mark.asyncio
    async def test_get_stock_price(self, tiingo_api):
        """Test getting stock price."""
        mock_response_data = [{
            "ticker": "AAPL",
            "timestamp": "2023-10-30T16:00:00Z",
            "close": 150.25,
            "high": 152.00,
            "low": 149.50,
            "open": 150.00,
            "volume": 1000000
        }]
        
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = Mock()
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_response.status = 200
            mock_get.return_value.__aenter__.return_value = mock_response
            
            price_data = await tiingo_api.get_stock_price("AAPL")
            
            assert price_data is not None
            assert price_data["ticker"] == "AAPL"
            assert price_data["close"] == 150.25
    
    @pytest.mark.asyncio
    async def test_get_stock_price_error(self, tiingo_api):
        """Test error handling in get_stock_price."""
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = Mock()
            mock_response.status = 404
            mock_get.return_value.__aenter__.return_value = mock_response
            
            price_data = await tiingo_api.get_stock_price("INVALID")
            
            assert price_data is None
    
    @pytest.mark.asyncio
    async def test_get_historical_data(self, tiingo_api):
        """Test getting historical data."""
        mock_response_data = [
            {
                "date": "2023-10-29T00:00:00Z",
                "close": 149.50,
                "high": 150.00,
                "low": 148.50,
                "open": 149.00,
                "volume": 800000
            },
            {
                "date": "2023-10-30T00:00:00Z",
                "close": 150.25,
                "high": 152.00,
                "low": 149.50,
                "open": 150.00,
                "volume": 1000000
            }
        ]
        
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = Mock()
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_response.status = 200
            mock_get.return_value.__aenter__.return_value = mock_response
            
            historical_data = await tiingo_api.get_historical_data("AAPL", "2023-10-29", "2023-10-30")
            
            assert len(historical_data) == 2
            assert historical_data[0]["close"] == 149.50
            assert historical_data[1]["close"] == 150.25
    
    @pytest.mark.asyncio
    async def test_get_historical_data_empty(self, tiingo_api):
        """Test getting historical data with empty response."""
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = Mock()
            mock_response.json = AsyncMock(return_value=[])
            mock_response.status = 200
            mock_get.return_value.__aenter__.return_value = mock_response
            
            historical_data = await tiingo_api.get_historical_data("AAPL", "2023-10-29", "2023-10-30")
            
            assert historical_data == []
    
    @pytest.mark.asyncio
    async def test_get_news(self, tiingo_api):
        """Test getting news."""
        mock_response_data = [
            {
                "title": "Apple Reports Strong Q4 Earnings",
                "description": "Apple Inc. reported quarterly earnings that beat analyst expectations",
                "url": "https://example.com/news/apple-earnings",
                "source": "Reuters",
                "tickers": ["AAPL"],
                "publishedDate": "2023-10-30T16:00:00Z"
            },
            {
                "title": "Tech Stocks Rally",
                "description": "Major tech stocks see significant gains",
                "url": "https://example.com/news/tech-rally",
                "source": "Bloomberg",
                "tickers": ["AAPL", "GOOGL", "MSFT"],
                "publishedDate": "2023-10-30T14:00:00Z"
            }
        ]
        
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = Mock()
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_response.status = 200
            mock_get.return_value.__aenter__.return_value = mock_response
            
            news_items = await tiingo_api.get_news(tickers=["AAPL"], limit=10)
            
            assert len(news_items) == 2
            assert isinstance(news_items[0], NewsItem)
            assert news_items[0].title == "Apple Reports Strong Q4 Earnings"
            assert news_items[0].symbols == ["AAPL"]
            assert news_items[0].source == "Reuters"
    
    @pytest.mark.asyncio
    async def test_get_news_with_sentiment(self, tiingo_api):
        """Test getting news with sentiment analysis."""
        mock_response_data = [
            {
                "title": "Apple Reports Strong Q4 Earnings",
                "description": "Apple Inc. reported quarterly earnings that beat analyst expectations",
                "url": "https://example.com/news/apple-earnings",
                "source": "Reuters",
                "tickers": ["AAPL"],
                "publishedDate": "2023-10-30T16:00:00Z"
            }
        ]
        
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = Mock()
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_response.status = 200
            mock_get.return_value.__aenter__.return_value = mock_response
            
            with patch.object(tiingo_api, '_analyze_sentiment', return_value=Decimal("0.75")) as mock_sentiment:
                news_items = await tiingo_api.get_news(tickers=["AAPL"], limit=10)
                
                assert len(news_items) == 1
                assert news_items[0].sentiment == Decimal("0.75")
                mock_sentiment.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_news_error(self, tiingo_api):
        """Test error handling in get_news."""
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = Mock()
            mock_response.status = 500
            mock_get.return_value.__aenter__.return_value = mock_response
            
            news_items = await tiingo_api.get_news(tickers=["AAPL"], limit=10)
            
            assert news_items == []
    
    @pytest.mark.asyncio
    async def test_get_market_data(self, tiingo_api):
        """Test getting market data."""
        mock_response_data = [
            {
                "date": "2023-10-30T16:00:00Z",
                "close": 150.25,
                "high": 152.00,
                "low": 149.50,
                "open": 150.00,
                "volume": 1000000
            }
        ]
        
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = Mock()
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_response.status = 200
            mock_get.return_value.__aenter__.return_value = mock_response
            
            market_data = await tiingo_api.get_market_data("AAPL", "1Day", 10)
            
            assert len(market_data) == 1
            assert market_data[0]["close"] == 150.25
            assert market_data[0]["symbol"] == "AAPL"
    
    @pytest.mark.asyncio
    async def test_get_market_data_intraday(self, tiingo_api):
        """Test getting intraday market data."""
        mock_response_data = [
            {
                "date": "2023-10-30T16:00:00Z",
                "close": 150.25,
                "high": 152.00,
                "low": 149.50,
                "open": 150.00,
                "volume": 1000000
            }
        ]
        
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = Mock()
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_response.status = 200
            mock_get.return_value.__aenter__.return_value = mock_response
            
            market_data = await tiingo_api.get_market_data("AAPL", "1Hour", 24)
            
            assert len(market_data) == 1
            assert market_data[0]["close"] == 150.25
    
    def test_analyze_sentiment(self, tiingo_api):
        """Test sentiment analysis."""
        # Test positive sentiment
        positive_text = "Apple reports strong earnings and beats expectations significantly"
        sentiment = tiingo_api._analyze_sentiment(positive_text)
        assert sentiment > 0
        
        # Test negative sentiment
        negative_text = "Apple stock crashes due to poor earnings and weak guidance"
        sentiment = tiingo_api._analyze_sentiment(negative_text)
        assert sentiment < 0
        
        # Test neutral sentiment
        neutral_text = "Apple releases quarterly report"
        sentiment = tiingo_api._analyze_sentiment(neutral_text)
        assert abs(sentiment) < 0.3  # Should be close to neutral
    
    def test_convert_timeframe(self, tiingo_api):
        """Test timeframe conversion."""
        # Test various timeframes
        assert tiingo_api._convert_timeframe("1Min") == "1min"
        assert tiingo_api._convert_timeframe("5Min") == "5min"
        assert tiingo_api._convert_timeframe("1Hour") == "1hour"
        assert tiingo_api._convert_timeframe("1Day") == "1day"
        assert tiingo_api._convert_timeframe("1Week") == "1week"
        assert tiingo_api._convert_timeframe("1Month") == "1month"
    
    def test_parse_news_item(self, tiingo_api):
        """Test parsing news item data."""
        news_data = {
            "title": "Apple Reports Strong Q4 Earnings",
            "description": "Apple Inc. reported quarterly earnings that beat analyst expectations",
            "url": "https://example.com/news/apple-earnings",
            "source": "Reuters",
            "tickers": ["AAPL"],
            "publishedDate": "2023-10-30T16:00:00Z"
        }
        
        news_item = tiingo_api._parse_news_item(news_data)
        
        assert isinstance(news_item, NewsItem)
        assert news_item.title == "Apple Reports Strong Q4 Earnings"
        assert news_item.symbols == ["AAPL"]
        assert news_item.source == "Reuters"
        assert news_item.published_at.year == 2023
        assert news_item.published_at.month == 10
        assert news_item.published_at.day == 30
    
    def test_build_url(self, tiingo_api):
        """Test URL building."""
        url = tiingo_api._build_url("daily", "AAPL", {"startDate": "2023-10-29"})
        
        assert url.startswith("https://api.tiingo.com/tiingo/daily/AAPL/prices")
        assert "token=test_tiingo_key" in url
        assert "startDate=2023-10-29" in url
    
    @pytest.mark.asyncio
    async def test_make_request_success(self, tiingo_api):
        """Test successful API request."""
        mock_response_data = {"test": "data"}
        
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = Mock()
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_response.status = 200
            mock_get.return_value.__aenter__.return_value = mock_response
            
            result = await tiingo_api._make_request("test_endpoint")
            
            assert result == mock_response_data
    
    @pytest.mark.asyncio
    async def test_make_request_http_error(self, tiingo_api):
        """Test API request with HTTP error."""
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = Mock()
            mock_response.status = 401
            mock_get.return_value.__aenter__.return_value = mock_response
            
            result = await tiingo_api._make_request("test_endpoint")
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_make_request_network_error(self, tiingo_api):
        """Test API request with network error."""
        with patch('aiohttp.ClientSession.get', side_effect=aiohttp.ClientError("Network error")):
            result = await tiingo_api._make_request("test_endpoint")
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_get_crypto_prices(self, tiingo_api):
        """Test getting cryptocurrency prices."""
        mock_response_data = [
            {
                "ticker": "btcusd",
                "timestamp": "2023-10-30T16:00:00Z",
                "close": 35000.00,
                "high": 36000.00,
                "low": 34000.00,
                "open": 35500.00,
                "volume": 1000000
            }
        ]
        
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = Mock()
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_response.status = 200
            mock_get.return_value.__aenter__.return_value = mock_response
            
            crypto_data = await tiingo_api.get_crypto_prices("btcusd")
            
            assert crypto_data is not None
            assert crypto_data["ticker"] == "btcusd"
            assert crypto_data["close"] == 35000.00


class TestTiingoAPIHelpers:
    """Test helper methods in TiingoAPI."""
    
    def test_sentiment_keywords(self):
        """Test sentiment analysis keywords."""
        from src.apis.tiingo_api import TiingoAPI
        
        api = TiingoAPI()
        
        # Test positive keywords
        positive_text = "earnings beat expectations strong growth"
        sentiment = api._analyze_sentiment(positive_text)
        assert sentiment > 0
        
        # Test negative keywords
        negative_text = "stock crashes poor performance loss"
        sentiment = api._analyze_sentiment(negative_text)
        assert sentiment < 0
    
    def test_date_parsing(self):
        """Test date parsing functionality."""
        from src.apis.tiingo_api import TiingoAPI
        
        api = TiingoAPI()
        
        # Test ISO format
        date_str = "2023-10-30T16:00:00Z"
        parsed_date = api._parse_date(date_str)
        
        assert parsed_date.year == 2023
        assert parsed_date.month == 10
        assert parsed_date.day == 30
        assert parsed_date.hour == 16
        assert parsed_date.tzinfo == timezone.utc


@pytest.mark.integration
class TestTiingoAPIIntegration:
    """Integration tests for Tiingo API (requires real credentials)."""
    
    @pytest.mark.skip(reason="Requires real Tiingo credentials")
    @pytest.mark.asyncio
    async def test_real_stock_price_fetch(self):
        """Test fetching real stock prices."""
        # This test would require real credentials and would be run separately
        # in an integration test environment
        pass
    
    @pytest.mark.skip(reason="Requires real Tiingo credentials")
    @pytest.mark.asyncio
    async def test_real_news_fetch(self):
        """Test fetching real news."""
        # This test would require real credentials and would be run separately
        # in an integration test environment
        pass 