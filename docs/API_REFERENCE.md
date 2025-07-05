# 📚 API Reference

This document provides detailed information about the APIs and interfaces in the LLM Trading Agent system.

## 🏗️ System Architecture

The system is organized into several key components:

- **Trading System**: Main orchestrator (`TradingSystem`)
- **Event System**: Redis-based event handling (`EventSystem`)
- **APIs**: External service integrations
- **Workflow**: LangGraph-based decision making
- **Scheduler**: Automated job management

## 🎯 Core Classes

### TradingSystem

Main orchestrator class that coordinates all system components.

```python
from src.trading_system import TradingSystem

# Initialize
trading_system = TradingSystem()

# Start the system
await trading_system.start()

# Stop the system
await trading_system.stop()
```

#### Methods

##### `async start()`
Starts the entire trading system including all components.

**Returns:** `None`

**Raises:** `Exception` if startup fails

##### `async stop()`
Stops the trading system gracefully.

**Returns:** `None`

##### `async start_trading()`
Enables trading operations (system must be started first).

**Returns:** `None`

##### `async stop_trading()`
Disables trading operations but keeps system running.

**Returns:** `None`

##### `async emergency_stop()`
Emergency shutdown - cancels all orders and closes positions.

**Returns:** `None`

##### `async get_portfolio() -> Portfolio`
Gets current portfolio information.

**Returns:** `Portfolio` object with current positions and metrics

##### `async get_status() -> Dict[str, Any]`
Gets comprehensive system status.

**Returns:** Dictionary with system status information

---

### AlpacaAPI

Wrapper for Alpaca Trading API operations.

```python
from src.apis.alpaca_api import AlpacaAPI

alpaca = AlpacaAPI()
portfolio = alpaca.get_portfolio()
```

#### Methods

##### `get_portfolio() -> Portfolio`
Retrieves current portfolio information.

**Returns:** `Portfolio` object

##### `place_order(order: Order) -> Order`
Places a trading order.

**Parameters:**
- `order`: Order object with trading details

**Returns:** Updated Order object with execution details

##### `cancel_order(order_id: str) -> bool`
Cancels an existing order.

**Parameters:**
- `order_id`: Alpaca order ID

**Returns:** `True` if successful

##### `get_orders(status: str = None) -> List[Order]`
Gets list of orders.

**Parameters:**
- `status`: Optional status filter ("open", "closed", etc.)

**Returns:** List of Order objects

##### `get_market_data(symbol: str) -> MarketData`
Gets current market data for a symbol.

**Parameters:**
- `symbol`: Stock symbol (e.g., "AAPL")

**Returns:** MarketData object

##### `is_market_open() -> bool`
Checks if market is currently open.

**Returns:** `True` if market is open

---

### TiingoAPI

Wrapper for Tiingo News and Data API.

```python
from src.apis.tiingo_api import TiingoAPI

tiingo = TiingoAPI()
news = tiingo.get_news(limit=10)
```

#### Methods

##### `get_news(symbols: List[str] = None, limit: int = 100) -> List[NewsItem]`
Gets news articles.

**Parameters:**
- `symbols`: Optional list of stock symbols to filter
- `limit`: Maximum number of articles

**Returns:** List of NewsItem objects

##### `get_symbol_news(symbol: str, limit: int = 50) -> List[NewsItem]`
Gets news for a specific symbol.

**Parameters:**
- `symbol`: Stock symbol
- `limit`: Maximum number of articles

**Returns:** List of NewsItem objects

##### `get_market_overview() -> Dict[str, Any]`
Gets market overview data for major indices.

**Returns:** Dictionary with market data

---

### TelegramBot

Telegram bot for remote control and notifications.

```python
from src.apis.telegram_bot import TelegramBot

bot = TelegramBot()
await bot.send_message("Hello!")
```

#### Methods

##### `async send_message(message: str, parse_mode: str = None)`
Sends a message to the configured chat.

**Parameters:**
- `message`: Message text
- `parse_mode`: Optional formatting ("Markdown", "HTML")

**Returns:** `None`

