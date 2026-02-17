"""
数据库工具函数

统一数据库可用性检查和相关工具。
"""

from agent_trader.utils.logging_config import get_logger

logger = get_logger(__name__)

# 统一的数据库可用性检查
DB_AVAILABLE = False
_db_modules = {}

try:
    from agent_trader.db import TradingRepository, init_db
    from agent_trader.db.memory import get_agent_memory
    DB_AVAILABLE = True
    _db_modules = {
        'TradingRepository': TradingRepository,
        'init_db': init_db,
        'get_agent_memory': get_agent_memory
    }
except ImportError as e:
    logger.warning(f"数据库模块不可用: {e}")
    DB_AVAILABLE = False


def check_db_available() -> bool:
    """
    检查数据库模块是否可用

    Returns:
        True 如果数据库可用
    """
    return DB_AVAILABLE


def get_trading_repository():
    """
    获取 TradingRepository 类

    Returns:
        TradingRepository 类，如果不可用则返回 None
    """
    return _db_modules.get('TradingRepository')


def get_init_db():
    """
    获取 init_db 函数

    Returns:
        init_db 函数，如果不可用则返回 None
    """
    return _db_modules.get('init_db')


def get_agent_memory_func():
    """
    获取 get_agent_memory 函数

    Returns:
        get_agent_memory 函数，如果不可用则返回 None
    """
    return _db_modules.get('get_agent_memory')

