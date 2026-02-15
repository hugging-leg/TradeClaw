import { useEffect, useState, useCallback } from 'react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast';
import { fetchSettings, updateSettings } from '@/api';
import type { TradingSettings } from '@/types';
import {
  Settings as SettingsIcon,
  Shield,
  Clock,
  Bot,
  Globe,
  Database,
  Activity,
  Save,
  RotateCcw,
  Crosshair,
  Server,
  KeyRound,
  Eye,
  EyeOff,
} from 'lucide-react';
import { cn } from '@/utils/cn';

type SettingsTab =
  | 'trading'
  | 'risk'
  | 'scheduling'
  | 'monitoring'
  | 'providers'
  | 'api_keys'
  | 'llm'
  | 'execution'
  | 'infra';

// ========== Field definitions ==========

interface FieldDef {
  key: string;
  label: string;
  description?: string;
  editable?: boolean;
  inputType?: 'number' | 'text' | 'boolean' | 'select' | 'password';
  /** Options for select type */
  options?: string[];
  step?: number;
  suffix?: string;
  /** Raw value is 0-1, display as 0-100 */
  isPercentage?: boolean;
  /** Write-only: value not returned by API, only accept new input */
  writeOnly?: boolean;
}

// Helper: all fields default to editable unless explicitly set to false
function f(def: Omit<FieldDef, 'editable'> & { editable?: boolean }): FieldDef {
  return { editable: true, ...def };
}

