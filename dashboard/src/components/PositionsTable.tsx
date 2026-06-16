import type { Position } from '../api/types';
import { cls, num, pct, usd } from '../format';

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
              <th>Symbol</th><th>Side</th><th>Qty</th><th>Avg Cost</th>
              <th>Last</th><th>Mkt Value</th><th>Unreal. P&L</th><th>%</th>
            </tr>
          </thead>
          <tbody>
            {data.map((p) => (
              <tr key={p.symbol}>
                <td>{p.symbol}</td>
                <td><span className={`badge ${p.side === 'long' ? 'buy' : 'sell'}`}>{p.side}</span></td>
                <td>{num(p.quantity, 0)}</td>
                <td>{usd(p.avg_price)}</td>
                <td>{usd(p.last_price)}</td>
                <td>{usd(p.market_value ?? p.last_price * p.quantity)}</td>
                <td className={cls(p.unrealized_pnl)}>{usd(p.unrealized_pnl)}</td>
                <td className={cls(p.unrealized_pct ?? 0)}>{pct(p.unrealized_pct ?? 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
