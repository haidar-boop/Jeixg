import { useEffect, useState } from 'react';
import { api } from './api/client';
import type {
  EquityPoint,
  Portfolio,
  Position,
  Prediction,
  RiskMetricsData,
  ScanRow,
  StrategyPerf,
  Trade,
} from './api/types';
import { EquityChart } from './components/EquityChart';
import { MarketScanner } from './components/MarketScanner';
import { PortfolioSummary } from './components/PortfolioSummary';
import { PositionsTable } from './components/PositionsTable';
import { Predictions } from './components/Predictions';
import { RiskMetrics } from './components/RiskMetrics';
import { StrategyPerformance } from './components/StrategyPerformance';
import { TradesTable } from './components/TradesTable';
import { cls, usd } from './format';
import { useWebSocket } from './hooks/useWebSocket';

const TABS = ['Overview', 'Positions', 'Trades', 'Strategies', 'AI', 'Scanner'] as const;
type Tab = (typeof TABS)[number];

const EMPTY_PF: Portfolio = { equity: 0, cash: 0, positions_value: 0, day_pnl: 0, total_pnl: 0 };

export default function App() {
  const [tab, setTab] = useState<Tab>('Overview');
  const [portfolio, setPortfolio] = useState<Portfolio>(EMPTY_PF);
  const [positions, setPositions] = useState<Position[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [equity, setEquity] = useState<EquityPoint[]>([]);
  const [strategies, setStrategies] = useState<StrategyPerf[]>([]);
  const [risk, setRisk] = useState<RiskMetricsData>({
    max_daily_loss_pct: 0, current_drawdown: 0, gross_exposure: 0, var_95: 0,
  });
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [scan, setScan] = useState<ScanRow[]>([]);

  const live = useWebSocket('/ws');

  useEffect(() => {
    api.portfolio().then(setPortfolio);
    api.positions().then(setPositions);
    api.trades().then(setTrades);
    api.equityCurve().then(setEquity);
    api.strategies().then(setStrategies);
    api.risk().then(setRisk);
    api.predictions().then(setPredictions);
    api.scanner().then(setScan);
  }, []);

  useEffect(() => {
    if (live?.type === 'snapshot') {
      const d = live.data as { portfolio: Portfolio; positions: Position[] };
      if (d.portfolio) setPortfolio(d.portfolio);
      if (d.positions) setPositions(d.positions);
    }
  }, [live]);

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
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="metrics">
            <div className="metric"><small>Portfolio Value</small><b>{usd(portfolio.equity)}</b></div>
            <div className="metric">
              <small>Day P&L</small>
              <b className={cls(portfolio.day_pnl)}>{usd(portfolio.day_pnl)}</b>
            </div>
          </div>
          <div className="metric"><small>{live ? 'live' : 'connecting…'}</small></div>
        </header>

        <main className="content">
          {tab === 'Overview' && (
            <>
              <PortfolioSummary data={portfolio} />
              <EquityChart data={equity} />
              <RiskMetrics data={risk} />
            </>
          )}
          {tab === 'Positions' && <PositionsTable data={positions} />}
          {tab === 'Trades' && <TradesTable data={trades} />}
          {tab === 'Strategies' && <StrategyPerformance data={strategies} />}
          {tab === 'AI' && <Predictions data={predictions} />}
          {tab === 'Scanner' && <MarketScanner data={scan} />}
        </main>
      </div>
    </div>
  );
}
