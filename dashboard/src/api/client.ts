// Thin fetch wrappers around the QuantTrade REST API.
// Every call falls back to an empty/neutral value if the backend is down so the
// dashboard renders standalone.

import type {
  EquityPoint,
  Portfolio,
  Position,
  Prediction,
  RiskMetricsData,
  ScanRow,
  StrategyPerf,
  Trade,
} from './types';

async function getJSON<T>(path: string, fallback: T): Promise<T> {
  try {
    const res = await fetch(path);
    if (!res.ok) throw new Error(`${res.status}`);
    return (await res.json()) as T;
  } catch {
    return fallback;
  }
}

export const api = {
  health: () => getJSON('/api/health', { status: 'down' }),
  portfolio: () =>
    getJSON<Portfolio>('/api/portfolio', {
      equity: 0, cash: 0, positions_value: 0, day_pnl: 0, total_pnl: 0,
    }),
  positions: () => getJSON<Position[]>('/api/positions', []),
  trades: () => getJSON<Trade[]>('/api/trades', []),
  equityCurve: () => getJSON<EquityPoint[]>('/api/equity_curve', []),
  strategies: () => getJSON<StrategyPerf[]>('/api/strategies', []),
  risk: () =>
    getJSON<RiskMetricsData>('/api/risk', {
      max_daily_loss_pct: 0, current_drawdown: 0, gross_exposure: 0, var_95: 0,
    }),
  predictions: () => getJSON<Prediction[]>('/api/predictions', []),
  scanner: () => getJSON<ScanRow[]>('/api/scanner', []),
};
