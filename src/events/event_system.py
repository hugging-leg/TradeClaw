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
    - trigger_workflow: Unified workflow trigger (with trigger type in data)
    - trigger_portfolio_check: Scheduled portfolio check
    - trigger_risk_check: Risk check
    - trigger_eod_analysis: End-of-day analysis
    - enable_trading / disable_trading: Trading control events
    
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
    
    async def publish(
        self,
        event_type: str,
        data: Dict[str, Any] = None,
        scheduled_time: Optional[datetime] = None,
        priority: int = 0
    ):
        """
        Unified event publishing method
        
        Args:
            event_type: Type of event (trigger_workflow, enable_trading, query_status, etc.)
            data: Event data dictionary
            scheduled_time: When to execute (None = immediate)
            priority: Event priority (lower number = higher priority, default: 0)
        
        Examples:
            # Normal priority workflow trigger
            await event_system.publish("trigger_workflow", {"trigger": "daily_rebalance"})
            
            # High priority risk alert
            from src.models.trading_models import EventPriority
            await event_system.publish("trigger_workflow", 
                                      {"trigger": "risk_alert"}, 
                                      priority=EventPriority.HIGH)
            
            # Low priority background check
            await event_system.publish("trigger_portfolio_check", 
                                      scheduled_time=next_check,
                                      priority=EventPriority.LOW)
        """
        # Ensure data has timestamp
        event_data = data or {}
        if "timestamp" not in event_data:
            event_data["timestamp"] = datetime.now().isoformat()
        
        event = TradingEvent(
            event_type=event_type,
            data=event_data,
            scheduled_time=scheduled_time,
            priority=priority
        )
        await self.publish_event(event)


# Global event system instance
event_system = EventSystem()