const FIELD_GROUPS: Record<SettingsTab, { title: string; subtitle: string; fields: FieldDef[] }> = {
  trading: {
    title: 'Trading Parameters',
    subtitle: 'Core trading configuration',
    fields: [
      f({ key: 'paper_trading', label: 'Paper Trading', description: 'Use paper trading mode (no real money)', inputType: 'boolean' }),
      f({ key: 'max_position_size', label: 'Max Position Size', description: 'Maximum allocation per position', isPercentage: true, step: 0.01 }),
      f({ key: 'max_positions', label: 'Max Positions', description: 'Maximum number of concurrent positions', inputType: 'number', step: 1 }),
      f({ key: 'rebalance_time', label: 'Rebalance Time', description: 'Daily rebalance trigger time (trading timezone)', inputType: 'text' }),
      f({ key: 'eod_analysis_time', label: 'EOD Analysis Time', description: 'End-of-day analysis time', inputType: 'text' }),
      { key: 'workflow_type', label: 'Workflow Type', description: 'Switch via Agent page', editable: false },
      f({ key: 'trading_timezone', label: 'Trading Timezone', description: 'e.g. US/Eastern', inputType: 'text' }),
      f({ key: 'exchange', label: 'Exchange', description: 'e.g. XNYS, XNAS', inputType: 'text' }),
    ],
  },
  risk: {
    title: 'Risk Management',
    subtitle: 'Stop loss, take profit, and limits',
    fields: [
      f({ key: 'risk_management_enabled', label: 'Risk Management', description: 'Enable/disable risk management', inputType: 'boolean' }),
      f({ key: 'stop_loss_percentage', label: 'Stop Loss', description: 'Per-position stop loss', isPercentage: true, step: 0.01 }),
      f({ key: 'take_profit_percentage', label: 'Take Profit', description: 'Per-position take profit', isPercentage: true, step: 0.01 }),
      f({ key: 'daily_loss_limit_percentage', label: 'Daily Loss Limit', description: 'Maximum daily portfolio loss', isPercentage: true, step: 0.01 }),
      f({ key: 'max_position_concentration', label: 'Max Concentration', description: 'Maximum single position weight', isPercentage: true, step: 0.01 }),
      f({ key: 'portfolio_pnl_alert_threshold', label: 'Portfolio P&L Alert', description: 'Alert when day P&L exceeds threshold', isPercentage: true, step: 0.01 }),
      f({ key: 'position_loss_alert_threshold', label: 'Position Loss Alert', description: 'Alert when position unrealized loss exceeds threshold', isPercentage: true, step: 0.01 }),
    ],
  },
  scheduling: {
    title: 'Scheduling',
    subtitle: 'Task intervals and timing',
    fields: [
      f({ key: 'portfolio_check_interval', label: 'Portfolio Check Interval', description: 'How often to check portfolio status', suffix: 'min', inputType: 'number', step: 1 }),
      f({ key: 'risk_check_interval', label: 'Risk Check Interval', description: 'How often to run risk checks', suffix: 'min', inputType: 'number', step: 1 }),
      f({ key: 'min_workflow_interval_minutes', label: 'Min Workflow Interval', description: 'Minimum time between workflow executions', suffix: 'min', inputType: 'number', step: 1 }),
      f({ key: 'scheduler_misfire_grace_time', label: 'Misfire Grace Time', description: 'APScheduler misfire grace time', suffix: 's', inputType: 'number', step: 1 }),
      f({ key: 'max_pending_llm_jobs', label: 'Max Pending LLM Jobs', description: 'Maximum pending LLM-scheduled tasks', inputType: 'number', step: 1 }),
      f({ key: 'message_rate_limit', label: 'Message Rate Limit', description: 'Max messages per second', suffix: '/s', inputType: 'number', step: 0.1 }),
    ],
  },
  monitoring: {
    title: 'Realtime Monitoring',
    subtitle: 'Price and volatility thresholds',
    fields: [
      f({ key: 'price_change_threshold', label: 'Price Change Threshold', description: 'Trigger workflow when price changes by this amount', suffix: '%', inputType: 'number', step: 0.5 }),
      f({ key: 'volatility_threshold', label: 'Volatility Threshold', description: 'Trigger workflow when volatility exceeds this', suffix: '%', inputType: 'number', step: 0.5 }),
      f({ key: 'rebalance_cooldown_seconds', label: 'Rebalance Cooldown', description: 'Minimum seconds between rebalances', suffix: 's', inputType: 'number', step: 60 }),
      f({ key: 'market_etfs', label: 'Market ETFs', description: 'Comma-separated list of ETFs to monitor', inputType: 'text' }),
    ],
  },
  providers: {
    title: 'API Providers',
    subtitle: 'Broker, market data, and messaging providers',
    fields: [
      f({ key: 'broker_provider', label: 'Broker', description: 'Trading broker API provider', inputType: 'select', options: ['alpaca', 'ibkr'] }),
      f({ key: 'alpaca_base_url', label: 'Alpaca Base URL', description: 'Paper: https://paper-api.alpaca.markets', inputType: 'text' }),
      f({ key: 'market_data_provider', label: 'Market Data', description: 'Market data provider', inputType: 'select', options: ['tiingo', 'alpaca', 'finnhub'] }),
      f({ key: 'realtime_data_provider', label: 'Realtime Data', description: 'Realtime data provider', inputType: 'select', options: ['finnhub', 'alpaca'] }),
      f({ key: 'news_providers', label: 'News Providers', description: 'Comma-separated news sources', inputType: 'text' }),
      f({ key: 'message_provider', label: 'Message Provider', description: 'Notification provider', inputType: 'select', options: ['telegram', 'none'] }),
      f({ key: 'telegram_chat_id', label: 'Telegram Chat ID', description: 'Telegram chat/group ID for notifications', inputType: 'text' }),
    ],
  },
  api_keys: {
    title: 'API Keys',
    subtitle: 'Write-only — enter a new key to update, current values are never sent to the browser',
    fields: [
      f({ key: 'alpaca_api_key', label: 'Alpaca API Key', inputType: 'password', writeOnly: true }),
      f({ key: 'alpaca_secret_key', label: 'Alpaca Secret Key', inputType: 'password', writeOnly: true }),
      f({ key: 'tiingo_api_key', label: 'Tiingo API Key', inputType: 'password', writeOnly: true }),
      f({ key: 'finnhub_api_key', label: 'Finnhub API Key', inputType: 'password', writeOnly: true }),
      f({ key: 'unusual_whales_api_key', label: 'Unusual Whales API Key', inputType: 'password', writeOnly: true }),
      f({ key: 'llm_api_key', label: 'LLM API Key', description: 'Primary LLM (OpenAI-compatible)', inputType: 'password', writeOnly: true }),
      f({ key: 'news_llm_api_key', label: 'News LLM API Key', description: 'Separate key for news filtering (empty = use primary)', inputType: 'password', writeOnly: true }),
      f({ key: 'telegram_bot_token', label: 'Telegram Bot Token', inputType: 'password', writeOnly: true }),
    ],
  },
  llm: {
    title: 'LLM Configuration',
    subtitle: 'API endpoints and news LLM — model/agent params are in Agent page',
    fields: [
      f({ key: 'llm_base_url', label: 'LLM Base URL', description: 'OpenAI-compatible API base URL', inputType: 'text' }),
      f({ key: 'news_llm_base_url', label: 'News LLM Base URL', description: 'Separate LLM for news filtering (empty = use primary)', inputType: 'text' }),
      f({ key: 'news_llm_model', label: 'News LLM Model', description: 'Model for news filtering (empty = use primary)', inputType: 'text' }),
    ],
  },
  execution: {
    title: 'Trade Execution',
    subtitle: 'Rebalance and order execution parameters',
    fields: [
      f({ key: 'rebalance_min_value_threshold', label: 'Min Value Threshold', description: 'Minimum adjustment market value ($)', suffix: '$', inputType: 'number', step: 5 }),
      f({ key: 'rebalance_min_pct_threshold', label: 'Min % Threshold', description: 'Minimum adjustment percentage', suffix: '%', inputType: 'number', step: 0.5 }),
      f({ key: 'rebalance_buy_reserve_ratio', label: 'Buy Reserve Ratio', description: 'Cash reserve ratio when buying', inputType: 'number', step: 0.01 }),
      f({ key: 'rebalance_weight_diff_threshold', label: 'Weight Diff Threshold', description: 'Minimum weight difference to trigger adjustment', inputType: 'number', step: 0.005 }),
      f({ key: 'rebalance_order_delay_seconds', label: 'Order Delay', description: 'Delay between consecutive orders', suffix: 's', inputType: 'number', step: 0.5 }),
      f({ key: 'cash_keywords', label: 'Cash Keywords', description: 'Comma-separated keywords treated as cash', inputType: 'text' }),
    ],
  },
  infra: {
    title: 'Infrastructure',
    subtitle: 'API server, logging, and environment',
    fields: [
      f({ key: 'api_cors_origins', label: 'CORS Origins', description: 'Comma-separated allowed origins', inputType: 'text' }),
      f({ key: 'environment', label: 'Environment', description: 'development / production', inputType: 'select', options: ['development', 'production'] }),
      f({ key: 'log_level', label: 'Log Level', description: 'Logging verbosity', inputType: 'select', options: ['DEBUG', 'INFO', 'WARNING', 'ERROR'] }),
      f({ key: 'log_to_file', label: 'Log to File', description: 'Write logs to file', inputType: 'boolean' }),
      { key: 'api_host', label: 'API Host', description: 'API server bind address (restart required)', editable: false },
      { key: 'api_port', label: 'API Port', description: 'API server port (restart required)', editable: false },
    ],
  },
};

