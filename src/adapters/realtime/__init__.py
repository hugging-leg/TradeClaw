"""
实时数据适配器

提供 WebSocket 实时数据流：
- 实时行情
- 实时新闻
"""

from src.adapters.realtime.finnhub_realtime import FinnhubRealtimeAdapter

__all__ = ["FinnhubRealtimeAdapter"]


