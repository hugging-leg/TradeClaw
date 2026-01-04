import os
from pathlib import Path
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support"""

    # === 数据路径配置 ===
    data_dir: str = "./user_data"

    # === 时区配置 ===
    trading_timezone: str = "US/Eastern"
    exchange: str = "XNYS"

    # === Trading APIs ===

    # Alpaca
    alpaca_api_key: str = "test_key"
    alpaca_secret_key: str = "test_secret"
    alpaca_base_url: str = "https://paper-api.alpaca.markets"

    # Tiingo
    tiingo_api_key: str = "test_key"

    # Interactive Brokers
    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 7497
    ibkr_client_id: int = 1
    ibkr_account: Optional[str] = None
    ibkr_readonly: bool = False

    # Unusual Whales
    unusual_whales_api_key: Optional[str] = None
    unusual_whales_base_url: str = "https://api.unusualwhales.com"

    # Finnhub
    finnhub_api_key: Optional[str] = None

    # === 提供商配置 ===
    broker_provider: str = "alpaca"
    market_data_provider: str = "tiingo"
    realtime_data_provider: str = "finnhub"
    news_providers: str = "tiingo,finnhub"
    message_provider: str = "telegram"

    # === LLM 配置 (OpenAI 兼容格式) ===
    # 主 LLM (Agent Workflow 使用)
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = "test_key"
    llm_model: str = "gpt-4o"

    # 新闻过滤 LLM (独立配置，可用便宜模型)
    # 如果未配置，使用主 LLM
    news_llm_base_url: Optional[str] = None
    news_llm_api_key: Optional[str] = None
    news_llm_model: Optional[str] = None

    # === Workflow 配置 ===
    workflow_type: str = "llm_portfolio"

    # === Telegram 配置 ===
    telegram_bot_token: str = "test_token"
    telegram_chat_id: str = "test_chat_id"

    # === 数据库配置 (SQLite, 存储在 user_data/) ===
    database_url: Optional[str] = None

    # === 交易参数 ===
    paper_trading: bool = True
    max_position_size: float = 0.1
    max_positions: int = 10
    rebalance_time: str = "09:30"
    stop_loss_percentage: float = 0.05
    take_profit_percentage: float = 0.15

    # === 风控配置 ===
    risk_management_enabled: bool = True
    daily_loss_limit_percentage: float = 0.10
    max_position_concentration: float = 0.25

    # === 实时监控配置 ===
    price_change_threshold: float = 5.0
    volatility_threshold: float = 8.0
    rebalance_cooldown_seconds: int = 3600

    # === 调度配置 ===
    portfolio_check_interval: int = 60
    risk_check_interval: int = 15

    # === 环境配置 ===
    environment: str = "development"
    log_level: str = "INFO"
    log_to_file: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def get_data_dir(self) -> Path:
        path = Path(self.data_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        db_path = self.get_data_dir() / "trading_agent.db"
        return f"sqlite:///{db_path}"

    def get_log_dir(self) -> Path:
        path = self.get_data_dir() / "logs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_news_providers(self) -> list[str]:
        if not self.news_providers:
            return ["tiingo"]
        return [p.strip() for p in self.news_providers.split(",") if p.strip()]

    def get_news_llm_config(self) -> dict:
        """获取新闻过滤 LLM 配置（如果未配置则使用主 LLM）"""
        return {
            "base_url": self.news_llm_base_url or self.llm_base_url,
            "api_key": self.news_llm_api_key or self.llm_api_key,
            "model": self.news_llm_model or self.llm_model,
        }


# Global settings instance
settings = Settings()
