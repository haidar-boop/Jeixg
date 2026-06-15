import type { Position } from '../api/types';
import { cls, usd } from '../format';

export function PositionsTable({ data }: { data: Position[] }) {
  return (
    <div className="panel">
      <h3>Open Positions</h3>
      {data.length === 0 ? (
        <div className="empty">No open positions.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Symbol</th><th>Side</th><th>Qty</th><th>Avg</th>
              <th>Last</th><th>Unrealized P&L</th>
            </tr>
          </thead>
          <tbody>
            {data.map((p) => (
              <tr key={p.symbol}>
                <td>{p.symbol}</td>
                <td><span className={`badge ${p.side === 'long' ? 'buy' : 'sell'}`}>{p.side}</span></td>
                <td>{p.quantity}</td>
                <td>{usd(p.avg_price)}</td>
                <td>{usd(p.last_price)}</td>
                <td className={cls(p.unrealized_pnl)}>{usd(p.unrealized_pnl)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
