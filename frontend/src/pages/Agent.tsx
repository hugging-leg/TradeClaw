import { useEffect, useState } from 'react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import {
  fetchDecisions,
  fetchAnalyses,
  fetchAgentMessages,
  fetchWorkflows,
  fetchAgentTools,
  fetchWorkflowExecutions,
  triggerAnalysis,
} from '@/api';
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
} from 'lucide-react';
import type {
  TradingDecision,
  AnalysisHistory,
  AgentMessage,
  WorkflowInfo,
  AgentTool,
  WorkflowExecution,
  ExecutionStep,
} from '@/types';

type Tab = 'execution' | 'tools' | 'decisions' | 'analyses' | 'messages';

const TOOL_CATEGORY_META: Record<string, { label: string; color: string; icon: typeof Database }> = {
  data: { label: 'Data', color: 'bg-blue-500/15 text-blue-400', icon: Database },
  trading: { label: 'Trading', color: 'bg-emerald-500/15 text-emerald-400', icon: TrendingUp },
  analysis: { label: 'Analysis', color: 'bg-purple-500/15 text-purple-400', icon: Brain },
  system: { label: 'System', color: 'bg-amber-500/15 text-amber-400', icon: Settings2 },
};

const STEP_TYPE_META: Record<string, { label: string; color: string; icon: typeof Brain }> = {
  llm_thinking: { label: 'LLM Thinking', color: 'text-purple-400', icon: Brain },
  tool_call: { label: 'Tool Call', color: 'text-blue-400', icon: Wrench },
  decision: { label: 'Decision', color: 'text-emerald-400', icon: Zap },
  notification: { label: 'Notification', color: 'text-amber-400', icon: Send },
};

