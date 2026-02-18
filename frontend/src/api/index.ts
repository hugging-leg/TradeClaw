/**
 * API Layer
 *
 * 所有页面通过此层获取数据，直接调用后端 API。
 */

import { api } from './client';

// ========== Auth ==========

export async function fetchAuthStatus(): Promise<{ auth_enabled: boolean }> {
  return api.get<{ auth_enabled: boolean }>('/auth/status');
}

export async function login(username: string, password: string): Promise<{ access_token: string; expires_in: number }> {
  return api.post<{ access_token: string; expires_in: number }>('/auth/login', { username, password });
}

// ========== Data API ==========

import type {
  Portfolio,
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
  AgentConfig,
  ActiveWorkflow,
  WorkflowExecution,
  RuleTrigger,
  JobFormData,
  ChatResponse,
  ChatQueueResponse,
} from '@/types';

// ========== Portfolio ==========

export async function fetchPortfolio(): Promise<Portfolio> {
  return api.get<Portfolio>('/portfolio');
}

export async function fetchPortfolioHistory(days = 30): Promise<PortfolioSnapshot[]> {
  return api.get<PortfolioSnapshot[]>(`/portfolio/history?days=${days}`);
}

// ========== Orders ==========

export async function fetchOrders(status?: string): Promise<Order[]> {
  const query = status ? `?status=${status}` : '';
  return api.get<Order[]>(`/orders${query}`);
}

export async function fetchActiveOrders(): Promise<Order[]> {
  return api.get<Order[]>('/orders/active');
}

export async function cancelOrder(orderId: string): Promise<{ success: boolean; order_id: string; message: string }> {
  return api.delete<{ success: boolean; order_id: string; message: string }>(`/orders/${orderId}`);
}

// ========== Agent ==========

export async function fetchDecisions(limit = 20): Promise<TradingDecision[]> {
  return api.get<TradingDecision[]>(`/agent/decisions?limit=${limit}`);
}

export async function fetchAnalyses(limit = 20): Promise<AnalysisHistory[]> {
  return api.get<AnalysisHistory[]>(`/agent/executions?limit=${limit}`);
}

export async function fetchAgentMessages(sessionId?: string): Promise<AgentMessage[]> {
  const query = sessionId ? `?session_id=${sessionId}` : '';
  return api.get<AgentMessage[]>(`/agent/messages${query}`);
}

// ========== System ==========

export async function fetchSystemStatus(): Promise<SystemStatus> {
  return api.get<SystemStatus>('/system/status');
}

export async function fetchSchedulerJobs(): Promise<SchedulerJob[]> {
  return api.get<SchedulerJob[]>('/scheduler/jobs');
}

export async function fetchExecutionHistory(): Promise<ExecutionRecord[]> {
  const status = await api.get<{ execution_history?: ExecutionRecord[] }>('/scheduler/status');
  return status.execution_history ?? [];
}

export async function fetchRiskEvents(): Promise<RiskEvent[]> {
  const status = await api.get<{ risk_events: RiskEvent[] }>('/system/status');
  return status.risk_events ?? [];
}

// ========== Workflows ==========

export async function fetchWorkflows(): Promise<Record<string, WorkflowInfo>> {
  return api.get<Record<string, WorkflowInfo>>('/agent/workflows');
}

export async function reloadWorkflows(): Promise<{
  loaded: string[];
  removed: string[];
  total: number;
  workflows: Record<string, WorkflowInfo>;
}> {
  return api.post('/agent/workflows/reload', {});
}

export async function fetchActiveWorkflow(): Promise<ActiveWorkflow> {
  return api.get<ActiveWorkflow>('/agent/active');
}

export async function switchWorkflow(workflowType: string): Promise<{ success: boolean; message: string; workflow_type: string }> {
  return api.post('/agent/switch', { workflow_type: workflowType });
}

// ========== Agent Chat ==========

export async function sendAgentChat(message: string): Promise<ChatResponse> {
  return api.post<ChatResponse>('/agent/chat', { message });
}

