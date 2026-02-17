// ========== Portfolio ==========

export interface Position {
  symbol: string;
  quantity: number;
  market_value: number;
  cost_basis: number;
  unrealized_pnl: number;
  unrealized_pnl_percentage: number;
  side: 'long' | 'short';
  avg_entry_price: number | null;
  current_price: number;
}

export interface Portfolio {
  equity: number;
  cash: number;
  market_value: number;
  day_trade_count: number;
  buying_power: number;
  positions: Position[];
  total_pnl: number;
  day_pnl: number;
  last_updated: string;
}

export interface PortfolioSnapshot {
  timestamp: string;
  equity: number | null;
  profit_loss: number | null;
  profit_loss_pct: number | null;
}

// ========== Orders ==========

export type OrderSide = 'buy' | 'sell';
export type OrderType = 'market' | 'limit' | 'stop' | 'stop_limit' | 'trailing_stop';
export type OrderStatus = 'pending' | 'submitted' | 'partial' | 'filled' | 'cancelled' | 'rejected' | 'expired';
export type TimeInForce = 'day' | 'gtc' | 'ioc' | 'fok';

export interface Order {
  id: string;
  symbol: string;
  side: OrderSide;
  order_type: OrderType;
  quantity: number;
  price: number | null;
  stop_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  time_in_force: TimeInForce;
  status: OrderStatus;
  filled_quantity: number;
  filled_price: number | null;
  broker_order_id: string | null;
  created_at: string;
  updated_at: string;
  filled_at: string | null;
  cancelled_at: string | null;
  error_message: string | null;
}

// ========== Agent ==========

export type TradingAction = 'buy' | 'sell' | 'hold';

export interface TradingDecision {
  id: string;
  action: TradingAction;
  symbol: string;
  quantity: number | null;
  price: number | null;
  reasoning: string;
  confidence: number;
  stop_loss: number | null;
  take_profit: number | null;
  created_at: string;
}

export interface AnalysisHistory {
  id: string;
  workflow_id: string | null;
  trigger: string;
  analysis_type: string | null;
  input_context: Record<string, unknown> | null;
  output_response: string | null;
  tool_calls: string[] | null;
  trades_executed: Record<string, unknown>[] | null;
  execution_time_seconds: number | null;
  success: boolean;
  error_message: string | null;
  created_at: string;
}

export interface AgentMessage {
  id: string;
  session_id: string;
  role: 'human' | 'ai' | 'system' | 'tool';
  content: string;
  additional_kwargs: Record<string, unknown> | null;
  created_at: string;
}

// ========== System ==========

export interface SystemStatus {
  is_running: boolean;
  is_trading_enabled: boolean;
  workflow_type: string;
  market_open: boolean;
  event_queue_size: number;
  scheduler_jobs: number;
  realtime_monitor_active: boolean;
  uptime_seconds: number;
}

export interface SchedulerJob {
  id: string;
  name: string;
  trigger: string;
  next_run_time: string | null;
  status: 'active' | 'paused';
  require_trading_day: boolean;
  require_market_open: boolean;
}

export interface ExecutionRecord {
  job_id: string;
  executed_at: string;
  success: boolean;
  duration_ms: number;
  error: string | null;
}

export interface RiskEvent {
  type: 'stop_loss' | 'take_profit' | 'daily_limit' | 'concentration';
  symbol: string;
  message: string;
  timestamp: string;
}

// ========== Workflow ==========

export interface WorkflowInfo {
  name: string;
  class_name: string;
  description: string;
  features: string[];
  best_for: string;
  deprecated: boolean;
  builtin: boolean;
}

// ========== Agent Tools ==========

export interface ToolParameter {
  name: string;
  type: string;
  description: string;
  required: boolean;
  default_value?: string;
}

export interface AgentTool {
  name: string;
  description: string;
  category: 'data' | 'trading' | 'analysis' | 'system';
  parameters: ToolParameter[];
  enabled: boolean;
}

// ========== Agent Execution ==========

export type ExecutionStepStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped';

export interface ExecutionStep {
  id: string;
  type: string;
  name: string;
  status: ExecutionStepStatus;
  input?: string;
  output?: string;
  duration_ms?: number;
  timestamp: string;
  error?: string;
}

export interface WorkflowExecution {
  id: string;
  workflow_type: string;
  trigger: string;
  status: 'running' | 'completed' | 'failed';
  steps: ExecutionStep[];
  started_at: string;
  completed_at?: string;
  total_duration_ms?: number;
}

