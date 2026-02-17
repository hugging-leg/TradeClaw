"""
数据库模块

提供数据持久化功能：
- 交易决策记录
- 分析历史
- 订单执行记录
- 组合快照
"""

from .session import get_db, init_db, close_db, DatabaseSession
from .models import (
    TradingDecision,
    AnalysisHistory,
    OrderRecord,
    PortfolioSnapshot,
    AgentMessage
)
from .repository import TradingRepository

__all__ = [
    'get_db',
    'init_db',
    'close_db',
    'DatabaseSession',
    'TradingDecision',
    'AnalysisHistory',
    'OrderRecord',
    'PortfolioSnapshot',
    'AgentMessage',
    'TradingRepository'
]

