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
} from 'lucide-react';
import { cn } from '@/utils/cn';

type SettingsTab = 'trading' | 'risk' | 'scheduling' | 'llm' | 'providers' | 'monitoring';

// ========== Field definitions ==========

interface FieldDef {
  key: keyof TradingSettings;
  label: string;
  description?: string;
  /** Fields that can be edited at runtime */
  editable?: boolean;
  /** Display transform (for read-only display) */
  display?: (v: unknown) => string;
  /** Input type hint */
  inputType?: 'number' | 'text' | 'boolean';
  /** Step for number inputs */
  step?: number;
  /** Suffix shown after the value */
  suffix?: string;
  /** For percentage fields: the raw value is 0-1, display as 0-100 */
  isPercentage?: boolean;
}

const FIELD_GROUPS: Record<SettingsTab, { title: string; subtitle: string; fields: FieldDef[] }> = {
  trading: {
    title: 'Trading Parameters',
    subtitle: 'Core trading configuration',
    fields: [
      { key: 'paper_trading', label: 'Paper Trading', description: 'Use paper trading mode (no real money)', inputType: 'boolean' },
      { key: 'max_position_size', label: 'Max Position Size', description: 'Maximum allocation per position', isPercentage: true },
      { key: 'max_positions', label: 'Max Positions', description: 'Maximum number of concurrent positions', inputType: 'number' },
      { key: 'rebalance_time', label: 'Rebalance Time', description: 'Daily rebalance trigger time (trading timezone)' },
      { key: 'eod_analysis_time', label: 'EOD Analysis Time', description: 'End-of-day analysis time' },
      { key: 'workflow_type', label: 'Workflow Type', description: 'Active trading workflow' },
      { key: 'trading_timezone', label: 'Trading Timezone' },
      { key: 'exchange', label: 'Exchange' },
    ],
  },
  risk: {
    title: 'Risk Management',
    subtitle: 'Stop loss, take profit, and limits',
    fields: [
      { key: 'stop_loss_percentage', label: 'Stop Loss', description: 'Per-position stop loss', editable: true, isPercentage: true, step: 0.01 },
      { key: 'take_profit_percentage', label: 'Take Profit', description: 'Per-position take profit', editable: true, isPercentage: true, step: 0.01 },
      { key: 'daily_loss_limit_percentage', label: 'Daily Loss Limit', description: 'Maximum daily portfolio loss', editable: true, isPercentage: true, step: 0.01 },
      { key: 'max_position_concentration', label: 'Max Position Concentration', description: 'Maximum single position weight', editable: true, isPercentage: true, step: 0.01 },
      { key: 'portfolio_pnl_alert_threshold', label: 'Portfolio P&L Alert', description: 'Alert when day P&L exceeds threshold', editable: true, isPercentage: true, step: 0.01 },
      { key: 'position_loss_alert_threshold', label: 'Position Loss Alert', description: 'Alert when position unrealized loss exceeds threshold', editable: true, isPercentage: true, step: 0.01 },
    ],
  },
  scheduling: {
    title: 'Scheduling',
    subtitle: 'Task intervals and timing',
    fields: [
      { key: 'portfolio_check_interval', label: 'Portfolio Check Interval', description: 'How often to check portfolio status', suffix: 'min', inputType: 'number' },
      { key: 'risk_check_interval', label: 'Risk Check Interval', description: 'How often to run risk checks', suffix: 'min', inputType: 'number' },
      { key: 'min_workflow_interval_minutes', label: 'Min Workflow Interval', description: 'Minimum time between workflow executions', editable: true, suffix: 'min', inputType: 'number', step: 1 },
    ],
  },
  llm: {
    title: 'LLM / Agent Configuration',
    subtitle: 'AI model and agent settings',
    fields: [
      { key: 'llm_model', label: 'LLM Model', description: 'Primary LLM model for agent workflows' },
      { key: 'llm_recursion_limit', label: 'Recursion Limit', description: 'Maximum ReAct agent recursion depth', inputType: 'number' },
      { key: 'environment', label: 'Environment' },
    ],
  },
  providers: {
    title: 'API Providers',
    subtitle: 'Broker, market data, and messaging',
    fields: [
      { key: 'broker_provider', label: 'Broker', description: 'Trading broker API provider' },
      { key: 'market_data_provider', label: 'Market Data', description: 'Market data provider' },
      { key: 'news_providers', label: 'News Providers', description: 'News data sources' },
    ],
  },
  monitoring: {
    title: 'Realtime Monitoring',
    subtitle: 'Price and volatility thresholds',
    fields: [
      { key: 'price_change_threshold', label: 'Price Change Threshold', description: 'Trigger workflow when price changes by this amount', editable: true, suffix: '%', inputType: 'number', step: 0.5 },
      { key: 'volatility_threshold', label: 'Volatility Threshold', description: 'Trigger workflow when volatility exceeds this', editable: true, suffix: '%', inputType: 'number', step: 0.5 },
    ],
  },
};

