import type { RiskMetricsData } from '../api/types';
import { cls, pct, usd } from '../format';

export function RiskMetrics({ data }: { data: RiskMetricsData }) {
  const items: { label: string; value: string; cls?: string }[] = [
    { label: 'Max Daily Loss Limit', value: pct(data.max_daily_loss_pct) },
    { label: 'Max Drawdown Limit', value: pct(data.max_drawdown_pct ?? 0) },
    { label: 'Max Position Size', value: pct(data.max_position_pct ?? 0) },
    { label: 'Today P&L', value: pct(data.day_pnl_pct ?? 0), cls: cls(data.day_pnl_pct ?? 0) },
    { label: 'Gross Exposure', value: pct(data.gross_exposure) },
  ];
  if (data.current_drawdown != null)
    items.push({ label: 'Current Drawdown', value: pct(data.current_drawdown), cls: 'neg' });
  if (data.var_95 != null)
    items.push({ label: 'VaR (95%)', value: pct(data.var_95), cls: 'neg' });
  if (data.buying_power != null)
    items.push({ label: 'Buying Power', value: usd(data.buying_power) });

  return (
    <div className="panel">
      <h3>Risk Controls</h3>
      <div className="cards">
        {items.map((i) => (
          <div className="card" key={i.label}>
            <div className="label">{i.label}</div>
            <div className={`value ${i.cls ?? ''}`}>{i.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
