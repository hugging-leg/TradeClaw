"""
API 依赖注入

通过全局引用获取 TradingSystem 实例，供所有 route 使用。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_trader.trading_system import TradingSystem

_trading_system: "TradingSystem | None" = None


def set_trading_system(ts: "TradingSystem") -> None:
    """在 main.py 启动时调用，注入 TradingSystem 实例"""
    global _trading_system
    _trading_system = ts


def get_trading_system() -> "TradingSystem":
    """获取 TradingSystem 实例（供 FastAPI Depends 使用）"""
    if _trading_system is None:
        raise RuntimeError("TradingSystem not initialized")
    return _trading_system
