import type { Portfolio } from '../api/types';
import { cls, usd } from '../format';

export function PortfolioSummary({ data }: { data: Portfolio }) {
  const cards = [
    { label: 'Equity', value: usd(data.equity), cls: '' },
    { label: 'Cash', value: usd(data.cash), cls: '' },
    { label: 'Positions Value', value: usd(data.positions_value), cls: '' },
    { label: 'Day P&L', value: usd(data.day_pnl), cls: cls(data.day_pnl) },
    { label: 'Total P&L', value: usd(data.total_pnl), cls: cls(data.total_pnl) },
  ];
  return (
    <div className="cards">
      {cards.map((c) => (
        <div className="card" key={c.label}>
          <div className="label">{c.label}</div>
          <div className={`value ${c.cls}`}>{c.value}</div>
        </div>
      ))}
    </div>
  );
}
