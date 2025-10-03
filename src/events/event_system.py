import asyncio
import logging
from typing import Dict, List, Callable, Any, Optional
from datetime import datetime, timedelta
import pytz
from src.models.trading_models import TradingEvent

logger = logging.getLogger(__name__)


class EventSystem:
    """
    Event-Driven System - Focus on Workflow Triggering and Scheduling
    
    Design Principles:
    1. Only handle workflow triggering events
    2. Order notifications handled by components directly, not through event system
    3. Support LLM agent self-scheduling via events
    4. Keep simple, avoid over-engineering
    
    Event Types:
    - trigger_daily_rebalance: Daily scheduled trigger
    - trigger_realtime_rebalance: Real-time market event trigger (price volatility, news, etc.)
    - trigger_manual_analysis: Manual trigger
    - trigger_portfolio_check: Scheduled portfolio check
    - trigger_risk_check: Risk check
    - trigger_eod_analysis: End-of-day analysis
    - schedule_next_analysis: LLM decides next analysis time (optional)
    - system_started / system_stopped: System state events
    
    Features:
    - Time-based scheduling: Events can be scheduled for future execution
    - Priority queue: Events processed in scheduled_time order
    - Immediate execution: Events with scheduled_time=None execute immediately
    """
    
    def __init__(self):
        self.event_handlers: Dict[str, List[Callable]] = {}
        self.is_running = False
        self.event_queue = asyncio.PriorityQueue()  # Priority queue for time-based scheduling
        self._event_counter = 0  # For maintaining insertion order when times are equal
        
    async def initialize(self):
        logger.info("Initialize Event System")
    
    async def start(self):
        await self.initialize()
        self.is_running = True
        
        asyncio.create_task(self._process_events())
        logger.info("Event System Started")
    
    async def stop(self):
        self.is_running = False
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
            event_type: Event Type (e.g. trigger_daily_rebalance)
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
        Publish Event to Priority Queue
        
        Args:
            event: TradingEvent Instance
        
        Events are stored in priority queue ordered by:
        1. scheduled_time (earliest first, None = immediate)
        2. priority field (lower = higher priority)
        3. insertion order (_event_counter)
        """
        try:
            # Use tuple for priority queue: (event, counter)
            # event.__lt__ handles comparison by scheduled_time and priority
            self._event_counter += 1
            await self.event_queue.put((event, self._event_counter))
            
            if event.scheduled_time:
                logger.debug(f"Event Scheduled: {event.event_type} at {event.scheduled_time.isoformat()}")
            else:
                logger.debug(f"Event Published (Immediate): {event.event_type}")
        except Exception as e:
            logger.error(f"Failed to Publish Event: {e}")
    
    async def _process_events(self):
        """
        Process Events from Priority Queue
        
        - Checks scheduled_time before executing
        - Re-queues events if scheduled time hasn't arrived
        - Processes immediate events (scheduled_time=None) right away
        """
        while self.is_running:
            try:
                # Get event from priority queue (non-blocking with timeout)
                event_tuple = await asyncio.wait_for(self.event_queue.get(), timeout=1.0)
                event, counter = event_tuple
                
                # Check if it's time to execute this event
                # Use timezone-aware datetime to compare with scheduled_time
                current_time = datetime.now(pytz.UTC)
                
                if event.scheduled_time and event.scheduled_time > current_time:
                    # Event is scheduled for future, calculate wait time
                    wait_seconds = (event.scheduled_time - current_time).total_seconds()
                    
                    # If wait time is very short (< 1 second), just wait
                    if wait_seconds < 1.0:
                        await asyncio.sleep(wait_seconds)
                        await self._handle_event(event)
                    else:
                        # Put back in queue and log
                        await self.event_queue.put((event, counter))
                        logger.debug(f"Event {event.event_type} re-queued, executes in {wait_seconds:.1f}s")
                        # Sleep a bit to avoid busy loop
                        await asyncio.sleep(0.5)
                else:
                    # Time has arrived (or immediate event), execute now
                    if event.scheduled_time:
                        logger.info(f"Executing Scheduled Event: {event.event_type}")
                    await self._handle_event(event)
                
            except asyncio.TimeoutError:
                # No events in queue, continue
                continue
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
    
    async def trigger_daily_rebalance(self, context: Dict[str, Any] = None, scheduled_time: Optional[datetime] = None):
        """
        Trigger Daily Rebalance
        
        Args:
            context: Event context data
            scheduled_time: When to execute (None = immediate)
        """
        event = TradingEvent(
            event_type="trigger_daily_rebalance",
            data=context or {"timestamp": datetime.now().isoformat()},
            scheduled_time=scheduled_time
        )
        await self.publish_event(event)
    
    async def trigger_realtime_rebalance(self, reason: str, details: Dict[str, Any], scheduled_time: Optional[datetime] = None):
        """
        Trigger Real-time Rebalance
        
        Args:
            reason: Trigger reason (price_change, high_volatility, breaking_news, etc.)
            details: Detailed information
            scheduled_time: When to execute (None = immediate)
        """
        event = TradingEvent(
            event_type="trigger_realtime_rebalance",
            data={
                "reason": reason,
                "details": details,
                "timestamp": datetime.now().isoformat()
            },
            scheduled_time=scheduled_time
        )
        await self.publish_event(event)
    
    async def trigger_manual_analysis(self, context: Dict[str, Any] = None, scheduled_time: Optional[datetime] = None):
        """
        Trigger Manual Analysis
        
        Args:
            context: Event context data
            scheduled_time: When to execute (None = immediate)
        """
        event = TradingEvent(
            event_type="trigger_manual_analysis",
            data=context or {"timestamp": datetime.now().isoformat()},
            scheduled_time=scheduled_time
        )
        await self.publish_event(event)
    
    async def trigger_portfolio_check(self, scheduled_time: Optional[datetime] = None):
        """
        Trigger Portfolio Check
        
        Args:
            scheduled_time: When to execute (None = immediate)
        """
        event = TradingEvent(
            event_type="trigger_portfolio_check",
            data={"timestamp": datetime.now().isoformat()},
            scheduled_time=scheduled_time
        )
        await self.publish_event(event)
    
    async def trigger_risk_check(self, scheduled_time: Optional[datetime] = None):
        """
        Trigger Risk Check
        
        Args:
            scheduled_time: When to execute (None = immediate)
        """
        event = TradingEvent(
            event_type="trigger_risk_check",
            data={"timestamp": datetime.now().isoformat()},
            scheduled_time=scheduled_time
        )
        await self.publish_event(event)
    
    async def trigger_eod_analysis(self, scheduled_time: Optional[datetime] = None):
        """
        Trigger End-of-Day Analysis
        
        Args:
            scheduled_time: When to execute (None = immediate)
        """
        event = TradingEvent(
            event_type="trigger_eod_analysis",
            data={"timestamp": datetime.now().isoformat()},
            scheduled_time=scheduled_time
        )
        await self.publish_event(event)
    
    async def schedule_next_analysis(self, scheduled_time: datetime, reason: str, priority: int = 0, context: Dict[str, Any] = None):
        """
        Schedule Next Analysis (LLM Self-Scheduling)
        
        This allows LLM agents to autonomously schedule their next analysis
        based on their decision-making process.
        
        Args:
            scheduled_time: When to execute the analysis
            reason: Reason for scheduling (e.g., "Expected FOMC announcement")
            priority: Event priority (lower = higher priority)
            context: Additional context data
        
        Example:
            await event_system.schedule_next_analysis(
                scheduled_time=datetime.now() + timedelta(hours=2),
                reason="Expected earnings report for AAPL",
                priority=1
            )
        """
        event_data = {
            "reason": reason,
            "scheduled_by": "llm_agent",
            "timestamp": datetime.now().isoformat()
        }
        if context:
            event_data.update(context)
        
        event = TradingEvent(
            event_type="trigger_manual_analysis",
            data=event_data,
            scheduled_time=scheduled_time,
            priority=priority
        )
        await self.publish_event(event)
        logger.info(f"LLM Scheduled Analysis: {scheduled_time.isoformat()} - {reason}")
    
    async def publish_system_event(self, event_type: str, message: str, level: str = "info", scheduled_time: Optional[datetime] = None):
        """
        Publish System Event
        
        Args:
            event_type: system_started, system_stopped, etc.
            message: Message content
            level: Log level
            scheduled_time: When to execute (None = immediate)
        """
        event = TradingEvent(
            event_type=event_type,
            data={
                "message": message,
                "level": level,
                "timestamp": datetime.now().isoformat()
            },
            scheduled_time=scheduled_time
        )
        await self.publish_event(event)


# Global event system instance
event_system = EventSystem()