// ========== Scheduler CRUD ==========

export type TriggerType = 'cron' | 'interval' | 'once';

export interface JobFormData {
  id: string;
  name: string;
  trigger_type: TriggerType;
  // cron fields
  cron_hour?: number;
  cron_minute?: number;
  cron_day_of_week?: string;
  // interval fields
  interval_minutes?: number;
  interval_hours?: number;
  // once (date) fields
  once_datetime?: string;  // ISO 8601 datetime string
  once_delay_minutes?: number;
  once_mode?: 'datetime' | 'delay';
  // conditions
  require_trading_day: boolean;
  require_market_open: boolean;
  // action
  event_type: string;
  event_data?: Record<string, unknown>;
}

export interface QueuedMessage {
  index: number;
  text: string;
  preview: string;
}

export interface ChatQueueResponse {
  queue_size: number;
  messages: QueuedMessage[];
}

// ========== Rule Triggers ==========

export type RuleTriggerType = 'price_change' | 'volatility' | 'news_importance';

export interface RuleTrigger {
  id: string;
  name: string;
  type: RuleTriggerType;
  enabled: boolean;
  threshold: number;
  description: string;
  last_triggered?: string;
  trigger_count: number;
}

// ========== Agent Config ==========

/**
 * Agent 配置 — 字段完全由后端 workflow 声明。
 * 通用字段: workflow_type, name, system_prompt
 * 其他字段由各 workflow 自行定义（如 llm_model, bl_risk_aversion 等）
 */
export type AgentConfig = Record<string, unknown> & {
  workflow_type: string;
  name: string;
  system_prompt: string | null;
};

export interface ActiveWorkflow {
  workflow_type: string;
  name: string;
  is_running: boolean;
  pending_triggers: number;
  chat_queue_size: number;
  stats: Record<string, unknown>;
}

export interface ChatResponse {
  status: 'queued' | 'triggered';
  message: string;
  queue_size: number;
}

// ========== Settings ==========

export interface TradingSettings {
  // Trading
  paper_trading: boolean;
  max_position_size: number;
  max_positions: number;
  rebalance_time: string;
  eod_analysis_time: string;
  workflow_type: string;
  trading_timezone: string;
  exchange: string;
  // Risk
  risk_management_enabled: boolean;
  stop_loss_percentage: number;
  take_profit_percentage: number;
  daily_loss_limit_percentage: number;
  max_position_concentration: number;
  portfolio_pnl_alert_threshold: number;
  position_loss_alert_threshold: number;
  // Scheduling
  portfolio_check_interval: number;
  risk_check_interval: number;
  min_workflow_interval_minutes: number;
  scheduler_misfire_grace_time: number;
  max_pending_llm_jobs: number;
  message_rate_limit: number;
  // Monitoring
  price_change_threshold: number;
  volatility_threshold: number;
  rebalance_cooldown_seconds: number;
  market_etfs: string;
  // Providers
  broker_provider: string;
  market_data_provider: string;
  realtime_data_provider: string;
  news_providers: string;
  message_provider: string;
  // Endpoints / non-secret connection info
  alpaca_base_url: string;
  telegram_chat_id: string;
  // LLM (agent-specific params like llm_model are in AgentConfig)
  llm_base_url: string;
  news_llm_base_url: string | null;
  news_llm_model: string | null;
  // Execution
  rebalance_min_value_threshold: number;
  rebalance_min_pct_threshold: number;
  rebalance_buy_reserve_ratio: number;
  rebalance_weight_diff_threshold: number;
  rebalance_order_delay_seconds: number;
  cash_keywords: string;
  // Infra
  api_host: string;
  api_port: number;
  api_cors_origins: string;
  environment: string;
  log_level: string;
  log_to_file: boolean;
  // Index signature for dynamic access
  [key: string]: unknown;
}

// ========== Backtest ==========

export interface BacktestConfig {
  start_date: string;
  end_date: string;
  initial_capital: number;
  workflow_type: string;
  symbols: string[];
}

export interface BacktestResult {
  id: string;
  config: BacktestConfig;
  total_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  total_trades: number;
  equity_curve: { date: string; equity: number }[];
  trades: Order[];
  status: 'running' | 'completed' | 'failed';
  created_at: string;
}
