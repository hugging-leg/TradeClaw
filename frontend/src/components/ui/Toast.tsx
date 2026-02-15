import { useEffect, useState, useCallback, createContext, useContext, type ReactNode } from 'react';
import { cn } from '@/utils/cn';
import { CheckCircle, XCircle, Info, AlertTriangle, X } from 'lucide-react';

// ========== Types ==========

type ToastVariant = 'success' | 'error' | 'info' | 'warning';

interface ToastItem {
  id: number;
  message: string;
  variant: ToastVariant;
  duration: number;
}

interface ToastContextValue {
  toast: (message: string, variant?: ToastVariant, duration?: number) => void;
}

// ========== Context ==========

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within <ToastProvider>');
  return ctx;
}

// ========== Toast Item ==========

const VARIANT_META: Record<ToastVariant, { icon: typeof CheckCircle; bg: string; border: string; text: string }> = {
  success: { icon: CheckCircle, bg: 'bg-emerald-950/90', border: 'border-emerald-500/30', text: 'text-emerald-300' },
  error: { icon: XCircle, bg: 'bg-red-950/90', border: 'border-red-500/30', text: 'text-red-300' },
  info: { icon: Info, bg: 'bg-blue-950/90', border: 'border-blue-500/30', text: 'text-blue-300' },
  warning: { icon: AlertTriangle, bg: 'bg-amber-950/90', border: 'border-amber-500/30', text: 'text-amber-300' },
};

function ToastItemComponent({ item, onDismiss }: { item: ToastItem; onDismiss: (id: number) => void }) {
  const [exiting, setExiting] = useState(false);
  const meta = VARIANT_META[item.variant];
  const Icon = meta.icon;

  useEffect(() => {
    const exitTimer = setTimeout(() => setExiting(true), item.duration - 300);
    const removeTimer = setTimeout(() => onDismiss(item.id), item.duration);
    return () => {
      clearTimeout(exitTimer);
      clearTimeout(removeTimer);
    };
  }, [item.id, item.duration, onDismiss]);

  return (
    <div
      className={cn(
        'pointer-events-auto flex items-center gap-3 rounded-lg border px-4 py-3 shadow-lg backdrop-blur-sm transition-all duration-300',
        meta.bg,
        meta.border,
        exiting ? 'translate-x-full opacity-0' : 'translate-x-0 opacity-100'
      )}
    >
      <Icon className={cn('h-4 w-4 shrink-0', meta.text)} />
      <span className="text-sm text-foreground">{item.message}</span>
      <button
        onClick={() => onDismiss(item.id)}
        className="ml-2 shrink-0 text-muted hover:text-foreground"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

// ========== Provider ==========

let _nextId = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const toast = useCallback((message: string, variant: ToastVariant = 'info', duration = 3000) => {
    const id = ++_nextId;
    setItems((prev) => [...prev, { id, message, variant, duration }]);
  }, []);

  const dismiss = useCallback((id: number) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      {/* Toast container */}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2">
        {items.map((item) => (
          <ToastItemComponent key={item.id} item={item} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}
