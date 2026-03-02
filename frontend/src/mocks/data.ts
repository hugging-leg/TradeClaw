/**
 * Centralized Mock Data
 *
 * All mock data lives here. No hardcoded data anywhere else.
 * When the real API is ready, replace the api/ layer — pages stay untouched.
 */

import type {
  Portfolio,
  Position,
  PortfolioSnapshot,
  Order,
  TradingDecision,
  AnalysisHistory,
  AgentMessage,
  SystemStatus,
  SchedulerJob,
  ExecutionRecord,
  RiskEvent,
  WorkflowInfo,
  TradingSettings,
  BacktestResult,
  AgentTool,
  WorkflowExecution,
  RuleTrigger,
} from '@/types';

// ========== Helpers ==========

function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString();
}

function hoursAgo(n: number): string {
  const d = new Date();
  d.setHours(d.getHours() - n);
  return d.toISOString();
}

function minutesAgo(n: number): string {
  const d = new Date();
  d.setMinutes(d.getMinutes() - n);
  return d.toISOString();
}

// ========== Positions ==========

export const mockPositions: Position[] = [
  {
    symbol: 'AAPL',
    quantity: 50,
    market_value: 11250,
    cost_basis: 10500,
    unrealized_pnl: 750,
    unrealized_pnl_percentage: 7.14,
    side: 'long',
    avg_entry_price: 210.0,
    current_price: 225.0,
  },
  {
    symbol: 'MSFT',
    quantity: 30,
    market_value: 12600,
    cost_basis: 11700,
    unrealized_pnl: 900,
    unrealized_pnl_percentage: 7.69,
    side: 'long',
    avg_entry_price: 390.0,
    current_price: 420.0,
  },
  {
    symbol: 'GOOGL',
    quantity: 25,
    market_value: 4375,
    cost_basis: 4500,
    unrealized_pnl: -125,
    unrealized_pnl_percentage: -2.78,
    side: 'long',
    avg_entry_price: 180.0,
    current_price: 175.0,
  },
  {
    symbol: 'NVDA',
    quantity: 15,
    market_value: 19500,
    cost_basis: 16500,
    unrealized_pnl: 3000,
    unrealized_pnl_percentage: 18.18,
    side: 'long',
    avg_entry_price: 1100.0,
    current_price: 1300.0,
  },
  {
    symbol: 'AMZN',
    quantity: 20,
    market_value: 4100,
    cost_basis: 4200,
    unrealized_pnl: -100,
    unrealized_pnl_percentage: -2.38,
    side: 'long',
    avg_entry_price: 210.0,
    current_price: 205.0,
  },
];

// ========== Portfolio ==========

export const mockPortfolio: Portfolio = {
  equity: 128450.75,
  cash: 76625.75,
  market_value: 51825.0,
  day_trade_count: 2,
  buying_power: 153250.5,
  positions: mockPositions,
  total_pnl: 4425.0,
  day_pnl: 1285.32,
  last_updated: new Date().toISOString(),
};

// ========== Portfolio Snapshots (30 days) ==========

export const mockPortfolioSnapshots: PortfolioSnapshot[] = Array.from(
  { length: 30 },
  (_, i) => {
    const dayIndex = 29 - i;
    const baseValue = 120000;
    const trend = dayIndex * 280;
    const noise = Math.sin(dayIndex * 0.8) * 1500 + Math.cos(dayIndex * 1.3) * 800;
    const equity = baseValue + trend + noise;
    const pnl = equity - baseValue;
    const pnlPct = pnl / baseValue;

    return {
      timestamp: daysAgo(dayIndex),
      equity: Math.round(equity * 100) / 100,
      profit_loss: Math.round(pnl * 100) / 100,
      profit_loss_pct: Math.round(pnlPct * 10000) / 10000,
    };
  }
);

// ========== Orders ==========

