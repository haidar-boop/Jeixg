import type { StrategyPerf } from '../api/types';
import { cls, pct, usd } from '../format';

export function StrategyPerformance({ data }: { data: StrategyPerf[] }) {
  return (
    <div className="panel">
      <h3>Strategy Performance</h3>
      {data.length === 0 ? (
        <div className="empty">No strategies running.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Strategy</th><th>Status</th><th>P&L</th>
              <th>Sharpe</th><th>Trades</th><th>Win Rate</th>
            </tr>
          </thead>
          <tbody>
            {data.map((s) => (
              <tr key={s.name}>
                <td>{s.name}</td>
                <td><span className="badge">{s.status}</span></td>
                <td className={cls(s.pnl)}>{usd(s.pnl)}</td>
                <td>{s.sharpe.toFixed(2)}</td>
                <td>{s.trades}</td>
                <td>{pct(s.win_rate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
