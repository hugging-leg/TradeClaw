import { useEffect, useState } from 'react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { StatCard } from '@/components/ui/StatCard';
import { fetchOrders } from '@/api';
import { formatCurrency, formatDateTime, formatRelative } from '@/utils/format';
import { cn } from '@/utils/cn';
import { ClipboardList, CheckCircle, XCircle, Clock } from 'lucide-react';
import type { Order, OrderStatus } from '@/types';

type FilterTab = 'all' | 'active' | 'filled' | 'cancelled';

const statusBadgeVariant: Record<OrderStatus, 'profit' | 'loss' | 'warning' | 'info' | 'muted'> = {
  pending: 'warning',
  submitted: 'info',
  partial: 'info',
  filled: 'profit',
  cancelled: 'muted',
  rejected: 'loss',
  expired: 'muted',
};

export default function Orders() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [filter, setFilter] = useState<FilterTab>('all');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchOrders().then((data) => {
      setOrders(data);
      setLoading(false);
    });
  }, []);

  const filtered = orders.filter((o) => {
    if (filter === 'all') return true;
    if (filter === 'active') return ['pending', 'submitted', 'partial'].includes(o.status);
    if (filter === 'filled') return o.status === 'filled';
    if (filter === 'cancelled') return ['cancelled', 'rejected', 'expired'].includes(o.status);
    return true;
  });

  const filledOrders = orders.filter((o) => o.status === 'filled');
  const activeOrders = orders.filter((o) => ['pending', 'submitted', 'partial'].includes(o.status));
  const totalFilled = filledOrders.reduce((sum, o) => sum + (o.filled_price ?? 0) * o.filled_quantity, 0);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="animate-fade-in space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Orders</h1>
        <p className="mt-1 text-sm text-muted">Order management and execution history</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard
          label="Total Orders"
          value={String(orders.length)}
          icon={<ClipboardList className="h-4 w-4" />}
        />
        <StatCard
          label="Active"
          value={String(activeOrders.length)}
          icon={<Clock className="h-4 w-4" />}
        />
        <StatCard
          label="Filled"
          value={String(filledOrders.length)}
          change={`${orders.length > 0 ? ((filledOrders.length / orders.length) * 100).toFixed(0) : 0}% fill rate`}
          icon={<CheckCircle className="h-4 w-4" />}
        />
        <StatCard
          label="Total Filled Value"
          value={formatCurrency(totalFilled)}
          icon={<XCircle className="h-4 w-4" />}
        />
      </div>

      {/* Orders Table */}
      <Card>
        <CardHeader
          title="Order History"
          subtitle={`${filtered.length} orders`}
          action={
            <div className="flex gap-1">
              {(['all', 'active', 'filled', 'cancelled'] as FilterTab[]).map((tab) => (
                <Button
                  key={tab}
                  variant={filter === tab ? 'primary' : 'ghost'}
                  size="sm"
                  onClick={() => setFilter(tab)}
                >
                  {tab.charAt(0).toUpperCase() + tab.slice(1)}
                </Button>
              ))}
            </div>
          }
        />
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border text-left">
                <th className="pb-3 text-xs font-medium text-muted">Symbol</th>
                <th className="pb-3 text-xs font-medium text-muted">Side</th>
                <th className="pb-3 text-xs font-medium text-muted">Type</th>
                <th className="pb-3 text-right text-xs font-medium text-muted">Quantity</th>
                <th className="pb-3 text-right text-xs font-medium text-muted">Price</th>
                <th className="pb-3 text-right text-xs font-medium text-muted">Filled</th>
                <th className="pb-3 text-right text-xs font-medium text-muted">Filled Price</th>
                <th className="pb-3 text-xs font-medium text-muted">Status</th>
                <th className="pb-3 text-xs font-medium text-muted">TIF</th>
                <th className="pb-3 text-right text-xs font-medium text-muted">Created</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={10} className="py-12 text-center text-sm text-muted">
                    No orders found
                  </td>
                </tr>
              ) : (
                filtered.map((order) => (
                  <tr
                    key={order.id}
                    className="border-b border-border/50 transition-colors last:border-0 hover:bg-card-hover"
                  >
                    <td className="py-3 text-sm font-semibold text-foreground">{order.symbol}</td>
                    <td className="py-3">
                      <Badge variant={order.side === 'buy' ? 'profit' : 'loss'}>
                        {order.side.toUpperCase()}
                      </Badge>
                    </td>
                    <td className="py-3 text-sm text-muted-foreground">{order.order_type}</td>
                    <td className="py-3 text-right text-sm text-muted-foreground">{order.quantity}</td>
                    <td className="py-3 text-right text-sm text-muted-foreground">
                      {order.price ? formatCurrency(order.price) : 'Market'}
                    </td>
                    <td className="py-3 text-right text-sm text-muted-foreground">
                      {order.filled_quantity > 0 ? order.filled_quantity : '—'}
                    </td>
                    <td className="py-3 text-right text-sm text-foreground">
                      {order.filled_price ? formatCurrency(order.filled_price) : '—'}
                    </td>
                    <td className="py-3">
                      <Badge variant={statusBadgeVariant[order.status]} dot>
                        {order.status}
                      </Badge>
                    </td>
                    <td className="py-3 text-sm uppercase text-muted-foreground">{order.time_in_force}</td>
                    <td className="py-3 text-right text-xs text-muted">
                      <span title={formatDateTime(order.created_at)}>{formatRelative(order.created_at)}</span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Order Details — Expandable in future */}
      {activeOrders.length > 0 && (
        <Card>
          <CardHeader title="Active Orders" subtitle="Pending execution" />
          <div className="space-y-2">
            {activeOrders.map((order) => (
              <div
                key={order.id}
                className={cn(
                  'flex items-center justify-between rounded-lg border border-border p-4 transition-colors hover:border-border-hover'
                )}
              >
                <div className="flex items-center gap-4">
                  <Badge variant={order.side === 'buy' ? 'profit' : 'loss'}>
                    {order.side.toUpperCase()}
                  </Badge>
                  <div>
                    <span className="text-sm font-semibold text-foreground">{order.symbol}</span>
                    <span className="ml-2 text-sm text-muted-foreground">
                      {order.quantity} shares @ {order.price ? formatCurrency(order.price) : 'Market'}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <Badge variant="warning" dot>
                    {order.status}
                  </Badge>
                  <span className="text-xs text-muted">{formatRelative(order.created_at)}</span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
