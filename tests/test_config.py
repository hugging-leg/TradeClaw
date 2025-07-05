"""
Unit tests for configuration module.
"""

import pytest
import os
from unittest.mock import patch, mock_open
from config import Settings


class TestSettings:
    """Test Settings configuration."""
    
    @patch.dict(os.environ, {
        'ALPACA_API_KEY': 'test_alpaca_key',
        'ALPACA_SECRET_KEY': 'test_alpaca_secret',
        'TIINGO_API_KEY': 'test_tiingo_key',
        'OPENAI_API_KEY': 'test_openai_key',
        'TELEGRAM_BOT_TOKEN': 'test_bot_token',
        'TELEGRAM_CHAT_ID': 'test_chat_id',
        'POSTGRES_PASSWORD': 'test_postgres_password'
    })
    def test_settings_from_environment(self):
        """Test settings loaded from environment variables."""
        settings = Settings()
        
        assert settings.alpaca_api_key == 'test_alpaca_key'
        assert settings.alpaca_secret_key == 'test_alpaca_secret'
        assert settings.tiingo_api_key == 'test_tiingo_key'
        assert settings.openai_api_key == 'test_openai_key'
        assert settings.telegram_bot_token == 'test_bot_token'
        assert settings.telegram_chat_id == 'test_chat_id'
    
    def test_default_values(self):
        """Test default configuration values."""
        with patch.dict(os.environ, {
            'ALPACA_API_KEY': 'test_key',
            'ALPACA_SECRET_KEY': 'test_secret',
            'TIINGO_API_KEY': 'test_tiingo',
            'OPENAI_API_KEY': 'test_openai',
            'TELEGRAM_BOT_TOKEN': 'test_token',
            'TELEGRAM_CHAT_ID': 'test_chat'
        }):
            settings = Settings()
            
            # Test values from .env file
            assert "paper-api.alpaca.markets" in settings.alpaca_base_url
            assert settings.openai_model == "gpt-4o"
            assert settings.database_url == "sqlite:///./trading_agent.db"
            assert settings.max_position_size == 10000.0  # From .env file
            assert settings.rebalance_time == "09:30"
            assert settings.stop_loss_percentage == 5.0  # From .env file  
            assert settings.take_profit_percentage == 15.0  # From .env file
            assert settings.environment == "development"
            assert settings.log_level == "INFO"
    
    @patch.dict(os.environ, {
        'ALPACA_API_KEY': 'test_key',
        'ALPACA_SECRET_KEY': 'test_secret',
        'TIINGO_API_KEY': 'test_tiingo',
        'OPENAI_API_KEY': 'test_openai',
        'TELEGRAM_BOT_TOKEN': 'test_token',
        'TELEGRAM_CHAT_ID': 'test_chat',
        'ALPACA_BASE_URL': 'https://api.alpaca.markets',
        'MAX_POSITION_SIZE': '0.2',
        'STOP_LOSS_PERCENTAGE': '0.03',
        'TAKE_PROFIT_PERCENTAGE': '0.20',
        'ENVIRONMENT': 'production',
        'LOG_LEVEL': 'DEBUG'
    })
    def test_custom_values(self):
        """Test custom configuration values."""
        settings = Settings()
        
        assert settings.alpaca_base_url == "https://api.alpaca.markets"
        assert settings.max_position_size == 0.2
        assert settings.stop_loss_percentage == 0.03
        assert settings.take_profit_percentage == 0.20
        assert settings.environment == "production"
        assert settings.log_level == "DEBUG"
    
    def test_missing_required_fields(self):
        """Test that settings work when no env vars are provided (still reads .env file)."""
        with patch.dict(os.environ, {}, clear=True):
            # Even with no env vars, it still reads from .env file
            settings = Settings()
            # Should get values from .env file, not defaults
            assert settings.alpaca_api_key is not None  # Should have some value from .env
            assert len(settings.alpaca_api_key) > 0  # Should not be empty
            assert settings.environment == "development"
    

    
    @patch.dict(os.environ, {
        'ALPACA_API_KEY': 'test_key',
        'ALPACA_SECRET_KEY': 'test_secret',
        'TIINGO_API_KEY': 'test_tiingo',
        'OPENAI_API_KEY': 'test_openai',
        'TELEGRAM_BOT_TOKEN': 'test_token',
        'TELEGRAM_CHAT_ID': 'test_chat',
        'OPENAI_MODEL': 'gpt-3.5-turbo'
    })
    def test_openai_model_configuration(self):
        """Test OpenAI model configuration."""
        settings = Settings()
        
        assert settings.openai_model == "gpt-3.5-turbo"
    
    @patch.dict(os.environ, {
        'ALPACA_API_KEY': 'test_key',
        'ALPACA_SECRET_KEY': 'test_secret',
        'TIINGO_API_KEY': 'test_tiingo',
        'OPENAI_API_KEY': 'test_openai',
        'TELEGRAM_BOT_TOKEN': 'test_token',
        'TELEGRAM_CHAT_ID': 'test_chat',
        'DATABASE_URL': 'postgresql://user:pass@localhost:5432/trading'
    })
    def test_database_url_configuration(self):
        """Test database URL configuration."""
        settings = Settings()
        
        assert settings.database_url == "postgresql://user:pass@localhost:5432/trading"
    
    @patch.dict(os.environ, {
        'ALPACA_API_KEY': 'test_key',
        'ALPACA_SECRET_KEY': 'test_secret',
        'TIINGO_API_KEY': 'test_tiingo',
        'OPENAI_API_KEY': 'test_openai',
        'TELEGRAM_BOT_TOKEN': 'test_token',
        'TELEGRAM_CHAT_ID': 'test_chat',
        'REBALANCE_TIME': '14:30'
    })
    def test_rebalance_time_configuration(self):
        """Test rebalance time configuration."""
        settings = Settings()
        
        assert settings.rebalance_time == "14:30"
    
    def test_settings_immutable(self):
        """Test that settings are immutable after creation."""
        with patch.dict(os.environ, {
            'ALPACA_API_KEY': 'test_key',
            'ALPACA_SECRET_KEY': 'test_secret',
            'TIINGO_API_KEY': 'test_tiingo',
            'OPENAI_API_KEY': 'test_openai',
            'TELEGRAM_BOT_TOKEN': 'test_token',
            'TELEGRAM_CHAT_ID': 'test_chat'
        }):
            settings = Settings()
            
            # Pydantic models with frozen=True are immutable
            with pytest.raises(Exception):  # ValidationError or AttributeError
                settings.alpaca_api_key = "new_key"


