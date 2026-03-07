import { useEffect, useState } from 'react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { StatusDot } from '@/components/ui/StatusDot';
import {
  fetchSchedulerJobs,
  fetchExecutionHistory,
  fetchRiskEvents,
  fetchSystemStatus,
  fetchRuleTriggers,
  toggleTrading,
  emergencyStop,
  createSchedulerJob,
  deleteSchedulerJob,
  pauseSchedulerJob,
  resumeSchedulerJob,
  updateRuleTrigger,
} from '@/api';
import { formatRelative, formatDuration } from '@/utils/format';
import { cn } from '@/utils/cn';
import {
  Clock,
  Play,
  Pause,
  AlertTriangle,
  Shield,
  CheckCircle,
  XCircle,
  Zap,
  OctagonX,
  Plus,
  Trash2,
  X,
  Radio,
  Activity,
  Newspaper,
  Settings2,
  Loader2,
} from 'lucide-react';
import type {
  SchedulerJob,
  ExecutionRecord,
  RiskEvent,
  SystemStatus,
  RuleTrigger,
  JobFormData,
  TriggerType,
} from '@/types';

// ========== Add Job Dialog ==========

interface AddJobDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (job: JobFormData) => void;
}

const EVENT_TYPE_OPTIONS = [
  { value: 'trigger_workflow', label: 'Trigger Workflow', description: 'Run the active trading workflow' },
  { value: 'trigger_portfolio_check', label: 'Portfolio Check', description: 'Check portfolio health' },
  { value: 'trigger_risk_check', label: 'Risk Check', description: 'Run risk management checks' },
  { value: 'trigger_eod_analysis', label: 'EOD Analysis', description: 'End-of-day analysis' },
];

