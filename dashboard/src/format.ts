export const usd = (n: number) =>
  (n ?? 0).toLocaleString('en-US', { style: 'currency', currency: 'USD' });
export const pct = (n: number) => `${((n ?? 0) * 100).toFixed(2)}%`;
export const num = (n: number, d = 2) => (n ?? 0).toFixed(d);
export const cls = (n: number) => (n >= 0 ? 'pos' : 'neg');

export function signalClass(signal: string): string {
  const s = (signal || '').toLowerCase();
  if (s === 'buy' || s === 'scale_in') return 'buy';
  if (s === 'sell' || s === 'close' || s === 'scale_out') return 'sell';
  return 'hold';
}

export function fmtTime(iso?: string): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return isNaN(d.getTime()) ? '—' : d.toLocaleString();
}
