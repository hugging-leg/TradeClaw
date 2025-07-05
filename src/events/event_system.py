import asyncio
import json
import logging
from typing import Dict, List, Callable, Any, Optional
from datetime import datetime
import redis.asyncio as redis
from src.models.trading_models import TradingEvent, Order, Portfolio
from config import settings


logger = logging.getLogger(__name__)


class EventSystem:
    """Event-driven system for trading events"""
    
    def __init__(self):
        self.redis_client = None
        self.pubsub = None
        self.event_handlers: Dict[str, List[Callable]] = {}
        self.is_running = False
        self.event_queue = asyncio.Queue()
        
    async def initialize(self):
        """Initialize Redis connection and pubsub"""
        try:
            self.redis_client = redis.from_url(settings.redis_url)
            self.pubsub = self.redis_client.pubsub()
            logger.info("Event system initialized")
        except Exception as e:
            logger.error(f"Failed to initialize event system: {e}")
            raise
    
    async def start(self):
        """Start the event system"""
        if not self.redis_client:
            await self.initialize()
        
        self.is_running = True
        
        # Subscribe to all trading events
        await self.pubsub.subscribe("trading_events")
        
        # Start event processing tasks
        asyncio.create_task(self._process_events())
        asyncio.create_task(self._handle_pubsub_messages())
        
        logger.info("Event system started")
    
    async def stop(self):
        """Stop the event system"""
        self.is_running = False
        
        if self.pubsub:
            await self.pubsub.unsubscribe("trading_events")
            await self.pubsub.close()
        
        if self.redis_client:
            await self.redis_client.close()
        
        logger.info("Event system stopped")
    
    def register_handler(self, event_type: str, handler: Callable):
        """Register an event handler"""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        
        self.event_handlers[event_type].append(handler)
        logger.info(f"Registered handler for event type: {event_type}")
    
    def unregister_handler(self, event_type: str, handler: Callable):
        """Unregister an event handler"""
        if event_type in self.event_handlers:
            try:
                self.event_handlers[event_type].remove(handler)
                logger.info(f"Unregistered handler for event type: {event_type}")
            except ValueError:
                logger.warning(f"Handler not found for event type: {event_type}")
    
    async def publish_event(self, event: TradingEvent):
        """Publish an event to the system"""
        try:
            # Serialize event data
            event_data = {
                "event_type": event.event_type,
                "timestamp": event.timestamp.isoformat(),
                "data": event.data,
                "processed": event.processed
            }
            
            # Publish to Redis
            await self.redis_client.publish("trading_events", json.dumps(event_data))
            
            # Add to local queue for immediate processing
            await self.event_queue.put(event)
            
            logger.debug(f"Published event: {event.event_type}")
            
        except Exception as e:
            logger.error(f"Failed to publish event: {e}")
    
    async def _process_events(self):
        """Process events from the queue"""
        while self.is_running:
            try:
                # Get event from queue with timeout
                event = await asyncio.wait_for(self.event_queue.get(), timeout=1.0)
                
                # Process the event
                await self._handle_event(event)
                
            except asyncio.TimeoutError:
                # No event received within timeout, continue loop
                continue
            except Exception as e:
                logger.error(f"Error processing event: {e}")
    
    async def _handle_pubsub_messages(self):
        """Handle messages from Redis pubsub"""
        while self.is_running:
            try:
                message = await self.pubsub.get_message(timeout=1.0)
                
                if message and message['type'] == 'message':
                    # Deserialize event data
                    event_data = json.loads(message['data'])
                    
                    # Create event object
                    event = TradingEvent(
                        event_type=event_data['event_type'],
                        timestamp=datetime.fromisoformat(event_data['timestamp']),
                        data=event_data['data'],
                        processed=event_data['processed']
                    )
                    
                    # Process the event
                    await self._handle_event(event)
                    
            except asyncio.TimeoutError:
                # No message received within timeout, continue loop
                continue
            except Exception as e:
                logger.error(f"Error handling pubsub message: {e}")
    
    async def _handle_event(self, event: TradingEvent):
        """Handle a single event"""
        try:
            # Get handlers for this event type
            handlers = self.event_handlers.get(event.event_type, [])
            
            if not handlers:
                logger.warning(f"No handlers registered for event type: {event.event_type}")
                return
            
            # Execute all handlers
            for handler in handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        handler(event)
                except Exception as e:
                    logger.error(f"Error in event handler: {e}")
            
            # Mark event as processed
            event.processed = True
            
        except Exception as e:
            logger.error(f"Error handling event: {e}")
    
    # Event publishing convenience methods
    async def publish_order_event(self, order: Order, event_type: str):
        """Publish an order-related event"""
        event = TradingEvent(
            event_type=event_type,
            data={
                "order_id": order.id,
                "symbol": order.symbol,
                "side": order.side.value,
                "quantity": str(order.quantity),
                "price": str(order.price) if order.price else None,
                "status": order.status.value,
                "filled_quantity": str(order.filled_quantity),
                "filled_price": str(order.filled_price) if order.filled_price else None,
                "created_at": order.created_at.isoformat() if order.created_at else None,
                "updated_at": order.updated_at.isoformat() if order.updated_at else None
            }
        )
        
        await self.publish_event(event)
    
    async def publish_portfolio_event(self, portfolio: Portfolio):
        """Publish a portfolio update event"""
        event = TradingEvent(
            event_type="portfolio_updated",
            data={
                "equity": str(portfolio.equity),
                "cash": str(portfolio.cash),
                "market_value": str(portfolio.market_value),
                "day_pnl": str(portfolio.day_pnl),
                "total_pnl": str(portfolio.total_pnl),
                "buying_power": str(portfolio.buying_power),
                "position_count": len(portfolio.positions),
                "positions": [
                    {
                        "symbol": pos.symbol,
                        "quantity": str(pos.quantity),
                        "market_value": str(pos.market_value),
                        "unrealized_pnl": str(pos.unrealized_pnl),
                        "side": pos.side
                    }
                    for pos in portfolio.positions
                ],
                "last_updated": portfolio.last_updated.isoformat()
            }
        )
        
        await self.publish_event(event)
    
    async def publish_market_event(self, event_type: str, data: Dict[str, Any]):
        """Publish a market-related event"""
        event = TradingEvent(
            event_type=event_type,
            data=data
        )
        
        await self.publish_event(event)
    
    async def publish_system_event(self, event_type: str, message: str, level: str = "info"):
        """Publish a system event"""
        event = TradingEvent(
            event_type=event_type,
            data={
                "message": message,
                "level": level
            }
        )
        
        await self.publish_event(event)
    
    async def get_event_history(self, event_type: Optional[str] = None, limit: int = 100) -> List[TradingEvent]:
        """Get event history from storage"""
        try:
            # This is a simplified implementation
            # In a production system, you'd want to store events in a database
            # and implement proper pagination and filtering
            
            # For now, return empty list
            return []
            
        except Exception as e:
            logger.error(f"Failed to get event history: {e}")
            return []


# Global event system instance
event_system = EventSystem() 