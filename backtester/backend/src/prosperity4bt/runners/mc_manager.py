from __future__ import annotations

import datetime as dt
import json
import shutil
import statistics
import uuid
from pathlib import Path

from prosperity4bt.config.settings import get_settings
from prosperity4bt.logging.exporters import write_json
from prosperity4bt.runners.run_manager import get_run_manager


class MonteCarloManager:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.mc_root = self.settings.mc_runs_root
        self.mc_root.mkdir(parents=True, exist_ok=True)

    def start_mc_run(
        self,
        trader_path: str,
        round_days: list[dict[str, int]],
        num_paths: int = 50,
        base_seed: int | None = None,
        fill_probability: float = 0.005,
        activity_boost: float = 0.003,
        sigma: float = 0.0,
        edge_fill_boost: float = 0.0,
        limit_overrides: dict[str, int] | None = None,
        data_roots: list[str] | None = None,
        time_limit_ms: int = 900,
        fill_skip_prob: float = 0.0,
        adverse_selection: float = 0.0,
        min_fill_fraction: float = 0.5,
        max_fill_fraction: float = 1.0,
    ) -> dict[str, object]:
        mc_id = uuid.uuid4().hex[:12]
        mc_dir = self.mc_root / mc_id
        mc_dir.mkdir(parents=True, exist_ok=True)

        if base_seed is None:
            base_seed = int(uuid.uuid4().int % (2**31))

        run_manager = get_run_manager()
        child_run_ids: list[str] = []

        for i in range(num_paths):
            seed = base_seed + i
            result = run_manager.start_run(
                trader_path=trader_path,
                round_days=round_days,
                matching_mode="invisible",
                fill_probability=fill_probability,
                activity_boost=activity_boost,
                random_seed=seed,
                sigma=sigma,
                edge_fill_boost=edge_fill_boost,
                limit_overrides=limit_overrides or {},
                data_roots=data_roots or [],
                time_limit_ms=time_limit_ms,
                mc_parent=mc_id,
                fill_skip_prob=fill_skip_prob,
                adverse_selection=adverse_selection,
                min_fill_fraction=min_fill_fraction,
                max_fill_fraction=max_fill_fraction,
            )
            child_run_ids.append(str(result["run_id"]))

        manifest = {
            "mc_id": mc_id,
            "status": "running",
            "num_paths": num_paths,
            "base_seed": base_seed,
            "child_run_ids": child_run_ids,
            "trader_path": trader_path,
            "matching_mode": "invisible",
            "created_at": dt.datetime.now(dt.UTC).isoformat(),
            "round_days": round_days,
            "fill_probability": fill_probability,
            "activity_boost": activity_boost,
            "sigma": sigma,
            "fill_skip_prob": fill_skip_prob,
            "adverse_selection": adverse_selection,
            "min_fill_fraction": min_fill_fraction,
            "max_fill_fraction": max_fill_fraction,
        }
        write_json(mc_dir / "mc_manifest.json", manifest)
        return self.get_mc_run(mc_id)

    def list_mc_runs(self) -> list[dict[str, object]]:
        runs: list[dict[str, object]] = []
        if not self.mc_root.exists():
            return runs
        for mc_dir in sorted(
            [p for p in self.mc_root.iterdir() if p.is_dir()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            try:
                runs.append(self.get_mc_run(mc_dir.name))
            except FileNotFoundError:
                continue
        return runs

    def get_mc_run(self, mc_id: str) -> dict[str, object]:
        mc_dir = self._require_mc_dir(mc_id)
        manifest = self._read_json(mc_dir / "mc_manifest.json")
        child_run_ids = manifest.get("child_run_ids", [])

        run_manager = get_run_manager()
        completed = 0
        failed = 0
        child_summaries: list[dict[str, object]] = []

        for run_id in child_run_ids:
            try:
                run = run_manager.get_run(run_id)
                run_manifest = run.get("manifest", {})
                status = run_manifest.get("status", "unknown")
                summary = run.get("summary")
                final_pnl = summary.get("final_pnl") if isinstance(summary, dict) else None
                if status == "completed":
                    completed += 1
                elif status == "failed":
                    failed += 1
                child_summaries.append({
                    "run_id": run_id,
                    "status": status,
                    "final_pnl": final_pnl,
                })
            except FileNotFoundError:
                child_summaries.append({"run_id": run_id, "status": "missing", "final_pnl": None})

        total = len(child_run_ids)
        if completed == total:
            overall_status = "completed"
        elif failed > 0 and completed + failed == total:
            overall_status = "partial"
        else:
            overall_status = "running"

        return {
            "mc_id": mc_id,
            "status": overall_status,
            "num_paths": manifest.get("num_paths", total),
            "completed_paths": completed,
            "failed_paths": failed,
            "base_seed": manifest.get("base_seed"),
            "child_run_ids": child_run_ids,
            "children": child_summaries,
            "trader_path": manifest.get("trader_path"),
            "matching_mode": "invisible",
            "created_at": manifest.get("created_at"),
            "round_days": manifest.get("round_days", []),
        }

    def get_mc_results(self, mc_id: str) -> dict[str, object]:
        mc_run = self.get_mc_run(mc_id)
        child_run_ids = mc_run.get("child_run_ids", [])
        run_manager = get_run_manager()

        pnl_paths: dict[str, list[list[float]]] = {}
        final_pnls: list[float] = []

        for run_id in child_run_ids:
            try:
                run = run_manager.get_run(run_id)
                summary = run.get("summary")
                if not isinstance(summary, dict) or summary.get("status") != "completed":
                    continue

                final_pnl = summary.get("final_pnl")
                if final_pnl is not None:
                    final_pnls.append(float(final_pnl))

                timeline = run_manager.read_timeline(run_id)
                # Aggregate PnL per timestamp (sum across products)
                ts_pnl: dict[int, float] = {}
                for row in timeline:
                    ts = int(row.get("timestamp", 0))
                    pnl = float(row.get("pnl", 0))
                    ts_pnl[ts] = ts_pnl.get(ts, 0) + pnl

                path = sorted([[ts, round(pnl, 4)] for ts, pnl in ts_pnl.items()])
                pnl_paths[run_id] = path
            except (FileNotFoundError, ValueError):
                continue

        risk_metrics = _compute_risk_metrics(final_pnls, pnl_paths)

        return {
            "mc_id": mc_id,
            "status": mc_run.get("status"),
            "num_paths": mc_run.get("num_paths"),
            "completed_paths": mc_run.get("completed_paths"),
            "pnl_paths": pnl_paths,
            "final_pnl_distribution": final_pnls,
            "risk_metrics": risk_metrics,
        }

    def delete_mc_run(self, mc_id: str) -> None:
        mc_dir = self._require_mc_dir(mc_id)
        manifest = self._read_json(mc_dir / "mc_manifest.json")
        run_manager = get_run_manager()
        for run_id in manifest.get("child_run_ids", []):
            try:
                run_manager.delete_run(run_id)
            except FileNotFoundError:
                pass
        shutil.rmtree(mc_dir)

    def _require_mc_dir(self, mc_id: str) -> Path:
        mc_dir = self.mc_root / mc_id
        if not mc_dir.exists():
            raise FileNotFoundError(f"MC run not found: {mc_id}")
        return mc_dir

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))


