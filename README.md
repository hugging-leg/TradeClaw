# TradeClaw — LLM Agent Trading System

AI 驱动的自主交易系统，支持美股和 ETF 交易。

## 核心特性

- **LLM 驱动决策** - 使用 LangGraph ReAct Agent，无硬编码规则
- **事件驱动架构** - 异步事件队列，组件完全解耦
- **多 Workflow 支持** - 顺序执行、工具调用、Black-Litterman、认知套利等
- **灵活 LLM 配置** - 多 Provider/模型自由组合，按 Agent 独立配置，YAML 持久化
- **实时监控** - WebSocket 实时行情 + 新闻轮询（AkShare/Tiingo/Finnhub），LLM 评估重要性
- **可配置风险规则** - 止损止盈规则链（YAML），支持硬编码规则与 LLM 分析触发共存
- **浏览器自动化** - Playwright 驱动，支持动态网页抓取和交互
- **代码执行沙箱** - RestrictedPython 安全沙箱，Agent 可执行数据分析代码
- **Telegram 控制** - 远程监控和命令执行
- **现代 Web UI** - React + TypeScript + TailwindCSS 响应式前端

## 快速开始

### 1. 安装

```bash
git clone https://github.com/BryantSuen/Agent-Trader
cd Agent-Trader
pip install -r requirements.txt
```

### 2. 配置

```bash
cp env.template .env
```

编辑 `.env`：

```bash
# Broker
ALPACA_API_KEY=your_key
ALPACA_SECRET_KEY=your_secret

# Market Data
TIINGO_API_KEY=your_key
FINNHUB_API_KEY=your_key

# LLM (兜底配置，推荐使用 Web UI 的 LLM Providers 管理)
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=your_key
LLM_MODEL=deepseek-chat

# Workflow
WORKFLOW_TYPE=llm_portfolio

# Telegram (可选)
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 3. 运行

```bash
python main.py
```

### Docker 部署

```bash
docker-compose up -d
```

数据存储在 `user_data/` 目录（数据库、日志等）。

## 配置说明

### 提供商配置

| 类型 | 配置项 | 可选值 |
|------|--------|--------|
| Broker | `BROKER_PROVIDER` | `alpaca`, `interactive_brokers` |
| 行情 | `MARKET_DATA_PROVIDER` | `tiingo` |
| 新闻 | `NEWS_PROVIDERS` | `tiingo`, `finnhub`, `unusual_whales` |
| 实时数据 | `REALTIME_DATA_PROVIDER` | `finnhub` |
| 消息 | `MESSAGE_PROVIDER` | `telegram` |

### LLM 配置

LLM 配置通过 `user_data/llm_config.yaml` 管理（也可通过 Web UI 的 LLM Providers 页面配置）：

```yaml
providers:
  - name: deepseek
    base_url: https://api.deepseek.com/v1
    api_key: sk-xxx
    models:
      - name: deepseek-chat
        model_id: deepseek-chat
        description: 主力模型
      - name: deepseek-reasoner
        model_id: deepseek-reasoner
        description: 推理模型

  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-xxx
    models:
      - name: gpt4o-mini
        model_id: gpt-4o-mini
        description: 快速便宜

roles:
  agent: deepseek-chat        # 主 Agent 使用的模型
  news_filter: gpt4o-mini     # 新闻过滤使用便宜模型
  memory_summary: gpt4o-mini  # 记忆摘要
```

每个 Agent 也可以在其独立配置中指定 `llm_model` 覆盖默认的 `agent` role。

### Workflow 类型

| 类型 | 说明 |
|------|------|
| `sequential` | 顺序执行固定步骤 |
| `tool_calling` | LLM 动态选择工具 |
| `llm_portfolio` | ReAct Agent 自主决策（推荐） |
| `balanced_portfolio` | 均衡组合策略 |
| `black_litterman` | Black-Litterman 模型优化 |
| `cognitive_arbitrage` | 认知套利策略 |

---

## 核心 Agent Workflow 详解

### 1. LLM Portfolio Agent (`llm_portfolio`)

**推荐使用** - 完全自主的 AI 投资组合经理。

#### 核心理念
- 使用 LangGraph ReAct Agent 架构：**Think → Act → Observe → Repeat**
- 零硬编码规则，所有决策由 LLM 自主完成
- 内置 Memory 支持，保持对话状态和历史记忆

#### 决策流程
```
触发事件 → 获取组合状态 → 获取市场数据 → 获取新闻 
    → LLM 分析 → 决定是否调仓 → 执行交易 → 安排下次分析
