import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api/client';
import type {
  Account, Clock, EquityPoint, Health, Order, Position, Prediction,
  RiskMetricsData, ScanRow, StrategyPerf, WatchRow,
} from './api/types';
import { AccountSummary } from './components/AccountSummary';
import { EquityChart } from './components/EquityChart';
import { MarketScanner } from './components/MarketScanner';
import { OrdersTable } from './components/OrdersTable';
import { PositionsTable } from './components/PositionsTable';
import { Predictions } from './components/Predictions';
import { RiskMetrics } from './components/RiskMetrics';
import { StrategyPerformance } from './components/StrategyPerformance';
import { Watchlist } from './components/Watchlist';
import { cls, usd } from './format';

const TABS = ['Overview', 'Positions', 'Watchlist', 'Orders', 'Scanner', 'AI', 'Risk'] as const;
type Tab = (typeof TABS)[number];

const REFRESH_MS = 20000;

const EMPTY_ACCOUNT: Account = {
  equity: 0, cash: 0, buying_power: 0, positions_value: 0, day_pnl: 0,
  day_pnl_pct: 0, unrealized_pnl: 0, num_positions: 0, status: '—', pattern_day_trader: false,
};

export default function App() {
  const [tab, setTab] = useState<Tab>('Overview');
  const [health, setHealth] = useState<Health | null>(null);
  const [clock, setClock] = useState<Clock>({ is_open: null });
  const [account, setAccount] = useState<Account>(EMPTY_ACCOUNT);
  const [positions, setPositions] = useState<Position[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [equity, setEquity] = useState<EquityPoint[]>([]);
  const [watch, setWatch] = useState<WatchRow[]>([]);
  const [strategies, setStrategies] = useState<StrategyPerf[]>([]);
  const [risk, setRisk] = useState<RiskMetricsData>({ max_daily_loss_pct: 0, gross_exposure: 0 });
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [scan, setScan] = useState<ScanRow[]>([]);
  const [updated, setUpdated] = useState<Date | null>(null);
  const [loading, setLoading] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval>>();

  const refresh = useCallback(async () => {
    setLoading(true);
    const [h, c, a, p, o, e, w, s, r, pr, sc] = await Promise.all([
      api.health(), api.clock(), api.account(), api.positions(), api.orders(),
      api.equityCurve(), api.watchlist(), api.strategies(), api.risk(),
      api.predictions(), api.scanner(),
    ]);
    setHealth(h); setClock(c); setAccount(a); setPositions(p); setOrders(o);
    setEquity(e); setWatch(w); setStrategies(s); setRisk(r); setPredictions(pr); setScan(sc);
    setUpdated(new Date()); setLoading(false);
  }, []);

  useEffect(() => {
    refresh();
    timer.current = setInterval(refresh, REFRESH_MS);
    return () => clearInterval(timer.current);
  }, [refresh]);

  const marketLabel =
    clock.is_open === null ? 'Market —' : clock.is_open ? 'Market Open' : 'Market Closed';

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="logo">Quant<span>Trade</span></div>
        <nav className="nav">
          {TABS.map((t) => (
            <button key={t} className={t === tab ? 'active' : ''} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
        </nav>
        <div className="side-meta">
          <div className={`dot ${health?.broker_connected ? 'on' : 'off'}`} />
          <span>{health ? `${health.broker} · ${health.mode}` : 'connecting…'}</span>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="metrics">
            <div className="metric"><small>Portfolio Value</small><b>{usd(account.equity)}</b></div>
            <div className="metric">
              <small>Day P&L</small>
              <b className={cls(account.day_pnl)}>{usd(account.day_pnl)}</b>
            </div>
            <div className="metric">
              <small>Open Positions</small><b>{account.num_positions}</b>
            </div>
          </div>
          <div className="topbar-right">
            <span className={`pill ${clock.is_open ? 'on' : 'off'}`}>{marketLabel}</span>
            <span className="muted small">
              {updated ? `updated ${updated.toLocaleTimeString()}` : 'loading…'}
            </span>
            <button className="refresh" onClick={refresh} disabled={loading}>
              {loading ? '…' : '↻'}
            </button>
          </div>
        </header>

        <main className="content">
          {tab === 'Overview' && (
            <>
              <AccountSummary data={account} />
              <EquityChart data={equity} />
              <div className="grid-2">
                <Watchlist data={watch} />
                <StrategyPerformance data={strategies} />
              </div>
            </>
          )}
          {tab === 'Positions' && <PositionsTable data={positions} />}
          {tab === 'Watchlist' && <Watchlist data={watch} />}
          {tab === 'Orders' && <OrdersTable data={orders} />}
          {tab === 'Scanner' && <MarketScanner data={scan} />}
          {tab === 'AI' && <Predictions data={predictions} />}
          {tab === 'Risk' && <RiskMetrics data={risk} />}
        </main>
      </div>
    </div>
  );
}