export const mockOrders: Order[] = [
  {
    id: 'ord-001',
    symbol: 'AAPL',
    side: 'buy',
    order_type: 'market',
    quantity: 50,
    price: null,
    stop_price: null,
    stop_loss: 200.0,
    take_profit: 250.0,
    time_in_force: 'day',
    status: 'filled',
    filled_quantity: 50,
    filled_price: 210.0,
    broker_order_id: 'alp-001',
    created_at: daysAgo(5),
    updated_at: daysAgo(5),
    filled_at: daysAgo(5),
    cancelled_at: null,
    error_message: null,
  },
  {
    id: 'ord-002',
    symbol: 'MSFT',
    side: 'buy',
    order_type: 'limit',
    quantity: 30,
    price: 385.0,
    stop_price: null,
    stop_loss: 370.0,
    take_profit: 430.0,
    time_in_force: 'gtc',
    status: 'filled',
    filled_quantity: 30,
    filled_price: 390.0,
    broker_order_id: 'alp-002',
    created_at: daysAgo(4),
    updated_at: daysAgo(4),
    filled_at: daysAgo(4),
    cancelled_at: null,
    error_message: null,
  },
  {
    id: 'ord-003',
    symbol: 'TSLA',
    side: 'buy',
    order_type: 'limit',
    quantity: 10,
    price: 240.0,
    stop_price: null,
    stop_loss: 220.0,
    take_profit: 280.0,
    time_in_force: 'gtc',
    status: 'pending',
    filled_quantity: 0,
    filled_price: null,
    broker_order_id: 'alp-003',
    created_at: hoursAgo(2),
    updated_at: hoursAgo(2),
    filled_at: null,
    cancelled_at: null,
    error_message: null,
  },
  {
    id: 'ord-004',
    symbol: 'GOOGL',
    side: 'sell',
    order_type: 'market',
    quantity: 10,
    price: null,
    stop_price: null,
    stop_loss: null,
    take_profit: null,
    time_in_force: 'day',
    status: 'cancelled',
    filled_quantity: 0,
    filled_price: null,
    broker_order_id: 'alp-004',
    created_at: daysAgo(2),
    updated_at: daysAgo(2),
    filled_at: null,
    cancelled_at: daysAgo(2),
    error_message: 'Market closed',
  },
  {
    id: 'ord-005',
    symbol: 'NVDA',
    side: 'buy',
    order_type: 'market',
    quantity: 15,
    price: null,
    stop_price: null,
    stop_loss: 1000.0,
    take_profit: 1500.0,
    time_in_force: 'day',
    status: 'filled',
    filled_quantity: 15,
    filled_price: 1100.0,
    broker_order_id: 'alp-005',
    created_at: daysAgo(7),
    updated_at: daysAgo(7),
    filled_at: daysAgo(7),
    cancelled_at: null,
    error_message: null,
  },
  {
    id: 'ord-006',
    symbol: 'AMZN',
    side: 'buy',
    order_type: 'limit',
    quantity: 20,
    price: 205.0,
    stop_price: null,
    stop_loss: 190.0,
    take_profit: 230.0,
    time_in_force: 'day',
    status: 'filled',
    filled_quantity: 20,
    filled_price: 210.0,
    broker_order_id: 'alp-006',
    created_at: daysAgo(3),
    updated_at: daysAgo(3),
    filled_at: daysAgo(3),
    cancelled_at: null,
    error_message: null,
  },
];

// ========== Trading Decisions ==========

