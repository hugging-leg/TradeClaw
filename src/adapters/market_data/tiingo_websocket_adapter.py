"""
Tiingo WebSocket适配器 - 实时市场数据流

该适配器通过Tiingo的WebSocket API提供实时市场数据：
- 实时股票报价
- 实时新闻推送
- 价格变动监控
- 支持多个股票订阅

WebSocket文档: https://api.tiingo.com/documentation/websockets/iex
"""

import asyncio
import json
import logging
import websockets
from typing import Dict, List, Any, Optional, Callable, Set
from datetime import datetime
from decimal import Decimal
from dataclasses import dataclass
from enum import Enum

from config import settings

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """WebSocket消息类型"""
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    HEARTBEAT = "H"
    QUOTE = "Q"  # 报价数据
    TRADE = "T"  # 成交数据
    NEWS = "N"   # 新闻数据


@dataclass
class MarketQuote:
    """市场报价数据"""
    symbol: str
    timestamp: datetime
    bid_price: Decimal
    bid_size: int
    ask_price: Decimal
    ask_size: int
    last_price: Decimal
    last_size: int


@dataclass
class MarketTrade:
    """市场成交数据"""
    symbol: str
    timestamp: datetime
    price: Decimal
    size: int


@dataclass
class MarketNews:
    """市场新闻数据"""
    symbol: str
    timestamp: datetime
    title: str
    description: str
    url: str


