import { useEffect, useState } from 'react';
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
import { fetchBacktestResults, fetchWorkflows } from '@/api';
import { formatCurrency, formatPercent, formatDate } from '@/utils/format';
import {
  FlaskConical,
  Play,
  TrendingUp,
  TrendingDown,
  BarChart3,
  Target,
} from 'lucide-react';
import type { BacktestResult, WorkflowInfo } from '@/types';

export default function Backtest() {
  const [results, setResults] = useState<BacktestResult[]>([]);
  const [workflows, setWorkflows] = useState<Record<string, WorkflowInfo>>({});
  const [selected, setSelected] = useState<BacktestResult | null>(null);

  useEffect(() => {
    Promise.all([fetchBacktestResults(), fetchWorkflows()]).then(([r, w]) => {
      setResults(r);
      setWorkflows(w);
      if (r.length > 0) setSelected(r[0]);
    });
  }, []);

  return (
    <div className="animate-fade-in space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Backtest</h1>
          <p className="mt-1 text-sm text-muted">Test strategies against historical data</p>
        </div>
        <Button icon={<Play className="h-4 w-4" />} disabled>
          New Backtest
          <Badge variant="muted" className="ml-2">Coming Soon</Badge>
        </Button>
      </div>

      {/* Backtest Config Form (placeholder) */}
      <Card>
        <CardHeader title="Configure Backtest" subtitle="Set parameters for a new backtest run" />
        <div className="grid grid-cols-4 gap-4">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted">Start Date</label>
            <input
              type="date"
              defaultValue="2025-01-01"
              className="w-full rounded-lg border border-border bg-input px-3 py-2 text-sm text-foreground outline-none focus:border-accent"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted">End Date</label>
            <input
              type="date"
              defaultValue="2025-06-30"
              className="w-full rounded-lg border border-border bg-input px-3 py-2 text-sm text-foreground outline-none focus:border-accent"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted">Initial Capital</label>
            <input
              type="number"
              defaultValue={100000}
              className="w-full rounded-lg border border-border bg-input px-3 py-2 text-sm text-foreground outline-none focus:border-accent"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted">Workflow</label>
            <select className="w-full rounded-lg border border-border bg-input px-3 py-2 text-sm text-foreground outline-none focus:border-accent">
              {Object.entries(workflows).map(([key, wf]) => (
                <option key={key} value={key}>
                  {wf.name}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="mt-4">
          <label className="mb-1.5 block text-xs font-medium text-muted">Symbols (comma-separated)</label>
          <input
            type="text"
            defaultValue="AAPL, MSFT, GOOGL, NVDA, AMZN"
            className="w-full rounded-lg border border-border bg-input px-3 py-2 text-sm text-foreground outline-none focus:border-accent"
          />
        </div>
      </Card>

      {/* Results */}
      {selected && (
        <>
          {/* Stats */}
          <div className="grid grid-cols-5 gap-4">
            <StatCard
              label="Total Return"
              value={formatPercent(selected.total_return)}
              changeType={selected.total_return >= 0 ? 'profit' : 'loss'}
              icon={<TrendingUp className="h-4 w-4" />}
            />
            <StatCard
              label="Sharpe Ratio"
              value={selected.sharpe_ratio.toFixed(2)}
              icon={<Target className="h-4 w-4" />}
            />
            <StatCard
              label="Max Drawdown"
              value={formatPercent(selected.max_drawdown)}
              changeType="loss"
              icon={<TrendingDown className="h-4 w-4" />}
            />
            <StatCard
              label="Win Rate"
              value={formatPercent(selected.win_rate, 1)}
              icon={<BarChart3 className="h-4 w-4" />}
            />
            <StatCard
              label="Total Trades"
              value={String(selected.total_trades)}
              icon={<FlaskConical className="h-4 w-4" />}
            />
          </div>

          {/* Equity Curve */}
          <Card>
            <CardHeader
              title="Equity Curve"
              subtitle={`${formatDate(selected.config.start_date)} — ${formatDate(selected.config.end_date)}`}
              action={
                <div className="flex items-center gap-2">
                  <Badge variant="info">{selected.config.workflow_type}</Badge>
                  <Badge variant="profit">{selected.status}</Badge>
                </div>
              }
            />
            <div className="h-[350px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={selected.equity_curve} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="btGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#22c55e" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="#22c55e" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11, fill: '#71717a' }}
                    axisLine={{ stroke: '#1e1e2e' }}
                    tickLine={false}
                    interval={Math.floor(selected.equity_curve.length / 8)}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: '#71717a' }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#12121a',
                      border: '1px solid #1e1e2e',
                      borderRadius: '8px',
                      fontSize: '12px',
                      color: '#f0f0f5',
                    }}
                    formatter={(value: number | undefined) => [formatCurrency(value ?? 0), 'Equity']}
                  />
                  <Area
                    type="monotone"
                    dataKey="equity"
                    stroke="#22c55e"
                    strokeWidth={2}
                    fill="url(#btGrad)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Card>

          {/* Backtest Info */}
          <Card>
            <CardHeader title="Backtest Configuration" />
            <div className="grid grid-cols-3 gap-4 text-sm">
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
                <span className="text-muted">Symbols</span>
                <div className="mt-1 flex flex-wrap gap-1">
                  {selected.config.symbols.map((s) => (
                    <Badge key={s} variant="muted">{s}</Badge>
                  ))}
                </div>
              </div>
            </div>
          </Card>
        </>
      )}

      {/* Previous Runs */}
      {results.length > 0 && (
        <Card>
          <CardHeader title="Previous Runs" subtitle={`${results.length} backtest(s)`} />
          <div className="space-y-2">
            {results.map((r) => (
              <div
                key={r.id}
                onClick={() => setSelected(r)}
                className="flex cursor-pointer items-center justify-between rounded-lg border border-border p-3 transition-colors hover:border-border-hover"
              >
                <div className="flex items-center gap-3">
                  <FlaskConical className="h-4 w-4 text-accent" />
                  <div>
                    <div className="text-sm font-semibold text-foreground">
                      {r.config.workflow_type} — {r.config.symbols.join(', ')}
                    </div>
                    <div className="text-xs text-muted">
                      {formatDate(r.config.start_date)} → {formatDate(r.config.end_date)}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className={r.total_return >= 0 ? 'text-sm font-semibold text-profit' : 'text-sm font-semibold text-loss'}>
                    {formatPercent(r.total_return)}
                  </span>
                  <Badge variant={r.status === 'completed' ? 'profit' : r.status === 'running' ? 'warning' : 'loss'}>
                    {r.status}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