export const mockDecisions: TradingDecision[] = [
  {
    id: 'dec-001',
    action: 'buy',
    symbol: 'NVDA',
    quantity: 15,
    price: 1100.0,
    reasoning:
      'Strong AI/ML demand cycle. NVDA earnings beat expectations by 20%. Data center revenue growing 150% YoY. Technical indicators show bullish momentum with RSI at 62.',
    confidence: 0.88,
    stop_loss: 1000.0,
    take_profit: 1500.0,
    created_at: daysAgo(7),
  },
  {
    id: 'dec-002',
    action: 'buy',
    symbol: 'AAPL',
    quantity: 50,
    price: 210.0,
    reasoning:
      'Services revenue hitting new highs. iPhone cycle showing strength in emerging markets. Valuation reasonable at 28x forward P/E. Strong buyback program provides downside support.',
    confidence: 0.75,
    stop_loss: 200.0,
    take_profit: 250.0,
    created_at: daysAgo(5),
  },
  {
    id: 'dec-003',
    action: 'hold',
    symbol: 'GOOGL',
    quantity: null,
    price: null,
    reasoning:
      'Mixed signals: Strong search revenue but regulatory headwinds from DOJ antitrust case. Cloud growth solid at 28% YoY. Maintaining position but not adding.',
    confidence: 0.6,
    stop_loss: null,
    take_profit: null,
    created_at: daysAgo(3),
  },
  {
    id: 'dec-004',
    action: 'buy',
    symbol: 'MSFT',
    quantity: 30,
    price: 390.0,
    reasoning:
      'Azure growth re-accelerating to 31% YoY. Copilot monetization showing early traction. Enterprise AI spending tailwind. Strong free cash flow generation.',
    confidence: 0.82,
    stop_loss: 370.0,
    take_profit: 430.0,
    created_at: daysAgo(4),
  },
  {
    id: 'dec-005',
    action: 'sell',
    symbol: 'META',
    quantity: 25,
    price: 580.0,
    reasoning:
      'Taking profits after 40% run-up. Valuation stretched at 32x forward P/E. Regulatory risks increasing in EU. Reallocating capital to higher-conviction positions.',
    confidence: 0.71,
    stop_loss: null,
    take_profit: null,
    created_at: daysAgo(1),
  },
];

// ========== Analysis History ==========

export const mockAnalyses: AnalysisHistory[] = [
  {
    id: 'ana-001',
    workflow_id: 'wf-daily-001',
    trigger: 'daily_rebalance',
    analysis_type: 'portfolio',
    input_context: { trigger: 'daily_rebalance', market_open: true },
    output_response:
      'Portfolio analysis complete. Current allocation is well-balanced across tech sector. Recommended increasing NVDA position due to strong AI demand. Suggested trimming META after recent run-up.',
    tool_calls: ['get_portfolio', 'get_market_data', 'get_news', 'submit_order'],
    trades_executed: [{ symbol: 'NVDA', side: 'buy', quantity: 15 }],
    execution_time_seconds: 45.2,
    success: true,
    error_message: null,
    created_at: daysAgo(7),
  },
  {
    id: 'ana-002',
    workflow_id: 'wf-realtime-002',
    trigger: 'realtime_price_alert',
    analysis_type: 'market',
    input_context: { trigger: 'price_alert', symbol: 'AAPL', change_pct: 3.2 },
    output_response:
      'AAPL showing unusual strength. Positive sentiment from new product launch rumors. Current price presents buying opportunity at support level.',
    tool_calls: ['get_market_data', 'get_news'],
    trades_executed: [{ symbol: 'AAPL', side: 'buy', quantity: 50 }],
    execution_time_seconds: 28.7,
    success: true,
    error_message: null,
    created_at: daysAgo(5),
  },
  {
    id: 'ana-003',
    workflow_id: 'wf-daily-003',
    trigger: 'daily_rebalance',
    analysis_type: 'portfolio',
    input_context: { trigger: 'daily_rebalance', market_open: true },
    output_response:
      'Market conditions stable. No significant rebalancing needed. All positions within target allocation ranges.',
    tool_calls: ['get_portfolio', 'get_market_data'],
    trades_executed: [],
    execution_time_seconds: 22.1,
    success: true,
    error_message: null,
    created_at: daysAgo(3),
  },
  {
    id: 'ana-004',
    workflow_id: 'wf-news-004',
    trigger: 'news_alert',
    analysis_type: 'risk',
    input_context: { trigger: 'news_alert', headline: 'Fed signals potential rate cut' },
    output_response:
      'Fed dovish signal is positive for growth stocks. Current portfolio is well-positioned. No action needed.',
    tool_calls: ['get_news', 'get_portfolio'],
    trades_executed: [],
    execution_time_seconds: 15.3,
    success: true,
    error_message: null,
    created_at: daysAgo(1),
  },
  {
    id: 'ana-005',
    workflow_id: 'wf-manual-005',
    trigger: 'manual_analysis',
    analysis_type: 'portfolio',
    input_context: { trigger: 'manual_analysis', source: 'telegram' },
    output_response: null,
    tool_calls: ['get_portfolio'],
    trades_executed: [],
    execution_time_seconds: null,
    success: false,
    error_message: 'LLM API timeout after 60 seconds',
    created_at: hoursAgo(6),
  },
];

