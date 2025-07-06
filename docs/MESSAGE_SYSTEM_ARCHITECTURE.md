# Message System Architecture

## Overview

The message system has been redesigned to follow a clean, layered architecture with clear separation of concerns. This design eliminates redundancy and provides the right level of abstraction for each layer.

## Architecture Layers

### 1. MessageTransport (Interface)
- **Purpose**: Handles only raw message delivery
- **Location**: `src/interfaces/message_transport.py`
- **Uses Factory Pattern**: ✅ Yes - Different transport providers (Telegram, Discord, Slack, Email)
- **Responsibilities**:
  - Raw message transmission
  - Connection management
  - Rate limiting
  - Transport-specific formatting (e.g., Telegram parse modes)

### 2. TradingMessageQueue (Direct Implementation)
- **Purpose**: Handles business-level message operations
- **Location**: `src/messaging/trading_message_queue.py`
- **Uses Factory Pattern**: ❌ No - Direct implementation
- **Responsibilities**:
  - Message formatting and templating
  - Business message types (orders, portfolio updates, alerts)
  - Queue management and prioritization
  - Retry logic
  - Uses MessageTransport for actual delivery

### 3. Implementations

#### Transport Layer (Factory Pattern)
- **TelegramTransport** (`src/adapters/transports/telegram_transport.py`)
- **DiscordTransport** (Future implementation)
- **SlackTransport** (Future implementation)
- **EmailTransport** (Future implementation)

#### Queue Layer (Direct Implementation)
- **TradingMessageQueue** (`src/messaging/trading_message_queue.py`)
  - Single implementation for trading business logic
  - No interface abstraction needed

## Why Different Patterns?

### MessageTransport: Interface + Factory Pattern ✅
- **Reason**: Different transport protocols are fundamentally different
- **Examples**: Telegram API vs Discord API vs SMTP
- **Benefits**: Easy to switch between transport providers
- **Configuration**: `message_provider = "telegram"`

### TradingMessageQueue: Direct Implementation ❌
- **Reason**: Business logic is specific to trading domain
- **Examples**: Order notifications, portfolio updates are always the same format
- **Benefits**: Simpler, no unnecessary abstraction
- **Implementation**: Direct class in `src/messaging/`

## Message Flow

```
Trading System → TradingMessageQueue → MessageTransport → External Service
                      ↓                     ↓
                 Business Logic     Configurable Transport
                 - Order formatting    - Telegram API
                 - Portfolio updates   - Discord API
                 - Alert templates     - Slack API
```

## Benefits of This Design

### 1. Right Level of Abstraction
- **Transport Layer**: Interface where it makes sense (different protocols)
- **Queue Layer**: Direct implementation where it makes sense (business logic)

### 2. Reduced Complexity
- No unnecessary MessageQueue interface
- Simpler configuration
- Less code to maintain

### 3. Clear Separation of Concerns
- **Transport**: "How to send messages"
- **Queue**: "What messages to send and when"

### 4. Extensibility Where Needed
- Easy to add new transports (Discord, Slack, Email)
- Business logic stays in one place (TradingMessageQueue)
- Transport and queue are loosely coupled

## Usage Examples

### Creating Message Queue
```python
from src.interfaces.factory import get_message_queue

# Simple - creates TradingMessageQueue with default transport
message_queue = get_message_queue()

# Custom transport
transport = get_message_transport("discord")
message_queue = get_message_queue(transport=transport)
```

### Sending Messages
```python
# Business-level operations
await message_queue.send_order_notification(order, "created")
await message_queue.send_portfolio_update(portfolio)
await message_queue.send_system_alert("error", "Connection failed")

# Queue management
await message_queue.start_processing()
processed = await message_queue.process_queue()
```

### Adding New Transport
```python
from src.interfaces.message_transport import MessageTransport

class DiscordTransport(MessageTransport):
    async def send_raw_message(self, content, format_type):
        # Implement Discord-specific sending
        pass

# Register in factory
MessageTransportFactory.register_provider(
    MessageTransportProvider.DISCORD,
    "src.adapters.transports.discord_transport:DiscordTransport"
)
```

## Configuration

```python
# config.py
message_provider: str = "telegram"  # Transport provider only
```

## File Structure

```
src/
├── interfaces/
│   └── message_transport.py        # Transport interface
├── messaging/
│   └── trading_message_queue.py    # Business logic implementation
├── adapters/
│   └── transports/
│       └── telegram_transport.py   # Transport implementations
└── interfaces/
    └── factory.py                  # Factory for transports
```

## Migration from Old Design

### Before (Over-abstracted)
```python
# Unnecessary interface abstraction
from src.interfaces.message_queue import MessageQueue
message_queue: MessageQueue = MessageQueueFactory.create_message_queue()
```

### After (Right Abstraction)
```python
# Simple and clear
from src.messaging.trading_message_queue import TradingMessageQueue
message_queue = get_message_queue()  # Returns TradingMessageQueue
```

## Design Principles Applied

1. **YAGNI (You Aren't Gonna Need It)**: Don't create abstractions until you actually need them
2. **Single Responsibility**: Each layer has a clear, single purpose
3. **Interface Segregation**: Only create interfaces where multiple implementations exist
4. **Direct Implementation**: For business logic that's domain-specific

This design provides the right balance of flexibility (where needed) and simplicity (where appropriate), avoiding over-engineering while maintaining clean architecture. 