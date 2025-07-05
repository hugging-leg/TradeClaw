# 🤖 LLM Trading Agent

A sophisticated, event-driven trading system that uses advanced LLMs (OpenAI or DeepSeek) to make intelligent trading decisions for US stocks. The system integrates multiple APIs and uses LangGraph for orchestrating complex trading workflows.

## ⚡ Key Features

- **🧠 AI-Powered Trading**: Uses OpenAI GPT-4o/O3 or DeepSeek models for intelligent trading decisions
- **💰 Cost-Effective Options**: Choose between OpenAI (premium) or DeepSeek (cost-effective) LLM providers
- **📊 Real-Time Data**: Integrates Alpaca API for trading and Tiingo for news/market data
- **🔄 Event-Driven Architecture**: In-memory event system for real-time event handling
- **📱 Telegram Control**: Complete remote control and notifications via Telegram bot
- **⏰ Automated Scheduling**: Daily rebalancing and risk management
- **🛡️ Risk Management**: Built-in stop-loss, take-profit, and portfolio risk controls
- **📈 LangGraph Workflow**: Sophisticated decision-making pipeline
- **🔐 Paper Trading**: Safe testing environment with Alpaca paper trading

## 🏗️ System Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Telegram Bot  │    │ OpenAI/DeepSeek │    │   Alpaca API    │
│   (Control)     │    │   (Decisions)   │    │   (Trading)     │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                    ┌─────────────▼─────────────┐
                    │     Trading System        │
                    │     (Orchestrator)        │
                    └─────────────┬─────────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
┌─────────▼───────┐    ┌─────────▼───────┐    ┌─────────▼───────┐
│  Event System   │    │   LangGraph     │    │   Scheduler     │
│  (In-Memory)    │    │   (Workflow)    │    │   (Daily Jobs)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                    ┌─────────────▼─────────────┐
                    │     Tiingo API            │
                    │     (News & Data)         │
                    └───────────────────────────┘
```

## 📋 Prerequisites

- Python 3.8+
- API keys for:
  - Alpaca Trading API
  - Tiingo News API
  - OpenAI API OR DeepSeek API
  - Telegram Bot

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

# LLM Provider Selection
LLM_PROVIDER=openai  # Options: openai, deepseek

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

### Trading Parameters

Edit these settings in your `.env` file:

```bash
# Risk Management
MAX_POSITION_SIZE=0.1          # 10% max position size
STOP_LOSS_PERCENTAGE=0.05      # 5% stop loss
TAKE_PROFIT_PERCENTAGE=0.15    # 15% take profit

# Scheduling
REBALANCE_TIME=09:30           # Daily rebalancing time (market open)

# Environment
ENVIRONMENT=development        # development or production
LOG_LEVEL=INFO                # DEBUG, INFO, WARNING, ERROR
```

### API Key Setup

#### 1. Alpaca API
- Sign up at [alpaca.markets](https://alpaca.markets)
- Create API keys for paper trading
- Use paper trading URL: `https://paper-api.alpaca.markets`