_MC_MANAGER: MonteCarloManager | None = None


def get_mc_manager() -> MonteCarloManager:
    global _MC_MANAGER
    if _MC_MANAGER is None:
        _MC_MANAGER = MonteCarloManager()
    return _MC_MANAGER


def _compute_risk_metrics(
    final_pnls: list[float],
    pnl_paths: dict[str, list[list[float]]],
) -> dict[str, float | None]:
    if not final_pnls:
        return {
            "mean_pnl": None, "median_pnl": None, "std_dev": None,
            "percentile_5": None, "percentile_25": None,
            "percentile_75": None, "percentile_95": None,
            "probability_of_loss": None,
            "max_drawdown_mean": None, "max_drawdown_worst": None,
            "sharpe_estimate": None, "var_95": None, "cvar_95": None,
        }

    sorted_pnls = sorted(final_pnls)
    n = len(sorted_pnls)
    mean = statistics.mean(final_pnls)
    std = statistics.stdev(final_pnls) if n > 1 else 0.0

    def percentile(pct: float) -> float:
        idx = pct / 100 * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        frac = idx - lo
        return sorted_pnls[lo] + frac * (sorted_pnls[hi] - sorted_pnls[lo])

    # VaR 95% = 5th percentile loss (how much you lose in worst 5% of cases)
    var_95 = percentile(5)
    # CVaR 95% = expected loss in worst 5% of cases
    cutoff_idx = max(1, int(0.05 * n))
    cvar_95 = statistics.mean(sorted_pnls[:cutoff_idx])

    # Max drawdown per path
    drawdowns: list[float] = []
    for path in pnl_paths.values():
        if not path:
            continue
        peak = path[0][1]
        max_dd = 0.0
        for _, pnl in path:
            if pnl > peak:
                peak = pnl
            dd = peak - pnl
            if dd > max_dd:
                max_dd = dd
        drawdowns.append(max_dd)

    prob_loss = sum(1 for p in final_pnls if p < 0) / n
    sharpe = mean / std if std > 0 else None

    return {
        "mean_pnl": round(mean, 2),
        "median_pnl": round(percentile(50), 2),
        "std_dev": round(std, 2),
        "percentile_5": round(percentile(5), 2),
        "percentile_25": round(percentile(25), 2),
        "percentile_75": round(percentile(75), 2),
        "percentile_95": round(percentile(95), 2),
        "probability_of_loss": round(prob_loss, 4),
        "max_drawdown_mean": round(statistics.mean(drawdowns), 2) if drawdowns else None,
        "max_drawdown_worst": round(max(drawdowns), 2) if drawdowns else None,
        "sharpe_estimate": round(sharpe, 4) if sharpe is not None else None,
        "var_95": round(var_95, 2),
        "cvar_95": round(cvar_95, 2),
    }
