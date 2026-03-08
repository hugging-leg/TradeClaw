/**
 * SSE Hook — 订阅后端 workflow 实时事件流
 *
 * 事件类型:
 * - workflow_start: workflow 开始执行
 * - step: 新的执行步骤（由 Agent ReAct 循环动态产生）
 * - step_update: 步骤状态更新
 * - llm_token: LLM 输出 token（增量推送，前端打字机效果）
 * - workflow_complete: workflow 执行完成
 * - heartbeat: 心跳（忽略）
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import { useAuthStore } from '@/stores/auth';
import type { WorkflowExecution, ExecutionStep } from '@/types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

export interface LLMTokenEvent {
  workflow_id: string;
  step_id: string;
  token: string;
  accumulated_length: number;
}

export interface AgentEventCallbacks {
  /** 新的 workflow 开始 */
  onWorkflowStart?: (data: {
    workflow_id: string;
    workflow_type: string;
    trigger: string;
    timestamp: string;
  }) => void;

  /** 新的执行步骤 */
  onStep?: (data: ExecutionStep & { workflow_id: string }) => void;

  /** 步骤状态更新 */
  onStepUpdate?: (data: {
    workflow_id: string;
    id: string;
    status: string;
    output?: string;
    input?: string;
    error?: string;
    duration_ms?: number;
    timestamp: string;
  }) => void;

  /** LLM token（增量） */
  onLLMToken?: (data: LLMTokenEvent) => void;

  /** Workflow 执行完成 */
  onWorkflowComplete?: (data: {
    workflow_id: string;
    workflow_type: string;
    trigger: string;
    success: boolean;
    error?: string;
    duration_ms: number;
    steps: ExecutionStep[];
    timestamp: string;
  }) => void;
}

/**
 * 连接到后端 SSE endpoint，接收实时 workflow 事件。
 *
 * 自动管理 EventSource 生命周期（连接、重连、token 刷新）。
 */