##### `async send_order_notification(order: Order, event_type: str)`
Sends order-related notification.

**Parameters:**
- `order`: Order object
- `event_type`: Type of event ("order_filled", etc.)

**Returns:** `None`

##### `async send_portfolio_update(portfolio: Portfolio)`
Sends portfolio update notification.

**Parameters:**
- `portfolio`: Portfolio object

**Returns:** `None`

---

### EventSystem

Redis-based event handling system.

```python
from src.events.event_system import event_system

# Register event handler
event_system.register_handler("order_filled", my_handler)

# Publish event
await event_system.publish_event(trading_event)
```

#### Methods

##### `register_handler(event_type: str, handler: Callable)`
Registers an event handler.

**Parameters:**
- `event_type`: Type of event to handle
- `handler`: Function to call when event occurs

**Returns:** `None`

##### `async publish_event(event: TradingEvent)`
Publishes an event to the system.

**Parameters:**
- `event`: TradingEvent object

**Returns:** `None`

##### `async publish_order_event(order: Order, event_type: str)`
Convenience method for order events.

**Parameters:**
- `order`: Order object
- `event_type`: Event type

**Returns:** `None`

---

## 📊 Data Models

### Portfolio

```python
class Portfolio(BaseModel):
    equity: Decimal
    cash: Decimal
    market_value: Decimal
    day_trade_count: int
    buying_power: Decimal
    positions: List[Position]
    total_pnl: Decimal
    day_pnl: Decimal
    last_updated: datetime
```

### Order

```python
class Order(BaseModel):
    id: Optional[str]
    symbol: str
    side: OrderSide  # BUY or SELL
    order_type: OrderType  # MARKET, LIMIT, etc.
    quantity: Decimal
    price: Optional[Decimal]
    status: OrderStatus
    filled_quantity: Decimal
    filled_price: Optional[Decimal]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
```

### Position

```python
class Position(BaseModel):
    symbol: str
    quantity: Decimal
    market_value: Decimal
    cost_basis: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_percentage: Decimal
    side: str  # "long" or "short"
```

### TradingDecision

```python
class TradingDecision(BaseModel):
    action: str  # "buy", "sell", "hold"
    symbol: str
    quantity: Optional[Decimal]
    price: Optional[Decimal]
    reasoning: str
    confidence: float  # 0.0 to 1.0
    stop_loss: Optional[Decimal]
    take_profit: Optional[Decimal]
```

### NewsItem

```python
class NewsItem(BaseModel):
    title: str
    description: str
    url: str
    source: str
    published_at: datetime
    symbols: List[str]
    sentiment: Optional[str]
```

---

## 🔄 Events

The system uses an event-driven architecture with the following event types:

### Order Events

- `order_created`: New order placed
- `order_filled`: Order executed
- `order_canceled`: Order cancelled
- `order_rejected`: Order rejected

### Portfolio Events

- `portfolio_updated`: Portfolio data refreshed

### System Events

- `system_started`: System startup
- `system_stopped`: System shutdown
- `trading_started`: Trading enabled
- `trading_stopped`: Trading disabled
- `emergency_stop`: Emergency shutdown
- `error`: System error

### Event Handler Example

```python
async def my_order_handler(event: TradingEvent):
    order_data = event.data
    print(f"Order {order_data['order_id']} was {event.event_type}")

# Register handler
event_system.register_handler("order_filled", my_order_handler)
```

---

## 🤖 LangGraph Workflow

The trading workflow is implemented using LangGraph with the following nodes:

### Workflow Nodes

1. **gather_data**: Collects portfolio, market data, and news
2. **analyze_market**: AI analyzes current market conditions  
3. **make_decision**: AI makes trading decisions
4. **execute_trades**: Executes approved trades

### Workflow State

```python
class TradingState(BaseModel):
    messages: List[Dict]
    portfolio: Optional[Portfolio]
    market_data: Dict[str, Any]
    news: List[Dict[str, Any]]
    decision: Optional[TradingDecision]
    context: Dict[str, Any]
```

### Running the Workflow

