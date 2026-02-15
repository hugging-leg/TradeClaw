"""
事件系统 - 仅负责即时事件分发

设计原则：
1. 只处理即时事件分发，不做定时调度
2. 定时任务全部交给 TradingScheduler (APScheduler)
3. 保持简单：注册 handler → 发布事件 → 立即分发

事件类型：
- trigger_workflow: 统一的 workflow 触发
- trigger_portfolio_check: 组合检查
- trigger_risk_check: 风控检查
- trigger_eod_analysis: 收盘分析
- enable_trading / disable_trading: 交易控制
- emergency_stop: 紧急停止
- query_*: 查询请求
"""

import asyncio
from src.utils.logging_config import get_logger
from typing import Dict, List, Callable, Any, Optional
from datetime import datetime, timezone

from src.models.trading_models import TradingEvent

logger = get_logger(__name__)


class EventSystem:
    """
    事件系统 - 即时事件分发

    职责：
    - 注册/注销事件处理器
    - 发布事件并立即分发给对应处理器
    - 使用 asyncio.Queue 实现异步解耦
    """

    def __init__(self):
        self.event_handlers: Dict[str, List[Callable]] = {}
        self.is_running = False
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self._event_counter = 0
        self._process_task: Optional[asyncio.Task] = None

    async def initialize(self):
        logger.info("Initialize Event System")

    async def start(self):
        await self.initialize()
        self.is_running = True

        self._process_task = asyncio.create_task(self._process_events())
        logger.info("Event System Started")

    async def stop(self):
        self.is_running = False
        if self._process_task and not self._process_task.done():
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass
        logger.info("Event System Stopped")

    def get_queue_size(self) -> int:
        """Get current event queue size"""
        return self.event_queue.qsize()

    def get_status(self) -> Dict[str, Any]:
        """Get event system status"""
        return {
            "is_running": self.is_running,
            "queue_size": self.get_queue_size(),
            "handlers_count": len(self.event_handlers),
            "event_counter": self._event_counter
        }

    def register_handler(self, event_type: str, handler: Callable):
        """
        Register Event Handler

        Args:
            event_type: Event Type
            handler: Async Handler Function
        """
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []

        self.event_handlers[event_type].append(handler)
        logger.info(f"Registered Handler: {event_type}")

    def unregister_handler(self, event_type: str, handler: Callable):
        """Unregister Event Handler"""
        if event_type in self.event_handlers:
            try:
                self.event_handlers[event_type].remove(handler)
                logger.info(f"Unregistered Handler: {event_type}")
            except ValueError:
                logger.warning(f"Handler Not Found: {event_type}")

    async def publish_event(self, event: TradingEvent):
        """
        Publish Event to Queue (immediate dispatch only)

        Args:
            event: TradingEvent Instance
        """
        try:
            self._event_counter += 1
            await self.event_queue.put(event)
            logger.debug(f"Event Published: {event.event_type}")
        except Exception as e:
            logger.error(f"Failed to Publish Event: {e}")

    async def _process_events(self):
        """
        Process Events from Queue

        简单的 FIFO 处理，无忙等待：
        - 使用 asyncio.Queue.get() 阻塞等待
        - 有事件时立即处理
        - 无事件时挂起，不消耗 CPU
        """
        while self.is_running:
            try:
                event = await asyncio.wait_for(self.event_queue.get(), timeout=1.0)
                await self._handle_event(event)
            except asyncio.TimeoutError:
                # 无事件，继续循环（仅用于检查 is_running 标志）
                continue
            except asyncio.CancelledError:
                logger.info("Event processing cancelled")
                break
            except Exception as e:
                logger.error(f"Error Processing Event: {e}")

    async def _handle_event(self, event: TradingEvent):
        """
        Process Single Event

        Args:
            event: Event Instance
        """
        try:
            handlers = self.event_handlers.get(event.event_type, [])

            if not handlers:
                logger.debug(f"No Handlers Registered: {event.event_type}")
            else:
                for handler in handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(event)
                        else:
                            handler(event)
                    except Exception as e:
                        logger.error(f"Handler Error [{event.event_type}]: {e}")

            event.processed = True

        except Exception as e:
            logger.error(f"Failed to Process Event: {e}")

    # === Convenient Event Publishing Methods ===

    async def publish(
        self,
        event_type: str,
        data: Dict[str, Any] = None,
        priority: int = 0
    ):
        """
        Unified event publishing method (immediate only)

        Args:
            event_type: Type of event
            data: Event data dictionary
            priority: Event priority (lower number = higher priority, default: 0)

        Examples:
            await event_system.publish("trigger_workflow", {"trigger": "daily_rebalance"})
        """
        event_data = data or {}
        if "timestamp" not in event_data:
            event_data["timestamp"] = datetime.now(timezone.utc).isoformat()

        event = TradingEvent(
            event_type=event_type,
            data=event_data,
            priority=priority
        )
        await self.publish_event(event)


# Global event system instance
event_system = EventSystem()
