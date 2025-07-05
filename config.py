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
    
    # OpenAI API
    openai_api_key: str = "test_key"
    openai_model: str = "gpt-4o"
    
    # Telegram Bot
    telegram_bot_token: str = "test_token"
    telegram_chat_id: str = "test_chat_id"
    
    # Database
    postgres_password: Optional[str] = None
    database_url: str = "sqlite:///./trading_agent.db"
    
    # Redis for event system (optional - will use in-memory events if not provided)
    redis_url: Optional[str] = None
    redis_password: Optional[str] = None
    use_redis: bool = False
    
    # Trading Parameters
    paper_trading: bool = True
    max_position_size: float = 0.1
    max_positions: int = 10
    rebalance_time: str = "09:30"
    daily_rebalance_time: str = "09:30"  # Alias for rebalance_time
    stop_loss_percentage: float = 0.05
    take_profit_percentage: float = 0.15
    
    # Environment
    environment: str = "development"
    log_level: str = "INFO"
    log_to_file: bool = True
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore extra environment variables
        frozen=True  # Make settings immutable
    )


# Global settings instance
settings = Settings() 