// ========== Agent Messages ==========

export const mockAgentMessages: AgentMessage[] = [
  {
    id: 'msg-001',
    session_id: 'session-daily-001',
    role: 'system',
    content: 'Daily rebalance workflow triggered. Analyzing portfolio and market conditions.',
    additional_kwargs: null,
    created_at: hoursAgo(8),
  },
  {
    id: 'msg-002',
    session_id: 'session-daily-001',
    role: 'ai',
    content:
      'I will analyze the current portfolio composition and market conditions. Let me check the portfolio first.',
    additional_kwargs: { tool_calls: ['get_portfolio'] },
    created_at: hoursAgo(8),
  },
  {
    id: 'msg-003',
    session_id: 'session-daily-001',
    role: 'tool',
    content: 'Portfolio: 5 positions, equity $128,450.75, day P&L +$1,285.32',
    additional_kwargs: { tool: 'get_portfolio' },
    created_at: hoursAgo(8),
  },
  {
    id: 'msg-004',
    session_id: 'session-daily-001',
    role: 'ai',
    content:
      'Portfolio looks healthy. All positions are within target allocation. NVDA is the top performer at +18.18%. No rebalancing needed today. I recommend holding current positions.',
    additional_kwargs: null,
    created_at: hoursAgo(8),
  },
  {
    id: 'msg-005',
    session_id: 'session-manual-002',
    role: 'human',
    content: '/analyze',
    additional_kwargs: { source: 'telegram' },
    created_at: hoursAgo(2),
  },
  {
    id: 'msg-006',
    session_id: 'session-manual-002',
    role: 'ai',
    content:
      'Starting manual analysis. Let me review current market conditions and news...',
    additional_kwargs: null,
    created_at: hoursAgo(2),
  },
];

// ========== System Status ==========

export const mockSystemStatus: SystemStatus = {
  is_running: true,
  is_trading_enabled: true,
  workflow_type: 'llm_portfolio',
  market_open: true,
  event_queue_size: 0,
  scheduler_jobs: 4,
  realtime_monitor_active: true,
  uptime_seconds: 43200,
};

// ========== Scheduler Jobs ==========

export const mockSchedulerJobs: SchedulerJob[] = [
  {
    id: 'daily_rebalance',
    name: 'Daily Rebalance',
    trigger: 'cron(09:35)',
    next_run_time: (() => {
      const d = new Date();
      d.setDate(d.getDate() + 1);
      d.setHours(9, 35, 0, 0);
      return d.toISOString();
    })(),
    status: 'active',
    require_trading_day: true,
    require_market_open: true,
  },
  {
    id: 'eod_analysis',
    name: 'End of Day Analysis',
    trigger: 'cron(16:05)',
    next_run_time: (() => {
      const d = new Date();
      d.setHours(16, 5, 0, 0);
      if (d < new Date()) d.setDate(d.getDate() + 1);
      return d.toISOString();
    })(),
    status: 'active',
    require_trading_day: true,
    require_market_open: false,
  },
  {
    id: 'portfolio_check',
    name: 'Portfolio Check',
    trigger: 'interval(60min)',
    next_run_time: minutesAgo(-15),
    status: 'active',
    require_trading_day: true,
    require_market_open: true,
  },
  {
    id: 'risk_check',
    name: 'Risk Check',
    trigger: 'interval(15min)',
    next_run_time: minutesAgo(-5),
    status: 'active',
    require_trading_day: true,
    require_market_open: true,
  },
];

// ========== Execution Records ==========

export const mockExecutionRecords: ExecutionRecord[] = [
  { job_id: 'daily_rebalance', executed_at: daysAgo(1), success: true, duration_ms: 45200, error: null },
  { job_id: 'eod_analysis', executed_at: daysAgo(1), success: true, duration_ms: 32100, error: null },
  { job_id: 'portfolio_check', executed_at: hoursAgo(1), success: true, duration_ms: 1200, error: null },
  { job_id: 'risk_check', executed_at: minutesAgo(15), success: true, duration_ms: 850, error: null },
  { job_id: 'risk_check', executed_at: minutesAgo(30), success: true, duration_ms: 920, error: null },
  { job_id: 'portfolio_check', executed_at: hoursAgo(2), success: true, duration_ms: 1100, error: null },
  { job_id: 'daily_rebalance', executed_at: daysAgo(2), success: false, duration_ms: 60000, error: 'LLM API timeout' },
  { job_id: 'risk_check', executed_at: minutesAgo(45), success: true, duration_ms: 780, error: null },
];

