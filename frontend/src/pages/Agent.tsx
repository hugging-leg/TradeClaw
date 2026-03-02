import { useEffect, useState, useCallback, useRef } from 'react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast';
import {
  fetchDecisions,
  fetchAnalyses,
  exportAnalyses,
  exportDecisions,
  fetchExecutionTriggers,
  fetchBacktestSummaries,
  fetchAgentMessages,
  fetchWorkflows,
  reloadWorkflows,
  fetchAgentTools,
  fetchWorkflowExecutions,
  fetchActiveWorkflow,
  fetchAgentConfig,
  updateAgentConfig,
  switchWorkflow,
  triggerAnalysis,
  toggleAgentTool,
  sendAgentChat,
  fetchChatQueue,
  cancelQueuedMessage,
  clearChatQueue,
  fetchLLMModels,
} from '@/api';
import type { BacktestSummary, ExportFilter } from '@/api';
import { useLiveExecution } from '@/api/useAgentEvents';
import { formatCurrency, formatRelative, formatDuration } from '@/utils/format';
import { cn } from '@/utils/cn';
import {
  Bot,
  Play,
  ArrowUpRight,
  ArrowDownRight,
  BarChart3,
  CheckCircle,
  XCircle,
  MessageSquare,
  Wrench,
  User,
  Cpu,
  Eye,
  Clock,
  Zap,
  Brain,
  Database,
  TrendingUp,
  Settings2,
  ChevronDown,
  ChevronRight,
  Send,
  Loader2,
  Save,
  RotateCcw,
  Shuffle,
  RefreshCw,
  Package,
  Puzzle,
  X,
  Trash2,
  EyeOff,
  Download,
  FileJson,
  ChevronLeft,
  Sparkles,
} from 'lucide-react';
import type {
  TradingDecision,
  AnalysisHistory,
  AgentMessage,
  WorkflowInfo,
  AgentTool,
  AgentConfig,
  ActiveWorkflow,
  WorkflowExecution,
  ExecutionStep,
  QueuedMessage,
  LLMModelRef,
} from '@/types';

type Tab = 'execution' | 'tools' | 'config' | 'decisions' | 'analyses' | 'messages';

const TOOL_CATEGORY_META: Record<string, { label: string; color: string; icon: typeof Database }> = {
  data: { label: 'Data', color: 'bg-blue-500/15 text-blue-400', icon: Database },
  trading: { label: 'Trading', color: 'bg-emerald-500/15 text-emerald-400', icon: TrendingUp },
  analysis: { label: 'Analysis', color: 'bg-purple-500/15 text-purple-400', icon: Brain },
  system: { label: 'System', color: 'bg-amber-500/15 text-amber-400', icon: Settings2 },
};

const STEP_TYPE_META: Record<string, { label: string; color: string; icon: typeof Brain }> = {
  llm_reasoning: { label: 'Reasoning', color: 'text-orange-400', icon: Sparkles },
  llm_thinking: { label: 'Thinking', color: 'text-purple-400', icon: Brain },
  tool_call: { label: 'Tool', color: 'text-blue-400', icon: Wrench },
  decision: { label: 'Decision', color: 'text-emerald-400', icon: Zap },
  notification: { label: 'Info', color: 'text-amber-400', icon: Send },
  user_message: { label: 'User', color: 'text-sky-400', icon: User },
};

/** Fallback for unknown step types — 不硬编码 workflow-specific 类型 */
const DEFAULT_STEP_META = { label: 'Step', color: 'text-cyan-400', icon: Zap };

// ========== Config field rendering helpers ==========

/** Fields that should be rendered as textarea instead of input */
const TEXTAREA_FIELDS = new Set(['system_prompt']);

/** Fields that should be rendered as password input */
const PASSWORD_FIELDS = new Set(['llm_api_key']);

/** Fields that should be rendered as model dropdown (references LLM config) */
const MODEL_SELECT_FIELDS = new Set(['llm_model']);

/** Fields that are read-only (shown but not editable) */
const READONLY_FIELDS = new Set(['workflow_type', 'name']);

/** Fields that should be hidden when null (not applicable for this workflow) */
const HIDE_WHEN_NULL = new Set(['system_prompt']);

/** Detect field type for rendering */
function detectFieldType(key: string, value: unknown): 'textarea' | 'number' | 'array' | 'boolean' | 'password' | 'model_select' | 'text' {
  if (TEXTAREA_FIELDS.has(key)) return 'textarea';
  if (PASSWORD_FIELDS.has(key)) return 'password';
  if (MODEL_SELECT_FIELDS.has(key)) return 'model_select';
  if (typeof value === 'number') return 'number';
  if (typeof value === 'boolean') return 'boolean';
  if (Array.isArray(value)) return 'array';
  return 'text';
}

/** Human-readable label from snake_case key */
function fieldLabel(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/\bLlm\b/, 'LLM')
    .replace(/\bBl\b/, 'BL')
    .replace(/\bCa\b/, 'CA');
}

