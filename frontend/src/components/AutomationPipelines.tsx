/**
 * Automation Pipelines Component
 *
 * Visual representation of the automated data processing pipelines:
 * 1. News Polling → LLM Filter → Workflow Trigger
 * 2. Price Monitoring → Threshold Check → Workflow Trigger
 * 3. Risk Rules → Position Check → Auto-execute / LLM Analysis
 *
 * Also provides configuration for monitoring thresholds and news polling.
 */

import { useEffect, useState } from 'react';
import {
  Newspaper,
  TrendingUp,
  Brain,
  ArrowRight,
  Activity,
  Zap,
  Clock,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Settings2,
  Radio,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import { fetchNewsPollingStatus, triggerNewsPoll } from '@/api';

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

interface AutomationPipelinesProps {
  settings: Record<string, unknown>;
  onUpdateSetting: (key: string, val: unknown) => void;
}

interface NewsPollingStatus {
  poll_interval_minutes: number;
  max_news_per_poll: number;
  seen_count: number;
  news_api_available: boolean;
  evaluator_available: boolean;
  total_polls: number;
  total_news_fetched: number;
  total_new_news: number;
  total_important: number;
  total_triggers: number;
  last_poll: string | null;
  last_error: string | null;
}

/* ------------------------------------------------------------------ */
/* Pipeline Step Component                                             */
/* ------------------------------------------------------------------ */

function PipelineStep({
  icon: Icon,
  label,
  description,
  status,
  className,
}: {
  icon: typeof Newspaper;
  label: string;
  description: string;
  status?: 'active' | 'inactive' | 'error';
  className?: string;
}) {
  const statusColor =
    status === 'active' ? 'border-emerald-500/30 bg-emerald-500/5' :
    status === 'error' ? 'border-red-500/30 bg-red-500/5' :
    'border-zinc-700/50 bg-zinc-800/30';

  const iconColor =
    status === 'active' ? 'text-emerald-400' :
    status === 'error' ? 'text-red-400' :
    'text-zinc-500';

  return (
    <div className={cn('flex items-center gap-3 rounded-lg border px-3 py-2.5', statusColor, className)}>
      <Icon className={cn('h-4 w-4 shrink-0', iconColor)} />
      <div className="min-w-0">
        <div className="text-xs font-medium text-zinc-200">{label}</div>
        <div className="text-[10px] text-zinc-500 leading-tight">{description}</div>
      </div>
    </div>
  );
}

function Arrow() {
  return (
    <div className="flex items-center justify-center shrink-0 w-6">
      <ArrowRight className="h-3.5 w-3.5 text-zinc-600" />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Pipeline Card                                                       */
/* ------------------------------------------------------------------ */

function PipelineCard({
  title,
  description,
  enabled,
  children,
  statusBadge,
}: {
  title: string;
  description: string;
  enabled: boolean;
  children: React.ReactNode;
  statusBadge?: React.ReactNode;
}) {
  return (
    <div className={cn(
      'rounded-xl border p-5 transition-all',
      enabled ? 'border-zinc-700/60 bg-zinc-900/40' : 'border-zinc-800/40 bg-zinc-900/20 opacity-60',
    )}>
      <div className="flex items-start justify-between mb-4">
        <div>
          <h4 className="text-sm font-semibold text-zinc-200">{title}</h4>
          <p className="text-xs text-zinc-500 mt-0.5">{description}</p>
        </div>
        {statusBadge}
      </div>
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Status Badge                                                        */
/* ------------------------------------------------------------------ */

function StatusBadge({ active, label }: { active: boolean; label: string }) {
  return (
    <span className={cn(
      'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium',
      active ? 'bg-emerald-500/15 text-emerald-400' : 'bg-zinc-700 text-zinc-400',
    )}>
      {active ? <CheckCircle2 className="h-2.5 w-2.5" /> : <XCircle className="h-2.5 w-2.5" />}
      {label}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Inline Setting                                                      */
/* ------------------------------------------------------------------ */

function InlineSetting({
  label,
  value,
  suffix,
  onChange,
  step = 1,
}: {
  label: string;
  value: number | string;
  suffix?: string;
  onChange: (v: number) => void;
  step?: number;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <span className="text-xs text-zinc-400">{label}</span>
      <div className="flex items-center gap-1.5">
        <input
          type="number"
          step={step}
          value={value}
          onChange={(e) => {
            const v = parseFloat(e.target.value);
            if (!isNaN(v)) onChange(v);
          }}
          className="w-20 rounded-md border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-white text-right focus:border-blue-500 focus:outline-none font-mono"
        />
        {suffix && <span className="text-[10px] text-zinc-600">{suffix}</span>}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Main Component                                                      */
/* ------------------------------------------------------------------ */

export default function AutomationPipelines({ settings, onUpdateSetting }: AutomationPipelinesProps) {
  const [newsStatus, setNewsStatus] = useState<NewsPollingStatus | null>(null);
  const [loadingPoll, setLoadingPoll] = useState(false);

  // Fetch news polling status
  useEffect(() => {
    fetchNewsPollingStatus()
      .then((data) => setNewsStatus((data.status ?? data) as NewsPollingStatus))
      .catch(() => {});
  }, []);

  const handleManualPoll = async () => {
    setLoadingPoll(true);
    try {
      await triggerNewsPoll();
      // Refresh status
      const data = await fetchNewsPollingStatus();
      setNewsStatus((data.status ?? data) as NewsPollingStatus);
    } catch {
      // ignore
    } finally {
      setLoadingPoll(false);
    }
  };

  const newsInterval = (settings.news_poll_interval_minutes as number) ?? 5;
  const newsMaxBatch = (settings.news_poll_max_per_batch as number) ?? 20;
  const priceThreshold = (settings.price_change_threshold as number) ?? 5.0;
  const volatilityThreshold = (settings.volatility_threshold as number) ?? 8.0;
  const cooldown = (settings.rebalance_cooldown_seconds as number) ?? 3600;
  const marketEtfs = (settings.market_etfs as string) ?? 'SPY,QQQ,IWM';
  const realtimeProvider = (settings.realtime_data_provider as string) ?? '';

  const newsEnabled = newsInterval > 0;
  const realtimeEnabled = !!realtimeProvider;

  return (
    <div className="space-y-5">
      {/* Pipeline 1: News Polling → LLM → Workflow */}
      <PipelineCard
        title="News Polling Pipeline"
        description="Periodically fetch news from REST APIs, filter with LLM, and trigger trading analysis for important events"
        enabled={newsEnabled}
        statusBadge={
          <StatusBadge
            active={newsEnabled && (newsStatus?.news_api_available ?? false)}
            label={newsEnabled ? 'Active' : 'Disabled'}
          />
        }
      >
        {/* Flow visualization */}
        <div className="flex items-center gap-1 overflow-x-auto pb-2 mb-4">
          <PipelineStep
            icon={Clock}
            label="Poll News"
            description={`Every ${newsInterval} min`}
            status={newsEnabled ? 'active' : 'inactive'}
          />
          <Arrow />
          <PipelineStep
            icon={Newspaper}
            label="Fetch & Deduplicate"
            description={`Up to ${newsMaxBatch} per batch`}
            status={newsEnabled ? 'active' : 'inactive'}
          />
          <Arrow />
          <PipelineStep
            icon={Brain}
            label="LLM Importance Filter"
            description="Evaluate relevance & urgency"
            status={newsStatus?.evaluator_available ? 'active' : newsEnabled ? 'error' : 'inactive'}
          />
          <Arrow />
          <PipelineStep
            icon={Zap}
            label="Trigger Workflow"
            description="Run trading agent analysis"
            status={newsEnabled ? 'active' : 'inactive'}
          />
        </div>

        {/* Stats */}
        {newsStatus && newsEnabled && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            <StatMini label="Total Polls" value={newsStatus.total_polls} />
            <StatMini label="News Fetched" value={newsStatus.total_news_fetched} />
            <StatMini label="Important" value={newsStatus.total_important} highlight />
            <StatMini label="Triggered" value={newsStatus.total_triggers} highlight />
          </div>
        )}

        {newsStatus?.last_error && (
          <div className="flex items-start gap-2 rounded-md bg-red-900/15 border border-red-800/30 px-3 py-2 mb-4 text-xs text-red-300">
            <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            <span>Last error: {newsStatus.last_error}</span>
          </div>
        )}

        {/* Settings */}
        <div className="border-t border-zinc-800 pt-3 space-y-1">
          <div className="flex items-center gap-1.5 mb-2">
            <Settings2 className="h-3 w-3 text-zinc-500" />
            <span className="text-[11px] font-medium text-zinc-400">Configuration</span>
          </div>
          <InlineSetting
            label="Poll Interval"
            value={newsInterval}
            suffix="min (0 = disabled)"
            onChange={(v) => onUpdateSetting('news_poll_interval_minutes', v)}
          />
          <InlineSetting
            label="Max News per Batch"
            value={newsMaxBatch}
            onChange={(v) => onUpdateSetting('news_poll_max_per_batch', v)}
          />
        </div>

        {newsEnabled && (
          <div className="mt-3 flex justify-end">
            <button
              onClick={handleManualPoll}
              disabled={loadingPoll}
              className="inline-flex items-center gap-1.5 rounded-md bg-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-600 disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={cn('h-3 w-3', loadingPoll && 'animate-spin')} />
              {loadingPoll ? 'Polling…' : 'Trigger Poll Now'}
            </button>
          </div>
        )}
      </PipelineCard>

      {/* Pipeline 2: Realtime Price Monitoring → Workflow */}
      <PipelineCard
        title="Price Monitoring Pipeline"
        description="Monitor real-time price changes and volatility for held positions via WebSocket, triggering LLM analysis on significant moves"
        enabled={realtimeEnabled}
        statusBadge={
          <StatusBadge
            active={realtimeEnabled}
            label={realtimeEnabled ? `${realtimeProvider}` : 'No Provider'}
          />
        }
      >
        {/* Flow visualization */}
        <div className="flex items-center gap-1 overflow-x-auto pb-2 mb-4">
          <PipelineStep
            icon={Radio}
            label="WebSocket Feed"
            description={realtimeEnabled ? `Provider: ${realtimeProvider}` : 'Not configured'}
            status={realtimeEnabled ? 'active' : 'inactive'}
          />
          <Arrow />
          <PipelineStep
            icon={TrendingUp}
            label="Price Tracker"
            description="Track held positions"
            status={realtimeEnabled ? 'active' : 'inactive'}
          />
          <Arrow />
          <PipelineStep
            icon={Activity}
            label="Threshold Check"
            description={`Δ ≥ ${priceThreshold}% or Vol ≥ ${volatilityThreshold}%`}
            status={realtimeEnabled ? 'active' : 'inactive'}
          />
          <Arrow />
          <PipelineStep
            icon={Zap}
            label="Trigger Workflow"
            description={`Cooldown: ${cooldown}s`}
            status={realtimeEnabled ? 'active' : 'inactive'}
          />
        </div>

        {!realtimeEnabled && (
          <div className="flex items-start gap-2 rounded-md bg-amber-900/15 border border-amber-800/30 px-3 py-2 mb-4 text-xs text-amber-300">
            <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            <span>No realtime data provider configured. Set one in the Providers tab to enable price monitoring.</span>
          </div>
        )}

        {/* Settings */}
        <div className="border-t border-zinc-800 pt-3 space-y-1">
          <div className="flex items-center gap-1.5 mb-2">
            <Settings2 className="h-3 w-3 text-zinc-500" />
            <span className="text-[11px] font-medium text-zinc-400">Configuration</span>
          </div>
          <InlineSetting
            label="Price Change Threshold"
            value={priceThreshold}
            suffix="%"
            step={0.5}
            onChange={(v) => onUpdateSetting('price_change_threshold', v)}
          />
          <InlineSetting
            label="Volatility Threshold"
            value={volatilityThreshold}
            suffix="%"
            step={0.5}
            onChange={(v) => onUpdateSetting('volatility_threshold', v)}
          />
          <InlineSetting
            label="Rebalance Cooldown"
            value={cooldown}
            suffix="seconds"
            step={60}
            onChange={(v) => onUpdateSetting('rebalance_cooldown_seconds', v)}
          />
          <div className="flex items-center justify-between gap-3 py-1.5">
            <span className="text-xs text-zinc-400">Market ETFs</span>
            <input
              type="text"
              value={marketEtfs}
              onChange={(e) => onUpdateSetting('market_etfs', e.target.value)}
              className="w-48 rounded-md border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-white focus:border-blue-500 focus:outline-none font-mono"
              placeholder="SPY,QQQ,IWM"
            />
          </div>
        </div>
      </PipelineCard>

      {/* How it works */}
      <div className="rounded-lg bg-zinc-900/30 border border-zinc-800/50 px-4 py-3">
        <h4 className="text-xs font-semibold text-zinc-400 mb-2">How Automation Works</h4>
        <div className="space-y-2 text-xs text-zinc-500">
          <p>
            <strong className="text-zinc-400">News Pipeline:</strong> An APScheduler job fetches news from configured REST APIs at the set interval. Each article is deduplicated by URL/title hash, then evaluated by a lightweight LLM for market relevance. Important news triggers the main trading workflow with full context.
          </p>
          <p>
            <strong className="text-zinc-400">Price Pipeline:</strong> When a WebSocket realtime provider is configured, the system subscribes to trade data for held positions and market ETFs. Price changes exceeding the threshold trigger the trading workflow. A cooldown prevents excessive triggers.
          </p>
          <p>
            <strong className="text-zinc-400">Both pipelines</strong> ultimately call <code className="rounded bg-zinc-800 px-1 py-0.5 text-zinc-400">trigger_workflow()</code>, which runs the active trading agent (configured in the Agent page) with the trigger context. The agent then decides whether to trade.
          </p>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Stat Mini                                                           */
/* ------------------------------------------------------------------ */

function StatMini({ label, value, highlight }: { label: string; value: number; highlight?: boolean }) {
  return (
    <div className="rounded-lg bg-zinc-800/40 border border-zinc-800 px-3 py-2">
      <div className="text-[10px] text-zinc-500">{label}</div>
      <div className={cn('text-sm font-semibold font-mono', highlight ? 'text-blue-400' : 'text-zinc-200')}>
        {value.toLocaleString()}
      </div>
    </div>
  );
}
