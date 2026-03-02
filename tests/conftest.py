"""
Pytest configuration and common fixtures.
"""

import pytest
import asyncio
import os
from unittest.mock import Mock, patch
from decimal import Decimal
from datetime import datetime, timezone


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    settings = Mock()
    settings.alpaca_api_key = "test_alpaca_key"
    settings.alpaca_secret_key = "test_alpaca_secret"
    settings.alpaca_base_url = "https://paper-api.alpaca.markets"
    settings.tiingo_api_key = "test_tiingo_key"
    settings.openai_api_key = "test_openai_key"
    settings.telegram_bot_token = "test_bot_token"
    settings.telegram_chat_id = "test_chat_id"
    settings.database_url = "sqlite:///./test_trading_agent.db"

    settings.stop_loss_percentage = 0.05
    settings.take_profit_percentage = 0.15
    settings.rebalance_time = "09:30"
    settings.environment = "testing"
    settings.log_level = "DEBUG"
    return settings


@pytest.fixture
def sample_timestamp():
    """Create a sample timestamp for testing."""
    return datetime(2023, 10, 30, 16, 0, tzinfo=timezone.utc)


@pytest.fixture
def sample_market_data():
    """Create sample market data for testing."""
    return {
        "symbol": "AAPL",
        "timestamp": "2023-10-30T16:00:00Z",
        "open": 150.00,
        "high": 152.00,
        "low": 149.50,
        "close": 151.00,
        "volume": 1000000
    }


@pytest.fixture
def sample_news_data():
    """Create sample news data for testing."""
    return {
        "title": "Apple Reports Strong Q4 Earnings",
        "description": "Apple Inc. reported quarterly earnings that beat analyst expectations",
        "url": "https://example.com/news/apple-earnings",
        "source": "Reuters",
        "tickers": ["AAPL"],
        "publishedDate": "2023-10-30T16:00:00Z"
    }


@pytest.fixture
def clean_environment():
    """Ensure clean environment for tests."""
    # Store original environment variables
    original_env = dict(os.environ)
    
    # Clear test-related environment variables
    test_vars = [
        'ALPACA_API_KEY', 'ALPACA_SECRET_KEY', 'TIINGO_API_KEY',
        'OPENAI_API_KEY', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID',
        'DATABASE_URL'
    ]
    
    for var in test_vars:
        if var in os.environ:
            del os.environ[var]
    
    yield
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def mock_database():
    """Create mock database for testing."""
    with patch('sqlalchemy.create_engine') as mock_engine:
        with patch('sqlalchemy.orm.sessionmaker') as mock_session:
            yield mock_engine, mock_session 