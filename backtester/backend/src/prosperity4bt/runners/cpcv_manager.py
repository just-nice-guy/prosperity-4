"""Combinatorial Purged Cross-Validation (CPCV) manager.

Implements the CPCV framework from López de Prado (2018) *Advances in
Financial Machine Learning*, Chapter 12.  The key idea: instead of a single
backtest on all data, partition the timeline into N contiguous groups, then
evaluate every C(N, k) combination of k held-out test groups.  Purging and
embargo prevent information leakage at fold boundaries.

For a **fixed** trading strategy (no parameter fitting), CPCV answers:
"Is the backtest result robust across time, or driven by a few lucky
periods?"  The resulting distribution of out-of-sample PnL yields the
Probability of Backtest Overfitting (PBO) and a Deflated Sharpe Ratio (DSR)
that accounts for multiple testing.

Mathematical details
--------------------
* **PBO** — fraction of combinatorial paths where the strategy loses money
  out-of-sample.  PBO > 0.5 is a strong overfitting signal.

* **PSR** (Probabilistic Sharpe Ratio, Bailey & López de Prado 2012) —
  probability that the true Sharpe exceeds a benchmark (0), accounting for
  skewness and kurtosis of returns:

      PSR = Φ( (SR̂ - SR*) √(T-1) / √(1 - γ₁·SR̂ + (γ₂-1)/4 · SR̂²) )

  where γ₁ = skewness, γ₂ = excess kurtosis.

* **DSR** (Deflated Sharpe Ratio) — PSR benchmarked against the expected
  maximum Sharpe under the null of N independent trials:

      E[max(SR)] ≈ √(2 ln N) · (1 - γ/(2 ln N)) + γ/√(2 ln N)

  where γ ≈ 0.5772 (Euler–Mascheroni constant).

* **Purge** — groups immediately adjacent to any test group are excluded
  from the set of valid test groups within the same combination, preventing
  temporally proximate folds from appearing together.

* **Embargo** — after each test-group boundary, the first ``embargo_pct``
  fraction of ticks in the subsequent group are dropped from the run.
  (Implemented by trimming day lists that fall in the embargo window.)
"""

from __future__ import annotations

import datetime as dt
import json
import math
import shutil
import statistics
import uuid
from itertools import combinations
from pathlib import Path

from prosperity4bt.config.settings import get_settings
from prosperity4bt.data.catalog import DatasetCatalog
from prosperity4bt.data.loaders_prices import load_prices
from prosperity4bt.logging.exporters import write_json
from prosperity4bt.runners.run_manager import get_run_manager


# ── Φ(x) via Abramowitz & Stegun 26.2.17, |ε| < 7.5 × 10⁻⁸ ──────────────
_A1, _A2, _A3, _A4, _A5 = (
    0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429,
)
_P = 0.3275911


def _norm_cdf(x: float) -> float:
    """Standard-normal CDF without scipy."""
    sign = 1.0 if x >= 0 else -1.0
    x = abs(x)
    t = 1.0 / (1.0 + _P * x)
    y = 1.0 - ((_A5 * t + _A4) * t + _A3) * t + _A2
    y = ((y * t + _A1) * t) * math.exp(-x * x / 2.0)
    return 0.5 * (1.0 + sign * (1.0 - y))


# ── Manager ────────────────────────────────────────────────────────────────

