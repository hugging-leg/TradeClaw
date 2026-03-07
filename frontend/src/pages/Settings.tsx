import { useEffect, useState, useCallback } from 'react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast';
import { fetchSettings, updateSettings } from '@/api';
import type { TradingSettings } from '@/types';
import LLMSettings from '@/components/LLMSettings';
import RiskRulesSettings from '@/components/RiskRulesSettings';
import AutomationPipelines from '@/components/AutomationPipelines';
import {
  Settings as SettingsIcon,
  ShieldAlert,
  Clock,
  Bot,
  Globe,
  Activity,
  Save,
  RotateCcw,
  Crosshair,
  KeyRound,
  Eye,
  EyeOff,
  Workflow,
} from 'lucide-react';
import { cn } from '@/utils/cn';

type SettingsTab =
  | 'trading'
  | 'risk_rules'
  | 'automation'
  | 'scheduling'
  | 'providers'
  | 'api_keys'
  | 'llm'
  | 'execution';

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
      f({ key: 'rebalance_time', label: 'Rebalance Time', description: 'Daily rebalance trigger time (trading timezone)', inputType: 'text' }),
      f({ key: 'eod_analysis_time', label: 'EOD Analysis Time', description: 'End-of-day analysis time', inputType: 'text' }),
      { key: 'workflow_type', label: 'Workflow Type', description: 'Switch via Agent page', editable: false },
      f({ key: 'trading_timezone', label: 'Trading Timezone', description: 'e.g. US/Eastern', inputType: 'text' }),
      f({ key: 'exchange', label: 'Exchange', description: 'e.g. XNYS, XNAS', inputType: 'text' }),
    ],
  },
  risk_rules: {
    title: 'Risk Management',
    subtitle: 'Stop-loss, take-profit rules and alert thresholds',
    fields: [], // Rendered by dedicated RiskRulesSettings component
  },
  automation: {
    title: 'Automation Pipelines',
    subtitle: 'Real-time news monitoring, price triggers, and LLM analysis flows',
    fields: [], // Rendered by dedicated AutomationPipelines component
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
  providers: {
    title: 'API Providers',
    subtitle: 'Broker, market data, and messaging providers',
    fields: [
      f({ key: 'broker_provider', label: 'Broker', description: 'Trading broker API provider', inputType: 'select', options: ['alpaca', 'ibkr'] }),
      f({ key: 'alpaca_base_url', label: 'Alpaca Base URL', description: 'Paper: https://paper-api.alpaca.markets', inputType: 'text' }),
      f({ key: 'market_data_provider', label: 'Market Data', description: 'Market data provider', inputType: 'select', options: ['tiingo', 'alpaca', 'finnhub'] }),
      f({ key: 'realtime_data_provider', label: 'Realtime Data', description: 'Realtime WebSocket data provider (leave empty if not available)', inputType: 'select', options: ['', 'finnhub', 'alpaca'] }),
      f({ key: 'news_providers', label: 'News Providers', description: 'Comma-separated news sources', inputType: 'text' }),
      f({ key: 'message_provider', label: 'Message Provider', description: 'Notification provider', inputType: 'select', options: ['telegram', 'none'] }),
      f({ key: 'telegram_chat_id', label: 'Telegram Chat ID', description: 'Telegram chat/group ID for notifications', inputType: 'text' }),
      f({ key: 'opensandbox_server_url', label: 'OpenSandbox Server', description: 'OpenSandbox server URL for code sandbox (e.g. localhost:8080)', inputType: 'text' }),
      f({ key: 'playwright_mcp_url', label: 'Playwright MCP URL', description: 'Playwright MCP server URL for browser automation (e.g. http://localhost:8931)', inputType: 'text' }),
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
      f({ key: 'telegram_bot_token', label: 'Telegram Bot Token', inputType: 'password', writeOnly: true }),
    ],
  },
  llm: {
    title: 'LLM Providers',
    subtitle: 'Manage API providers, models, and role assignments',
    fields: [], // Rendered by dedicated LLMSettings component
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
};

const tabs: { key: SettingsTab; label: string; icon: typeof SettingsIcon }[] = [
  { key: 'trading', label: 'Trading', icon: Activity },
  { key: 'risk_rules', label: 'Risk', icon: ShieldAlert },
  { key: 'automation', label: 'Automation', icon: Workflow },
  { key: 'scheduling', label: 'Scheduling', icon: Clock },
  { key: 'providers', label: 'Providers', icon: Globe },
  { key: 'api_keys', label: 'API Keys', icon: KeyRound },
  { key: 'llm', label: 'LLM', icon: Bot },
  { key: 'execution', label: 'Execution', icon: Crosshair },
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
              {opt || '(none)'}
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

  // Check if current tab is a custom-rendered tab
  const isCustomTab = activeTab === 'llm' || activeTab === 'risk_rules' || activeTab === 'automation';

  return (
    <div className="animate-fade-in space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Settings</h1>
          <p className="mt-1 text-sm text-muted">
            System configuration — changes persist to YAML where applicable
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
          {activeTab === 'llm' ? (
            <LLMSettings />
          ) : activeTab === 'risk_rules' ? (
            <RiskRulesSettings
              riskEnabled={settings.risk_management_enabled as boolean | undefined}
              alertThresholds={{
                portfolio_pnl_alert_threshold: settings.portfolio_pnl_alert_threshold as number | undefined,
                position_loss_alert_threshold: settings.position_loss_alert_threshold as number | undefined,
              }}
              onUpdateSetting={(key, val) => {
                handleEdit(key, val);
                // Auto-save alert threshold changes immediately
                updateSettings({ [key]: val } as Partial<TradingSettings>)
                  .then((updated) => setSettings(updated as unknown as Record<string, unknown>))
                  .catch(() => toast('Failed to update setting', 'error'));
              }}
            />
          ) : activeTab === 'automation' ? (
            <AutomationPipelines settings={settings} onUpdateSetting={handleEdit} />
          ) : isCustomTab ? null : (
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
          )}
        </div>
      </div>
    </div>
  );
}