// ========== Risk Events ==========

export const mockRiskEvents: RiskEvent[] = [
  {
    type: 'stop_loss',
    symbol: 'TSLA',
    message: 'Stop loss triggered at $220.00 (-8.3%)',
    timestamp: daysAgo(10),
  },
  {
    type: 'concentration',
    symbol: 'NVDA',
    message: 'Position concentration at 37.6% exceeds 25% limit',
    timestamp: daysAgo(2),
  },
  {
    type: 'take_profit',
    symbol: 'META',
    message: 'Take profit triggered at $580.00 (+15.2%)',
    timestamp: daysAgo(1),
  },
];

// ========== Workflows ==========

export const mockWorkflows: Record<string, WorkflowInfo> = {
  llm_portfolio: {
    name: 'LLM Portfolio',
    class_name: 'LLMPortfolioAgent',
    description: 'ReAct agent with LangGraph for intelligent portfolio management',
    features: ['Market analysis', 'News sentiment', 'Portfolio optimization', 'Auto-rebalancing'],
    best_for: 'General purpose portfolio management',
    deprecated: false,
    builtin: true,
  },
  balanced_portfolio: {
    name: 'Balanced Portfolio',
    class_name: 'BalancedPortfolioWorkflow',
    description: 'Equal-weight portfolio strategy with automatic rebalancing',
    features: ['Equal weighting', 'Threshold rebalancing', 'Position sizing'],
    best_for: 'Simple, diversified portfolios',
    deprecated: false,
    builtin: true,
  },
  black_litterman: {
    name: 'Black-Litterman',
    class_name: 'BlackLittermanWorkflow',
    description: 'Black-Litterman model with LLM-generated market views',
    features: ['BL optimization', 'LLM views', 'Risk-adjusted allocation'],
    best_for: 'Quantitative portfolio optimization',
    deprecated: false,
    builtin: true,
  },
  cognitive_arbitrage: {
    name: 'Cognitive Arbitrage',
    class_name: 'CognitiveArbitrageWorkflow',
    description: 'News-driven event arbitrage using cognitive analysis',
    features: ['News scoring', 'Event detection', 'Short-term trading'],
    best_for: 'News-driven short-term opportunities',
    deprecated: false,
    builtin: true,
  },
  tool_calling: {
    name: 'Tool Calling',
    class_name: 'ToolCallingWorkflow',
    description: 'Simple tool-calling workflow for direct LLM interaction',
    features: ['Direct tool access', 'Flexible prompting'],
    best_for: 'Custom analysis tasks',
    deprecated: false,
    builtin: true,
  },
  sequential: {
    name: 'Sequential',
    class_name: 'SequentialWorkflow',
    description: 'Step-by-step sequential analysis workflow',
    features: ['Deterministic flow', 'Step-by-step analysis'],
    best_for: 'Predictable, auditable analysis',
    deprecated: false,
    builtin: true,
  },
};

// ========== Settings ==========

