"""
时间计算工具 - 使用 exchange_calendars 处理交易日

注意：
- 禁止简化！必须使用 exchange_calendars 检查节假日
- 所有时间操作都应该是时区感知的
- 服务器时区可能与交易时区不同，必须显式转换
"""

from src.utils.logging_config import get_logger
from datetime import datetime, timedelta
from typing import Optional
import pytz

logger = get_logger(__name__)

# 尝试导入 exchange_calendars
try:
    import exchange_calendars as xcals
    import pandas as pd
    XCALS_AVAILABLE = True
except ImportError:
    XCALS_AVAILABLE = False
    logger.warning("exchange_calendars 未安装，时间计算将不准确。运行: pip install exchange_calendars")


def get_default_exchange() -> str:
    """获取默认交易所（从配置）"""
    try:
        from config import settings
        return settings.exchange
    except Exception:
        return 'XNYS'


def get_default_timezone() -> str:
    """获取默认交易时区（从配置）"""
    try:
        from config import settings
        return settings.trading_timezone
    except Exception:
        return 'US/Eastern'


# 缓存日历实例避免重复创建
_calendar_cache = {}


def get_calendar(exchange: str = 'XNYS'):
    """
    获取交易日历实例（带缓存）

    Args:
        exchange: 交易所代码，默认 XNYS (NYSE)

    Returns:
        exchange_calendars 日历实例

    Raises:
        RuntimeError: 如果 exchange_calendars 不可用
    """
    if not XCALS_AVAILABLE:
        raise RuntimeError(
            "exchange_calendars 未安装。请运行: pip install exchange_calendars"
        )

    if exchange not in _calendar_cache:
        _calendar_cache[exchange] = xcals.get_calendar(exchange)
        logger.info(f"已加载交易日历: {exchange}")

    return _calendar_cache[exchange]


def parse_time_config(time_str: str) -> tuple[int, int]:
    """
    解析时间配置字符串 (HH:MM 格式)

    Args:
        time_str: 时间字符串，如 "09:30", "16:05"

    Returns:
        (hour, minute) 元组

    Raises:
        ValueError: 格式无效时
    """
    try:
        parts = time_str.strip().split(":")
        if len(parts) != 2:
            raise ValueError(f"无效的时间格式: {time_str}. 期望 HH:MM")

        hour = int(parts[0])
        minute = int(parts[1])

        if not (0 <= hour <= 23):
            raise ValueError(f"无效的小时: {hour}. 必须 0-23")
        if not (0 <= minute <= 59):
            raise ValueError(f"无效的分钟: {minute}. 必须 0-59")

        return hour, minute

    except (ValueError, IndexError) as e:
        logger.error(f"解析时间配置失败 '{time_str}': {e}")
        raise ValueError(f"无效的时间配置: {time_str}") from e


def is_trading_day(
    dt: Optional[datetime] = None,
    exchange: str = 'XNYS',
    timezone: str = 'US/Eastern'
) -> bool:
    """
    检查是否为交易日（考虑节假日）

    Args:
        dt: 要检查的日期时间（默认当前时间）
        exchange: 交易所代码
        timezone: 时区

    Returns:
        是否为交易日

    Raises:
        RuntimeError: 如果无法获取交易日历
    """
    tz = pytz.timezone(timezone)
    check_dt = dt or datetime.now(tz)

    # 确保时区感知
    if check_dt.tzinfo is None:
        check_dt = tz.localize(check_dt)

    try:
        calendar = get_calendar(exchange)
        return calendar.is_session(check_dt.date())
    except Exception as e:
        logger.error(f"检查交易日失败: {e}")
        raise RuntimeError(f"无法确定是否为交易日: {e}") from e


def is_market_open(
    dt: Optional[datetime] = None,
    exchange: str = 'XNYS',
    timezone: str = 'US/Eastern'
) -> bool:
    """
    检查市场是否开放

    Args:
        dt: 要检查的日期时间（默认当前时间）
        exchange: 交易所代码
        timezone: 时区

    Returns:
        市场是否开放

    Raises:
        RuntimeError: 如果无法获取交易日历
    """
    tz = pytz.timezone(timezone)
    check_dt = dt or datetime.now(tz)

    # 确保时区感知
    if check_dt.tzinfo is None:
        check_dt = tz.localize(check_dt)

    try:
        calendar = get_calendar(exchange)
        ts = pd.Timestamp(check_dt)
        return calendar.is_open_on_minute(ts)
    except Exception as e:
        logger.error(f"检查市场状态失败: {e}")
        raise RuntimeError(f"无法确定市场状态: {e}") from e


def get_next_trading_day(
    dt: Optional[datetime] = None,
    exchange: str = 'XNYS',
    timezone: str = 'US/Eastern'
) -> datetime:
    """
    获取下一个交易日

    Args:
        dt: 起始日期时间（默认当前时间）
        exchange: 交易所代码
        timezone: 时区

    Returns:
        下一个交易日的日期（带时区）

    Raises:
        RuntimeError: 如果无法获取交易日历
    """
    tz = pytz.timezone(timezone)
    check_dt = dt or datetime.now(tz)

    if check_dt.tzinfo is None:
        check_dt = tz.localize(check_dt)

    try:
        calendar = get_calendar(exchange)
        check_date = pd.Timestamp(check_dt.date())

        # 查找大于当前日期的所有交易日
        future_sessions = calendar.sessions[calendar.sessions > check_date]

        if len(future_sessions) == 0:
            raise RuntimeError("没有可用的未来交易日")

        next_session = future_sessions[0]
        result_dt = datetime.combine(next_session.date(), datetime.min.time())
        return tz.localize(result_dt)
    except Exception as e:
        logger.error(f"获取下一个交易日失败: {e}")
        raise RuntimeError(f"无法获取下一个交易日: {e}") from e


