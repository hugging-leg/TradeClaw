import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import utc from 'dayjs/plugin/utc';

dayjs.extend(utc);
dayjs.extend(relativeTime);

/**
 * 解析后端返回的 UTC 时间字符串。
 *
 * 后端所有时间均为 UTC（ISO 8601 带 +00:00 或 Z 后缀）。
 * dayjs.utc() 正确解析后，.local() 转为用户本地时区显示。
 */
function parseUTC(date: string | Date): dayjs.Dayjs {
  return dayjs.utc(date).local();
}

/** Format number as currency: $1,234.56 */
export function formatCurrency(value: number, decimals = 2): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

/** Format number with commas: 1,234.56 */
export function formatNumber(value: number, decimals = 2): string {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

/** Format percentage: +7.14% or -2.38% */
export function formatPercent(value: number, decimals = 2): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(decimals)}%`;
}

/** Format P&L with sign and color class */
export function formatPnl(value: number): { text: string; className: string } {
  const text = formatCurrency(Math.abs(value));
  if (value > 0) return { text: `+${text}`, className: 'text-profit' };
  if (value < 0) return { text: `-${text}`, className: 'text-loss' };
  return { text, className: 'text-muted-foreground' };
}

/** Format date (UTC → local): Feb 15, 2026 */
export function formatDate(date: string | Date): string {
  return parseUTC(date).format('MMM D, YYYY');
}

/** Format datetime (UTC → local): Feb 15, 2026 14:30 */
export function formatDateTime(date: string | Date): string {
  return parseUTC(date).format('MMM D, YYYY HH:mm');
}

/** Format time (UTC → local): 14:30:05 */
export function formatTime(date: string | Date): string {
  return parseUTC(date).format('HH:mm:ss');
}

/** Relative time (UTC → local): 2 hours ago */
export function formatRelative(date: string | Date): string {
  return parseUTC(date).fromNow();
}

/** Format duration in seconds to human readable */
export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

/** Format uptime from seconds */
export function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}