export const mockSettings: TradingSettings = {
  // Trading
  paper_trading: true,
  rebalance_time: '09:30',
  eod_analysis_time: '16:05',
  workflow_type: 'llm_portfolio',
  trading_timezone: 'US/Eastern',
  exchange: 'XNYS',
  // Risk
  risk_management_enabled: true,
  stop_loss_percentage: 0.05,
  take_profit_percentage: 0.15,
  daily_loss_limit_percentage: 0.1,
  max_position_concentration: 0.25,
  portfolio_pnl_alert_threshold: 0.05,
  position_loss_alert_threshold: 0.1,
  // Scheduling
  portfolio_check_interval: 60,
  risk_check_interval: 15,
  min_workflow_interval_minutes: 30,
  scheduler_misfire_grace_time: 60,
  max_pending_llm_jobs: 5,
  message_rate_limit: 1.0,
  // Monitoring
  news_poll_interval_minutes: 5,
  news_poll_max_per_batch: 20,
  news_importance_threshold: 7,
  price_change_threshold: 5.0,
  volatility_threshold: 8.0,
  rebalance_cooldown_seconds: 3600,
  market_etfs: 'SPY,QQQ,IWM',
  // Providers
  broker_provider: 'alpaca',
  market_data_provider: 'tiingo',
  realtime_data_provider: '',
  news_providers: 'tiingo,finnhub',
  message_provider: 'telegram',
  // Endpoints / non-secret connection info
  alpaca_base_url: 'https://paper-api.alpaca.markets',
  telegram_chat_id: '123456789',
  opensandbox_server_url: '',
  // LLM
  llm_base_url: 'https://api.openai.com/v1',
  news_llm_base_url: null,
  news_llm_model: null,
  // Execution
  rebalance_min_value_threshold: 20.0,
  rebalance_min_pct_threshold: 1.0,
  rebalance_buy_reserve_ratio: 0.95,
  rebalance_weight_diff_threshold: 0.02,
  rebalance_order_delay_seconds: 1.0,
  cash_keywords: 'CASH,USD,DOLLAR',
  // Infra
  api_host: '0.0.0.0',
  api_port: 8000,
  api_cors_origins: 'http://localhost:5173,http://localhost:3000',
  environment: 'development',
  log_level: 'INFO',
  log_to_file: true,
};

// ========== Backtest Results ==========

export const mockBacktestResults: BacktestResult[] = [
  {
    id: 'bt-001',
    config: {
      start_date: '2025-01-01',
      end_date: '2025-06-30',
      initial_capital: 100000,
      workflow_type: 'llm_portfolio',
      commission_rate: 0.001,
      slippage_bps: 5.0,
      run_interval_days: 1,
    },
    status: 'completed',
    progress: 1.0,
    current_date: null,
    result: {
      total_return: 0.185,
      annualized_return: 0.42,
      sharpe_ratio: 1.82,
      max_drawdown: 0.083,
      win_rate: 0.642,
      total_trades: 47,
      profit_factor: 2.1,
      avg_trade_pnl: 394.0,
      final_equity: 118500,
      initial_capital: 100000,
    },
    equity_curve: Array.from({ length: 180 }, (_, i) => {
      const base = 100000;
      const trend = i * 100;
      const noise = Math.sin(i * 0.15) * 2000 + Math.cos(i * 0.3) * 1000;
      return {
        date: (() => {
          const d = new Date('2025-01-01');
          d.setDate(d.getDate() + i);
          return d.toISOString().split('T')[0];
        })(),
        equity: Math.round((base + trend + noise) * 100) / 100,
        cash: Math.round((base * 0.3 + noise * 0.1) * 100) / 100,
        positions_value: Math.round((base * 0.7 + trend + noise * 0.9) * 100) / 100,
      };
    }),
    trades: [],
    error: null,
    created_at: daysAgo(3),
    started_at: daysAgo(3),
    completed_at: daysAgo(3),
  },
];

// ========== Agent Tools ==========

