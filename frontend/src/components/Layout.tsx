import { NavLink, Outlet } from 'react-router-dom';
import { cn } from '@/utils/cn';
import {
  LayoutDashboard,
  PieChart,
  ClipboardList,
  Bot,
  Clock,
  Settings,
  FlaskConical,
  Activity,
} from 'lucide-react';
import { StatusDot } from '@/components/ui/StatusDot';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/portfolio', icon: PieChart, label: 'Portfolio' },
  { to: '/orders', icon: ClipboardList, label: 'Orders' },
  { to: '/agent', icon: Bot, label: 'Agent' },
  { to: '/scheduler', icon: Clock, label: 'Scheduler' },
  { to: '/backtest', icon: FlaskConical, label: 'Backtest' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

export function Layout() {
  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar */}
      <aside className="flex w-[220px] shrink-0 flex-col border-r border-border bg-sidebar">
        {/* Logo */}
        <div className="flex h-14 items-center gap-2.5 border-b border-border px-5">
          <Activity className="h-5 w-5 text-accent" />
          <span className="text-sm font-bold tracking-tight text-foreground">Agent Trader</span>
        </div>

        {/* Nav */}
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-3">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-accent/10 text-accent-light'
                    : 'text-muted hover:bg-sidebar-hover hover:text-foreground'
                )
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="border-t border-border px-4 py-3">
          <div className="flex items-center justify-between">
            <StatusDot status="online" label="System Online" />
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[1400px] p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
