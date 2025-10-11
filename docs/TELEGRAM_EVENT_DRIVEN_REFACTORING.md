# Telegram Service Event-Driven Refactoring

## 📋 概述

将 `TelegramService` 完全解耦，使其只依赖 `EventSystem`，所有操作（查询、控制）都通过事件驱动架构实现。

## 🎯 重构目标

1. **完全解耦**: TelegramService 不再直接依赖 TradingSystem
2. **事件驱动**: 所有命令和查询都通过事件发布
3. **单向依赖**: TelegramService → EventSystem ← TradingSystem
4. **清晰职责**: TelegramService 只负责接收用户输入和发布事件

## 🔧 核心改动

### 1. TelegramService 初始化

**之前**:
```python
def __init__(self, trading_system=None):
    self.trading_system = trading_system
```

**现在**:
```python
def __init__(self, event_system=None):
    self.event_system = event_system
```

### 2. 命令处理器

所有命令处理器从直接调用 `trading_system` 方法改为发布事件：

#### /start 命令
**之前**: `await self.trading_system.start()`  
**现在**: `await self.event_system.publish_system_event("start_system", ...)`

#### /stop 命令
**之前**: `await self.trading_system.stop()`  
**现在**: `await self.event_system.publish_system_event("stop_system", ...)`

#### /status 命令
**之前**: `status = await self.trading_system.get_status()`  
**现在**: `await self.event_system.publish_system_event("query_status", ...)`

#### /portfolio 命令
**之前**: `portfolio = await self.trading_system.get_portfolio()`  
**现在**: `await self.event_system.publish_system_event("query_portfolio", ...)`

#### /orders 命令
**之前**: `orders = await self.trading_system.get_active_orders()`  
**现在**: `await self.event_system.publish_system_event("query_orders", ...)`

#### /analyze 命令
**之前**: `await self.trading_system.run_manual_analysis()`  
**现在**: `await self.event_system.publish_workflow_event(trigger="manual_analysis", ...)`

#### /emergency 命令
**之前**: `await self.trading_system.emergency_stop()`  
**现在**: `await self.event_system.publish_system_event("emergency_stop", ...)`

### 3. Callback Handlers

所有 callback handlers (按钮交互) 也改为发布事件：

- `_handle_status_callback` → 发布 `query_status` 事件
- `_handle_portfolio_callback` → 发布 `query_portfolio` 事件
- `_handle_orders_callback` → 发布 `query_orders` 事件
- `_handle_positions_callback` → 调用 `_handle_portfolio_callback`
- `_handle_analyze_callback` → 发布 workflow 事件
- `_handle_emergency_callback` → 发布 `emergency_stop` 事件

### 4. TradingSystem 事件处理器

在 `TradingSystem` 中添加了 6 个新的事件处理器：

#### 系统控制事件
- `_handle_start_system`: 处理系统启动请求
- `_handle_stop_system`: 处理系统停止请求
- `_handle_emergency_stop`: 处理紧急停止请求

#### 查询事件
- `_handle_query_status`: 处理状态查询，格式化并发送状态信息
- `_handle_query_portfolio`: 处理投资组合查询，发送格式化的组合信息
- `_handle_query_orders`: 处理订单查询，发送活跃订单列表

### 5. Factory 更新

`MessageTransportFactory.create_message_transport()` 方法更新：

**之前**:
```python
def create_message_transport(cls, trading_system=None, **kwargs):
    return transport_class(trading_system=trading_system, **kwargs)
```

**现在**:
```python
def create_message_transport(cls, event_system=None, **kwargs):
    return transport_class(event_system=event_system, **kwargs)
```

### 6. TradingSystem 初始化顺序

调整初始化顺序，确保 `event_system` 在创建 transport 之前初始化：

```python
def __init__(self):
    # Initialize APIs
    self.broker_api = get_broker_api()
    self.market_data_api = get_market_data_api()
    self.news_api = get_news_api()
    
    # Initialize event system first (needed by message transport)
    self.event_system = event_system
    
    # Initialize message manager with transport (pass event_system)
    transport = MessageTransportFactory.create_message_transport(
        event_system=self.event_system
    )
    self.message_manager = MessageManager(transport=transport)
```

## 📊 新增事件类型

| 事件类型 | 触发源 | 处理器 | 功能 |
|---------|--------|--------|------|
| `start_system` | Telegram /start | `_handle_start_system` | 启动交易系统 |
| `stop_system` | Telegram /stop | `_handle_stop_system` | 停止交易系统 |
| `emergency_stop` | Telegram /emergency | `_handle_emergency_stop` | 紧急停止所有操作 |
| `query_status` | Telegram /status | `_handle_query_status` | 查询系统状态 |
| `query_portfolio` | Telegram /portfolio | `_handle_query_portfolio` | 查询投资组合 |
| `query_orders` | Telegram /orders | `_handle_query_orders` | 查询活跃订单 |

## 🔄 数据流

### 旧架构 (紧耦合)
```
Telegram User → TelegramService → TradingSystem
                                   ↓
                              直接调用方法
                                   ↓
                              返回结果
```

### 新架构 (事件驱动)
```
Telegram User → TelegramService → EventSystem → TradingSystem
                                                  ↓
                                             处理事件
                                                  ↓
                                          通过 MessageManager
                                          发送响应到 Telegram
```

## ✅ 优势

1. **解耦**: TelegramService 不再依赖 TradingSystem 的具体实现
2. **可扩展**: 可以轻松添加其他消息传输方式 (Slack, Discord 等)
3. **统一接口**: 所有操作都通过统一的事件系统
4. **易于测试**: 可以独立测试 TelegramService 和 TradingSystem
5. **异步友好**: 事件发布后立即返回，不阻塞 Telegram bot
6. **单向依赖**: 清晰的依赖关系，便于维护

## 📝 事件数据格式

所有事件都包含 `chat_id` 用于响应：

```python
{
    "chat_id": "123456789",  # Telegram chat ID for response
    "source": "telegram_command"  # Optional: event source
}
```

TradingSystem 的事件处理器会提取 `chat_id` 并使用 `message_manager` 发送响应到该聊天。

## 🔍 响应机制

查询事件的响应流程：

1. TelegramService 发布查询事件（包含 chat_id）
2. TradingSystem 事件处理器接收事件
3. 处理器执行查询操作（获取数据）
4. 处理器格式化数据
5. 处理器通过 `message_manager.send_message(text, chat_id)` 发送响应
6. MessageManager 路由到正确的 transport (TelegramService)
7. TelegramService 发送消息到 Telegram

## 📂 修改的文件

1. `src/adapters/transports/telegram_service.py` - 完全重构
2. `src/trading_system.py` - 添加事件处理器
3. `src/interfaces/factory.py` - 更新 MessageTransportFactory
4. `src/events/event_system.py` - 无需修改（已支持所需功能）

## 🎉 总结

这次重构实现了完全的事件驱动架构，TelegramService 现在是一个纯粹的"表示层"组件，只负责：
- 接收用户输入
- 发布事件到 EventSystem
- 发送消息给用户

所有业务逻辑都保留在 TradingSystem 中，通过事件处理器响应。这种架构更加清晰、可维护、可扩展。

