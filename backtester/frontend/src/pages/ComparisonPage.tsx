import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { apiFetch } from "../api/client";
import { ComparisonRecord } from "../api/types";
import { ComparisonPanel } from "../features/comparisons/ComparisonPanel";

export function ComparisonPage() {
  const params = useParams();
  const navigate = useNavigate();
  const comparisonId = params.comparisonId ?? "";

  const comparisonQuery = useQuery({
    queryKey: ["comparison", comparisonId],
    queryFn: () => apiFetch<ComparisonRecord>(`/api/comparisons/${comparisonId}`),
    enabled: comparisonId !== "demo" && Boolean(comparisonId)
  });

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-header-left">
          <p className="page-eyebrow">Calibration</p>
          <h1 className="page-title">Log Comparison</h1>
          <p className="page-desc">Local simulation results vs official Prosperity submission log.</p>
        </div>
        <button className="btn btn-ghost" onClick={() => navigate(-1)}>
          ← Back
        </button>
      </div>

      <div className="panel">
        <div className="panel-header">
          <div className="panel-header-left">
            <p className="panel-eyebrow">Accuracy</p>
            <p className="panel-title">Comparison Output</p>
          </div>
        </div>
        <div className="panel-body">
          {comparisonId === "demo" ? (
            <div className="empty-state">
              <span className="empty-state-icon">🔬</span>
              <span>No comparison imported yet. Paste an official log in the Results page to create one.</span>
            </div>
          ) : comparisonQuery.isLoading ? (
            <p className="muted-text">Loading comparison…</p>
          ) : comparisonQuery.data ? (
            <ComparisonPanel comparison={comparisonQuery.data} />
          ) : (
            <p className="error-text">Failed to load comparison.</p>
          )}
        </div>
      </div>
    </div>
  );
}
