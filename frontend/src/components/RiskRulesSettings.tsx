/**
 * Risk Rules Settings Component
 *
 * Unified risk management UI: global toggle, alert thresholds, and
 * configurable stop-loss / take-profit rule chains.
 * Rules are evaluated in priority order (lower = first).
 */

import { useEffect, useState, useCallback } from 'react';
import {
  fetchRiskRules,
  createRiskRule,
  updateRiskRule,
  deleteRiskRule,
  type RiskRuleData,
} from '@/api';
import {
  Plus,
  Trash2,
  Pencil,
  ChevronDown,
  ChevronRight,
  Save,
  X,
  Shield,
  ShieldAlert,
  Brain,
  TrendingDown,
  TrendingUp,
  AlertTriangle,
  PieChart,
  Activity,
  Info,
} from 'lucide-react';
import { cn } from '@/utils/cn';

/* ------------------------------------------------------------------ */
/* Props                                                               */
/* ------------------------------------------------------------------ */

interface RiskRulesSettingsProps {
  riskEnabled?: boolean;
  alertThresholds?: {
    portfolio_pnl_alert_threshold?: number;
    position_loss_alert_threshold?: number;
  };
  onUpdateSetting?: (key: string, val: unknown) => void;
}

/* ------------------------------------------------------------------ */
/* Constants                                                           */
/* ------------------------------------------------------------------ */

