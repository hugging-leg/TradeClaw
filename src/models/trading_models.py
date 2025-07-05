from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from decimal import Decimal
from enum import Enum


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"


class TimeInForce(str, Enum):
    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


class Position(BaseModel):
    """Portfolio position model"""
    symbol: str
    quantity: Decimal
    market_value: Decimal
    cost_basis: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_percentage: Decimal
    side: str  # "long" or "short"
    

class Order(BaseModel):
    """Order model"""
    id: Optional[str] = None
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    time_in_force: TimeInForce = TimeInForce.DAY
    status: OrderStatus = OrderStatus.NEW
    filled_quantity: Decimal = Decimal('0')
    filled_price: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    client_order_id: Optional[str] = None


class Portfolio(BaseModel):
    """Portfolio model"""
    equity: Decimal
    cash: Decimal
    market_value: Decimal
    day_trade_count: int
    buying_power: Decimal
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
    sentiment: Optional[str] = None  # "positive", "negative", "neutral"


class TradingEvent(BaseModel):
    """Trading event model for event-driven system"""
    event_type: str  # "order_created", "order_filled", "order_canceled", "portfolio_updated"
    timestamp: datetime = Field(default_factory=datetime.now)
    data: Dict[str, Any]
    processed: bool = False


class TradingDecision(BaseModel):
    """Trading decision from LLM"""
    action: str  # "buy", "sell", "hold"
    symbol: str
    quantity: Optional[Decimal] = None
    price: Optional[Decimal] = None
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None 