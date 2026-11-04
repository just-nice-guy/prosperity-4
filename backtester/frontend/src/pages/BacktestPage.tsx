import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { apiFetch } from "../api/client";
import { CpcvRun, DatasetInfo, MonteCarloRun, RunRecord } from "../api/types";

const POS_LIMIT = 80;


function RunRow({
  run,
  onOpen,
  onDelete,
}: {
  run: RunRecord;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const pnl = run.summary?.final_pnl;
  const traderFile = run.manifest.trader_path?.split(/[\\/]/).pop();
  const datasets = run.manifest.datasets ?? [];
  const datasetLabel = datasets.map((d) => `R${d.round_num}D${d.day_num}`).join(", ");

  return (
    <div className="run-row" onClick={() => onOpen(run.run_id)}>
      <div className="run-row-left">
        <span className="run-row-id">{run.run_id}</span>
        <span className="run-row-path">
          {[traderFile, run.manifest.matching_mode, datasetLabel]
            .filter(Boolean)
            .join(" · ")}
        </span>
      </div>
      <div className="run-row-right" style={{ alignItems: "center", flexDirection: "row", gap: 8 }}>
        <span className={`pill pill-${run.manifest.status}`}>{run.manifest.status}</span>
        {pnl !== undefined ? (
          <span className={pnl >= 0 ? "pnl-positive" : "pnl-negative"} style={{ fontSize: 12 }}>
            {pnl >= 0 ? "+" : ""}{pnl.toFixed(2)}
          </span>
        ) : (
          <span style={{ fontSize: 11, color: "var(--text-dim)" }}>—</span>
        )}
        <button
          className="btn btn-ghost"
          style={{ padding: "2px 6px", fontSize: 13, color: "var(--text-dim)", lineHeight: 1 }}
          onClick={(e) => { e.stopPropagation(); onDelete(run.run_id); }}
          title="Delete run"
        >
          ✕
        </button>
      </div>
    </div>
  );
}

export function BacktestPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const datasetsQuery = useQuery({
    queryKey: ["datasets"],
    queryFn: () => apiFetch<DatasetInfo[]>("/api/datasets")
  });
  const productsQuery = useQuery({
    queryKey: ["products"],
    queryFn: () => apiFetch<string[]>("/api/datasets/products")
  });
  const runsQuery = useQuery({
    queryKey: ["runs"],
    queryFn: () => apiFetch<RunRecord[]>("/api/runs"),
    refetchInterval: 2500
  });

  const datasets = datasetsQuery.data ?? [];
  const runs = (runsQuery.data ?? []).slice().reverse();
  const allProducts = productsQuery.data ?? [];

  const [traderPath, setTraderPath] = useState("");
  const [matchingMode, setMatchingMode] = useState("prosperity");
  const [fillProbability, setFillProbability] = useState(0.005);
  const [activityBoost, setActivityBoost] = useState(0.003);
  const [randomSeed, setRandomSeed] = useState("");
  const [sigma, setSigma] = useState(0.0);
  const [edgeFillBoost, setEdgeFillBoost] = useState(0.0);
  const [selectedDays, setSelectedDays] = useState<string[]>([]);
  const [selectedProducts, setSelectedProducts] = useState<string[]>([]);

  // Monte Carlo settings
  const [mcEnabled, setMcEnabled] = useState(false);
  const [mcNumPaths, setMcNumPaths] = useState(50);
  const [mcBaseSeed, setMcBaseSeed] = useState("");
  const [mcFillSkipProb, setMcFillSkipProb] = useState(0.0);
  const [mcAdverseSelection, setMcAdverseSelection] = useState(0.0);
  const [mcMinFillFraction, setMcMinFillFraction] = useState(0.5);
  const [mcMaxFillFraction, setMcMaxFillFraction] = useState(1.0);

  // CPCV settings
  const [cpcvEnabled, setCpcvEnabled] = useState(false);
  const [cpcvNGroups, setCpcvNGroups] = useState(6);
  const [cpcvKTest, setCpcvKTest] = useState(2);
  const [cpcvPurge, setCpcvPurge] = useState(0);
  const [cpcvEmbargo, setCpcvEmbargo] = useState(0.0);

  // Pre-select all datasets once they load (only on first successful load)
  useEffect(() => {
    if (datasets.length > 0 && selectedDays.length === 0) {
      setSelectedDays(datasets.map((d) => `${d.round_num}:${d.day_num}`));
    }
  }, [datasets]);

  // Pre-select all products once they load
  useEffect(() => {
    if (allProducts.length > 0 && selectedProducts.length === 0) {
      setSelectedProducts(allProducts);
    }
  }, [allProducts]);

  const toggleDay = (value: string, checked: boolean) => {
    setSelectedDays((prev) =>
      checked ? [...prev, value] : prev.filter((v) => v !== value)
    );
  };

  const toggleProduct = (product: string, checked: boolean) => {
    setSelectedProducts((prev) =>
      checked ? [...prev, product] : prev.filter((p) => p !== product)
    );
  };

  const deleteRun = useMutation({
    mutationFn: (runId: string) =>
      apiFetch(`/api/runs/${runId}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["runs"] }),
  });

  // Reset MC when switching away from invisible mode
  useEffect(() => {
    if (matchingMode !== "invisible") setMcEnabled(false);
  }, [matchingMode]);


  const mcRunsQuery = useQuery({
    queryKey: ["mc-runs"],
    queryFn: () => apiFetch<MonteCarloRun[]>("/api/research/monte-carlo"),
    refetchInterval: 3000,
  });
  const mcRuns = (mcRunsQuery.data ?? []).slice().reverse();

  const cpcvRunsQuery = useQuery({
    queryKey: ["cpcv-runs"],
    queryFn: () => apiFetch<CpcvRun[]>("/api/research/cpcv"),
    refetchInterval: 3000,
  });
  const cpcvRuns = (cpcvRunsQuery.data ?? []).slice().reverse();

  const clearAllRuns = useMutation({
    mutationFn: () => apiFetch("/api/runs", { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["runs"] }),
  });

  const handleDelete = useCallback((runId: string) => {
    deleteRun.mutate(runId);
  }, [deleteRun]);

  const buildLimitOverrides = () => {
    const limitOverrides: Record<string, number> = {};
    for (const p of allProducts) {
      if (!selectedProducts.includes(p)) limitOverrides[p] = 0;
    }
    return limitOverrides;
  };

  const buildRoundDays = () =>
    selectedDays.map((v) => {
      const [round_num, day_num] = v.split(":").map(Number);
      return { round_num, day_num };
    });

  const createRun = useMutation({
    mutationFn: async () => {
      return apiFetch<RunRecord>("/api/runs", {
        method: "POST",
        body: JSON.stringify({
          trader_path: traderPath,
          matching_mode: matchingMode,
          fill_probability: fillProbability,
          activity_boost: activityBoost,
          random_seed: randomSeed.trim() ? parseInt(randomSeed.trim(), 10) : null,
          sigma: sigma,
          edge_fill_boost: edgeFillBoost,
          round_days: buildRoundDays(),
          limit_overrides: buildLimitOverrides(),
        })
      });
    },
    onSuccess: async (data) => {
      await queryClient.invalidateQueries({ queryKey: ["runs"] });
      navigate(`/results/${data.run_id}`);
    }
  });

  const launchMc = useMutation({
    mutationFn: async () => {
      return apiFetch<MonteCarloRun>("/api/research/monte-carlo", {
        method: "POST",
        body: JSON.stringify({
          trader_path: traderPath,
          round_days: buildRoundDays(),
          num_paths: mcNumPaths,
          base_seed: mcBaseSeed.trim() ? parseInt(mcBaseSeed.trim(), 10) : null,
          fill_probability: fillProbability,
          activity_boost: activityBoost,
          sigma: sigma,
          edge_fill_boost: edgeFillBoost,
          limit_overrides: buildLimitOverrides(),
          time_limit_ms: 900,
          fill_skip_prob: mcFillSkipProb,
          adverse_selection: mcAdverseSelection,
          min_fill_fraction: mcMinFillFraction,
          max_fill_fraction: mcMaxFillFraction,
        }),
      });
    },
    onSuccess: async (data) => {
      await queryClient.invalidateQueries({ queryKey: ["mc-runs"] });
      navigate(`/research/${data.mc_id}`);
    }
  });

  const launchCpcv = useMutation({
    mutationFn: async () => {
      return apiFetch<CpcvRun>("/api/research/cpcv", {
        method: "POST",
        body: JSON.stringify({
          trader_path: traderPath,
          round_days: buildRoundDays(),
          n_groups: cpcvNGroups,
          k_test_groups: cpcvKTest,
          purge_groups: cpcvPurge,
          embargo_pct: cpcvEmbargo,
          matching_mode: matchingMode,
          fill_probability: fillProbability,
          activity_boost: activityBoost,
          sigma: sigma,
          edge_fill_boost: edgeFillBoost,
          random_seed: randomSeed.trim() ? parseInt(randomSeed.trim(), 10) : null,
          limit_overrides: buildLimitOverrides(),
          time_limit_ms: 900,
        }),
      });
    },
    onSuccess: async (data) => {
      await queryClient.invalidateQueries({ queryKey: ["cpcv-runs"] });
      navigate(`/cpcv/${data.cpcv_id}`);
    }
  });

  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    createRun.mutate();
  };

  return (
    <div className="page">
      {/* Header */}
      <div className="page-header">
        <div className="page-header-left">
          <p className="page-eyebrow">Backtest</p>
          <h1 className="page-title">Run a Strategy</h1>
          <p className="page-desc">Configure your trader and launch a local simulation.</p>
        </div>
      </div>

      <div className="split-layout" style={{ alignItems: "start" }}>
        {/* Left: Config form */}
        <div className="panel">
          <div className="panel-header">
            <div className="panel-header-left">
              <p className="panel-eyebrow">Configuration</p>
              <p className="panel-title">Strategy Setup</p>
            </div>
          </div>
          <div className="panel-body">
            <form className="stack gap-16" onSubmit={submit}>

              {/* Trader path */}
              <label className="field">
                <span className="field-label">Trader file path</span>
                <input
                  value={traderPath}
                  onChange={(e) => setTraderPath(e.target.value)}
                  placeholder="C:\Users\...\stage0\trader.py"
                  required
                />
              </label>

              {/* Matching mode */}
              <div className="field">
                <span className="field-label">Matching mode</span>
                <select value={matchingMode} onChange={(e) => setMatchingMode(e.target.value)}>
                  <option value="prosperity">Prosperity — matches against CSV market trades</option>
                  <option value="invisible">Invisible Taker — probabilistic fills (realistic)</option>
                </select>
                <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
                  {matchingMode === "invisible"
                    ? "Simulates invisible taker bots like the real exchange. Fill probability is random per tick, kept low for HFT (10k ticks/day)."
                    : "Matches passive orders against market trades from CSV data. Overfills compared to real exchange."}
                </span>
              </div>

              {/* Fill probability + activity boost — only for invisible mode */}
              {matchingMode === "invisible" && (
                <>
                  <div className="field">
                    <span className="field-label">
                      Base fill probability: {(fillProbability * 100).toFixed(2)}%
                    </span>
                    <input
                      type="range"
                      min="0.0001"
                      max="0.05"
                      step="0.0001"
                      value={fillProbability}
                      onChange={(e) => setFillProbability(parseFloat(e.target.value))}
                      style={{ width: "100%" }}
                    />
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)" }}>
                      <span>0.01%</span>
                      <span>5%</span>
                    </div>
                    <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
                      Per-tick fill chance. Keep low — with ~10k ticks/day even 0.5% yields ~50 fills.
                    </span>
                  </div>
                  <div className="field">
                    <span className="field-label">
                      Activity boost: +{(activityBoost * 100).toFixed(2)}%
                    </span>
                    <input
                      type="range"
                      min="0.000"
                      max="0.02"
                      step="0.0001"
                      value={activityBoost}
                      onChange={(e) => setActivityBoost(parseFloat(e.target.value))}
                      style={{ width: "100%" }}
                    />
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)" }}>
                      <span>0%</span>
                      <span>2%</span>
                    </div>
                    <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
                      Extra fill probability when bot-to-bot trades exist at the same tick.
                      Effective: {(fillProbability * 100).toFixed(2)}% + {(activityBoost * 100).toFixed(2)}% = {((fillProbability + activityBoost) * 100).toFixed(2)}% when active.
                    </span>
                  </div>
                  <div className="field">
                    <span className="field-label">
                      Sigma (randomize): {sigma.toFixed(3)}
                    </span>
                    <input
                      type="range"
                      min="0.0"
                      max="0.02"
                      step="0.001"
                      value={sigma}
                      onChange={(e) => setSigma(parseFloat(e.target.value))}
                      style={{ width: "100%" }}
                    />
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)" }}>
                      <span>0 (deterministic)</span>
                      <span>0.02</span>
                    </div>
                    <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
                      When &gt; 0, fill probability is drawn from N(centre, sigma) each tick, making fills more stochastic. 0 = flat probability.
                    </span>
                  </div>
                  <div className="field">
                    <span className="field-label">
                      Edge fill boost: {edgeFillBoost.toFixed(2)}
                    </span>
                    <input
                      type="range"
                      min="0.0"
                      max="2.0"
                      step="0.05"
                      value={edgeFillBoost}
                      onChange={(e) => setEdgeFillBoost(parseFloat(e.target.value))}
                      style={{ width: "100%" }}
                    />
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)" }}>
                      <span>0 (off)</span>
                      <span>2.0</span>
                    </div>
                    <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
                      Tighter quotes get more fills. Multiplier per tick of price improvement over best market quote.
                      E.g. 0.5 with 3-tick edge = +150% fill probability.
                    </span>
                  </div>
                  <label className="field">
                    <span className="field-label">Seed (optional)</span>
                    <input
                      value={randomSeed}
                      onChange={(e) => setRandomSeed(e.target.value)}
                      placeholder="Leave empty for auto seed"
                      type="number"
                    />
                    <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
                      Fixed integer seed for reproducible results. Empty = derived from run ID.
                    </span>
                  </label>
                </>
              )}

              {/* Dataset selection */}
              <div className="field">
                <span className="field-label">Datasets</span>
                {datasetsQuery.isLoading && <p className="muted-text" style={{ fontSize: 12 }}>Loading…</p>}
                {datasets.length > 0 && (
                  <div className="dataset-checkbox-grid">
                    {datasets.map((ds) => {
                      const value = `${ds.round_num}:${ds.day_num}`;
                      const checked = selectedDays.includes(value);
                      return (
                        <label key={value} className="dataset-checkbox-card">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={(e) => toggleDay(value, e.target.checked)}
                          />
                          <div className="dataset-checkbox-label">
                            <strong>Round {ds.round_num}</strong>
                            <span>Day {ds.day_num}</span>
                          </div>
                        </label>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Product selection */}
              <div className="field">
                <span className="field-label">Products</span>
                {productsQuery.isLoading && <p className="muted-text" style={{ fontSize: 12 }}>Loading…</p>}
                {allProducts.length > 0 && (
                  <div className="dataset-checkbox-grid">
                    {allProducts.map((product) => {
                      const checked = selectedProducts.includes(product);
                      return (
                        <label key={product} className="dataset-checkbox-card">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={(e) => toggleProduct(product, e.target.checked)}
                          />
                          <div className="dataset-checkbox-label">
                            <strong>{product}</strong>
                            <span>limit {POS_LIMIT}</span>
                          </div>
                        </label>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Launch */}
              <div style={{ paddingTop: 4 }}>
                <button
                  type="submit"
                  className="btn btn-primary btn-full"
                  disabled={createRun.isPending || selectedDays.length === 0 || !traderPath.trim() || selectedProducts.length === 0}
                >
                  {createRun.isPending ? "Launching…" : "Launch Simulation"}
                </button>
                {createRun.isError && (
                  <p className="error-text" style={{ marginTop: 8 }}>
                    {String(createRun.error)}
                  </p>
                )}
              </div>

            </form>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Run history */}
          <div className="panel">
            <div className="panel-header">
              <div className="panel-header-left">
                <p className="panel-eyebrow">History</p>
                <p className="panel-title">Previous Runs</p>
              </div>
              {runs.length > 0 && (
                <button
                  className="btn btn-ghost"
                  style={{ fontSize: 11, color: "var(--red)", padding: "4px 8px" }}
                  onClick={() => clearAllRuns.mutate()}
                  disabled={clearAllRuns.isPending}
                >
                  {clearAllRuns.isPending ? "Clearing…" : "Clear all"}
                </button>
              )}
            </div>
            <div className="panel-body">
              {runsQuery.isLoading && <p className="muted-text">Loading runs…</p>}
              {runs.length === 0 && !runsQuery.isLoading && (
                <div className="empty-state">
                  <span className="empty-state-icon">🚀</span>
                  <span>No runs yet. Launch your first simulation above.</span>
                </div>
              )}
              {runs.length > 0 && (
                <div className="run-list">
                  {runs.map((run) => (
                    <RunRow
                      key={run.run_id}
                      run={run}
                      onOpen={(id) => navigate(`/results/${id}`)}
                      onDelete={handleDelete}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Research block */}
          <div className="panel">
            <div className="panel-header">
              <div className="panel-header-left">
                <p className="panel-eyebrow">Research</p>
                <p className="panel-title">Research Tools</p>
              </div>
            </div>
            <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: 16 }}>

              {/* ── Monte Carlo ── */}
              <div style={{
                border: "1px solid rgba(48,54,61,0.5)",
                borderRadius: 8,
                padding: 12,
                opacity: matchingMode !== "invisible" && !mcEnabled ? 0.45 : 1,
                pointerEvents: matchingMode !== "invisible" ? "none" : "auto",
              }}>
                <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: matchingMode === "invisible" ? "pointer" : "default" }}>
                  <input
                    type="checkbox"
                    checked={mcEnabled}
                    onChange={(e) => setMcEnabled(e.target.checked)}
                    disabled={matchingMode !== "invisible"}
                  />
                  <span style={{ fontWeight: 600, fontSize: 13 }}>Monte Carlo</span>
                </label>
                <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 4, display: "block" }}>
                  Run N simulation paths with varied seeds. Produces PnL distribution, risk metrics (VaR, Sharpe, etc.).
                  {matchingMode !== "invisible" && (
                    <span style={{ color: "var(--yellow, #d29922)", display: "block", marginTop: 2 }}>
                      Requires Invisible Taker mode.
                    </span>
                  )}
                </span>

                {mcEnabled && (
                  <div className="stack gap-12" style={{ marginTop: 12 }}>
                    {/* ── Simulation paths ── */}
                    <div className="field">
                      <span className="field-label">
                        Number of paths: {mcNumPaths}
                      </span>
                      <input
                        type="range"
                        min="2"
                        max="500"
                        step="1"
                        value={mcNumPaths}
                        onChange={(e) => setMcNumPaths(parseInt(e.target.value, 10))}
                        style={{ width: "100%" }}
                      />
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)" }}>
                        <span>2</span>
                        <span>500</span>
                      </div>
                    </div>
                    <label className="field">
                      <span className="field-label">Base seed (optional)</span>
                      <input
                        value={mcBaseSeed}
                        onChange={(e) => setMcBaseSeed(e.target.value)}
                        placeholder="Leave empty for random"
                        type="number"
                      />
                      <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
                        Each path uses base_seed + i. Empty = random base.
                      </span>
                    </label>

                    {/* ── Microstructure noise ── */}
                    <div style={{ borderTop: "1px solid rgba(48,54,61,0.3)", paddingTop: 8 }}>
                      <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                        Microstructure
                      </span>
                    </div>

                    <div className="field">
                      <span className="field-label">
                        Fill skip probability: {(mcFillSkipProb * 100).toFixed(1)}%
                      </span>
                      <input
                        type="range"
                        min="0"
                        max="0.5"
                        step="0.01"
                        value={mcFillSkipProb}
                        onChange={(e) => setMcFillSkipProb(parseFloat(e.target.value))}
                        style={{ width: "100%" }}
                      />
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)" }}>
                        <span>0%</span>
                        <span>50%</span>
                      </div>
                      <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
                        Randomly discard fills that would have occurred. Simulates queue-position uncertainty.
                      </span>
                    </div>

                    <div className="field">
                      <span className="field-label">
                        Adverse selection: {mcAdverseSelection.toFixed(2)}x
                      </span>
                      <input
                        type="range"
                        min="0"
                        max="5"
                        step="0.1"
                        value={mcAdverseSelection}
                        onChange={(e) => setMcAdverseSelection(parseFloat(e.target.value))}
                        style={{ width: "100%" }}
                      />
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)" }}>
                        <span>0 (off)</span>
                        <span>5x</span>
                      </div>
                      <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
                        Boost fill probability when mid-price moves against you (toxic flow). Multiplier: fill_prob * (1 + value) on adverse ticks.
                      </span>
                    </div>

                    <div className="field">
                      <span className="field-label">
                        Fill fraction: {(mcMinFillFraction * 100).toFixed(0)}% – {(mcMaxFillFraction * 100).toFixed(0)}%
                      </span>
                      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                        <input
                          type="range"
                          min="0.05"
                          max="1"
                          step="0.05"
                          value={mcMinFillFraction}
                          onChange={(e) => {
                            const v = parseFloat(e.target.value);
                            setMcMinFillFraction(v);
                            if (v > mcMaxFillFraction) setMcMaxFillFraction(v);
                          }}
                          style={{ flex: 1 }}
                        />
                        <span style={{ fontSize: 10, color: "var(--text-dim)", minWidth: 16, textAlign: "center" }}>to</span>
                        <input
                          type="range"
                          min="0.05"
                          max="1"
                          step="0.05"
                          value={mcMaxFillFraction}
                          onChange={(e) => {
                            const v = parseFloat(e.target.value);
                            setMcMaxFillFraction(v);
                            if (v < mcMinFillFraction) setMcMinFillFraction(v);
                          }}
                          style={{ flex: 1 }}
                        />
                      </div>
                      <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
                        Portion of order quantity filled per event. Narrower = thinner liquidity.
                      </span>
                    </div>

                    {/* Launch MC button */}
                    <button
                      type="button"
                      className="btn btn-primary btn-full"
                      disabled={launchMc.isPending || selectedDays.length === 0 || !traderPath.trim() || selectedProducts.length === 0}
                      onClick={() => launchMc.mutate()}
                    >
                      {launchMc.isPending ? "Launching…" : `Launch Monte Carlo (${mcNumPaths} paths)`}
                    </button>
                    {launchMc.isError && (
                      <p className="error-text" style={{ marginTop: 4 }}>
                        {String(launchMc.error)}
                      </p>
                    )}
                  </div>
                )}

                {/* Recent MC runs */}
                {mcRuns.length > 0 && (
                  <div style={{ marginTop: 12, borderTop: "1px solid rgba(48,54,61,0.3)", paddingTop: 8 }}>
                    <span style={{ fontSize: 11, color: "var(--text-dim)", fontWeight: 500 }}>Recent runs</span>
                    <div className="run-list" style={{ marginTop: 4 }}>
                      {mcRuns.slice(0, 5).map((mc) => (
                        <div
                          key={mc.mc_id}
                          className="run-row"
                          style={{ pointerEvents: "auto" }}
                          onClick={() => navigate(`/research/${mc.mc_id}`)}
                        >
                          <div className="run-row-left">
                            <span className="run-row-id">{mc.mc_id}</span>
                            <span className="run-row-path">
                              {mc.completed_paths}/{mc.num_paths} paths
                            </span>
                          </div>
                          <span className={`pill pill-${mc.status}`} style={{ fontSize: 10 }}>{mc.status}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* ── CPCV ── */}
              <div style={{
                border: "1px solid rgba(48,54,61,0.5)",
                borderRadius: 8,
                padding: 12,
              }}>
                <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                  <input
                    type="checkbox"
                    checked={cpcvEnabled}
                    onChange={(e) => setCpcvEnabled(e.target.checked)}
                  />
                  <span style={{ fontWeight: 600, fontSize: 13 }}>CPCV</span>
                </label>
                <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 4, display: "block" }}>
                  Combinatorial Purged Cross-Validation (Lopez de Prado, 2018).
                  Tests strategy robustness across all C(N,k) data splits. Computes PBO and Deflated Sharpe Ratio.
                </span>

                {cpcvEnabled && (
                  <div className="stack gap-12" style={{ marginTop: 12 }}>
                    <div className="field">
                      <span className="field-label">N (number of folds): {cpcvNGroups}</span>
                      <input
                        type="range" min={2} max={20} step={1}
                        value={cpcvNGroups}
                        onChange={(e) => {
                          const v = parseInt(e.target.value, 10);
                          setCpcvNGroups(v);
                          if (cpcvKTest >= v) setCpcvKTest(v - 1);
                        }}
                        style={{ width: "100%" }}
                      />
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)" }}>
                        <span>2</span>
                        <span>20</span>
                      </div>
                      <span style={{ fontSize: 10, color: "var(--text-dim)" }}>
                        Splits the total tick timeline into N contiguous segments.
                      </span>
                    </div>
                    <div className="field">
                      <span className="field-label">k (test folds per split): {cpcvKTest}</span>
                      <input
                        type="range" min={1} max={Math.max(1, cpcvNGroups - 1)} step={1}
                        value={cpcvKTest}
                        onChange={(e) => setCpcvKTest(parseInt(e.target.value, 10))}
                        style={{ width: "100%" }}
                      />
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)" }}>
                        <span>1</span>
                        <span>{Math.max(1, cpcvNGroups - 1)}</span>
                      </div>
                      <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
                        C({cpcvNGroups},{cpcvKTest}) ={" "}
                        {(() => {
                          let num = 1, den = 1;
                          for (let i = 0; i < cpcvKTest; i++) {
                            num *= cpcvNGroups - i;
                            den *= i + 1;
                          }
                          return Math.round(num / den);
                        })()}{" "}
                        combinations (backtest runs).
                      </span>
                    </div>

                    <div style={{ borderTop: "1px solid rgba(48,54,61,0.3)", paddingTop: 8 }}>
                      <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                        Leakage Prevention
                      </span>
                    </div>

                    <div className="field">
                      <span className="field-label">Purge gap: {cpcvPurge} group(s)</span>
                      <input
                        type="range" min="0" max="3" step="1"
                        value={cpcvPurge}
                        onChange={(e) => setCpcvPurge(parseInt(e.target.value, 10))}
                        style={{ width: "100%" }}
                      />
                      <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
                        Minimum gap between test folds in the same combination. Prevents temporally adjacent folds from co-occurring.
                      </span>
                    </div>
                    <div className="field">
                      <span className="field-label">Embargo: {(cpcvEmbargo * 100).toFixed(0)}%</span>
                      <input
                        type="range" min="0" max="0.2" step="0.01"
                        value={cpcvEmbargo}
                        onChange={(e) => setCpcvEmbargo(parseFloat(e.target.value))}
                        style={{ width: "100%" }}
                      />
                      <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
                        Fraction of ticks dropped at fold boundaries to prevent look-ahead bias from serial correlation.
                      </span>
                    </div>

                    <button
                      type="button"
                      className="btn btn-primary btn-full"
                      disabled={launchCpcv.isPending || selectedDays.length === 0 || !traderPath.trim() || selectedProducts.length === 0}
                      onClick={() => launchCpcv.mutate()}
                    >
                      {launchCpcv.isPending
                        ? "Launching..."
                        : `Launch CPCV (${(() => {
                            let num = 1, den = 1;
                            for (let i = 0; i < cpcvKTest; i++) {
                              num *= cpcvNGroups - i;
                              den *= i + 1;
                            }
                            return Math.round(num / den);
                          })()} paths)`}
                    </button>
                    {launchCpcv.isError && (
                      <p className="error-text" style={{ marginTop: 4 }}>
                        {String(launchCpcv.error)}
                      </p>
                    )}
                  </div>
                )}

                {/* Recent CPCV runs */}
                {cpcvRuns.length > 0 && (
                  <div style={{ marginTop: 12, borderTop: "1px solid rgba(48,54,61,0.3)", paddingTop: 8 }}>
                    <span style={{ fontSize: 11, color: "var(--text-dim)", fontWeight: 500 }}>Recent runs</span>
                    <div className="run-list" style={{ marginTop: 4 }}>
                      {cpcvRuns.slice(0, 5).map((r) => (
                        <div
                          key={r.cpcv_id}
                          className="run-row"
                          onClick={() => navigate(`/cpcv/${r.cpcv_id}`)}
                        >
                          <div className="run-row-left">
                            <span className="run-row-id">{r.cpcv_id}</span>
                            <span className="run-row-path">
                              {r.completed_combinations}/{r.total_combinations} paths
                            </span>
                          </div>
                          <span className={`pill pill-${r.status}`} style={{ fontSize: 10 }}>{r.status}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
