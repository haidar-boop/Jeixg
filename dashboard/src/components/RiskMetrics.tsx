import type { RiskMetricsData } from '../api/types';
import { pct } from '../format';

export function RiskMetrics({ data }: { data: RiskMetricsData }) {
  const items = [
    { label: 'Max Daily Loss Limit', value: pct(data.max_daily_loss_pct) },
    { label: 'Current Drawdown', value: pct(data.current_drawdown), cls: 'neg' },
    { label: 'Gross Exposure', value: pct(data.gross_exposure) },
    { label: 'VaR (95%)', value: pct(data.var_95), cls: 'neg' },
  ];
  return (
    <div className="panel">
      <h3>Risk Metrics</h3>
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
