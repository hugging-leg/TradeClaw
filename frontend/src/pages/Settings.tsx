import { useEffect, useState } from 'react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { fetchSettings } from '@/api';
import type { TradingSettings } from '@/types';
import {
  Settings as SettingsIcon,
  Shield,
  Clock,
  Bot,
  Globe,
  Database,
  Activity,
} from 'lucide-react';
import { cn } from '@/utils/cn';

type SettingsTab = 'trading' | 'risk' | 'scheduling' | 'llm' | 'providers' | 'monitoring';

interface SettingRowProps {
  label: string;
  value: string | number | boolean;
  description?: string;
}

function SettingRow({ label, value, description }: SettingRowProps) {
  const displayValue =
    typeof value === 'boolean' ? (
      <Badge variant={value ? 'profit' : 'muted'}>{value ? 'Enabled' : 'Disabled'}</Badge>
    ) : (
      <span className="text-sm font-medium text-foreground">{String(value)}</span>
    );

  return (
    <div className="flex items-center justify-between border-b border-border/50 py-3 last:border-0">
      <div>
        <div className="text-sm text-foreground">{label}</div>
        {description && <div className="mt-0.5 text-xs text-muted">{description}</div>}
      </div>
      {displayValue}
    </div>
  );
}

const tabs: { key: SettingsTab; label: string; icon: typeof SettingsIcon }[] = [
  { key: 'trading', label: 'Trading', icon: Activity },
  { key: 'risk', label: 'Risk Management', icon: Shield },
  { key: 'scheduling', label: 'Scheduling', icon: Clock },
  { key: 'llm', label: 'LLM / Agent', icon: Bot },
  { key: 'providers', label: 'Providers', icon: Globe },
  { key: 'monitoring', label: 'Monitoring', icon: Database },
];

export default function Settings() {
  const [settings, setSettings] = useState<TradingSettings | null>(null);
  const [activeTab, setActiveTab] = useState<SettingsTab>('trading');

  useEffect(() => {
    fetchSettings().then(setSettings);
  }, []);

  if (!settings) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="animate-fade-in space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Settings</h1>
        <p className="mt-1 text-sm text-muted">System configuration and environment settings</p>
      </div>

      <div className="flex gap-6">
        {/* Sidebar Tabs */}
        <div className="w-48 shrink-0 space-y-1">
          {tabs.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={cn(
                'flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                activeTab === key
                  ? 'bg-accent/10 text-accent-light'
                  : 'text-muted hover:bg-card-hover hover:text-foreground'
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1">
          {activeTab === 'trading' && (
            <Card>
              <CardHeader title="Trading Parameters" subtitle="Core trading configuration" />
              <SettingRow label="Paper Trading" value={settings.paper_trading} description="Use paper trading mode (no real money)" />
              <SettingRow label="Max Position Size" value={`${(settings.max_position_size * 100).toFixed(0)}%`} description="Maximum allocation per position" />
              <SettingRow label="Max Positions" value={settings.max_positions} description="Maximum number of concurrent positions" />
              <SettingRow label="Rebalance Time" value={settings.rebalance_time} description="Daily rebalance trigger time (trading timezone)" />
              <SettingRow label="EOD Analysis Time" value={settings.eod_analysis_time} description="End-of-day analysis time" />
              <SettingRow label="Workflow Type" value={settings.workflow_type} description="Active trading workflow" />
              <SettingRow label="Trading Timezone" value={settings.trading_timezone} />
              <SettingRow label="Exchange" value={settings.exchange} />
            </Card>
          )}

          {activeTab === 'risk' && (
            <Card>
              <CardHeader title="Risk Management" subtitle="Stop loss, take profit, and limits" />
              <SettingRow label="Stop Loss" value={`${(settings.stop_loss_percentage * 100).toFixed(0)}%`} description="Per-position stop loss percentage" />
              <SettingRow label="Take Profit" value={`${(settings.take_profit_percentage * 100).toFixed(0)}%`} description="Per-position take profit percentage" />
              <SettingRow label="Daily Loss Limit" value={`${(settings.daily_loss_limit_percentage * 100).toFixed(0)}%`} description="Maximum daily portfolio loss" />
              <SettingRow label="Max Position Concentration" value={`${(settings.max_position_concentration * 100).toFixed(0)}%`} description="Maximum single position weight" />
              <SettingRow label="Portfolio P&L Alert" value={`${(settings.portfolio_pnl_alert_threshold * 100).toFixed(0)}%`} description="Alert when day P&L exceeds threshold" />
              <SettingRow label="Position Loss Alert" value={`${(settings.position_loss_alert_threshold * 100).toFixed(0)}%`} description="Alert when position unrealized loss exceeds threshold" />
            </Card>
          )}

          {activeTab === 'scheduling' && (
            <Card>
              <CardHeader title="Scheduling" subtitle="Task intervals and timing" />
              <SettingRow label="Portfolio Check Interval" value={`${settings.portfolio_check_interval} min`} description="How often to check portfolio status" />
              <SettingRow label="Risk Check Interval" value={`${settings.risk_check_interval} min`} description="How often to run risk checks" />
              <SettingRow label="Min Workflow Interval" value={`${settings.min_workflow_interval_minutes} min`} description="Minimum time between workflow executions" />
            </Card>
          )}

          {activeTab === 'llm' && (
            <Card>
              <CardHeader title="LLM / Agent Configuration" subtitle="AI model and agent settings" />
              <SettingRow label="LLM Model" value={settings.llm_model} description="Primary LLM model for agent workflows" />
              <SettingRow label="Recursion Limit" value={settings.llm_recursion_limit} description="Maximum ReAct agent recursion depth" />
              <SettingRow label="Environment" value={settings.environment} />
            </Card>
          )}

          {activeTab === 'providers' && (
            <Card>
              <CardHeader title="API Providers" subtitle="Broker, market data, and messaging" />
              <SettingRow label="Broker" value={settings.broker_provider} description="Trading broker API provider" />
              <SettingRow label="Market Data" value={settings.market_data_provider} description="Market data provider" />
              <SettingRow label="News Providers" value={settings.news_providers} description="News data sources" />
            </Card>
          )}

          {activeTab === 'monitoring' && (
            <Card>
              <CardHeader title="Realtime Monitoring" subtitle="Price and volatility thresholds" />
              <SettingRow label="Price Change Threshold" value={`${settings.price_change_threshold}%`} description="Trigger workflow when price changes by this amount" />
              <SettingRow label="Volatility Threshold" value={`${settings.volatility_threshold}%`} description="Trigger workflow when volatility exceeds this" />
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
