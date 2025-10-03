from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from decimal import Decimal
from enum import Enum
import pytz


def utc_now():
    """Get current UTC time (timezone-aware)"""
    return datetime.now(pytz.UTC)


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    STOP_LIMIT = "stop_limit"

class TimeInForce(str, Enum):
    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"

class OrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"


class TradingAction(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class Position(BaseModel):
    """Portfolio position model"""
    symbol: str
    quantity: Decimal
    market_value: Decimal
    cost_basis: Decimal = Decimal('0')
    unrealized_pnl: Decimal = Decimal('0')
    unrealized_pnl_percentage: Decimal = Decimal('0')
    side: PositionSide
    avg_entry_price: Optional[Decimal] = None
    

class Order(BaseModel):
    """Order model"""
    id: Optional[str] = None
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    time_in_force: TimeInForce = TimeInForce.DAY
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: Decimal = Decimal('0')
    filled_price: Optional[Decimal] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    client_order_id: Optional[str] = None
    
    @property
    def filled_percentage(self) -> Decimal:
        """Calculate filled percentage"""
        if self.quantity == 0:
            return Decimal('0')
        return (self.filled_quantity / self.quantity) * Decimal('100')
    
    @property
    def is_filled(self) -> bool:
        """Check if order is completely filled"""
        return self.status == OrderStatus.FILLED


class Portfolio(BaseModel):
    """Portfolio model"""
    equity: Decimal
    cash: Decimal
    market_value: Decimal
    day_trade_count: int = 0
    buying_power: Decimal = Decimal('0')
    positions: List[Position] = []
    total_pnl: Decimal = Decimal('0')
    day_pnl: Decimal = Decimal('0')
    last_updated: datetime = Field(default_factory=datetime.now)


class MarketData(BaseModel):
    """Market data model"""
    symbol: str
    price: Decimal
    bid: Optional[Decimal] = None
    ask: Optional[Decimal] = None
    volume: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class NewsItem(BaseModel):
    """News item model"""
    title: str
    description: str
    url: str
    source: str
    published_at: datetime
    symbols: List[str] = []
    sentiment: Optional[Decimal] = None  # -1.0 to 1.0 sentiment score
    created_at: datetime = Field(default_factory=datetime.now)


class TradingEvent(BaseModel):
    """
    Trading event model for event-driven system with scheduled execution
    
    Events can be scheduled for future execution by setting scheduled_time.
    If scheduled_time is None, event executes immediately.
    All datetimes are timezone-aware (UTC) to avoid comparison issues.
    """
    event_type: str  # "trigger_daily_rebalance", "trigger_manual_analysis", etc.
    timestamp: datetime = Field(default_factory=utc_now)  # When event was created (UTC)
    scheduled_time: Optional[datetime] = None  # When event should execute (None = immediate)
    data: Dict[str, Any]
    processed: bool = False
    priority: int = 0  # Lower number = higher priority (for events at same time)
    
    def __lt__(self, other):
        """Compare events for priority queue ordering"""
        if not isinstance(other, TradingEvent):
            return NotImplemented
        # Primary: scheduled_time (None = immediate = now)
        self_time = self.scheduled_time or self.timestamp
        other_time = other.scheduled_time or other.timestamp
        if self_time != other_time:
            return self_time < other_time
        # Secondary: priority
        return self.priority < other.priority


class TradingDecision(BaseModel):
    """Trading decision from LLM"""
    action: TradingAction
    symbol: str
    quantity: Optional[Decimal] = None
    price: Optional[Decimal] = None
    reasoning: str
    confidence: Decimal = Field(ge=Decimal('0.0'), le=Decimal('1.0'))
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    created_at: datetime = Field(default_factory=datetime.now) 