# 🚀 Setup Guide

This guide will walk you through setting up the LLM Trading Agent system step by step.

## 📋 Prerequisites Checklist

- [ ] Python 3.8 or higher installed

- [ ] Git installed
- [ ] Text editor or IDE

## 🔧 Step-by-Step Setup

### 1. System Requirements

**Python Version Check:**
```bash
python --version
# Should show Python 3.8 or higher
```

**Install Git (if not already installed):**
```bash
# Ubuntu/Debian
sudo apt-get install git

# macOS
brew install git

# Windows - Download from https://git-scm.com/
```

### 2. Clone and Setup Project

```bash
# Clone the repository
git clone <repository-url>
cd Agent_Trader

# Create virtual environment (recommended)
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. API Keys Setup

You'll need to obtain API keys from four services:

#### 3.1 Alpaca Trading API

1. **Sign up** at [alpaca.markets](https://alpaca.markets)
2. **Verify your identity** (required for trading)
3. **Navigate to** Paper Trading section
4. **Generate API keys** for paper trading
5. **Copy** both API Key and Secret Key
6. **Note:** Start with paper trading URL: `https://paper-api.alpaca.markets`

#### 3.2 Tiingo News API

1. **Sign up** at [tiingo.com](https://tiingo.com)
2. **Go to** your dashboard
3. **Copy** your API key
4. **Note:** Free tier includes 1000 requests/day

#### 3.3 OpenAI API

1. **Sign up** at [openai.com](https://openai.com)
2. **Add billing information** (required for API access)
3. **Create API key** in the API section
4. **Copy** your API key
5. **Note:** Make sure you have access to GPT-4o or O3

#### 3.4 Telegram Bot

1. **Open Telegram** and search for [@BotFather](https://t.me/BotFather)
2. **Send** `/newbot` command
3. **Follow prompts** to create your bot
4. **Copy** the bot token
5. **Get your chat ID:**
   - Send a message to [@userinfobot](https://t.me/userinfobot)
   - Copy your chat ID number

### 4. Environment Configuration

Create a `.env` file in the project root:

```bash
# Copy the example file
cp .env.example .env

# Edit with your favorite text editor
nano .env  # or vim, code, etc.
```

Fill in your API keys:

```bash
# Trading APIs
ALPACA_API_KEY=your_alpaca_api_key_here
ALPACA_SECRET_KEY=your_alpaca_secret_key_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets
TIINGO_API_KEY=your_tiingo_api_key_here

# OpenAI API
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here

# Database
DATABASE_URL=sqlite:///./trading_agent.db

# Risk Management
MAX_POSITION_SIZE=0.1
STOP_LOSS_PERCENTAGE=0.05
TAKE_PROFIT_PERCENTAGE=0.15

# Scheduling
REBALANCE_TIME=09:30

# System
ENVIRONMENT=development
LOG_LEVEL=INFO
```

### 5. Test Your Setup

#### 5.1 Test API Connections

```bash
# Test the configuration
python -c "from config import settings; print('Config loaded successfully')"

# Test APIs (create a simple test script)
python test_apis.py
```

#### 5.2 Create Test Script

Create `test_apis.py`:

```python
import asyncio
from src.apis.alpaca_api import AlpacaAPI
from src.apis.tiingo_api import TiingoAPI
from src.apis.telegram_bot import TelegramBot

async def test_apis():
    print("Testing API connections...")
    
    # Test Alpaca
    try:
        alpaca = AlpacaAPI()
        portfolio = alpaca.get_portfolio()
        print(f"✅ Alpaca API: Connected - Portfolio equity: ${portfolio.equity}")
    except Exception as e:
        print(f"❌ Alpaca API: {e}")
    
    # Test Tiingo
    try:
        tiingo = TiingoAPI()
        news = tiingo.get_news(limit=1)
        print(f"✅ Tiingo API: Connected - Got {len(news)} news items")
    except Exception as e:
        print(f"❌ Tiingo API: {e}")
    
    # Test Telegram
    try:
        telegram = TelegramBot()
        await telegram.send_message("🧪 Test message from trading bot!")
        print("✅ Telegram Bot: Connected - Check your Telegram for test message")
    except Exception as e:
        print(f"❌ Telegram Bot: {e}")

if __name__ == "__main__":
    asyncio.run(test_apis())
```

Run the test:
```bash
python test_apis.py
```

### 6. First Run

#### 6.1 Start the Trading System

```bash
# Start the system
python main.py
```

You should see:
```
╔════════════════════════════════════════════════════════════════╗
║                                                                ║
║                    🤖 LLM Trading Agent                        ║
║                                                                ║
║    Powered by OpenAI O3 • Alpaca API • Tiingo News           ║
║                                                                ║
║                     Built with LangGraph                       ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝

2024-01-01 10:00:00 - main - INFO - 🚀 Starting LLM Trading Agent
2024-01-01 10:00:00 - main - INFO - Environment: development
2024-01-01 10:00:00 - main - INFO - Alpaca Base URL: https://paper-api.alpaca.markets
...
```

#### 7.3 Test Telegram Commands

1. **Open Telegram** and find your bot
2. **Send** `/help` to see available commands
3. **Send** `/status` to check system status
4. **Send** `/portfolio` to view your portfolio

## 🔍 Troubleshooting

### Common Issues

#### 1. API Key Errors
```
Error: Invalid API key
```
**Solution:**
- Double-check your API keys in `.env`
- Ensure no extra spaces or quotes
- Verify keys are active on respective platforms

#### 2. Telegram Bot Not Responding
```
Error: Unauthorized
```
**Solution:**
- Check your bot token is correct
- Verify your chat ID is correct
- Make sure you've sent at least one message to the bot

#### 3. Permission Errors
```
Error: Insufficient permissions
```
**Solution:**
- Check Alpaca account verification status
- Ensure API keys have trading permissions
- Verify paper trading is enabled

#### 4. Module Import Errors
```
Error: No module named 'src'
```
**Solution:**
- Make sure you're in the project root directory
- Check if virtual environment is activated
- Reinstall dependencies: `pip install -r requirements.txt`

### Debug Mode

Enable debug logging for more information:

```bash
# Set debug level in .env
LOG_LEVEL=DEBUG

# Or run with debug flag
LOG_LEVEL=DEBUG python main.py
```

## 🛡️ Security Checklist

- [ ] API keys are stored in `.env` file (not in code)
- [ ] `.env` file is in `.gitignore` (never commit it)
- [ ] Using paper trading for testing
- [ ] Risk management settings are configured
- [ ] Telegram bot token is kept private

## 📊 Performance Optimization

### For Production Use

1. **Use PostgreSQL** instead of SQLite:
```bash
DATABASE_URL=postgresql://user:password@localhost/trading_agent
```

2. **Set up log rotation**:
```bash
# Create logrotate configuration
sudo nano /etc/logrotate.d/trading-agent
```

3. **Use process manager**:
```bash
# Install PM2
npm install -g pm2

# Start with PM2
pm2 start main.py --name trading-agent --interpreter python
```

## 🎯 Next Steps

1. **Monitor** your system for a few days in paper trading mode
2. **Adjust** risk parameters based on your comfort level
3. **Review** logs and trading decisions
4. **Consider** live trading only after thorough testing

## 📞 Getting Help

If you encounter issues:

1. **Check logs** in the `logs/` directory
2. **Review** this setup guide
3. **Check** the main README.md
4. **Verify** all API keys and permissions

---

**⚠️ Remember**: Always start with paper trading and never risk more than you can afford to lose! 