const RULE_TYPES = [
  { value: 'hard_stop_loss', label: 'Hard Stop Loss', icon: TrendingDown, color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/20', category: 'hard' },
  { value: 'hard_take_profit', label: 'Hard Take Profit', icon: TrendingUp, color: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/20', category: 'hard' },
  { value: 'trailing_stop', label: 'Trailing Stop', icon: Activity, color: 'text-amber-400', bg: 'bg-amber-500/10', border: 'border-amber-500/20', category: 'hard' },
  { value: 'daily_loss_limit', label: 'Daily Loss Limit', icon: AlertTriangle, color: 'text-red-300', bg: 'bg-red-400/10', border: 'border-red-400/20', category: 'hard' },
  { value: 'concentration_limit', label: 'Concentration Limit', icon: PieChart, color: 'text-yellow-400', bg: 'bg-yellow-500/10', border: 'border-yellow-500/20', category: 'hard' },
  { value: 'llm_stop_loss', label: 'LLM Stop Loss', icon: Brain, color: 'text-violet-400', bg: 'bg-violet-500/10', border: 'border-violet-500/20', category: 'llm' },
  { value: 'llm_take_profit', label: 'LLM Take Profit', icon: Brain, color: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/20', category: 'llm' },
] as const;

const RULE_ACTIONS = [
  { value: 'close', label: 'Close Position' },
  { value: 'llm_analyze', label: 'LLM Analysis' },
  { value: 'alert', label: 'Alert Only' },
  { value: 'reduce', label: 'Reduce Position' },
] as const;

function getRuleTypeInfo(type: string) {
  return RULE_TYPES.find((t) => t.value === type) ?? {
    value: type, label: type, icon: Shield, color: 'text-zinc-400',
    bg: 'bg-zinc-500/10', border: 'border-zinc-500/20', category: 'hard',
  };
}

function getActionLabel(action: string) {
  return RULE_ACTIONS.find((a) => a.value === action)?.label ?? action;
}

function isLLMType(type: string) {
  return type === 'llm_stop_loss' || type === 'llm_take_profit';
}

/* ------------------------------------------------------------------ */
/* Empty rule factory                                                  */
/* ------------------------------------------------------------------ */

function emptyRule(): RiskRuleData {
  return {
    name: '',
    type: 'hard_stop_loss',
    enabled: true,
    priority: 100,
    threshold: 0.05,
    action: 'close',
    reduce_ratio: 0.5,
    symbols: null,
    cooldown_seconds: 0,
    description: null,
  };
}

/* ------------------------------------------------------------------ */
/* Rule Row (compact table-like display)                               */
/* ------------------------------------------------------------------ */

function RuleRow({
  rule,
  onEdit,
  onDelete,
  onToggle,
}: {
  rule: RiskRuleData;
  onEdit: () => void;
  onDelete: () => void;
  onToggle: () => void;
}) {
  const typeInfo = getRuleTypeInfo(rule.type);
  const Icon = typeInfo.icon;
  const isLLM = isLLMType(rule.type);

  return (
    <div
      className={cn(
        'group flex items-center gap-3 rounded-lg border px-4 py-3 transition-all',
        rule.enabled
          ? 'border-zinc-700/60 bg-zinc-800/30 hover:border-zinc-600'
          : 'border-zinc-800/40 bg-zinc-900/20 opacity-50',
      )}
    >
      {/* Toggle */}
      <button
        onClick={onToggle}
        className={cn(
          'relative h-5 w-9 shrink-0 rounded-full transition-colors',
          rule.enabled ? 'bg-blue-600' : 'bg-zinc-700',
        )}
        title={rule.enabled ? 'Disable' : 'Enable'}
      >
        <span
          className={cn(
            'absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform',
            rule.enabled ? 'left-[18px]' : 'left-0.5',
          )}
        />
      </button>

      {/* Icon + Name */}
      <div className={cn('shrink-0 rounded-md p-1.5', typeInfo.bg)}>
        <Icon className={cn('h-3.5 w-3.5', typeInfo.color)} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-zinc-200 truncate">{rule.name}</span>
          {isLLM && (
            <span className="inline-flex items-center gap-0.5 rounded bg-violet-500/15 px-1.5 py-0.5 text-[10px] font-medium text-violet-300">
              <Brain className="h-2.5 w-2.5" /> AI
            </span>
          )}
        </div>
        {rule.description && (
          <p className="text-xs text-zinc-500 truncate mt-0.5">{rule.description}</p>
        )}
      </div>

      {/* Stats */}
      <div className="hidden sm:flex items-center gap-4 text-xs text-zinc-400 shrink-0">
        <span className="font-mono">{(rule.threshold * 100).toFixed(1)}%</span>
        <span className="w-24 text-center">{getActionLabel(rule.action)}</span>
        <span className="font-mono text-zinc-500 w-8 text-right">P{rule.priority}</span>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={onEdit}
          className="rounded p-1.5 text-zinc-500 hover:bg-zinc-700 hover:text-zinc-200 transition-colors"
          title="Edit"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={onDelete}
          className="rounded p-1.5 text-zinc-500 hover:bg-red-900/30 hover:text-red-400 transition-colors"
          title="Delete"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Rule Editor (inline form)                                           */
/* ------------------------------------------------------------------ */

function RuleEditor({
  rule,
  isNew,
  saving,
  onSave,
  onCancel,
  onChange,
}: {
  rule: RiskRuleData;
  isNew: boolean;
  saving: boolean;
  onSave: () => void;
  onCancel: () => void;
  onChange: (r: RiskRuleData) => void;
}) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="rounded-lg border border-blue-500/30 bg-blue-950/20 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2 text-sm font-medium text-zinc-200"
        >
          {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          {isNew ? 'New Rule' : `Edit: ${rule.name}`}
        </button>
        <div className="flex items-center gap-2">
          <button
            onClick={onCancel}
            className="inline-flex items-center gap-1 rounded-md px-3 py-1.5 text-xs text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200 transition-colors"
          >
            <X className="h-3 w-3" />
            Cancel
          </button>
          <button
            onClick={onSave}
            disabled={saving || !rule.name.trim()}
            className="inline-flex items-center gap-1 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-40 transition-colors"
          >
            <Save className="h-3 w-3" />
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Name" hint="Unique identifier">
            <input
              type="text"
              value={rule.name}
              onChange={(e) => onChange({ ...rule, name: e.target.value })}
              disabled={!isNew}
              placeholder="e.g. hard_sl_5pct"
              className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-white placeholder:text-zinc-600 focus:border-blue-500 focus:outline-none disabled:opacity-50 font-mono"
            />
          </Field>

          <Field label="Type">
            <select
              value={rule.type}
              onChange={(e) => {
                const newType = e.target.value;
                const autoAction = isLLMType(newType) ? 'llm_analyze' : rule.action;
                onChange({ ...rule, type: newType, action: autoAction });
              }}
              className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none"
            >
              {RULE_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </Field>

          <Field label="Action">
            <select
              value={rule.action}
              onChange={(e) => onChange({ ...rule, action: e.target.value })}
              className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none"
            >
              {RULE_ACTIONS.map((a) => (
                <option key={a.value} value={a.value}>{a.label}</option>
              ))}
            </select>
          </Field>

          <Field label="Threshold (%)" hint="e.g. 5.0 = 5%">
            <input
              type="number"
              step="0.1"
              value={(rule.threshold * 100).toFixed(1)}
              onChange={(e) => onChange({ ...rule, threshold: parseFloat(e.target.value) / 100 || 0 })}
              className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none font-mono"
            />
          </Field>

          <Field label="Priority" hint="Lower = evaluated first">
            <input
              type="number"
              value={rule.priority}
              onChange={(e) => onChange({ ...rule, priority: parseInt(e.target.value) || 100 })}
              className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none font-mono"
            />
          </Field>

          {rule.action === 'reduce' && (
            <Field label="Reduce (%)" hint="Position reduction ratio">
              <input
                type="number"
                step="1"
                value={(rule.reduce_ratio * 100).toFixed(0)}
                onChange={(e) => onChange({ ...rule, reduce_ratio: parseFloat(e.target.value) / 100 || 0.5 })}
                className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none font-mono"
              />
            </Field>
          )}

          <Field label="Cooldown (s)" hint="Min time between triggers">
            <input
              type="number"
              value={rule.cooldown_seconds}
              onChange={(e) => onChange({ ...rule, cooldown_seconds: parseInt(e.target.value) || 0 })}
              className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none font-mono"
            />
          </Field>

          <div className="sm:col-span-2 lg:col-span-3">
            <Field label="Description">
              <input
                type="text"
                value={rule.description ?? ''}
                onChange={(e) => onChange({ ...rule, description: e.target.value || null })}
                placeholder="Optional note"
                className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-white placeholder:text-zinc-600 focus:border-blue-500 focus:outline-none"
              />
            </Field>
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Field wrapper                                                       */
/* ------------------------------------------------------------------ */

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-zinc-400">{label}</label>
      {children}
      {hint && <p className="mt-0.5 text-[10px] text-zinc-600">{hint}</p>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Main Component                                                      */
/* ------------------------------------------------------------------ */

export default function RiskRulesSettings({
  riskEnabled,
  alertThresholds,
  onUpdateSetting,
}: RiskRulesSettingsProps) {
  const [rules, setRules] = useState<RiskRuleData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Editor state
  const [editingRule, setEditingRule] = useState<RiskRuleData | null>(null);
  const [isNew, setIsNew] = useState(false);

  /* ---- Load ---- */
  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await fetchRiskRules();
      setRules(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  /* ---- Handlers ---- */

  const handleAdd = () => {
    setEditingRule(emptyRule());
    setIsNew(true);
  };

  const handleEdit = (rule: RiskRuleData) => {
    setEditingRule({ ...rule });
    setIsNew(false);
  };

  const handleCancel = () => {
    setEditingRule(null);
    setIsNew(false);
  };

  const handleSave = async () => {
    if (!editingRule) return;
    try {
      setSaving(true);
      setError(null);
      if (isNew) {
        await createRiskRule(editingRule);
      } else {
        const { name, ...updates } = editingRule;
        await updateRiskRule(name, updates);
      }
      setEditingRule(null);
      setIsNew(false);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (name: string) => {
    if (!confirm(`Delete rule "${name}"?`)) return;
    try {
      setError(null);
      await deleteRiskRule(name);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleToggle = async (rule: RiskRuleData) => {
    try {
      setError(null);
      await updateRiskRule(rule.name, { enabled: !rule.enabled });
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  /* ---- Render ---- */

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="animate-spin rounded-full h-7 w-7 border-2 border-blue-500 border-t-transparent" />
      </div>
    );
  }

  const sortedRules = [...rules].sort((a, b) => a.priority - b.priority);
  const hardRules = sortedRules.filter((r) => !isLLMType(r.type));
  const llmRules = sortedRules.filter((r) => isLLMType(r.type));

  return (
    <div className="space-y-6">
      {/* Global Risk Toggle + Alert Thresholds */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <Shield className="h-5 w-5 text-blue-400" />
            <div>
              <h3 className="text-base font-semibold text-zinc-100">Risk Management</h3>
              <p className="text-xs text-zinc-500 mt-0.5">Global risk engine and alert thresholds</p>
            </div>
          </div>
          {onUpdateSetting && (
            <button
              onClick={() => onUpdateSetting('risk_management_enabled', !riskEnabled)}
              className={cn(
                'relative h-6 w-11 rounded-full transition-colors',
                riskEnabled ? 'bg-blue-600' : 'bg-zinc-700',
              )}
              title={riskEnabled ? 'Disable risk management' : 'Enable risk management'}
            >
              <span
                className={cn(
                  'absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform',
                  riskEnabled ? 'left-[22px]' : 'left-0.5',
                )}
              />
            </button>
          )}
        </div>

        {riskEnabled && onUpdateSetting && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-3 border-t border-zinc-800">
            <div>
              <label className="text-xs text-zinc-400 mb-1 block">Portfolio P&L Alert Threshold</label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  step="0.1"
                  value={
                    alertThresholds?.portfolio_pnl_alert_threshold != null
                      ? (alertThresholds.portfolio_pnl_alert_threshold * 100).toFixed(1)
                      : ''
                  }
                  onChange={(e) => {
                    const v = parseFloat(e.target.value);
                    if (!isNaN(v)) onUpdateSetting('portfolio_pnl_alert_threshold', v / 100);
                  }}
                  className="w-24 rounded-md border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-sm text-white text-right focus:border-blue-500 focus:outline-none font-mono"
                />
                <span className="text-xs text-zinc-500">%</span>
              </div>
              <p className="text-[10px] text-zinc-600 mt-0.5">Alert when daily P&L exceeds this</p>
            </div>
            <div>
              <label className="text-xs text-zinc-400 mb-1 block">Position Loss Alert Threshold</label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  step="0.1"
                  value={
                    alertThresholds?.position_loss_alert_threshold != null
                      ? (alertThresholds.position_loss_alert_threshold * 100).toFixed(1)
                      : ''
                  }
                  onChange={(e) => {
                    const v = parseFloat(e.target.value);
                    if (!isNaN(v)) onUpdateSetting('position_loss_alert_threshold', v / 100);
                  }}
                  className="w-24 rounded-md border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-sm text-white text-right focus:border-blue-500 focus:outline-none font-mono"
                />
                <span className="text-xs text-zinc-500">%</span>
              </div>
              <p className="text-[10px] text-zinc-600 mt-0.5">Alert when position loss exceeds this</p>
            </div>
          </div>
        )}
      </div>

      {/* Rules Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-zinc-200">Rule Chain</h3>
          <p className="text-xs text-zinc-500 mt-0.5">
            {sortedRules.length} rule{sortedRules.length !== 1 ? 's' : ''} — evaluated in priority order
          </p>
        </div>
        <button
          onClick={handleAdd}
          className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500 transition-colors"
        >
          <Plus className="h-3.5 w-3.5" />
          Add Rule
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-red-800/50 bg-red-900/20 px-3 py-2.5 text-sm text-red-300">
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Rule Editor */}
      {editingRule && (
        <RuleEditor
          rule={editingRule}
          isNew={isNew}
          saving={saving}
          onSave={handleSave}
          onCancel={handleCancel}
          onChange={setEditingRule}
        />
      )}

      {/* Rules display */}
      {sortedRules.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-zinc-700 py-12 text-center">
          <ShieldAlert className="h-8 w-8 text-zinc-600 mb-2" />
          <p className="text-sm text-zinc-400">No risk rules configured</p>
          <p className="text-xs text-zinc-600 mt-1">Click &ldquo;Add Rule&rdquo; to get started</p>
        </div>
      ) : (
        <div className="space-y-5">
          {/* Hard rules */}
          {hardRules.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 mb-1">
                <Shield className="h-3.5 w-3.5 text-zinc-500" />
                <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
                  Hard Rules
                </span>
                <span className="text-[10px] text-zinc-600">({hardRules.length})</span>
              </div>
              {hardRules.map((rule) => (
                <RuleRow
                  key={rule.name}
                  rule={rule}
                  onEdit={() => handleEdit(rule)}
                  onDelete={() => handleDelete(rule.name)}
                  onToggle={() => handleToggle(rule)}
                />
              ))}
            </div>
          )}

          {/* LLM rules */}
          {llmRules.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 mb-1">
                <Brain className="h-3.5 w-3.5 text-violet-400" />
                <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
                  LLM Analysis Triggers
                </span>
                <span className="text-[10px] text-zinc-600">({llmRules.length})</span>
              </div>
              {llmRules.map((rule) => (
                <RuleRow
                  key={rule.name}
                  rule={rule}
                  onEdit={() => handleEdit(rule)}
                  onDelete={() => handleDelete(rule.name)}
                  onToggle={() => handleToggle(rule)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Info */}
      <div className="flex items-start gap-2.5 rounded-lg bg-zinc-900/40 px-4 py-3 text-xs text-zinc-500">
        <Info className="h-3.5 w-3.5 mt-0.5 shrink-0 text-zinc-600" />
        <div className="space-y-1">
          <p>Rules are evaluated in ascending priority order. Once a &ldquo;Close&rdquo; action fires for a position, subsequent rules are skipped for that position.</p>
          <p>LLM rules trigger an AI agent for evaluation instead of executing trades directly. Set them at a wider threshold than hard rules.</p>
          <p>Persisted to <code className="rounded bg-zinc-800 px-1 py-0.5 text-zinc-400 text-[10px]">user_data/risk_rules.yaml</code></p>
        </div>
      </div>
    </div>
  );
}