```python
from src.agents.trading_workflow import TradingWorkflow

workflow = TradingWorkflow(alpaca_api, tiingo_api)
result = await workflow.run_workflow()
```

---

## ⏰ Scheduler

The scheduler manages automated tasks:

### Default Schedule

- **Daily Rebalancing**: Market open (9:30 AM ET)
- **Portfolio Monitoring**: Every hour during market hours
- **Risk Checks**: Every 15 minutes during market hours
- **Market Close Analysis**: 4:05 PM ET
- **Daily Cleanup**: Midnight

### Custom Jobs

```python
from src.scheduler.trading_scheduler import TradingScheduler

scheduler = TradingScheduler()

# Add custom job
scheduler.add_custom_job(
    job_id="my_job",
    schedule_time="10:00",
    job_func=my_function,
    days=["monday", "wednesday", "friday"]
)
```

---

## 🔧 Configuration

### Environment Variables

All configuration is managed through environment variables:

```bash
# Trading APIs
ALPACA_API_KEY=your_key
ALPACA_SECRET_KEY=your_secret
TIINGO_API_KEY=your_key

# AI
OPENAI_API_KEY=your_key
OPENAI_MODEL=gpt-4o

# Notifications
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id

# Risk Management
MAX_POSITION_SIZE=0.1
STOP_LOSS_PERCENTAGE=0.05
TAKE_PROFIT_PERCENTAGE=0.15

# System
ENVIRONMENT=development
LOG_LEVEL=INFO
```

### Settings Object

```python
from config import settings

print(settings.max_position_size)  # 0.1
print(settings.alpaca_api_key)     # your_key
```

---

## 🚨 Error Handling

### Exception Types

The system defines several custom exception types:

- `TradingSystemError`: General system errors
- `APIConnectionError`: API connection issues
- `OrderExecutionError`: Trading execution errors
- `RiskManagementError`: Risk limit violations

### Error Events

Errors are published as events and can be handled:

```python
async def error_handler(event: TradingEvent):
    error_msg = event.data['message']
    level = event.data['level']
    # Handle error appropriately

event_system.register_handler("error", error_handler)
```

---

## 📊 Logging

### Log Levels

- `DEBUG`: Detailed debugging information
- `INFO`: General information about system operation
- `WARNING`: Warning messages for potential issues
- `ERROR`: Error messages for serious problems

### Log Format

```
2024-01-01 10:00:00 - module_name - LEVEL - message
```

### Log Files

- Location: `logs/trading_agent_YYYYMMDD.log`
- Rotation: Daily
- Retention: Configurable

---

## 🔐 Security

### API Key Management

- Store in `.env` file
- Never commit to version control
- Use environment variables in production

### Risk Controls

- Position size limits
- Stop loss orders
- Portfolio risk monitoring
- Emergency stop functionality

### Telegram Security

- Bot token protection
- Chat ID verification
- Command authentication

---

## 🧪 Testing

### Unit Tests

```python
import unittest
from src.apis.alpaca_api import AlpacaAPI

class TestAlpacaAPI(unittest.TestCase):
    def setUp(self):
        self.api = AlpacaAPI()
    
    def test_get_portfolio(self):
        portfolio = self.api.get_portfolio()
        self.assertIsNotNone(portfolio.equity)
```

### Integration Tests

```python
import asyncio
from src.trading_system import TradingSystem

async def test_system_startup():
    system = TradingSystem()
    await system.start()
    status = await system.get_status()
    assert status['status'] == 'running'
    await system.stop()
```

### API Testing

Use the provided `test_apis.py` script to verify API connections:

```bash
python test_apis.py
```

---

## 📈 Performance Monitoring

### Metrics

The system tracks various performance metrics:

- Trade execution latency
- API response times
- Event processing speed
- Memory usage
- Error rates

### Monitoring Tools

- Built-in logging
- Telegram notifications
- Redis monitoring
- Custom metrics collection

---

This API reference provides the foundation for understanding and extending the LLM Trading Agent system. For additional examples and use cases, refer to the main README.md and setup documentation. 