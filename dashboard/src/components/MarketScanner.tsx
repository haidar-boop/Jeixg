import type { ScanRow } from '../api/types';
import { cls, pct, usd } from '../format';

export function MarketScanner({ data }: { data: ScanRow[] }) {
  return (
    <div className="panel">
      <h3>Market Scanner</h3>
      {data.length === 0 ? (
        <div className="empty">No scan results.</div>
      ) : (
        <table>
          <thead>
            <tr><th>Symbol</th><th>Score</th><th>Price</th><th>Change</th><th>Reason</th></tr>
          </thead>
          <tbody>
            {data.map((r) => (
              <tr key={r.symbol}>
                <td>{r.symbol}</td>
                <td>{r.score.toFixed(2)}</td>
                <td>{usd(r.price)}</td>
                <td className={cls(r.change_pct)}>{pct(r.change_pct)}</td>
                <td style={{ textAlign: 'left' }}>{r.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