export const mockAgentTools: AgentTool[] = [
  {
    name: 'get_portfolio_status',
    description: '获取当前投资组合状态，包括总资产、现金、持仓等信息',
    category: 'data',
    parameters: [],
    enabled: true,
  },
  {
    name: 'get_market_data',
    description: '获取市场概况，包括主要指数（SPY, QQQ等）的最新数据',
    category: 'data',
    parameters: [],
    enabled: true,
  },
  {
    name: 'get_latest_news',
    description: '获取最新市场新闻，支持按股票代码或行业过滤',
    category: 'data',
    parameters: [
      { name: 'limit', type: 'int', description: '新闻数量，默认20条', required: false, default_value: '20' },
      { name: 'symbol', type: 'string', description: '按股票代码过滤（如 AAPL, TSLA）', required: false },
      { name: 'sector', type: 'string', description: '按行业过滤（如 Technology, Finance）', required: false },
    ],
    enabled: true,
  },
  {
    name: 'get_position_analysis',
    description: '分析当前持仓分布，包括各仓位占比、集中度等',
    category: 'analysis',
    parameters: [],
    enabled: true,
  },
  {
    name: 'get_latest_price',
    description: '获取个股最新价格',
    category: 'data',
    parameters: [
      { name: 'symbol', type: 'string', description: '股票代码，如 AAPL', required: true },
    ],
    enabled: true,
  },
  {
    name: 'get_historical_prices',
    description: '获取个股历史价格数据（支持自定义时间框架）',
    category: 'data',
    parameters: [
      { name: 'symbol', type: 'string', description: '股票代码', required: true },
      { name: 'timeframe', type: 'string', description: '时间框架: 1Day, 1Hour, 30Min, 15Min, 5Min, 1Min', required: false, default_value: '1Day' },
      { name: 'limit', type: 'int', description: '返回的K线数量', required: false, default_value: '100' },
    ],
    enabled: true,
  },
  {
    name: 'rebalance_portfolio',
    description: '执行组合重新平衡，指定目标配置百分比',
    category: 'trading',
    parameters: [
      { name: 'target_allocations', type: 'Dict[str, float]', description: '目标配置，例如 {"AAPL": 25.0, "MSFT": 25.0}', required: true },
      { name: 'reason', type: 'string', description: '重新平衡的原因说明', required: true },
    ],
    enabled: true,
  },
  {
    name: 'get_current_time',
    description: '获取当前日期和时间（UTC时间）',
    category: 'system',
    parameters: [],
    enabled: true,
  },
  {
    name: 'check_market_status',
    description: '检查市场是否开放',
    category: 'system',
    parameters: [],
    enabled: true,
  },
  {
    name: 'schedule_next_analysis',
    description: '安排下一次分析的时间（LLM自主调度）',
    category: 'system',
    parameters: [
      { name: 'delay_hours', type: 'float', description: '延迟小时数', required: true },
      { name: 'reason', type: 'string', description: '调度原因', required: true },
    ],
    enabled: true,
  },
];

// ========== Workflow Executions ==========

