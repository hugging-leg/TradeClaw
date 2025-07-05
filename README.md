# 🤖 LLM Trading Agent

A sophisticated, event-driven trading system that uses advanced LLMs (OpenAI or DeepSeek) to make intelligent trading decisions for US stocks. The system integrates multiple APIs and uses LangGraph for orchestrating complex trading workflows with real-time Telegram notifications.

## ⚡ Key Features

- **🧠 AI-Powered Trading**: Uses OpenAI GPT-4o/O3 or DeepSeek models for intelligent trading decisions
- **💰 Cost-Effective Options**: Choose between OpenAI (premium) or DeepSeek (cost-effective) LLM providers
- **📊 Real-Time Data**: Integrates Alpaca API for trading and Tiingo for news/market data
- **🔄 Event-Driven Architecture**: In-memory event system for real-time event handling
- **📱 Telegram Control & Updates**: Complete remote control with real-time workflow progress notifications
- **🔗 LangGraph Workflow**: Four-stage AI decision pipeline with live progress tracking
- **📢 Message Queue System**: Intelligent Telegram notifications with anti-flood protection
- **⏰ Automated Scheduling**: Daily rebalancing and risk management
- **🛡️ Risk Management**: Built-in stop-loss, take-profit, and portfolio risk controls
- **🔐 Paper Trading**: Safe testing environment with Alpaca paper trading

## 🏗️ System Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Telegram Bot  │    │ OpenAI/DeepSeek │    │   Alpaca API    │
│ (Control+Updates)│    │   (Decisions)   │    │   (Trading)     │
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
└─────────────────┘    └─────────┬───────┘    └─────────────────┘
          │              ┌───────▼───────┐              │
          │              │Message Queue  │              │
          │              │  (Telegram)   │              │
          │              └───────────────┘              │
          └──────────────────────┼──────────────────────┘
                                 │
                    ┌─────────────▼─────────────┐
                    │     Tiingo API            │
                    │     (News & Data)         │
                    └───────────────────────────┘
```

## 🤖 Agent Workflow Deep Dive

The heart of the system is the **LangGraph-powered AI trading workflow** that executes in four distinct stages. Each stage sends real-time updates to Telegram, providing complete transparency into the AI's decision-making process.

### 🔄 Workflow Architecture

The trading workflow uses **LangGraph** to create a structured, observable AI decision pipeline:

```python
# Workflow Structure
StateGraph(TradingState)
├── gather_data      → analyze_market
├── analyze_market   → make_decision  
├── make_decision    → execute_trades
└── execute_trades   → END
```

### 📊 Stage 1: Data Gathering

**Purpose**: Collect all necessary market information for analysis

**Process**:
1. **Portfolio Snapshot**: Retrieves current equity, cash, positions, and P&L
2. **Market Data**: Fetches real-time data for major indices (SPY, QQQ, IWM, DIA)
3. **News Collection**: Gathers latest 20 market news articles from Tiingo
4. **Market Status**: Checks if markets are currently open

**Telegram Updates**:
```
ℹ️ **Starting Data Collection**
   Gathering portfolio, market data, and news...

ℹ️ **Portfolio Status**
   • Equity: $50,000.00
   • Cash: $25,000.00
   • Day P&L: +$123.45
   • Positions: 3

📰 **Latest Market News**
   1. Federal Reserve signals dovish stance amid inflation concerns...
      Source: Reuters
   
   2. Tech stocks rally on AI breakthrough announcement...
      Source: Bloomberg
   
   3. Oil prices surge following geopolitical tensions...
      Source: MarketWatch
```

**Data Structure**:
```python
state = TradingState(
    portfolio=Portfolio(...),
    market_data={
        "SPY": {"close": 420.50, "volume": 85000000},
        "QQQ": {"close": 350.25, "volume": 45000000}
    },
    news=[
        {
            "title": "Market rallies on positive earnings",
            "description": "Strong Q4 results drive optimism",
            "source": "Reuters",
            "published_at": "2024-01-15T14:30:00Z",
            "symbols": ["AAPL", "MSFT"]
        }
    ]
)
```

### 🔍 Stage 2: Market Analysis

**Purpose**: AI analyzes collected data to understand market conditions

**LLM Prompt Structure**:
```
You are a professional trading analyst. Analyze current market conditions:

Current Portfolio: [portfolio details]
Market Data: [index performance]
Recent News: [news headlines]
Market Status: OPEN/CLOSED

Provide analysis on:
1. Overall market sentiment
2. Key trends and patterns  
3. Risk assessment
4. Portfolio performance evaluation
5. Potential opportunities or threats
```

**AI Analysis Focus**:
- **Sentiment Analysis**: Bullish/bearish market sentiment from news
- **Technical Patterns**: Index movements and volume analysis
- **Risk Assessment**: Market volatility and economic indicators
- **News Impact**: How current events affect trading opportunities
- **Portfolio Performance**: Current positions vs market performance

**Telegram Updates**:
```
ℹ️ **Starting Market Analysis**
   Analyzing market conditions and portfolio performance...

