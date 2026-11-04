import { ComparisonRecord } from "../../api/types";

type ComparisonPanelProps = {
  comparison: ComparisonRecord;
};

export function ComparisonPanel({ comparison }: ComparisonPanelProps) {
  return (
    <div className="stack gap-16">
      <div className="stats-grid">
        <div className="stat-card">
          <span className="stat-label">Run ID</span>
          <span className="stat-value" style={{ fontSize: 12, fontFamily: "monospace" }}>{comparison.run_id}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Label</span>
          <span className="stat-value" style={{ fontSize: 14 }}>{comparison.label}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Trade Δ</span>
          <span className="stat-value">{String(comparison.diff.trade_count_delta ?? "--")}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">PnL Δ</span>
          <span className="stat-value">{String(comparison.diff.final_pnl_delta ?? "--")}</span>
        </div>
      </div>
      <div className="two-col">
        <div className="code-block">
          <div className="code-block-title">Local summary</div>
          <pre>{JSON.stringify(comparison.local, null, 2)}</pre>
        </div>
        <div className="code-block">
          <div className="code-block-title">Official derived summary</div>
          <pre>{JSON.stringify(comparison.official, null, 2)}</pre>
        </div>
      </div>
    </div>
  );
}