const tabs: { key: SettingsTab; label: string; icon: typeof SettingsIcon }[] = [
  { key: 'trading', label: 'Trading', icon: Activity },
  { key: 'risk', label: 'Risk Management', icon: Shield },
  { key: 'scheduling', label: 'Scheduling', icon: Clock },
  { key: 'llm', label: 'LLM / Agent', icon: Bot },
  { key: 'providers', label: 'Providers', icon: Globe },
  { key: 'monitoring', label: 'Monitoring', icon: Database },
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
  const isEdited = editedValue !== undefined;
  const displayVal = isEdited ? editedValue : value;
  const isEditable = !!field.editable && !!onEdit;

  // Format display value
  const formatDisplay = (v: unknown): string => {
    if (field.isPercentage && typeof v === 'number') return `${(v * 100).toFixed(0)}%`;
    if (field.suffix && typeof v === 'number') return `${v}${field.suffix}`;
    return String(v ?? '');
  };

  return (
    <div className="flex items-center justify-between border-b border-border/50 py-3 last:border-0">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-sm text-foreground">
          {field.label}
          {isEdited && (
            <span className="rounded bg-accent/20 px-1.5 py-0.5 text-[10px] text-accent-light">modified</span>
          )}
        </div>
        {field.description && <div className="mt-0.5 text-xs text-muted">{field.description}</div>}
      </div>

      <div className="ml-4 shrink-0">
        {isEditable ? (
          typeof value === 'boolean' ? (
            <button
              onClick={() => onEdit(!(displayVal as boolean))}
              className={cn(
                'flex h-7 w-12 items-center rounded-full px-0.5 transition-colors',
                displayVal ? 'bg-accent' : 'bg-gray-700'
              )}
            >
              <div
                className={cn(
                  'h-6 w-6 rounded-full bg-white shadow transition-transform',
                  displayVal ? 'translate-x-5' : 'translate-x-0'
                )}
              />
            </button>
          ) : (
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
                  onEdit(field.isPercentage ? raw / 100 : raw);
                }}
                className="w-24 rounded-md border border-border bg-background px-2 py-1 text-right text-sm text-foreground focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              />
              {field.isPercentage && <span className="text-xs text-muted">%</span>}
              {field.suffix && !field.isPercentage && <span className="text-xs text-muted">{field.suffix}</span>}
            </div>
          )
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
  const [settings, setSettings] = useState<TradingSettings | null>(null);
  const [activeTab, setActiveTab] = useState<SettingsTab>('trading');
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    fetchSettings()
      .then(setSettings)
      .catch(() => toast('Failed to load settings', 'error'));
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const editedCount = Object.keys(draft).length;

  const handleEdit = (key: string, val: unknown) => {
    setDraft((prev) => {
      const next = { ...prev };
      // If reverted to original, remove from draft
      if (settings && val === (settings as unknown as Record<string, unknown>)[key]) {
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
      setSettings(updated);
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Settings</h1>
          <p className="mt-1 text-sm text-muted">
            System configuration — runtime changes reset on restart
          </p>
        </div>
        {editedCount > 0 && (
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted">{editedCount} field(s) modified</span>
            <Button
              variant="secondary"
              icon={<RotateCcw className="h-4 w-4" />}
              onClick={handleReset}
            >
              Reset
            </Button>
            <Button
              icon={<Save className="h-4 w-4" />}
              loading={saving}
              onClick={handleSave}
            >
              Save Changes
            </Button>
          </div>
        )}
      </div>

      <div className="flex gap-6">
        {/* Sidebar Tabs */}
        <div className="w-48 shrink-0 space-y-1">
          {tabs.map(({ key, label, icon: Icon }) => {
            // Count editable fields with changes in this tab
            const tabEdits = FIELD_GROUPS[key].fields.filter((f) => f.key in draft).length;
            return (
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
        <div className="flex-1">
          <Card>
            <CardHeader title={group.title} subtitle={group.subtitle} />
            {group.fields.map((field) => (
              <SettingRow
                key={field.key}
                field={field}
                value={(settings as unknown as Record<string, unknown>)[field.key]}
                editedValue={draft[field.key]}
                onEdit={field.editable ? (val) => handleEdit(field.key, val) : undefined}
              />
            ))}
          </Card>
        </div>
      </div>
    </div>
  );
}
