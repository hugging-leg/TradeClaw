# 🤖 LLM Trading Agent

A sophisticated, event-driven trading system that uses advanced LLMs (OpenAI or DeepSeek) to make intelligent trading decisions for US stocks. The system features a **factory pattern architecture** with multiple workflow types and integrates multiple APIs, using LangGraph for orchestrating complex trading workflows with real-time Telegram notifications.

## ⚡ Key Features

- **🧠 AI-Powered Trading**: Uses OpenAI GPT-4o/O3 or DeepSeek models for intelligent trading decisions
- **🏭 Factory Pattern Architecture**: Multiple workflow types with configurable strategies
- **⚙️ Flexible Workflow Types**: Choose between Sequential (fixed-step) or Tool Calling (dynamic) workflows
- **💰 Cost-Effective Options**: Choose between OpenAI (premium) or DeepSeek (cost-effective) LLM providers
- **📊 Real-Time Data**: Integrates Alpaca API for trading and Tiingo for market data
- **🔄 Event-Driven Architecture**: In-memory event system for real-time event handling
- **📱 Enhanced Telegram Control**: Complete remote control with improved command handlers and real-time workflow progress notifications
- **🔗 LangGraph Workflow**: Structured AI decision pipeline with live progress tracking
- **📢 Intelligent Message System**: Advanced message formatting with anti-flood protection and markdown support
- **⏰ Automated Scheduling**: Daily rebalancing and risk management with robust restart functionality
- **🛡️ Risk Management**: Built-in stop-loss, take-profit, and portfolio risk controls
- **🔐 Paper Trading**: Safe testing environment with Alpaca paper trading
- **🧹 Clean Code Architecture**: Modular design with dedicated utility modules for better maintainability

## 🏗️ System Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Telegram Bot  │    │ OpenAI/DeepSeek │    │   Alpaca API    │
│ (Enhanced UI)   │    │   (Decisions)   │    │   (Trading)     │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                    ┌─────────────▼─────────────┐
                    │     Trading System        │
                    │   (Enhanced Orchestrator) │
                    └─────────────┬─────────────┘
                                 │
                    ┌─────────────▼─────────────┐
                    │   Workflow Factory        │
                    │   (Pattern-Based)         │
                    └─────────────┬─────────────┘
                                 │
               ┌─────────────────┬─────────────────┐
               │                                  │
     ┌─────────▼───────┐                ┌─────────▼───────┐
     │ Sequential      │                │ Tool Calling    │
     │ Workflow        │                │ Workflow        │
     │ (Fixed Steps)   │                │ (Dynamic LLM)   │
     └─────────────────┘                └─────────────────┘
          │                                      │
          └──────────────────┬───────────────────┘
          │                  │                   │
┌─────────▼───────┐ ┌─────────▼───────┐ ┌─────────▼───────┐
│  Event System   │ │   Scheduler     │ │Message Manager  │
│  (In-Memory)    │ │  (Enhanced)     │ │ (Intelligent)   │
└─────────────────┘ └─────────────────┘ └─────────────────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                    ┌─────────────▼─────────────┐
                    │     Utility Modules       │
                    │  (String Processing)      │
                    └─────────────┬─────────────┘
                                 │
                    ┌─────────────▼─────────────┐
                    │     Tiingo API            │
                    │     (News & Data)         │
                    └───────────────────────────┘