#### 2. Tiingo API
- Sign up at [tiingo.com](https://tiingo.com)
- Get your free API key from the dashboard

#### 3. LLM Provider (Choose One)

**Option A: OpenAI API**
- Sign up at [openai.com](https://openai.com)
- Create API key with access to GPT-4o or O3
- Higher quality, premium pricing

**Option B: DeepSeek API**
- Sign up at [platform.deepseek.com](https://platform.deepseek.com)
- Create API key for DeepSeek models
- Cost-effective alternative (~90% cheaper than OpenAI)

#### 4. Telegram Bot
- Create a bot via [@BotFather](https://t.me/BotFather)
- Get your bot token
- Find your chat ID by messaging [@userinfobot](https://t.me/userinfobot)

## 🧠 LLM Provider Options

The system supports two LLM providers:

### OpenAI (Premium)
- **Models**: GPT-4o, GPT-4, GPT-3.5-turbo
- **Pros**: Highest quality reasoning, fastest responses
- **Cons**: Higher cost
- **Best For**: Production trading with premium requirements

### DeepSeek (Cost-Effective)
- **Models**: deepseek-chat, deepseek-coder
- **Pros**: ~90% cheaper than OpenAI, good performance
- **Cons**: Slightly less nuanced reasoning
- **Best For**: Development, testing, cost-conscious production

### Switching Providers

Simply update your `.env` file:
```bash
# Switch to DeepSeek
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_deepseek_key

# Switch to OpenAI
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_key
```

For detailed LLM configuration, see [LLM Provider Guide](docs/LLM_PROVIDER_GUIDE.md).

## 🏃 Usage

### Starting the System

```bash
# Start the trading system
python main.py
```

### Telegram Commands

Once the system is running, you can control it via Telegram:

```
/start          - Start trading operations
/stop           - Stop trading operations
/status         - Get system status
/portfolio      - View current portfolio
/orders         - View active orders
/emergency_stop - Emergency stop (cancel all orders)
/help           - Show help message
```

### System Lifecycle

1. **System Startup**: Initializes all components and connects to APIs
2. **Daily Rebalancing**: Runs at market open (9:30 AM ET by default)
3. **Continuous Monitoring**: Checks portfolio and risk every 15 minutes
4. **Event Processing**: Handles order fills, cancellations, and alerts
5. **End-of-Day Analysis**: Generates daily performance report

## 🔍 Components Deep Dive

### 1. Trading System (`src/trading_system.py`)
Main orchestrator that coordinates all components:
- Manages system lifecycle
- Handles event processing
- Coordinates risk management
- Manages emergency procedures

### 2. Event System (`src/events/event_system.py`)
In-memory event system for real-time events:
- Order events (created, filled, canceled)
- Portfolio updates
- System alerts
- Risk management triggers

### 3. LangGraph Workflow (`src/agents/trading_workflow.py`)
AI-powered decision-making pipeline:
- **Data Gathering**: Collects portfolio, market data, and news
- **Market Analysis**: AI analyzes current conditions
- **Decision Making**: AI makes trading decisions
- **Trade Execution**: Executes approved trades

### 4. Scheduler (`src/scheduler/trading_scheduler.py`)
Automated job scheduling:
- Daily rebalancing at market open
- Hourly portfolio monitoring
- Risk checks every 15 minutes
- End-of-day analysis

### 5. API Integrations
- **Alpaca API**: Trading execution and portfolio management
- **Tiingo API**: News and market data
- **Telegram Bot**: Remote control and notifications

## 🛡️ Risk Management

### Built-in Safety Features

1. **Position Limits**: Maximum 10% of portfolio per position
2. **Stop Loss**: Automatic 5% stop loss on all positions
3. **Take Profit**: Automatic 15% take profit on all positions
4. **Portfolio Risk**: Daily loss limit monitoring
5. **Emergency Stop**: Instant shutdown via Telegram
6. **Paper Trading**: Safe testing environment

### Risk Parameters

```python
# Configurable in .env file
MAX_POSITION_SIZE = 0.1       # 10% max position
STOP_LOSS_PERCENTAGE = 0.05   # 5% stop loss
TAKE_PROFIT_PERCENTAGE = 0.15 # 15% take profit
```

## 📊 Monitoring and Alerts

### Telegram Notifications

The system sends automatic notifications for:
- ✅ Order executions
- 📊 Portfolio updates
- ⚠️ Risk alerts
- 🚨 System errors
- 📈 Daily performance reports

### Logging

Comprehensive logging system:
- **File Logs**: `logs/trading_agent_YYYYMMDD.log`
- **Console Output**: Real-time system status
- **Log Levels**: DEBUG, INFO, WARNING, ERROR

## 🔧 Development

### Project Structure

```
Agent_Trader/
├── main.py                    # Main entry point
├── config.py                  # Configuration management
├── requirements.txt           # Dependencies
├── README.md                 # This file
├── logs/                     # Log files
└── src/
    ├── models/
    │   └── trading_models.py  # Pydantic models
    ├── apis/
    │   ├── alpaca_api.py     # Alpaca integration
    │   ├── tiingo_api.py     # Tiingo integration
    │   └── telegram_bot.py   # Telegram bot
    ├── events/
    │   └── event_system.py   # Event handling
    ├── agents/
    │   └── trading_workflow.py # LangGraph workflow
    ├── scheduler/
    │   └── trading_scheduler.py # Job scheduling
    └── trading_system.py      # Main orchestrator
```

### Adding Custom Strategies

To add custom trading strategies:

1. Create a new workflow in `src/agents/`
2. Implement the LangGraph workflow pattern
3. Register with the trading system
4. Add configuration parameters

### Testing

The system includes comprehensive unit tests for all components:

#### Run All Tests
```bash
python run_tests.py
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

# Run specific test file
python run_tests.py tests/test_config.py
```

#### Direct pytest Commands
```bash
# Basic test run
pytest tests/

# With coverage
pytest tests/ --cov=src --cov-report=html

# Specific test markers
pytest tests/ -m "not integration"  # Skip integration tests
pytest tests/ -m "unit"             # Only unit tests
```

#### Test Structure
```
tests/
├── conftest.py              # Pytest configuration and fixtures
├── test_config.py           # Configuration tests
├── test_trading_models.py   # Data model tests
├── test_event_system.py     # Event system tests
├── test_alpaca_api.py       # Alpaca API tests
├── test_telegram_bot.py     # Telegram bot tests
└── test_tiingo_api.py       # Tiingo API tests
```

#### Test Categories
- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test component interactions (requires real API credentials)
- **Slow Tests**: Tests that take longer to run (marked with `@pytest.mark.slow`)

#### Coverage Goals
- Target: 80%+ code coverage
- HTML coverage reports generated in `htmlcov/`

### Manual Testing

```bash
# Run with paper trading (default)
ALPACA_BASE_URL=https://paper-api.alpaca.markets python main.py

# Enable debug logging
LOG_LEVEL=DEBUG python main.py
```

## 🚨 Important Warnings

⚠️ **This system trades real money when configured for live trading**

🛡️ **Always test with paper trading first**

📊 **Monitor your positions actively**

💰 **Never risk more than you can afford to lose**

🔒 **Keep your API keys secure**

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For issues and questions:
1. Check the logs in `logs/` directory
2. Review the Telegram bot messages
3. Verify API keys and permissions

## 🙏 Acknowledgments

- **OpenAI** for the LLM capabilities
- **Alpaca** for the trading API
- **Tiingo** for market data and news
- **LangGraph** for workflow orchestration

---

**Disclaimer**: This software is for educational purposes only. Trading involves substantial risk of loss and is not suitable for all investors. Past performance does not guarantee future results. 