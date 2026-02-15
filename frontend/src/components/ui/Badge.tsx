import { cn } from '@/utils/cn';
import type { ReactNode } from 'react';

type BadgeVariant = 'default' | 'profit' | 'loss' | 'warning' | 'info' | 'muted';

const variantStyles: Record<BadgeVariant, string> = {
  default: 'bg-accent/15 text-accent-light',
  profit: 'bg-profit-bg text-profit',
  loss: 'bg-loss-bg text-loss',
  warning: 'bg-warning-bg text-warning',
  info: 'bg-info-bg text-info',
  muted: 'bg-border text-muted-foreground',
};

interface BadgeProps {
  children: ReactNode;
  variant?: BadgeVariant;
  className?: string;
  dot?: boolean;
}

export function Badge({ children, variant = 'default', className, dot }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium',
        variantStyles[variant],
        className
      )}
    >
      {dot && (
        <span
          className={cn('h-1.5 w-1.5 rounded-full', {
            'bg-accent-light': variant === 'default',
            'bg-profit': variant === 'profit',
            'bg-loss': variant === 'loss',
            'bg-warning': variant === 'warning',
            'bg-info': variant === 'info',
            'bg-muted': variant === 'muted',
          })}
        />
      )}
      {children}
    </span>
  );
}
