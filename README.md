# TradeClaw — LLM Agent Trading System

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](license.txt)

AI-powered autonomous trading system for US equities and ETFs.

> 🇨🇳 [中文文档](README_CN.md)

## Highlights

- **LLM-Driven Decisions** — LangGraph ReAct Agent with zero hard-coded rules
- **Event-Driven Architecture** — Async event queue, fully decoupled components
- **Multiple Workflows** — Sequential, tool-calling, Black-Litterman, cognitive arbitrage, and more
- **Flexible LLM Config** — Multi-provider / multi-model, per-agent override, YAML-persisted
- **Real-Time Monitoring** — WebSocket quotes + news polling (AkShare / Alpaca / Tiingo / Finnhub) with LLM importance scoring
- **Configurable Risk Rules** — Stop-loss / take-profit rule chains (YAML); hard rules and LLM-triggered analysis coexist
- **Browser Automation** — Playwright-driven dynamic web scraping and interaction
- **Code Execution Sandbox** — RestrictedPython sandbox (local) or OpenSandbox (Docker isolation)
- **Telegram Control** — Remote monitoring and command execution
- **Modern Web UI** — React + TypeScript + TailwindCSS responsive dashboard

## Quick Start (Docker — Recommended)

The fastest way to get started is the **one-line install script**:

```bash
curl -fsSL https://raw.githubusercontent.com/BryantSuen/Agent-Trader/main/install.sh | bash
```

This will:

1. Create a `tradeclaw/` directory
2. Download `docker-compose.yml`, `env.template`, and SearXNG config
3. Create the `user_data/` directory tree
4. Copy `env.template` → `.env` for you to edit
5. Start all services via `docker compose up -d`

After the script finishes, edit `tradeclaw/.env` with your API keys, then visit **http://localhost:8000**.

### Manual Docker Setup

```bash
git clone https://github.com/BryantSuen/Agent-Trader.git tradeclaw
cd tradeclaw
cp env.template .env
# Edit .env with your API keys
docker compose up -d
```

### Local Development

```bash
git clone https://github.com/BryantSuen/Agent-Trader.git tradeclaw
cd tradeclaw
pip install -r requirements.txt
# Optional extras
pip install playwright && playwright install chromium
pip install RestrictedPython

cp env.template .env
# Edit .env

# Start infrastructure (Postgres + SearXNG)
docker compose -f docker-compose.dev.yml up -d

# Start the trading agent
python main.py
```

## Configuration

### `.env` — Essential Settings

```bash
cp env.template .env
```

Edit `.env`:

```bash
# Broker
ALPACA_API_KEY=your_key
ALPACA_SECRET_KEY=your_secret

# Market Data
TIINGO_API_KEY=your_key

# LLM (fallback; prefer Web UI → LLM Providers for management)
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=your_key
LLM_MODEL=deepseek-chat

# Workflow
WORKFLOW_TYPE=llm_portfolio

# Telegram (optional)
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

### Provider Matrix

| Type | Env Variable | Options |
|------|-------------|---------|
| Broker | `BROKER_PROVIDER` | `alpaca`, `interactive_brokers` |
| Market Data | `MARKET_DATA_PROVIDER` | `tiingo` |
| News | `NEWS_PROVIDERS` | `akshare`, `alpaca`, `tiingo`, `finnhub`, `unusual_whales` |
| Real-Time Data | `REALTIME_DATA_PROVIDER` | `finnhub` (or leave empty) |
| Messaging | `MESSAGE_PROVIDER` | `telegram` |

### LLM Configuration

LLM configuration is managed via `user_data/llm_config.yaml` (or through the Web UI → Settings → LLM Providers):

```yaml
providers:
  - name: deepseek
    base_url: https://api.deepseek.com/v1
    api_key: sk-xxx
    models:
      - name: deepseek-chat
        model_id: deepseek-chat
        description: General purpose model
      - name: deepseek-reasoner
        model_id: deepseek-reasoner
        description: Reasoning model

  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-xxx
    models:
      - name: gpt4o-mini
        model_id: gpt-4o-mini
        description: Fast and cheap

roles:
  agent: deepseek-chat         # Main agent model
  news_filter: gpt4o-mini      # News filtering (cheap model)
  memory_summary: gpt4o-mini   # Memory summarization
