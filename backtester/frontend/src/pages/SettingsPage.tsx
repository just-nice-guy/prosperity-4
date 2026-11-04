import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../api/client";
import { RuntimeSettings, SystemInfo } from "../api/types";

function barColor(pct: number): string {
  if (pct < 50) return "var(--teal)";
  if (pct < 80) return "#f59e0b";
  return "var(--red)";
}

function Bar({ pct, label, sublabel }: { pct: number; label: string; sublabel?: string }) {
  return (
    <div style={{ marginBottom: 4 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, marginBottom: 3 }}>
        <span style={{ fontWeight: 600 }}>{label}</span>
        <span style={{ color: "var(--text-dim)" }}>{sublabel}</span>
      </div>
      <div style={{ height: 10, background: "var(--border)", borderRadius: 5, overflow: "hidden" }}>
        <div style={{ width: `${Math.min(100, pct)}%`, height: "100%", background: barColor(pct), borderRadius: 5, transition: "width 0.4s" }} />
      </div>
    </div>
  );
}

export function SettingsPage() {
  const queryClient = useQueryClient();

  const settingsQ = useQuery({
    queryKey: ["runtime-settings"],
    queryFn: () => apiFetch<RuntimeSettings>("/api/settings"),
  });

  const sysQ = useQuery({
    queryKey: ["system-info"],
    queryFn: () => apiFetch<SystemInfo>("/api/settings/system-info"),
    refetchInterval: 3000,
  });

  const [maxConcurrent, setMaxConcurrent] = useState(4);
  const [cleanup, setCleanup] = useState(true);
  const [maxCombos, setMaxCombos] = useState(200);
  const [maxTotal, setMaxTotal] = useState(2000);
  const [cpuLimit, setCpuLimit] = useState(0);
  const [ramLimitMb, setRamLimitMb] = useState(0);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (settingsQ.data) {
      setMaxConcurrent(settingsQ.data.max_concurrent_runs);
      setCleanup(settingsQ.data.cleanup_temp_traders);
      setMaxCombos(settingsQ.data.max_optimization_combos);
      setMaxTotal(settingsQ.data.max_total_runs);
      setCpuLimit(settingsQ.data.cpu_limit);
      setRamLimitMb(settingsQ.data.ram_limit_mb);
    }
  }, [settingsQ.data]);

  const saveMut = useMutation({
    mutationFn: () =>
      apiFetch<RuntimeSettings>("/api/settings", {
        method: "PUT",
        body: JSON.stringify({
          max_concurrent_runs: maxConcurrent,
          cleanup_temp_traders: cleanup,
          max_optimization_combos: maxCombos,
          max_total_runs: maxTotal,
          cpu_limit: cpuLimit,
          ram_limit_mb: ramLimitMb,
        }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["runtime-settings"] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  const sys = sysQ.data;
  const totalRamGb = sys ? (sys.ram_total_mb / 1024) : 0;
  const usedRamGb = sys ? (sys.ram_used_mb / 1024) : 0;
  const availRamGb = sys ? (sys.ram_available_mb / 1024) : 0;
  const workerRamMb = sys?.worker_ram_mb ?? 0;
  const ramLimitGb = ramLimitMb / 1024;
  const effectiveCpu = cpuLimit > 0 ? Math.min(cpuLimit, maxConcurrent) : maxConcurrent;

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-header-left">
          <p className="page-eyebrow">System</p>
          <h1 className="page-title">Settings</h1>
          <p className="page-desc">Resource allocation and limits to prevent system overload.</p>
        </div>
      </div>

      {/* ── Live System Monitor ──────────────────────────────────────── */}
      <div className="panel">
        <div className="panel-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <p className="panel-title">System Monitor (live)</p>
          {sys && (
            <span style={{ fontSize: 11, color: "var(--text-dim)" }}>
              {sys.worker_count} worker{sys.worker_count !== 1 ? "s" : ""} running
              {sys.worker_count > 0 && ` (${workerRamMb} MB RAM)`}
            </span>
          )}
        </div>
        <div className="panel-body">
          {!sys ? (
            <p className="muted-text" style={{ fontSize: 12 }}>Loading system info...</p>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
              {/* CPU */}
              <div>
                <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 8 }}>
                  <span style={{ fontSize: 24, fontWeight: 700, color: "var(--text)" }}>{sys.cpu_percent}%</span>
                  <span style={{ fontSize: 12, color: "var(--text-dim)" }}>CPU</span>
                </div>
                <Bar pct={sys.cpu_percent} label="CPU Usage" sublabel={`${sys.cpu_logical} logical / ${sys.cpu_physical} physical cores`} />
                {cpuLimit > 0 && (
                  <Bar pct={(effectiveCpu / sys.cpu_logical) * 100} label="Backtester CPU Allocation" sublabel={`${effectiveCpu} / ${sys.cpu_logical} cores`} />
                )}
                <div style={{ marginTop: 8 }}>
                  <div className="stats-grid" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
                    <div className="stat-card"><span className="stat-label">Logical</span><span className="stat-value">{sys.cpu_logical}</span></div>
                    <div className="stat-card"><span className="stat-label">Physical</span><span className="stat-value">{sys.cpu_physical}</span></div>
                    <div className="stat-card"><span className="stat-label">Workers</span><span className="stat-value">{sys.worker_count}</span></div>
                  </div>
                </div>
              </div>
              {/* RAM */}
              <div>
                <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 8 }}>
                  <span style={{ fontSize: 24, fontWeight: 700, color: "var(--text)" }}>{usedRamGb.toFixed(1)} GB</span>
                  <span style={{ fontSize: 12, color: "var(--text-dim)" }}>/ {totalRamGb.toFixed(1)} GB RAM</span>
                </div>
                <Bar pct={sys.ram_percent} label="System RAM" sublabel={`${availRamGb.toFixed(1)} GB available`} />
                {workerRamMb > 0 && (
                  <Bar pct={(workerRamMb / sys.ram_total_mb) * 100} label="Backtester Workers" sublabel={`${workerRamMb} MB`} />
                )}
                {ramLimitMb > 0 && (
                  <Bar pct={(workerRamMb / ramLimitMb) * 100} label="Worker RAM vs Limit" sublabel={`${workerRamMb} / ${ramLimitMb} MB`} />
                )}
                <div style={{ marginTop: 8 }}>
                  <div className="stats-grid" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
                    <div className="stat-card"><span className="stat-label">Total</span><span className="stat-value">{totalRamGb.toFixed(1)} GB</span></div>
                    <div className="stat-card"><span className="stat-label">Available</span><span className="stat-value">{availRamGb.toFixed(1)} GB</span></div>
                    <div className="stat-card"><span className="stat-label">Workers</span><span className="stat-value">{workerRamMb} MB</span></div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── CPU Allocation ───────────────────────────────────────────── */}
      <div className="panel">
        <div className="panel-header"><p className="panel-title">CPU Allocation</p></div>
        <div className="panel-body stack gap-16">
          <div className="field">
            <span className="field-label">
              CPU core limit: {cpuLimit === 0 ? "No limit" : `${cpuLimit} core${cpuLimit > 1 ? "s" : ""}`}
            </span>
            <input
              type="range"
              min={0}
              max={sys?.cpu_logical ?? 16}
              step={1}
              value={cpuLimit}
              onChange={(e) => setCpuLimit(parseInt(e.target.value, 10))}
              style={{ width: "100%" }}
            />
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)" }}>
              <span>0 (no limit)</span>
              <span>{sys?.cpu_logical ?? "?"} (all cores)</span>
            </div>
            <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
              Maximum CPU cores reserved for backtester workers. 0 = unlimited, uses max concurrent runs as the only limiter.
              If set, concurrent workers are capped to min(this, max concurrent runs).
            </span>
          </div>

          <div className="field">
            <span className="field-label">Max concurrent runs: {maxConcurrent}</span>
            <input
              type="range"
              min={1}
              max={Math.min(32, (sys?.cpu_logical ?? 8) * 2)}
              step={1}
              value={maxConcurrent}
              onChange={(e) => setMaxConcurrent(parseInt(e.target.value, 10))}
              style={{ width: "100%" }}
            />
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)" }}>
              <span>1 (safe)</span>
              <span>{Math.min(32, (sys?.cpu_logical ?? 8) * 2)}</span>
            </div>
            <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
              Maximum number of worker processes running at the same time.
              Recommended: {Math.max(1, Math.floor((sys?.cpu_physical ?? 4) / 2))} to {sys?.cpu_physical ?? 4} (physical cores).
            </span>
          </div>

          {cpuLimit > 0 && maxConcurrent > cpuLimit && (
            <div style={{ padding: "8px 12px", borderRadius: "var(--radius-sm)", background: "rgba(245,158,11,0.08)", border: "1px solid rgba(245,158,11,0.25)", fontSize: 12, color: "#d97706" }}>
              Max concurrent ({maxConcurrent}) &gt; CPU limit ({cpuLimit}). Effective concurrent workers: {effectiveCpu}.
            </div>
          )}
        </div>
      </div>

      {/* ── RAM Allocation ───────────────────────────────────────────── */}
      <div className="panel">
        <div className="panel-header"><p className="panel-title">RAM Allocation</p></div>
        <div className="panel-body stack gap-16">
          <div className="field">
            <span className="field-label">
              RAM limit for workers: {ramLimitMb === 0 ? "No limit" : `${ramLimitGb >= 1 ? ramLimitGb.toFixed(1) + " GB" : ramLimitMb + " MB"}`}
            </span>
            <input
              type="range"
              min={0}
              max={Math.round(totalRamGb * 1024 * 0.9)}
              step={256}
              value={ramLimitMb}
              onChange={(e) => setRamLimitMb(parseInt(e.target.value, 10))}
              style={{ width: "100%" }}
            />
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)" }}>
              <span>0 (no limit)</span>
              <span>{(totalRamGb * 0.9).toFixed(1)} GB (90% of {totalRamGb.toFixed(1)} GB)</span>
            </div>
            <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
              Maximum total RAM usage for all backtester worker processes combined.
              When the limit is reached, new runs are queued until workers free up memory.
              0 = no limit. Each worker uses ~60-120 MB depending on dataset size.
            </span>
          </div>

          {ramLimitMb > 0 && (
            <div className="stats-grid" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
              <div className="stat-card">
                <span className="stat-label">RAM limit</span>
                <span className="stat-value">{ramLimitGb >= 1 ? ramLimitGb.toFixed(1) + " GB" : ramLimitMb + " MB"}</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Est. max workers</span>
                <span className="stat-value">~{Math.max(1, Math.floor(ramLimitMb / 80))}</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">System headroom</span>
                <span className="stat-value">{(totalRamGb - ramLimitGb).toFixed(1)} GB</span>
              </div>
            </div>
          )}

          {ramLimitMb > 0 && ramLimitMb > totalRamGb * 1024 * 0.85 && (
            <div style={{ padding: "8px 12px", borderRadius: "var(--radius-sm)", background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", fontSize: 12, color: "var(--red)" }}>
              Warning: RAM limit ({ramLimitGb.toFixed(1)} GB) is close to total system RAM ({totalRamGb.toFixed(1)} GB). Leave headroom for the OS and other applications.
            </div>
          )}
        </div>
      </div>

      {/* ── Optimization Caps ────────────────────────────────────────── */}
      <div className="panel">
        <div className="panel-header"><p className="panel-title">Optimization Caps</p></div>
        <div className="panel-body stack gap-16">
          <div className="field">
            <span className="field-label">Max parameter combinations: {maxCombos}</span>
            <input
              type="range"
              min={5}
              max={1000}
              step={5}
              value={maxCombos}
              onChange={(e) => setMaxCombos(parseInt(e.target.value, 10))}
              style={{ width: "100%" }}
            />
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)" }}>
              <span>5</span>
              <span>1000</span>
            </div>
            <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
              Hard cap per optimization. Grid search is sampled down if it exceeds this.
            </span>
          </div>

          <div className="field">
            <span className="field-label">Max total runs per optimization: {maxTotal.toLocaleString()}</span>
            <input
              type="range"
              min={10}
              max={10000}
              step={10}
              value={maxTotal}
              onChange={(e) => setMaxTotal(parseInt(e.target.value, 10))}
              style={{ width: "100%" }}
            />
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)" }}>
              <span>10</span>
              <span>10,000</span>
            </div>
            <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
              Hard cap on total runs (combinations x CPCV paths + OOS). Prevents accidentally launching thousands of runs.
            </span>
          </div>
        </div>
      </div>

      {/* ── Cleanup ──────────────────────────────────────────────────── */}
      <div className="panel">
        <div className="panel-header"><p className="panel-title">Cleanup</p></div>
        <div className="panel-body stack gap-12">
          <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
            <input type="checkbox" checked={cleanup} onChange={(e) => setCleanup(e.target.checked)} />
            <div>
              <span style={{ fontWeight: 600, fontSize: 13 }}>Auto-cleanup temporary trader scripts</span>
              <p style={{ fontSize: 11, color: "var(--text-dim)", margin: "2px 0 0" }}>
                Delete modified trader copies after each combo finishes. Disable to inspect generated scripts.
              </p>
            </div>
          </label>
        </div>
      </div>

      {/* ── Summary + Save ───────────────────────────────────────────── */}
      <div className="panel">
        <div className="panel-header"><p className="panel-title">Allocation Summary</p></div>
        <div className="panel-body">
          <div className="stats-grid">
            <div className="stat-card">
              <span className="stat-label">CPU Allocation</span>
              <span className="stat-value">{cpuLimit === 0 ? `${maxConcurrent} workers` : `${cpuLimit} core${cpuLimit > 1 ? "s" : ""}`}</span>
            </div>
            <div className="stat-card">
              <span className="stat-label">Effective Workers</span>
              <span className="stat-value">{effectiveCpu}</span>
            </div>
            <div className="stat-card">
              <span className="stat-label">RAM Allocation</span>
              <span className="stat-value">{ramLimitMb === 0 ? "Unlimited" : (ramLimitGb >= 1 ? ramLimitGb.toFixed(1) + " GB" : ramLimitMb + " MB")}</span>
            </div>
            <div className="stat-card">
              <span className="stat-label">Est. Peak RAM</span>
              <span className="stat-value">{ramLimitMb > 0 ? (ramLimitGb >= 1 ? ramLimitGb.toFixed(1) + " GB" : ramLimitMb + " MB") : `~${(effectiveCpu * 80 / 1000).toFixed(1)} GB`}</span>
            </div>
            <div className="stat-card">
              <span className="stat-label">Max Combos</span>
              <span className="stat-value">{maxCombos}</span>
            </div>
            <div className="stat-card">
              <span className="stat-label">Max Total Runs</span>
              <span className="stat-value">{maxTotal.toLocaleString()}</span>
            </div>
          </div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <button
          className="btn btn-primary"
          onClick={() => saveMut.mutate()}
          disabled={saveMut.isPending}
          style={{ minWidth: 160, padding: "10px 24px", fontSize: 14 }}
        >
          {saveMut.isPending ? "Saving..." : "Save Settings"}
        </button>
        {saved && (
          <span style={{ fontSize: 13, color: "var(--green)", fontWeight: 600 }}>Settings saved</span>
        )}
        {saveMut.isError && (
          <span className="error-text">{String((saveMut.error as Error)?.message ?? saveMut.error)}</span>
        )}
      </div>
    </div>
  );
}