```

## 🧹 Recent Improvements (v2.0)

### 🔧 **String Processing Refactoring**
- **200+ lines moved** from business logic to dedicated utility modules
- **New `src/utils/` directory** with specialized string processing functions:
  - `string_utils.py`: General text processing and formatting
  - `telegram_utils.py`: Telegram-specific markdown handling and escaping
  - `message_formatters.py`: Portfolio, order, and alert message formatting
- **Improved code reusability** and eliminated duplicate formatting logic
- **Enhanced maintainability** with centralized string processing

### 📱 **Enhanced Telegram Command Handlers**
- **Fixed command processing issues**: Resolved stopped message problems and duplicate notifications
- **Improved markdown formatting**: Better bold text support and special character escaping
- **Enhanced error handling**: More robust command processing with graceful fallbacks
- **Unified message flow**: Centralized message handling through message manager
- **Better user experience**: Cleaner command responses and status updates

### 🔄 **System Reliability Improvements**
- **Robust restart functionality**: Enhanced scheduler thread lifecycle management
- **Graceful shutdown**: Improved stop/start cycles while preserving command availability
- **Better error recovery**: Enhanced exception handling and system state management
- **Improved logging**: More detailed system state tracking and debugging information

### 🏗️ **Code Organization Enhancements**
- **Modular architecture**: Better separation of concerns across components
- **Utility abstraction**: Common functions extracted to reusable modules
- **Interface consistency**: Standardized message formatting and handling
- **Backward compatibility**: All improvements maintain existing functionality

## 🏭 Workflow Factory Pattern

The system uses a **factory pattern** to create different types of trading workflows, providing flexibility and extensibility:

### 🔄 Available Workflow Types

#### 1. Sequential Workflow (`sequential`)
**Description**: Fixed-step workflow with predictable execution sequence

**Characteristics**:
- ✅ Fixed four-step process (Data → Analysis → Decision → Execution)
- ✅ Highly predictable and consistent results
- ✅ Uses LangGraph state management
- ✅ Lower token usage and cost
- ✅ Great for systematic trading strategies

**Best For**: Consistent, repeatable trading analysis with predictable patterns

#### 2. Tool Calling Workflow (`tool_calling`)
**Description**: Dynamic workflow where LLM decides which tools to use and when

**Characteristics**:
- 🤖 LLM dynamically selects which tools to call
- 🤖 Flexible execution order based on AI reasoning
- 🤖 Real-time tool calling with iteration loops
- 🤖 Intelligent decision-making process
- 🤖 Higher token usage but more adaptive

**Available Tools**:
- `get_portfolio_info`: Get current portfolio status
- `get_market_data`: Fetch market data for symbols
- `get_news`: Retrieve financial news
- `get_market_status`: Check if markets are open
- `get_active_orders`: View pending orders
- `make_trading_decision`: Make final trading decision

**Best For**: Adaptive, intelligent trading analysis that responds to market conditions

### 🔄 Workflow Configuration

Configure your preferred workflow type in `.env`:

```bash
# Workflow Configuration
WORKFLOW_TYPE=sequential      # Options: sequential, tool_calling

# For tool_calling workflow, ensure you have a compatible LLM provider
LLM_PROVIDER=openai          # Options: openai, deepseek
```

### 📊 Workflow Comparison

| Feature | Sequential Workflow | Tool Calling Workflow |
|---------|-------------------|---------------------|
| **Execution Pattern** | Fixed four-step flow | LLM dynamic decisions |
| **Predictability** | High (same steps always) | Medium (LLM dependent) |
| **Flexibility** | Low | High |
| **Tool Usage** | Predefined calls | Dynamic tool selection |
| **Token Usage** | Lower | Higher (multi-turn) |
| **Cost** | Lower | Higher |
| **Speed** | Faster | Slower (iterations) |
| **Adaptability** | Low | High |
| **Use Case** | Systematic analysis | Market-responsive strategies |
| **Best For** | Consistent strategies | Adaptive analysis |

### 🔧 Factory Pattern Benefits

1. **🔄 Easy Switching**: Change workflow types via configuration
2. **🛡️ Type Safety**: Compile-time validation of workflow types
3. **📝 Extensibility**: Add new workflow types without breaking existing code
4. **🔍 Validation**: Automatic configuration validation
5. **🏗️ Dependency Injection**: Proper initialization of all workflows
6. **📊 Unified Interface**: All workflows implement the same interface

## 🤖 Agent Workflow Deep Dive

### 🔄 Sequential Workflow (Default)

The traditional workflow executes in a fixed sequence with real-time Telegram updates:

```python
# Fixed Workflow Structure
StateGraph(TradingState)
├── gather_data      → analyze_market
├── analyze_market   → make_decision  
├── make_decision    → execute_trades
└── execute_trades   → END
```

### 🔄 Tool Calling Workflow

The dynamic workflow lets the LLM decide which tools to use and when:

```python
# Dynamic Workflow Structure
while not finished and iterations < max_iterations:
    llm_decides_next_action()
    if action == "call_tool":
        execute_tool(selected_tool)
    elif action == "make_decision":
        finalize_trading_decision()
        finished = True
```

**Example Tool Calling Session**:
```
🤖 LLM: "I need to understand the current market conditions. Let me start by checking the portfolio."
🔧 Tool: get_portfolio_info()
📊 Result: Portfolio shows $50K equity, 3 positions...

🤖 LLM: "Now let me get the latest news to understand market sentiment."
🔧 Tool: get_news()
📰 Result: Headlines about Fed policy, tech earnings...

🤖 LLM: "Based on the portfolio and news, let me check SPY and QQQ market data."
🔧 Tool: get_market_data(['SPY', 'QQQ'])
📈 Result: SPY up 1.2%, QQQ up 2.1%...

