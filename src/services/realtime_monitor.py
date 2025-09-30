"""
实时市场监控服务

该服务使用Tiingo WebSocket监控实时市场数据，并在检测到重大事件时触发重新平衡：
- 价格剧烈波动（如±5%）
- 突发新闻
- 多个持仓同时大幅变动

设计原则：
- 避免过度交易（设置冷却期）
- 智能事件过滤
- 与BalancedPortfolioWorkflow集成
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime, timedelta
from decimal import Decimal
from collections import defaultdict

from src.adapters.market_data.tiingo_websocket_adapter import (
    TiingoWebSocketAdapter, MarketQuote, MarketTrade, MarketNews
)
from src.models.trading_models import Portfolio

logger = logging.getLogger(__name__)


class PriceTracker:
    """价格跟踪器 - 监控价格变化"""
    
    def __init__(self, symbol: str, initial_price: Decimal):
        self.symbol = symbol
        self.initial_price = initial_price
        self.current_price = initial_price
        self.high_price = initial_price
        self.low_price = initial_price
        self.last_update = datetime.now()
    
    def update(self, price: Decimal):
        """更新价格"""
        self.current_price = price
        self.high_price = max(self.high_price, price)
        self.low_price = min(self.low_price, price)
        self.last_update = datetime.now()
    
    def get_change_percentage(self) -> Decimal:
        """计算价格变化百分比"""
        if self.initial_price == 0:
            return Decimal('0')
        return ((self.current_price - self.initial_price) / self.initial_price) * 100
    
    def get_volatility(self) -> Decimal:
        """计算波动率（高低价差百分比）"""
        if self.initial_price == 0:
            return Decimal('0')
        return ((self.high_price - self.low_price) / self.initial_price) * 100


class RealtimeMarketMonitor:
    """
    实时市场监控服务
    
    功能：
    - 监控持仓股票的实时价格
    - 检测价格剧烈波动
    - 监听突发新闻
    - 触发重新平衡
    """
    
    # 触发阈值
    PRICE_CHANGE_THRESHOLD = Decimal('5.0')  # 价格变化5%触发
    VOLATILITY_THRESHOLD = Decimal('8.0')    # 波动率8%触发
    REBALANCE_COOLDOWN = 3600  # 重新平衡冷却期（秒）
    
    def __init__(self, trading_system=None):
        """
        初始化监控服务
        
        Args:
            trading_system: TradingSystem实例（用于触发重新平衡）
        """
        self.trading_system = trading_system
        self.ws_adapter = TiingoWebSocketAdapter()
        
        # 价格跟踪
        self.price_trackers: Dict[str, PriceTracker] = {}
        
        # 事件记录
        self.last_rebalance_trigger = None
        self.trigger_history: List[Dict[str, Any]] = []
        
        # 监控状态
        self.is_monitoring = False
        self.monitor_task = None
        
        # 注册处理器
        self.ws_adapter.register_quote_handler(self._handle_quote)
        self.ws_adapter.register_trade_handler(self._handle_trade)
        self.ws_adapter.register_news_handler(self._handle_news)
        
        logger.info("实时市场监控服务已初始化")
    
    async def start(self, portfolio: Optional[Portfolio] = None):
        """
        启动监控服务
        
        Args:
            portfolio: 当前组合（用于确定要监控的股票）
        """
        try:
            if self.is_monitoring:
                logger.warning("监控服务已在运行")
                return
            
            logger.info("启动实时市场监控服务")
            self.is_monitoring = True
            
            # 连接WebSocket
            if not self.ws_adapter.is_connected:
                await self.ws_adapter.connect()
            
            # 如果提供了组合，订阅持仓股票
            if portfolio and portfolio.positions:
                symbols = [pos.symbol for pos in portfolio.positions if pos.quantity != 0]
                if symbols:
                    await self.subscribe_symbols(symbols, portfolio)
            
            # 启动WebSocket数据流（在后台运行）
            self.monitor_task = asyncio.create_task(self.ws_adapter.start())
            
            logger.info("监控服务启动成功")
            
        except Exception as e:
            logger.error(f"启动监控服务失败: {e}")
            self.is_monitoring = False
    
    async def stop(self):
        """停止监控服务"""
        try:
            logger.info("停止实时市场监控服务")
            self.is_monitoring = False
            
            # 停止WebSocket
            await self.ws_adapter.stop()
            
            # 取消监控任务
            if self.monitor_task:
                self.monitor_task.cancel()
                try:
                    await self.monitor_task
                except asyncio.CancelledError:
                    pass
            
            logger.info("监控服务已停止")
            
        except Exception as e:
            logger.error(f"停止监控服务时出错: {e}")
    
    async def subscribe_symbols(self, symbols: List[str], portfolio: Optional[Portfolio] = None):
        """
        订阅股票实时数据
        
        Args:
            symbols: 股票代码列表
            portfolio: 组合信息（用于初始化价格跟踪器）
        """
        try:
            # 订阅WebSocket
            await self.ws_adapter.subscribe(symbols)
            
            # 初始化价格跟踪器
            if portfolio:
                for position in portfolio.positions:
                    if position.symbol in symbols and position.quantity != 0:
                        current_price = position.market_value / abs(position.quantity) if position.quantity != 0 else Decimal('0')
                        self.price_trackers[position.symbol] = PriceTracker(
                            symbol=position.symbol,
                            initial_price=current_price
                        )
            
            logger.info(f"已订阅股票实时数据: {symbols}")
            
        except Exception as e:
            logger.error(f"订阅股票失败: {e}")
    
    async def unsubscribe_symbols(self, symbols: List[str]):
        """取消订阅股票"""
        try:
            await self.ws_adapter.unsubscribe(symbols)
            
            # 移除价格跟踪器
            for symbol in symbols:
                if symbol in self.price_trackers:
                    del self.price_trackers[symbol]
            
            logger.info(f"已取消订阅: {symbols}")
            
        except Exception as e:
            logger.error(f"取消订阅失败: {e}")
    
    async def _handle_quote(self, quote: MarketQuote):
        """处理报价数据"""
        try:
            # 更新价格跟踪器
            if quote.symbol in self.price_trackers:
                tracker = self.price_trackers[quote.symbol]
                tracker.update(quote.last_price)
                
                # 检查是否触发重新平衡
                await self._check_rebalance_triggers(tracker)
            
        except Exception as e:
            logger.error(f"处理报价数据时出错: {e}")
    
    async def _handle_trade(self, trade: MarketTrade):
        """处理成交数据"""
        try:
            # 更新价格跟踪器
            if trade.symbol in self.price_trackers:
                tracker = self.price_trackers[trade.symbol]
                tracker.update(trade.price)
                
                # 可以根据成交量判断市场活跃度
                logger.debug(f"成交: {trade.symbol} @ {trade.price}, 数量: {trade.size}")
            
        except Exception as e:
            logger.error(f"处理成交数据时出错: {e}")
    
    async def _handle_news(self, news: MarketNews):
        """处理新闻数据"""
        try:
            logger.info(f"突发新闻 ({news.symbol}): {news.title}")
            
            # 检查是否是持仓股票的重要新闻
            if news.symbol in self.price_trackers:
                # 判断新闻重要性（这里简化处理，实际可以用NLP分析）
                if await self._is_breaking_news(news):
                    await self._trigger_rebalance(
                        reason="breaking_news",
                        details={
                            "symbol": news.symbol,
                            "title": news.title,
                            "url": news.url
                        }
                    )
            
        except Exception as e:
            logger.error(f"处理新闻数据时出错: {e}")
    
    async def _check_rebalance_triggers(self, tracker: PriceTracker):
        """检查是否触发重新平衡"""
        try:
            change_pct = abs(tracker.get_change_percentage())
            volatility = tracker.get_volatility()
            
            # 1. 检查价格变化
            if change_pct >= self.PRICE_CHANGE_THRESHOLD:
                await self._trigger_rebalance(
                    reason="price_change",
                    details={
                        "symbol": tracker.symbol,
                        "change_percentage": float(change_pct),
                        "current_price": float(tracker.current_price),
                        "initial_price": float(tracker.initial_price)
                    }
                )
                return
            
            # 2. 检查波动率
            if volatility >= self.VOLATILITY_THRESHOLD:
                await self._trigger_rebalance(
                    reason="high_volatility",
                    details={
                        "symbol": tracker.symbol,
                        "volatility": float(volatility),
                        "high_price": float(tracker.high_price),
                        "low_price": float(tracker.low_price)
                    }
                )
                return
            
        except Exception as e:
            logger.error(f"检查触发器时出错: {e}")
    
    async def _trigger_rebalance(self, reason: str, details: Dict[str, Any]):
        """触发重新平衡"""
        try:
            # 检查冷却期
            if self.last_rebalance_trigger:
                elapsed = (datetime.now() - self.last_rebalance_trigger).total_seconds()
                if elapsed < self.REBALANCE_COOLDOWN:
                    logger.info(f"重新平衡冷却中（剩余{self.REBALANCE_COOLDOWN - elapsed:.0f}秒）")
                    return
            
            logger.warning(f"触发重新平衡: {reason} - {details}")
            
            # 记录触发
            self.last_rebalance_trigger = datetime.now()
            self.trigger_history.append({
                "timestamp": self.last_rebalance_trigger.isoformat(),
                "reason": reason,
                "details": details
            })
            
            # 调用trading_system执行重新平衡
            if self.trading_system:
                # 构建上下文
                context = {
                    "trigger": reason,
                    "timestamp": datetime.now().isoformat()
                }
                
                if reason == "breaking_news":
                    context["news_event"] = details
                elif reason in ["price_change", "high_volatility"]:
                    context["market_event"] = details
                
                # 如果使用portfolio management workflow，触发它
                if hasattr(self.trading_system, 'trading_workflow'):
                    workflow_type = self.trading_system.trading_workflow.get_workflow_type()
                    if workflow_type in ["balanced_portfolio", "llm_portfolio"]:
                        # 直接调用portfolio workflow
                        asyncio.create_task(
                            self.trading_system.trading_workflow.run_workflow(context)
                        )
                    else:
                        # 使用通用的manual_analysis
                        asyncio.create_task(
                            self.trading_system.run_manual_analysis()
                        )
            
        except Exception as e:
            logger.error(f"触发重新平衡失败: {e}")
    
    async def _is_breaking_news(self, news: MarketNews) -> bool:
        """
        判断是否是突发新闻
        
        这里简化处理，实际可以：
        1. 使用NLP分析标题关键词
        2. 检查新闻源的可信度
        3. 分析新闻的时效性
        
        Args:
            news: 新闻数据
            
        Returns:
            是否是突发新闻
        """
        # 关键词列表（表示重大事件）
        keywords = [
            "merger", "acquisition", "bankruptcy", "fraud", 
            "investigation", "lawsuit", "earnings", "guidance",
            "CEO", "resign", "leadership", "restructure",
            "breakthrough", "recall", "FDA", "approval"
        ]
        
        title_lower = news.title.lower()
        return any(keyword in title_lower for keyword in keywords)
    
    def update_portfolio_positions(self, portfolio: Portfolio):
        """
        更新监控的组合持仓
        
        当组合发生变化时调用此方法更新监控列表
        
        Args:
            portfolio: 最新的组合信息
        """
        try:
            # 获取当前持仓符号
            current_symbols = {pos.symbol for pos in portfolio.positions if pos.quantity != 0}
            
            # 获取正在监控的符号
            monitored_symbols = set(self.price_trackers.keys())
            
            # 找出需要添加和移除的符号
            symbols_to_add = current_symbols - monitored_symbols
            symbols_to_remove = monitored_symbols - current_symbols
            
            # 更新订阅
            if symbols_to_add:
                asyncio.create_task(self.subscribe_symbols(list(symbols_to_add), portfolio))
            
            if symbols_to_remove:
                asyncio.create_task(self.unsubscribe_symbols(list(symbols_to_remove)))
            
        except Exception as e:
            logger.error(f"更新组合持仓失败: {e}")
    
    def get_monitored_symbols(self) -> List[str]:
        """获取当前监控的股票列表"""
        return list(self.price_trackers.keys())
    
    def get_price_changes(self) -> Dict[str, Dict[str, Any]]:
        """获取所有监控股票的价格变化"""
        changes = {}
        for symbol, tracker in self.price_trackers.items():
            changes[symbol] = {
                "current_price": float(tracker.current_price),
                "initial_price": float(tracker.initial_price),
                "change_percentage": float(tracker.get_change_percentage()),
                "volatility": float(tracker.get_volatility()),
                "high_price": float(tracker.high_price),
                "low_price": float(tracker.low_price),
                "last_update": tracker.last_update.isoformat()
            }
        return changes
    
    def get_status(self) -> Dict[str, Any]:
        """获取监控服务状态"""
        return {
            "is_monitoring": self.is_monitoring,
            "websocket_status": self.ws_adapter.get_status(),
            "monitored_symbols": self.get_monitored_symbols(),
            "price_trackers_count": len(self.price_trackers),
            "last_rebalance_trigger": self.last_rebalance_trigger.isoformat() if self.last_rebalance_trigger else None,
            "trigger_history_count": len(self.trigger_history),
            "thresholds": {
                "price_change": float(self.PRICE_CHANGE_THRESHOLD),
                "volatility": float(self.VOLATILITY_THRESHOLD),
                "cooldown_seconds": self.REBALANCE_COOLDOWN
            }
        }
