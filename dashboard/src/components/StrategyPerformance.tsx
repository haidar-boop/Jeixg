import type { StrategyPerf } from '../api/types';
import { cls, num, pct, usd } from '../format';

export function StrategyPerformance({ data }: { data: StrategyPerf[] }) {
  return (
    <div className="panel">
      <h3>Strategy</h3>
      {data.length === 0 ? (
        <div className="empty">No active strategy.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Strategy</th><th>Status</th><th>Symbols</th><th>Open</th>
              <th>Day P&L</th><th>Sharpe</th><th>Win Rate</th>
            </tr>
          </thead>
          <tbody>
            {data.map((s) => (
              <tr key={s.name}>
                <td>{s.name}</td>
                <td><span className="badge">{s.status}</span></td>
                <td>{s.symbols ?? '—'}</td>
                <td>{s.open_positions ?? '—'}</td>
                <td className={cls(s.day_pnl ?? s.pnl ?? 0)}>
                  {s.day_pnl != null ? usd(s.day_pnl) : s.pnl != null ? usd(s.pnl) : '—'}
                </td>
                <td>{s.sharpe != null ? num(s.sharpe, 2) : '—'}</td>
                <td>{s.win_rate != null ? pct(s.win_rate) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
