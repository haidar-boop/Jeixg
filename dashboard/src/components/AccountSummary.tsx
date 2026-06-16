import type { Account } from '../api/types';
import { cls, pct, usd } from '../format';

export function AccountSummary({ data }: { data: Account }) {
  const cards = [
    { label: 'Equity', value: usd(data.equity) },
    { label: 'Cash', value: usd(data.cash) },
    { label: 'Buying Power', value: usd(data.buying_power) },
    { label: 'Invested', value: usd(data.positions_value) },
    {
      label: 'Day P&L',
      value: `${usd(data.day_pnl)} (${pct(data.day_pnl_pct)})`,
      cls: cls(data.day_pnl),
    },
    { label: 'Unrealized P&L', value: usd(data.unrealized_pnl), cls: cls(data.unrealized_pnl) },
    { label: 'Open Positions', value: String(data.num_positions) },
    { label: 'Account', value: data.status },
  ];
  return (
    <div className="cards">
      {cards.map((c) => (
        <div className="card" key={c.label}>
          <div className="label">{c.label}</div>
          <div className={`value ${c.cls ?? ''}`}>{c.value}</div>
        </div>
      ))}
    </div>
  );
}
