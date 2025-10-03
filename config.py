import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    # Trading APIs
    alpaca_api_key: str = "test_key"
    alpaca_secret_key: str = "test_secret"
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    tiingo_api_key: str = "test_key"
    
    # Provider Configuration
    broker_provider: str = "alpaca"  # Options: "alpaca", "interactive_brokers", "td_ameritrade", "schwab"
    market_data_provider: str = "tiingo"  # Options: "tiingo", "alpha_vantage", "yahoo_finance", "polygon", "finnhub"
    news_provider: str = "tiingo"  # Options: "tiingo", "alpha_vantage", "news_api", "custom"
    message_provider: str = "telegram"  # Options: "telegram", "discord", "slack", "email" (transport layer)
    
    # LLM Configuration
    llm_provider: str = "openai"  # Options: "openai", "deepseek"
    
    # OpenAI API
    openai_api_key: str = "test_key"
    openai_model: str = "gpt-4o"
    
    # DeepSeek API
    deepseek_api_key: str = "test_key"
    deepseek_model: str = "deepseek-chat"
    
    # Workflow Configuration
    workflow_type: str = "sequential"  # Options: "sequential", "tool_calling"
    
    # Telegram Bot
    telegram_bot_token: str = "test_token"
    telegram_chat_id: str = "test_chat_id"
    
    # Database
    postgres_password: Optional[str] = None
    database_url: str = "sqlite:///./trading_agent.db"
    
    # Event system uses in-memory events only
    
    # Trading Parameters
    paper_trading: bool = True
    max_position_size: float = 0.1
    max_positions: int = 10
    rebalance_time: str = "09:30"  # US/Eastern time - system auto-converts to local time
    stop_loss_percentage: float = 0.05
    take_profit_percentage: float = 0.15
    
    # Scheduling Intervals (in minutes)
    portfolio_check_interval: int = 60  # Portfolio check interval (default: hourly)
    risk_check_interval: int = 15  # Risk check interval (default: every 15 minutes)
    
    # Environment
    environment: str = "development"
    log_level: str = "INFO"
    log_to_file: bool = True
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore extra environment variables
    )


# Global settings instance
settings = Settings() 