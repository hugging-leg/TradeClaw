/**
 * LLM Provider & Model Settings Component
 *
 * Features:
 * - Manage multiple API Providers (base_url + api_key)
 * - Manage multiple Models per Provider (id + model_id + temperature)
 * - Role assignments (agent / news_filter / memory_summary -> model id)
 * - Connectivity testing
 */

import { useEffect, useState, useCallback } from 'react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast';
import {
  fetchLLMProviders,
  updateLLMProviders,
  fetchLLMRoles,
  testLLMModel,
} from '@/api';
import type { LLMProvider, LLMModel, LLMRoles, LLMModelRef } from '@/types';
import {
  Plus,
  Trash2,
  Save,
  RotateCcw,
  Eye,
  EyeOff,
  Zap,
  Check,
  X,
  ChevronDown,
  ChevronRight,
  Loader2,
} from 'lucide-react';

// ========== Provider Editor ==========

function ModelRow({
  model,
  onChange,
  onRemove,
  onTest,
  testing,
  testResult,
}: {
  model: LLMModel;
  onChange: (m: LLMModel) => void;
  onRemove: () => void;
  onTest: () => void;
  testing: boolean;
  testResult?: { success: boolean; error?: string };
}) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border/50 bg-background/50 p-3 sm:flex-row sm:items-center sm:gap-3">
      <div className="grid flex-1 gap-2 sm:grid-cols-4">
        <div>
          <label className="mb-1 block text-[10px] font-medium uppercase tracking-wider text-muted">
            Unique Name
          </label>
          <input
            type="text"
            value={model.id}
            onChange={(e) => onChange({ ...model, id: e.target.value })}
            placeholder="e.g. gpt4o"
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent font-mono"
          />
        </div>
        <div>
          <label className="mb-1 block text-[10px] font-medium uppercase tracking-wider text-muted">
            Display Name
          </label>
          <input
            type="text"
            value={model.name}
            onChange={(e) => onChange({ ...model, name: e.target.value })}
            placeholder="GPT-4o"
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
          />
        </div>
        <div>
          <label className="mb-1 block text-[10px] font-medium uppercase tracking-wider text-muted">
            Model ID (API)
          </label>
          <input
            type="text"
            value={model.model_id}
            onChange={(e) => onChange({ ...model, model_id: e.target.value })}
            placeholder="gpt-4o"
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent font-mono"
          />
        </div>
        <div>
          <label className="mb-1 block text-[10px] font-medium uppercase tracking-wider text-muted">
            Temperature
          </label>
          <input
            type="number"
            min={0}
            max={2}
            step={0.1}
            value={model.temperature}
            onChange={(e) => onChange({ ...model, temperature: Number(e.target.value) })}
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
          />
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <Button
          variant="ghost"
          size="sm"
          onClick={onTest}
          disabled={testing || !model.id}
          title="Test connectivity"
        >
          {testing ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : testResult ? (
            testResult.success ? (
              <Check className="h-3.5 w-3.5 text-profit" />
            ) : (
              <X className="h-3.5 w-3.5 text-loss" />
            )
          ) : (
            <Zap className="h-3.5 w-3.5" />
          )}
        </Button>
        <Button variant="ghost" size="sm" onClick={onRemove} title="Remove model">
          <Trash2 className="h-3.5 w-3.5 text-loss" />
        </Button>
      </div>
    </div>
  );
}

