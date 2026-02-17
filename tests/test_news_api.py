"""
Unit tests for News API and adapters.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone

from agent_trader.interfaces.news_api import NewsAPI, NewsProvider
from agent_trader.interfaces.factory import get_news_api
from agent_trader.adapters.news.tiingo_news_adapter import TiingoNewsAdapter
from agent_trader.models.trading_models import NewsItem
from config import Settings


class TestNewsAPI:
    """Test NewsAPI abstract interface."""
    
    def test_news_provider_enum(self):
        """Test NewsProvider enum values."""
        assert NewsProvider.TIINGO.value == "tiingo"
        assert NewsProvider.ALPHA_VANTAGE.value == "alpha_vantage"
        assert NewsProvider.NEWS_API.value == "news_api"
        assert NewsProvider.CUSTOM.value == "custom"


class TestTiingoNewsAdapter:
    """Test TiingoNewsAdapter class."""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = Mock(spec=Settings)
        settings.tiingo_api_key = "test_tiingo_key"
        return settings
    
    @pytest.fixture
    def tiingo_adapter(self, mock_settings):
        """Create TiingoNewsAdapter instance with mocked dependencies."""
        with patch('src.adapters.news.tiingo_news_adapter.settings', mock_settings):
            adapter = TiingoNewsAdapter()
            return adapter
    
    def test_tiingo_adapter_initialization(self, tiingo_adapter):
        """Test TiingoNewsAdapter initialization."""
        assert tiingo_adapter.base_url == "https://api.tiingo.com"
        assert "Token test_tiingo_key" in tiingo_adapter.headers['Authorization']
    
    def test_get_provider_name(self, tiingo_adapter):
        """Test getting provider name."""
        assert tiingo_adapter.get_provider_name() == "Tiingo"
    
    def test_get_provider_info(self, tiingo_adapter):
        """Test getting provider info."""
        info = tiingo_adapter.get_provider_info()
        assert info['name'] == 'Tiingo'
        assert info['provider'] == 'tiingo'
        assert 'features' in info
        assert 'rate_limits' in info
        assert 'supported_markets' in info
    
    @pytest.mark.asyncio
    async def test_get_news_success(self, tiingo_adapter):
        """Test getting news successfully."""
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
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            news_items = await tiingo_adapter.get_news(limit=10)
            
            assert len(news_items) == 1
            assert isinstance(news_items[0], NewsItem)
            assert news_items[0].title == "Apple Reports Strong Q4 Earnings"
            assert news_items[0].symbols == ["AAPL"]
            assert news_items[0].source == "Reuters"
    
    @pytest.mark.asyncio
    async def test_get_news_error(self, tiingo_adapter):
        """Test error handling in get_news."""
        with patch('requests.get') as mock_get:
            mock_get.side_effect = Exception("API Error")
            
            news_items = await tiingo_adapter.get_news(limit=10)
            
            assert news_items == []
    
    def test_parse_news_item_success(self, tiingo_adapter):
        """Test parsing news item successfully."""
        news_data = {
            "title": "Test News",
            "description": "Test description",
            "url": "https://example.com/news/test",
            "source": "Test Source",
            "tickers": ["AAPL"],
            "publishedDate": "2023-10-30T16:00:00Z"
        }
        
        news_item = tiingo_adapter._parse_news_item(news_data)
        
        assert isinstance(news_item, NewsItem)
        assert news_item.title == "Test News"
        assert news_item.description == "Test description"
        assert news_item.source == "Test Source"
        assert news_item.symbols == ["AAPL"]


class TestNewsAPIConvenience:
    """Test convenience functions."""
    
    @patch('src.interfaces.factory.NewsFactory.create_news_api')
    def test_get_news_api_convenience(self, mock_create):
        """Test convenience function get_news_api."""
        mock_api = Mock()
        mock_create.return_value = mock_api
        
        result = get_news_api()
        
        assert result == mock_api
        mock_create.assert_called_once_with(None) 