export function useAgentEvents(callbacks: AgentEventCallbacks) {
  const esRef = useRef<EventSource | null>(null);
  const token = useAuthStore((s) => s.token);
  const callbacksRef = useRef(callbacks);
  callbacksRef.current = callbacks;

  useEffect(() => {
    if (!token) return;

    // EventSource 不支持自定义 header，通过 query param 传 token
    const url = `${API_BASE_URL}/agent/events?token=${encodeURIComponent(token)}`;
    const es = new EventSource(url);
    esRef.current = es;

    es.addEventListener('workflow_start', (e) => {
      try {
        const data = JSON.parse(e.data);
        callbacksRef.current.onWorkflowStart?.(data);
      } catch { /* ignore parse errors */ }
    });

    es.addEventListener('step', (e) => {
      try {
        const data = JSON.parse(e.data);
        callbacksRef.current.onStep?.(data);
      } catch { /* ignore */ }
    });

    es.addEventListener('step_update', (e) => {
      try {
        const data = JSON.parse(e.data);
        callbacksRef.current.onStepUpdate?.(data);
      } catch { /* ignore */ }
    });

    es.addEventListener('llm_token', (e) => {
      try {
        const data = JSON.parse(e.data);
        callbacksRef.current.onLLMToken?.(data);
      } catch { /* ignore */ }
    });

    es.addEventListener('workflow_complete', (e) => {
      try {
        const data = JSON.parse(e.data);
        callbacksRef.current.onWorkflowComplete?.(data);
      } catch { /* ignore */ }
    });

    // heartbeat — 忽略
    es.addEventListener('heartbeat', () => {});

    es.onerror = () => {
      // EventSource 会自动重连
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [token]);
}

/**
 * 高级 hook — 自动管理 live execution 状态。
 *
 * 实现类似 Cursor Plan 的实时展示：
 * - 步骤列表由 Agent ReAct 循环动态产生（非 hardcode）
 * - LLM token 实时流式更新（打字机效果）
 * - 每个 step 有 streaming_text 字段保存实时 LLM 输出
 *
 * 返回当前正在运行的 execution（如果有）。
 * 当 workflow 完成后，调用 onComplete 回调让父组件刷新历史列表。
 */
export function useLiveExecution(onComplete?: () => void) {
  const [liveExecution, setLiveExecution] = useState<WorkflowExecution | null>(null);
  // 用 ref 存储 streaming text，避免高频 setState 导致性能问题
  const streamingTextRef = useRef<Record<string, string>>({});
  // 用于触发 streaming text 的 UI 更新（节流）
  const [streamingTexts, setStreamingTexts] = useState<Record<string, string>>({});
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleWorkflowStart = useCallback((data: {
    workflow_id: string;
    workflow_type: string;
    trigger: string;
    timestamp: string;
  }) => {
    streamingTextRef.current = {};
    setStreamingTexts({});
    setLiveExecution({
      id: data.workflow_id,
      workflow_type: data.workflow_type,
      trigger: data.trigger,
      status: 'running',
      steps: [],
      started_at: data.timestamp,
    });
  }, []);

  const handleStep = useCallback((data: ExecutionStep & { workflow_id: string }) => {
    setLiveExecution((prev) => {
      if (!prev || prev.id !== data.workflow_id) return prev;
      // 去重：如果 step id 已存在（replay 后收到重复事件），更新而非追加
      const existingIndex = prev.steps.findIndex((s) => s.id === data.id);
      const step: ExecutionStep = {
        id: data.id,
        type: data.type,
        name: data.name,
        status: data.status,
        input: data.input,
        output: data.output,
        duration_ms: data.duration_ms,
        timestamp: data.timestamp,
        error: data.error,
        parent_step_id: data.parent_step_id,
      };
      if (existingIndex >= 0) {
        // 已存在 — 用最新数据更新
        const steps = [...prev.steps];
        steps[existingIndex] = step;
        return { ...prev, steps };
      }
      return { ...prev, steps: [...prev.steps, step] };
    });
  }, []);

  const handleStepUpdate = useCallback((data: {
    workflow_id: string;
    id: string;
    status: string;
    output?: string;
    input?: string;
    error?: string;
    duration_ms?: number;
  }) => {
    setLiveExecution((prev) => {
      if (!prev || prev.id !== data.workflow_id) return prev;
      const steps = prev.steps.map((s) =>
        s.id === data.id
          ? {
              ...s,
              status: data.status as ExecutionStep['status'],
              ...(data.output !== undefined && { output: data.output }),
              ...(data.input !== undefined && { input: data.input }),
              ...(data.error !== undefined && { error: data.error }),
              ...(data.duration_ms !== undefined && { duration_ms: data.duration_ms }),
            }
          : s
      );
      return { ...prev, steps };
    });
    // 当 step 完成时，将 streaming text 合并到 step output 后清除
    if (data.status === 'completed' || data.status === 'failed') {
      const streamedText = streamingTextRef.current[data.id];
      if (streamedText && !data.output) {
        // 后端可能没有发送 output，用 streaming text 作为 fallback
        setLiveExecution((prev) => {
          if (!prev) return prev;
          const steps = prev.steps.map((s) =>
            s.id === data.id && !s.output ? { ...s, output: streamedText } : s
          );
          return { ...prev, steps };
        });
      }
      delete streamingTextRef.current[data.id];
      setStreamingTexts((prev) => {
        const next = { ...prev };
        delete next[data.id];
        return next;
      });
    }
  }, []);

  const handleLLMToken = useCallback((data: LLMTokenEvent) => {
    // 高频事件 — 先累积到 ref，节流更新 state
    const key = data.step_id;
    streamingTextRef.current[key] = (streamingTextRef.current[key] || '') + data.token;

    // 节流：每 50ms 刷新一次 UI
    if (!flushTimerRef.current) {
      flushTimerRef.current = setTimeout(() => {
        setStreamingTexts({ ...streamingTextRef.current });
        flushTimerRef.current = null;
      }, 50);
    }
  }, []);

  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  const handleWorkflowComplete = useCallback((data: {
    workflow_id: string;
    success: boolean;
    duration_ms: number;
    timestamp: string;
  }) => {
    setLiveExecution((prev) => {
      if (!prev || prev.id !== data.workflow_id) return prev;
      return {
        ...prev,
        status: data.success ? 'completed' : 'failed',
        completed_at: data.timestamp,
        total_duration_ms: data.duration_ms,
      };
    });
    streamingTextRef.current = {};
    setStreamingTexts({});

    // 延迟清除 live execution，让用户看到完成状态
    setTimeout(() => {
      setLiveExecution(null);
      onCompleteRef.current?.();
    }, 3000);
  }, []);

  // 清理 flush timer
  useEffect(() => {
    return () => {
      if (flushTimerRef.current) clearTimeout(flushTimerRef.current);
    };
  }, []);

  useAgentEvents({
    onWorkflowStart: handleWorkflowStart,
    onStep: handleStep,
    onStepUpdate: handleStepUpdate,
    onLLMToken: handleLLMToken,
    onWorkflowComplete: handleWorkflowComplete,
  });

  return { liveExecution, streamingTexts };
}
