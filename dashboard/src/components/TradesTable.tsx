import type { Trade } from '../api/types';
import { cls, pct, usd } from '../format';

export function TradesTable({ data }: { data: Trade[] }) {
  return (
    <div className="panel">
      <h3>Trade History</h3>
      {data.length === 0 ? (
        <div className="empty">No trades recorded.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Symbol</th><th>Side</th><th>Qty</th><th>Entry</th>
              <th>Exit</th><th>P&L</th><th>Return</th><th>Strategy</th>
            </tr>
          </thead>
          <tbody>
            {data.slice().reverse().map((t, i) => (
              <tr key={i}>
                <td>{t.symbol}</td>
                <td><span className={`badge ${t.side === 'long' ? 'buy' : 'sell'}`}>{t.side}</span></td>
                <td>{t.quantity}</td>
                <td>{usd(t.entry_price)}</td>
                <td>{usd(t.exit_price)}</td>
                <td className={cls(t.pnl)}>{usd(t.pnl)}</td>
                <td className={cls(t.return_pct)}>{pct(t.return_pct)}</td>
                <td>{t.strategy}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
