# 🤖 AI Trading Agent

Intelligent trading agent powered by LLM for automated US stock trading with multiple API provider support.

## 🏗️ System Architecture

### Core Components

- **TradingSystem**: Main system orchestrator managing all component lifecycles
- **API Adapters**: Unified interfaces for brokers, market data, news, and other services
- **AI Workflows**: Supports Sequential (fixed steps) and ToolCalling (dynamic decisions) modes
- **Event System**: Real-time processing of orders, portfolio, and trading events
- **Task Scheduler**: Automated execution of daily trading tasks
- **Telegram Bot**: Remote control and real-time notifications

### System Architecture

![System Architecture](assets/images/diagrams/system-architecture.svg)

*Complete system architecture showing all components and their relationships*

### Workflow Process

![Workflow Process](assets/images/diagrams/workflow-flow.svg)

*Simplified workflow showing the main process flow*

**📊 Documentation Links:**
- **[System Architecture Details](docs/system-architecture.md)** - Detailed component descriptions
- **[Workflow Documentation](docs/workflow-diagram.md)** - Process flow explanations



## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Environment Setup
```bash
cp env.template .env
```

Configure `.env` file:
```bash
# API Keys
ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret
TIINGO_API_KEY=your_tiingo_key

# AI Configuration
LLM_PROVIDER=openai  # or deepseek
OPENAI_API_KEY=your_openai_key
WORKFLOW_TYPE=sequential  # or tool_calling

# Telegram Configuration
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Trading Parameters
PAPER_TRADING=true
MAX_POSITION_SIZE=0.1
STOP_LOSS_PERCENTAGE=0.05
TAKE_PROFIT_PERCENTAGE=0.15
```

### 3. Start System
```bash
python main.py
```

## 🤖 AI Workflows

### Sequential Workflow
- **Execution Flow**: Data Collection → Market Analysis → Decision Making → Trade Execution
- **Characteristics**: Predictable, cost-effective, suitable for systematic trading strategies
- **Use Case**: Daily automated trading

### Tool Calling Workflow
- **Execution Method**: LLM dynamically selects tools and execution order
- **Characteristics**: More intelligent, adaptive, higher cost
- **Use Case**: Complex market analysis and decision making

#### Available Tools
- `get_portfolio_info`: Get portfolio information
- `get_market_data`: Fetch market data
- `get_news`: Retrieve news feed
- `get_market_status`: Check market status
- `get_active_orders`: View active orders
- `make_trading_decision`: Make trading decisions

## 📱 Telegram Control

### Basic Commands
- `/start` - Start trading system
- `/stop` - Stop trading system
- `/status` - Check system status
- `/portfolio` - Portfolio overview
- `/analyze` - Manually trigger AI analysis
- `/emergency` - Emergency stop all trading

## ⚙️ Configuration

### Trading Parameters
```bash
PAPER_TRADING=true              # Paper trading mode
MAX_POSITION_SIZE=0.1          # Max position size (10%)
MAX_POSITIONS=10               # Max number of positions
STOP_LOSS_PERCENTAGE=0.05      # Stop loss percentage (5%)
TAKE_PROFIT_PERCENTAGE=0.15    # Take profit percentage (15%)
REBALANCE_TIME=09:30           # Daily rebalancing time
```

### AI Model Configuration
```bash
LLM_PROVIDER=openai            # AI provider: openai or deepseek
OPENAI_MODEL=gpt-4o           # OpenAI model
DEEPSEEK_MODEL=deepseek-chat  # DeepSeek model
WORKFLOW_TYPE=sequential      # Workflow type: sequential or tool_calling
```

### API Providers
```bash
BROKER_PROVIDER=alpaca          # Broker: alpaca
MARKET_DATA_PROVIDER=tiingo     # Market data: tiingo
NEWS_PROVIDER=tiingo            # News: tiingo
MESSAGE_PROVIDER=telegram       # Messaging: telegram
```

## 🏗️ Project Structure

```
src/
├── adapters/                   # API Adapters
|   │   ├── brokers/
│   │   │   └── alpaca_adapter.py   # Alpaca broker interface
|   │   ├── market_data/
│   │   │   └── tiingo_market_data_adapter.py  # Tiingo market data
|   │   ├── news/
│   │   │   └── tiingo_news_adapter.py         # Tiingo news
|   │   └── transports/
│   │   │   └── telegram_service.py            # Telegram service
├── interfaces/                 # Abstract Interfaces
│   │   ├── broker_api.py          # Broker interface definition
│   │   ├── market_data_api.py     # Market data interface
│   │   ├── news_api.py            # News interface
│   │   ├── message_transport.py   # Message transport interface
│   │   └── factory.py             # Service creation
├── agents/                     # AI Workflows
│   │   ├── workflow_factory.py    # Workflow creation
│   │   ├── workflow_base.py       # Base class
│   │   ├── sequential_workflow.py # Sequential workflow
│   │   └── tool_calling_workflow.py # Tool calling workflow
├── events/
│   │   └── event_system.py        # Event system
├── messaging/
│   │   └── message_manager.py     # Message management
├── scheduler/
│   │   └── trading_scheduler.py   # Task scheduling
├── models/
│   │   └── trading_models.py      # Data models
├── utils/                      # Utility functions
│   │   ├── string_utils.py        
│   │   ├── telegram_utils.py      
│   │   └── message_formatters.py  
└── trading_system.py          # Main system
```

## 🧪 Testing

```bash
# Run all tests
python run_tests.py

# Run specific tests
pytest tests/test_workflow_factory.py -v
pytest tests/test_alpaca_api.py -v
```

## 📊 System Features

### Automated Trading
- **AI Decision Making**: Intelligent analysis based on market data and news
- **Risk Control**: Automatic stop-loss and take-profit mechanisms
- **Position Management**: Smart position allocation and rebalancing
- **Real-time Monitoring**: 24/7 market monitoring and response

### Remote Control
- **Telegram Integration**: Control trading system anytime, anywhere
- **Real-time Notifications**: Instant notifications for trades, system status
- **Command Control**: Complete control with start, stop, query commands

### Security
- **Paper Trading**: Enabled by default, zero-risk testing
- **Multi-layer Security**: API keys, permissions, and access controls
- **Emergency Stop**: One-click position closure for capital protection

## 🔒 Risk Management

- **Paper Trading**: Enabled by default, safe testing environment
- **Position Limits**: Maximum 10% per position, total position control
- **Stop Loss**: Automatic 5% stop-loss protection
- **Take Profit**: Automatic 15% take-profit to lock in gains
- **Emergency Controls**: One-click liquidation and emergency stop

## 📄 License

MIT License

## ⚠️ Disclaimer

This software is for educational purposes only. Trading involves significant risk and may result in financial loss. Past performance does not guarantee future results. Use with caution. 