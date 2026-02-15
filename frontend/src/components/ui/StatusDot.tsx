import { cn } from '@/utils/cn';

interface StatusDotProps {
  status: 'online' | 'offline' | 'warning';
  label?: string;
  className?: string;
}

const statusStyles = {
  online: 'bg-profit',
  offline: 'bg-loss',
  warning: 'bg-warning',
};

export function StatusDot({ status, label, className }: StatusDotProps) {
  return (
    <span className={cn('inline-flex items-center gap-2', className)}>
      <span className="relative flex h-2.5 w-2.5">
        {status === 'online' && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-profit opacity-40" />
        )}
        <span className={cn('relative inline-flex h-2.5 w-2.5 rounded-full', statusStyles[status])} />
      </span>
      {label && <span className="text-xs text-muted-foreground">{label}</span>}
    </span>
  );
}
