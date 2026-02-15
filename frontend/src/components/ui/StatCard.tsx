import { cn } from '@/utils/cn';
import type { ReactNode } from 'react';
import { TrendingUp, TrendingDown } from 'lucide-react';

interface StatCardProps {
  label: string;
  value: string;
  change?: string;
  changeType?: 'profit' | 'loss' | 'neutral';
  icon?: ReactNode;
  className?: string;
}

export function StatCard({ label, value, change, changeType = 'neutral', icon, className }: StatCardProps) {
  return (
    <div
      className={cn(
        'rounded-xl border border-border bg-card p-5 transition-colors hover:border-border-hover',
        className
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted">{label}</span>
        {icon && <span className="text-muted">{icon}</span>}
      </div>
      <div className="mt-2 text-2xl font-bold tracking-tight text-foreground">{value}</div>
      {change && (
        <div className="mt-1.5 flex items-center gap-1">
          {changeType === 'profit' && <TrendingUp className="h-3.5 w-3.5 text-profit" />}
          {changeType === 'loss' && <TrendingDown className="h-3.5 w-3.5 text-loss" />}
          <span
            className={cn('text-xs font-medium', {
              'text-profit': changeType === 'profit',
              'text-loss': changeType === 'loss',
              'text-muted': changeType === 'neutral',
            })}
          >
            {change}
          </span>
        </div>
      )}
    </div>
  );
}