function ExecutionStepItem({ step, isLast }: { step: ExecutionStep; isLast: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const meta = STEP_TYPE_META[step.type] || STEP_TYPE_META.tool_call;
  const Icon = meta.icon;

  const statusColor = {
    pending: 'border-gray-600 bg-gray-800',
    running: 'border-accent bg-accent/20 animate-pulse',
    completed: 'border-emerald-500 bg-emerald-500/20',
    failed: 'border-red-500 bg-red-500/20',
    skipped: 'border-gray-600 bg-gray-800/50',
  }[step.status];

  return (
    <div className="flex gap-3">
      {/* Timeline connector */}
      <div className="flex flex-col items-center">
        <div className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2', statusColor)}>
          {step.status === 'running' ? (
            <Loader2 className={cn('h-4 w-4 animate-spin', meta.color)} />
          ) : step.status === 'failed' ? (
            <XCircle className="h-4 w-4 text-red-400" />
          ) : (
            <Icon className={cn('h-4 w-4', meta.color)} />
          )}
        </div>
        {!isLast && <div className="w-px flex-1 bg-border" />}
      </div>

      {/* Content */}
      <div className={cn('mb-4 min-w-0 flex-1 pb-1', isLast && 'mb-0')}>
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex w-full items-center gap-2 text-left"
        >
          {expanded ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted" />
          )}
          <span className="text-sm font-medium text-foreground">{step.name}</span>
          <Badge variant="muted">{meta.label}</Badge>
          {step.duration_ms !== undefined && (
            <span className="ml-auto text-xs text-muted">{step.duration_ms}ms</span>
          )}
        </button>

        {expanded && (
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

function ExecutionCard({ execution }: { execution: WorkflowExecution }) {
  const [expanded, setExpanded] = useState(false);
  const statusBadge = {
    running: <Badge variant="info">Running</Badge>,
    completed: <Badge variant="profit">Completed</Badge>,
    failed: <Badge variant="loss">Failed</Badge>,
  }[execution.status];

  const successSteps = execution.steps.filter((s) => s.status === 'completed').length;
  const failedSteps = execution.steps.filter((s) => s.status === 'failed').length;

  return (
    <Card>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-3 text-left"
      >
        <div className={cn(
          'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl',
          execution.status === 'completed' && 'bg-emerald-500/15',
          execution.status === 'failed' && 'bg-red-500/15',
          execution.status === 'running' && 'bg-accent/15',
        )}>
          {execution.status === 'running' ? (
            <Loader2 className="h-5 w-5 animate-spin text-accent-light" />
          ) : execution.status === 'completed' ? (
            <CheckCircle className="h-5 w-5 text-emerald-400" />
          ) : (
            <XCircle className="h-5 w-5 text-red-400" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-foreground">{execution.trigger}</span>
            {statusBadge}
            <Badge variant="muted">{execution.workflow_type}</Badge>
          </div>
          <div className="mt-1 flex items-center gap-3 text-xs text-muted">
            <span>{formatRelative(execution.started_at)}</span>
            {execution.total_duration_ms && (
              <span>Duration: {formatDuration(execution.total_duration_ms / 1000)}</span>
            )}
            <span>{successSteps} completed{failedSteps > 0 ? `, ${failedSteps} failed` : ''}</span>
          </div>
        </div>
        {expanded ? (
          <ChevronDown className="h-5 w-5 shrink-0 text-muted" />
        ) : (
          <ChevronRight className="h-5 w-5 shrink-0 text-muted" />
        )}
      </button>

      {expanded && (
        <div className="mt-4 border-t border-border pt-4">
          {execution.steps.map((step, i) => (
            <ExecutionStepItem
              key={step.id}
              step={step}
              isLast={i === execution.steps.length - 1}
            />
          ))}
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
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3">
          <div className={cn('flex h-9 w-9 shrink-0 items-center justify-center rounded-lg', catMeta.color)}>
            <CatIcon className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm font-semibold text-foreground">{tool.name}</span>
              <Badge variant="muted">{catMeta.label}</Badge>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{tool.description}</p>
          </div>
        </div>
        <button
          onClick={() => onToggle(tool.name)}
          className={cn(
            'flex h-7 w-12 items-center rounded-full px-0.5 transition-colors',
            tool.enabled ? 'bg-accent' : 'bg-gray-700'
          )}
        >
          <div
            className={cn(
              'h-6 w-6 rounded-full bg-white shadow transition-transform',
              tool.enabled ? 'translate-x-5' : 'translate-x-0'
            )}
          />
        </button>
      </div>

      {tool.parameters.length > 0 && (
        <div className="mt-3">
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
                <div key={p.name} className="flex items-center gap-2 rounded-md bg-gray-900/50 px-3 py-1.5 text-xs">
                  <code className="font-medium text-foreground">{p.name}</code>
                  <Badge variant="muted">{p.type}</Badge>
                  {p.required && <Badge variant="loss">required</Badge>}
                  <span className="text-muted-foreground">{p.description}</span>
                  {p.default_value && (
                    <span className="ml-auto text-muted">default: {p.default_value}</span>
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

export default function Agent() {
  const [decisions, setDecisions] = useState<TradingDecision[]>([]);
  const [analyses, setAnalyses] = useState<AnalysisHistory[]>([]);
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [workflows, setWorkflows] = useState<Record<string, WorkflowInfo>>({});
  const [tools, setTools] = useState<AgentTool[]>([]);
  const [executions, setExecutions] = useState<WorkflowExecution[]>([]);
  const [tab, setTab] = useState<Tab>('execution');
  const [triggering, setTriggering] = useState(false);
  const [toolFilter, setToolFilter] = useState<string>('all');

  useEffect(() => {
    Promise.all([
      fetchDecisions(20),
      fetchAnalyses(20),
      fetchAgentMessages(),
      fetchWorkflows(),
      fetchAgentTools(),
      fetchWorkflowExecutions(),
    ]).then(([d, a, m, w, t, e]) => {
      setDecisions(d);
      setAnalyses(a);
      setMessages(m);
      setWorkflows(w);
      setTools(t);
      setExecutions(e);
    });
  }, []);

  const handleTriggerAnalysis = async () => {
    setTriggering(true);
    await triggerAnalysis();
    setTriggering(false);
  };

  const handleToggleTool = (name: string) => {
    setTools((prev) =>
      prev.map((t) => (t.name === name ? { ...t, enabled: !t.enabled } : t))
    );
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
    <div className="animate-fade-in space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Agent</h1>
          <p className="mt-1 text-sm text-muted">AI workflow management, tools, and execution history</p>
        </div>
        <Button
          icon={<Play className="h-4 w-4" />}
          loading={triggering}
          onClick={handleTriggerAnalysis}
        >
          Trigger Analysis
        </Button>
      </div>

      {/* Workflow Cards */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        {Object.entries(workflows).slice(0, 6).map(([key, wf]) => (
          <Card key={key} hover className="cursor-pointer">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-semibold text-foreground">{wf.name}</h3>
                  {wf.deprecated && <Badge variant="loss">Deprecated</Badge>}
                </div>
                <p className="mt-1 text-xs text-muted">{wf.description}</p>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-1">
              {wf.features.slice(0, 3).map((f) => (
                <Badge key={f} variant="muted">{f}</Badge>
              ))}
            </div>
            {wf.best_for && (
              <p className="mt-2 text-xs text-accent-light">{wf.best_for}</p>
            )}
          </Card>
        ))}
      </div>

      {/* Tab Switcher */}
      <div className="flex gap-1 overflow-x-auto border-b border-border pb-0">
        {([
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
              'flex shrink-0 items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors',
              tab === key
                ? 'border-accent text-accent-light'
                : 'border-transparent text-muted hover:text-foreground'
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
            {key === 'tools' && (
              <span className="rounded-full bg-accent/15 px-1.5 py-0.5 text-[10px] font-bold text-accent-light">
                {tools.filter((t) => t.enabled).length}/{tools.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Execution Timeline Tab */}
      {tab === 'execution' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-foreground">Workflow Executions</h2>
            <div className="flex items-center gap-2 text-xs text-muted">
              <Clock className="h-3.5 w-3.5" />
              {executions.length} execution{executions.length !== 1 ? 's' : ''}
            </div>
          </div>
          {executions.length === 0 ? (
            <Card>
              <div className="flex flex-col items-center py-12 text-center">
                <Zap className="mb-3 h-10 w-10 text-muted" />
                <p className="text-sm text-muted">No workflow executions yet</p>
                <p className="mt-1 text-xs text-muted">Trigger an analysis to see execution details here</p>
              </div>
            </Card>
          ) : (
            executions.map((exec) => (
              <ExecutionCard key={exec.id} execution={exec} />
            ))
          )}
        </div>
      )}

      {/* Tools Tab */}
      {tab === 'tools' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-foreground">Agent Tools</h2>
            <div className="flex items-center gap-2">
              <Eye className="h-4 w-4 text-muted" />
              <span className="text-xs text-muted">
                {tools.filter((t) => t.enabled).length} enabled / {tools.length} total
              </span>
            </div>
          </div>

          {/* Category filter */}
          <div className="flex gap-1.5">
            {toolCategories.map((cat) => {
              const count = cat === 'all' ? tools.length : tools.filter((t) => t.category === cat).length;
              return (
                <button
                  key={cat}
                  onClick={() => setToolFilter(cat)}
                  className={cn(
                    'rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
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
          {decisions.map((d) => (
            <Card key={d.id} hover>
              <div className="flex items-start gap-4">
                <div
                  className={cn(
                    'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl',
                    d.action === 'buy' && 'bg-profit-bg',
                    d.action === 'sell' && 'bg-loss-bg',
                    d.action === 'hold' && 'bg-info-bg'
                  )}
                >
                  {d.action === 'buy' && <ArrowUpRight className="h-5 w-5 text-profit" />}
                  {d.action === 'sell' && <ArrowDownRight className="h-5 w-5 text-loss" />}
                  {d.action === 'hold' && <BarChart3 className="h-5 w-5 text-info" />}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-base font-bold text-foreground">{d.symbol}</span>
                    <Badge variant={d.action === 'buy' ? 'profit' : d.action === 'sell' ? 'loss' : 'info'}>
                      {d.action.toUpperCase()}
                    </Badge>
                    {d.quantity && (
                      <span className="text-sm text-muted-foreground">
                        {d.quantity} shares {d.price ? `@ ${formatCurrency(d.price)}` : ''}
                      </span>
                    )}
                    <span className="ml-auto text-xs text-muted">{formatRelative(d.created_at)}</span>
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{d.reasoning}</p>
                  <div className="mt-3 flex items-center gap-4">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs text-muted">Confidence</span>
                      <div className="h-1.5 w-20 rounded-full bg-border">
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
                  </div>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Analyses Tab */}
      {tab === 'analyses' && (
        <div className="space-y-3">
          {analyses.map((a) => (
            <Card key={a.id} hover>
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  {a.success ? (
                    <CheckCircle className="h-5 w-5 text-profit" />
                  ) : (
                    <XCircle className="h-5 w-5 text-loss" />
                  )}
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-foreground">{a.trigger}</span>
                      {a.analysis_type && <Badge variant="info">{a.analysis_type}</Badge>}
                      <Badge variant={a.success ? 'profit' : 'loss'}>
                        {a.success ? 'Success' : 'Failed'}
                      </Badge>
                    </div>
                    {a.workflow_id && (
                      <span className="mt-0.5 text-xs text-muted">{a.workflow_id}</span>
                    )}
                  </div>
                </div>
                <span className="text-xs text-muted">{formatRelative(a.created_at)}</span>
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

              <div className="mt-3 flex items-center gap-4">
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
                <div key={msg.id} className="flex items-start gap-3">
                  <div
                    className={cn(
                      'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
                      roleColors[msg.role] || 'bg-border text-muted'
                    )}
                  >
                    <Icon className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold uppercase text-muted-foreground">
                        {msg.role}
                      </span>
                      <span className="text-xs text-muted">{formatRelative(msg.created_at)}</span>
                    </div>
                    <p className="mt-1 text-sm leading-relaxed text-foreground">{msg.content}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}
    </div>
  );
}
