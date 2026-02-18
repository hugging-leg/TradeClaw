import { useEffect, useState, useCallback, useRef } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { Card, CardHeader } from '@/components/ui/Card';
import { StatCard } from '@/components/ui/StatCard';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import {
  fetchBacktestResults,
  fetchBacktestDetail,
  submitBacktest,
  cancelBacktest,
  fetchWorkflows,
  exportAnalyses,
} from '@/api';
import type { AnalysisHistory } from '@/types';
import { useAuthStore } from '@/stores/auth';
import { formatCurrency, formatPercent, formatDate, formatDateTime } from '@/utils/format';
import {
  FlaskConical,
  Play,
  TrendingUp,
  TrendingDown,
  BarChart3,
  Target,
  Square,
  Loader2,
  RefreshCw,
  Activity,
  ChevronDown,
  ChevronUp,
  Download,
  FileJson,
  CheckCircle,
  XCircle,
  Wrench,
  Brain,
  Clock,
} from 'lucide-react';
import type { BacktestResult, BacktestStatistics, WorkflowInfo } from '@/types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

// ============================================================
// Backtest SSE Hook — subscribe to backtest_progress events
// ============================================================

function useBacktestSSE(onProgress: (data: {
  task_id: string;
  status: string;
  progress: number;
  current_date: string | null;
  equity_curve: { date: string; equity: number; cash: number; positions_value: number }[];
  latest_equity: { date: string; equity: number } | null;
  trades: { symbol: string; side: string; quantity: number; price: number; commission: number; timestamp: string; order_id: string }[];
  new_trades: { symbol: string; side: string; quantity: number; price: number; commission: number; timestamp: string; order_id: string }[];
  error: string | null;
  result: BacktestStatistics | null;
}) => void) {
  const token = useAuthStore((s) => s.token);

  useEffect(() => {
    const url = `${API_BASE_URL}/agent/events${token ? `?token=${token}` : ''}`;
    const es = new EventSource(url);

    es.addEventListener('backtest_progress', (e) => {
      try {
        const data = JSON.parse(e.data);
        onProgress(data);
      } catch { /* ignore parse errors */ }
    });

    es.onerror = () => {
      // SSE will auto-reconnect
    };

    return () => es.close();
  }, [token, onProgress]);
}

// ============================================================
// Config Form Component
// ============================================================

interface ConfigFormProps {
  workflows: Record<string, WorkflowInfo>;
  onSubmit: (config: {
    start_date: string;
    end_date: string;
    initial_capital: number;
    workflow_type: string;
    commission_rate: number;
    slippage_bps: number;
    run_interval_days: number;
  }) => void;
  isSubmitting: boolean;
}

