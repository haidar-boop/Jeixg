import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { EquityPoint } from '../api/types';

export function EquityChart({ data }: { data: EquityPoint[] }) {
  const points = data.map((d) => ({
    date: d.timestamp.slice(0, 10),
    equity: d.equity,
  }));
  return (
    <div className="panel">
      <h3>Equity Curve</h3>
      {points.length === 0 ? (
        <div className="empty">No equity data yet.</div>
      ) : (
        <ResponsiveContainer width="100%" height={280}>
          <AreaChart data={points}>
            <defs>
              <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#4c8dff" stopOpacity={0.4} />
                <stop offset="100%" stopColor="#4c8dff" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#232b3a" vertical={false} />
            <XAxis dataKey="date" stroke="#8a93a6" minTickGap={40} fontSize={11} />
            <YAxis stroke="#8a93a6" domain={['auto', 'auto']} fontSize={11}
              tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
            <Tooltip contentStyle={{ background: '#141925', border: '1px solid #232b3a' }} />
            <Area type="monotone" dataKey="equity" stroke="#4c8dff" fill="url(#eq)" />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