```

Each agent/workflow can override the default model by setting `llm_model` in its own config file (`user_data/agents/<workflow>.yaml`).

### Risk Rules

Risk rules are configured in `user_data/risk_rules.yaml` and support multiple rule sets with both hard rules and LLM-triggered analysis:

```yaml
active_rule_set: default
rule_sets:
  - name: default
    description: Default risk rule set
    rules:
      - id: default_stop_loss
        name: Default Stop-Loss
        type: stop_loss
        threshold: 5.0          # 5% stop-loss
        action: close_position
      - id: default_take_profit
        name: Default Take-Profit
        type: take_profit
        threshold: 15.0         # 15% take-profit
        action: close_position
      - id: concentration_llm
        name: Position Concentration LLM
        type: position_concentration
        threshold: 25.0         # >25% triggers LLM analysis
        action: trigger_llm_analysis
```

Rule actions: `close_position`, `trigger_llm_analysis`, `disable_trading`

---

## Workflows

### 1. LLM Portfolio Agent (`llm_portfolio`) — Recommended

Fully autonomous AI portfolio manager using LangGraph ReAct architecture: **Think → Act → Observe → Repeat**.

**Decision Flow:**

```
Trigger → Get portfolio state → Get market data → Get news
  → LLM analysis → Decide rebalancing → Execute trades → Schedule next analysis
```

**Available Tools:**

| Tool | Category | Description |
|------|----------|-------------|
| `get_portfolio_status` | data | Portfolio state (equity, cash, positions) |
| `get_market_data` | data | Market overview (SPY, QQQ, etc.) |
| `get_latest_news` | data | News (filterable by symbol/sector) |
| `get_latest_price` | data | Real-time price quote |
| `get_historical_prices` | data | Historical OHLCV bars |
| `check_market_status` | system | Check if market is open |
| `adjust_position` | trading | Adjust position to target weight |
| `schedule_next_analysis` | system | Schedule next analysis time |
| `web_search` | web | SearXNG meta-search |
| `web_read` | web | Extract article text (Trafilatura) |
| `browser_goto` | browser | Navigate to URL (Playwright) |
| `browser_screenshot` | browser | Take page screenshot |
| `browser_action` | browser | Page interaction (click, fill, JS) |
| `execute_python` | sandbox | Execute Python in sandbox |

### 2. Black-Litterman Workflow (`black_litterman`)

Quantitative + AI — Scientific portfolio allocation based on the Black-Litterman model:

```
Market equilibrium returns (Prior) + LLM-generated views (Views)
  → Bayesian update → Posterior expected returns → Mean-variance optimization → Optimal weights
```

**Default Universe:** `SPY, QQQ, IWM, AAPL, MSFT, GOOGL, NVDA, AMD, META, GLD, TLT, XLF, XLE`

**Dependencies:** `pip install pyportfolioopt cvxpy`

### 3. Cognitive Arbitrage Workflow (`cognitive_arbitrage`)

Second-order momentum strategy — Exploits news propagation time lag:

```
Direct beneficiaries → Already priced in by the market
Indirect beneficiaries → Supply chain / competition / sector linkage, slower reaction → Arbitrage opportunity
```

Core idea: **Buy the highest-scoring indirect beneficiaries**.

### Workflow Comparison

| Feature | LLM Portfolio | Black-Litterman | Cognitive Arbitrage |
|---------|---------------|-----------------|---------------------|
| Decision Method | Fully autonomous LLM | Quant model + LLM views | LLM news propagation analysis |
| Mathematical Basis | None | Mean-variance optimization | Score accumulation |
| Best For | General use | Quant enthusiasts | Event-driven traders |
| Explainability | Medium | High | High (traceable chains) |
| Asset Scope | Any | Fixed universe | Dynamic (LLM-identified) |
| Core Strength | Flexible & autonomous | Scientific allocation | Time-lag arbitrage |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        TradingSystem                          │
├──────────────────────────────────────────────────────────────┤
│  SchedulerMixin   MessageManager   RealtimeMonitor           │
│  RiskManager      NewsPolling      QueryHandler              │
│       │                │                 │                   │
│       ▼                ▼                 ▼                   │
│  ┌──────────┐   ┌───────────┐   ┌──────────────────┐        │
│  │ Workflow  │   │ Telegram  │   │  FinnhubRealtime │        │
│  │ Factory   │   │ Service   │   │  + NewsPolling   │        │
│  └────┬─────┘   └───────────┘   └──────────────────┘        │
│       │                                                      │
│       ▼                                                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              LLM Agent (LangGraph ReAct)              │   │
│  │  ┌──────────────────────────────────────────────┐    │   │
│  │  │ Tools: data, trading, analysis, system,      │    │   │
│  │  │        web_search, browser, sandbox           │    │   │
│  │  └──────────────────────────────────────────────┘    │   │
│  └──────────────────────────────────────────────────────┘   │
│       │                                                      │
│  ┌────┴─────────────────────────────────────────────┐       │
│  │  Config Layer (YAML)                              │       │
│  │  llm_config.yaml  agents/*.yaml  risk_rules.yaml  │       │
│  └───────────────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
    ┌──────────┐   ┌──────────┐   ┌──────────┐
    │  Broker  │   │  Market  │   │   News   │
    │   API    │   │  Data    │   │   API    │
    └──────────┘   └──────────┘   └──────────┘
```

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Enable automated trading |
| `/stop` | Pause automated trading |
| `/status` | System status |
| `/portfolio` | Portfolio overview |
| `/orders` | Active orders |
| `/analyze` | Trigger LLM analysis |
| `/emergency` | Emergency stop |

