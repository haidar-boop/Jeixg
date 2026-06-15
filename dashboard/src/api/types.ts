// Shared API types mirroring the FastAPI backend responses.

export interface Portfolio {
  equity: number;
  cash: number;
  positions_value: number;
  day_pnl: number;
  total_pnl: number;
}

export interface Position {
  symbol: string;
  quantity: number;
  avg_price: number;
  last_price: number;
  unrealized_pnl: number;
  side: string;
}

export interface Trade {
  symbol: string;
  side: string;
  quantity: number;
  entry_price: number;
  exit_price: number;
  pnl: number;
  return_pct: number;
  exit_time: string;
  strategy: string;
}

export interface EquityPoint {
  timestamp: string;
  equity: number;
}

export interface StrategyPerf {
  name: string;
  status: string;
  pnl: number;
  sharpe: number;
  trades: number;
  win_rate: number;
}

export interface RiskMetricsData {
  max_daily_loss_pct: number;
  current_drawdown: number;
  gross_exposure: number;
  var_95: number;
}

export interface Prediction {
  symbol: string;
  signal: string;
  probability: number;
  model: string;
}

export interface ScanRow {
  symbol: string;
  score: number;
  reason: string;
  price: number;
  change_pct: number;
  metrics: Record<string, number>;
}