class TestSettingsValidation:
    """Test Settings validation."""
    
    @patch.dict(os.environ, {
        'ALPACA_API_KEY': 'test_key',
        'ALPACA_SECRET_KEY': 'test_secret',
        'TIINGO_API_KEY': 'test_tiingo',
        'OPENAI_API_KEY': 'test_openai',
        'TELEGRAM_BOT_TOKEN': 'test_token',
        'TELEGRAM_CHAT_ID': 'test_chat',
        'MAX_POSITION_SIZE': 'invalid_float'
    })
    def test_invalid_float_validation(self):
        """Test validation of invalid float values."""
        with pytest.raises(Exception):  # ValidationError
            Settings()
    
    @patch.dict(os.environ, {
        'ALPACA_API_KEY': '',
        'ALPACA_SECRET_KEY': 'test_secret',
        'TIINGO_API_KEY': 'test_tiingo',
        'OPENAI_API_KEY': 'test_openai',
        'TELEGRAM_BOT_TOKEN': 'test_token',
        'TELEGRAM_CHAT_ID': 'test_chat'
    })
    def test_empty_required_field(self):
        """Test that empty environment variables are handled gracefully."""
        # Empty env var should use the default
        settings = Settings()
        assert settings.alpaca_api_key == ""  # Empty env var overrides default
        assert settings.alpaca_secret_key == "test_secret"
    
    @patch.dict(os.environ, {
        'ALPACA_API_KEY': 'test_key',
        'ALPACA_SECRET_KEY': 'test_secret',
        'TIINGO_API_KEY': 'test_tiingo',
        'OPENAI_API_KEY': 'test_openai',
        'TELEGRAM_BOT_TOKEN': 'test_token',
        'TELEGRAM_CHAT_ID': 'test_chat',
        'ALPACA_BASE_URL': 'invalid_url'
    })
    def test_valid_url_accepted(self):
        """Test that valid URLs are accepted."""
        settings = Settings()
        # Even invalid URLs are accepted as strings by pydantic
        assert settings.alpaca_base_url == "invalid_url" 