## Extending

### Add a New Workflow

```python
from agent_trader.agents.workflow_factory import register_workflow
from agent_trader.agents.workflow_base import WorkflowBase

@register_workflow("my_workflow", description="My custom workflow")
class MyWorkflow(WorkflowBase):
    async def run_workflow(self, initial_context=None):
        # Your logic here
        pass
```

### Add a New Adapter

```python
from agent_trader.interfaces.factory import register_broker
from agent_trader.interfaces.broker_api import BrokerAPI

@register_broker("my_broker")
class MyBrokerAdapter(BrokerAPI):
    # Implement the interface
    pass
```

## Project Structure

```
tradeclaw/
├── main.py                         # Entry point
├── config.py                       # Global config (pydantic-settings)
├── agent_trader/
│   ├── trading_system.py           # Core system orchestrator
│   ├── agents/                     # Workflow implementations
│   │   ├── tools/                  # Agent tools
│   │   │   ├── data_tools.py       # Data retrieval
│   │   │   ├── trading_tools.py    # Trade execution
│   │   │   ├── analysis_tools.py   # Analysis utilities
│   │   │   ├── web_search_tools.py # SearXNG search
│   │   │   ├── browser_tools.py    # Playwright browser automation
│   │   │   └── code_sandbox_tools.py # Code execution sandbox
│   │   ├── workflow_base.py        # Workflow base class
│   │   └── workflow_factory.py     # Workflow registry & discovery
│   ├── adapters/                   # Adapters
│   │   ├── brokers/                # Broker adapters (Alpaca, IBKR)
│   │   ├── market_data/            # Market data adapters (Tiingo)
│   │   ├── news/                   # News adapters (AkShare, Alpaca, Tiingo, Finnhub)
│   │   ├── realtime/               # Real-time data adapters (Finnhub)
│   │   └── transports/             # Message transports (Telegram)
│   ├── config/                     # Configuration managers
│   │   ├── llm_config.py           # LLM provider/model config (YAML)
│   │   ├── agent_config.py         # Per-agent config (YAML)
│   │   └── risk_rules.py           # Risk rules config (YAML)
│   ├── interfaces/                 # Abstract interfaces & factories
│   ├── services/                   # Services
│   │   ├── risk_manager.py         # Risk management
│   │   ├── news_polling.py         # News polling
│   │   ├── realtime_monitor.py     # Real-time monitoring
│   │   └── scheduler_mixin.py      # APScheduler mixin
│   ├── api/                        # FastAPI backend
│   ├── models/                     # Data models
│   ├── db/                         # Database
│   └── utils/                      # Utilities
├── frontend/                       # React + TypeScript frontend
├── user_data/                      # Data directory
│   ├── llm_config.yaml             # LLM configuration
│   ├── risk_rules.yaml             # Risk rules
│   └── agents/                     # Per-workflow configs
├── searxng/                        # SearXNG configuration
├── docker-compose.yml              # Production deployment
├── docker-compose.dev.yml          # Development infrastructure
├── install.sh                      # One-line install script
└── requirements.txt                # Python dependencies
```

## Important Notes

- Paper trading is enabled by default; switch `ALPACA_BASE_URL` for live trading
- All times are based on the configured `TRADING_TIMEZONE` (default: `US/Eastern`)
- Logging uses structlog with structured output and `correlation_id` tracing
- Data is persisted in the `user_data/` directory (database, logs, YAML configs)

## Disclaimer

This software is for educational and research purposes only. Trading involves significant risk and may result in partial or total loss of investment. Past performance does not guarantee future results. Start with paper trading and consult a licensed financial advisor before making investment decisions.

**Use at your own risk.**
