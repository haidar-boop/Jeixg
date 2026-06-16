import type { Order } from '../api/types';
import { fmtTime, num, signalClass, usd } from '../format';

export function OrdersTable({ data }: { data: Order[] }) {
  return (
    <div className="panel">
      <h3>Recent Orders</h3>
      {data.length === 0 ? (
        <div className="empty">No orders yet.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Time</th><th>Symbol</th><th>Side</th><th>Type</th>
              <th>Qty</th><th>Filled</th><th>Avg Price</th><th>Status</th>
            </tr>
          </thead>
          <tbody>
            {data.map((o, i) => (
              <tr key={i}>
                <td>{fmtTime(o.time)}</td>
                <td>{o.symbol}</td>
                <td><span className={`badge ${signalClass(o.side)}`}>{o.side.toUpperCase()}</span></td>
                <td>{o.type}</td>
                <td>{num(o.quantity, 0)}</td>
                <td>{num(o.filled_quantity, 0)}</td>
                <td>{o.avg_fill_price ? usd(o.avg_fill_price) : '—'}</td>
                <td><span className="badge">{o.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
