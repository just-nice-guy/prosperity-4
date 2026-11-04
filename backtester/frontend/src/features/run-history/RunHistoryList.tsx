import { Link } from "react-router-dom";
import { RunRecord } from "../../api/types";

type RunHistoryListProps = {
  runs: RunRecord[];
};

export function RunHistoryList({ runs }: RunHistoryListProps) {
  return (
    <div className="history-list">
      {runs.map((run) => (
        <Link key={run.run_id} className="history-row" to={`/runs/${run.run_id}`}>
          <div>
            <strong>{run.run_id}</strong>
            <span>{run.manifest.trader_path ?? "Unknown trader"}</span>
          </div>
          <div>
            <span className={`pill pill-${run.manifest.status}`}>{run.manifest.status}</span>
            <span>
              PnL {run.summary?.final_pnl !== undefined ? run.summary.final_pnl.toFixed(2) : "--"}
            </span>
          </div>
        </Link>
      ))}
      {runs.length === 0 ? <p className="muted-text">No run artifact found yet.</p> : null}
    </div>
  );
}