/** Password field with show/hide toggle */
function PasswordField({ value, onChange }: { value: unknown; onChange: (v: string) => void }) {
  const [show, setShow] = useState(false);
  return (
    <div className="flex items-center gap-1.5">
      <input
        type={show ? 'text' : 'password'}
        value={value != null ? String(value) : ''}
        placeholder="Enter new value to update…"
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-border bg-background px-3 py-2 font-mono text-sm text-foreground placeholder:text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent sm:max-w-sm"
      />
      <button
        type="button"
        onClick={() => setShow((p) => !p)}
        className="rounded p-1.5 text-muted hover:text-foreground transition-colors"
        title={show ? 'Hide' : 'Show'}
      >
        {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
}

// ========== Sub-components ==========

function ExecutionStepItem({
  step,
  isLast,
  streamingText,
}: {
  step: ExecutionStep;
  isLast: boolean;
  /** 实时 LLM token 流（仅 running 的 llm_thinking step 有值） */
  streamingText?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const meta = STEP_TYPE_META[step.type] || DEFAULT_STEP_META;
  const Icon = meta.icon;
  const streamRef = useRef<HTMLDivElement>(null);

  // 自动展开正在运行的步骤
  const isRunning = step.status === 'running';
  const hasStreaming = !!streamingText;

  // 自动滚动到底部（streaming 时）
  useEffect(() => {
    if (hasStreaming && streamRef.current) {
      streamRef.current.scrollTop = streamRef.current.scrollHeight;
    }
  }, [streamingText, hasStreaming]);

  const statusColor = {
    pending: 'border-gray-600 bg-gray-800',
    running: 'border-accent bg-accent/20 animate-pulse',
    completed: 'border-emerald-500 bg-emerald-500/20',
    failed: 'border-red-500 bg-red-500/20',
    skipped: 'border-gray-600 bg-gray-800/50',
  }[step.status];

  const showDetails = expanded || isRunning;

  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <div className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2', statusColor)}>
          {isRunning ? (
            <Loader2 className={cn('h-4 w-4 animate-spin', meta.color)} />
          ) : step.status === 'failed' ? (
            <XCircle className="h-4 w-4 text-red-400" />
          ) : step.status === 'pending' ? (
            <Clock className="h-4 w-4 text-gray-400" />
          ) : (
            <Icon className={cn('h-4 w-4', meta.color)} />
          )}
        </div>
        {!isLast && <div className="w-px flex-1 bg-border" />}
      </div>
      <div className={cn('mb-4 min-w-0 flex-1 pb-1', isLast && 'mb-0')}>
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex w-full items-center gap-2 text-left"
        >
          {showDetails ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted" />
          )}
          <span className="text-sm font-medium text-foreground">{step.name}</span>
          <Badge variant="muted">
            {STEP_TYPE_META[step.type]
              ? meta.label
              : step.type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
          </Badge>
          {step.duration_ms !== undefined && (
            <span className="ml-auto text-xs text-muted">{step.duration_ms}ms</span>
          )}
          {isRunning && !step.duration_ms && (
            <span className="ml-auto text-xs text-accent-light">running...</span>
          )}
        </button>

        {/* LLM Streaming Text — 类似 Cursor 的实时打字机效果 */}
        {hasStreaming && (
          <div
            ref={streamRef}
            className="mt-2 max-h-48 overflow-y-auto rounded-lg border border-accent/20 bg-gray-950/80 p-3 pl-5"
          >
            <pre className="whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
              {streamingText}
              <span className="inline-block h-4 w-1.5 animate-pulse bg-accent-light" />
            </pre>
          </div>
        )}

        {showDetails && !hasStreaming && (
          <div className="mt-2 space-y-2 pl-5">
            {step.input && (
              <div className="rounded-lg bg-gray-900/50 p-3">
                <span className="mb-1 block text-xs font-medium text-muted">Input</span>
                <pre className="overflow-x-auto text-xs text-muted-foreground">{step.input}</pre>
              </div>
            )}
            {step.output && (
              <div className="rounded-lg bg-gray-900/50 p-3">
                <span className="mb-1 block text-xs font-medium text-muted">Output</span>
                <pre className="overflow-x-auto whitespace-pre-wrap text-xs text-muted-foreground">{step.output}</pre>
              </div>
            )}
            {step.error && (
              <div className="rounded-lg bg-red-950/30 p-3">
                <span className="mb-1 block text-xs font-medium text-red-400">Error</span>
                <pre className="overflow-x-auto text-xs text-red-300">{step.error}</pre>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function ExecutionCard({
  execution,
  streamingTexts,
  defaultExpanded,
}: {
  execution: WorkflowExecution;
  /** LLM token 流式文本（step_id -> accumulated text） */
  streamingTexts?: Record<string, string>;
  /** 是否默认展开（live execution 默认展开） */
  defaultExpanded?: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded ?? false);
  const isLive = execution.status === 'running';

  // Live execution 自动展开
  useEffect(() => {
    if (isLive) setExpanded(true);
  }, [isLive]);

  const statusBadge = {
    running: <Badge variant="info">Running</Badge>,
    completed: <Badge variant="profit">Completed</Badge>,
    failed: <Badge variant="loss">Failed</Badge>,
  }[execution.status];

  const successSteps = execution.steps.filter((s) => s.status === 'completed').length;
  const failedSteps = execution.steps.filter((s) => s.status === 'failed').length;
  const runningSteps = execution.steps.filter((s) => s.status === 'running').length;

  return (
    <Card>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2.5 text-left sm:gap-3"
      >
        <div className={cn(
          'flex h-9 w-9 shrink-0 items-center justify-center rounded-xl sm:h-10 sm:w-10',
          execution.status === 'completed' && 'bg-emerald-500/15',
          execution.status === 'failed' && 'bg-red-500/15',
          execution.status === 'running' && 'bg-accent/15',
        )}>
          {execution.status === 'running' ? (
            <Loader2 className="h-4 w-4 animate-spin text-accent-light sm:h-5 sm:w-5" />
          ) : execution.status === 'completed' ? (
            <CheckCircle className="h-4 w-4 text-emerald-400 sm:h-5 sm:w-5" />
          ) : (
            <XCircle className="h-4 w-4 text-red-400 sm:h-5 sm:w-5" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
            <span className="text-sm font-semibold text-foreground">{execution.trigger}</span>
            {statusBadge}
            <Badge variant="muted">{execution.workflow_type}</Badge>
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-muted sm:mt-1 sm:text-xs">
            <span>{formatRelative(execution.started_at)}</span>
            {execution.total_duration_ms && (
              <span>Duration: {formatDuration(execution.total_duration_ms / 1000)}</span>
            )}
            {isLive ? (
              <span>
                {successSteps} done
                {runningSteps > 0 ? `, ${runningSteps} running` : ''}
                {failedSteps > 0 ? `, ${failedSteps} failed` : ''}
              </span>
            ) : (
              <span>{successSteps} completed{failedSteps > 0 ? `, ${failedSteps} failed` : ''}</span>
            )}
          </div>
        </div>
        {expanded ? (
          <ChevronDown className="h-4 w-4 shrink-0 text-muted sm:h-5 sm:w-5" />
        ) : (
          <ChevronRight className="h-4 w-4 shrink-0 text-muted sm:h-5 sm:w-5" />
        )}
      </button>
      {expanded && (
        <div className="mt-4 border-t border-border pt-4">
          {execution.steps.map((step, i) => (
            <ExecutionStepItem
              key={step.id}
              step={step}
              isLast={i === execution.steps.length - 1}
              streamingText={streamingTexts?.[step.id]}
            />
          ))}
          {isLive && execution.steps.length === 0 && (
            <div className="flex items-center gap-2 py-4 text-sm text-muted">
              <Loader2 className="h-4 w-4 animate-spin" />
              Waiting for agent to start...
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function ToolCard({ tool, onToggle }: { tool: AgentTool; onToggle: (name: string) => void }) {
  const [showParams, setShowParams] = useState(false);
  const catMeta = TOOL_CATEGORY_META[tool.category] || TOOL_CATEGORY_META.system;
  const CatIcon = catMeta.icon;

  return (
    <Card hover className={cn(!tool.enabled && 'opacity-50')}>
      <div className="flex items-start gap-3">
        <div className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-lg sm:h-9 sm:w-9', catMeta.color)}>
          <CatIcon className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="truncate font-mono text-xs font-semibold text-foreground sm:text-sm">{tool.name}</span>
                <Badge variant="muted">{catMeta.label}</Badge>
              </div>
              <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground sm:mt-1 sm:text-xs">{tool.description}</p>
            </div>
            <button
              onClick={() => onToggle(tool.name)}
              className={cn(
                'flex h-6 w-10 shrink-0 items-center rounded-full px-0.5 transition-colors sm:h-7 sm:w-12',
                tool.enabled ? 'bg-accent' : 'bg-gray-700'
              )}
            >
              <div
                className={cn(
                  'h-5 w-5 rounded-full bg-white shadow transition-transform sm:h-6 sm:w-6',
                  tool.enabled ? 'translate-x-4 sm:translate-x-5' : 'translate-x-0'
                )}
              />
            </button>
          </div>
        </div>
      </div>
      {tool.parameters.length > 0 && (
        <div className="mt-2 sm:mt-3">
          <button
            onClick={() => setShowParams(!showParams)}
            className="flex items-center gap-1 text-xs text-muted hover:text-foreground"
          >
            {showParams ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            {tool.parameters.length} parameter{tool.parameters.length > 1 ? 's' : ''}
          </button>
          {showParams && (
            <div className="mt-2 space-y-1.5">
              {tool.parameters.map((p) => (
                <div key={p.name} className="flex flex-wrap items-center gap-1.5 rounded-md bg-gray-900/50 px-2.5 py-1.5 text-xs sm:gap-2 sm:px-3">
                  <code className="font-medium text-foreground">{p.name}</code>
                  <Badge variant="muted">{p.type}</Badge>
                  {p.required && <Badge variant="loss">required</Badge>}
                  <span className="basis-full text-muted-foreground sm:basis-auto">{p.description}</span>
                  {p.default_value && (
                    <span className="text-muted sm:ml-auto">default: {p.default_value}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

// ========== Config Editor ==========

function ConfigEditor({
  config,
  onSave,
  saving,
  allModels,
}: {
  config: AgentConfig;
  onSave: (updates: Record<string, unknown>) => Promise<void>;
  saving: boolean;
  allModels: LLMModelRef[];
}) {
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [editedKeys, setEditedKeys] = useState<Set<string>>(new Set());

  // Reset draft when config changes (e.g. after save or workflow switch)
  useEffect(() => {
    setDraft({});
    setEditedKeys(new Set());
  }, [config]);

  const getValue = (key: string) => (key in draft ? draft[key] : config[key]);

  const handleChange = (key: string, raw: string | boolean) => {
    const original = config[key];
    let parsed: unknown = raw;

    // Type-aware parsing
    if (typeof original === 'number' && typeof raw === 'string') {
      const n = Number(raw);
      parsed = isNaN(n) ? raw : n;
    }
    if (Array.isArray(original) && typeof raw === 'string') {
      parsed = raw.split(',').map((s) => s.trim()).filter(Boolean);
    }

    setDraft((prev) => ({ ...prev, [key]: parsed }));
    setEditedKeys((prev) => {
      const next = new Set(prev);
      // If reverted to original, remove from edited set
      if (JSON.stringify(parsed) === JSON.stringify(original)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const handleReset = () => {
    setDraft({});
    setEditedKeys(new Set());
  };

  const handleSave = async () => {
    // Only send changed fields
    const updates: Record<string, unknown> = {};
    for (const key of editedKeys) {
      updates[key] = draft[key];
    }
    await onSave(updates);
  };

  // Separate config keys into groups, hide null fields that are not applicable
  const allKeys = Object.keys(config);
  const readonlyKeys = allKeys.filter((k) => READONLY_FIELDS.has(k));
  const editableKeys = allKeys.filter(
    (k) => !READONLY_FIELDS.has(k) && !(HIDE_WHEN_NULL.has(k) && config[k] == null)
  );

  return (
    <div className="space-y-5">
      {/* Readonly info */}
      <div className="flex flex-wrap items-center gap-3 sm:gap-4">
        {readonlyKeys.map((key) => (
          <div key={key} className="flex items-center gap-1.5">
            <span className="text-xs text-muted">{fieldLabel(key)}:</span>
            <Badge variant="info">{String(config[key])}</Badge>
          </div>
        ))}
      </div>

      {/* Editable fields */}
      <div className="space-y-4">
        {editableKeys.map((key) => {
          const value = getValue(key);
          const type = detectFieldType(key, config[key]);
          const isEdited = editedKeys.has(key);

          return (
            <div key={key}>
              <label className="mb-1.5 flex flex-wrap items-center gap-1.5 text-xs font-medium text-foreground sm:gap-2 sm:text-sm">
                {fieldLabel(key)}
                {isEdited && (
                  <span className="rounded bg-accent/20 px-1.5 py-0.5 text-[10px] text-accent-light">modified</span>
                )}
              </label>

              {type === 'textarea' ? (
                <textarea
                  value={value != null ? String(value) : ''}
                  onChange={(e) => handleChange(key, e.target.value)}
                  rows={8}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 font-mono text-xs text-foreground placeholder:text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                />
              ) : type === 'number' ? (
                <input
                  type="number"
                  step="any"
                  value={value != null ? String(value) : ''}
                  onChange={(e) => handleChange(key, e.target.value)}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent sm:max-w-xs"
                />
              ) : type === 'boolean' ? (
                <button
                  onClick={() => handleChange(key, !(value as boolean))}
                  className={cn(
                    'flex h-7 w-12 items-center rounded-full px-0.5 transition-colors',
                    value ? 'bg-accent' : 'bg-gray-700'
                  )}
                >
                  <div
                    className={cn(
                      'h-6 w-6 rounded-full bg-white shadow transition-transform',
                      value ? 'translate-x-5' : 'translate-x-0'
                    )}
                  />
                </button>
              ) : type === 'array' ? (
                <input
                  type="text"
                  value={Array.isArray(value) ? (value as string[]).join(', ') : String(value ?? '')}
                  onChange={(e) => handleChange(key, e.target.value)}
                  placeholder="Comma-separated values"
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                />
              ) : type === 'password' ? (
                <PasswordField value={value} onChange={(v) => handleChange(key, v)} />
              ) : type === 'model_select' ? (
                <select
                  value={value != null ? String(value) : ''}
                  onChange={(e) => handleChange(key, e.target.value)}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent sm:max-w-sm"
                >
                  <option value="">— use default (role: agent) —</option>
                  {allModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} ({m.provider_name} / {m.model_id})
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  value={value != null ? String(value) : ''}
                  onChange={(e) => handleChange(key, e.target.value)}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                />
              )}
            </div>
          );
        })}
      </div>

      {/* Actions */}
      <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4 sm:gap-3">
        <Button
          icon={<Save className="h-4 w-4" />}
          onClick={handleSave}
          loading={saving}
          disabled={editedKeys.size === 0}
        >
          Save
        </Button>
        <Button
          variant="secondary"
          icon={<RotateCcw className="h-4 w-4" />}
          onClick={handleReset}
          disabled={editedKeys.size === 0}
        >
          Reset
        </Button>
        {editedKeys.size > 0 && (
          <span className="text-xs text-muted">
            {editedKeys.size} field{editedKeys.size > 1 ? 's' : ''} modified
            <span className="hidden sm:inline"> (persisted to YAML)</span>
          </span>
        )}
      </div>
    </div>
  );
}

// ========== Workflow Switcher ==========

function WorkflowSwitcher({
  active,
  workflows,
  onSwitch,
  onReload,
  switching,
  reloading,
}: {
  active: ActiveWorkflow | null;
  workflows: Record<string, WorkflowInfo>;
  onSwitch: (type: string) => void;
  onReload: () => void;
  switching: boolean;
  reloading: boolean;
}) {
  const [showPicker, setShowPicker] = useState(false);

  const currentWf = active?.workflow_type ? workflows[active.workflow_type] : null;

  return (
    <div className="space-y-4">
      {/* Current workflow */}
      <Card className="border-accent/30 bg-accent/5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
          <div className="flex items-center gap-3 sm:gap-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent/15 sm:h-12 sm:w-12">
              <Bot className="h-5 w-5 text-accent-light sm:h-6 sm:w-6" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
                <h3 className="text-sm font-semibold text-foreground">
                  {active?.name ?? 'Loading...'}
                </h3>
                <Badge variant="info">{active?.workflow_type ?? '—'}</Badge>
                {currentWf?.builtin ? (
                  <Badge variant="muted">
                    <Package className="mr-1 h-3 w-3" />Built-in
                  </Badge>
                ) : currentWf ? (
                  <Badge variant="info">
                    <Puzzle className="mr-1 h-3 w-3" />Custom
                  </Badge>
                ) : null}
                {active?.is_running && <Badge variant="profit">Running</Badge>}
              </div>
              {active?.stats && (
                <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted">
                  <span>Runs: {String(active.stats.total_runs ?? 0)}</span>
                  <span>Success: {String(active.stats.successful_runs ?? 0)}</span>
                  <span>Failed: {String(active.stats.failed_runs ?? 0)}</span>
                  {active.stats.last_run != null && (
                    <span>Last: {formatRelative(String(active.stats.last_run))}</span>
                  )}
                </div>
              )}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2 self-end sm:self-center">
            <Button
              variant="ghost"
              icon={<RefreshCw className={cn('h-4 w-4', reloading && 'animate-spin')} />}
              onClick={onReload}
              loading={reloading}
              title="Reload external workflows"
            />
            <Button
              variant="secondary"
              icon={<Shuffle className="h-4 w-4" />}
              onClick={() => setShowPicker(!showPicker)}
              loading={switching}
            >
              Switch
            </Button>
          </div>
        </div>
      </Card>

      {/* Workflow picker */}
      {showPicker && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Object.entries(workflows).map(([key, wf]) => {
            const isCurrent = key === active?.workflow_type;
            return (
              <Card
                key={key}
                hover={!isCurrent}
                className={cn(
                  'cursor-pointer transition-all',
                  isCurrent && 'border-accent/40 bg-accent/5',
                  !isCurrent && 'hover:border-accent/20'
                )}
              >
                <button
                  className="w-full text-left"
                  disabled={isCurrent || switching}
                  onClick={() => {
                    onSwitch(key);
                    setShowPicker(false);
                  }}
                >
                  <div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <h3 className="text-sm font-semibold text-foreground">{wf.name}</h3>
                      {wf.builtin ? (
                        <Badge variant="muted">
                          <Package className="mr-1 h-3 w-3" />Built-in
                        </Badge>
                      ) : (
                        <Badge variant="info">
                          <Puzzle className="mr-1 h-3 w-3" />Custom
                        </Badge>
                      )}
                      {isCurrent && <Badge variant="profit">Active</Badge>}
                      {wf.deprecated && <Badge variant="loss">Deprecated</Badge>}
                    </div>
                    <p className="mt-1 text-xs text-muted">{wf.description}</p>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-1">
                    {wf.features.slice(0, 3).map((f) => (
                      <Badge key={f} variant="muted">{f}</Badge>
                    ))}
                  </div>
                  {wf.best_for && (
                    <p className="mt-2 text-xs text-accent-light">{wf.best_for}</p>
                  )}
                </button>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ========== Chat Input ==========

function AgentChatInput({
  isRunning,
  queueSize: initialQueueSize,
  onSend,
}: {
  isRunning: boolean;
  queueSize: number;
  onSend: (message: string) => Promise<void>;
}) {
  const { toast } = useToast();
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [queuedMessages, setQueuedMessages] = useState<QueuedMessage[]>([]);
  const [showQueue, setShowQueue] = useState(false);
  const [cancellingIndex, setCancellingIndex] = useState<number | null>(null);
  const [clearing, setClearing] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 当 agent 运行时且有队列消息，定期拉取队列内容
  const refreshQueue = useCallback(async () => {
    try {
      const data = await fetchChatQueue();
      setQueuedMessages(data.messages);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (isRunning && initialQueueSize > 0) {
      refreshQueue();
      // 每 2 秒刷新一次队列（消息被消费时更新）
      pollRef.current = setInterval(refreshQueue, 2000);
    } else if (!isRunning) {
      setQueuedMessages([]);
      setShowQueue(false);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [isRunning, initialQueueSize, refreshQueue]);

  const handleSubmit = async () => {
    const text = message.trim();
    if (!text || sending) return;
    setSending(true);
    try {
      await onSend(text);
      setMessage('');
      // 发送后刷新队列
      if (isRunning) {
        setTimeout(refreshQueue, 300);
      }
      setTimeout(() => inputRef.current?.focus(), 50);
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleCancelMessage = async (index: number) => {
    setCancellingIndex(index);
    try {
      await cancelQueuedMessage(index);
      toast('Message cancelled', 'info');
      await refreshQueue();
    } catch {
      toast('Failed to cancel message', 'error');
    } finally {
      setCancellingIndex(null);
    }
  };

  const handleClearQueue = async () => {
    setClearing(true);
    try {
      const result = await clearChatQueue();
      toast(`Cleared ${result.cleared} message(s)`, 'info');
      setQueuedMessages([]);
      setShowQueue(false);
    } catch {
      toast('Failed to clear queue', 'error');
    } finally {
      setClearing(false);
    }
  };

  const effectiveQueueSize = queuedMessages.length || initialQueueSize;

  return (
    <div className="sticky bottom-0 z-10 -mx-4 border-t border-border bg-background/95 px-3 py-2.5 backdrop-blur-sm sm:px-4 sm:py-3 md:-mx-6 md:px-6">
      {/* Queued messages panel — Cursor-like queue display */}
      {isRunning && effectiveQueueSize > 0 && (
        <div className="mb-3">
          <button
            onClick={() => { setShowQueue(!showQueue); if (!showQueue) refreshQueue(); }}
            className="flex w-full items-center gap-2 rounded-lg border border-accent/20 bg-accent/5 px-3 py-2 text-left transition-colors hover:bg-accent/10"
          >
            <span className="relative flex h-2 w-2 shrink-0">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
            </span>
            <span className="flex-1 text-xs font-medium text-accent-light">
              {effectiveQueueSize} message{effectiveQueueSize > 1 ? 's' : ''} queued
            </span>
            <span className="text-[10px] text-muted">
              {showQueue ? 'click to collapse' : 'click to manage'}
            </span>
            {showQueue ? (
              <ChevronDown className="h-3.5 w-3.5 text-muted" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 text-muted" />
            )}
          </button>

          {showQueue && (
            <div className="mt-2 space-y-1.5">
              {queuedMessages.map((msg, i) => (
                <div
                  key={`${msg.index}-${msg.text.slice(0, 20)}`}
                  className="group flex items-center gap-2 rounded-lg border border-border/50 bg-card px-3 py-2"
                >
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent/15 text-[10px] font-bold text-accent-light">
                    {i + 1}
                  </span>
                  <p className="min-w-0 flex-1 truncate text-xs text-foreground">{msg.preview}</p>
                  <button
                    onClick={() => handleCancelMessage(msg.index)}
                    disabled={cancellingIndex === msg.index}
                    className="shrink-0 rounded-md p-1 text-muted opacity-0 transition-all hover:bg-loss-bg hover:text-loss group-hover:opacity-100 disabled:opacity-50"
                    title="Cancel this message"
                  >
                    {cancellingIndex === msg.index ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <X className="h-3.5 w-3.5" />
                    )}
                  </button>
                </div>
              ))}
              {queuedMessages.length > 1 && (
                <button
                  onClick={handleClearQueue}
                  disabled={clearing}
                  className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-border py-1.5 text-xs text-muted transition-colors hover:border-loss/30 hover:text-loss"
                >
                  {clearing ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Trash2 className="h-3 w-3" />
                  )}
                  Clear all queued messages
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* Status indicator */}
      <div className="mb-1.5 flex items-center gap-2 text-[11px] text-muted sm:mb-2 sm:text-xs">
        {isRunning ? (
          <>
            <span className="relative flex h-2 w-2 shrink-0">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
            </span>
            <span className="text-accent-light">Agent running</span>
            <span className="hidden text-muted sm:inline">— new messages will be queued</span>
          </>
        ) : (
          <>
            <span className="h-2 w-2 shrink-0 rounded-full bg-muted/40" />
            <span>
              <span className="sm:hidden">Send a message to start analysis</span>
              <span className="hidden sm:inline">Agent idle — send a message to start a new analysis</span>
            </span>
          </>
        )}
      </div>

      {/* Input area */}
      <div className="flex items-end gap-2">
        <div className="relative flex-1">
          <textarea
            ref={inputRef}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isRunning ? 'Add instructions for the agent...' : 'Ask the agent to analyze, trade, or explain...'}
            rows={1}
            className={cn(
              'w-full resize-none rounded-xl border bg-card px-4 py-2.5 pr-12 text-sm text-foreground',
              'placeholder:text-muted/60',
              'focus:border-accent/50 focus:outline-none focus:ring-2 focus:ring-accent/20',
              'transition-colors',
              'max-h-32 min-h-[40px]',
              'border-border',
            )}
            style={{
              height: 'auto',
              minHeight: '40px',
            }}
            onInput={(e) => {
              const target = e.target as HTMLTextAreaElement;
              target.style.height = 'auto';
              target.style.height = Math.min(target.scrollHeight, 128) + 'px';
            }}
          />
        </div>
        <button
          onClick={handleSubmit}
          disabled={!message.trim() || sending}
          className={cn(
            'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-all',
            message.trim() && !sending
              ? 'bg-accent text-white hover:bg-accent-light shadow-sm'
              : 'bg-card-hover text-muted cursor-not-allowed',
          )}
        >
          {sending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </button>
      </div>
    </div>
  );
}

// ========== Export Dialog ==========

function ExportMenu({
  type,
  onExport,
  exporting,
}: {
  type: 'executions' | 'analyses' | 'decisions';
  onExport: (format: 'csv' | 'json', opts?: ExportFilter) => void;
  exporting: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [triggers, setTriggers] = useState<string[]>([]);
  const [backtests, setBacktests] = useState<BacktestSummary[]>([]);
  const [selectedTrigger, setSelectedTrigger] = useState<string>('');
  const [selectedBacktest, setSelectedBacktest] = useState<string>('');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');
  const [preset, setPreset] = useState<string>('7d');
  const menuRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  // Load triggers + backtest list when menu opens
  useEffect(() => {
    if (open && type !== 'decisions') {
      fetchExecutionTriggers().then(setTriggers).catch(() => {});
      fetchBacktestSummaries().then(setBacktests).catch(() => {});
    }
  }, [open, type]);

  // Reset backtest selection when trigger changes
  useEffect(() => {
    if (selectedTrigger !== 'backtest') setSelectedBacktest('');
  }, [selectedTrigger]);

  // Apply date preset
  useEffect(() => {
    if (preset === 'custom') return;
    const today = new Date();
    const to = today.toISOString().slice(0, 10);
    setDateTo(to);
    if (preset === '7d') {
      const d = new Date(today); d.setDate(d.getDate() - 7);
      setDateFrom(d.toISOString().slice(0, 10));
    } else if (preset === '30d') {
      const d = new Date(today); d.setDate(d.getDate() - 30);
      setDateFrom(d.toISOString().slice(0, 10));
    } else if (preset === '90d') {
      const d = new Date(today); d.setDate(d.getDate() - 90);
      setDateFrom(d.toISOString().slice(0, 10));
    } else if (preset === 'all') {
      setDateFrom('');
      setDateTo('');
    }
  }, [preset]);

  const handleExport = (format: 'csv' | 'json') => {
    const opts: ExportFilter = {};
    if (selectedTrigger) opts.trigger = selectedTrigger;
    if (selectedBacktest) opts.backtest_id = selectedBacktest;
    if (dateFrom) opts.date_from = dateFrom;
    if (dateTo) opts.date_to = dateTo;
    onExport(format, Object.keys(opts).length > 0 ? opts : undefined);
    setOpen(false);
  };

  const formatBacktestLabel = (bt: BacktestSummary) => {
    const date = bt.created_at ? new Date(bt.created_at).toLocaleDateString() : '';
    return `${bt.id.slice(0, 8)} · ${bt.start_date}~${bt.end_date} (${date})`;
  };

  const inputCls = 'w-full rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs text-foreground focus:border-accent focus:outline-none';

  return (
    <div className="relative" ref={menuRef}>
      <Button
        variant="ghost"
        icon={exporting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
        disabled={exporting}
        onClick={() => setOpen(!open)}
      >
        <span className="hidden sm:inline">Export</span>
      </Button>
      {open && (
        <div className="absolute right-0 top-full z-20 mt-1 w-72 rounded-xl border border-border bg-card p-3 shadow-xl sm:w-80">
          <p className="mb-2.5 text-xs font-semibold text-foreground">Export {type}</p>

          {/* Date range presets */}
          <div className="mb-2.5">
            <label className="mb-1 block text-[11px] text-muted">Time range</label>
            <div className="flex flex-wrap gap-1">
              {[
                { value: '7d', label: '7 days' },
                { value: '30d', label: '30 days' },
                { value: '90d', label: '90 days' },
                { value: 'all', label: 'All' },
                { value: 'custom', label: 'Custom' },
              ].map((p) => (
                <button
                  key={p.value}
                  onClick={() => setPreset(p.value)}
                  className={`rounded-md px-2 py-1 text-[11px] font-medium transition-colors ${
                    preset === p.value
                      ? 'bg-accent text-white'
                      : 'bg-surface-2 text-muted hover:text-foreground'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {/* Custom date inputs */}
          {preset === 'custom' && (
            <div className="mb-2.5 grid grid-cols-2 gap-2">
              <div>
                <label className="mb-1 block text-[11px] text-muted">From</label>
                <input
                  type="date"
                  value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                  className={inputCls}
                />
              </div>
              <div>
                <label className="mb-1 block text-[11px] text-muted">To</label>
                <input
                  type="date"
                  value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                  className={inputCls}
                />
              </div>
            </div>
          )}

          {/* Filter by trigger (only for executions/analyses) */}
          {type !== 'decisions' && triggers.length > 0 && (
            <div className="mb-2.5">
              <label className="mb-1 block text-[11px] text-muted">Filter by trigger</label>
              <select
                value={selectedTrigger}
                onChange={(e) => setSelectedTrigger(e.target.value)}
                className={inputCls}
              >
                <option value="">All types</option>
                {triggers.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
          )}

          {/* Select specific backtest (when trigger=backtest) */}
          {type !== 'decisions' && selectedTrigger === 'backtest' && backtests.length > 0 && (
            <div className="mb-2.5">
              <label className="mb-1 block text-[11px] text-muted">Select backtest run</label>
              <select
                value={selectedBacktest}
                onChange={(e) => setSelectedBacktest(e.target.value)}
                className={inputCls}
              >
                <option value="">All backtests</option>
                {backtests.map((bt) => (
                  <option key={bt.id} value={bt.id}>{formatBacktestLabel(bt)}</option>
                ))}
              </select>
            </div>
          )}

          {/* Summary hint */}
          <p className="mb-2.5 text-[11px] text-muted">
            {dateFrom && dateTo
              ? `${dateFrom} — ${dateTo}`
              : dateFrom
              ? `From ${dateFrom}`
              : dateTo
              ? `Until ${dateTo}`
              : 'All time'}
            {selectedTrigger ? ` · ${selectedTrigger}` : ''}
            {selectedBacktest ? ` · backtest ${selectedBacktest.slice(0, 8)}…` : ''}
          </p>

          <div className="flex gap-2">
            <button
              onClick={() => handleExport('csv')}
              disabled={exporting}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-border bg-background px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-card-hover disabled:opacity-50"
            >
              <Download className="h-3.5 w-3.5" />
              CSV
            </button>
            <button
              onClick={() => handleExport('json')}
              disabled={exporting}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-border bg-background px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-card-hover disabled:opacity-50"
            >
              <FileJson className="h-3.5 w-3.5" />
              JSON
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ========== Pagination ==========

function Pagination({
  page,
  total,
  pageSize,
  onPageChange,
}: {
  page: number;
  total: number;
  pageSize: number;
  onPageChange: (page: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (total <= pageSize) return null;

  return (
    <div className="flex items-center justify-between border-t border-border pt-3">
      <span className="text-xs text-muted">
        {page * pageSize + 1}–{Math.min((page + 1) * pageSize, total)} of {total}
      </span>
      <div className="flex items-center gap-1.5">
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page === 0}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-border text-muted transition-colors hover:bg-card-hover hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        {/* Page number buttons — show up to 5 pages */}
        {Array.from({ length: totalPages }, (_, i) => i)
          .filter((i) => {
            if (totalPages <= 5) return true;
            if (i === 0 || i === totalPages - 1) return true;
            return Math.abs(i - page) <= 1;
          })
          .reduce<(number | 'ellipsis')[]>((acc, i) => {
            const last = acc[acc.length - 1];
            if (typeof last === 'number' && i - last > 1) acc.push('ellipsis');
            acc.push(i);
            return acc;
          }, [])
          .map((item, idx) =>
            item === 'ellipsis' ? (
              <span key={`e-${idx}`} className="px-1 text-xs text-muted">…</span>
            ) : (
              <button
                key={item}
                onClick={() => onPageChange(item)}
                className={cn(
                  'flex h-8 min-w-[2rem] items-center justify-center rounded-lg border text-xs font-medium transition-colors',
                  page === item
                    ? 'border-accent bg-accent/15 text-accent-light'
                    : 'border-border text-muted hover:bg-card-hover hover:text-foreground'
                )}
              >
                {item + 1}
              </button>
            )
          )}
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages - 1}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-border text-muted transition-colors hover:bg-card-hover hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

// ========== Export Helpers ==========

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
  // UTF-8 BOM 前缀，确保 Excel 正确识别中文
  downloadFile('\uFEFF' + [headers.join(','), ...rows].join('\n'), filename, 'text/csv;charset=utf-8');
}

function exportAsJSON(data: unknown, filename: string) {
  downloadFile(JSON.stringify(data, null, 2), filename, 'application/json');
}

// ========== Main Agent Page ==========

export default function Agent() {
  const { toast } = useToast();
  const PAGE_SIZE = 10;

  const [decisions, setDecisions] = useState<TradingDecision[]>([]);
  const [decisionsTotal, setDecisionsTotal] = useState(0);
  const [decisionsPage, setDecisionsPage] = useState(0);

  const [analyses, setAnalyses] = useState<AnalysisHistory[]>([]);
  const [analysesTotal, setAnalysesTotal] = useState(0);
  const [analysesPage, setAnalysesPage] = useState(0);

  const [executions, setExecutions] = useState<WorkflowExecution[]>([]);
  const [executionsTotal, setExecutionsTotal] = useState(0);
  const [executionsPage, setExecutionsPage] = useState(0);

  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [workflows, setWorkflows] = useState<Record<string, WorkflowInfo>>({});
  const [tools, setTools] = useState<AgentTool[]>([]);
  const [active, setActive] = useState<ActiveWorkflow | null>(null);
  const [config, setConfig] = useState<AgentConfig | null>(null);
  const [allModels, setAllModels] = useState<LLMModelRef[]>([]);
  const [tab, setTab] = useState<Tab>('config');
  const [triggering, setTriggering] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [saving, setSaving] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [toolFilter, setToolFilter] = useState<string>('all');
  const [exporting, setExporting] = useState(false);

  const loadAll = useCallback(() => {
    Promise.all([
      fetchDecisions(PAGE_SIZE, decisionsPage * PAGE_SIZE),
      fetchAnalyses(PAGE_SIZE, analysesPage * PAGE_SIZE),
      fetchAgentMessages(),
      fetchWorkflows(),
      fetchAgentTools(),
      fetchWorkflowExecutions(PAGE_SIZE, executionsPage * PAGE_SIZE),
      fetchActiveWorkflow(),
      fetchAgentConfig(),
      fetchLLMModels(),
    ]).then(([dResp, aResp, m, w, t, eResp, aw, cfg, models]) => {
      setDecisions(dResp.items);
      setDecisionsTotal(dResp.total);
      setAnalyses(aResp.items);
      setAnalysesTotal(aResp.total);
      setMessages(m);
      setWorkflows(w);
      setTools(t);
      setExecutions(eResp.items);
      setExecutionsTotal(eResp.total);
      setActive(aw);
      setConfig(cfg);
      setAllModels(models);
    }).catch(() => {
      toast('Failed to load agent data', 'error');
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [toast, decisionsPage, analysesPage, executionsPage]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // SSE — 实时 workflow 事件（类似 Cursor Plan 的实时展示）
  const { liveExecution, streamingTexts } = useLiveExecution(() => {
    // workflow 完成后刷新数据
    loadAll();
  });

  // 当 live execution 开始时，同步 active.is_running 并自动切到 execution tab
  useEffect(() => {
    if (liveExecution) {
      setActive((prev) => prev ? { ...prev, is_running: true } : prev);
      setTab('execution');
    }
  }, [liveExecution]);

  // Fallback polling（SSE 断开时仍可工作）
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (active?.is_running && !liveExecution) {
      // 仅在没有 live SSE 数据时 polling
      pollingRef.current = setInterval(async () => {
        try {
          const aw = await fetchActiveWorkflow();
          setActive(aw);
          if (!aw.is_running) {
            loadAll();
          }
        } catch { /* ignore polling errors */ }
      }, 3000);
    } else if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [active?.is_running, liveExecution, loadAll]);

  const handleTriggerAnalysis = async () => {
    setTriggering(true);
    try {
      await triggerAnalysis();
      toast('Analysis triggered successfully', 'success');
      // Refresh active status to start polling
      const aw = await fetchActiveWorkflow();
      setActive(aw);
    } catch {
      toast('Failed to trigger analysis', 'error');
    } finally {
      setTriggering(false);
    }
  };

  const handleSendChat = async (message: string) => {
    try {
      const result = await sendAgentChat(message);
      if (result.status === 'queued') {
        toast(`Message queued (position: ${result.queue_size})`, 'info');
        // 更新 active 中的 queue_size
        setActive((prev) => prev ? { ...prev, chat_queue_size: result.queue_size } : prev);
      } else {
        toast('New analysis started', 'success');
        const aw = await fetchActiveWorkflow();
        setActive(aw);
      }
    } catch {
      toast('Failed to send message', 'error');
    }
  };

  const handleToggleTool = async (name: string) => {
    const target = tools.find((t) => t.name === name);
    if (!target) return;

    const newEnabled = !target.enabled;
    setTools((prev) =>
      prev.map((t) => (t.name === name ? { ...t, enabled: newEnabled } : t))
    );
    try {
      await toggleAgentTool(name, newEnabled);
      toast(`Tool "${name}" ${newEnabled ? 'enabled' : 'disabled'}`, 'success');
    } catch {
      setTools((prev) =>
        prev.map((t) => (t.name === name ? { ...t, enabled: !newEnabled } : t))
      );
      toast(`Failed to toggle tool "${name}"`, 'error');
    }
  };

  const handleSwitchWorkflow = async (type: string) => {
    setSwitching(true);
    try {
      await switchWorkflow(type);
      const [aw, cfg, t] = await Promise.all([
        fetchActiveWorkflow(),
        fetchAgentConfig(),
        fetchAgentTools(),
      ]);
      setActive(aw);
      setConfig(cfg);
      setTools(t);
      toast(`Switched to ${aw.workflow_type || type}`, 'success');
    } catch {
      toast('Failed to switch workflow', 'error');
    } finally {
      setSwitching(false);
    }
  };

  const handleReloadWorkflows = async () => {
    setReloading(true);
    try {
      const result = await reloadWorkflows();
      setWorkflows(result.workflows);
      const parts: string[] = [];
      if (result.loaded.length > 0) parts.push(`Loaded: ${result.loaded.join(', ')}`);
      if (result.removed.length > 0) parts.push(`Removed: ${result.removed.join(', ')}`);
      toast(
        parts.length > 0
          ? `Workflows reloaded — ${parts.join('; ')}`
          : `Workflows reloaded — ${result.total} total (no changes)`,
        'success',
      );
    } catch {
      toast('Failed to reload workflows', 'error');
    } finally {
      setReloading(false);
    }
  };

  const handleSaveConfig = async (updates: Record<string, unknown>) => {
    setSaving(true);
    try {
      const result = await updateAgentConfig(updates);
      setConfig(result.config);
      toast(`Updated ${Object.keys(updates).length} config field(s)`, 'success');
    } catch {
      toast('Failed to update configuration', 'error');
    } finally {
      setSaving(false);
    }
  };

  const filteredTools =
    toolFilter === 'all' ? tools : tools.filter((t) => t.category === toolFilter);

  const roleIcons: Record<string, typeof Bot> = {
    ai: Bot,
    human: User,
    system: Cpu,
    tool: Wrench,
  };

  const roleColors: Record<string, string> = {
    ai: 'bg-accent/15 text-accent-light',
    human: 'bg-profit-bg text-profit',
    system: 'bg-info-bg text-info',
    tool: 'bg-warning-bg text-warning',
  };

  const toolCategories = ['all', 'data', 'trading', 'analysis', 'system'];

  return (
    <div className="animate-fade-in space-y-4 sm:space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-bold tracking-tight text-foreground sm:text-2xl">Agent</h1>
          <p className="mt-0.5 text-xs text-muted sm:mt-1 sm:text-sm">AI workflow management, tools, and execution history</p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2 sm:gap-3">
          {active?.is_running && (
            <div className="flex items-center gap-2 rounded-lg border border-accent/30 bg-accent/10 px-2.5 py-1 sm:px-3 sm:py-1.5">
              <span className="relative flex h-2 w-2 sm:h-2.5 sm:w-2.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-accent sm:h-2.5 sm:w-2.5" />
              </span>
              <span className="text-xs font-medium text-accent-light sm:text-sm">Running</span>
              {(active.pending_triggers ?? 0) > 0 && (
                <Badge variant="warning">{active.pending_triggers} queued</Badge>
              )}
            </div>
          )}
          <Button
            icon={<Play className="h-4 w-4" />}
            loading={triggering}
            disabled={active?.is_running}
            onClick={handleTriggerAnalysis}
          >
            <span className="hidden sm:inline">{active?.is_running ? 'Workflow Running' : 'Trigger Analysis'}</span>
            <span className="sm:hidden">{active?.is_running ? 'Running' : 'Trigger'}</span>
          </Button>
        </div>
      </div>

      {/* Active Workflow & Switcher */}
      <WorkflowSwitcher
        active={active}
        workflows={workflows}
        onSwitch={handleSwitchWorkflow}
        onReload={handleReloadWorkflows}
        switching={switching}
        reloading={reloading}
      />

      {/* Tab Switcher */}
      <div className="-mx-4 overflow-x-auto border-b border-border px-4 md:mx-0 md:px-0">
        <div className="flex min-w-max gap-0.5 sm:gap-1">
          {([
            { key: 'config', label: 'Config', icon: Settings2 },
            { key: 'execution', label: 'Execution', icon: Zap },
            { key: 'tools', label: 'Tools', icon: Wrench },
            { key: 'decisions', label: 'Decisions', icon: BarChart3 },
            { key: 'analyses', label: 'Analyses', icon: Cpu },
            { key: 'messages', label: 'Messages', icon: MessageSquare },
          ] as const).map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={cn(
                'flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-xs font-medium transition-colors sm:gap-2 sm:px-4 sm:py-2.5 sm:text-sm',
                tab === key
                  ? 'border-accent text-accent-light'
                  : 'border-transparent text-muted hover:text-foreground'
              )}
            >
              <Icon className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
              {label}
              {key === 'tools' && (
                <span className="rounded-full bg-accent/15 px-1.5 py-0.5 text-[10px] font-bold text-accent-light">
                  {tools.filter((t) => t.enabled).length}/{tools.length}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Config Tab */}
      {tab === 'config' && (
        <div className="space-y-4">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="text-base font-semibold text-foreground sm:text-lg">Workflow Configuration</h2>
            <span className="text-xs text-muted">Changes are persisted to YAML config files</span>
          </div>
          {config ? (
            <Card>
              <ConfigEditor config={config} onSave={handleSaveConfig} saving={saving} allModels={allModels} />
            </Card>
          ) : (
            <Card>
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-6 w-6 animate-spin text-muted" />
              </div>
            </Card>
          )}
        </div>
      )}

      {/* Execution Timeline Tab */}
      {tab === 'execution' && (
        <div className="space-y-3 sm:space-y-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="text-base font-semibold text-foreground sm:text-lg">Workflow Executions</h2>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted">
                <Clock className="mr-1 inline h-3.5 w-3.5" />
                {executionsTotal} total
              </span>
              <ExportMenu
                type="executions"
                exporting={exporting}
                onExport={async (format, opts) => {
                  setExporting(true);
                  try {
                    const data = await exportAnalyses(opts);
                    const parts = ['executions'];
                    if (opts?.backtest_id) parts.push(`bt-${opts.backtest_id.slice(0, 8)}`);
                    else if (opts?.trigger) parts.push(opts.trigger);
                    if (opts?.date_from) parts.push(opts.date_from);
                    if (opts?.date_to) parts.push(opts.date_to);
                    const filename = parts.join('_');
                    if (format === 'csv') {
                      exportAsCSV(data as unknown as Record<string, unknown>[], `${filename}.csv`);
                    } else {
                      exportAsJSON(data, `${filename}.json`);
                    }
                    toast(`Exported ${data.length} executions as ${format.toUpperCase()}`, 'success');
                  } catch { toast('Export failed', 'error'); }
                  finally { setExporting(false); }
                }}
              />
            </div>
          </div>

          {/* Live execution (SSE) — 置顶显示，类似 Cursor Plan */}
          {liveExecution && (
            <div className="rounded-xl border-2 border-accent/40 bg-accent/5">
              <ExecutionCard
                execution={liveExecution}
                streamingTexts={streamingTexts}
                defaultExpanded
              />
            </div>
          )}

          {executions.length === 0 && !liveExecution ? (
            <Card>
              <div className="flex flex-col items-center py-12 text-center">
                <Zap className="mb-3 h-10 w-10 text-muted" />
                <p className="text-sm text-muted">No workflow executions yet</p>
                <p className="mt-1 text-xs text-muted">Trigger an analysis to see execution details here</p>
              </div>
            </Card>
          ) : (
            <>
              {executions.map((exec) => (
                <ExecutionCard key={exec.id} execution={exec} />
              ))}
              <Pagination
                page={executionsPage}
                total={executionsTotal}
                pageSize={PAGE_SIZE}
                onPageChange={setExecutionsPage}
              />
            </>
          )}
        </div>
      )}

      {/* Tools Tab */}
      {tab === 'tools' && (
        <div className="space-y-3 sm:space-y-4">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="text-base font-semibold text-foreground sm:text-lg">Agent Tools</h2>
            <div className="flex items-center gap-2">
              <Eye className="h-3.5 w-3.5 text-muted sm:h-4 sm:w-4" />
              <span className="text-xs text-muted">
                {tools.filter((t) => t.enabled).length} enabled / {tools.length} total
              </span>
            </div>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {toolCategories.map((cat) => {
              const count = cat === 'all' ? tools.length : tools.filter((t) => t.category === cat).length;
              return (
                <button
                  key={cat}
                  onClick={() => setToolFilter(cat)}
                  className={cn(
                    'rounded-lg px-2.5 py-1 text-xs font-medium transition-colors sm:px-3 sm:py-1.5',
                    toolFilter === cat
                      ? 'bg-accent text-white'
                      : 'bg-card-hover text-muted hover:text-foreground'
                  )}
                >
                  {cat === 'all' ? 'All' : TOOL_CATEGORY_META[cat]?.label || cat}
                  <span className="ml-1 opacity-60">({count})</span>
                </button>
              );
            })}
          </div>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {filteredTools.map((tool) => (
              <ToolCard key={tool.name} tool={tool} onToggle={handleToggleTool} />
            ))}
          </div>
        </div>
      )}

      {/* Decisions Tab */}
      {tab === 'decisions' && (
        <div className="space-y-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="text-base font-semibold text-foreground sm:text-lg">Trading Decisions</h2>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted">{decisionsTotal} total</span>
              <ExportMenu
                type="decisions"
                exporting={exporting}
                onExport={async (format, opts) => {
                  setExporting(true);
                  try {
                    const data = await exportDecisions(opts);
                    const parts = ['decisions'];
                    if (opts?.symbol) parts.push(opts.symbol);
                    if (opts?.date_from) parts.push(opts.date_from);
                    if (opts?.date_to) parts.push(opts.date_to);
                    const filename = parts.join('_');
                    if (format === 'csv') {
                      exportAsCSV(data as unknown as Record<string, unknown>[], `${filename}.csv`);
                    } else {
                      exportAsJSON(data, `${filename}.json`);
                    }
                    toast(`Exported ${data.length} decisions as ${format.toUpperCase()}`, 'success');
                  } catch { toast('Export failed', 'error'); }
                  finally { setExporting(false); }
                }}
              />
            </div>
          </div>
          {decisions.length === 0 ? (
            <Card>
              <div className="flex flex-col items-center py-12 text-center">
                <BarChart3 className="mb-3 h-10 w-10 text-muted" />
                <p className="text-sm text-muted">No trading decisions yet</p>
              </div>
            </Card>
          ) : (
            <>
              {decisions.map((d) => (
                <Card key={d.id} hover>
                  <div className="flex items-start gap-3 sm:gap-4">
                    <div
                      className={cn(
                        'flex h-9 w-9 shrink-0 items-center justify-center rounded-xl sm:h-10 sm:w-10',
                        d.action === 'buy' && 'bg-profit-bg',
                        d.action === 'sell' && 'bg-loss-bg',
                        d.action === 'hold' && 'bg-info-bg'
                      )}
                    >
                      {d.action === 'buy' && <ArrowUpRight className="h-4 w-4 text-profit sm:h-5 sm:w-5" />}
                      {d.action === 'sell' && <ArrowDownRight className="h-4 w-4 text-loss sm:h-5 sm:w-5" />}
                      {d.action === 'hold' && <BarChart3 className="h-4 w-4 text-info sm:h-5 sm:w-5" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
                        <span className="text-sm font-bold text-foreground sm:text-base">{d.symbol}</span>
                        <Badge variant={d.action === 'buy' ? 'profit' : d.action === 'sell' ? 'loss' : 'info'}>
                          {d.action.toUpperCase()}
                        </Badge>
                        {d.quantity && (
                          <span className="text-xs text-muted-foreground sm:text-sm">
                            {d.quantity} shares {d.price ? `@ ${formatCurrency(d.price)}` : ''}
                          </span>
                        )}
                      </div>
                      <span className="mt-0.5 block text-[11px] text-muted sm:hidden">{formatRelative(d.created_at)}</span>
                      <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground sm:mt-2 sm:text-sm">{d.reasoning}</p>
                      <div className="mt-2 flex flex-wrap items-center gap-3 sm:mt-3 sm:gap-4">
                        <div className="flex items-center gap-1.5">
                          <span className="text-xs text-muted">Confidence</span>
                          <div className="h-1.5 w-16 rounded-full bg-border sm:w-20">
                            <div
                              className="h-1.5 rounded-full bg-accent"
                              style={{ width: `${d.confidence * 100}%` }}
                            />
                          </div>
                          <span className="text-xs font-medium text-foreground">
                            {(d.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                        {d.stop_loss && (
                          <span className="text-xs text-muted">
                            SL: <span className="text-loss">{formatCurrency(d.stop_loss)}</span>
                          </span>
                        )}
                        {d.take_profit && (
                          <span className="text-xs text-muted">
                            TP: <span className="text-profit">{formatCurrency(d.take_profit)}</span>
                          </span>
                        )}
                        <span className="ml-auto hidden text-xs text-muted sm:inline">{formatRelative(d.created_at)}</span>
                      </div>
                    </div>
                  </div>
                </Card>
              ))}
              <Pagination
                page={decisionsPage}
                total={decisionsTotal}
                pageSize={PAGE_SIZE}
                onPageChange={setDecisionsPage}
              />
            </>
          )}
        </div>
      )}

      {/* Analyses Tab */}
      {tab === 'analyses' && (
        <div className="space-y-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="text-base font-semibold text-foreground sm:text-lg">Analysis History</h2>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted">{analysesTotal} total</span>
              <ExportMenu
                type="analyses"
                exporting={exporting}
                onExport={async (format, opts) => {
                  setExporting(true);
                  try {
                    const data = await exportAnalyses(opts);
                    const parts = ['analyses'];
                    if (opts?.backtest_id) parts.push(`bt-${opts.backtest_id.slice(0, 8)}`);
                    else if (opts?.trigger) parts.push(opts.trigger);
                    if (opts?.date_from) parts.push(opts.date_from);
                    if (opts?.date_to) parts.push(opts.date_to);
                    const filename = parts.join('_');
                    if (format === 'csv') {
                      exportAsCSV(data as unknown as Record<string, unknown>[], `${filename}.csv`);
                    } else {
                      exportAsJSON(data, `${filename}.json`);
                    }
                    toast(`Exported ${data.length} analyses as ${format.toUpperCase()}`, 'success');
                  } catch { toast('Export failed', 'error'); }
                  finally { setExporting(false); }
                }}
              />
            </div>
          </div>
          {analyses.length === 0 ? (
            <Card>
              <div className="flex flex-col items-center py-12 text-center">
                <Cpu className="mb-3 h-10 w-10 text-muted" />
                <p className="text-sm text-muted">No analysis history yet</p>
              </div>
            </Card>
          ) : (
            <>
              {analyses.map((a) => (
                <Card key={a.id} hover>
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <div className="flex items-center gap-2.5 sm:gap-3">
                      {a.success ? (
                        <CheckCircle className="h-4 w-4 shrink-0 text-profit sm:h-5 sm:w-5" />
                      ) : (
                        <XCircle className="h-4 w-4 shrink-0 text-loss sm:h-5 sm:w-5" />
                      )}
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
                          <span className="text-sm font-semibold text-foreground">{a.trigger}</span>
                          {a.analysis_type && <Badge variant="info">{a.analysis_type}</Badge>}
                          <Badge variant={a.success ? 'profit' : 'loss'}>
                            {a.success ? 'Success' : 'Failed'}
                          </Badge>
                        </div>
                        {a.workflow_id && (
                          <span className="mt-0.5 block truncate text-xs text-muted">{a.workflow_id}</span>
                        )}
                      </div>
                    </div>
                    <span className="shrink-0 pl-6 text-xs text-muted sm:pl-0">{formatRelative(a.created_at)}</span>
                  </div>
                  {a.output_response && (
                    <p className="mt-3 rounded-lg bg-background p-3 text-sm text-muted-foreground">
                      {a.output_response}
                    </p>
                  )}
                  {a.error_message && (
                    <p className="mt-3 rounded-lg bg-loss-bg p-3 text-sm text-loss">
                      {a.error_message}
                    </p>
                  )}
                  <div className="mt-2 flex flex-wrap items-center gap-3 sm:mt-3 sm:gap-4">
                    {a.execution_time_seconds && (
                      <span className="text-xs text-muted">
                        Duration: <span className="text-foreground">{formatDuration(a.execution_time_seconds)}</span>
                      </span>
                    )}
                    {a.tool_calls && a.tool_calls.length > 0 && (
                      <div className="flex items-center gap-1">
                        <Wrench className="h-3 w-3 text-muted" />
                        <span className="text-xs text-muted">{a.tool_calls.length} tool calls</span>
                      </div>
                    )}
                    {a.trades_executed && a.trades_executed.length > 0 && (
                      <span className="text-xs text-muted">
                        {a.trades_executed.length} trade(s) executed
                      </span>
                    )}
                  </div>
                </Card>
              ))}
              <Pagination
                page={analysesPage}
                total={analysesTotal}
                pageSize={PAGE_SIZE}
                onPageChange={setAnalysesPage}
              />
            </>
          )}
        </div>
      )}

      {/* Messages Tab */}
      {tab === 'messages' && (
        <Card>
          <CardHeader title="Agent Conversation" subtitle="Recent messages" />
          <div className="space-y-3">
            {messages.map((msg) => {
              const Icon = roleIcons[msg.role] || MessageSquare;
              return (
                <div key={msg.id} className="flex items-start gap-2.5 sm:gap-3">
                  <div
                    className={cn(
                      'flex h-7 w-7 shrink-0 items-center justify-center rounded-lg sm:h-8 sm:w-8',
                      roleColors[msg.role] || 'bg-border text-muted'
                    )}
                  >
                    <Icon className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 sm:gap-2">
                      <span className="text-[11px] font-semibold uppercase text-muted-foreground sm:text-xs">
                        {msg.role}
                      </span>
                      <span className="text-[11px] text-muted sm:text-xs">{formatRelative(msg.created_at)}</span>
                    </div>
                    <p className="mt-0.5 text-xs leading-relaxed text-foreground sm:mt-1 sm:text-sm">{msg.content}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* Chat Input — 固定在底部 */}
      <AgentChatInput
        isRunning={!!(active?.is_running || liveExecution)}
        queueSize={active?.chat_queue_size ?? 0}
        onSend={handleSendChat}
      />
    </div>
  );
}
