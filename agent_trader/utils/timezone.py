"""
统一时区工具

设计原则：
- 所有内部时间一律使用 UTC aware datetime
- 仅在展示给用户时转换为交易时区
- 服务器时区不确定，禁止使用 datetime.now() (naive) 或 datetime.utcnow()
- 统一入口，避免各模块各自处理时区

回测支持：
- 通过 contextvars 实现 SimulatedClock，utc_now() 自动返回模拟时间
- contextvars 是 per-task 隔离的，回测和实盘可同时运行互不干扰
- 使用 simulated_clock(dt) context manager 或 set_simulated_time/clear_simulated_time
"""

from contextvars import ContextVar
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

import pytz

from config import settings


# UTC 时区常量
UTC = timezone.utc

# 交易时区（从配置读取，仅用于展示）
_trading_tz: Optional[pytz.BaseTzInfo] = None

# 模拟时间（回测用，per-task 隔离）
_simulated_time: ContextVar[Optional[datetime]] = ContextVar(
    "_simulated_time", default=None
)


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

    回测模式下自动返回模拟时间（通过 contextvars 注入）。
    """
    sim = _simulated_time.get()
    if sim is not None:
        return sim
    return datetime.now(UTC)


# ========== 回测时间控制 ==========


def set_simulated_time(dt: datetime) -> None:
    """
    设置当前 task 的模拟时间（回测用）。

    Args:
        dt: UTC aware datetime
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    _simulated_time.set(dt)


def clear_simulated_time() -> None:
    """清除模拟时间，恢复为真实时间。"""
    _simulated_time.set(None)


@contextmanager
def simulated_clock(dt: datetime):
    """
    Context manager: 在 with 块内 utc_now() 返回模拟时间。

    用法:
        with simulated_clock(some_datetime):
            # 这里的 utc_now() 返回 some_datetime
            await workflow.execute(...)

    Args:
        dt: UTC aware datetime
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    token = _simulated_time.set(dt)
    try:
        yield
    finally:
        _simulated_time.reset(token)


# ========== 原有工具函数 ==========


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
