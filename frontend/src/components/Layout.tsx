import { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
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
  LogOut,
  Menu,
  X,
} from 'lucide-react';
import { StatusDot } from '@/components/ui/StatusDot';
import { useAuthStore } from '@/stores/auth';

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
  const navigate = useNavigate();
  const { authRequired, clearToken } = useAuthStore();
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleLogout = () => {
    clearToken();
    navigate('/login', { replace: true });
  };

  const closeMobile = () => setMobileOpen(false);

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* ===== Desktop Sidebar ===== */}
      <aside className="hidden md:flex w-[220px] shrink-0 flex-col border-r border-border bg-sidebar">
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
            {authRequired && (
              <button
                onClick={handleLogout}
                className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted transition-colors hover:bg-sidebar-hover hover:text-foreground"
                title="Logout"
              >
                <LogOut className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>
      </aside>

      {/* ===== Mobile Overlay ===== */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden" onClick={closeMobile}>
          {/* Backdrop */}
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

          {/* Drawer */}
          <aside
            className="relative z-50 flex h-full w-[260px] flex-col bg-sidebar"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex h-14 items-center justify-between border-b border-border px-5">
              <div className="flex items-center gap-2.5">
                <Activity className="h-5 w-5 text-accent" />
                <span className="text-sm font-bold tracking-tight text-foreground">Agent Trader</span>
              </div>
              <button
                onClick={closeMobile}
                className="rounded-lg p-1.5 text-muted hover:bg-sidebar-hover hover:text-foreground"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Nav */}
            <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-3">
              {navItems.map(({ to, icon: Icon, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={to === '/'}
                  onClick={closeMobile}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
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
                {authRequired && (
                  <button
                    onClick={() => {
                      closeMobile();
                      handleLogout();
                    }}
                    className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted transition-colors hover:bg-sidebar-hover hover:text-foreground"
                    title="Logout"
                  >
                    <LogOut className="h-3.5 w-3.5" />
                    <span>Logout</span>
                  </button>
                )}
              </div>
            </div>
          </aside>
        </div>
      )}

      {/* ===== Main Content ===== */}
      <main className="flex-1 overflow-y-auto">
        {/* Mobile top bar */}
        <div className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-background/80 px-4 backdrop-blur-md md:hidden">
          <button
            onClick={() => setMobileOpen(true)}
            className="rounded-lg p-1.5 text-muted hover:bg-card-hover hover:text-foreground"
          >
            <Menu className="h-5 w-5" />
          </button>
          <Activity className="h-4 w-4 text-accent" />
          <span className="text-sm font-bold text-foreground">Agent Trader</span>
        </div>

        <div className="mx-auto max-w-[1400px] p-4 md:p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