export async function fetchChatQueue(): Promise<ChatQueueResponse> {
  return api.get<ChatQueueResponse>('/agent/chat/queue');
}

export async function cancelQueuedMessage(index: number): Promise<{ success: boolean; removed: string; queue_size: number }> {
  return api.delete(`/agent/chat/queue/${index}`);
}

export async function clearChatQueue(): Promise<{ success: boolean; cleared: number; queue_size: number }> {
  return api.delete('/agent/chat/queue');
}

// ========== Agent Config ==========

export async function fetchAgentConfig(): Promise<AgentConfig> {
  return api.get<AgentConfig>('/agent/config');
}

export async function updateAgentConfig(updates: Partial<AgentConfig>): Promise<{ updated: string[]; config: AgentConfig }> {
  return api.patch('/agent/config', updates);
}

// ========== Settings ==========

export async function fetchSettings(): Promise<TradingSettings> {
  return api.get<TradingSettings>('/settings');
}

export async function updateSettings(_settings: Partial<TradingSettings>): Promise<TradingSettings> {
  const res = await api.patch<{ current: TradingSettings }>('/settings', _settings);
  return res.current;
}

// ========== Actions ==========

export async function triggerAnalysis(): Promise<{ success: boolean; message: string }> {
  return api.post<{ success: boolean; message: string }>('/system/analyze');
}

export async function toggleTrading(enabled: boolean): Promise<{ success: boolean }> {
  const path = enabled ? '/system/trading/enable' : '/system/trading/disable';
  return api.post<{ success: boolean }>(path);
}

export async function emergencyStop(): Promise<{ success: boolean }> {
  return api.post<{ success: boolean }>('/system/emergency-stop');
}

// ========== Agent Tools & Execution ==========

export async function fetchAgentTools(): Promise<AgentTool[]> {
  return api.get<AgentTool[]>('/agent/tools');
}

export async function toggleAgentTool(toolName: string, enabled: boolean): Promise<{ name: string; enabled: boolean }> {
  return api.patch<{ name: string; enabled: boolean }>(`/agent/tools/${toolName}`, { enabled });
}

export async function fetchWorkflowExecutions(): Promise<WorkflowExecution[]> {
  const analyses = await api.get<AnalysisHistory[]>('/agent/executions?limit=10');
  return analyses.map((a) => _analysisToExecution(a));
}

export async function fetchLatestExecution(): Promise<WorkflowExecution | null> {
  const executions = await fetchWorkflowExecutions();
  return executions[0] || null;
}

export async function fetchWorkflowStats(): Promise<{ workflow_type: string; is_running: boolean; stats: Record<string, unknown> }> {
  return api.get('/agent/stats');
}

// ========== Scheduler CRUD ==========

export async function createSchedulerJob(job: JobFormData): Promise<SchedulerJob> {
  if (job.trigger_type === 'cron') {
    return api.post<SchedulerJob>('/scheduler/jobs/cron', {
      job_id: job.id,
      hour: job.cron_hour ?? 9,
      minute: job.cron_minute ?? 30,
      day_of_week: job.cron_day_of_week ?? 'mon-fri',
      require_trading_day: job.require_trading_day,
      require_market_open: job.require_market_open,
      event_type: job.event_type,
      event_data: job.event_data,
    });
  } else if (job.trigger_type === 'once') {
    return api.post<SchedulerJob>('/scheduler/jobs/date', {
      job_id: job.id,
      run_at: job.once_mode === 'datetime' ? job.once_datetime : undefined,
      delay_minutes: job.once_mode === 'delay' ? job.once_delay_minutes : undefined,
      require_trading_day: job.require_trading_day,
      trigger_name: job.event_type === 'trigger_workflow' ? 'scheduled_once' : job.event_type,
    });
  } else {
    return api.post<SchedulerJob>('/scheduler/jobs/interval', {
      job_id: job.id,
      minutes: job.interval_minutes,
      hours: job.interval_hours,
      require_market_open: job.require_market_open,
      event_type: job.event_type,
      event_data: job.event_data,
    });
  }
}

