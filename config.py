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
    eod_analysis_time: str = "16:05"
    stop_loss_percentage: float = 0.05
    take_profit_percentage: float = 0.15

    # === 风控配置 ===
    risk_management_enabled: bool = True
    daily_loss_limit_percentage: float = 0.10
    max_position_concentration: float = 0.25

    # === 告警阈值 ===
    portfolio_pnl_alert_threshold: float = 0.05
    position_loss_alert_threshold: float = 0.10

    # === 实时监控配置 ===
    price_change_threshold: float = 5.0
    volatility_threshold: float = 8.0
    rebalance_cooldown_seconds: int = 3600
    market_etfs: str = "SPY,QQQ,IWM"

    # === 调度配置 ===
    portfolio_check_interval: int = 60
    risk_check_interval: int = 15
    min_workflow_interval_minutes: int = 30
    scheduler_misfire_grace_time: int = 60  # APScheduler misfire grace time (seconds)
    scheduler_max_history: int = 200  # 调度器执行历史最大保留条数
    max_pending_llm_jobs: int = 5  # LLM 自主调度最大待执行任务数
    message_rate_limit: float = 1.0

    # === LLM Agent 配置 ===
    llm_recursion_limit: int = 64
    llm_max_analysis_history: int = 50
    llm_max_summary_tokens: int = 1500

    # === 均衡组合策略配置 ===
    # === 交易执行配置 ===
    rebalance_min_value_threshold: float = 20.0  # 最小调整市值阈值 ($)
    rebalance_min_pct_threshold: float = 1.0  # 最小调整百分比阈值 (%)
    rebalance_buy_reserve_ratio: float = 0.95  # 买入时预留资金比例
    rebalance_weight_diff_threshold: float = 0.02  # 权重差异阈值 (BL 模式)
    rebalance_order_delay_seconds: float = 1.0  # 连续下单间隔秒数
    cash_keywords: str = "CASH,USD,DOLLAR"  # 现金关键词（逗号分隔）

    # === Black-Litterman 配置 ===
    bl_risk_aversion: float = 2.5
    bl_historical_days: int = 252
    bl_base_variance: float = 0.05
    bl_min_weight: float = 0.01
    bl_default_universe: str = "SPY,QQQ,IWM,AAPL,MSFT,GOOGL,NVDA,AMD,META,GLD,TLT,XLF,XLE"

    # === 认知套利配置 ===
    ca_direct_min_score: int = 7
    ca_direct_max_score: int = 10
    ca_indirect_multiplier: float = 1.5
    ca_min_confidence: int = 3
    ca_score_window_days: int = 7
    ca_top_k: int = 3
    ca_default_holding_days: int = 7
    ca_min_holding_days: int = 3
    ca_max_holding_days: int = 14
    ca_position_size_pct: float = 0.10
    ca_max_positions: int = 5

    # === API 配置 ===
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # === 鉴权配置 ===
    # 用户名 + bcrypt 哈希密码。初始密码通过 scripts/hash_password.py 生成
    auth_username: str = "admin"
    auth_password_hash: str = ""  # 空 = 鉴权关闭（开发模式）
    jwt_secret_key: str = "CHANGE-ME-TO-A-RANDOM-STRING"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 小时

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

    def get_market_etfs(self) -> list[str]:
        if not self.market_etfs:
            return ["SPY", "QQQ", "IWM"]
        return [s.strip().upper() for s in self.market_etfs.split(",") if s.strip()]

    def get_cash_keywords(self) -> list[str]:
        if not self.cash_keywords:
            return []
        return [k.strip().upper() for k in self.cash_keywords.split(",") if k.strip()]

    def get_bl_default_universe(self) -> list[str]:
        if not self.bl_default_universe:
            return []
        return [s.strip().upper() for s in self.bl_default_universe.split(",") if s.strip()]

    def get_cors_origins(self) -> list[str]:
        if not self.api_cors_origins:
            return []
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]

    def get_news_llm_config(self) -> dict:
        """获取新闻过滤 LLM 配置（如果未配置则使用主 LLM）"""
        return {
            "base_url": self.news_llm_base_url or self.llm_base_url,
            "api_key": self.news_llm_api_key or self.llm_api_key,
            "model": self.news_llm_model or self.llm_model,
        }


# Global settings instance
settings = Settings()
