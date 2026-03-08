"""
Settings API — 读取/更新系统配置
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from config import settings

router = APIRouter()

# 可通过 GET /settings 读取的配置字段
# 密钥/Token 类字段不在此列表中 —— 只写不读，避免每次请求都传输密钥
_READABLE_FIELDS = [
    # Trading
    "paper_trading",
    "rebalance_time", "eod_analysis_time",
    "workflow_type", "trading_timezone", "exchange",
    # Risk
    "risk_management_enabled",
    "stop_loss_percentage", "take_profit_percentage",
    "daily_loss_limit_percentage", "max_position_concentration",
    "portfolio_pnl_alert_threshold", "position_loss_alert_threshold",
    # Scheduling
    "portfolio_check_interval", "risk_check_interval",
    "min_workflow_interval_minutes",
    "scheduler_misfire_grace_time", "max_pending_llm_jobs",
    "llm_min_interval_minutes",
    "message_rate_limit",
    # Subagent
    "subagent_max_depth", "subagent_max_parallel", "subagent_default_timeout",
    # Monitoring
    "price_change_threshold", "volatility_threshold",
    "rebalance_cooldown_seconds", "market_etfs",
    # News
    "news_poll_interval_minutes", "news_poll_max_per_batch",
    "news_importance_threshold",
    # Providers
    "broker_provider", "market_data_provider", "realtime_data_provider",
    "news_providers", "message_provider",
    # Endpoints / non-secret connection info (readable)
    "alpaca_base_url", "telegram_chat_id",
    "opensandbox_server_url",
    "playwright_mcp_url",
    # Embedding
    "embedding_provider", "embedding_base_url", "embedding_model",
    # NOTE: LLM configuration is now managed via /api/llm/* endpoints (llm_config.yaml)
    # Rebalance execution
    "rebalance_min_value_threshold", "rebalance_min_pct_threshold",
    "rebalance_buy_reserve_ratio", "rebalance_weight_diff_threshold",
    "rebalance_order_delay_seconds", "cash_keywords",
    # NOTE: bl_* and ca_* params are managed via /api/agent/config
    # API / infra
    "api_host", "api_port", "api_cors_origins",
    # General
    "environment", "log_level", "log_to_file",
]

# 密钥字段 — 只写不读：PATCH 时接受明文新值，GET 时不返回
# NOTE: LLM API keys are now managed via /api/llm/* endpoints (llm_config.yaml)
_WRITE_ONLY_FIELDS = frozenset({
    "alpaca_api_key", "alpaca_secret_key",
    "tiingo_api_key", "finnhub_api_key",
    "unusual_whales_api_key",
    "telegram_bot_token",
    "embedding_api_key",
})

# 绝不可通过 API 修改的字段（可读但不可写）
# 修改这些值要么无效（服务已绑定端口）、要么有安全风险
_FORBIDDEN_FIELDS = frozenset({
    "database_url", "data_dir",
    "api_host", "api_port",  # 修改后 uvicorn 仍监听旧地址，会导致断连
    "auth_username", "auth_password_hash",
    "jwt_secret_key", "jwt_algorithm", "jwt_expire_minutes",
})


class SettingsUpdate(BaseModel):
    """
    可更新的配置 — 所有非禁止的运行时参数。

    所有字段均为 Optional，只发送需要修改的字段即可。
    密钥字段为只写：提交明文新值即可更新，空字符串表示不修改。
    """
    # Trading
    paper_trading: Optional[bool] = None
    rebalance_time: Optional[str] = None
    eod_analysis_time: Optional[str] = None
    trading_timezone: Optional[str] = None
    exchange: Optional[str] = None
    # Risk
    risk_management_enabled: Optional[bool] = None
    stop_loss_percentage: Optional[float] = None
    take_profit_percentage: Optional[float] = None
    daily_loss_limit_percentage: Optional[float] = None
    max_position_concentration: Optional[float] = None
    portfolio_pnl_alert_threshold: Optional[float] = None
    position_loss_alert_threshold: Optional[float] = None
    # Scheduling
    portfolio_check_interval: Optional[int] = None
    risk_check_interval: Optional[int] = None
    min_workflow_interval_minutes: Optional[int] = None
    scheduler_misfire_grace_time: Optional[int] = None
    max_pending_llm_jobs: Optional[int] = None
    llm_min_interval_minutes: Optional[int] = None
    message_rate_limit: Optional[float] = None
    # Subagent
    subagent_max_depth: Optional[int] = None
    subagent_max_parallel: Optional[int] = None
    subagent_default_timeout: Optional[int] = None
    # Monitoring
    price_change_threshold: Optional[float] = None
    volatility_threshold: Optional[float] = None
    rebalance_cooldown_seconds: Optional[int] = None
    market_etfs: Optional[str] = None
    # News
    news_poll_interval_minutes: Optional[int] = None
    news_poll_max_per_batch: Optional[int] = None
    news_importance_threshold: Optional[int] = None
    # Providers
    broker_provider: Optional[str] = None
    market_data_provider: Optional[str] = None
    realtime_data_provider: Optional[str] = None
    news_providers: Optional[str] = None
    message_provider: Optional[str] = None
    # API Keys (BYO key)
    alpaca_api_key: Optional[str] = None
    alpaca_secret_key: Optional[str] = None
    alpaca_base_url: Optional[str] = None
    opensandbox_server_url: Optional[str] = None
    playwright_mcp_url: Optional[str] = None
    tiingo_api_key: Optional[str] = None
    finnhub_api_key: Optional[str] = None
    unusual_whales_api_key: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    # NOTE: LLM configuration is now managed via /api/llm/* endpoints (llm_config.yaml)
    # Rebalance execution
    rebalance_min_value_threshold: Optional[float] = None
    rebalance_min_pct_threshold: Optional[float] = None
    rebalance_buy_reserve_ratio: Optional[float] = None
    rebalance_weight_diff_threshold: Optional[float] = None
    rebalance_order_delay_seconds: Optional[float] = None
    cash_keywords: Optional[str] = None
    # NOTE: bl_* and ca_* params are managed via /api/agent/config
    # API / infra
    api_cors_origins: Optional[str] = None
    # General
    environment: Optional[str] = None
    log_level: Optional[str] = None
    log_to_file: Optional[bool] = None


def _build_readable_dict() -> dict:
    """构建可读配置字典 — 密钥字段不包含在内"""
    result = {}
    for field in _READABLE_FIELDS:
        result[field] = getattr(settings, field, None)
    return result


@router.get("/settings")
async def get_settings():
    """获取当前配置 — 密钥字段不返回"""
    return _build_readable_dict()


@router.patch("/settings")
async def update_settings(update: SettingsUpdate):
    """
    运行时更新配置参数

    注意：仅修改内存中的值，不持久化到 .env 文件。
    重启后恢复为 .env / 环境变量中的值。
    密钥字段为只写：提交非空明文新值即可更新。
    """
    updated = {}
    for field, value in update.model_dump(exclude_none=True).items():
        if field in _FORBIDDEN_FIELDS:
            continue
        # 密钥字段：空字符串视为"不修改"
        if field in _WRITE_ONLY_FIELDS:
            if not isinstance(value, str) or not value.strip():
                continue
            value = value.strip()
        if hasattr(settings, field):
            setattr(settings, field, value)
            # 密钥字段更新成功后只返回确认，不回显值
            updated[field] = "(updated)" if field in _WRITE_ONLY_FIELDS else value

    # If opensandbox_server_url changed, reset sandbox availability cache
    if "opensandbox_server_url" in updated:
        try:
            from agent_trader.agents.tools.code_sandbox_tools import OpenSandboxBackend
            OpenSandboxBackend.get_instance().reset_availability()
        except Exception:
            pass

    # If playwright_mcp_url changed, reset browser MCP availability cache
    if "playwright_mcp_url" in updated:
        try:
            from agent_trader.agents.tools.browser_tools import PlaywrightMCPClient
            PlaywrightMCPClient.get_instance().reset_availability()
        except Exception:
            pass

    return {
        "updated": updated,
        "current": _build_readable_dict(),
    }
