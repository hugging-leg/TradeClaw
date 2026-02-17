"""
实时数据 API 接口

定义实时市场数据提供商的统一接口。
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Callable, Set
from datetime import datetime
from decimal import Decimal
from dataclasses import dataclass


@dataclass
class RealtimeTrade:
    """实时成交数据"""
    symbol: str
    timestamp: datetime
    price: Decimal
    volume: int
    conditions: List[str] = None

    def __post_init__(self):
        if self.conditions is None:
            self.conditions = []


@dataclass
class RealtimeNews:
    """实时新闻"""
    id: str
    symbol: str
    headline: str
    summary: str
    source: str
    url: str
    timestamp: datetime


class RealtimeDataAPI(ABC):
    """
    实时数据 API 接口

    提供商需实现：
    - WebSocket 连接管理
    - 股票订阅/取消订阅
    - 数据回调注册
    """

    @abstractmethod
    async def connect(self) -> bool:
        """连接到数据源"""
        pass

    @abstractmethod
    async def disconnect(self):
        """断开连接"""
        pass

    @abstractmethod
    async def subscribe(self, symbols: List[str]):
        """订阅股票"""
        pass

    @abstractmethod
    async def unsubscribe(self, symbols: List[str]):
        """取消订阅"""
        pass

    @abstractmethod
    async def start(self):
        """开始接收数据"""
        pass

    @abstractmethod
    async def stop(self):
        """停止接收"""
        pass

    @abstractmethod
    def register_trade_handler(self, handler: Callable):
        """注册成交数据处理器"""
        pass

    @abstractmethod
    def register_news_handler(self, handler: Callable):
        """注册新闻处理器"""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        pass

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """是否已连接"""
        pass

    @property
    @abstractmethod
    def subscribed_symbols(self) -> Set[str]:
        """已订阅的股票"""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """获取提供商名称"""
        pass


