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
  id: string;
  total_value: number;
  cash: number;
  positions_value: number;
  day_pnl: number;
  total_pnl: number;
  positions: Record<string, unknown>[] | null;
  created_at: string;
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
  type: 'tool_call' | 'llm_thinking' | 'decision' | 'notification';
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

export type TriggerType = 'cron' | 'interval';

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
  // conditions
  require_trading_day: boolean;
  require_market_open: boolean;
  // action
  event_type: string;
  event_data?: Record<string, unknown>;
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

// ========== Settings ==========

export interface TradingSettings {
  paper_trading: boolean;
  max_position_size: number;
  max_positions: number;
  rebalance_time: string;
  eod_analysis_time: string;
  stop_loss_percentage: number;
  take_profit_percentage: number;
  daily_loss_limit_percentage: number;
  max_position_concentration: number;
  portfolio_pnl_alert_threshold: number;
  position_loss_alert_threshold: number;
  price_change_threshold: number;
  volatility_threshold: number;
  portfolio_check_interval: number;
  risk_check_interval: number;
  min_workflow_interval_minutes: number;
  workflow_type: string;
  trading_timezone: string;
  exchange: string;
  broker_provider: string;
  market_data_provider: string;
  news_providers: string;
  llm_model: string;
  llm_recursion_limit: number;
  environment: string;
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