def get_next_market_open(
    dt: Optional[datetime] = None,
    exchange: str = 'XNYS',
    timezone: str = 'US/Eastern'
) -> datetime:
    """
    获取下一个市场开放时间

    Args:
        dt: 起始日期时间（默认当前时间）
        exchange: 交易所代码
        timezone: 时区

    Returns:
        下一个市场开放时间（带时区）

    Raises:
        RuntimeError: 如果无法获取交易日历
    """
    tz = pytz.timezone(timezone)
    check_dt = dt or datetime.now(tz)

    if check_dt.tzinfo is None:
        check_dt = tz.localize(check_dt)

    try:
        calendar = get_calendar(exchange)
        # 正确创建 UTC 时间戳
        utc_dt = check_dt.astimezone(pytz.UTC)
        ts = pd.Timestamp(utc_dt.replace(tzinfo=None), tz='UTC')

        next_open = calendar.next_open(ts)
        # 转换回目标时区
        return next_open.tz_convert(timezone).to_pydatetime()
    except Exception as e:
        logger.error(f"获取下一个市场开放时间失败: {e}")
        raise RuntimeError(f"无法获取下一个市场开放时间: {e}") from e


def get_next_market_close(
    dt: Optional[datetime] = None,
    exchange: str = 'XNYS',
    timezone: str = 'US/Eastern'
) -> datetime:
    """
    获取下一个市场关闭时间

    Args:
        dt: 起始日期时间（默认当前时间）
        exchange: 交易所代码
        timezone: 时区

    Returns:
        下一个市场关闭时间（带时区）

    Raises:
        RuntimeError: 如果无法获取交易日历
    """
    tz = pytz.timezone(timezone)
    check_dt = dt or datetime.now(tz)

    if check_dt.tzinfo is None:
        check_dt = tz.localize(check_dt)

    try:
        calendar = get_calendar(exchange)
        # 正确创建 UTC 时间戳
        utc_dt = check_dt.astimezone(pytz.UTC)
        ts = pd.Timestamp(utc_dt.replace(tzinfo=None), tz='UTC')

        next_close = calendar.next_close(ts)
        # 转换回目标时区
        return next_close.tz_convert(timezone).to_pydatetime()
    except Exception as e:
        logger.error(f"获取下一个市场关闭时间失败: {e}")
        raise RuntimeError(f"无法获取下一个市场关闭时间: {e}") from e


def calculate_next_trading_day_time(
    hour: int,
    minute: int,
    timezone: pytz.tzinfo.BaseTzInfo = None,
    exchange: str = None
) -> datetime:
    """
    计算下一个交易日的指定时间

    Args:
        hour: 目标小时 (0-23)
        minute: 目标分钟 (0-59)
        timezone: 时区对象（默认使用配置）
        exchange: 交易所代码（默认使用配置）

    Returns:
        下一个交易日的指定时间（时区感知）

    Raises:
        RuntimeError: 如果无法获取交易日历
    """
    if timezone is None:
        timezone = pytz.timezone(get_default_timezone())
    exchange = exchange or get_default_exchange()

    now = datetime.now(timezone)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # 如果今天的目标时间已过，从明天开始
    if target <= now:
        target += timedelta(days=1)

    try:
        calendar = get_calendar(exchange)

        # 循环查找下一个交易日
        while not calendar.is_session(target.date()):
            target += timedelta(days=1)

        return target

    except Exception as e:
        logger.error(f"计算下一个交易日时间失败: {e}")
        raise RuntimeError(f"无法计算下一个交易日时间: {e}") from e


def calculate_next_interval(
    interval_minutes: int,
    timezone: pytz.tzinfo.BaseTzInfo = None,
    market_hours_only: bool = True,
    exchange: str = None
) -> datetime:
    """
    计算下一个间隔时间点（市场时间内）

    Args:
        interval_minutes: 间隔分钟数
        timezone: 时区对象（默认使用配置）
        market_hours_only: 是否只在市场时间内
        exchange: 交易所代码（默认使用配置）

    Returns:
        下一个间隔时间点

    Raises:
        RuntimeError: 如果无法获取交易日历
    """
    if timezone is None:
        timezone = pytz.timezone(get_default_timezone())
    exchange = exchange or get_default_exchange()
    now = datetime.now(timezone)

    # 计算下一个间隔
    if interval_minutes >= 60:
        hours_interval = interval_minutes // 60
        next_time = (now + timedelta(hours=hours_interval)).replace(
            minute=30, second=0, microsecond=0
        )
    else:
        minutes = ((now.minute // interval_minutes) + 1) * interval_minutes
        if minutes >= 60:
            next_time = (now + timedelta(hours=1)).replace(
                minute=0, second=0, microsecond=0
            )
        else:
            next_time = now.replace(minute=minutes, second=0, microsecond=0)

    if not market_hours_only:
        return next_time

    # 检查是否在市场时间内
    try:
        calendar = get_calendar(exchange)
        # 正确创建 UTC 时间戳
        utc_dt = next_time.astimezone(pytz.UTC)
        ts = pd.Timestamp(utc_dt.replace(tzinfo=None), tz='UTC')

        if calendar.is_open_on_minute(ts):
            return next_time
        else:
            # 返回下一个市场开放后 30 分钟
            next_open = calendar.next_open(ts)
            result = (next_open + pd.Timedelta(minutes=30))
            return result.tz_convert(str(timezone)).to_pydatetime()

    except Exception as e:
        logger.error(f"计算下一个间隔时间失败: {e}")
        raise RuntimeError(f"无法计算下一个间隔时间: {e}") from e