function ConfigForm({ workflows, onSubmit, isSubmitting }: ConfigFormProps) {
  const [startDate, setStartDate] = useState('2025-01-01');
  const [endDate, setEndDate] = useState('2025-06-30');
  const [capital, setCapital] = useState(100000);
  const [workflowType, setWorkflowType] = useState('');
  const [commissionRate, setCommissionRate] = useState(0.001);
  const [slippageBps, setSlippageBps] = useState(5.0);
  const [runInterval, setRunInterval] = useState(1);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Set default workflow
  useEffect(() => {
    const keys = Object.keys(workflows);
    if (keys.length > 0 && !workflowType) {
      setWorkflowType(keys[0]);
    }
  }, [workflows, workflowType]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      start_date: startDate,
      end_date: endDate,
      initial_capital: capital,
      workflow_type: workflowType,
      commission_rate: commissionRate,
      slippage_bps: slippageBps,
      run_interval_days: runInterval,
    });
  };

  const inputClass =
    'w-full rounded-lg border border-border bg-input px-3 py-2 text-sm text-foreground outline-none focus:border-accent focus:ring-1 focus:ring-accent';

  return (
    <Card>
      <CardHeader title="Configure Backtest" subtitle="Set parameters for a new backtest run" />
      <form onSubmit={handleSubmit}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4 lg:gap-4">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted">Start Date</label>
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className={inputClass} />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted">End Date</label>
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className={inputClass} />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted">Initial Capital ($)</label>
            <input
              type="number"
              value={capital}
              onChange={(e) => setCapital(Number(e.target.value))}
              min={1000}
              step={1000}
              className={inputClass}
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted">Workflow</label>
            <select
              value={workflowType}
              onChange={(e) => setWorkflowType(e.target.value)}
              className={inputClass}
            >
              {Object.entries(workflows).map(([key, wf]) => (
                <option key={key} value={key}>
                  {wf.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Advanced Settings */}
        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="mt-3 flex items-center gap-1 text-xs text-muted hover:text-foreground transition-colors"
        >
          {showAdvanced ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          Advanced Settings
        </button>

        {showAdvanced && (
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted">
                Commission Rate
                <span className="ml-1 text-muted/60">({(commissionRate * 100).toFixed(2)}%)</span>
              </label>
              <input
                type="number"
                value={commissionRate}
                onChange={(e) => setCommissionRate(Number(e.target.value))}
                min={0}
                max={0.1}
                step={0.0001}
                className={inputClass}
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted">
                Slippage (bps)
                <span className="ml-1 text-muted/60">({slippageBps} bps = {(slippageBps / 100).toFixed(3)}%)</span>
              </label>
              <input
                type="number"
                value={slippageBps}
                onChange={(e) => setSlippageBps(Number(e.target.value))}
                min={0}
                max={100}
                step={0.5}
                className={inputClass}
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted">
                Run Interval (trading days)
              </label>
              <input
                type="number"
                value={runInterval}
                onChange={(e) => setRunInterval(Number(e.target.value))}
                min={1}
                max={30}
                step={1}
                className={inputClass}
              />
            </div>
          </div>
        )}

        <div className="mt-4 flex items-center gap-3">
          <Button
            type="submit"
            icon={isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            disabled={isSubmitting || !workflowType}
          >
            {isSubmitting ? 'Starting...' : 'Run Backtest'}
          </Button>
        </div>
      </form>
    </Card>
  );
}

// ============================================================
// Progress Bar Component
// ============================================================

function ProgressBar({ progress, status, currentDate }: {
  progress: number;
  status: string;
  currentDate: string | null;
}) {
  const pct = Math.round(progress * 100);
  const isRunning = status === 'running';

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted">
          {isRunning ? (
            <span className="flex items-center gap-1.5">
              <Loader2 className="h-3 w-3 animate-spin text-accent" />
              Running{currentDate ? ` — ${currentDate}` : ''}
            </span>
          ) : status === 'completed' ? (
            '✅ Completed'
          ) : status === 'failed' ? (
            '❌ Failed'
          ) : status === 'cancelled' ? (
            '⛔ Cancelled'
          ) : (
            'Pending'
          )}
        </span>
        <span className="font-mono text-foreground">{pct}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-surface-2">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            status === 'completed'
              ? 'bg-profit'
              : status === 'failed'
              ? 'bg-loss'
              : 'bg-accent'
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ============================================================
// Equity Chart Component
// ============================================================

function EquityChart({ data, initialCapital }: {
  data: { date: string; equity: number }[];
  initialCapital: number;
}) {
  if (!data || data.length < 2) {
    return (
      <div className="flex h-[300px] items-center justify-center text-sm text-muted">
        No equity data yet
      </div>
    );
  }

  const finalEquity = data[data.length - 1].equity;
  const isProfit = finalEquity >= initialCapital;
  const color = isProfit ? '#22c55e' : '#ef4444';
  const gradientId = `btGrad-${isProfit ? 'profit' : 'loss'}`;

  // 计算 Y 轴 domain：精确缩放以显示微小变化
  const equities = data.map((d) => d.equity);
  const minEq = Math.min(...equities);
  const maxEq = Math.max(...equities);
  const range = maxEq - minEq;
  // 添加 10% 的 padding，最小 padding 为 initialCapital 的 0.1%
  const padding = Math.max(range * 0.1, initialCapital * 0.001);
  const yDomain: [number, number] = [
    Math.floor(minEq - padding),
    Math.ceil(maxEq + padding),
  ];

  // 智能 Y 轴格式化：变化小时显示精确值，变化大时用 k 格式
  const yRange = yDomain[1] - yDomain[0];
  const formatYAxis = (v: number) => {
    if (yRange < 1000) {
      return `$${v.toLocaleString()}`;
    }
    return `$${(v / 1000).toFixed(1)}k`;
  };

  return (
    <div className="h-[300px] sm:h-[350px]">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.3} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 11, fill: '#71717a' }}
            axisLine={{ stroke: '#1e1e2e' }}
            tickLine={false}
            interval={Math.max(1, Math.floor(data.length / 8))}
          />
          <YAxis
            domain={yDomain}
            tick={{ fontSize: 11, fill: '#71717a' }}
            axisLine={false}
            tickLine={false}
            tickFormatter={formatYAxis}
            width={70}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#12121a',
              border: '1px solid #2a2a3e',
              borderRadius: '8px',
              fontSize: '12px',
              color: '#f0f0f5',
            }}
            labelStyle={{ color: '#a0a0b0' }}
            formatter={(value?: number) => [formatCurrency(value ?? 0), 'Equity']}
          />
          <Area type="monotone" dataKey="equity" stroke={color} strokeWidth={2} fill={`url(#${gradientId})`} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// ============================================================
// Trades Table Component
// ============================================================

function TradesTable({ trades }: { trades: BacktestResult['trades'] }) {
  const [showAll, setShowAll] = useState(false);
  if (!trades || trades.length === 0) {
    return <div className="py-4 text-center text-sm text-muted">No trades executed</div>;
  }

  const displayed = showAll ? trades : trades.slice(0, 20);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-border text-xs text-muted">
            <th className="px-3 py-2">Time</th>
            <th className="px-3 py-2">Symbol</th>
            <th className="px-3 py-2">Side</th>
            <th className="px-3 py-2 text-right">Qty</th>
            <th className="px-3 py-2 text-right">Price</th>
            <th className="px-3 py-2 text-right">Commission</th>
          </tr>
        </thead>
        <tbody>
          {displayed.map((t, i) => (
            <tr key={i} className="border-b border-border/50 hover:bg-surface-2/50">
              <td className="px-3 py-2 text-xs text-muted">{t.timestamp?.slice(0, 10) || '—'}</td>
              <td className="px-3 py-2 font-medium text-foreground">{t.symbol}</td>
              <td className="px-3 py-2">
                <Badge variant={t.side === 'buy' ? 'profit' : 'loss'} className="text-xs">
                  {t.side.toUpperCase()}
                </Badge>
              </td>
              <td className="px-3 py-2 text-right font-mono">{t.quantity}</td>
              <td className="px-3 py-2 text-right font-mono">${t.price?.toFixed(2)}</td>
              <td className="px-3 py-2 text-right font-mono text-muted">${t.commission?.toFixed(4)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {trades.length > 20 && (
        <button
          onClick={() => setShowAll(!showAll)}
          className="mt-2 w-full py-2 text-center text-xs text-accent hover:underline"
        >
          {showAll ? 'Show less' : `Show all ${trades.length} trades`}
        </button>
      )}
    </div>
  );
}

// ============================================================
// Analyses Panel Component
// ============================================================

function AnalysesPanel({ backtestId }: { backtestId: string }) {
  const [analyses, setAnalyses] = useState<AnalysisHistory[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 10;

  useEffect(() => {
    setLoading(true);
    setPage(0);
    exportAnalyses({ backtest_id: backtestId })
      .then(setAnalyses)
      .catch(() => setAnalyses([]))
      .finally(() => setLoading(false));
  }, [backtestId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-5 w-5 animate-spin text-accent" />
        <span className="ml-2 text-sm text-muted">Loading analyses…</span>
      </div>
    );
  }

  if (analyses.length === 0) {
    return (
      <div className="flex flex-col items-center py-12 text-center">
        <Brain className="mb-3 h-10 w-10 text-muted/30" />
        <p className="text-sm text-muted">No analysis records for this backtest</p>
      </div>
    );
  }

  const totalPages = Math.ceil(analyses.length / PAGE_SIZE);
  const displayed = analyses.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const formatDuration = (s: number) => {
    if (s < 1) return `${Math.round(s * 1000)}ms`;
    if (s < 60) return `${s.toFixed(1)}s`;
    return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
  };

  const getSimulatedDate = (a: AnalysisHistory) => {
    const ctx = a.input_context as Record<string, unknown> | null;
    return ctx?.simulated_date as string | undefined;
  };

  return (
    <div className="space-y-3">
      {/* Summary bar */}
      <div className="flex flex-wrap items-center gap-3 text-xs text-muted">
        <span>{analyses.length} analysis record(s)</span>
        <span>·</span>
        <span className="text-profit">
          {analyses.filter((a) => a.success).length} success
        </span>
        <span className="text-loss">
          {analyses.filter((a) => !a.success).length} failed
        </span>
        {analyses[0]?.execution_time_seconds && (
          <>
            <span>·</span>
            <span>
              Avg {formatDuration(
                analyses.reduce((s, a) => s + (a.execution_time_seconds || 0), 0) / analyses.length
              )}
            </span>
          </>
        )}
      </div>

      {/* Analysis cards */}
      {displayed.map((a) => {
        const isExpanded = expandedId === a.id;
        const simDate = getSimulatedDate(a);
        return (
          <div
            key={a.id}
            className="rounded-xl border border-border bg-card transition-colors hover:border-border-hover"
          >
            {/* Header — always visible */}
            <button
              onClick={() => setExpandedId(isExpanded ? null : a.id)}
              className="flex w-full items-center gap-3 px-4 py-3 text-left"
            >
              {a.success ? (
                <CheckCircle className="h-4 w-4 shrink-0 text-profit" />
              ) : (
                <XCircle className="h-4 w-4 shrink-0 text-loss" />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  {simDate && (
                    <span className="text-sm font-semibold text-foreground">Day {simDate}</span>
                  )}
                  {a.analysis_type && <Badge variant="info">{a.analysis_type}</Badge>}
                  <Badge variant={a.success ? 'profit' : 'loss'} className="text-[10px]">
                    {a.success ? 'OK' : 'FAIL'}
                  </Badge>
                </div>
                <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[11px] text-muted">
                  {a.execution_time_seconds != null && (
                    <span className="flex items-center gap-0.5">
                      <Clock className="h-3 w-3" />
                      {formatDuration(a.execution_time_seconds)}
                    </span>
                  )}
                  {a.tool_calls && a.tool_calls.length > 0 && (
                    <span className="flex items-center gap-0.5">
                      <Wrench className="h-3 w-3" />
                      {a.tool_calls.length} tools
                    </span>
                  )}
                  {a.trades_executed && a.trades_executed.length > 0 && (
                    <span className="text-accent font-medium">
                      {a.trades_executed.length} trade(s)
                    </span>
                  )}
                </div>
              </div>
              {isExpanded ? (
                <ChevronUp className="h-4 w-4 shrink-0 text-muted" />
              ) : (
                <ChevronDown className="h-4 w-4 shrink-0 text-muted" />
              )}
            </button>

            {/* Expanded detail */}
            {isExpanded && (
              <div className="border-t border-border px-4 py-3 space-y-3">
                {/* LLM Response */}
                {a.output_response && (
                  <div>
                    <p className="mb-1 text-[11px] font-medium text-muted">Agent Response</p>
                    <div className="max-h-64 overflow-y-auto rounded-lg bg-background p-3 text-xs leading-relaxed text-muted-foreground whitespace-pre-wrap">
                      {a.output_response}
                    </div>
                  </div>
                )}

                {/* Error */}
                {a.error_message && (
                  <div className="rounded-lg bg-loss/10 border border-loss/20 p-3 text-xs text-loss">
                    {a.error_message}
                  </div>
                )}

                {/* Tool calls */}
                {a.tool_calls && a.tool_calls.length > 0 && (
                  <div>
                    <p className="mb-1 text-[11px] font-medium text-muted">Tool Calls</p>
                    <div className="flex flex-wrap gap-1.5">
                      {a.tool_calls.map((tc, i) => {
                        let label: string;
                        if (typeof tc === 'string') {
                          label = tc;
                        } else if (tc && typeof tc === 'object' && 'name' in tc && typeof (tc as any).name === 'string') {
                          label = String((tc as any).name);
                        } else {
                          label = JSON.stringify(tc);
                        }
                        return (
                          <Badge key={i} variant="muted" className="text-[10px]">
                            {label}
                          </Badge>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Trades executed */}
                {a.trades_executed && a.trades_executed.length > 0 && (
                  <div>
                    <p className="mb-1 text-[11px] font-medium text-muted">Trades Executed</p>
                    <div className="space-y-1">
                      {a.trades_executed.map((t, i) => (
                        <div key={i} className="flex items-center gap-2 text-xs">
                          <Badge variant={(t.side as string) === 'buy' ? 'profit' : 'loss'} className="text-[10px]">
                            {(t.side as string)?.toUpperCase()}
                          </Badge>
                          <span className="font-medium text-foreground">{t.symbol as string}</span>
                          <span className="text-muted">qty {t.quantity as number}</span>
                          {t.price != null && (
                            <span className="text-muted">@ ${Number(t.price).toFixed(2)}</span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Metadata */}
                <div className="flex flex-wrap gap-3 text-[11px] text-muted pt-1 border-t border-border/50">
                  <span>ID: {a.id.slice(0, 8)}…</span>
                  {a.workflow_id && <span>Workflow: {a.workflow_id}</span>}
                </div>
              </div>
            )}
          </div>
        );
      })}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-2">
          <button
            onClick={() => setPage(Math.max(0, page - 1))}
            disabled={page === 0}
            className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted transition-colors hover:bg-surface-2 disabled:opacity-40"
          >
            ← Prev
          </button>
          <span className="text-xs text-muted">
            {page + 1} / {totalPages}
          </span>
          <button
            onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
            disabled={page >= totalPages - 1}
            className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted transition-colors hover:bg-surface-2 disabled:opacity-40"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}

// ============================================================
// Export Helpers
// ============================================================

function downloadFile(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function exportAsCSV(data: Record<string, unknown>[], filename: string) {
  if (data.length === 0) return;
  const headers = Object.keys(data[0]);
  const rows = data.map((row) =>
    headers.map((h) => {
      const v = row[h];
      const s = v == null ? '' : typeof v === 'object' ? JSON.stringify(v) : String(v);
      return `"${s.replace(/"/g, '""')}"`;
    }).join(',')
  );
  downloadFile('\uFEFF' + [headers.join(','), ...rows].join('\n'), filename, 'text/csv;charset=utf-8');
}

function exportAsJSON(data: unknown, filename: string) {
  downloadFile(JSON.stringify(data, null, 2), filename, 'application/json;charset=utf-8');
}

// ============================================================
// Main Page
// ============================================================

export default function Backtest() {
  const [results, setResults] = useState<BacktestResult[]>([]);
  const [workflows, setWorkflows] = useState<Record<string, WorkflowInfo>>({});
  const [selected, setSelected] = useState<BacktestResult | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState<'equity' | 'trades' | 'analyses' | 'config'>('equity');
  const [exportingId, setExportingId] = useState<string | null>(null);

  // Keep a ref for SSE updates
  const resultsRef = useRef(results);
  resultsRef.current = results;
  const selectedRef = useRef(selected);
  selectedRef.current = selected;

  // Load data
  const loadData = useCallback(async () => {
    try {
      const [r, w] = await Promise.all([fetchBacktestResults(), fetchWorkflows()]);
      setResults(r);
      setWorkflows(w);
      if (r.length > 0 && !selectedRef.current) {
        setSelected(r[0]);
      }
    } catch (e) {
      console.error('Failed to load backtest data:', e);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  // SSE progress updates
  const handleProgress = useCallback((data: {
    task_id: string;
    status: string;
    progress: number;
    current_date: string | null;
    equity_curve: { date: string; equity: number; cash: number; positions_value: number }[];
    latest_equity: { date: string; equity: number } | null;
    trades: { symbol: string; side: string; quantity: number; price: number; commission: number; timestamp: string; order_id: string }[];
    new_trades: { symbol: string; side: string; quantity: number; price: number; commission: number; timestamp: string; order_id: string }[];
    error: string | null;
    result: BacktestStatistics | null;
  }) => {
    const updateTask = (task: BacktestResult): BacktestResult => {
      const updated = { ...task };
      updated.status = data.status as BacktestResult['status'];
      updated.progress = data.progress;
      updated.current_date = data.current_date;
      updated.error = data.error;

      // 使用完整 equity_curve（后端推送的是完整数据）
      if (data.equity_curve && data.equity_curve.length > 0) {
        updated.equity_curve = data.equity_curve;
      }

      // 使用完整 trades 列表
      if (data.trades && data.trades.length > 0) {
        updated.trades = data.trades;
      }

      // 完成时更新统计
      if (data.result) {
        updated.result = data.result;
      }

      return updated;
    };

    setResults((prev) => {
      const idx = prev.findIndex((r) => r.id === data.task_id);
      if (idx === -1) return prev;
      const updated = [...prev];
      updated[idx] = updateTask(updated[idx]);
      return updated;
    });

    // If the selected task is being updated, refresh selected too
    setSelected((prev) => {
      if (!prev || prev.id !== data.task_id) return prev;
      return updateTask(prev);
    });

    // When completed, fetch full detail for final persistence data
    if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
      fetchBacktestDetail(data.task_id).then((detail) => {
        setResults((prev) => prev.map((r) => (r.id === data.task_id ? detail : r)));
        setSelected((prev) => (prev?.id === data.task_id ? detail : prev));
      }).catch(() => {});
    }
  }, []);

  useBacktestSSE(handleProgress);

  // Submit backtest
  const handleSubmit = async (config: Parameters<typeof submitBacktest>[0]) => {
    setIsSubmitting(true);
    try {
      const task = await submitBacktest(config);
      setResults((prev) => [task, ...prev]);
      setSelected(task);
    } catch (e) {
      console.error('Failed to submit backtest:', e);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Cancel backtest
  const handleCancel = async (taskId: string) => {
    try {
      await cancelBacktest(taskId);
    } catch (e) {
      console.error('Failed to cancel backtest:', e);
    }
  };

  // Export analyses for a specific backtest
  const handleExport = async (backtestId: string, format: 'csv' | 'json') => {
    setExportingId(backtestId);
    try {
      const data = await exportAnalyses({ backtest_id: backtestId });
      const bt = results.find((r) => r.id === backtestId);
      const label = bt ? `${bt.config.workflow_type}_${bt.config.start_date}_${bt.config.end_date}` : backtestId.slice(0, 8);
      if (format === 'csv') {
        exportAsCSV(data as unknown as Record<string, unknown>[], `backtest_${label}.csv`);
      } else {
        exportAsJSON(data, `backtest_${label}.json`);
      }
    } catch (e) {
      console.error('Export failed:', e);
    } finally {
      setExportingId(null);
    }
  };

  // Helpers
  const stats: BacktestStatistics | null = selected?.result ?? null;
  const isRunning = selected?.status === 'running';

  return (
    <div className="animate-fade-in space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Backtest</h1>
          <p className="mt-1 text-sm text-muted">Test strategies against historical data</p>
        </div>
        <Button
          variant="secondary"
          icon={<RefreshCw className="h-4 w-4" />}
          onClick={loadData}
        >
          Refresh
        </Button>
      </div>

      {/* Config Form */}
      <ConfigForm workflows={workflows} onSubmit={handleSubmit} isSubmitting={isSubmitting} />

      {/* Selected Backtest Detail */}
      {selected && (
        <>
          {/* Progress Bar (if running) */}
          {(selected.status === 'running' || selected.status === 'pending') && (
            <Card>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <CardHeader
                  title={`Backtest ${selected.id.slice(0, 8)}…`}
                  subtitle={`${selected.config.workflow_type} — ${selected.config.start_date} → ${selected.config.end_date}`}
                />
                {isRunning && (
                  <Button
                    variant="danger"
                    size="sm"
                    icon={<Square className="h-3 w-3" />}
                    onClick={() => handleCancel(selected.id)}
                  >
                    Cancel
                  </Button>
                )}
              </div>
              <ProgressBar
                progress={selected.progress}
                status={selected.status}
                currentDate={selected.current_date}
              />
            </Card>
          )}

          {/* Stats */}
          {stats && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-6 md:gap-4">
              <StatCard
                label="Total Return"
                value={formatPercent(stats.total_return * 100)}
                changeType={stats.total_return >= 0 ? 'profit' : 'loss'}
                icon={<TrendingUp className="h-4 w-4" />}
              />
              <StatCard
                label="Annualized"
                value={formatPercent(stats.annualized_return * 100)}
                changeType={stats.annualized_return >= 0 ? 'profit' : 'loss'}
                icon={<Activity className="h-4 w-4" />}
              />
              <StatCard
                label="Sharpe Ratio"
                value={stats.sharpe_ratio.toFixed(2)}
                icon={<Target className="h-4 w-4" />}
              />
              <StatCard
                label="Max Drawdown"
                value={formatPercent(stats.max_drawdown * 100)}
                changeType="loss"
                icon={<TrendingDown className="h-4 w-4" />}
              />
              <StatCard
                label="Win Rate"
                value={formatPercent(stats.win_rate * 100, 1)}
                icon={<BarChart3 className="h-4 w-4" />}
              />
              <StatCard
                label="Trades"
                value={String(stats.total_trades)}
                icon={<FlaskConical className="h-4 w-4" />}
              />
            </div>
          )}

          {/* Tabs + Export */}
          <div className="-mx-4 overflow-x-auto px-4 pb-0 md:mx-0 md:px-0">
            <div className="flex items-center justify-between border-b border-border">
              <div className="flex gap-1">
                {(['equity', 'trades', 'analyses', 'config'] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
                      activeTab === tab
                        ? 'border-accent text-accent'
                        : 'border-transparent text-muted hover:text-foreground'
                    }`}
                  >
                    {tab === 'equity' ? 'Equity Curve' : tab === 'trades' ? `Trades (${selected.trades?.length || 0})` : tab === 'analyses' ? 'Analyses' : 'Configuration'}
                  </button>
                ))}
              </div>
              {selected.status === 'completed' && (
                <div className="flex items-center gap-1 pb-1">
                  <button
                    onClick={(e) => { e.stopPropagation(); handleExport(selected.id, 'csv'); }}
                    disabled={exportingId === selected.id}
                    className="flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-surface-2 hover:text-foreground disabled:opacity-50"
                    title="Export analyses as CSV"
                  >
                    {exportingId === selected.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                    <span className="hidden sm:inline">CSV</span>
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleExport(selected.id, 'json'); }}
                    disabled={exportingId === selected.id}
                    className="flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-surface-2 hover:text-foreground disabled:opacity-50"
                    title="Export analyses as JSON"
                  >
                    <FileJson className="h-3.5 w-3.5" />
                    <span className="hidden sm:inline">JSON</span>
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Tab Content */}
          {activeTab === 'equity' && (
            <Card>
              <CardHeader
                title="Equity Curve"
                subtitle={`${formatDate(selected.config.start_date)} — ${formatDate(selected.config.end_date)}`}
                action={
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="info">{selected.config.workflow_type}</Badge>
                    <Badge
                      variant={
                        selected.status === 'completed'
                          ? 'profit'
                          : selected.status === 'running'
                          ? 'warning'
                          : selected.status === 'failed'
                          ? 'loss'
                          : 'muted'
                      }
                    >
                      {selected.status}
                    </Badge>
                    {stats && (
                      <span className="text-sm font-semibold text-foreground">
                        {formatCurrency(stats.final_equity)}
                      </span>
                    )}
                  </div>
                }
              />
              <EquityChart
                data={selected.equity_curve || []}
                initialCapital={selected.config.initial_capital}
              />
            </Card>
          )}

          {activeTab === 'trades' && (
            <Card>
              <CardHeader title="Trade History" subtitle={`${selected.trades?.length || 0} trades executed`} />
              <TradesTable trades={selected.trades || []} />
            </Card>
          )}

          {activeTab === 'analyses' && (
            <Card>
              <CardHeader
                title="Agent Analyses"
                subtitle="LLM analysis records for each simulated trading day"
              />
              <AnalysesPanel backtestId={selected.id} />
            </Card>
          )}

          {activeTab === 'config' && (
            <Card>
              <CardHeader title="Backtest Configuration" />
              <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
                <div>
                  <span className="text-muted">Period</span>
                  <div className="mt-1 text-foreground">
                    {formatDate(selected.config.start_date)} → {formatDate(selected.config.end_date)}
                  </div>
                </div>
                <div>
                  <span className="text-muted">Initial Capital</span>
                  <div className="mt-1 text-foreground">{formatCurrency(selected.config.initial_capital)}</div>
                </div>
                <div>
                  <span className="text-muted">Commission Rate</span>
                  <div className="mt-1 text-foreground">{(selected.config.commission_rate * 100).toFixed(2)}%</div>
                </div>
                <div>
                  <span className="text-muted">Slippage</span>
                  <div className="mt-1 text-foreground">{selected.config.slippage_bps} bps</div>
                </div>
                <div>
                  <span className="text-muted">Workflow</span>
                  <div className="mt-1 text-foreground">{selected.config.workflow_type}</div>
                </div>
                <div>
                  <span className="text-muted">Run Interval</span>
                  <div className="mt-1 text-foreground">Every {selected.config.run_interval_days} trading day(s)</div>
                </div>
                {stats && (
                  <>
                    <div>
                      <span className="text-muted">Profit Factor</span>
                      <div className="mt-1 text-foreground">{stats.profit_factor?.toFixed(2) || '—'}</div>
                    </div>
                    <div>
                      <span className="text-muted">Avg Trade P&L</span>
                      <div className="mt-1 text-foreground">{formatCurrency(stats.avg_trade_pnl || 0)}</div>
                    </div>
                  </>
                )}
              </div>
              {selected.error && (
                <div className="mt-4 rounded-lg border border-loss/30 bg-loss/10 p-3 text-sm text-loss">
                  {selected.error}
                </div>
              )}
            </Card>
          )}
        </>
      )}

      {/* Previous Runs */}
      {results.length > 0 && (
        <Card>
          <CardHeader title="All Runs" subtitle={`${results.length} backtest(s)`} />
          <div className="space-y-2">
            {results.map((r) => {
              const rStats = r.result;
              const totalReturn = rStats?.total_return ?? r.total_return ?? 0;
              return (
                <div
                  key={r.id}
                  onClick={() => setSelected(r)}
                  className={`flex cursor-pointer flex-col gap-2 rounded-lg border p-3 transition-colors sm:flex-row sm:items-center sm:justify-between ${
                    selected?.id === r.id
                      ? 'border-accent bg-accent/5'
                      : 'border-border hover:border-border-hover'
                  }`}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <FlaskConical className="h-4 w-4 shrink-0 text-accent" />
                    <div className="min-w-0">
                      <div className="truncate text-sm font-semibold text-foreground">
                        {r.config.workflow_type} — <span className="text-xs font-normal text-muted">{r.id}</span>
                      </div>
                      <div className="text-xs text-muted">
                        {formatDate(r.config.start_date)} → {formatDate(r.config.end_date)}
                        {r.started_at && <span className="hidden sm:inline"> • Started {formatDateTime(r.started_at)}</span>}
                      </div>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {r.status === 'running' && (
                      <div className="flex items-center gap-1 text-xs text-muted">
                        <Loader2 className="h-3 w-3 animate-spin" />
                        {Math.round((r.progress || 0) * 100)}%
                      </div>
                    )}
                    {r.status === 'completed' && (
                      <>
                        <span
                          className={
                            totalReturn >= 0
                              ? 'text-sm font-semibold text-profit'
                              : 'text-sm font-semibold text-loss'
                          }
                        >
                          {formatPercent(totalReturn * 100)}
                        </span>
                        <button
                          onClick={(e) => { e.stopPropagation(); handleExport(r.id, 'csv'); }}
                          disabled={exportingId === r.id}
                          className="rounded-md p-1.5 text-muted transition-colors hover:bg-surface-2 hover:text-foreground disabled:opacity-50"
                          title="Export analyses (CSV)"
                        >
                          {exportingId === r.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                        </button>
                      </>
                    )}
                    <Badge
                      variant={
                        r.status === 'completed'
                          ? 'profit'
                          : r.status === 'running'
                          ? 'warning'
                          : r.status === 'failed'
                          ? 'loss'
                          : 'muted'
                      }
                    >
                      {r.status}
                    </Badge>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* Empty State */}
      {results.length === 0 && !isSubmitting && (
        <Card>
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <FlaskConical className="mb-4 h-12 w-12 text-muted/30" />
            <h3 className="text-lg font-semibold text-foreground">No backtests yet</h3>
            <p className="mt-1 text-sm text-muted">
              Configure and run your first backtest above to see results here.
            </p>
          </div>
        </Card>
      )}
    </div>
  );
}