function ProviderCard({
  provider,
  onChange,
  onRemove,
  onTestModel,
  testingModel,
  testResults,
}: {
  provider: LLMProvider;
  onChange: (p: LLMProvider) => void;
  onRemove: () => void;
  onTestModel: (modelId: string) => void;
  testingModel: string | null;
  testResults: Record<string, { success: boolean; error?: string }>;
}) {
  const [expanded, setExpanded] = useState(true);
  const [showKey, setShowKey] = useState(false);

  return (
    <Card className="overflow-hidden">
      {/* Provider header */}
      <div className="flex items-start gap-3">
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-1 shrink-0 rounded p-0.5 text-muted hover:text-foreground transition-colors"
        >
          {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </button>
        <div className="min-w-0 flex-1">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className="mb-1 block text-[10px] font-medium uppercase tracking-wider text-muted">
                Provider ID
              </label>
              <input
                type="text"
                value={provider.id}
                onChange={(e) => onChange({ ...provider, id: e.target.value })}
                placeholder="openai"
                className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent font-mono"
              />
            </div>
            <div>
              <label className="mb-1 block text-[10px] font-medium uppercase tracking-wider text-muted">
                Display Name
              </label>
              <input
                type="text"
                value={provider.name}
                onChange={(e) => onChange({ ...provider, name: e.target.value })}
                placeholder="OpenAI"
                className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
            <div>
              <label className="mb-1 block text-[10px] font-medium uppercase tracking-wider text-muted">
                Base URL
              </label>
              <input
                type="text"
                value={provider.base_url}
                onChange={(e) => onChange({ ...provider, base_url: e.target.value })}
                placeholder="https://api.openai.com/v1"
                className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent font-mono"
              />
            </div>
            <div>
              <label className="mb-1 block text-[10px] font-medium uppercase tracking-wider text-muted">
                API Key
              </label>
              <div className="flex items-center gap-1">
                <input
                  type={showKey ? 'text' : 'password'}
                  value={provider.api_key}
                  onChange={(e) => onChange({ ...provider, api_key: e.target.value })}
                  placeholder="sk-..."
                  className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent font-mono"
                />
                <button
                  type="button"
                  onClick={() => setShowKey(!showKey)}
                  className="shrink-0 rounded p-1 text-muted hover:text-foreground transition-colors"
                >
                  {showKey ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                </button>
              </div>
            </div>
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={onRemove} className="shrink-0 mt-1" title="Remove provider">
          <Trash2 className="h-4 w-4 text-loss" />
        </Button>
      </div>

      {/* Models */}
      {expanded && (
        <div className="mt-4 space-y-2">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-medium text-muted">
              Models ({provider.models.length})
            </h4>
            <Button
              variant="ghost"
              size="sm"
              onClick={() =>
                onChange({
                  ...provider,
                  models: [
                    ...provider.models,
                    { id: '', name: '', model_id: '', temperature: 0.1 },
                  ],
                })
              }
            >
              <Plus className="h-3.5 w-3.5" />
              <span className="text-xs">Add Model</span>
            </Button>
          </div>
          {provider.models.length === 0 && (
            <p className="py-4 text-center text-xs text-muted">
              No models configured. Click "Add Model" to get started.
            </p>
          )}
          {provider.models.map((model, mi) => (
            <ModelRow
              key={mi}
              model={model}
              onChange={(m) => {
                const models = [...provider.models];
                models[mi] = m;
                onChange({ ...provider, models });
              }}
              onRemove={() => {
                const models = provider.models.filter((_, i) => i !== mi);
                onChange({ ...provider, models });
              }}
              onTest={() => onTestModel(model.id)}
              testing={testingModel === model.id}
              testResult={testResults[model.id]}
            />
          ))}
        </div>
      )}
    </Card>
  );
}

// ========== Roles Editor ==========

function RolesEditor({
  roles,
  allModels,
  onChange,
}: {
  roles: LLMRoles;
  allModels: LLMModelRef[];
  onChange: (roles: LLMRoles) => void;
}) {
  const builtinRoles = [
    { key: 'agent', label: 'Agent Workflow', description: 'Default LLM for agent decision-making' },
    { key: 'news_filter', label: 'News Filter', description: 'LLM for evaluating news importance' },
    { key: 'memory_summary', label: 'Memory Summary', description: 'LLM for generating memory summaries' },
  ];

  // Find custom roles (not in builtinRoles)
  const builtinKeys = new Set(builtinRoles.map((r) => r.key));
  const customRoles = Object.entries(roles)
    .filter(([k]) => !builtinKeys.has(k))
    .map(([k, v]) => ({ key: k, label: k, description: 'Custom role', value: v }));

  const renderSelect = (roleKey: string, value: string) => (
    <select
      value={value}
      onChange={(e) => onChange({ ...roles, [roleKey]: e.target.value })}
      className="w-48 rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
    >
      <option value="">— not set —</option>
      {allModels.map((m) => (
        <option key={m.id} value={m.id}>
          {m.name} ({m.provider_name})
        </option>
      ))}
    </select>
  );

  return (
    <Card>
      <CardHeader title="Role Assignments" subtitle="Map functional roles to specific models" />
      <div className="space-y-3">
        {builtinRoles.map((role) => (
          <div
            key={role.key}
            className="flex flex-col gap-2 border-b border-border/50 py-2 last:border-0 sm:flex-row sm:items-center sm:justify-between"
          >
            <div>
              <div className="text-sm text-foreground">{role.label}</div>
              <div className="text-xs text-muted">{role.description}</div>
            </div>
            {renderSelect(role.key, roles[role.key] || '')}
          </div>
        ))}
        {customRoles.map((role) => (
          <div
            key={role.key}
            className="flex flex-col gap-2 border-b border-border/50 py-2 last:border-0 sm:flex-row sm:items-center sm:justify-between"
          >
            <div>
              <div className="flex items-center gap-2 text-sm text-foreground">
                {role.label}
                <span className="rounded bg-accent/10 px-1.5 py-0.5 text-[10px] text-accent-light">custom</span>
              </div>
              <div className="text-xs text-muted">{role.description}</div>
            </div>
            <div className="flex items-center gap-1.5">
              {renderSelect(role.key, role.value)}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  const next = { ...roles };
                  delete next[role.key];
                  onChange(next);
                }}
                title="Remove custom role"
              >
                <Trash2 className="h-3.5 w-3.5 text-loss" />
              </Button>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

// ========== Main Component ==========

export default function LLMSettings() {
  const { toast } = useToast();
  const [providers, setProviders] = useState<LLMProvider[]>([]);
  const [roles, setRoles] = useState<LLMRoles>({ agent: '', news_filter: '', memory_summary: '' });
  const [allModels, setAllModels] = useState<LLMModelRef[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  // Test state
  const [testingModel, setTestingModel] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, { success: boolean; error?: string }>>({});

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const [provRes, rolesRes] = await Promise.all([fetchLLMProviders(), fetchLLMRoles()]);
      setProviders(provRes.providers);
      setAllModels(provRes.models);
      setRoles(rolesRes);
      setDirty(false);
    } catch {
      toast('Failed to load LLM configuration', 'error');
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    load();
  }, [load]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await updateLLMProviders(providers, roles);
      setProviders(res.providers);
      setAllModels(res.models);
      setRoles(res.roles);
      setDirty(false);
      setTestResults({});
      toast('LLM configuration saved', 'success');
    } catch (e) {
      toast(`Failed to save: ${e instanceof Error ? e.message : 'Unknown error'}`, 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async (modelId: string) => {
    if (!modelId) return;
    setTestingModel(modelId);
    try {
      const res = await testLLMModel(modelId);
      setTestResults((prev) => ({ ...prev, [modelId]: { success: res.success, error: res.error } }));
      if (res.success) {
        toast(`✅ ${modelId}: OK`, 'success');
      } else {
        toast(`❌ ${modelId}: ${res.error}`, 'error');
      }
    } catch (e) {
      setTestResults((prev) => ({
        ...prev,
        [modelId]: { success: false, error: e instanceof Error ? e.message : 'Unknown error' },
      }));
      toast(`❌ Test failed: ${e instanceof Error ? e.message : 'Unknown error'}`, 'error');
    } finally {
      setTestingModel(null);
    }
  };

  const updateProvider = (index: number, p: LLMProvider) => {
    const next = [...providers];
    next[index] = p;
    setProviders(next);
    setDirty(true);
  };

  const removeProvider = (index: number) => {
    setProviders(providers.filter((_, i) => i !== index));
    setDirty(true);
  };

  const addProvider = () => {
    setProviders([
      ...providers,
      {
        id: `provider-${providers.length + 1}`,
        name: '',
        base_url: 'https://api.openai.com/v1',
        api_key: '',
        models: [],
      },
    ]);
    setDirty(true);
  };

  // Compute allModels from current draft providers (for role dropdowns)
  const draftModels: LLMModelRef[] = providers.flatMap((p) =>
    p.models
      .filter((m) => m.id)
      .map((m) => ({
        id: m.id,
        name: m.name || m.id,
        provider_id: p.id,
        provider_name: p.name || p.id,
        model_id: m.model_id,
      })),
  );

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Action bar */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-foreground">LLM Providers</h2>
          <p className="text-xs text-muted">
            Configure API providers, models, and role assignments — persisted to YAML
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" icon={<Plus className="h-4 w-4" />} onClick={addProvider}>
            Add Provider
          </Button>
          {dirty && (
            <>
              <Button variant="secondary" size="sm" icon={<RotateCcw className="h-4 w-4" />} onClick={load}>
                Reset
              </Button>
              <Button size="sm" icon={<Save className="h-4 w-4" />} loading={saving} onClick={handleSave}>
                Save All
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Providers */}
      {providers.length === 0 ? (
        <Card>
          <div className="flex flex-col items-center justify-center py-12">
            <p className="text-sm text-muted">No LLM providers configured yet.</p>
            <Button className="mt-4" size="sm" icon={<Plus className="h-4 w-4" />} onClick={addProvider}>
              Add Your First Provider
            </Button>
          </div>
        </Card>
      ) : (
        providers.map((provider, pi) => (
          <ProviderCard
            key={pi}
            provider={provider}
            onChange={(p) => updateProvider(pi, p)}
            onRemove={() => removeProvider(pi)}
            onTestModel={handleTest}
            testingModel={testingModel}
            testResults={testResults}
          />
        ))
      )}

      {/* Roles */}
      <RolesEditor
        roles={roles}
        allModels={dirty ? draftModels : allModels}
        onChange={(r) => {
          setRoles(r);
          setDirty(true);
        }}
      />
    </div>
  );
}