export async function deleteSchedulerJob(jobId: string): Promise<{ success: boolean }> {
  return api.delete<{ success: boolean }>(`/scheduler/jobs/${jobId}`);
}

export async function pauseSchedulerJob(jobId: string): Promise<SchedulerJob> {
  return api.post<SchedulerJob>(`/scheduler/jobs/${jobId}/pause`);
}

export async function resumeSchedulerJob(jobId: string): Promise<SchedulerJob> {
  return api.post<SchedulerJob>(`/scheduler/jobs/${jobId}/resume`);
}

// ========== Rule Triggers ==========

export async function fetchRuleTriggers(): Promise<RuleTrigger[]> {
  return api.get<RuleTrigger[]>('/scheduler/rules');
}

export async function updateRuleTrigger(id: string, updates: Partial<RuleTrigger>): Promise<RuleTrigger> {
  const result = await api.patch<RuleTrigger[]>(`/scheduler/rules/${id}`, updates);
  const updated = (Array.isArray(result) ? result : []).find((r) => r.id === id);
  if (!updated) throw new Error(`Rule ${id} not found in response`);
  return updated;
}

// ========== Backtest ==========

export async function fetchBacktestResults(): Promise<BacktestResult[]> {
  return api.get<BacktestResult[]>('/backtest');
}

export async function fetchBacktestDetail(taskId: string): Promise<BacktestResult> {
  return api.get<BacktestResult>(`/backtest/${taskId}`);
}

export async function submitBacktest(config: {
  start_date: string;
  end_date: string;
  initial_capital: number;
  workflow_type: string;
  commission_rate: number;
  slippage_bps: number;
  run_interval_days: number;
}): Promise<BacktestResult> {
  return api.post<BacktestResult>('/backtest', config);
}

export async function cancelBacktest(taskId: string): Promise<{ success: boolean; message: string }> {
  return api.post<{ success: boolean; message: string }>(`/backtest/${taskId}/cancel`, {});
}

/** @deprecated Use submitBacktest instead */
export async function runBacktest(config: unknown): Promise<BacktestResult> {
  return api.post<BacktestResult>('/backtest', config);
}

// ========== Helpers ==========

/**
 * 将 AnalysisHistory DB 记录映射为前端 WorkflowExecution 格式
 *
 * DB 中存储了 tool_calls（工具名称列表）和 output_response（LLM 回复文本），
 * 这里将它们还原为 ExecutionStep 列表，以便在 ExecutionCard 中展示。
 */
function _analysisToExecution(a: AnalysisHistory): WorkflowExecution {
  const steps: WorkflowExecution['steps'] = [];

  // Tool call steps
  if (a.tool_calls?.length) {
    for (let i = 0; i < a.tool_calls.length; i++) {
      steps.push({
        id: `${a.id}-tool-${i}`,
        type: 'tool_call',
        name: a.tool_calls[i],
        status: 'completed',
        timestamp: a.created_at,
      });
    }
  }

  // LLM thinking step（从 output_response 还原）
  if (a.output_response) {
    steps.push({
      id: `${a.id}-thinking`,
      type: 'llm_thinking',
      name: 'Agent 思考结果',
      status: a.success ? 'completed' : 'failed',
      output: a.output_response,
      timestamp: a.created_at,
    });
  }

  // Error step
  if (!a.success && a.error_message) {
    steps.push({
      id: `${a.id}-error`,
      type: 'notification',
      name: 'Error',
      status: 'failed',
      error: a.error_message,
      timestamp: a.created_at,
    });
  }

  return {
    id: a.id,
    workflow_type: a.analysis_type ?? a.trigger,
    trigger: a.trigger,
    status: a.success ? 'completed' : 'failed',
    steps,
    started_at: a.created_at,
    completed_at: a.created_at,
    total_duration_ms: a.execution_time_seconds ? a.execution_time_seconds * 1000 : undefined,
  };
}
