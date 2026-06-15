export const usd = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD' });
export const pct = (n: number) => `${(n * 100).toFixed(2)}%`;
export const cls = (n: number) => (n >= 0 ? 'pos' : 'neg');