export const mockWorkflowExecutions: WorkflowExecution[] = [
  {
    id: 'exec-001',
    workflow_type: 'llm_portfolio',
    trigger: 'daily_rebalance',
    status: 'completed',
    steps: [
      {
        id: 'step-1',
        type: 'llm_thinking',
        name: 'Analyzing trigger context',
        status: 'completed',
        output: 'Daily rebalance triggered. I will check portfolio status and market conditions.',
        duration_ms: 1200,
        timestamp: hoursAgo(8),
      },
      {
        id: 'step-2',
        type: 'tool_call',
        name: 'get_portfolio_status',
        status: 'completed',
        input: '{}',
        output: 'Portfolio: $128,450.75 | Cash 59.6% | 5 positions',
        duration_ms: 850,
        timestamp: hoursAgo(8),
      },
      {
        id: 'step-3',
        type: 'tool_call',
        name: 'get_market_data',
        status: 'completed',
        input: '{}',
        output: 'SPY: +0.8%, QQQ: +1.2%, IWM: -0.3%',
        duration_ms: 620,
        timestamp: hoursAgo(8),
      },
      {
        id: 'step-4',
        type: 'tool_call',
        name: 'get_latest_news',
        status: 'completed',
        input: '{"limit": 10}',
        output: '10 news items retrieved. Key: Fed signals rate cut, NVDA earnings beat.',
        duration_ms: 1100,
        timestamp: hoursAgo(8),
      },
      {
        id: 'step-5',
        type: 'llm_thinking',
        name: 'Evaluating portfolio allocation',
        status: 'completed',
        output: 'Portfolio is well-balanced. NVDA is the top performer. No significant rebalancing needed. Current allocation aligns with market conditions.',
        duration_ms: 2800,
        timestamp: hoursAgo(8),
      },
      {
        id: 'step-6',
        type: 'decision',
        name: 'Trading Decision: HOLD',
        status: 'completed',
        output: 'No rebalancing needed. All positions within target ranges.',
        duration_ms: 500,
        timestamp: hoursAgo(8),
      },
      {
        id: 'step-7',
        type: 'notification',
        name: 'Send completion notification',
        status: 'completed',
        output: 'Workflow complete notification sent via Telegram',
        duration_ms: 200,
        timestamp: hoursAgo(8),
      },
    ],
    started_at: hoursAgo(8),
    completed_at: hoursAgo(8),
    total_duration_ms: 7270,
  },
  {
    id: 'exec-002',
    workflow_type: 'llm_portfolio',
    trigger: 'realtime_price_alert',
    status: 'completed',
    steps: [
      {
        id: 'step-1',
        type: 'llm_thinking',
        name: 'Analyzing price alert',
        status: 'completed',
        output: 'NVDA price jumped +5.2%. Checking if this is related to earnings or news.',
        duration_ms: 1500,
        timestamp: daysAgo(1),
      },
      {
        id: 'step-2',
        type: 'tool_call',
        name: 'get_latest_news',
        status: 'completed',
        input: '{"symbol": "NVDA", "limit": 5}',
        output: 'NVDA earnings beat expectations by 20%. Data center revenue growing 150% YoY.',
        duration_ms: 900,
        timestamp: daysAgo(1),
      },
      {
        id: 'step-3',
        type: 'tool_call',
        name: 'get_portfolio_status',
        status: 'completed',
        input: '{}',
        output: 'NVDA position: 15 shares, +18.18%',
        duration_ms: 700,
        timestamp: daysAgo(1),
      },
      {
        id: 'step-4',
        type: 'llm_thinking',
        name: 'Deciding on action',
        status: 'completed',
        output: 'NVDA fundamentals strong. Position already at 15% allocation. Will hold current position. No need to add more given concentration risk.',
        duration_ms: 2200,
        timestamp: daysAgo(1),
      },
      {
        id: 'step-5',
        type: 'decision',
        name: 'Trading Decision: HOLD NVDA',
        status: 'completed',
        output: 'Hold NVDA position. Strong fundamentals but concentration risk limits additional buying.',
        duration_ms: 400,
        timestamp: daysAgo(1),
      },
    ],
    started_at: daysAgo(1),
    completed_at: daysAgo(1),
    total_duration_ms: 5700,
  },
  {
    id: 'exec-003',
    workflow_type: 'llm_portfolio',
    trigger: 'manual_analysis',
    status: 'failed',
    steps: [
      {
        id: 'step-1',
        type: 'llm_thinking',
        name: 'Starting manual analysis',
        status: 'completed',
        output: 'Manual analysis requested. Will perform full portfolio review.',
        duration_ms: 1000,
        timestamp: hoursAgo(6),
      },
      {
        id: 'step-2',
        type: 'tool_call',
        name: 'get_portfolio_status',
        status: 'completed',
        input: '{}',
        output: 'Portfolio retrieved successfully.',
        duration_ms: 800,
        timestamp: hoursAgo(6),
      },
      {
        id: 'step-3',
        type: 'tool_call',
        name: 'get_market_data',
        status: 'failed',
        input: '{}',
        error: 'LLM API timeout after 60 seconds',
        duration_ms: 60000,
        timestamp: hoursAgo(6),
      },
    ],
    started_at: hoursAgo(6),
    completed_at: hoursAgo(6),
    total_duration_ms: 61800,
  },
];

// ========== Rule Triggers ==========

export const mockRuleTriggers: RuleTrigger[] = [
  {
    id: 'rule-price-change',
    name: 'Price Change Alert',
    type: 'price_change',
    enabled: true,
    threshold: 5.0,
    description: 'Trigger analysis when any held position price changes by ±5% from daily open',
    last_triggered: daysAgo(2),
    trigger_count: 12,
  },
  {
    id: 'rule-volatility',
    name: 'High Volatility Alert',
    type: 'volatility',
    enabled: true,
    threshold: 8.0,
    description: 'Trigger analysis when intraday volatility (high-low range) exceeds 8%',
    last_triggered: daysAgo(5),
    trigger_count: 4,
  },
  {
    id: 'rule-news',
    name: 'Important News Alert',
    type: 'news_importance',
    enabled: true,
    threshold: 0.8,
    description: 'Trigger analysis when LLM evaluates news importance above 0.8 (high urgency)',
    last_triggered: daysAgo(1),
    trigger_count: 8,
  },
];
