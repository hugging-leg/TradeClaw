"""
Time Calculation Utilities for Trading System

Handles timezone-aware time calculations, trading day scheduling, and market hours.
"""
import logging
from datetime import datetime, timedelta
import pytz

logger = logging.getLogger(__name__)


def parse_time_config(time_str: str) -> tuple[int, int]:
    """
    Parse time configuration string in HH:MM format
    
    Args:
        time_str: Time string in format "HH:MM" (e.g., "09:30", "16:05")
    
    Returns:
        Tuple of (hour, minute)
    
    Raises:
        ValueError: If time_str format is invalid
    """
    try:
        parts = time_str.strip().split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid time format: {time_str}. Expected HH:MM")
        
        hour = int(parts[0])
        minute = int(parts[1])
        
        if not (0 <= hour <= 23):
            raise ValueError(f"Invalid hour: {hour}. Must be 0-23")
        if not (0 <= minute <= 59):
            raise ValueError(f"Invalid minute: {minute}. Must be 0-59")
        
        return hour, minute
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing time config '{time_str}': {e}")
        # Fallback to market open time
        logger.warning("Falling back to default time 09:30")
        return 9, 30


def calculate_next_trading_day_time(hour: int, minute: int, timezone: pytz.tzinfo.BaseTzInfo) -> datetime:
    """
    Calculate next occurrence of specific time on a trading day (Mon-Fri)
    
    Args:
        hour: Target hour (0-23)
        minute: Target minute (0-59)
        timezone: Timezone for calculation (e.g., pytz.timezone('US/Eastern'))
    
    Returns:
        Next scheduled datetime (timezone-aware)
    """
    now = datetime.now(timezone)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    # If time has passed today, move to tomorrow
    if target <= now:
        target += timedelta(days=1)
    
    # Skip weekends
    while target.weekday() >= 5:  # 5=Saturday, 6=Sunday
        target += timedelta(days=1)
    
    return target


def calculate_next_interval(
    interval_minutes: int,
    timezone: pytz.tzinfo.BaseTzInfo,
    market_hours_only: bool = True,
    market_open_hour: int = 9,
    market_close_hour: int = 16
) -> datetime:
    """
    Calculate next occurrence of a time interval during market hours
    
    Args:
        interval_minutes: Interval in minutes (e.g., 15, 60)
        timezone: Timezone for calculation
        market_hours_only: If True, only schedule during market hours
        market_open_hour: Market opening hour (default 9 for 9:00 AM)
        market_close_hour: Market closing hour (default 16 for 4:00 PM)
    
    Returns:
        Next scheduled datetime (timezone-aware)
    """
    now = datetime.now(timezone)
    
    # Calculate next interval
    if interval_minutes >= 60:
        # For intervals >= 1 hour, align to hour boundaries
        hours_interval = interval_minutes // 60
        next_time = (now + timedelta(hours=hours_interval)).replace(
            minute=30, second=0, microsecond=0
        )
    else:
        # For sub-hour intervals, round up to next interval mark
        minutes = ((now.minute // interval_minutes) + 1) * interval_minutes
        if minutes >= 60:
            next_time = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        else:
            next_time = now.replace(minute=minutes, second=0, microsecond=0)
    
    # If market hours only, check if within market hours
    if market_hours_only:
        # If outside market hours, move to next market day opening
        if next_time.hour < market_open_hour or next_time.hour >= market_close_hour:
            return calculate_next_trading_day_time(market_open_hour, 30, timezone)
        
        # Skip weekends
        while next_time.weekday() >= 5:
            next_time = calculate_next_trading_day_time(market_open_hour, 30, timezone)
    else:
        # Skip weekends even if not market hours only
        while next_time.weekday() >= 5:
            next_time += timedelta(days=1)
    
    return next_time