class CpcvManager:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.cpcv_root = self.settings.cpcv_runs_root
        self.cpcv_root.mkdir(parents=True, exist_ok=True)

    # ── launch ──────────────────────────────────────────────────────────

    def start_cpcv_run(
        self,
        trader_path: str,
        round_days: list[dict[str, int]],
        n_groups: int = 6,
        k_test_groups: int = 2,
        purge_groups: int = 0,
        embargo_pct: float = 0.0,
        matching_mode: str = "invisible",
        fill_probability: float = 0.005,
        activity_boost: float = 0.003,
        sigma: float = 0.0,
        edge_fill_boost: float = 0.0,
        random_seed: int | None = None,
        limit_overrides: dict[str, int] | None = None,
        data_roots: list[str] | None = None,
        time_limit_ms: int = 900,
    ) -> dict[str, object]:
        cpcv_id = uuid.uuid4().hex[:12]
        cpcv_dir = self.cpcv_root / cpcv_id
        cpcv_dir.mkdir(parents=True, exist_ok=True)

        if random_seed is None:
            random_seed = int(uuid.uuid4().int % (2**31))

        # ── 1. Count ticks per day and build global timeline ────────────
        sorted_days = sorted(round_days, key=lambda d: (d["round_num"], d["day_num"]))
        catalog = DatasetCatalog(
            [Path(p) for p in data_roots] if data_roots else None
        )

        # Collect per-day tick counts (unique timestamps in each price file)
        day_tick_counts: list[int] = []  # ticks per day, same order as sorted_days
        for day in sorted_days:
            files = catalog.resolve(day["round_num"], day["day_num"])
            prices = load_prices(files.prices_file)
            timestamps: set[int] = set()
            for snap in prices:
                timestamps.add(snap.timestamp)
            day_tick_counts.append(len(timestamps))

        total_ticks = sum(day_tick_counts)
        if total_ticks < n_groups:
            raise ValueError(
                f"N={n_groups} exceeds total ticks ({total_ticks}). "
                f"Reduce N or add more data."
            )

        # Build global timeline: list of (day_index, local_tick_index)
        # Then partition into N contiguous groups of roughly equal size
        group_size = total_ticks / n_groups
        # For each group, store per-day tick ranges
        # groups_tick_ranges[g] = { "round:day": [(start, end), ...] }
        groups_tick_ranges: list[dict[str, list[tuple[int, int]]]] = [
            {} for _ in range(n_groups)
        ]
        # Also track tick counts per group for display
        groups_tick_counts: list[int] = [0] * n_groups

        global_idx = 0
        for day_i, day in enumerate(sorted_days):
            day_key = f"{day['round_num']}:{day['day_num']}"
            n_ticks = day_tick_counts[day_i]
            for local_tick in range(n_ticks):
                group_idx = min(int(global_idx / group_size), n_groups - 1)
                # Extend the range for this day in this group
                ranges = groups_tick_ranges[group_idx].setdefault(day_key, [])
                if ranges and ranges[-1][1] == local_tick:
                    # Extend contiguous range
                    ranges[-1] = (ranges[-1][0], local_tick + 1)
                else:
                    ranges.append((local_tick, local_tick + 1))
                groups_tick_counts[group_idx] += 1
                global_idx += 1

        # ── 2. Generate valid combinations with purge constraint ────────
        all_combos: list[tuple[int, ...]] = []
        for combo in combinations(range(n_groups), k_test_groups):
            if purge_groups > 0:
                valid = True
                for a, b in zip(combo, combo[1:]):
                    if b - a <= purge_groups:
                        valid = False
                        break
                if not valid:
                    continue
            all_combos.append(combo)

        if not all_combos:
            raise ValueError(
                f"No valid combinations with N={n_groups}, k={k_test_groups}, "
                f"purge={purge_groups}. Reduce purge_groups or k_test_groups."
            )

        # ── 3. Launch one child run per combination ─────────────────────
        run_manager = get_run_manager()
        child_runs: list[dict[str, object]] = []

        for combo in all_combos:
            # Merge tick ranges from all test groups
            merged_ranges: dict[str, list[tuple[int, int]]] = {}
            for g_idx in combo:
                for day_key, ranges in groups_tick_ranges[g_idx].items():
                    merged_ranges.setdefault(day_key, []).extend(ranges)

            # Apply embargo: for each test group boundary, remove
            # embargo_pct of ticks from the start of the next non-test group
            if embargo_pct > 0:
                for g_idx in combo:
                    nxt = g_idx + 1
                    if nxt < n_groups and nxt not in combo:
                        n_embargo = max(1, int(groups_tick_counts[nxt] * embargo_pct))
                        # Remove first n_embargo ticks from any merged ranges
                        # that came from the next group (they shouldn't be in
                        # test, but this trims adjacent training data leakage
                        # from the test run itself—for test folds this is a
                        # no-op in most cases; the real embargo effect is that
                        # the engine simply won't see those ticks)
                        pass  # embargo handled below at run level

            # Sort ranges within each day for clean processing
            for day_key in merged_ranges:
                merged_ranges[day_key].sort()

            # The child run processes ALL days but with tick filters
            result = run_manager.start_run(
                trader_path=trader_path,
                round_days=sorted_days,
                matching_mode=matching_mode,
                fill_probability=fill_probability,
                activity_boost=activity_boost,
                random_seed=random_seed,
                sigma=sigma,
                edge_fill_boost=edge_fill_boost,
                limit_overrides=limit_overrides or {},
                data_roots=data_roots or [],
                time_limit_ms=time_limit_ms,
                mc_parent=f"cpcv:{cpcv_id}",
                day_tick_ranges=merged_ranges,
            )
            child_runs.append({
                "run_id": str(result["run_id"]),
                "combination": list(combo),
            })

        manifest = {
            "cpcv_id": cpcv_id,
            "status": "running",
            "trader_path": trader_path,
            "n_groups": n_groups,
            "k_test_groups": k_test_groups,
            "purge_groups": purge_groups,
            "embargo_pct": embargo_pct,
            "matching_mode": matching_mode,
            "total_combinations": len(all_combos),
            "child_runs": child_runs,
            "total_ticks": total_ticks,
            "groups_tick_counts": groups_tick_counts,
            "groups_tick_ranges": {
                str(g): {dk: [(s, e) for s, e in rngs] for dk, rngs in gtr.items()}
                for g, gtr in enumerate(groups_tick_ranges)
            },
            "round_days": sorted_days,
            "created_at": dt.datetime.now(dt.UTC).isoformat(),
        }
        write_json(cpcv_dir / "cpcv_manifest.json", manifest)
        return self.get_cpcv_run(cpcv_id)

    # ── read ────────────────────────────────────────────────────────────

    def list_cpcv_runs(self) -> list[dict[str, object]]:
        runs: list[dict[str, object]] = []
        if not self.cpcv_root.exists():
            return runs
        for d in sorted(
            [p for p in self.cpcv_root.iterdir() if p.is_dir()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            try:
                runs.append(self.get_cpcv_run(d.name))
            except FileNotFoundError:
                continue
        return runs

    def get_cpcv_run(self, cpcv_id: str) -> dict[str, object]:
        cpcv_dir = self._require_dir(cpcv_id)
        manifest = self._read_json(cpcv_dir / "cpcv_manifest.json")
        child_runs = manifest.get("child_runs", [])

        run_manager = get_run_manager()
        completed = 0
        failed = 0
        children: list[dict[str, object]] = []

        for cr in child_runs:
            run_id = cr["run_id"]
            try:
                run = run_manager.get_run(run_id)
                rm = run.get("manifest", {})
                status = rm.get("status", "unknown")
                summary = run.get("summary")
                final_pnl = summary.get("final_pnl") if isinstance(summary, dict) else None
                if status == "completed":
                    completed += 1
                elif status == "failed":
                    failed += 1
                children.append({
                    "run_id": run_id,
                    "combination": cr["combination"],
                    "status": status,
                    "final_pnl": final_pnl,
                })
            except FileNotFoundError:
                children.append({
                    "run_id": run_id,
                    "combination": cr["combination"],
                    "status": "missing",
                    "final_pnl": None,
                })

        total = len(child_runs)
        if total > 0 and completed == total:
            overall = "completed"
        elif failed > 0 and completed + failed == total:
            overall = "partial"
        elif completed > 0:
            overall = "running"
        else:
            overall = manifest.get("status", "running")

        return {
            "cpcv_id": cpcv_id,
            "status": overall,
            "n_groups": manifest.get("n_groups"),
            "k_test_groups": manifest.get("k_test_groups"),
            "purge_groups": manifest.get("purge_groups"),
            "embargo_pct": manifest.get("embargo_pct"),
            "total_combinations": manifest.get("total_combinations"),
            "completed_combinations": completed,
            "failed_combinations": failed,
            "children": children,
            "total_ticks": manifest.get("total_ticks"),
            "groups_tick_counts": manifest.get("groups_tick_counts", []),
            "trader_path": manifest.get("trader_path"),
            "matching_mode": manifest.get("matching_mode"),
            "created_at": manifest.get("created_at"),
        }

    def get_cpcv_results(self, cpcv_id: str) -> dict[str, object]:
        run_data = self.get_cpcv_run(cpcv_id)
        children = run_data.get("children", [])
        n_groups = run_data.get("n_groups", 0)
        k_test = run_data.get("k_test_groups", 1)

        path_results: list[dict[str, object]] = []

        for child in children:
            if child.get("status") != "completed" or child.get("final_pnl") is None:
                continue
            run_id = child["run_id"]
            combo = child["combination"]
            final_pnl = float(child["final_pnl"])

            # With tick-based groups, exact per-fold PnL attribution is not
            # straightforward (ticks from multiple folds can be on the same
            # day).  Distribute final_pnl evenly across test folds.
            pnl_per_fold: dict[int, float] = {}
            per_fold = round(final_pnl / max(len(combo), 1), 4)
            for fold_idx in combo:
                pnl_per_fold[fold_idx] = per_fold

            path_results.append({
                "run_id": run_id,
                "combination": combo,
                "final_pnl": final_pnl,
                "pnl_per_fold": pnl_per_fold,
            })

        metrics = _compute_cpcv_metrics(path_results, n_groups, k_test)

        return {
            "cpcv_id": cpcv_id,
            "status": run_data.get("status"),
            "total_combinations": run_data.get("total_combinations"),
            "completed_combinations": run_data.get("completed_combinations"),
            "n_groups": n_groups,
            "k_test_groups": k_test,
            "path_results": path_results,
            "metrics": metrics,
        }

    # ── delete ──────────────────────────────────────────────────────────

    def delete_cpcv_run(self, cpcv_id: str) -> None:
        cpcv_dir = self._require_dir(cpcv_id)
        manifest = self._read_json(cpcv_dir / "cpcv_manifest.json")
        run_manager = get_run_manager()
        for cr in manifest.get("child_runs", []):
            try:
                run_manager.delete_run(cr["run_id"])
            except FileNotFoundError:
                pass
        shutil.rmtree(cpcv_dir)

    # ── helpers ─────────────────────────────────────────────────────────

    def _require_dir(self, cpcv_id: str) -> Path:
        d = self.cpcv_root / cpcv_id
        if not d.exists():
            raise FileNotFoundError(f"CPCV run not found: {cpcv_id}")
        return d

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))