```

#### 工具列表

| 工具 | 分类 | 功能 |
|------|------|------|
| `get_portfolio_status` | data | 获取组合状态（总资产、现金、持仓） |
| `get_market_data` | data | 获取市场概况（SPY, QQQ 等指数） |
| `get_latest_news` | data | 获取新闻（支持按股票/行业过滤） |
| `get_latest_price` | data | 获取实时价格 |
| `get_historical_prices` | data | 获取历史 K 线 |
| `check_market_status` | system | 检查市场开盘状态 |
| `adjust_position` | trading | 调整单一持仓到目标比例 |
| `schedule_next_analysis` | system | 安排下次分析时间 |
| `web_search` | web_search | SearXNG 元搜索引擎搜索 |
| `web_read` | web_search | 提取网页正文（Trafilatura） |
| `browser_goto` | browser | 浏览器访问动态网页（Playwright） |
| `browser_screenshot` | browser | 截取当前页面截图 |
| `browser_action` | browser | 页面交互（点击、填写、执行JS） |
| `execute_python` | sandbox | 安全沙箱执行 Python 代码 |

#### 投资风格
- 追踪主升趋势，避免炒作垃圾股
- 严格分仓，避免单票梭哈
- 灵活使用杠杆 ETF（TQQQ/SQQQ）进行增强
- 重点关注：科技股、金融、黄金、Fed 政策

#### 配置示例
```bash
WORKFLOW_TYPE=llm_portfolio
```

---

### 2. Black-Litterman Workflow (`black_litterman`)

**量化 + AI 结合** - 基于 Black-Litterman 模型的科学配置。

#### 核心理念
Black-Litterman 模型是一种将市场均衡收益与投资者主观观点相结合的资产配置方法：

```
市场均衡收益 (Prior) + LLM 生成的观点 (Views) 
    → 贝叶斯更新 → 后验收益预期 → 均值-方差优化 → 最优权重
```

#### 决策流程
```
1. 获取资产池历史数据（默认 1 年）
2. 计算协方差矩阵和市场隐含均衡收益
3. LLM 分析市场，生成投资观点和置信度
4. Black-Litterman 模型融合先验和观点
5. 均值-方差优化求解最优权重
6. 执行组合再平衡
```

#### 默认资产池
```python
['SPY', 'QQQ', 'IWM',           # 指数 ETF
 'AAPL', 'MSFT', 'GOOGL',       # 大型科技
 'NVDA', 'AMD', 'META',         # 科技成长
 'GLD', 'TLT',                  # 黄金、长期国债
 'XLF', 'XLE']                  # 金融、能源
```

#### LLM 观点格式
```json
{
  "views": {
    "NVDA": 0.20,   // 预期超越市场 20%
    "TLT": -0.05    // 预期跑输市场 5%
  },
  "view_confidences": {
    "NVDA": 0.8,    // 80% 置信度
    "TLT": 0.6      // 60% 置信度
  },
  "reasoning": "AI 芯片需求强劲，利率预期下行有限..."
}
```

#### 优势
- 数学上的均值-方差优化
- 观点可解释、可追溯
- 置信度控制观点对结果的影响程度
- 无观点时回归市场均衡权重

#### 依赖
```bash
pip install pyportfolioopt cvxpy
```

#### 配置示例
```bash
WORKFLOW_TYPE=black_litterman
```

---

### 3. Cognitive Arbitrage Workflow (`cognitive_arbitrage`)

**二阶动量策略** - 利用新闻传导时间差套利。

#### 核心理念
```
直接受益股票 → 已被市场发现，已经涨过了
间接受益股票 → 供应链/竞争/行业联动，反应较慢，存在套利空间
```

核心思想：**买入间接受益评分最高的股票**

#### 决策流程
```
1. 获取市场新闻
2. LLM 分析每条新闻，识别：
   - 直接受益/受损的股票（新闻直接相关）
   - 间接受益/受损的股票（供应链、竞争、行业联动）
