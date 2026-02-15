/**
 * API Layer
 *
 * Currently returns mock data. When the backend API is ready,
 * replace implementations here — all pages use this layer exclusively.
 */

import {
  mockPortfolio,
  mockPortfolioSnapshots,
  mockOrders,
  mockDecisions,
  mockAnalyses,
  mockAgentMessages,
  mockSystemStatus,
  mockSchedulerJobs,
  mockExecutionRecords,
  mockRiskEvents,
  mockWorkflows,
  mockSettings,
  mockBacktestResults,
  mockAgentTools,
  mockWorkflowExecutions,
  mockRuleTriggers,
} from '@/mocks/data';

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
  WorkflowExecution,
  RuleTrigger,
  JobFormData,
} from '@/types';

// Simulate network delay
const delay = (ms = 300) => new Promise((r) => setTimeout(r, ms));

// ========== Portfolio ==========

export async function fetchPortfolio(): Promise<Portfolio> {
  await delay();
  return mockPortfolio;
}

export async function fetchPortfolioHistory(days = 30): Promise<PortfolioSnapshot[]> {
  await delay();
  return mockPortfolioSnapshots.slice(0, days);
}

// ========== Orders ==========

export async function fetchOrders(status?: string): Promise<Order[]> {
  await delay();
  if (status) return mockOrders.filter((o) => o.status === status);
  return mockOrders;
}

export async function fetchActiveOrders(): Promise<Order[]> {
  await delay();
  return mockOrders.filter((o) => ['pending', 'submitted', 'partial'].includes(o.status));
}

// ========== Agent ==========

export async function fetchDecisions(limit = 20): Promise<TradingDecision[]> {
  await delay();
  return mockDecisions.slice(0, limit);
}

export async function fetchAnalyses(limit = 20): Promise<AnalysisHistory[]> {
  await delay();
  return mockAnalyses.slice(0, limit);
}

export async function fetchAgentMessages(sessionId?: string): Promise<AgentMessage[]> {
  await delay();
  if (sessionId) return mockAgentMessages.filter((m) => m.session_id === sessionId);
  return mockAgentMessages;
}

// ========== System ==========

export async function fetchSystemStatus(): Promise<SystemStatus> {
  await delay(200);
  return mockSystemStatus;
}

export async function fetchSchedulerJobs(): Promise<SchedulerJob[]> {
  await delay();
  return mockSchedulerJobs;
}

export async function fetchExecutionHistory(): Promise<ExecutionRecord[]> {
  await delay();
  return mockExecutionRecords;
}

export async function fetchRiskEvents(): Promise<RiskEvent[]> {
  await delay();
  return mockRiskEvents;
}

// ========== Workflows ==========

export async function fetchWorkflows(): Promise<Record<string, WorkflowInfo>> {
  await delay();
  return mockWorkflows;
}

// ========== Settings ==========

export async function fetchSettings(): Promise<TradingSettings> {
  await delay();
  return mockSettings;
}

export async function updateSettings(_settings: Partial<TradingSettings>): Promise<TradingSettings> {
  await delay(500);
  // In real impl, this would POST to the backend
  return { ...mockSettings, ..._settings };
}

// ========== Actions ==========

export async function triggerAnalysis(): Promise<{ success: boolean; message: string }> {
  await delay(500);
  return { success: true, message: 'Analysis triggered successfully' };
}

export async function toggleTrading(enabled: boolean): Promise<{ success: boolean }> {
  await delay(500);
  mockSystemStatus.is_trading_enabled = enabled;
  return { success: true };
}

export async function emergencyStop(): Promise<{ success: boolean }> {
  await delay(500);
  return { success: true };
}

// ========== Agent Tools & Execution ==========

export async function fetchAgentTools(): Promise<AgentTool[]> {
  await delay();
  return mockAgentTools;
}

export async function updateAgentTool(name: string, updates: Partial<AgentTool>): Promise<AgentTool> {
  await delay(300);
  const tool = mockAgentTools.find((t) => t.name === name);
  if (!tool) throw new Error(`Tool ${name} not found`);
  return { ...tool, ...updates };
}

export async function fetchWorkflowExecutions(): Promise<WorkflowExecution[]> {
  await delay();
  return mockWorkflowExecutions;
}

export async function fetchLatestExecution(): Promise<WorkflowExecution | null> {
  await delay(200);
  return mockWorkflowExecutions[0] || null;
}

// ========== Scheduler CRUD ==========

export async function createSchedulerJob(_job: JobFormData): Promise<SchedulerJob> {
  await delay(500);
  const newJob: SchedulerJob = {
    id: _job.id,
    name: _job.name,
    trigger: _job.trigger_type === 'cron'
      ? `cron[hour=${_job.cron_hour ?? 9}, minute=${_job.cron_minute ?? 30}]`
      : `interval[${_job.interval_hours ? _job.interval_hours + 'h' : _job.interval_minutes + 'm'}]`,
    next_run_time: new Date(Date.now() + 3600000).toISOString(),
    status: 'active',
    require_trading_day: _job.require_trading_day,
    require_market_open: _job.require_market_open,
  };
  mockSchedulerJobs.push(newJob);
  return newJob;
}

export async function deleteSchedulerJob(jobId: string): Promise<{ success: boolean }> {
  await delay(300);
  const idx = mockSchedulerJobs.findIndex((j) => j.id === jobId);
  if (idx >= 0) mockSchedulerJobs.splice(idx, 1);
  return { success: true };
}

export async function pauseSchedulerJob(jobId: string): Promise<SchedulerJob> {
  await delay(300);
  const job = mockSchedulerJobs.find((j) => j.id === jobId);
  if (!job) throw new Error(`Job ${jobId} not found`);
  job.status = 'paused';
  return job;
}

export async function resumeSchedulerJob(jobId: string): Promise<SchedulerJob> {
  await delay(300);
  const job = mockSchedulerJobs.find((j) => j.id === jobId);
  if (!job) throw new Error(`Job ${jobId} not found`);
  job.status = 'active';
  return job;
}

// ========== Rule Triggers ==========

export async function fetchRuleTriggers(): Promise<RuleTrigger[]> {
  await delay();
  return mockRuleTriggers;
}

export async function updateRuleTrigger(id: string, updates: Partial<RuleTrigger>): Promise<RuleTrigger> {
  await delay(300);
  const trigger = mockRuleTriggers.find((t) => t.id === id);
  if (!trigger) throw new Error(`Rule ${id} not found`);
  Object.assign(trigger, updates);
  return trigger;
}

// ========== Backtest ==========

export async function fetchBacktestResults(): Promise<BacktestResult[]> {
  await delay();
  return mockBacktestResults;
}

export async function runBacktest(_config: unknown): Promise<BacktestResult> {
  await delay(2000);
  return mockBacktestResults[0];
}