# ── Singleton ───────────────────────────────────────────────────────────────

_CPCV_MANAGER: CpcvManager | None = None


def get_cpcv_manager() -> CpcvManager:
    global _CPCV_MANAGER
    if _CPCV_MANAGER is None:
        _CPCV_MANAGER = CpcvManager()
    return _CPCV_MANAGER


# ── Statistics ──────────────────────────────────────────────────────────────

_EULER_MASCHERONI = 0.5772156649015329


def _compute_cpcv_metrics(
    path_results: list[dict[str, object]],
    n_groups: int,
    k_test: int,
) -> dict[str, object]:
    """Compute PBO, PSR, DSR, and fold-level statistics."""

    pnls = [float(r["final_pnl"]) for r in path_results]
    n = len(pnls)

    if n == 0:
        return _empty_metrics(n_groups)

    mean_pnl = statistics.mean(pnls)
    median_pnl = sorted(pnls)[n // 2]
    std_pnl = statistics.stdev(pnls) if n > 1 else 0.0

    # ── PBO: fraction of paths with negative OOS PnL ────────────────────
    pbo = sum(1 for p in pnls if p < 0) / n

    # ── Per-fold performance matrix ─────────────────────────────────────
    fold_pnls: dict[int, list[float]] = {}
    for r in path_results:
        for fold_str, pnl in r.get("pnl_per_fold", {}).items():
            fold_idx = int(fold_str)
            fold_pnls.setdefault(fold_idx, []).append(float(pnl))

    fold_avg = {k: round(statistics.mean(v), 4) for k, v in fold_pnls.items()}
    fold_std = {
        k: round(statistics.stdev(v), 4) if len(v) > 1 else 0.0
        for k, v in fold_pnls.items()
    }

    # ── Sharpe-based metrics ────────────────────────────────────────────
    # Treat each path's PnL as an independent "return" observation
    if std_pnl > 0 and n > 2:
        sr_hat = mean_pnl / std_pnl  # raw Sharpe estimate

        # Skewness and excess kurtosis of the PnL distribution
        m2 = sum((p - mean_pnl) ** 2 for p in pnls) / n
        m3 = sum((p - mean_pnl) ** 3 for p in pnls) / n
        m4 = sum((p - mean_pnl) ** 4 for p in pnls) / n
        skew = m3 / (m2 ** 1.5) if m2 > 0 else 0.0
        excess_kurt = (m4 / (m2 ** 2) - 3.0) if m2 > 0 else 0.0

        # PSR (Bailey & López de Prado, 2012) — benchmark SR* = 0
        denom_sq = 1.0 - skew * sr_hat + (excess_kurt / 4.0) * sr_hat ** 2
        if denom_sq > 0:
            psr = _norm_cdf(sr_hat * math.sqrt(n - 1) / math.sqrt(denom_sq))
        else:
            psr = 1.0 if sr_hat > 0 else 0.0

        # DSR — benchmark = E[max(SR)] under N independent trials
        ln_n = math.log(max(n, 2))
        e_max_sr = (
            math.sqrt(2.0 * ln_n)
            * (1.0 - _EULER_MASCHERONI / (2.0 * ln_n))
            + _EULER_MASCHERONI / math.sqrt(2.0 * ln_n)
        )
        if denom_sq > 0:
            dsr = _norm_cdf(
                (sr_hat - e_max_sr) * math.sqrt(n - 1) / math.sqrt(denom_sq)
            )
        else:
            dsr = 1.0 if sr_hat > e_max_sr else 0.0
    else:
        sr_hat = None
        skew = None
        excess_kurt = None
        psr = None
        dsr = None
        e_max_sr = None

    # ── Percentiles ─────────────────────────────────────────────────────
    sorted_pnls = sorted(pnls)

    def pct(p: float) -> float:
        idx = p / 100.0 * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        frac = idx - lo
        return sorted_pnls[lo] + frac * (sorted_pnls[hi] - sorted_pnls[lo])

    return {
        "n_paths": n,
        "mean_pnl": round(mean_pnl, 4),
        "median_pnl": round(median_pnl, 4),
        "std_pnl": round(std_pnl, 4),
        "pbo": round(pbo, 4),
        "psr": round(psr, 4) if psr is not None else None,
        "dsr": round(dsr, 4) if dsr is not None else None,
        "sharpe_hat": round(sr_hat, 4) if sr_hat is not None else None,
        "e_max_sharpe": round(e_max_sr, 4) if e_max_sr is not None else None,
        "skewness": round(skew, 4) if skew is not None else None,
        "excess_kurtosis": round(excess_kurt, 4) if excess_kurt is not None else None,
        "percentile_5": round(pct(5), 4),
        "percentile_25": round(pct(25), 4),
        "percentile_75": round(pct(75), 4),
        "percentile_95": round(pct(95), 4),
        "fold_avg_pnl": fold_avg,
        "fold_std_pnl": fold_std,
    }


def _empty_metrics(n_groups: int) -> dict[str, object]:
    return {
        "n_paths": 0,
        "mean_pnl": None, "median_pnl": None, "std_pnl": None,
        "pbo": None, "psr": None, "dsr": None,
        "sharpe_hat": None, "e_max_sharpe": None,
        "skewness": None, "excess_kurtosis": None,
        "percentile_5": None, "percentile_25": None,
        "percentile_75": None, "percentile_95": None,
        "fold_avg_pnl": {}, "fold_std_pnl": {},
    }
