import { useEffect, useState } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import {
  DollarSign,
  Wallet,
  TrendingUp,
  BarChart3,
  CheckCircle,
  XCircle,
  Clock,
} from 'lucide-react';
import { Card, CardHeader } from '@/components/ui/Card';
import { StatCard } from '@/components/ui/StatCard';
import { Badge } from '@/components/ui/Badge';
import { StatusDot } from '@/components/ui/StatusDot';
import { fetchPortfolio, fetchPortfolioHistory, fetchSystemStatus, fetchAnalyses } from '@/api';
import { formatCurrency, formatPercent, formatRelative, formatDate } from '@/utils/format';
import { cn } from '@/utils/cn';
import type { Portfolio, PortfolioSnapshot, SystemStatus, AnalysisHistory } from '@/types';

const CHART_COLORS = ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#3b82f6', '#8b5cf6'];

export default function Dashboard() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [snapshots, setSnapshots] = useState<PortfolioSnapshot[]>([]);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [analyses, setAnalyses] = useState<AnalysisHistory[]>([]);

  useEffect(() => {
    // 各请求独立 catch，避免一个失败导致全部丢失
    fetchPortfolio().then(setPortfolio).catch(() => {});
    fetchPortfolioHistory(30).then(setSnapshots).catch(() => {});
    fetchSystemStatus().then(setStatus).catch(() => {});
    fetchAnalyses(5).then(setAnalyses).catch(() => {});
  }, []);

  if (!portfolio || !status) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      </div>
    );
  }

  const totalReturn = portfolio.equity > 0
    ? ((portfolio.total_pnl / (portfolio.equity - portfolio.total_pnl)) * 100)
    : 0;

  const dayReturn = portfolio.equity > 0
    ? ((portfolio.day_pnl / (portfolio.equity - portfolio.day_pnl)) * 100)
    : 0;

  const chartData = snapshots
    .filter((s) => s.equity != null)
    .map((s) => ({
      date: formatDate(s.timestamp),
      value: s.equity!,
    }));

  const pieData = portfolio.positions.map((p) => ({
    name: p.symbol,
    value: p.market_value,
  }));

  // Add cash as a slice
  pieData.push({ name: 'Cash', value: portfolio.cash });

  return (
    <div className="animate-fade-in space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Dashboard</h1>
          <p className="mt-1 text-sm text-muted">Portfolio overview and system status</p>
        </div>
        <div className="flex items-center gap-3">
          <StatusDot
            status={status.is_running ? 'online' : 'offline'}
            label={status.is_running ? 'System Running' : 'System Stopped'}
          />
          <Badge variant={status.market_open ? 'profit' : 'muted'} dot>
            {status.market_open ? 'Market Open' : 'Market Closed'}
          </Badge>
        </div>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard
          label="Total Equity"
          value={formatCurrency(portfolio.equity)}
          change={formatPercent(totalReturn)}
          changeType={totalReturn >= 0 ? 'profit' : 'loss'}
          icon={<DollarSign className="h-4 w-4" />}
        />
        <StatCard
          label="Day P&L"
          value={formatCurrency(portfolio.day_pnl)}
          change={formatPercent(dayReturn)}
          changeType={portfolio.day_pnl >= 0 ? 'profit' : 'loss'}
          icon={<TrendingUp className="h-4 w-4" />}
        />
        <StatCard
          label="Cash Available"
          value={formatCurrency(portfolio.cash)}
          icon={<Wallet className="h-4 w-4" />}
        />
        <StatCard
          label="Positions"
          value={String(portfolio.positions.length)}
          change={`${portfolio.day_trade_count} day trades`}
          icon={<BarChart3 className="h-4 w-4" />}
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-3 gap-4">
        {/* Equity Curve */}
        <Card className="col-span-2">
          <CardHeader title="Portfolio Value" subtitle="Last 30 days" />
          <div className="h-[280px]">
            {chartData.length === 0 ? (
              <div className="flex h-full items-center justify-center text-sm text-muted">
                No portfolio history data available
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#6366f1" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="#6366f1" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11, fill: '#71717a' }}
                    axisLine={{ stroke: '#1e1e2e' }}
                    tickLine={false}
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
                      border: '1px solid #2a2a3e',
                      borderRadius: '8px',
                      fontSize: '12px',
                      color: '#f0f0f5',
                    }}
                    labelStyle={{ color: '#a0a0b0' }}
                    itemStyle={{ color: '#e0e0e8' }}
                    formatter={(value: number | undefined) => [formatCurrency(value ?? 0), 'Value']}
                  />
                  <Area
                    type="monotone"
                    dataKey="value"
                    stroke="#6366f1"
                    strokeWidth={2}
                    fill="url(#colorValue)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>

        {/* Allocation Pie */}
        <Card>
          <CardHeader title="Allocation" subtitle="Current portfolio" />
          <div className="h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={80}
                  paddingAngle={3}
                  dataKey="value"
                  stroke="none"
                >
                  {pieData.map((_, idx) => (
                    <Cell key={idx} fill={CHART_COLORS[idx % CHART_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#12121a',
                    border: '1px solid #2a2a3e',
                    borderRadius: '8px',
                    fontSize: '12px',
                    color: '#f0f0f5',
                  }}
                  itemStyle={{ color: '#e0e0e8' }}
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  formatter={(value: any, _name: any, entry: any) => {
                    const label = entry?.payload?.name ?? '';
                    return [formatCurrency(Number(value) || 0), label];
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          {/* Legend */}
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5">
            {pieData.map((item, idx) => (
              <div key={item.name} className="flex items-center gap-1.5">
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ backgroundColor: CHART_COLORS[idx % CHART_COLORS.length] }}
                />
                <span className="text-xs text-muted-foreground">{item.name}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Bottom Row */}
      <div className="grid grid-cols-2 gap-4">
        {/* Recent Analyses */}
        <Card>
          <CardHeader title="Recent Analyses" subtitle="AI workflow executions" />
          <div className="space-y-3">
            {analyses.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted">No analyses yet</p>
            ) : (
              analyses.map((a) => (
                <div
                  key={a.id}
                  className="flex items-start gap-3 rounded-lg border border-border p-3 transition-colors hover:border-border-hover"
                >
                  <div
                    className={cn(
                      'mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg',
                      a.success ? 'bg-profit-bg' : 'bg-loss-bg'
                    )}
                  >
                    {a.success ? (
                      <CheckCircle className="h-3.5 w-3.5 text-profit" />
                    ) : (
                      <XCircle className="h-3.5 w-3.5 text-loss" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-foreground capitalize">
                        {a.trigger.replace(/_/g, ' ')}
                      </span>
                      <Badge variant={a.success ? 'profit' : 'loss'}>
                        {a.success ? 'SUCCESS' : 'FAILED'}
                      </Badge>
                      <span className="ml-auto text-xs text-muted">{formatRelative(a.created_at)}</span>
                    </div>
                    {a.output_response && (
                      <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                        {a.output_response.slice(0, 200)}
                      </p>
                    )}
                    {a.error_message && (
                      <p className="mt-1 line-clamp-2 text-xs text-loss">{a.error_message}</p>
                    )}
                    <div className="mt-1.5 flex items-center gap-3">
                      {a.tool_calls && a.tool_calls.length > 0 && (
                        <span className="text-xs text-muted">
                          Tools: <span className="text-foreground">{a.tool_calls.length}</span>
                        </span>
                      )}
                      {a.execution_time_seconds != null && (
                        <span className="flex items-center gap-1 text-xs text-muted">
                          <Clock className="h-3 w-3" />
                          <span className="text-foreground">{a.execution_time_seconds.toFixed(1)}s</span>
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>

        {/* Positions Table */}
        <Card>
          <CardHeader title="Positions" subtitle="Current holdings" />
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="pb-2 text-xs font-medium text-muted">Symbol</th>
                  <th className="pb-2 text-right text-xs font-medium text-muted">Qty</th>
                  <th className="pb-2 text-right text-xs font-medium text-muted">Price</th>
                  <th className="pb-2 text-right text-xs font-medium text-muted">Value</th>
                  <th className="pb-2 text-right text-xs font-medium text-muted">P&L</th>
                </tr>
              </thead>
              <tbody>
                {portfolio.positions.map((pos) => (
                  <tr key={pos.symbol} className="border-b border-border/50 last:border-0">
                    <td className="py-2.5 text-sm font-semibold text-foreground">{pos.symbol}</td>
                    <td className="py-2.5 text-right text-sm text-muted-foreground">{pos.quantity}</td>
                    <td className="py-2.5 text-right text-sm text-muted-foreground">
                      {formatCurrency(pos.current_price)}
                    </td>
                    <td className="py-2.5 text-right text-sm text-foreground">
                      {formatCurrency(pos.market_value)}
                    </td>
                    <td
                      className={cn(
                        'py-2.5 text-right text-sm font-medium',
                        pos.unrealized_pnl >= 0 ? 'text-profit' : 'text-loss'
                      )}
                    >
                      {formatPercent(pos.unrealized_pnl_percentage)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
}