3. 累积评分（只关注间接受益）
4. 买入间接受益评分最高的股票
5. 持有固定天数后卖出
```

#### LLM 分析输出格式
```json
{
  "direct_benefits": [
    {"ticker": "NVDA", "relevance": 9, "reason": "H100 销量超预期"}
  ],
  "indirect_benefits": [
    {"ticker": "TSM", "confidence": 5, "reason": "台积电代工受益", "chain": "NVDA 订单增加 → TSM 产能利用率提升"},
    {"ticker": "AVGO", "confidence": 4, "reason": "网络芯片需求", "chain": "AI 服务器增加 → 网络设备需求增加"}
  ],
  "direct_negatives": [...],
  "indirect_negatives": [...]
}
```

#### 评分规则
| 类型 | 分数范围 | 说明 |
|------|----------|------|
| 直接受益 | 7-10 分 | 记录但不买（已涨过） |
| 间接受益 | 1-6 分 × 1.5 | **真正要买的** |
| 间接受损 | -1 到 -6 分 | 减分 |

#### 传导链示例
- NVDA 芯片销量增加 → AMD 竞争压力（间接受损）
- NVDA 芯片销量增加 → TSM 代工受益（间接受益）
- 美联储降息 → 科技股估值提升（间接受益）
- 原油价格上涨 → 航空公司成本上升（间接受损）

#### 适用场景
- 利用新闻传导的时间差
- 市场反应较慢的二阶效应
- 供应链和行业联动分析

#### 配置示例
```bash
WORKFLOW_TYPE=cognitive_arbitrage
```

---

### Workflow 对比

| 特性 | LLM Portfolio | Black-Litterman | Cognitive Arbitrage |
|------|---------------|-----------------|---------------------|
| 决策方式 | 完全 LLM 自主 | 量化模型 + LLM 观点 | LLM 分析新闻传导 |
| 数学基础 | 无 | 均值-方差优化 | 评分累积 |
| 适合人群 | 通用 | 量化爱好者 | 事件驱动交易者 |
| 可解释性 | 中 | 高 | 高（传导链可追溯） |
| 资产范围 | 任意 | 固定资产池 | 动态（LLM 识别） |
| 核心优势 | 灵活自主 | 科学配置 | 时间差套利 |

### 风险管理

风险规则通过 `user_data/risk_rules.yaml` 配置，支持多规则集和 LLM 分析触发：

```yaml
active_rule_set: default
rule_sets:
  - name: default
    description: 系统默认风险规则集
    rules:
      - id: default_stop_loss
        name: 默认止损
        type: stop_loss
        threshold: 5.0       # 5% 止损
        action: close_position
      - id: default_take_profit
        name: 默认止盈
        type: take_profit
        threshold: 15.0      # 15% 止盈
        action: close_position
      - id: concentration_llm
        name: 仓位集中度 LLM 分析
        type: position_concentration
        threshold: 25.0      # 单仓位 > 25% 触发 LLM 分析
        action: trigger_llm_analysis
