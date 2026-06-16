import type { WatchRow } from '../api/types';
import { cls, num, pct, signalClass, usd } from '../format';

export function Watchlist({ data }: { data: WatchRow[] }) {
  return (
    <div className="panel">
      <h3>Watchlist — what the bot sees now</h3>
      {data.length === 0 ? (
        <div className="empty">No watchlist data (market data may be loading).</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Symbol</th><th>Price</th><th>Change</th><th>Signal</th>
              <th>RSI</th><th>Trend</th><th>Holding</th>
            </tr>
          </thead>
          <tbody>
            {data.map((r) => (
              <tr key={r.symbol}>
                <td>{r.symbol}</td>
                <td>{usd(r.last_price)}</td>
                <td className={cls(r.change_pct)}>{pct(r.change_pct)}</td>
                <td><span className={`badge ${signalClass(r.signal)}`}>{r.signal.toUpperCase()}</span></td>
                <td className={r.rsi >= 70 ? 'neg' : r.rsi <= 30 ? 'pos' : ''}>{num(r.rsi, 1)}</td>
                <td>{r.trend}</td>
                <td>{r.held ? `${num(r.position_qty, 0)} sh` : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
