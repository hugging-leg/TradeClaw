import os
from typing import Optional
from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    # Trading APIs
    alpaca_api_key: str = Field(..., env="ALPACA_API_KEY")
    alpaca_secret_key: str = Field(..., env="ALPACA_SECRET_KEY")
    alpaca_base_url: str = Field("https://paper-api.alpaca.markets", env="ALPACA_BASE_URL")
    tiingo_api_key: str = Field(..., env="TIINGO_API_KEY")
    
    # OpenAI API
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    openai_model: str = Field("gpt-4o", env="OPENAI_MODEL")
    
    # Telegram Bot
    telegram_bot_token: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(..., env="TELEGRAM_CHAT_ID")
    
    # Redis for event system (optional - will use in-memory events if not provided)
    redis_url: Optional[str] = Field(None, env="REDIS_URL")
    
    # Database
    database_url: str = Field("sqlite:///./trading_agent.db", env="DATABASE_URL")
    
    # Trading Parameters
    max_position_size: float = Field(0.1, env="MAX_POSITION_SIZE")
    rebalance_time: str = Field("09:30", env="REBALANCE_TIME")
    stop_loss_percentage: float = Field(0.05, env="STOP_LOSS_PERCENTAGE")
    take_profit_percentage: float = Field(0.15, env="TAKE_PROFIT_PERCENTAGE")
    
    # Environment
    environment: str = Field("development", env="ENVIRONMENT")
    log_level: str = Field("INFO", env="LOG_LEVEL")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings() 