const tabs: { key: SettingsTab; label: string; icon: typeof SettingsIcon }[] = [
  { key: 'trading', label: 'Trading', icon: Activity },
  { key: 'risk', label: 'Risk', icon: Shield },
  { key: 'scheduling', label: 'Scheduling', icon: Clock },
  { key: 'monitoring', label: 'Monitoring', icon: Database },
  { key: 'providers', label: 'Providers', icon: Globe },
  { key: 'api_keys', label: 'API Keys', icon: KeyRound },
  { key: 'llm', label: 'LLM', icon: Bot },
  { key: 'execution', label: 'Execution', icon: Crosshair },
  { key: 'infra', label: 'Infrastructure', icon: Server },
];

// ========== Setting Row ==========

function SettingRow({
  field,
  value,
  editedValue,
  onEdit,
}: {
  field: FieldDef;
  value: unknown;
  editedValue: unknown;
  onEdit?: (val: unknown) => void;
}) {
  const [showSecret, setShowSecret] = useState(false);
  const isEdited = editedValue !== undefined;
  const displayVal = isEdited ? editedValue : value;
  const isEditable = field.editable !== false && !!onEdit;

  // Format display value
  const formatDisplay = (v: unknown): string => {
    if (v === null || v === undefined) return '—';
    if (field.isPercentage && typeof v === 'number') return `${(v * 100).toFixed(1)}%`;
    if (field.suffix && typeof v === 'number') return `${v} ${field.suffix}`;
    if (typeof v === 'boolean') return v ? 'Enabled' : 'Disabled';
    return String(v);
  };

  const renderInput = () => {
    const inputType = field.inputType ?? (typeof value === 'number' ? 'number' : typeof value === 'boolean' ? 'boolean' : 'text');

    if (inputType === 'boolean') {
      return (
        <button
          onClick={() => onEdit!(!(displayVal as boolean))}
          className={cn(
            'flex h-7 w-12 items-center rounded-full px-0.5 transition-colors',
            displayVal ? 'bg-accent' : 'bg-gray-700',
          )}
        >
          <div
            className={cn(
              'h-6 w-6 rounded-full bg-white shadow transition-transform',
              displayVal ? 'translate-x-5' : 'translate-x-0',
            )}
          />
        </button>
      );
    }

    if (inputType === 'select' && field.options) {
      return (
        <select
          value={String(displayVal ?? '')}
          onChange={(e) => onEdit!(e.target.value)}
          className="w-44 rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
        >
          {field.options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
          {/* If current value is not in options, show it anyway */}
          {displayVal != null && String(displayVal) !== '' && !field.options.includes(String(displayVal)) && (
            <option value={String(displayVal)}>{String(displayVal)}</option>
          )}
        </select>
      );
    }

    if (inputType === 'password') {
      // Write-only fields: value is never returned from API, show empty input
      const pwValue = field.writeOnly ? String(editedValue ?? '') : String(displayVal ?? '');
      return (
        <div className="flex items-center gap-1.5">
          <input
            type={showSecret ? 'text' : 'password'}
            value={pwValue}
            placeholder={field.writeOnly ? 'Enter new value to update…' : '****'}
            onChange={(e) => onEdit!(e.target.value)}
            className="w-56 rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent font-mono"
          />
          <button
            type="button"
            onClick={() => setShowSecret((p) => !p)}
            className="rounded p-1 text-muted hover:text-foreground transition-colors"
            title={showSecret ? 'Hide' : 'Show'}
          >
            {showSecret ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
      );
    }

    if (inputType === 'number' || field.isPercentage) {
      return (
        <div className="flex items-center gap-1.5">
          <input
            type="number"
            step={field.step ?? 'any'}
            value={
              field.isPercentage && typeof displayVal === 'number'
                ? (displayVal * 100).toFixed(1)
                : String(displayVal ?? '')
            }
            onChange={(e) => {
              const raw = Number(e.target.value);
              if (isNaN(raw)) return;
              onEdit!(field.isPercentage ? raw / 100 : raw);
            }}
            className="w-28 rounded-md border border-border bg-background px-2 py-1.5 text-right text-sm text-foreground focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
          />
          {field.isPercentage && <span className="text-xs text-muted">%</span>}
          {field.suffix && !field.isPercentage && <span className="text-xs text-muted">{field.suffix}</span>}
        </div>
      );
    }

    // text input
    return (
      <input
        type="text"
        value={String(displayVal ?? '')}
        onChange={(e) => onEdit!(e.target.value)}
        className="w-56 rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
      />
    );
  };

  return (
    <div className="flex flex-col gap-2 border-b border-border/50 py-3 last:border-0 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-sm text-foreground">
          {field.label}
          {isEdited && (
            <span className="rounded bg-accent/20 px-1.5 py-0.5 text-[10px] text-accent-light">modified</span>
          )}
        </div>
        {field.description && <div className="mt-0.5 text-xs text-muted">{field.description}</div>}
      </div>

      <div className="shrink-0 sm:ml-4">
        {isEditable ? (
          renderInput()
        ) : typeof value === 'boolean' ? (
          <Badge variant={value ? 'profit' : 'muted'}>{value ? 'Enabled' : 'Disabled'}</Badge>
        ) : (
          <span className="text-sm font-medium text-foreground">{formatDisplay(value)}</span>
        )}
      </div>
    </div>
  );
}

// ========== Main ==========

export default function Settings() {
  const { toast } = useToast();
  const [settings, setSettings] = useState<Record<string, unknown> | null>(null);
  const [activeTab, setActiveTab] = useState<SettingsTab>('trading');
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    fetchSettings()
      .then((data) => setSettings(data as unknown as Record<string, unknown>))
      .catch(() => toast('Failed to load settings', 'error'));
  }, [toast]);

  useEffect(() => {
    load();
  }, [load]);

  const editedCount = Object.keys(draft).length;

  const handleEdit = (key: string, val: unknown) => {
    setDraft((prev) => {
      const next = { ...prev };
      // If reverted to original, remove from draft
      if (settings && val === settings[key]) {
        delete next[key];
      } else {
        next[key] = val;
      }
      return next;
    });
  };

  const handleReset = () => setDraft({});

  const handleSave = async () => {
    if (editedCount === 0) return;
    setSaving(true);
    try {
      const updated = await updateSettings(draft as Partial<TradingSettings>);
      // updateSettings returns the current settings dict after the patch
      setSettings(updated as unknown as Record<string, unknown>);
      setDraft({});
      toast(`Updated ${editedCount} setting(s)`, 'success');
    } catch {
      toast('Failed to update settings', 'error');
    } finally {
      setSaving(false);
    }
  };

  if (!settings) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      </div>
    );
  }

  const group = FIELD_GROUPS[activeTab];

  return (
    <div className="animate-fade-in space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Settings</h1>
          <p className="mt-1 text-sm text-muted">
            System configuration — runtime changes reset on restart
          </p>
        </div>
        {editedCount > 0 && (
          <div className="flex items-center gap-3">
            <span className="hidden text-xs text-muted sm:inline">{editedCount} field(s) modified</span>
            <Button variant="secondary" icon={<RotateCcw className="h-4 w-4" />} onClick={handleReset}>
              Reset
            </Button>
            <Button icon={<Save className="h-4 w-4" />} loading={saving} onClick={handleSave}>
              Save Changes
            </Button>
          </div>
        )}
      </div>

      {/* Mobile: horizontal scrollable tabs */}
      <div className="-mx-4 overflow-x-auto px-4 md:hidden">
        <div className="flex gap-1.5 pb-2">
          {tabs.map(({ key, label, icon: Icon }) => {
            const tabEdits = FIELD_GROUPS[key].fields.filter((fd) => fd.key in draft).length;
            return (
              <button
                key={key}
                onClick={() => setActiveTab(key)}
                className={cn(
                  'flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition-colors',
                  activeTab === key
                    ? 'bg-accent/10 text-accent-light'
                    : 'bg-card text-muted hover:text-foreground',
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {label}
                {tabEdits > 0 && (
                  <span className="rounded-full bg-accent/20 px-1 py-0.5 text-[10px] font-bold text-accent-light">
                    {tabEdits}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex gap-6">
        {/* Desktop Sidebar Tabs */}
        <div className="hidden w-48 shrink-0 space-y-1 md:block">
          {tabs.map(({ key, label, icon: Icon }) => {
            const tabEdits = FIELD_GROUPS[key].fields.filter((fd) => fd.key in draft).length;
            return (
              <button
                key={key}
                onClick={() => setActiveTab(key)}
                className={cn(
                  'flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  activeTab === key
                    ? 'bg-accent/10 text-accent-light'
                    : 'text-muted hover:bg-card-hover hover:text-foreground',
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
                {tabEdits > 0 && (
                  <span className="ml-auto rounded-full bg-accent/20 px-1.5 py-0.5 text-[10px] font-bold text-accent-light">
                    {tabEdits}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Content */}
        <div className="min-w-0 flex-1">
          <Card>
            <CardHeader title={group.title} subtitle={group.subtitle} />
            {group.fields.map((field) => (
              <SettingRow
                key={field.key}
                field={field}
                value={settings[field.key]}
                editedValue={draft[field.key]}
                onEdit={field.editable !== false ? (val) => handleEdit(field.key, val) : undefined}
              />
            ))}
          </Card>
        </div>
      </div>
    </div>
  );
}