class TiingoWebSocketAdapter:
    """
    Tiingo WebSocket适配器
    
    提供实时市场数据流和事件处理功能
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化WebSocket适配器
        
        Args:
            api_key: Tiingo API密钥（如果未提供，从settings读取）
        """
        self.api_key = api_key or settings.tiingo_api_key
        self.ws_url = "wss://api.tiingo.com/iex"
        
        # WebSocket连接
        self.websocket = None
        self.is_connected = False
        self.is_running = False
        
        # 订阅管理
        self.subscribed_symbols: Set[str] = set()
        self.quote_handlers: List[Callable[[MarketQuote], Any]] = []
        self.trade_handlers: List[Callable[[MarketTrade], Any]] = []
        self.news_handlers: List[Callable[[MarketNews], Any]] = []
        
        # 连接管理
        self.reconnect_delay = 5  # 秒
        self.max_reconnect_attempts = 10
        self.reconnect_attempts = 0
        
        # 心跳管理
        self.last_heartbeat = None
        self.heartbeat_interval = 30  # 秒
        self.heartbeat_task = None
        
        logger.info("Tiingo WebSocket适配器已初始化")
    
    async def connect(self) -> bool:
        """
        连接到Tiingo WebSocket
        
        Returns:
            连接是否成功
        """
        try:
            logger.info(f"连接到Tiingo WebSocket: {self.ws_url}")
            
            # 建立WebSocket连接
            self.websocket = await websockets.connect(
                self.ws_url,
                extra_headers={
                    "Content-Type": "application/json"
                }
            )
            
            # 发送认证消息
            auth_message = {
                "eventName": "subscribe",
                "authorization": self.api_key,
                "eventData": {
                    "thresholdLevel": 5  # 数据频率级别 (1-5, 5最频繁)
                }
            }
            
            await self.websocket.send(json.dumps(auth_message))
            
            self.is_connected = True
            self.reconnect_attempts = 0
            
            logger.info("WebSocket连接成功")
            return True
            
        except Exception as e:
            logger.error(f"WebSocket连接失败: {e}")
            self.is_connected = False
            return False
    
    async def disconnect(self):
        """断开WebSocket连接"""
        try:
            logger.info("断开WebSocket连接")
            
            self.is_running = False
            self.is_connected = False
            
            # 停止心跳任务
            if self.heartbeat_task:
                self.heartbeat_task.cancel()
                try:
                    await self.heartbeat_task
                except asyncio.CancelledError:
                    pass
            
            # 关闭WebSocket
            if self.websocket:
                await self.websocket.close()
                self.websocket = None
            
            logger.info("WebSocket已断开")
            
        except Exception as e:
            logger.error(f"断开连接时出错: {e}")
    
    async def start(self):
        """启动WebSocket数据流"""
        try:
            if self.is_running:
                logger.warning("WebSocket已在运行")
                return
            
            logger.info("启动WebSocket数据流")
            self.is_running = True
            
            # 连接
            if not self.is_connected:
                await self.connect()
            
            # 启动心跳任务
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
            # 启动消息处理循环
            await self._message_loop()
            
        except Exception as e:
            logger.error(f"WebSocket启动失败: {e}")
            self.is_running = False
    
    async def stop(self):
        """停止WebSocket数据流"""
        await self.disconnect()
    
    async def subscribe(self, symbols: List[str]):
        """
        订阅股票实时数据
        
        Args:
            symbols: 股票代码列表
        """
        try:
            if not self.is_connected:
                logger.error("未连接到WebSocket，无法订阅")
                return
            
            # 过滤已订阅的股票
            new_symbols = [s.upper() for s in symbols if s.upper() not in self.subscribed_symbols]
            
            if not new_symbols:
                logger.info("所有股票已订阅")
                return
            
            # 构建订阅消息
            subscribe_message = {
                "eventName": "subscribe",
                "authorization": self.api_key,
                "eventData": {
                    "tickers": new_symbols
                }
            }
            
            await self.websocket.send(json.dumps(subscribe_message))
            
            # 更新订阅列表
            self.subscribed_symbols.update(new_symbols)
            
            logger.info(f"已订阅股票: {new_symbols}")
            
        except Exception as e:
            logger.error(f"订阅失败: {e}")
    
    async def unsubscribe(self, symbols: List[str]):
        """
        取消订阅股票
        
        Args:
            symbols: 股票代码列表
        """
        try:
            if not self.is_connected:
                logger.error("未连接到WebSocket，无法取消订阅")
                return
            
            # 过滤未订阅的股票
            symbols_to_remove = [s.upper() for s in symbols if s.upper() in self.subscribed_symbols]
            
            if not symbols_to_remove:
                logger.info("没有需要取消订阅的股票")
                return
            
            # 构建取消订阅消息
            unsubscribe_message = {
                "eventName": "unsubscribe",
                "authorization": self.api_key,
                "eventData": {
                    "tickers": symbols_to_remove
                }
            }
            
            await self.websocket.send(json.dumps(unsubscribe_message))
            
            # 更新订阅列表
            self.subscribed_symbols.difference_update(symbols_to_remove)
            
            logger.info(f"已取消订阅: {symbols_to_remove}")
            
        except Exception as e:
            logger.error(f"取消订阅失败: {e}")
    
    def register_quote_handler(self, handler: Callable[[MarketQuote], Any]):
        """注册报价数据处理器"""
        self.quote_handlers.append(handler)
        logger.info(f"已注册报价处理器: {handler.__name__}")
    
    def register_trade_handler(self, handler: Callable[[MarketTrade], Any]):
        """注册成交数据处理器"""
        self.trade_handlers.append(handler)
        logger.info(f"已注册成交处理器: {handler.__name__}")
    
    def register_news_handler(self, handler: Callable[[MarketNews], Any]):
        """注册新闻数据处理器"""
        self.news_handlers.append(handler)
        logger.info(f"已注册新闻处理器: {handler.__name__}")
    
    async def _message_loop(self):
        """消息处理主循环"""
        while self.is_running:
            try:
                if not self.websocket:
                    logger.warning("WebSocket连接丢失，尝试重连...")
                    await self._reconnect()
                    continue
                
                # 接收消息（超时30秒）
                try:
                    message = await asyncio.wait_for(
                        self.websocket.recv(),
                        timeout=30
                    )
                except asyncio.TimeoutError:
                    logger.debug("接收消息超时，继续...")
                    continue
                
                # 处理消息
                await self._handle_message(message)
                
            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket连接关闭")
                if self.is_running:
                    await self._reconnect()
            except Exception as e:
                logger.error(f"消息处理循环错误: {e}")
                await asyncio.sleep(1)
    
    async def _handle_message(self, message: str):
        """
        处理接收到的消息
        
        Args:
            message: WebSocket消息（JSON字符串）
        """
        try:
            data = json.loads(message)
            
            # 处理不同类型的消息
            if isinstance(data, dict):
                message_type = data.get("messageType")
                
                if message_type == "H":  # 心跳
                    await self._handle_heartbeat(data)
                elif message_type == "I":  # 订阅响应
                    logger.info(f"订阅确认: {data}")
                elif message_type == "E":  # 错误
                    logger.error(f"WebSocket错误: {data}")
                    
            elif isinstance(data, list):
                # 市场数据数组
                for item in data:
                    await self._handle_market_data(item)
            
        except json.JSONDecodeError:
            logger.error(f"无法解析消息: {message}")
        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
    
    async def _handle_market_data(self, data: Dict[str, Any]):
        """处理市场数据"""
        try:
            data_type = data.get("type")
            
            if data_type == "Q":  # 报价数据
                quote = self._parse_quote(data)
                if quote:
                    await self._dispatch_quote(quote)
                    
            elif data_type == "T":  # 成交数据
                trade = self._parse_trade(data)
                if trade:
                    await self._dispatch_trade(trade)
                    
            elif data_type == "N":  # 新闻数据
                news = self._parse_news(data)
                if news:
                    await self._dispatch_news(news)
                    
        except Exception as e:
            logger.error(f"处理市场数据时出错: {e}")
    
    def _parse_quote(self, data: Dict[str, Any]) -> Optional[MarketQuote]:
        """解析报价数据"""
        try:
            return MarketQuote(
                symbol=data.get("ticker", ""),
                timestamp=datetime.fromisoformat(data.get("timestamp", "")),
                bid_price=Decimal(str(data.get("bidPrice", 0))),
                bid_size=data.get("bidSize", 0),
                ask_price=Decimal(str(data.get("askPrice", 0))),
                ask_size=data.get("askSize", 0),
                last_price=Decimal(str(data.get("last", 0))),
                last_size=data.get("lastSize", 0)
            )
        except Exception as e:
            logger.error(f"解析报价数据失败: {e}")
            return None
    
    def _parse_trade(self, data: Dict[str, Any]) -> Optional[MarketTrade]:
        """解析成交数据"""
        try:
            return MarketTrade(
                symbol=data.get("ticker", ""),
                timestamp=datetime.fromisoformat(data.get("timestamp", "")),
                price=Decimal(str(data.get("price", 0))),
                size=data.get("size", 0)
            )
        except Exception as e:
            logger.error(f"解析成交数据失败: {e}")
            return None
    
    def _parse_news(self, data: Dict[str, Any]) -> Optional[MarketNews]:
        """解析新闻数据"""
        try:
            return MarketNews(
                symbol=data.get("ticker", ""),
                timestamp=datetime.fromisoformat(data.get("timestamp", "")),
                title=data.get("title", ""),
                description=data.get("description", ""),
                url=data.get("url", "")
            )
        except Exception as e:
            logger.error(f"解析新闻数据失败: {e}")
            return None
    
    async def _dispatch_quote(self, quote: MarketQuote):
        """分发报价数据到处理器"""
        for handler in self.quote_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(quote)
                else:
                    handler(quote)
            except Exception as e:
                logger.error(f"报价处理器错误: {e}")
    
    async def _dispatch_trade(self, trade: MarketTrade):
        """分发成交数据到处理器"""
        for handler in self.trade_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(trade)
                else:
                    handler(trade)
            except Exception as e:
                logger.error(f"成交处理器错误: {e}")
    
    async def _dispatch_news(self, news: MarketNews):
        """分发新闻数据到处理器"""
        for handler in self.news_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(news)
                else:
                    handler(news)
            except Exception as e:
                logger.error(f"新闻处理器错误: {e}")
    
    async def _handle_heartbeat(self, data: Dict[str, Any]):
        """处理心跳消息"""
        self.last_heartbeat = datetime.now()
        logger.debug(f"收到心跳: {data}")
    
    async def _heartbeat_loop(self):
        """心跳发送循环"""
        while self.is_running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                
                if self.is_connected and self.websocket:
                    # 发送心跳消息
                    heartbeat = {"eventName": "heartbeat"}
                    await self.websocket.send(json.dumps(heartbeat))
                    logger.debug("发送心跳")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"心跳循环错误: {e}")
    
    async def _reconnect(self):
        """重新连接"""
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            logger.error(f"达到最大重连次数 ({self.max_reconnect_attempts})，停止重连")
            self.is_running = False
            return
        
        self.reconnect_attempts += 1
        logger.info(f"尝试重连 ({self.reconnect_attempts}/{self.max_reconnect_attempts})...")
        
        await asyncio.sleep(self.reconnect_delay)
        
        if await self.connect():
            # 重新订阅之前的股票
            if self.subscribed_symbols:
                await self.subscribe(list(self.subscribed_symbols))
                
    def get_subscribed_symbols(self) -> List[str]:
        """获取当前订阅的股票列表"""
        return list(self.subscribed_symbols)
    
    def is_symbol_subscribed(self, symbol: str) -> bool:
        """检查股票是否已订阅"""
        return symbol.upper() in self.subscribed_symbols
    
    def get_status(self) -> Dict[str, Any]:
        """获取适配器状态"""
        return {
            "is_connected": self.is_connected,
            "is_running": self.is_running,
            "subscribed_symbols": list(self.subscribed_symbols),
            "subscribed_count": len(self.subscribed_symbols),
            "quote_handlers": len(self.quote_handlers),
            "trade_handlers": len(self.trade_handlers),
            "news_handlers": len(self.news_handlers),
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "reconnect_attempts": self.reconnect_attempts
        }