```

规则动作类型：`close_position`（平仓）、`trigger_llm_analysis`（触发 LLM 分析）、`disable_trading`（禁用交易）

也可通过 `.env` 设置基础参数：
```bash
RISK_MANAGEMENT_ENABLED=true
STOP_LOSS_PERCENTAGE=0.05
TAKE_PROFIT_PERCENTAGE=0.15
```

### 实时监控

```bash
PRICE_CHANGE_THRESHOLD=5.0      # 价格波动阈值 (%)
VOLATILITY_THRESHOLD=8.0         # 波动率阈值 (%)
REBALANCE_COOLDOWN_SECONDS=3600  # 冷却期 (秒)
```

## 架构

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

## Telegram 命令

| 命令 | 说明 |
|------|------|
| `/start` | 启用自动交易 |
| `/stop` | 暂停自动交易 |
| `/status` | 系统状态 |
| `/portfolio` | 组合概览 |
| `/orders` | 活跃订单 |
| `/analyze` | 触发 LLM 分析 |
| `/emergency` | 紧急停止 |

## 扩展开发

### 添加新的 Workflow

```python
from agent_trader.agents.workflow_factory import register_workflow
from agent_trader.agents.workflow_base import WorkflowBase

@register_workflow("my_workflow", description="My custom workflow")
class MyWorkflow(WorkflowBase):
    async def run_workflow(self, initial_context=None):
        # 实现逻辑
        pass
```

### 添加新的适配器

```python
from agent_trader.interfaces.factory import register_broker
from agent_trader.interfaces.broker_api import BrokerAPI

@register_broker("my_broker")
class MyBrokerAdapter(BrokerAPI):
    # 实现接口
    pass
```

## 目录结构

```
TradeClaw/
├── main.py                         # 入口
├── config.py                       # 全局配置 (pydantic-settings)
├── agent_trader/
│   ├── trading_system.py           # 核心系统协调器
│   ├── agents/                     # Workflow 实现
│   │   ├── tools/                  # Agent Tools
│   │   │   ├── data_tools.py       # 数据获取
│   │   │   ├── trading_tools.py    # 交易执行
│   │   │   ├── analysis_tools.py   # 分析工具
│   │   │   ├── web_search_tools.py # SearXNG 搜索
│   │   │   ├── browser_tools.py    # Playwright 浏览器自动化
│   │   │   └── code_sandbox_tools.py # RestrictedPython 沙箱
│   │   ├── workflow_base.py        # Workflow 基类
│   │   └── workflow_factory.py     # Workflow 注册和发现
│   ├── adapters/                   # 适配器
│   │   ├── brokers/                # Broker 适配器 (Alpaca, IB)
│   │   ├── market_data/            # 行情适配器 (Tiingo)
│   │   ├── news/                   # 新闻适配器 (Tiingo, Finnhub, AkShare)
│   │   ├── realtime/               # 实时数据适配器 (Finnhub)
│   │   └── transports/             # 消息传输适配器 (Telegram)
│   ├── config/                     # 配置管理
│   │   ├── llm_config.py           # LLM Provider/Model 配置 (YAML)
│   │   ├── agent_config.py         # Agent 独立配置 (YAML)
│   │   └── risk_rules.py           # 风险规则配置 (YAML)
│   ├── interfaces/                 # 抽象接口和工厂
│   ├── services/                   # 服务
│   │   ├── risk_manager.py         # 风险管理
│   │   ├── news_polling.py         # 新闻轮询
│   │   ├── realtime_monitor.py     # 实时监控
│   │   └── scheduler_mixin.py      # APScheduler 混入
│   ├── api/                        # FastAPI 后端
│   ├── models/                     # 数据模型
│   ├── db/                         # 数据库
│   └── utils/                      # 工具函数
├── frontend/                       # React + TypeScript 前端
├── user_data/                      # 数据目录
│   ├── llm_config.yaml             # LLM 配置
│   ├── risk_rules.yaml             # 风险规则
│   └── agents/                     # 各 Workflow 独立配置
├── docker-compose.yml              # Docker 部署
└── requirements.txt                # 依赖
```

## 注意事项

- 默认使用 Paper Trading，生产环境需修改 `ALPACA_BASE_URL`
- 所有时间基于配置的 `TRADING_TIMEZONE`（默认 US/Eastern）
- 日志使用 structlog，支持结构化输出和 correlation_id 追踪

## 风险声明

本软件仅供教育和研究用途。交易涉及重大风险，可能导致全部或部分投资损失。过去的表现不代表未来的结果。请从 Paper Trading 开始，并在做出投资决定前咨询持牌财务顾问。

**风险自担。**