🔍 **Market Analysis Summary**
   • Overall market sentiment appears bullish
   • Technology sector showing strong momentum
   • Risk levels remain moderate due to Fed uncertainty
   • Energy sector experiencing volatility
   • Portfolio outperforming market by 2.3%
   
   Full analysis: 1,247 characters
```

### 🤔 Stage 3: Decision Making

**Purpose**: AI makes specific trading decisions based on analysis

**Decision Framework**:
```
Based on market analysis, make trading decisions considering:

Portfolio Summary: [available cash, buying power, positions]
Market Analysis: [AI's previous analysis]
Risk Management Rules:
- Max position size: 10% of portfolio
- Stop loss: 5%
- Take profit: 15%

Output Format:
DECISION: [BUY/SELL/HOLD]
SYMBOL: [stock symbol]
QUANTITY: [number of shares]
REASONING: [detailed reasoning]
CONFIDENCE: [0.0-1.0]
```

**Decision Types**:
1. **BUY**: Enter new position or add to existing
2. **SELL**: Close position or reduce exposure  
3. **HOLD**: No action needed

**Risk Considerations**:
- Portfolio diversification limits
- Position size constraints
- Market timing factors
- News impact assessment
- Confidence threshold requirements

**Telegram Updates**:
```
ℹ️ **Making Trading Decision**
   Evaluating trading opportunities based on analysis...

🤔 **Trading Decision**

   **Action:** BUY
   **Symbol:** AAPL
   **Confidence:** 78.5%
   **Quantity:** 50
   **Reasoning:** Strong fundamentals, positive earnings surprise, 
   and bullish technical indicators suggest upward momentum. 
   Current market conditions favor technology stocks...
```

### 💼 Stage 4: Trade Execution

**Purpose**: Execute approved trading decisions

**Execution Logic**:
1. **Market Status Check**: Verify markets are open
2. **Order Validation**: Confirm symbol, quantity, and buying power
3. **Order Submission**: Submit market order to Alpaca API
4. **Order Tracking**: Monitor order status and fill information
5. **Portfolio Update**: Refresh portfolio state after execution

**Order Types Supported**:
- **Market Orders**: Immediate execution at current market price
- **Day Orders**: Automatically cancel at market close
- **Risk Management**: Automatic stop-loss and take-profit orders

**Telegram Updates**:
```
💼 **Executing Trade**
   Submitting order to market...

✅ **Trade Executed**
   
   ✅ AAPL BUY 50 shares
   📋 Order ID: 12345-67890-abcdef
   💰 Filled at: $185.47 per share
   📊 Total: $9,273.50

✅ **Workflow Complete**
   
   🎯 Trading analysis and execution cycle finished successfully!
```

### 🚫 Error Handling

**Graceful Degradation**:
- **API Failures**: Continue with cached data where possible
- **Market Closed**: Queue decisions for next market open
- **Insufficient Funds**: Adjust position sizes automatically
- **News Unavailable**: Use portfolio and market data only

**Error Notifications**:
```
❌ **Data Collection Error**
   Unable to fetch latest news: API rate limit exceeded
   
⚠️ **Trade Execution**
   Market is closed. Cannot execute trades at this time.
   
❌ **Trade Failed**
   Insufficient buying power for AAPL purchase
```

### 📱 Telegram Message Queue System

**Anti-Flood Protection**:
- **Rate Limiting**: 1-second delay between messages
- **Message Batching**: Combines related updates when possible
- **Queue Management**: Processes messages in order during high activity

**Message Types**:
- `📢` **Info**: General status updates
- `✅` **Success**: Completed actions  
- `⚠️` **Warning**: Non-critical issues
- `❌` **Error**: Critical problems
- `📰` **News**: Market news summaries
- `🔍` **Analysis**: AI analysis results
- `🤔` **Decision**: Trading decisions
- `💼` **Trade**: Execution updates

**Smart Formatting**:
- **Truncation**: Long messages automatically summarized
- **Key Extraction**: Important points highlighted with bullets
- **Emoji Categorization**: Visual message type identification
- **Markdown Support**: Rich text formatting for readability

### 🔄 Workflow Triggers

**Manual Triggers**:
- `/analyze` command in Telegram
- Direct API calls to `run_manual_analysis()`

**Automated Triggers**:
- **Daily Rebalancing**: 9:30 AM ET (market open)
- **Risk Events**: Portfolio loss thresholds
- **News Alerts**: Significant market events (future enhancement)

**Trigger Context**:
```python
# Each workflow run includes context
initial_context = {
    "trigger": "manual_analysis",     # or "daily_rebalance"
    "timestamp": "2024-01-15T14:30:00Z",
    "user_id": "telegram_user_123",   # for manual triggers
    "risk_event": "stop_loss_hit"     # for automated triggers
}
```

### 📈 Workflow State Management

**State Persistence**:
```python
class TradingState(BaseModel):
    messages: List[Dict[str, str]]           # Conversation history
    portfolio: Optional[Portfolio]            # Current portfolio
    market_data: Dict[str, Any]              # Market snapshots  
    news: List[Dict[str, Any]]               # News articles
    decision: Optional[TradingDecision]       # Final decision
    context: Dict[str, Any]                  # Execution context
```

**State Evolution**:
1. **Initial**: Empty state with trigger context
2. **Data Loaded**: Portfolio, market data, and news populated
3. **Analyzed**: AI analysis added to context
4. **Decided**: Trading decision finalized
5. **Executed**: Order information and results stored

This comprehensive workflow ensures that every trading decision is:
- **🔍 Data-Driven**: Based on real market conditions
- **🤖 AI-Powered**: Leveraging advanced language models  
- **📱 Transparent**: Full visibility through Telegram updates
- **🛡️ Risk-Managed**: Bounded by safety parameters
- **📊 Auditable**: Complete decision trail preserved

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

### Manual Trading Analysis

You can manually trigger the AI trading workflow at any time using the Telegram bot:

1. **Send `/analyze` command** in Telegram
2. **Watch real-time updates** as the AI:
   - Collects current portfolio and market data
   - Gathers latest financial news
   - Analyzes market conditions using LLM
   - Makes informed trading decisions
   - Executes trades if markets are open

3. **Review complete workflow** with full transparency into AI reasoning

**Benefits of Manual Analysis**:
- Test the AI's current market assessment
- Trigger trades outside of scheduled times  
- Monitor AI decision-making process in real-time
- Educational insight into trading strategy

### Telegram Commands

Once the system is running, you can control it via Telegram:

```
/start          - Start trading operations
/stop           - Stop trading operations
/status         - Get system status
/portfolio      - View current portfolio
/orders         - View active orders
/analyze        - Manually trigger AI trading workflow (with real-time updates)
/emergency_stop - Emergency stop (cancel all orders)
/help           - Show help message
```

### 📱 Real-Time Workflow Updates

The `/analyze` command triggers the full AI trading workflow and sends real-time progress updates:

**Example Analysis Session**:
```
🤖 Starting LLM trading analysis...

ℹ️ **Starting Data Collection**
   Gathering portfolio, market data, and news...

ℹ️ **Portfolio Status**
   • Equity: $50,000.00
   • Cash: $25,000.00
   • Day P&L: +$123.45
   • Positions: 3

📰 **Latest Market News**
   1. Federal Reserve signals dovish stance...
   2. Tech stocks rally on AI breakthrough...
   3. Oil prices surge following tensions...

🔍 **Market Analysis Summary**
   • Overall market sentiment appears bullish
   • Technology sector showing strong momentum
   • Risk levels remain moderate
   
🤔 **Trading Decision**
   **Action:** BUY
   **Symbol:** AAPL
   **Confidence:** 78.5%
   **Reasoning:** Strong fundamentals and positive...

✅ **Trade Executed**
   ✅ AAPL BUY 50 shares
   📋 Order ID: 12345-67890
   
✅ **Workflow Complete**
   🎯 Analysis and execution cycle finished!
```

This provides complete transparency into the AI's decision-making process, from data collection to trade execution.

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
AI-powered decision-making pipeline with real-time Telegram updates:
- **Data Gathering**: Collects portfolio, market data, and news (with progress updates)
- **Market Analysis**: AI analyzes current conditions (with analysis summaries)
- **Decision Making**: AI makes trading decisions (with decision details)
- **Trade Execution**: Executes approved trades (with execution confirmations)
- **Message Queue**: Intelligent Telegram notification system with anti-flood protection

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

The system provides comprehensive real-time notifications:

**Real-Time Workflow Updates**:
- 📢 Data collection progress
- 📰 News summaries with key headlines
- 🔍 AI market analysis results
- 🤔 Trading decisions with reasoning
- 💼 Trade execution confirmations

**System Notifications**:
- ✅ Order executions and fills
- 📊 Portfolio updates and P&L changes
- ⚠️ Risk alerts and stop-loss triggers
- 🚨 System errors and API failures
- 📈 Daily performance reports

**Smart Message Features**:
- 🚦 Rate limiting to prevent spam
- 📝 Automatic message summarization
- 🎯 Emoji categorization for quick scanning
- 📱 Rich markdown formatting

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

- **OpenAI** and **DeepSeek** for the LLM capabilities
- **Alpaca** for the trading API
- **Tiingo** for market data and news
- **LangGraph** for workflow orchestration and state management
- **Python-Telegram-Bot** for Telegram integration

---

**Disclaimer**: This software is for educational purposes only. Trading involves substantial risk of loss and is not suitable for all investors. Past performance does not guarantee future results. 