"""
Settings API — 读取/更新系统配置
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from config import settings

router = APIRouter()

# 可通过 API 读取的配置字段（安全字段，不含密钥）
_READABLE_FIELDS = [
    "paper_trading", "max_position_size", "max_positions",
    "rebalance_time", "eod_analysis_time",
    "stop_loss_percentage", "take_profit_percentage",
    "daily_loss_limit_percentage", "max_position_concentration",
    "portfolio_pnl_alert_threshold", "position_loss_alert_threshold",
    "price_change_threshold", "volatility_threshold",
    "portfolio_check_interval", "risk_check_interval",
    "min_workflow_interval_minutes",
    "workflow_type", "trading_timezone", "exchange",
    "broker_provider", "market_data_provider", "news_providers",
    "llm_model", "llm_recursion_limit",
    "environment",
]


class SettingsUpdate(BaseModel):
    """可更新的配置子集（运行时可安全修改的参数）"""
    stop_loss_percentage: Optional[float] = None
    take_profit_percentage: Optional[float] = None
    daily_loss_limit_percentage: Optional[float] = None
    max_position_concentration: Optional[float] = None
    portfolio_pnl_alert_threshold: Optional[float] = None
    position_loss_alert_threshold: Optional[float] = None
    price_change_threshold: Optional[float] = None
    volatility_threshold: Optional[float] = None
    min_workflow_interval_minutes: Optional[int] = None


@router.get("/settings")
async def get_settings():
    """获取当前配置（安全字段）"""
    return {field: getattr(settings, field) for field in _READABLE_FIELDS}


@router.patch("/settings")
async def update_settings(update: SettingsUpdate):
    """
    运行时更新配置参数

    注意：仅修改内存中的值，不持久化到 .env 文件。
    重启后恢复为 .env / 环境变量中的值。
    """
    updated = {}
    for field, value in update.model_dump(exclude_none=True).items():
        if hasattr(settings, field):
            setattr(settings, field, value)
            updated[field] = value

    return {
        "updated": updated,
        "current": {field: getattr(settings, field) for field in _READABLE_FIELDS},
    }
