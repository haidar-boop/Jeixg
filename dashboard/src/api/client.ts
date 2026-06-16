// Typed fetch wrappers around the QuantTrade dashboard API.
// Every call falls back to a neutral value if the backend is unreachable, so the
// UI always renders.

import type {
  Account,
  Clock,
  EquityPoint,
  Health,
  Order,
  Position,
  Prediction,
  RiskMetricsData,
  ScanRow,
  StrategyPerf,
  WatchRow,
} from './types';

async function getJSON<T>(path: string, fallback: T): Promise<T> {
  try {
    const res = await fetch(path, { headers: { Accept: 'application/json' } });
    if (!res.ok) throw new Error(String(res.status));
    return (await res.json()) as T;
  } catch {
    return fallback;
  }
}

const EMPTY_ACCOUNT: Account = {
  equity: 0, cash: 0, buying_power: 0, positions_value: 0, day_pnl: 0,
  day_pnl_pct: 0, unrealized_pnl: 0, num_positions: 0, status: '—',
  pattern_day_trader: false,
};

export const api = {
  health: () => getJSON<Health>('/api/health', {
    status: 'down', mode: 'demo', broker: '—', broker_connected: false,
  }),
  account: () => getJSON<Account>('/api/account', EMPTY_ACCOUNT),
  positions: () => getJSON<Position[]>('/api/positions', []),
  orders: () => getJSON<Order[]>('/api/orders', []),
  equityCurve: () => getJSON<EquityPoint[]>('/api/equity_curve', []),
  watchlist: () => getJSON<WatchRow[]>('/api/watchlist', []),
  clock: () => getJSON<Clock>('/api/clock', { is_open: null }),
  strategies: () => getJSON<StrategyPerf[]>('/api/strategies', []),
  risk: () => getJSON<RiskMetricsData>('/api/risk', {
    max_daily_loss_pct: 0, gross_exposure: 0,
  }),
  predictions: () => getJSON<Prediction[]>('/api/predictions', []),
  scanner: () => getJSON<ScanRow[]>('/api/scanner', []),
};
