import { ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../api/client";
import { RunRecord } from "../api/types";

type ShellProps = {
  children: ReactNode;
};

function IconData() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="1" y="3" width="14" height="10" rx="1.5" />
      <line x1="5" y1="3" x2="5" y2="13" />
      <line x1="10" y1="3" x2="10" y2="13" />
      <line x1="1" y1="7" x2="15" y2="7" />
    </svg>
  );
}

function IconBacktest() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="4,2 13,8 4,14" fill="currentColor" stroke="none" opacity="0.3" />
      <polygon points="4,2 13,8 4,14" />
    </svg>
  );
}

function IconResults() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="1,11 5,7 8,9 11,5 15,8" />
      <line x1="1" y1="14" x2="15" y2="14" />
    </svg>
  );
}

function IconVisualizer() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="1" y="1" width="14" height="14" rx="1.5" />
      <polyline points="4,10 7,6 10,8 13,4" />
      <line x1="4" y1="12" x2="4" y2="10" />
      <line x1="7" y1="12" x2="7" y2="6" />
      <line x1="10" y1="12" x2="10" y2="8" />
    </svg>
  );
}

function IconResearch() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="7" cy="7" r="4" />
      <line x1="10" y1="10" x2="14" y2="14" />
      <polyline points="5,7 7,9 9,5" />
    </svg>
  );
}

function IconCpcv() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="1" y="2" width="14" height="12" rx="1.5" />
      <line x1="1" y1="6" x2="15" y2="6" />
      <line x1="1" y1="10" x2="15" y2="10" />
      <line x1="5.5" y1="2" x2="5.5" y2="14" />
      <line x1="10.5" y1="2" x2="10.5" y2="14" />
    </svg>
  );
}

function IconOptimization() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="8" cy="8" r="6" />
      <circle cx="8" cy="8" r="3" />
      <circle cx="8" cy="8" r="0.8" fill="currentColor" />
      <line x1="8" y1="1" x2="8" y2="3" />
      <line x1="8" y1="13" x2="8" y2="15" />
      <line x1="1" y1="8" x2="3" y2="8" />
      <line x1="13" y1="8" x2="15" y2="8" />
    </svg>
  );
}

function IconSettings() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="8" cy="8" r="2.5" />
      <path d="M6.8 1.5h2.4l.4 1.7a5.5 5.5 0 011.3.8l1.6-.6 1.2 2.1-1.2 1.1c.1.5.1.9 0 1.3l1.2 1.1-1.2 2.1-1.6-.6a5.5 5.5 0 01-1.3.8l-.4 1.7H6.8l-.4-1.7a5.5 5.5 0 01-1.3-.8l-1.6.6-1.2-2.1 1.2-1.1c-.1-.5-.1-.9 0-1.3l-1.2-1.1 1.2-2.1 1.6.6a5.5 5.5 0 011.3-.8z" />
    </svg>
  );
}

export function Shell({ children }: ShellProps) {
  const navigate = useNavigate();
  const runsQuery = useQuery({
    queryKey: ["runs"],
    queryFn: () => apiFetch<RunRecord[]>("/api/runs"),
    refetchInterval: 5000
  });

  const lastRun = (runsQuery.data ?? []).slice(-1)[0] ?? null;
  const lastPnl = lastRun?.summary?.final_pnl;
  const pnlClass = lastPnl !== undefined
    ? lastPnl >= 0 ? "pnl-positive" : "pnl-negative"
    : "pnl-neutral";

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="brand">
          <div className="brand-icon">P4</div>
          <div className="brand-text">
            <span className="brand-title">Backtester Lab</span>
            <span className="brand-sub">Prosperity 4</span>
          </div>
        </div>

        <nav className="nav-section">
          <p className="nav-label">Workspace</p>
          <NavLink to="/data" className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
            <IconData />
            Data
          </NavLink>
          <NavLink to="/backtest" className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
            <IconBacktest />
            Backtest
          </NavLink>
          <NavLink
            to={lastRun ? `/results/${lastRun.run_id}` : "/results"}
            className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
          >
            <IconResults />
            Results
          </NavLink>
          <NavLink to="/visualizer" className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
            <IconVisualizer />
            Visualizer
          </NavLink>
          <NavLink to="/synthetics" className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
            <IconCpcv />
            Synthetics
          </NavLink>
        </nav>

        <nav className="nav-section">
          <p className="nav-label">Research</p>
          <NavLink to="/research" className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
            <IconResearch />
            Monte Carlo
          </NavLink>
          <NavLink to="/cpcv" className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
            <IconCpcv />
            CPCV
          </NavLink>
          <NavLink to="/optimization" className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
            <IconOptimization />
            Optimization
          </NavLink>
        </nav>

        <nav className="nav-section">
          <p className="nav-label">System</p>
          <NavLink to="/settings" className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
            <IconSettings />
            Settings
          </NavLink>
        </nav>

        {lastRun && (
          <div className="sidebar-footer">
            <span className="sidebar-meta">Last run</span>
            <div
              className="sidebar-last-run"
              onClick={() => navigate(`/results/${lastRun.run_id}`)}
            >
              <span className="sidebar-last-run-label">
                <span className={`pill pill-${lastRun.manifest.status}`} style={{ display: "inline-flex", fontSize: 10 }}>
                  {lastRun.manifest.status}
                </span>
              </span>
              <span className="sidebar-last-run-id">{lastRun.run_id}</span>
              {lastPnl !== undefined && (
                <span className={`sidebar-last-run-pnl ${pnlClass}`}>
                  {lastPnl >= 0 ? "+" : ""}{lastPnl.toFixed(2)} XIRECs
                </span>
              )}
            </div>
          </div>
        )}
      </aside>

      <main className="app-content">{children}</main>
    </div>
  );
}