🤖 LLM: "I have enough information to make a trading decision."
🔧 Tool: make_trading_decision()
💼 Result: BUY AAPL 50 shares - bullish sentiment, strong tech momentum
```

## 🚀 Installation

1. **Clone the repository**:
```bash
git clone <repository-url>
cd Agent_Trader
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Create environment file**:
```bash
cp .env.example .env
```

4. **Configure your API keys** in `.env`:
```bash
# Trading APIs
ALPACA_API_KEY=your_alpaca_api_key_here
ALPACA_SECRET_KEY=your_alpaca_secret_key_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets
TIINGO_API_KEY=your_tiingo_api_key_here

# Workflow Configuration
WORKFLOW_TYPE=sequential      # Options: sequential, tool_calling

# LLM Provider Selection
LLM_PROVIDER=openai          # Options: openai, deepseek

# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o

# DeepSeek Configuration (Alternative to OpenAI)
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_MODEL=deepseek-chat

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here
```

## 🔧 Configuration

### Workflow Selection

Choose your preferred workflow type:

```bash
# Fixed-step workflow (recommended for beginners)
WORKFLOW_TYPE=sequential

# Dynamic workflow (for advanced users)
WORKFLOW_TYPE=tool_calling
```

### Trading Parameters

Edit these settings in your `.env` file:

```bash
# Risk Management
MAX_POSITION_SIZE=0.1          # 10% max position size
STOP_LOSS_PERCENTAGE=0.05      # 5% stop loss
TAKE_PROFIT_PERCENTAGE=0.15    # 15% take profit

# Workflow Configuration
WORKFLOW_TYPE=sequential       # sequential or tool_calling

# Scheduling
REBALANCE_TIME=09:30           # Daily rebalancing time (market open)

# Environment
ENVIRONMENT=development        # development or production
LOG_LEVEL=INFO                # DEBUG, INFO, WARNING, ERROR
```

## 🏃 Usage

### Starting the System

```bash
# Start the trading system
python main.py
```

The system will automatically:
1. Validate your workflow configuration
2. Create the appropriate workflow type (Sequential or Tool Calling)
3. Initialize all components
4. Start the event system and Telegram bot

### Workflow Type Validation

The system validates your configuration on startup:

```
INFO - Validating workflow configuration...
INFO - Workflow type: sequential
INFO - LLM provider: openai
INFO - Configuration validated successfully
INFO - Initialized with sequential workflow
```

### Manual Trading Analysis

Both workflow types support manual analysis via Telegram:

1. **Send `/analyze` command** in Telegram
2. **Watch workflow execution**:
   - **Sequential**: Fixed steps with predictable progress
   - **Tool Calling**: Dynamic execution with LLM-driven decisions

3. **Review results** with full transparency

**Sequential Workflow Example**:
```
🤖 Starting sequential workflow analysis...

ℹ️ **Step 1: Data Collection**
   Gathering portfolio, market data, and news...

ℹ️ **Step 2: Market Analysis**
   Analyzing market conditions...

🤔 **Step 3: Decision Making**
   Making trading decision...

💼 **Step 4: Trade Execution**
   Executing approved trades...

✅ **Sequential Workflow Complete**
```

**Tool Calling Workflow Example**:
```
🤖 Starting tool calling workflow analysis...

🔧 **Tool Selection**: get_portfolio_info
   📊 Retrieved portfolio status...

🔧 **Tool Selection**: get_news
   📰 Retrieved latest 20 news articles...

🔧 **Tool Selection**: get_market_data
   📈 Retrieved SPY, QQQ, IWM data...

🔧 **Tool Selection**: make_trading_decision
   🤔 LLM making final decision...

✅ **Tool Calling Workflow Complete**
```

### 📱 Enhanced Telegram Commands

The Telegram bot includes improved command handling with better formatting and reliability:

#### Core Commands
- **`/start`**: Start the trading system with enhanced status reporting
- **`/stop`**: Gracefully stop the system while keeping commands available
- **`/status`**: Get comprehensive system status with proper markdown formatting
- **`/help`**: Display all available commands with descriptions

#### Enhanced Features
- **Improved markdown**: Proper **bold** text and special character escaping
- **Better error handling**: Graceful fallbacks when message formatting fails
- **Unified messaging**: Consistent message flow through the message manager
- **Status persistence**: Commands remain available even after system stop
- **Real-time updates**: Live progress notifications during workflow execution

