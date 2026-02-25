import { useEffect, useState } from 'react';
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Treemap,
} from 'recharts';
import { Card, CardHeader } from '@/components/ui/Card';
import { StatCard } from '@/components/ui/StatCard';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { fetchPortfolio, fetchPortfolioHistory } from '@/api';
import { formatCurrency, formatPercent, formatDate } from '@/utils/format';
import { cn } from '@/utils/cn';
import { DollarSign, TrendingUp, PieChart, Layers } from 'lucide-react';
import type { Portfolio as PortfolioType, PortfolioSnapshot } from '@/types';

const TREEMAP_COLORS = ['#6366f1', '#22c55e', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

type TimeRange = '7d' | '30d' | '90d';

export default function Portfolio() {
  const [portfolio, setPortfolio] = useState<PortfolioType | null>(null);
  const [snapshots, setSnapshots] = useState<PortfolioSnapshot[]>([]);
  const [range, setRange] = useState<TimeRange>('30d');

  useEffect(() => {
    fetchPortfolio().then(setPortfolio).catch(() => {});
  }, []);

  useEffect(() => {
    const days = range === '7d' ? 7 : range === '30d' ? 30 : 90;
    fetchPortfolioHistory(days).then(setSnapshots).catch(() => {});
  }, [range]);

  if (!portfolio) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      </div>
    );
  }

  const equityData = snapshots
    .filter((s) => s.equity != null)
    .map((s) => ({
      date: formatDate(s.timestamp),
      value: s.equity!,
    }));

  // Smart Y-axis domain: zoom into actual data range so fluctuations are visible
  const equityYDomain: [number, number] | undefined = (() => {
    if (equityData.length === 0) return undefined;
    const vals = equityData.map((d) => d.value);
    const minV = Math.min(...vals);
    const maxV = Math.max(...vals);
    const range = maxV - minV;
    const padding = Math.max(range * 0.1, maxV * 0.001);
    return [Math.floor(minV - padding), Math.ceil(maxV + padding)];
  })();

  const pnlData = snapshots
    .filter((s) => s.profit_loss != null)
    .map((s) => ({
      date: formatDate(s.timestamp),
      pnl: s.profit_loss!,
    }));

  const treemapData = portfolio.positions.map((p, i) => ({
    name: p.symbol,
    size: p.market_value,
    pnl: p.unrealized_pnl_percentage,
    fill: TREEMAP_COLORS[i % TREEMAP_COLORS.length],
  }));

  const totalUnrealizedPnl = portfolio.positions.reduce((sum, p) => sum + p.unrealized_pnl, 0);

  return (
    <div className="animate-fade-in space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Portfolio</h1>
        <p className="mt-1 text-sm text-muted">Position details and performance history</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
        <StatCard
          label="Total Equity"
          value={formatCurrency(portfolio.equity)}
          icon={<DollarSign className="h-4 w-4" />}
        />
        <StatCard
          label="Market Value"
          value={formatCurrency(portfolio.market_value)}
          icon={<Layers className="h-4 w-4" />}
        />
        <StatCard
          label="Unrealized P&L"
          value={formatCurrency(totalUnrealizedPnl)}
          changeType={totalUnrealizedPnl >= 0 ? 'profit' : 'loss'}
          change={formatPercent(
            portfolio.market_value > 0
              ? (totalUnrealizedPnl / (portfolio.market_value - totalUnrealizedPnl)) * 100
              : 0
          )}
          icon={<TrendingUp className="h-4 w-4" />}
        />
        <StatCard
          label="Buying Power"
          value={formatCurrency(portfolio.buying_power)}
          icon={<PieChart className="h-4 w-4" />}
        />
      </div>

      {/* Equity Curve + Day P&L */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Equity Curve"
            action={
              <div className="flex gap-1">
                {(['7d', '30d', '90d'] as TimeRange[]).map((r) => (
                  <Button
                    key={r}
                    variant={range === r ? 'primary' : 'ghost'}
                    size="sm"
                    onClick={() => setRange(r)}
                  >
                    {r}
                  </Button>
                ))}
              </div>
            }
          />
          <div className="h-[260px]">
            {equityData.length === 0 ? (
              <div className="flex h-full items-center justify-center text-sm text-muted">
                No equity history available
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={equityData} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#6366f1" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="#6366f1" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
                  <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#71717a' }} axisLine={{ stroke: '#1e1e2e' }} tickLine={false} />
                  <YAxis domain={equityYDomain} tick={{ fontSize: 11, fill: '#71717a' }} axisLine={false} tickLine={false} tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#12121a', border: '1px solid #2a2a3e', borderRadius: '8px', fontSize: '12px', color: '#f0f0f5' }}
                    labelStyle={{ color: '#a0a0b0' }}
                    itemStyle={{ color: '#e0e0e8' }}
                    formatter={(value: number | undefined) => [formatCurrency(value ?? 0), 'Equity']}
                  />
                  <Area type="monotone" dataKey="value" stroke="#6366f1" strokeWidth={2} fill="url(#eqGrad)" />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title="Daily P&L" subtitle="Profit/Loss by day" />
          <div className="h-[260px]">
            {pnlData.length === 0 ? (
              <div className="flex h-full items-center justify-center text-sm text-muted">
                No P&L history available
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={pnlData} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
                  <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#71717a' }} axisLine={{ stroke: '#1e1e2e' }} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: '#71717a' }} axisLine={false} tickLine={false} tickFormatter={(v: number) => `$${v.toFixed(0)}`} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#12121a', border: '1px solid #2a2a3e', borderRadius: '8px', fontSize: '12px', color: '#f0f0f5' }}
                    labelStyle={{ color: '#a0a0b0' }}
                    itemStyle={{ color: '#e0e0e8' }}
                    formatter={(value: number | undefined) => [formatCurrency(value ?? 0), 'P&L']}
                  />
                  <Bar dataKey="pnl">
                    {pnlData.map((entry, idx) => (
                      <Cell
                        key={idx}
                        fill={entry.pnl >= 0 ? '#22c55e' : '#ef4444'}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>
      </div>

      {/* Treemap + Table */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Treemap */}
        <Card>
          <CardHeader title="Position Map" subtitle="Sized by market value" />
          <div className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <Treemap
                data={treemapData}
                dataKey="size"
                nameKey="name"
                stroke="none"
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                content={(props: any) => {
                  const { x, y, width, height, name, index } = props;
                  const fill = props.fill || TREEMAP_COLORS[index % TREEMAP_COLORS.length];
                  const pnl = treemapData[index]?.pnl ?? 0;
                  const pnlColor = pnl >= 0 ? '#86efac' : '#fca5a5';
                  return (
                    <g>
                      <rect
                        x={x + 1}
                        y={y + 1}
                        width={Math.max(width - 2, 0)}
                        height={Math.max(height - 2, 0)}
                        fill={fill}
                        rx={6}
                        opacity={0.9}
                      />
                      {width > 50 && height > 35 && (
                        <>
                          <text
                            x={x + width / 2}
                            y={y + height / 2 - 7}
                            textAnchor="middle"
                            dominantBaseline="central"
                            fill="#fff"
                            fontSize={13}
                            fontWeight={700}
                          >
                            {name}
                          </text>
                          <text
                            x={x + width / 2}
                            y={y + height / 2 + 10}
                            textAnchor="middle"
                            dominantBaseline="central"
                            fill={pnlColor}
                            fontSize={10}
                            fontWeight={500}
                          >
                            {pnl >= 0 ? '+' : ''}{(pnl * 100).toFixed(1)}%
                          </text>
                        </>
                      )}
                      {width > 30 && width <= 50 && height > 20 && (
                        <text
                          x={x + width / 2}
                          y={y + height / 2}
                          textAnchor="middle"
                          dominantBaseline="central"
                          fill="#fff"
                          fontSize={10}
                          fontWeight={600}
                        >
                          {name}
                        </text>
                      )}
                    </g>
                  );
                }}
              >
                <Tooltip
                  contentStyle={{ backgroundColor: '#12121a', border: '1px solid #2a2a3e', borderRadius: '8px', fontSize: '12px', color: '#f0f0f5' }}
                  labelStyle={{ color: '#a0a0b0' }}
                  itemStyle={{ color: '#e0e0e8' }}
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  formatter={(value: any) => [formatCurrency(Number(value) || 0), 'Market Value']}
                />
              </Treemap>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Positions Table */}
        <Card className="lg:col-span-2">
          <CardHeader title="All Positions" subtitle={`${portfolio.positions.length} holdings`} />
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="pb-3 text-xs font-medium text-muted">Symbol</th>
                  <th className="pb-3 text-xs font-medium text-muted">Side</th>
                  <th className="pb-3 text-right text-xs font-medium text-muted">Quantity</th>
                  <th className="pb-3 text-right text-xs font-medium text-muted">Avg Entry</th>
                  <th className="pb-3 text-right text-xs font-medium text-muted">Current</th>
                  <th className="pb-3 text-right text-xs font-medium text-muted">Market Value</th>
                  <th className="pb-3 text-right text-xs font-medium text-muted">Cost Basis</th>
                  <th className="pb-3 text-right text-xs font-medium text-muted">Unrealized P&L</th>
                  <th className="pb-3 text-right text-xs font-medium text-muted">P&L %</th>
                </tr>
              </thead>
              <tbody>
                {portfolio.positions.map((pos) => (
                  <tr
                    key={pos.symbol}
                    className="border-b border-border/50 transition-colors last:border-0 hover:bg-card-hover"
                  >
                    <td className="py-3 text-sm font-semibold text-foreground">{pos.symbol}</td>
                    <td className="py-3">
                      <Badge variant={pos.side === 'long' ? 'profit' : 'loss'}>
                        {pos.side.toUpperCase()}
                      </Badge>
                    </td>
                    <td className="py-3 text-right text-sm text-muted-foreground">{pos.quantity}</td>
                    <td className="py-3 text-right text-sm text-muted-foreground">
                      {pos.avg_entry_price ? formatCurrency(pos.avg_entry_price) : '—'}
                    </td>
                    <td className="py-3 text-right text-sm text-foreground">
                      {formatCurrency(pos.current_price)}
                    </td>
                    <td className="py-3 text-right text-sm text-foreground">
                      {formatCurrency(pos.market_value)}
                    </td>
                    <td className="py-3 text-right text-sm text-muted-foreground">
                      {formatCurrency(pos.cost_basis)}
                    </td>
                    <td
                      className={cn(
                        'py-3 text-right text-sm font-medium',
                        pos.unrealized_pnl >= 0 ? 'text-profit' : 'text-loss'
                      )}
                    >
                      {formatCurrency(pos.unrealized_pnl)}
                    </td>
                    <td
                      className={cn(
                        'py-3 text-right text-sm font-semibold',
                        pos.unrealized_pnl_percentage >= 0 ? 'text-profit' : 'text-loss'
                      )}
                    >
                      {formatPercent(pos.unrealized_pnl_percentage)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {/* Summary */}
          <div className="mt-4 flex items-center justify-between border-t border-border pt-3">
            <span className="text-xs text-muted">Last updated: {formatDate(portfolio.last_updated)}</span>
            <span className={cn('text-sm font-semibold', totalUnrealizedPnl >= 0 ? 'text-profit' : 'text-loss')}>
              Total: {formatCurrency(totalUnrealizedPnl)} ({formatPercent(
                portfolio.market_value > 0
                  ? (totalUnrealizedPnl / (portfolio.market_value - totalUnrealizedPnl)) * 100
                  : 0
              )})
            </span>
          </div>
        </Card>
      </div>
    </div>
  );
}
