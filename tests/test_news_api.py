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
        s = Mock(spec=Settings)
        s.tiingo_api_key = "test_tiingo_key"
        return s
    
    @pytest.fixture
    def tiingo_adapter(self, mock_settings):
        """Create TiingoNewsAdapter instance with mocked dependencies."""
        with patch('agent_trader.adapters.news.tiingo_news_adapter.settings', mock_settings):
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


class TestAlpacaNewsAdapter:
    """Test AlpacaNewsAdapter class."""

    @pytest.fixture
    def mock_settings(self):
        s = Mock(spec=Settings)
        s.alpaca_api_key = "test_alpaca_key"
        s.alpaca_secret_key = "test_alpaca_secret"
        return s

    @pytest.fixture
    def adapter(self, mock_settings):
        with patch(
            "agent_trader.adapters.news.alpaca_news_adapter.settings", mock_settings
        ):
            from agent_trader.adapters.news.alpaca_news_adapter import AlpacaNewsAdapter

            return AlpacaNewsAdapter()

    def test_initialization_enabled(self, adapter):
        assert adapter.is_enabled is True
        assert adapter.api_key == "test_alpaca_key"
        assert adapter.secret_key == "test_alpaca_secret"

    def test_initialization_disabled_when_no_key(self):
        s = Mock(spec=Settings)
        s.alpaca_api_key = ""
        s.alpaca_secret_key = ""
        with patch(
            "agent_trader.adapters.news.alpaca_news_adapter.settings", s
        ):
            from agent_trader.adapters.news.alpaca_news_adapter import AlpacaNewsAdapter

            a = AlpacaNewsAdapter()
            assert a.is_enabled is False

    def test_initialization_disabled_when_test_key(self):
        s = Mock(spec=Settings)
        s.alpaca_api_key = "test_key"
        s.alpaca_secret_key = "secret"
        with patch(
            "agent_trader.adapters.news.alpaca_news_adapter.settings", s
        ):
            from agent_trader.adapters.news.alpaca_news_adapter import AlpacaNewsAdapter

            a = AlpacaNewsAdapter()
            assert a.is_enabled is False

    def test_headers(self, adapter):
        h = adapter._headers()
        assert h["APCA-API-KEY-ID"] == "test_alpaca_key"
        assert h["APCA-API-SECRET-KEY"] == "test_alpaca_secret"

    def test_parse_article(self, adapter):
        article = {
            "headline": "Test Headline",
            "summary": "Test Summary",
            "source": "reuters",
            "url": "https://example.com/news",
            "created_at": "2025-01-15T10:30:00Z",
            "symbols": ["AAPL", "MSFT"],
        }
        item = adapter._parse_article(article)
        assert isinstance(item, NewsItem)
        assert item.title == "Test Headline"
        assert item.description == "Test Summary"
        assert item.source == "reuters"
        assert item.url == "https://example.com/news"
        assert item.symbols == ["AAPL", "MSFT"]

    def test_parse_article_missing_fields(self, adapter):
        article = {}
        item = adapter._parse_article(article)
        assert item.title == ""
        assert item.description == ""
        assert item.source == "alpaca"
        # published_at defaults to utc_now() when not provided
        assert item.published_at is not None

    @pytest.mark.asyncio
    async def test_get_news_disabled(self):
        s = Mock(spec=Settings)
        s.alpaca_api_key = ""
        s.alpaca_secret_key = ""
        with patch(
            "agent_trader.adapters.news.alpaca_news_adapter.settings", s
        ):
            from agent_trader.adapters.news.alpaca_news_adapter import AlpacaNewsAdapter

            a = AlpacaNewsAdapter()
            result = await a.get_news(limit=10)
            assert result == []

    @staticmethod
    def _make_aiohttp_mocks(mock_resp):
        """Create properly nested async context manager mocks for aiohttp."""

        class FakeGetCM:
            async def __aenter__(self):
                return mock_resp

            async def __aexit__(self, *args):
                pass

        class FakeSession:
            def get(self, *args, **kwargs):
                return FakeGetCM()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        return FakeSession

    @pytest.mark.asyncio
    async def test_get_news_success(self, adapter):
        mock_json = {
            "news": [
                {
                    "headline": "Apple Earnings",
                    "summary": "Strong Q4",
                    "source": "reuters",
                    "url": "https://example.com/1",
                    "created_at": "2025-01-15T10:30:00Z",
                    "symbols": ["AAPL"],
                },
                {
                    "headline": "Market Update",
                    "summary": "Markets rise",
                    "source": "bloomberg",
                    "url": "https://example.com/2",
                    "created_at": "2025-01-15T11:00:00Z",
                    "symbols": [],
                },
            ]
        }

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_json)

        FakeSession = self._make_aiohttp_mocks(mock_resp)

        with patch(
            "agent_trader.adapters.news.alpaca_news_adapter.aiohttp.ClientSession",
            FakeSession,
        ):
            result = await adapter.get_news(limit=10)
            assert len(result) == 2
            assert result[0].title == "Apple Earnings"
            assert result[1].title == "Market Update"

    @pytest.mark.asyncio
    async def test_get_news_api_error(self, adapter):
        mock_resp = AsyncMock()
        mock_resp.status = 403
        mock_resp.text = AsyncMock(return_value="Forbidden")

        FakeSession = self._make_aiohttp_mocks(mock_resp)

        with patch(
            "agent_trader.adapters.news.alpaca_news_adapter.aiohttp.ClientSession",
            FakeSession,
        ):
            result = await adapter.get_news(limit=10)
            assert result == []

    def test_get_provider_name(self, adapter):
        assert adapter.get_provider_name() == "Alpaca"

    def test_get_provider_info(self, adapter):
        info = adapter.get_provider_info()
        assert info["name"] == "Alpaca"
        assert info["enabled"] is True

    @pytest.mark.asyncio
    async def test_search_news_returns_empty(self, adapter):
        """Alpaca doesn't support free-text search."""
        result = await adapter.search_news("test query")
        assert result == []