#### Command Examples
```
User: /start
Bot: 🚀 **Starting Trading System**
     
     Initializing...

Bot: 🚀 **Trading System Online**
     
     All components initialized successfully. Ready for trading operations!

User: /status
Bot: 📊 **Trading System Status**
     
     🏃 **Running**: ✅ Yes
     💰 **Trading Enabled**: ✅ Yes
     🏪 **Market Open**: ❌ No
     📅 **Scheduler**: ✅ Running
     ...
```

## 🔍 Components Deep Dive

### 1. Trading System (`src/trading_system.py`)
Main orchestrator that coordinates all components:
- Uses **WorkflowFactory** to create appropriate workflow type
- Manages system lifecycle and event processing
- Handles risk management and emergency procedures
- Validates workflow configuration on startup

### 2. Workflow Factory (`src/agents/workflow_factory.py`)
**Factory pattern implementation** for creating workflows:
- **Type-safe workflow creation** with validation
- **Configuration validation** and error handling
- **Dependency injection** for all workflow types
- **Registry pattern** for future workflow extensions

### 3. Workflow Base (`src/agents/workflow_base.py`)
**Abstract base class** defining common workflow interface:
- Unified interface for all workflow types
- Common utility methods (portfolio, market data, news)
- Error handling and notification system
- Telegram integration support

### 4. Sequential Workflow (`src/agents/sequential_workflow.py`)
**Fixed-step workflow implementation**:
- Refactored from original `trading_workflow.py`
- LangGraph state management
- Predictable four-step execution
- Optimized for consistency and reliability

### 5. Tool Calling Workflow (`src/agents/tool_calling_workflow.py`)
**Dynamic workflow implementation**:
- LLM-driven tool selection and execution
- Flexible iteration loops with safety limits
- Real-time tool calling notifications
- Adaptive decision-making process

### 6. Event System (`src/events/event_system.py`)
In-memory event system for real-time events:
- Order events (created, filled, canceled)
- Portfolio updates and system alerts
- Risk management triggers
- Workflow completion notifications

### 7. Scheduler (`src/scheduler/trading_scheduler.py`)
Automated job scheduling:
- Daily rebalancing at market open
- Portfolio monitoring and risk checks
- End-of-day analysis and reporting
- Compatible with all workflow types

### 8. API Integrations
- **Alpaca API**: Trading execution and portfolio management
- **Tiingo API**: News and market data
- **Telegram Bot**: Enhanced remote control and notifications

### 9. Utility Modules (`src/utils/`)
**New modular string processing system**:
- **`string_utils.py`**: General text processing, formatting, and validation utilities
- **`telegram_utils.py`**: Telegram-specific markdown handling, escaping, and character limits
- **`message_formatters.py`**: Specialized formatters for portfolio, order, and alert messages
- **Benefits**: Improved code reusability, centralized formatting logic, better maintainability

## 🔧 Development

### Project Structure

```
Agent_Trader/
├── main.py                          # Main entry point
├── config.py                        # Configuration management
├── requirements.txt                 # Dependencies
├── README.md                       # This file
├── logs/                           # Log files
└── src/
    ├── adapters/                    # External service adapters
    │   ├── brokers/
    │   │   └── alpaca_adapter.py    # Alpaca broker integration
    │   ├── market_data/
    │   │   └── tiingo_market_data_adapter.py # Tiingo market data
    │   ├── news/
    │   │   └── tiingo_news_adapter.py # Tiingo news integration
    │   └── transports/
    │       └── telegram_service.py  # Enhanced Telegram bot
    ├── interfaces/                  # Abstract interfaces
    │   ├── broker_api.py           # Broker interface
    │   ├── market_data_api.py      # Market data interface
    │   ├── message_transport.py    # Message transport interface
    │   ├── news_api.py             # News API interface
    │   └── factory.py              # Service factory
    ├── models/
    │   └── trading_models.py        # Pydantic models
    ├── events/
    │   └── event_system.py         # Event handling
    ├── agents/
    │   ├── workflow_factory.py     # Factory pattern implementation
    │   ├── workflow_base.py        # Abstract base class
    │   ├── sequential_workflow.py  # Fixed-step workflow
    │   └── tool_calling_workflow.py # Dynamic workflow
    ├── messaging/
    │   └── message_manager.py      # Intelligent message management
    ├── scheduler/
    │   └── trading_scheduler.py    # Enhanced job scheduling
    ├── utils/                      # Utility modules (NEW)
    │   ├── string_utils.py         # General string processing
    │   ├── telegram_utils.py       # Telegram-specific utilities
    │   └── message_formatters.py   # Message formatting functions
    └── trading_system.py           # Main orchestrator
```

