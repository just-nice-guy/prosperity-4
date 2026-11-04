import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../api/client";
import { DatasetInfo, RunRecord } from "../api/types";
import { Panel } from "../components/Panel";
import { StatCard } from "../components/StatCard";
import { RunCreateForm } from "../features/run-config/RunCreateForm";
import { RunHistoryList } from "../features/run-history/RunHistoryList";

export function RunsPage() {
  const datasetsQuery = useQuery({
    queryKey: ["datasets"],
    queryFn: () => apiFetch<DatasetInfo[]>("/api/datasets")
  });
  const runsQuery = useQuery({
    queryKey: ["runs"],
    queryFn: () => apiFetch<RunRecord[]>("/api/runs"),
    refetchInterval: 2500
  });

  const completedRuns = (runsQuery.data ?? []).filter((run) => run.manifest.status === "completed");
  return (
    <div className="page-stack">
      <section className="hero-banner">
        <div>
          <p className="hero-kicker">Research Workflow</p>
          <h2>Replay faster, inspect cleaner, calibrate harder.</h2>
          <p>
            This workspace is built to tighten the loop between strategy code, simulated fills, logs,
            and visual inspection.
          </p>
        </div>
        <div className="stats-grid">
          <StatCard label="Datasets" value={String(datasetsQuery.data?.length ?? 0)} />
          <StatCard label="Runs" value={String(runsQuery.data?.length ?? 0)} />
          <StatCard
            label="Completed"
            value={String(completedRuns.length)}
            tone={completedRuns.length > 0 ? "positive" : "default"}
          />
        </div>
      </section>

      <div className="two-column-layout">
        <Panel title="Launch a run" subtitle="Execution">
          {datasetsQuery.data ? <RunCreateForm datasets={datasetsQuery.data} /> : <p>Loading datasets...</p>}
        </Panel>

        <Panel title="Run history" subtitle="Artifacts">
          <RunHistoryList runs={runsQuery.data ?? []} />
        </Panel>
      </div>
    </div>
  );
}
