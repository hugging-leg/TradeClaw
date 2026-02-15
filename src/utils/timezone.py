"""
统一时区工具

设计原则：
- 所有内部时间一律使用 UTC aware datetime
- 仅在展示给用户时转换为交易时区
- 服务器时区不确定，禁止使用 datetime.now() (naive) 或 datetime.utcnow()
- 统一入口，避免各模块各自处理时区
"""

from datetime import datetime, timezone
from typing import Optional

import pytz

from config import settings


# UTC 时区常量
UTC = timezone.utc

# 交易时区（从配置读取，仅用于展示）
_trading_tz: Optional[pytz.BaseTzInfo] = None


def get_trading_timezone() -> pytz.BaseTzInfo:
    """获取交易时区对象（带缓存）"""
    global _trading_tz
    if _trading_tz is None:
        _trading_tz = pytz.timezone(settings.trading_timezone)
    return _trading_tz


def utc_now() -> datetime:
    """
    获取当前 UTC 时间（timezone-aware）

    这是项目中获取 "当前时间" 的唯一推荐方式。
    禁止使用 datetime.now() / datetime.utcnow()。
    """
    return datetime.now(UTC)


def to_trading_tz(dt: datetime) -> datetime:
    """
    将 UTC 时间转换为交易时区（仅用于展示）

    Args:
        dt: UTC aware datetime

    Returns:
        交易时区的 datetime
    """
    if dt.tzinfo is None:
        # 假设 naive datetime 是 UTC
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(get_trading_timezone())


def format_for_display(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S %Z") -> str:
    """
    格式化时间用于展示（转换为交易时区）

    Args:
        dt: UTC aware datetime
        fmt: 格式字符串

    Returns:
        格式化后的字符串（交易时区）
    """
    return to_trading_tz(dt).strftime(fmt)


def ensure_utc(dt: datetime) -> datetime:
    """
    确保 datetime 是 UTC aware 的

    - 如果已有 tzinfo 且不是 UTC，则转换为 UTC
    - 如果是 naive，假设为 UTC 并附加时区
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
