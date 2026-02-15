/**
 * API Layer
 *
 * 所有页面通过此层获取数据，直接调用后端 API。
 */

import { api } from './client';

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

export async function fetchActiveWorkflow(): Promise<ActiveWorkflow> {
  return api.get<ActiveWorkflow>('/agent/active');
}

export async function switchWorkflow(workflowType: string): Promise<{ success: boolean; message: string; workflow_type: string }> {
  return api.post('/agent/switch', { workflow_type: workflowType });
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

export async function runBacktest(config: unknown): Promise<BacktestResult> {
  return api.post<BacktestResult>('/backtest', config);
}

// ========== Helpers ==========

/**
 * 将 AnalysisHistory DB 记录映射为前端 WorkflowExecution 格式
 */
function _analysisToExecution(a: AnalysisHistory): WorkflowExecution {
  return {
    id: a.id,
    workflow_type: a.analysis_type ?? a.trigger,
    trigger: a.trigger,
    status: a.success ? 'completed' : 'failed',
    steps: (a.tool_calls ?? []).map((tc, i) => ({
      id: `${a.id}-step-${i}`,
      type: 'tool_call' as const,
      name: tc,
      status: 'completed' as const,
      timestamp: a.created_at,
    })),
    started_at: a.created_at,
    completed_at: a.created_at,
    total_duration_ms: a.execution_time_seconds ? a.execution_time_seconds * 1000 : undefined,
  };
}
