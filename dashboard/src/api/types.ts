// Shared API types mirroring the QuantTrade dashboard backend.

export interface Health {
  status: string;
  mode: string;            // "live" | "demo"
  broker: string;
  broker_connected: boolean;
  symbols?: string[];
  strategy?: string;
}

export interface Account {
  equity: number;
  cash: number;
  buying_power: number;
  positions_value: number;
  day_pnl: number;
  day_pnl_pct: number;
  unrealized_pnl: number;
  num_positions: number;
  status: string;
  pattern_day_trader: boolean;
}

export interface Position {
  symbol: string;
  quantity: number;
  avg_price: number;
  last_price: number;
  market_value?: number;
  unrealized_pnl: number;
  unrealized_pct?: number;
  side: string;
}

export interface Order {
  symbol: string;
  side: string;
  type: string;
  quantity: number;
  filled_quantity: number;
  avg_fill_price: number;
  status: string;
  time: string;
}

export interface EquityPoint {
  timestamp: string;
  equity: number;
}

export interface WatchRow {
  symbol: string;
  last_price: number;
  change_pct: number;
  signal: string;          // buy | sell | hold | close
  rsi: number;
  trend: string;
  held: boolean;
  position_qty: number;
}

export interface StrategyPerf {
  name: string;
  status: string;
  symbols?: number;
  day_pnl?: number;
  open_positions?: number;
  pnl?: number;
  sharpe?: number;
  trades?: number;
  win_rate?: number;
}

export interface RiskMetricsData {
  max_daily_loss_pct: number;
  max_drawdown_pct?: number;
  max_position_pct?: number;
  day_pnl_pct?: number;
  current_drawdown?: number;
  gross_exposure: number;
  buying_power?: number;
  var_95?: number;
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

export interface Clock {
  is_open: boolean | null;
  next_open?: string;
  next_close?: string;
  timestamp?: string;
}