function AddJobDialog({ open, onClose, onSubmit }: AddJobDialogProps) {
  const [name, setName] = useState('');
  const [triggerType, setTriggerType] = useState<TriggerType>('cron');
  const [cronHour, setCronHour] = useState(9);
  const [cronMinute, setCronMinute] = useState(35);
  const [cronDow, setCronDow] = useState('mon-fri');
  const [intervalMinutes, setIntervalMinutes] = useState(30);
  const [onceMode, setOnceMode] = useState<'datetime' | 'delay'>('delay');
  const [onceDatetime, setOnceDatetime] = useState('');
  const [onceDelayMinutes, setOnceDelayMinutes] = useState(30);
  const [requireTradingDay, setRequireTradingDay] = useState(true);
  const [requireMarketOpen, setRequireMarketOpen] = useState(false);
  const [eventType, setEventType] = useState('trigger_workflow');

  if (!open) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const id = `job_${Date.now()}`;
    onSubmit({
      id,
      name: name || `Custom ${triggerType} job`,
      trigger_type: triggerType,
      cron_hour: triggerType === 'cron' ? cronHour : undefined,
      cron_minute: triggerType === 'cron' ? cronMinute : undefined,
      cron_day_of_week: triggerType === 'cron' ? cronDow : undefined,
      interval_minutes: triggerType === 'interval' ? intervalMinutes : undefined,
      once_mode: triggerType === 'once' ? onceMode : undefined,
      once_datetime: triggerType === 'once' && onceMode === 'datetime'
        ? new Date(onceDatetime).toISOString() // Convert local datetime-local to UTC ISO string
        : undefined,
      once_delay_minutes: triggerType === 'once' && onceMode === 'delay' ? onceDelayMinutes : undefined,
      require_trading_day: requireTradingDay,
      require_market_open: requireMarketOpen,
      event_type: eventType,
    });
    onClose();
    // Reset
    setName('');
    setTriggerType('cron');
    setCronHour(9);
    setCronMinute(35);
    setCronDow('mon-fri');
    setIntervalMinutes(30);
    setOnceMode('delay');
    setOnceDatetime('');
    setOnceDelayMinutes(30);
    setRequireTradingDay(true);
    setRequireMarketOpen(false);
    setEventType('trigger_workflow');
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 backdrop-blur-sm sm:items-center">
      <div className="max-h-[90vh] w-full overflow-y-auto rounded-t-2xl border border-border bg-card p-5 shadow-2xl sm:max-w-lg sm:rounded-2xl sm:p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-foreground">Add Scheduled Job</h2>
          <button onClick={onClose} className="rounded-lg p-1.5 text-muted hover:bg-card-hover hover:text-foreground">
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          {/* Job Name */}
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">Job Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Morning Analysis"
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
            />
          </div>

          {/* Trigger Type */}
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">Trigger Type</label>
            <div className="flex flex-col gap-2 sm:flex-row">
              {([
                { key: 'cron' as const, label: '⏰ Cron (Fixed Time)' },
                { key: 'interval' as const, label: '🔄 Interval (Repeating)' },
                { key: 'once' as const, label: '🎯 Once (One-time)' },
              ]).map(({ key, label }) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setTriggerType(key)}
                  className={cn(
                    'flex-1 rounded-lg border px-4 py-2.5 text-sm font-medium transition-colors',
                    triggerType === key
                      ? 'border-accent bg-accent/10 text-accent-light'
                      : 'border-border bg-background text-muted hover:text-foreground'
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Cron Fields */}
          {triggerType === 'cron' && (
            <div className="space-y-3 rounded-lg border border-border/50 bg-background p-4">
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="mb-1 block text-xs text-muted">Hour (0-23)</label>
                  <input
                    type="number"
                    min={0}
                    max={23}
                    value={cronHour}
                    onChange={(e) => setCronHour(parseInt(e.target.value))}
                    className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus:border-accent focus:outline-none"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-muted">Minute (0-59)</label>
                  <input
                    type="number"
                    min={0}
                    max={59}
                    value={cronMinute}
                    onChange={(e) => setCronMinute(parseInt(e.target.value))}
                    className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus:border-accent focus:outline-none"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-muted">Day of Week</label>
                  <select
                    value={cronDow}
                    onChange={(e) => setCronDow(e.target.value)}
                    className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus:border-accent focus:outline-none"
                  >
                    <option value="mon-fri">Mon-Fri</option>
                    <option value="*">Every Day</option>
                    <option value="mon">Monday</option>
                    <option value="tue">Tuesday</option>
                    <option value="wed">Wednesday</option>
                    <option value="thu">Thursday</option>
                    <option value="fri">Friday</option>
                  </select>
                </div>
              </div>
              <p className="text-xs text-muted">
                Preview: Runs at <span className="font-semibold text-foreground">{String(cronHour).padStart(2, '0')}:{String(cronMinute).padStart(2, '0')}</span> ({cronDow}) in trading timezone
              </p>
            </div>
          )}

          {/* Interval Fields */}
          {triggerType === 'interval' && (
            <div className="space-y-3 rounded-lg border border-border/50 bg-background p-4">
              <div>
                <label className="mb-1 block text-xs text-muted">Interval (minutes)</label>
                <input
                  type="number"
                  min={1}
                  max={1440}
                  value={intervalMinutes}
                  onChange={(e) => setIntervalMinutes(parseInt(e.target.value))}
                  className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus:border-accent focus:outline-none"
                />
              </div>
              <p className="text-xs text-muted">
                Preview: Runs every <span className="font-semibold text-foreground">{intervalMinutes} minutes</span>
                {intervalMinutes >= 60 && (
                  <span> ({Math.floor(intervalMinutes / 60)}h {intervalMinutes % 60}m)</span>
                )}
              </p>
            </div>
          )}

          {/* Once (Date) Fields */}
          {triggerType === 'once' && (
            <div className="space-y-3 rounded-lg border border-border/50 bg-background p-4">
              {/* Mode selector */}
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setOnceMode('delay')}
                  className={cn(
                    'flex-1 rounded-lg border px-3 py-2 text-xs font-medium transition-colors',
                    onceMode === 'delay'
                      ? 'border-accent bg-accent/10 text-accent-light'
                      : 'border-border bg-card text-muted hover:text-foreground'
                  )}
                >
                  ⏱️ Delay
                </button>
                <button
                  type="button"
                  onClick={() => setOnceMode('datetime')}
                  className={cn(
                    'flex-1 rounded-lg border px-3 py-2 text-xs font-medium transition-colors',
                    onceMode === 'datetime'
                      ? 'border-accent bg-accent/10 text-accent-light'
                      : 'border-border bg-card text-muted hover:text-foreground'
                  )}
                >
                  📅 Specific Time
                </button>
              </div>

              {onceMode === 'delay' ? (
                <div>
                  <label className="mb-1 block text-xs text-muted">Delay (minutes from now)</label>
                  <input
                    type="number"
                    min={1}
                    max={10080}
                    value={onceDelayMinutes}
                    onChange={(e) => setOnceDelayMinutes(parseInt(e.target.value))}
                    className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus:border-accent focus:outline-none"
                  />
                  <p className="mt-2 text-xs text-muted">
                    Preview: Runs in <span className="font-semibold text-foreground">
                      {onceDelayMinutes >= 60
                        ? `${Math.floor(onceDelayMinutes / 60)}h ${onceDelayMinutes % 60}m`
                        : `${onceDelayMinutes} minutes`}
                    </span> from now
                  </p>
                </div>
              ) : (
                <div>
                  <label className="mb-1 block text-xs text-muted">Date & Time</label>
                  <input
                    type="datetime-local"
                    value={onceDatetime}
                    onChange={(e) => setOnceDatetime(e.target.value)}
                    className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus:border-accent focus:outline-none"
                  />
                  {onceDatetime && (
                    <p className="mt-2 text-xs text-muted">
                      Preview: Runs at <span className="font-semibold text-foreground">
                        {new Date(onceDatetime).toLocaleString()}
                      </span>
                    </p>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Event Type */}
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">Action</label>
            <div className="space-y-1.5">
              {EVENT_TYPE_OPTIONS.map((opt) => (
                <label
                  key={opt.value}
                  className={cn(
                    'flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors',
                    eventType === opt.value
                      ? 'border-accent bg-accent/5'
                      : 'border-border hover:border-border-hover'
                  )}
                >
                  <input
                    type="radio"
                    name="eventType"
                    value={opt.value}
                    checked={eventType === opt.value}
                    onChange={(e) => setEventType(e.target.value)}
                    className="sr-only"
                  />
                  <div
                    className={cn(
                      'flex h-4 w-4 items-center justify-center rounded-full border-2',
                      eventType === opt.value ? 'border-accent' : 'border-border'
                    )}
                  >
                    {eventType === opt.value && <div className="h-2 w-2 rounded-full bg-accent" />}
                  </div>
                  <div>
                    <div className="text-sm font-medium text-foreground">{opt.label}</div>
                    <div className="text-xs text-muted">{opt.description}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Conditions */}
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">Conditions</label>
            <div className="flex gap-4">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={requireTradingDay}
                  onChange={(e) => setRequireTradingDay(e.target.checked)}
                  className="h-4 w-4 rounded border-border bg-background text-accent focus:ring-accent"
                />
                <span className="text-sm text-foreground">Trading Day Only</span>
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={requireMarketOpen}
                  onChange={(e) => setRequireMarketOpen(e.target.checked)}
                  className="h-4 w-4 rounded border-border bg-background text-accent focus:ring-accent"
                />
                <span className="text-sm text-foreground">Market Open Only</span>
              </label>
            </div>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={onClose} type="button">Cancel</Button>
            <Button type="submit" icon={<Plus className="h-4 w-4" />}>Add Job</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ========== Rule Trigger Card ==========

function RuleTriggerCard({
  rule,
  onToggle,
  onUpdateThreshold,
}: {
  rule: RuleTrigger;
  onToggle: (id: string) => void;
  onUpdateThreshold: (id: string, threshold: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [tempThreshold, setTempThreshold] = useState(rule.threshold);

  const typeIcon = {
    price_change: Radio,
    volatility: Activity,
    news_importance: Newspaper,
  }[rule.type] || Radio;

  const TypeIcon = typeIcon;

  const typeColor = {
    price_change: 'bg-blue-500/15 text-blue-400',
    volatility: 'bg-amber-500/15 text-amber-400',
    news_importance: 'bg-purple-500/15 text-purple-400',
  }[rule.type] || 'bg-gray-500/15 text-gray-400';

  const handleSave = () => {
    onUpdateThreshold(rule.id, tempThreshold);
    setEditing(false);
  };

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border p-4 transition-colors hover:border-border-hover sm:flex-row sm:items-center sm:gap-4">
      <div className={cn('flex h-10 w-10 shrink-0 items-center justify-center rounded-xl', typeColor)}>
        <TypeIcon className="h-5 w-5" />
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-foreground">{rule.name}</span>
          <Badge variant={rule.enabled ? 'profit' : 'muted'} dot>{rule.enabled ? 'Active' : 'Disabled'}</Badge>
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">{rule.description}</p>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
          {rule.last_triggered && (
            <span>Last: {formatRelative(rule.last_triggered)}</span>
          )}
          <span>Triggered {rule.trigger_count}x</span>
        </div>
      </div>

      {/* Threshold + Toggle */}
      <div className="flex items-center gap-2 sm:shrink-0">
        {editing ? (
          <div className="flex flex-wrap items-center gap-1.5">
            <input
              type="number"
              step="0.1"
              value={tempThreshold}
              onChange={(e) => setTempThreshold(parseFloat(e.target.value))}
              className="w-20 rounded-lg border border-accent bg-background px-2 py-1 text-right text-sm text-foreground focus:outline-none"
              autoFocus
            />
            <span className="text-xs text-muted">{rule.type === 'news_importance' ? '' : '%'}</span>
            <button
              onClick={handleSave}
              className="rounded-md bg-accent px-2 py-1 text-xs text-white hover:bg-accent/80"
            >
              Save
            </button>
            <button
              onClick={() => { setEditing(false); setTempThreshold(rule.threshold); }}
              className="rounded-md bg-card-hover px-2 py-1 text-xs text-muted hover:text-foreground"
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            onClick={() => setEditing(true)}
            className="rounded-lg bg-card-hover px-3 py-1.5 text-sm font-mono font-semibold text-foreground hover:bg-border"
          >
            {rule.threshold}{rule.type === 'news_importance' ? '' : '%'}
          </button>
        )}

        {/* Toggle */}
        <button
          onClick={() => onToggle(rule.id)}
          className={cn(
            'flex h-7 w-12 shrink-0 items-center rounded-full px-0.5 transition-colors',
            rule.enabled ? 'bg-accent' : 'bg-gray-700'
          )}
        >
          <div
            className={cn(
              'h-6 w-6 rounded-full bg-white shadow transition-transform',
              rule.enabled ? 'translate-x-5' : 'translate-x-0'
            )}
          />
        </button>
      </div>
    </div>
  );
}

// ========== Main Component ==========

export default function Scheduler() {
  const [jobs, setJobs] = useState<SchedulerJob[]>([]);
  const [history, setHistory] = useState<ExecutionRecord[]>([]);
  const [riskEvents, setRiskEvents] = useState<RiskEvent[]>([]);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [ruleTriggers, setRuleTriggers] = useState<RuleTrigger[]>([]);
  const [toggling, setToggling] = useState(false);
  const [showAddJob, setShowAddJob] = useState(false);
  const [deletingJob, setDeletingJob] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetchSchedulerJobs(),
      fetchExecutionHistory(),
      fetchRiskEvents(),
      fetchSystemStatus(),
      fetchRuleTriggers(),
    ]).then(([j, h, r, s, rt]) => {
      setJobs(j);
      setHistory(h);
      setRiskEvents(r);
      setStatus(s);
      setRuleTriggers(rt);
    }).finally(() => setLoading(false));
  }, []);

  const handleToggleTrading = async () => {
    if (!status) return;
    setToggling(true);
    await toggleTrading(!status.is_trading_enabled);
    setStatus({ ...status, is_trading_enabled: !status.is_trading_enabled });
    setToggling(false);
  };

  const handleEmergencyStop = async () => {
    if (!confirm('⚠️ Are you sure? This will close all positions immediately.')) return;
    await emergencyStop();
  };

  const handleAddJob = async (jobData: JobFormData) => {
    const newJob = await createSchedulerJob(jobData);
    setJobs((prev) => [...prev, newJob]);
  };

  const handleDeleteJob = async (jobId: string) => {
    setDeletingJob(jobId);
    await deleteSchedulerJob(jobId);
    setJobs((prev) => prev.filter((j) => j.id !== jobId));
    setDeletingJob(null);
  };

  const handleToggleJob = async (job: SchedulerJob) => {
    if (job.status === 'active') {
      const updated = await pauseSchedulerJob(job.id);
      setJobs((prev) => prev.map((j) => (j.id === job.id ? updated : j)));
    } else {
      const updated = await resumeSchedulerJob(job.id);
      setJobs((prev) => prev.map((j) => (j.id === job.id ? updated : j)));
    }
  };

  const handleToggleRule = async (ruleId: string) => {
    const rule = ruleTriggers.find((r) => r.id === ruleId);
    if (!rule) return;
    const updated = await updateRuleTrigger(ruleId, { enabled: !rule.enabled });
    setRuleTriggers((prev) => prev.map((r) => (r.id === ruleId ? updated : r)));
  };

  const handleUpdateRuleThreshold = async (ruleId: string, threshold: number) => {
    const updated = await updateRuleTrigger(ruleId, { threshold });
    setRuleTriggers((prev) => prev.map((r) => (r.id === ruleId ? updated : r)));
  };

  const riskTypeIcon: Record<string, typeof Shield> = {
    stop_loss: AlertTriangle,
    take_profit: CheckCircle,
    daily_limit: OctagonX,
    concentration: Shield,
  };

  const riskTypeVariant: Record<string, 'loss' | 'profit' | 'warning' | 'info'> = {
    stop_loss: 'loss',
    take_profit: 'profit',
    daily_limit: 'warning',
    concentration: 'info',
  };

  return (
    <div className="animate-fade-in space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Scheduler & Triggers</h1>
          <p className="mt-1 text-sm text-muted">Manage scheduled tasks, event triggers, and risk controls</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            icon={status?.is_trading_enabled ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            loading={toggling}
            onClick={handleToggleTrading}
          >
            {status?.is_trading_enabled ? 'Disable Trading' : 'Enable Trading'}
          </Button>
          <Button
            variant="danger"
            icon={<OctagonX className="h-4 w-4" />}
            onClick={handleEmergencyStop}
          >
            Emergency Stop
          </Button>
        </div>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="flex flex-col items-center justify-center py-16">
          <Loader2 className="mb-3 h-8 w-8 animate-spin text-accent" />
          <p className="text-sm text-muted">Loading scheduler data…</p>
        </div>
      )}

      {/* System Status */}
      {!loading && status && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <Card className="flex items-center gap-3 !p-4">
            <StatusDot status={status.is_running ? 'online' : 'offline'} />
            <div>
              <div className="text-xs text-muted">System</div>
              <div className="text-sm font-semibold text-foreground">
                {status.is_running ? 'Running' : 'Stopped'}
              </div>
            </div>
          </Card>
          <Card className="flex items-center gap-3 !p-4">
            <StatusDot status={status.is_trading_enabled ? 'online' : 'warning'} />
            <div>
              <div className="text-xs text-muted">Trading</div>
              <div className="text-sm font-semibold text-foreground">
                {status.is_trading_enabled ? 'Enabled' : 'Disabled'}
              </div>
            </div>
          </Card>
          <Card className="flex items-center gap-3 !p-4">
            <StatusDot status={status.market_open ? 'online' : 'offline'} />
            <div>
              <div className="text-xs text-muted">Market</div>
              <div className="text-sm font-semibold text-foreground">
                {status.market_open ? 'Open' : 'Closed'}
              </div>
            </div>
          </Card>
          <Card className="flex items-center gap-3 !p-4">
            <Zap className="h-4 w-4 text-accent" />
            <div>
              <div className="text-xs text-muted">Event Queue</div>
              <div className="text-sm font-semibold text-foreground">{status.event_queue_size}</div>
            </div>
          </Card>
          <Card className="flex items-center gap-3 !p-4">
            <Clock className="h-4 w-4 text-accent" />
            <div>
              <div className="text-xs text-muted">Scheduled Jobs</div>
              <div className="text-sm font-semibold text-foreground">{jobs.length}</div>
            </div>
          </Card>
        </div>
      )}

      {!loading && <>
      {/* Scheduled Jobs (with CRUD) */}
      <Card>
        <div className="flex items-center justify-between">
          <CardHeader title="Scheduled Jobs" subtitle={`${jobs.length} jobs configured`} />
          <Button
            icon={<Plus className="h-4 w-4" />}
            onClick={() => setShowAddJob(true)}
          >
            Add Job
          </Button>
        </div>
        <div className="mt-2 space-y-2">
          {jobs.map((job) => (
            <div
              key={job.id}
              className="flex flex-col gap-2 rounded-lg border border-border p-3 transition-colors hover:border-border-hover sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex items-center gap-3 min-w-0">
                <div
                  className={cn(
                    'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
                    job.status === 'active' ? 'bg-profit-bg' : 'bg-border'
                  )}
                >
                  <Clock
                    className={cn('h-4 w-4', job.status === 'active' ? 'text-profit' : 'text-muted')}
                  />
                </div>
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-foreground">{job.name}</div>
                  <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
                    <code className="rounded bg-card-hover px-1.5 py-0.5 font-mono text-[11px]">{job.trigger}</code>
                    {job.next_run_time && (
                      <span>Next: {formatRelative(job.next_run_time)}</span>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-1.5 sm:gap-2 sm:shrink-0">
                {job.require_trading_day && <Badge variant="muted">Trading Day</Badge>}
                {job.require_market_open && <Badge variant="muted">Market Open</Badge>}
                <Badge variant={job.status === 'active' ? 'profit' : 'muted'} dot>
                  {job.status}
                </Badge>

                {/* Pause/Resume */}
                <button
                  onClick={() => handleToggleJob(job)}
                  className={cn(
                    'rounded-lg p-1.5 transition-colors',
                    job.status === 'active'
                      ? 'text-muted hover:bg-amber-500/15 hover:text-amber-400'
                      : 'text-muted hover:bg-profit-bg hover:text-profit'
                  )}
                  title={job.status === 'active' ? 'Pause' : 'Resume'}
                >
                  {job.status === 'active' ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                </button>

                {/* Delete */}
                <button
                  onClick={() => handleDeleteJob(job.id)}
                  disabled={deletingJob === job.id}
                  className="rounded-lg p-1.5 text-muted transition-colors hover:bg-loss-bg hover:text-loss disabled:opacity-50"
                  title="Delete job"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
          {jobs.length === 0 && (
            <div className="flex flex-col items-center py-8 text-center text-sm text-muted">
              <Clock className="mb-2 h-8 w-8" />
              <p>No scheduled jobs</p>
              <p className="mt-1 text-xs">Click "Add Job" to create one</p>
            </div>
          )}
        </div>
      </Card>

      {/* Rule Triggers */}
      <Card>
        <CardHeader
          title="Rule Triggers"
          subtitle="Event-driven triggers that activate workflow analysis"
        />
        <div className="mt-2 space-y-3">
          {ruleTriggers.map((rule) => (
            <RuleTriggerCard
              key={rule.id}
              rule={rule}
              onToggle={handleToggleRule}
              onUpdateThreshold={handleUpdateRuleThreshold}
            />
          ))}
          {ruleTriggers.length === 0 && (
            <div className="flex flex-col items-center py-8 text-center text-sm text-muted">
              <Settings2 className="mb-2 h-8 w-8" />
              <p>No rule triggers configured</p>
            </div>
          )}
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Execution History */}
        <Card>
          <CardHeader title="Execution History" subtitle="Recent job runs" />
          <div className="space-y-2">
            {history.map((rec, idx) => (
              <div
                key={idx}
                className="flex flex-col gap-1.5 rounded-lg border border-border/50 p-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="flex items-center gap-3 min-w-0">
                  {rec.success ? (
                    <CheckCircle className="h-4 w-4 shrink-0 text-profit" />
                  ) : (
                    <XCircle className="h-4 w-4 shrink-0 text-loss" />
                  )}
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-foreground">{rec.job_id}</div>
                    <div className="text-xs text-muted">{formatRelative(rec.executed_at)}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2 sm:shrink-0">
                  {rec.duration_ms != null && rec.duration_ms > 0 && (
                    <span className="text-xs text-muted-foreground">
                      {formatDuration(rec.duration_ms / 1000)}
                    </span>
                  )}
                  {rec.error && (
                    <Badge variant="loss">{rec.error}</Badge>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Risk Events */}
        <Card>
          <CardHeader title="Risk Events" subtitle="Recent risk management actions" />
          {riskEvents.length === 0 ? (
            <div className="flex items-center justify-center py-8 text-sm text-muted">
              <Shield className="mr-2 h-4 w-4" />
              No risk events recorded
            </div>
          ) : (
            <div className="space-y-2">
              {riskEvents.map((evt, idx) => {
                const evtType = evt.type ?? 'unknown';
                const Icon = riskTypeIcon[evtType] || Shield;
                const variant = riskTypeVariant[evtType] || 'info';
                return (
                  <div
                    key={idx}
                    className="flex items-center justify-between rounded-lg border border-border p-3 transition-colors hover:border-border-hover"
                  >
                    <div className="flex items-center gap-3">
                      <Icon className={cn('h-4 w-4', {
                        'text-loss': variant === 'loss',
                        'text-profit': variant === 'profit',
                        'text-warning': variant === 'warning',
                        'text-info': variant === 'info',
                      })} />
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-foreground">{evt.symbol ?? '—'}</span>
                          <Badge variant={variant}>{evtType.replace('_', ' ')}</Badge>
                        </div>
                        <p className="mt-0.5 text-xs text-muted-foreground">{evt.message ?? ''}</p>
                      </div>
                    </div>
                    <span className="text-xs text-muted">{evt.timestamp ? formatRelative(evt.timestamp) : '—'}</span>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </div>

      </>}

      {/* Add Job Dialog */}
      <AddJobDialog
        open={showAddJob}
        onClose={() => setShowAddJob(false)}
        onSubmit={handleAddJob}
      />
    </div>
  );
}