### Adding Custom Workflows

To add a new workflow type:

1. **Create workflow class** inheriting from `WorkflowBase`:
```python
from src.agents.workflow_base import WorkflowBase

class CustomWorkflow(WorkflowBase):
    def get_workflow_type(self) -> str:
        return "custom"
    
    async def run_workflow(self, initial_context: Dict[str, Any]) -> Dict[str, Any]:
        # Implement your custom workflow logic
        pass
```

2. **Register in factory**:
```python
from src.agents.workflow_factory import WorkflowFactory, WorkflowType

# Add to enum
class WorkflowType(Enum):
    CUSTOM = "custom"

# Register in factory
WorkflowFactory.register_workflow(WorkflowType.CUSTOM, CustomWorkflow)
```

3. **Add configuration option**:
```bash
# In .env file
WORKFLOW_TYPE=custom
```

### Configuration Validation

The system includes comprehensive configuration validation:

```python
from src.agents.workflow_factory import validate_workflow_config

# Validate configuration
is_valid = validate_workflow_config()
if not is_valid:
    print("Configuration errors detected!")
```

### Testing

The system includes comprehensive unit tests for all components:

#### Run All Tests
```bash
python run_tests.py
```

#### Test the Factory Pattern
```bash
# Test workflow factory
pytest tests/test_workflow_factory.py -v

# Test specific workflow types
pytest tests/test_sequential_workflow.py -v
pytest tests/test_tool_calling_workflow.py -v
```

#### Test Options
```bash
# Run with coverage reporting
python run_tests.py --coverage

# Run only unit tests (fast)
python run_tests.py --unit

# Run only integration tests
python run_tests.py --integration

# Skip slow tests
python run_tests.py --fast
```

#### Test Structure
```
tests/
├── conftest.py                    # Pytest configuration and fixtures
├── test_config.py                 # Configuration tests
├── test_trading_models.py         # Data model tests
├── test_event_system.py           # Event system tests
├── test_alpaca_api.py             # Alpaca API tests
├── test_telegram_bot.py           # Enhanced Telegram bot tests
├── test_telegram_message_queue.py # Message queue system tests
├── test_tiingo_api.py             # Tiingo API tests
├── test_workflow_factory.py       # Factory pattern tests
├── test_sequential_workflow.py    # Sequential workflow tests
├── test_tool_calling_workflow.py  # Tool calling workflow tests
└── test_news_api.py               # News API integration tests
```

### Code Quality Features

#### String Processing & Utilities
- **Centralized formatting**: All message formatting handled by specialized utility modules
- **Markdown safety**: Proper escaping of special characters for Telegram
- **Reusable functions**: Common string operations available across the codebase
- **Type safety**: Proper type hints and validation for all utility functions

#### Enhanced Error Handling
- **Graceful degradation**: System continues operating even if individual components fail
- **Comprehensive logging**: Detailed error tracking and debugging information
- **Retry mechanisms**: Automatic retry for transient failures
- **User-friendly messages**: Clear error messages in Telegram interface

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For issues and questions:
1. Check the logs in `logs/` directory
2. Review the Telegram bot messages
3. Verify API keys and permissions
4. Check workflow configuration validation

Common issues:
- **"Unsupported workflow type"**: Check your `WORKFLOW_TYPE` setting
- **"Workflow creation failed"**: Verify your LLM provider configuration
- **"Configuration validation failed"**: Check all required API keys

## 🎯 Recent Updates

### Version 2.0 Highlights
- **String Processing Refactoring**: Moved 200+ lines of formatting code to dedicated utility modules
- **Enhanced Telegram Bot**: Improved command handling, markdown formatting, and error recovery
- **System Reliability**: Better restart functionality and graceful shutdown handling
- **Code Organization**: Modular architecture with improved separation of concerns
- **Maintainability**: Centralized utilities and consistent interfaces across components

### Performance Improvements
- **Reduced code duplication**: Eliminated redundant string processing across components
- **Better error handling**: More robust exception handling and recovery mechanisms
- **Enhanced logging**: Improved debugging and system monitoring capabilities
- **Optimized messaging**: Intelligent message queuing and formatting

## 🙏 Acknowledgments

- **OpenAI** and **DeepSeek** for the LLM capabilities
- **Alpaca** for the trading API
- **Tiingo** for market data and news
- **LangGraph** for workflow orchestration and state management
- **Python-Telegram-Bot** for Telegram integration

---

**Disclaimer**: This software is for educational purposes only. Trading involves substantial risk of loss and is not suitable for all investors. Past performance does not guarantee future results. 