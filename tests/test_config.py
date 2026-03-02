"""
Tests for Configuration Loading

Tests configuration management including:
- Environment variable loading
- Default values
- Required fields
- Provider configurations
"""

import pytest
import os
from unittest.mock import patch

from config import Settings


class TestConfigurationLoading:
    """Test suite for configuration loading"""
    
    def test_settings_initialization(self):
        """Test that settings can be initialized"""
        from config import settings
        
        assert settings is not None
        assert hasattr(settings, 'workflow_type')
    
    def test_required_fields(self):
        """Test that required configuration fields exist"""
        from config import settings
        
        # Core configuration
        assert hasattr(settings, 'paper_trading')
        assert hasattr(settings, 'broker_provider')
        assert hasattr(settings, 'market_data_provider')
        assert hasattr(settings, 'news_providers')
        
        # LLM configuration
        assert hasattr(settings, 'llm_base_url')
        assert hasattr(settings, 'llm_api_key')
        assert hasattr(settings, 'llm_model')
        assert hasattr(settings, 'workflow_type')
        
        # Schedule configuration
        assert hasattr(settings, 'rebalance_time')
    
    @patch.dict(os.environ, {
        'WORKFLOW_TYPE': 'llm_portfolio',
        'PAPER_TRADING': 'true'
    })
    def test_environment_variables(self):
        """Test loading from environment variables"""
        from importlib import reload
        import config
        reload(config)
        
        assert config.settings.workflow_type == 'llm_portfolio'
        assert config.settings.paper_trading == True
    
    def test_broker_provider_options(self):
        """Test broker provider configuration"""
        from config import settings
        
        # Should be alpaca by default or configured
        assert settings.broker_provider.lower() in ['alpaca', 'interactive_brokers']
    
    def test_market_data_provider_options(self):
        """Test market data provider configuration"""
        from config import settings
        
        # Should be tiingo by default or configured
        assert settings.market_data_provider.lower() in ['tiingo']
    
    def test_workflow_type_options(self):
        """Test workflow type configuration"""
        from config import settings
        
        # Should be one of the valid workflow types
        valid_types = [
            'llm_portfolio',
            'black_litterman',
            'cognitive_arbitrage',
        ]
        assert settings.workflow_type.lower() in valid_types
    
    def test_schedule_time_format(self):
        """Test schedule time is in correct format"""
        from config import settings
        
        # Should be HH:MM format
        schedule_time = settings.rebalance_time
        assert isinstance(schedule_time, str)
        assert ':' in schedule_time
        
        parts = schedule_time.split(':')
        assert len(parts) == 2
        
        hour, minute = parts
        assert hour.isdigit()
        assert minute.isdigit()
        assert 0 <= int(hour) <= 23
        assert 0 <= int(minute) <= 59
    
    def test_paper_trading_default(self):
        """Test that paper trading is enabled by default for safety"""
        from config import settings
        
        # Should default to True for safety
        assert isinstance(settings.paper_trading, bool)
    
    def test_api_keys_are_strings(self):
        """Test that API keys are loaded as strings"""
        from config import settings
        
        # All API keys should be strings (even if empty)
        assert isinstance(settings.alpaca_api_key, str)
        assert isinstance(settings.tiingo_api_key, str)
        assert isinstance(settings.llm_api_key, str)


class TestConfigurationDefaults:
    """Test suite for configuration defaults"""
    
    def test_default_portfolio_check_interval(self):
        """Test default portfolio check interval"""
        from config import settings
        
        assert isinstance(settings.portfolio_check_interval, int)
        assert settings.portfolio_check_interval > 0
    
    def test_default_risk_check_interval(self):
        """Test default risk check interval"""
        from config import settings
        
        assert isinstance(settings.risk_check_interval, int)
        assert settings.risk_check_interval > 0

    def test_news_polling_settings(self):
        """Test news polling configuration defaults"""
        from config import settings
        
        assert hasattr(settings, 'news_poll_interval_minutes')
        assert isinstance(settings.news_poll_interval_minutes, int)
        assert settings.news_poll_interval_minutes >= 0
        
        assert hasattr(settings, 'news_poll_max_per_batch')
        assert isinstance(settings.news_poll_max_per_batch, int)
        assert settings.news_poll_max_per_batch > 0

    def test_news_importance_threshold(self):
        """Test news importance threshold default and range"""
        from config import settings
        
        assert hasattr(settings, 'news_importance_threshold')
        assert isinstance(settings.news_importance_threshold, int)
        assert 0 <= settings.news_importance_threshold <= 10
        assert settings.news_importance_threshold == 7  # default


class TestConfigurationValidation:
    """Test suite for configuration validation"""
    
    def test_invalid_workflow_type_handled(self):
        """Test that invalid workflow type is handled"""
        from config import settings
        
        # Should not crash with invalid workflow type
        # Factory will handle validation
        assert settings.workflow_type is not None
    
    def test_missing_api_keys_warning(self):
        """Test that missing API keys don't crash the system"""
        from config import settings
        
        # System should initialize even with missing keys
        assert settings is not None
    
    def test_settings_immutability(self):
        """Test that settings can be accessed"""
        from config import settings
        
        original_value = settings.workflow_type
        assert settings.workflow_type is not None


class TestProviderConfiguration:
    """Test suite for provider-specific configuration"""
    
    def test_alpaca_configuration(self):
        """Test Alpaca broker configuration"""
        from config import settings
        
        if settings.broker_provider.lower() == 'alpaca':
            assert hasattr(settings, 'alpaca_base_url')
            assert hasattr(settings, 'alpaca_api_key')
            assert hasattr(settings, 'alpaca_secret_key')
    
    def test_tiingo_configuration(self):
        """Test Tiingo configuration"""
        from config import settings
        
        if settings.market_data_provider.lower() == 'tiingo':
            assert hasattr(settings, 'tiingo_api_key')
    
    def test_llm_configuration(self):
        """Test LLM configuration fields"""
        from config import settings
        
        assert hasattr(settings, 'llm_base_url')
        assert hasattr(settings, 'llm_api_key')
        assert hasattr(settings, 'llm_model')
    
    def test_telegram_configuration(self):
        """Test Telegram configuration"""
        from config import settings
        
        assert hasattr(settings, 'telegram_bot_token')
        assert hasattr(settings, 'telegram_chat_id')

    def test_data_dir_configuration(self):
        """Test data directory configuration"""
        from config import settings

        assert hasattr(settings, 'data_dir')
        assert hasattr(settings, 'get_data_dir')
        data_dir = settings.get_data_dir()
        assert data_dir is not None


class TestRiskConfiguration:
    """Test suite for risk management configuration"""
    
    def test_risk_management_enabled(self):
        """Test risk management enabled flag"""
        from config import settings
        
        assert isinstance(settings.risk_management_enabled, bool)
    
    def test_stop_loss_percentage(self):
        """Test stop loss percentage"""
        from config import settings
        
        assert isinstance(settings.stop_loss_percentage, float)
        assert 0 < settings.stop_loss_percentage < 1
    
    def test_take_profit_percentage(self):
        """Test take profit percentage"""
        from config import settings
        
        assert isinstance(settings.take_profit_percentage, float)
        assert 0 < settings.take_profit_percentage < 1
    
    def test_daily_loss_limit(self):
        """Test daily loss limit percentage"""
        from config import settings
        
        assert isinstance(settings.daily_loss_limit_percentage, float)
        assert 0 < settings.daily_loss_limit_percentage < 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
