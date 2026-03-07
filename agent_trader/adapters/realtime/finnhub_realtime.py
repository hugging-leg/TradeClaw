"""
Finnhub 实时数据适配器

实现 RealtimeDataAPI 接口，提供 WebSocket 实时数据：
- 实时交易报价 (type: trade)
- 实时新闻推送 (type: news)

API 文档: https://finnhub.io/docs/api/websocket-news
"""

import asyncio
import json
from agent_trader.utils.logging_config import get_logger
from typing import Dict, List, Any, Optional, Callable, Set
from datetime import datetime
from decimal import Decimal
import websockets

from config import settings
from agent_trader.interfaces.realtime_data_api import (
    RealtimeDataAPI, RealtimeTrade, RealtimeNews
)
from agent_trader.interfaces.factory import register_realtime

logger = get_logger(__name__)


@register_realtime("finnhub")
class FinnhubRealtimeAdapter(RealtimeDataAPI):
    """
    Finnhub 实时数据适配器

    支持：
    - 实时交易: subscribe/unsubscribe
    - 实时新闻: subscribe-news/unsubscribe-news
    """

    WS_URL = "wss://ws.finnhub.io"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or getattr(settings, 'finnhub_api_key', None)

        if not self.api_key:
            logger.warning("Finnhub API key 未配置")

        # 连接状态
        self.websocket = None
        self._is_connected = False
        self._is_running = False

        # 订阅列表
        self._subscribed_trades: Set[str] = set()
        self._subscribed_news: Set[str] = set()

        # 回调处理器
        self._trade_handlers: List[Callable] = []
        self._news_handlers: List[Callable] = []

        # 重连配置
        self.max_reconnect_attempts = 10
        self.reconnect_attempts = 0

        # 心跳
        self._ping_task = None
        # Reconnect task — tracked to prevent duplicate reconnect loops
        self._reconnect_task: Optional[asyncio.Task] = None

        logger.info("Finnhub 实时适配器已初始化")

    # ========== RealtimeDataAPI 接口实现 ==========

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def subscribed_symbols(self) -> Set[str]:
        return self._subscribed_trades | self._subscribed_news

    def get_provider_name(self) -> str:
        return "Finnhub"

    async def connect(self) -> bool:
        if not self.api_key:
            logger.error("无法连接：API key 未配置")
            return False

        try:
            url = f"{self.WS_URL}?token={self.api_key}"
            logger.info("连接到 Finnhub WebSocket...")

            self.websocket = await websockets.connect(
                url,
                ping_interval=30,
                ping_timeout=10
            )
            self._is_connected = True
            self.reconnect_attempts = 0

            logger.info("Finnhub WebSocket 连接成功")
            return True

        except Exception as e:
            logger.error(f"WebSocket 连接失败: {e}")
            self._is_connected = False
            return False

    async def disconnect(self):
        self._is_running = False
        self._is_connected = False

        if self._ping_task:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass

        if self.websocket:
            await self.websocket.close()
            self.websocket = None

        logger.info("Finnhub 连接已断开")

    async def subscribe(self, symbols: List[str]):
        """订阅交易和新闻"""
        await self.subscribe_trades(symbols)
        await self.subscribe_news(symbols)

    async def subscribe_trades(self, symbols: List[str]):
        """订阅实时交易"""
        if not self._is_connected or not self.websocket:
            logger.warning("未连接，无法订阅交易")
            return

        for symbol in symbols:
            if symbol not in self._subscribed_trades:
                msg = json.dumps({"type": "subscribe", "symbol": symbol})
                await self.websocket.send(msg)
                self._subscribed_trades.add(symbol)
                logger.debug(f"订阅交易: {symbol}")

        logger.info(f"已订阅交易: {symbols}")

    async def subscribe_news(self, symbols: List[str]):
        """订阅实时新闻"""
        if not self._is_connected or not self.websocket:
            logger.warning("未连接，无法订阅新闻")
            return

        for symbol in symbols:
            if symbol not in self._subscribed_news:
                msg = json.dumps({"type": "subscribe-news", "symbol": symbol})
                await self.websocket.send(msg)
                self._subscribed_news.add(symbol)
                logger.debug(f"订阅新闻: {symbol}")

        logger.info(f"已订阅新闻: {symbols}")

    async def unsubscribe(self, symbols: List[str]):
        """取消订阅交易和新闻"""
        await self.unsubscribe_trades(symbols)
        await self.unsubscribe_news(symbols)

    async def unsubscribe_trades(self, symbols: List[str]):
        """取消订阅交易"""
        if not self._is_connected or not self.websocket:
            return

        for symbol in symbols:
            if symbol in self._subscribed_trades:
                msg = json.dumps({"type": "unsubscribe", "symbol": symbol})
                await self.websocket.send(msg)
                self._subscribed_trades.discard(symbol)

    async def unsubscribe_news(self, symbols: List[str]):
        """取消订阅新闻"""
        if not self._is_connected or not self.websocket:
            return

        for symbol in symbols:
            if symbol in self._subscribed_news:
                msg = json.dumps({"type": "unsubscribe-news", "symbol": symbol})
                await self.websocket.send(msg)
                self._subscribed_news.discard(symbol)

    async def start(self):
        """启动 WebSocket 消息循环"""
        if not self._is_connected:
            await self.connect()

        if not self._is_connected:
            logger.error("无法启动：Finnhub 未连接")
            return

        self._is_running = True
        logger.info("开始接收实时数据...")

        try:
            while self._is_running and self.websocket:
                try:
                    message = await asyncio.wait_for(
                        self.websocket.recv(),
                        timeout=60
                    )
                    await self._handle_message(message)

                except asyncio.TimeoutError:
                    # 超时，发送 ping
                    if self.websocket:
                        try:
                            await self.websocket.ping()
                        except Exception:
                            pass

                except websockets.ConnectionClosed:
                    logger.warning("WebSocket 连接关闭")
                    await self._handle_disconnect()
                    break

        except Exception as e:
            logger.error(f"WebSocket 错误: {e}")
            await self._handle_disconnect()

    async def stop(self):
        await self.disconnect()

    def register_trade_handler(self, handler: Callable):
        self._trade_handlers.append(handler)

    def register_news_handler(self, handler: Callable):
        self._news_handlers.append(handler)

    def get_status(self) -> Dict[str, Any]:
        return {
            "provider": "Finnhub",
            "connected": self._is_connected,
            "running": self._is_running,
            "subscribed_trades": list(self._subscribed_trades),
            "subscribed_news": list(self._subscribed_news),
            "reconnect_attempts": self.reconnect_attempts,
            "api_key_configured": bool(self.api_key)
        }

    # ========== 内部方法 ==========

    async def _handle_message(self, message: str):
        """处理 WebSocket 消息"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "trade":
                # 实时交易数据
                for trade_data in data.get("data", []):
                    trade = RealtimeTrade(
                        symbol=trade_data["s"],
                        timestamp=datetime.fromtimestamp(trade_data["t"] / 1000),
                        price=Decimal(str(trade_data["p"])),
                        volume=trade_data["v"],
                        conditions=trade_data.get("c", [])
                    )
                    await self._notify_trade(trade)

            elif msg_type == "news":
                # 实时新闻数据
                for news_data in data.get("data", []):
                    news = RealtimeNews(
                        id=str(news_data["id"]),
                        symbol=news_data.get("related", ""),
                        headline=news_data["headline"],
                        summary=news_data.get("summary", ""),
                        source=news_data.get("source", ""),
                        url=news_data.get("url", ""),
                        timestamp=datetime.fromtimestamp(news_data["datetime"])
                    )
                    await self._notify_news(news)

            elif msg_type == "ping":
                # 心跳响应
                pass

            elif msg_type == "error":
                logger.error(f"Finnhub 错误: {data.get('msg')}")

        except Exception as e:
            logger.error(f"处理消息失败: {e}, message: {message[:200]}")

    async def _handle_disconnect(self):
        """处理断开连接"""
        self._is_connected = False

        if not self._is_running:
            return

        if self.reconnect_attempts < self.max_reconnect_attempts:
            self.reconnect_attempts += 1
            wait_time = min(2 ** self.reconnect_attempts, 60)
            logger.info(f"尝试重连 ({self.reconnect_attempts}/{self.max_reconnect_attempts})，等待 {wait_time}s...")

            await asyncio.sleep(wait_time)

            if await self.connect():
                # 重新订阅
                trades = list(self._subscribed_trades)
                news = list(self._subscribed_news)
                self._subscribed_trades.clear()
                self._subscribed_news.clear()

                await self.subscribe_trades(trades)
                await self.subscribe_news(news)
                # Cancel any prior reconnect-spawned start() task
                if self._reconnect_task and not self._reconnect_task.done():
                    self._reconnect_task.cancel()
                self._reconnect_task = asyncio.create_task(self.start())
        else:
            logger.error("达到最大重连次数")

    async def _notify_trade(self, trade: RealtimeTrade):
        """通知交易处理器"""
        for handler in self._trade_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(trade)
                else:
                    handler(trade)
            except Exception as e:
                logger.error(f"交易处理器错误: {e}")

    async def _notify_news(self, news: RealtimeNews):
        """通知新闻处理器"""
        for handler in self._news_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(news)
                else:
                    handler(news)
            except Exception as e:
                logger.error(f"新闻处理器错误: {e}")

