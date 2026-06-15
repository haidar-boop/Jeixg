import type { Prediction } from '../api/types';
import { pct } from '../format';

export function Predictions({ data }: { data: Prediction[] }) {
  return (
    <div className="panel">
      <h3>AI Predictions</h3>
      {data.length === 0 ? (
        <div className="empty">No predictions available.</div>
      ) : (
        <table>
          <thead>
            <tr><th>Symbol</th><th>Signal</th><th>Probability</th><th>Model</th></tr>
          </thead>
          <tbody>
            {data.map((p) => (
              <tr key={p.symbol}>
                <td>{p.symbol}</td>
                <td><span className={`badge ${p.signal === 'buy' ? 'buy' : 'sell'}`}>{p.signal}</span></td>
                <td>{pct(p.probability)}</td>
                <td>{p.model}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