class TestCompositeNewsAdapter:
    """Test CompositeNewsAdapter provider registry and initialization."""

    def test_provider_registry_has_alpaca(self):
        from agent_trader.adapters.news.composite_news_adapter import CompositeNewsAdapter
        assert "alpaca" in CompositeNewsAdapter.PROVIDER_REGISTRY

    def test_provider_registry_has_akshare(self):
        from agent_trader.adapters.news.composite_news_adapter import CompositeNewsAdapter
        assert "akshare" in CompositeNewsAdapter.PROVIDER_REGISTRY

    def test_check_api_key_alpaca(self):
        from agent_trader.adapters.news.composite_news_adapter import _check_api_key_configured

        with patch("agent_trader.adapters.news.composite_news_adapter.settings") as ms:
            ms.alpaca_api_key = "real_key"
            assert _check_api_key_configured("alpaca") is True

            ms.alpaca_api_key = "test_key"
            assert _check_api_key_configured("alpaca") is False

            ms.alpaca_api_key = ""
            assert _check_api_key_configured("alpaca") is False

    def test_check_api_key_akshare(self):
        from agent_trader.adapters.news.composite_news_adapter import _check_api_key_configured

        # AkShare is always available (no API key needed)
        assert _check_api_key_configured("akshare") is True


class TestNewsAPIConvenience:
    """Test convenience functions."""
    
    @patch('agent_trader.interfaces.factory.NewsFactory.create_news_api')
    def test_get_news_api_convenience(self, mock_create):
        """Test convenience function get_news_api."""
        mock_api = Mock()
        mock_create.return_value = mock_api
        
        result = get_news_api()
        
        assert result == mock_api
        mock_create.assert_called_once_with(None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
