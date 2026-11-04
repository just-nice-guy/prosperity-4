"""CPCV-based parameter optimization manager.

For each candidate parameter combination:
  1. Create a modified trader file with overridden constants.
  2. Run a mini-CPCV on the in-sample (IS) portion of the data.
  3. Run a single backtest on the out-of-sample (OOS) portion.

The IS CPCV yields per-combination metrics (mean PnL, Sharpe, PBO).
Combinations are ranked by the chosen objective.  The OOS backtest
provides an independent check: a large IS/OOS gap signals overfitting.

Overfitting protection
----------------------
* IS/OOS split -- the strategy never sees OOS during optimisation.
* CPCV on IS  -- each parameter set is tested on multiple fold combinations,
  not a single cherry-picked window.
* Deflated Sharpe -- the best IS Sharpe is penalised for the number of
  combinations tried (multiple-testing correction).
* Minimum-trades filter -- discards combinations that generated fewer than
  ``min_trades`` fills (likely degenerate parameter sets).
* Concurrency throttle -- respects max_concurrent_runs to avoid crashing.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import math
import random as rand_mod
import shutil
import statistics
import threading
import time
import uuid
from itertools import combinations
from pathlib import Path

from prosperity4bt.config.settings import get_settings, get_runtime_settings
from prosperity4bt.data.catalog import DatasetCatalog
from prosperity4bt.data.loaders_prices import load_prices
from prosperity4bt.logging.exporters import write_json
from prosperity4bt.runners.param_discovery import create_modified_trader, discover_parameters
from prosperity4bt.runners.run_manager import get_run_manager


# -- norm CDF (Abramowitz & Stegun) ----------------------------------------
_A1, _A2, _A3, _A4, _A5 = (
    0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429,
)
_P = 0.3275911


def _norm_cdf(x: float) -> float:
    sign = 1.0 if x >= 0 else -1.0
    x = abs(x)
    t = 1.0 / (1.0 + _P * x)
    y = 1.0 - ((_A5 * t + _A4) * t + _A3) * t + _A2
    y = ((y * t + _A1) * t) * math.exp(-x * x / 2.0)
    return 0.5 * (1.0 + sign * (1.0 - y))


_EULER_MASCHERONI = 0.5772156649015329


# -- Tick-range utilities ---------------------------------------------------

def _count_ticks_per_day(
    sorted_days: list[dict[str, int]],
    catalog: DatasetCatalog,
) -> list[int]:
    counts: list[int] = []
    for day in sorted_days:
        files = catalog.resolve(day["round_num"], day["day_num"])
        prices = load_prices(files.prices_file)
        counts.append(len({snap.timestamp for snap in prices}))
    return counts


def _global_to_day_ranges(
    sorted_days: list[dict[str, int]],
    day_tick_counts: list[int],
    global_start: int,
    global_end: int,
) -> dict[str, list[tuple[int, int]]]:
    """Map a global tick range [start, end) to per-day index ranges."""
    result: dict[str, list[tuple[int, int]]] = {}
    cumulative = 0
    for day, count in zip(sorted_days, day_tick_counts):
        day_key = f"{day['round_num']}:{day['day_num']}"
        overlap_start = max(global_start, cumulative) - cumulative
        overlap_end = min(global_end, cumulative + count) - cumulative
        if overlap_start < overlap_end:
            result[day_key] = [(overlap_start, overlap_end)]
        cumulative += count
    return result


def _split_is_into_groups(
    sorted_days: list[dict[str, int]],
    day_tick_counts: list[int],
    is_end: int,
    n_groups: int,
) -> list[dict[str, list[tuple[int, int]]]]:
    """Split IS ticks [0, is_end) into N contiguous groups (per-day ranges)."""
    group_size = is_end / n_groups
    groups: list[dict[str, list[tuple[int, int]]]] = [{} for _ in range(n_groups)]

    cumulative = 0
    for day, count in zip(sorted_days, day_tick_counts):
        day_key = f"{day['round_num']}:{day['day_num']}"
        for local_tick in range(count):
            global_tick = cumulative + local_tick
            if global_tick >= is_end:
                break
            group_idx = min(int(global_tick / group_size), n_groups - 1)
            ranges = groups[group_idx].setdefault(day_key, [])
            if ranges and ranges[-1][1] == local_tick:
                ranges[-1] = (ranges[-1][0], local_tick + 1)
            else:
                ranges.append((local_tick, local_tick + 1))
        cumulative += count
    return groups


# -- Combination generation -------------------------------------------------

def _generate_param_combinations(
    parameters: list[dict[str, object]],
    method: str,
    budget: int,
    seed: int | None,
) -> list[dict[str, int | float]]:
    grids: list[tuple[str, list[float], str]] = []
    for p in parameters:
        min_v = float(p["min_value"])
        max_v = float(p["max_value"])
        step = float(p["step"])
        values: list[float] = []
        v = min_v
        while v <= max_v + step * 0.01:
            values.append(round(v, 10))
            v += step
        grids.append((str(p["name"]), values, str(p.get("type", "float"))))

    if method == "grid":
        all_combos: list[dict[str, int | float]] = []
        for combo in itertools.product(*(g[1] for g in grids)):
            overrides: dict[str, int | float] = {}
            for i, (name, _, ptype) in enumerate(grids):
                overrides[name] = int(combo[i]) if ptype == "int" else float(combo[i])
            all_combos.append(overrides)
        if len(all_combos) > budget:
            rng = rand_mod.Random(seed)
            all_combos = rng.sample(all_combos, budget)
        return all_combos

    # Random search
    rng = rand_mod.Random(seed)
    combos: list[dict[str, int | float]] = []
    for _ in range(budget):
        overrides = {}
        for name, values, ptype in grids:
            val = rng.choice(values)
            overrides[name] = int(val) if ptype == "int" else float(val)
        combos.append(overrides)
    return combos


# -- Manager ----------------------------------------------------------------

class OptimizationManager:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.opt_root = self.settings.optimization_runs_root
        self.opt_root.mkdir(parents=True, exist_ok=True)

    # -- launch -------------------------------------------------------------

    def start_optimization(
        self,
        trader_path: str,
        round_days: list[dict[str, int]],
        parameters: list[dict[str, object]],
        search_method: str = "grid",
        search_budget: int = 50,
        objective: str = "mean_pnl",
        is_fraction: float = 0.7,
        cpcv_n: int = 5,
        cpcv_k: int = 1,
        purge_groups: int = 1,
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
        min_trades: int = 5,
    ) -> dict[str, object]:
        # Enforce budget cap from runtime settings
        runtime = get_runtime_settings()
        max_combos = int(runtime.get("max_optimization_combos", 200))
        max_total = int(runtime.get("max_total_runs", 2000))
        if search_budget > max_combos:
            search_budget = max_combos

        opt_id = uuid.uuid4().hex[:12]
        opt_dir = self.opt_root / opt_id
        traders_dir = opt_dir / "traders"
        traders_dir.mkdir(parents=True, exist_ok=True)

        if random_seed is None:
            random_seed = int(uuid.uuid4().int % (2**31))

        sorted_days = sorted(round_days, key=lambda d: (d["round_num"], d["day_num"]))
        catalog = DatasetCatalog(
            [Path(p) for p in data_roots] if data_roots else None
        )
        day_tick_counts = _count_ticks_per_day(sorted_days, catalog)
        total_ticks = sum(day_tick_counts)

        # -- IS / OOS split -------------------------------------------------
        is_tick_count = int(total_ticks * is_fraction)
        oos_day_ranges = _global_to_day_ranges(
            sorted_days, day_tick_counts, is_tick_count, total_ticks,
        )

        if cpcv_n > is_tick_count:
            cpcv_n = max(2, is_tick_count // 100)

        # -- CPCV groups within IS ------------------------------------------
        is_groups = _split_is_into_groups(
            sorted_days, day_tick_counts, is_tick_count, cpcv_n,
        )

        # Valid CPCV fold combinations (with purge)
        cpcv_combos: list[tuple[int, ...]] = []
        for combo in combinations(range(cpcv_n), cpcv_k):
            if purge_groups > 0:
                valid = True
                for a, b in zip(combo, combo[1:]):
                    if b - a <= purge_groups:
                        valid = False
                        break
                if not valid:
                    continue
            cpcv_combos.append(combo)

        if not cpcv_combos:
            raise ValueError(
                f"No valid CPCV fold combinations with N={cpcv_n}, k={cpcv_k}, "
                f"purge={purge_groups}."
            )

        # -- Parameter combinations -----------------------------------------
        param_combos = _generate_param_combinations(
            parameters, search_method, search_budget, random_seed,
        )

        # Enforce total run cap
        n_cpcv_paths = len(cpcv_combos)
        runs_per_combo = n_cpcv_paths + 1
        if len(param_combos) * runs_per_combo > max_total:
            param_combos = param_combos[: max(1, max_total // runs_per_combo)]

        # -- Build manifest (runs launched async by background thread) ------
        manifest_combos: list[dict[str, object]] = []
        for combo_idx, overrides in enumerate(param_combos):
            manifest_combos.append({
                "combo_idx": combo_idx,
                "overrides": overrides,
                "is_run_ids": [],
                "oos_run_id": None,
            })

        manifest = {
            "opt_id": opt_id,
            "status": "running",
            "trader_path": trader_path,
            "parameters": parameters,
            "search_method": search_method,
            "search_budget": search_budget,
            "objective": objective,
            "is_fraction": is_fraction,
            "cpcv_n": cpcv_n,
            "cpcv_k": cpcv_k,
            "purge_groups": purge_groups,
            "embargo_pct": embargo_pct,
            "matching_mode": matching_mode,
            "total_ticks": total_ticks,
            "is_ticks": is_tick_count,
            "oos_ticks": total_ticks - is_tick_count,
            "total_combinations": len(param_combos),
            "cpcv_paths_per_combo": n_cpcv_paths,
            "total_runs": len(param_combos) * runs_per_combo,
            "min_trades": min_trades,
            "combinations": manifest_combos,
            "created_at": dt.datetime.now(dt.UTC).isoformat(),
        }
        write_json(opt_dir / "opt_manifest.json", manifest)

        # -- Launch runs in background thread with throttling ---------------
        run_args = dict(
            sorted_days=sorted_days,
            matching_mode=matching_mode,
            fill_probability=fill_probability,
            activity_boost=activity_boost,
            random_seed=random_seed,
            sigma=sigma,
            edge_fill_boost=edge_fill_boost,
            limit_overrides=limit_overrides or {},
            data_roots=data_roots or [],
            time_limit_ms=time_limit_ms,
        )

        thread = threading.Thread(
            target=self._run_optimization_thread,
            args=(
                opt_id, opt_dir, traders_dir, trader_path,
                param_combos, cpcv_combos, is_groups,
                oos_day_ranges, run_args,
            ),
            daemon=True,
        )
        thread.start()
        return self.get_optimization(opt_id)

    def _run_optimization_thread(
        self,
        opt_id: str,
        opt_dir: Path,
        traders_dir: Path,
        trader_path: str,
        param_combos: list[dict[str, int | float]],
        cpcv_combos: list[tuple[int, ...]],
        is_groups: list[dict[str, list[tuple[int, int]]]],
        oos_day_ranges: dict[str, list[tuple[int, int]]],
        run_args: dict[str, object],
    ) -> None:
        """Background thread: launches runs respecting max_concurrent_runs and RAM."""
        import psutil

        runtime = get_runtime_settings()
        max_concurrent = int(runtime.get("max_concurrent_runs", 4))
        cleanup = bool(runtime.get("cleanup_temp_traders", True))
        ram_limit_mb = int(runtime.get("ram_limit_mb", 0))
        cpu_limit = int(runtime.get("cpu_limit", 0))

        # If cpu_limit is set, cap concurrent to the lesser value
        if cpu_limit > 0:
            max_concurrent = min(max_concurrent, cpu_limit)

        semaphore = threading.Semaphore(max_concurrent)
        run_manager = get_run_manager()
        manifest_path = opt_dir / "opt_manifest.json"

        def _wait_for_run(run_id: str) -> None:
            """Block until a run completes (poll every 1s)."""
            while True:
                try:
                    r = run_manager.get_run(run_id)
                    if r.get("manifest", {}).get("status") == "completed":
                        return
                except FileNotFoundError:
                    return
                time.sleep(1.0)

        def _wait_for_ram() -> None:
            """If ram_limit_mb is set, block until worker RAM is below the limit."""
            if ram_limit_mb <= 0:
                return
            while True:
                worker_rss = 0
                try:
                    for proc in psutil.process_iter(["cmdline", "memory_info"]):
                        cmdline = proc.info.get("cmdline") or []
                        if any("prosperity4bt.runners.worker" in c for c in cmdline):
                            mem = proc.info.get("memory_info")
                            if mem:
                                worker_rss += mem.rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                if worker_rss / (1024 * 1024) < ram_limit_mb:
                    return
                time.sleep(2.0)

        def _launch_and_wait(
            trader_file: str,
            day_ranges: dict[str, list[tuple[int, int]]],
        ) -> str:
            """Acquire semaphore slot, check RAM, launch run, wait, release."""
            semaphore.acquire()
            _wait_for_ram()
            try:
                result = run_manager.start_run(
                    trader_path=trader_file,
                    round_days=run_args["sorted_days"],
                    matching_mode=run_args["matching_mode"],
                    fill_probability=run_args["fill_probability"],
                    activity_boost=run_args["activity_boost"],
                    random_seed=run_args["random_seed"],
                    sigma=run_args["sigma"],
                    edge_fill_boost=run_args["edge_fill_boost"],
                    limit_overrides=run_args["limit_overrides"],
                    data_roots=run_args["data_roots"],
                    time_limit_ms=run_args["time_limit_ms"],
                    mc_parent=f"opt:{opt_id}",
                    day_tick_ranges=day_ranges,
                )
                rid = str(result["run_id"])
                _wait_for_run(rid)
                return rid
            finally:
                semaphore.release()

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        for combo_idx, overrides in enumerate(param_combos):
            modified_path = traders_dir / f"combo_{combo_idx}.py"
            create_modified_trader(trader_path, overrides, str(modified_path))

            # Launch IS CPCV paths with threads (throttled by semaphore)
            threads: list[threading.Thread] = []
            is_run_ids: list[str | None] = [None] * len(cpcv_combos)

            for path_idx, fold_combo in enumerate(cpcv_combos):
                merged: dict[str, list[tuple[int, int]]] = {}
                for fold_idx in fold_combo:
                    for day_key, ranges in is_groups[fold_idx].items():
                        merged.setdefault(day_key, []).extend(ranges)
                for dk in merged:
                    merged[dk].sort()

                def _run_is(idx: int = path_idx, dr: dict = merged) -> None:
                    is_run_ids[idx] = _launch_and_wait(str(modified_path), dr)

                t = threading.Thread(target=_run_is, daemon=True)
                t.start()
                threads.append(t)

            for t in threads:
                t.join()

            # OOS single backtest (also throttled)
            oos_run_id = _launch_and_wait(str(modified_path), oos_day_ranges)

            # Update manifest incrementally
            manifest["combinations"][combo_idx]["is_run_ids"] = [
                r for r in is_run_ids if r is not None
            ]
            manifest["combinations"][combo_idx]["oos_run_id"] = oos_run_id
            write_json(manifest_path, manifest)

            # Clean up temp trader for this combo
            if cleanup and modified_path.exists():
                modified_path.unlink()

        # Mark as completed
        manifest["status"] = "completed"
        write_json(manifest_path, manifest)

        # Clean up traders directory if empty
        if cleanup and traders_dir.exists():
            remaining = list(traders_dir.iterdir())
            if not remaining:
                traders_dir.rmdir()

    # -- read ---------------------------------------------------------------

    def list_optimizations(self) -> list[dict[str, object]]:
        runs: list[dict[str, object]] = []
        if not self.opt_root.exists():
            return runs
        for d in sorted(
            [p for p in self.opt_root.iterdir() if p.is_dir()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            try:
                runs.append(self.get_optimization(d.name))
            except FileNotFoundError:
                continue
        return runs

    def get_optimization(self, opt_id: str) -> dict[str, object]:
        opt_dir = self._require_dir(opt_id)
        manifest = self._read_json(opt_dir / "opt_manifest.json")
        combos = manifest.get("combinations", [])
        run_manager = get_run_manager()

        completed_runs = 0
        total_runs = int(manifest.get("total_runs", 0))
        for combo in combos:
            for rid in combo.get("is_run_ids", []):
                try:
                    r = run_manager.get_run(rid)
                    if r.get("manifest", {}).get("status") == "completed":
                        completed_runs += 1
                except FileNotFoundError:
                    pass
            oos_rid = combo.get("oos_run_id")
            if oos_rid:
                try:
                    r = run_manager.get_run(oos_rid)
                    if r.get("manifest", {}).get("status") == "completed":
                        completed_runs += 1
                except FileNotFoundError:
                    pass

        status = manifest.get("status", "running")
        if status != "completed":
            status = "completed" if completed_runs >= total_runs and total_runs > 0 else "running"

        return {
            "opt_id": opt_id,
            "status": status,
            "trader_path": manifest.get("trader_path"),
            "parameters": manifest.get("parameters"),
            "search_method": manifest.get("search_method"),
            "objective": manifest.get("objective"),
            "is_fraction": manifest.get("is_fraction"),
            "cpcv_n": manifest.get("cpcv_n"),
            "cpcv_k": manifest.get("cpcv_k"),
            "total_combinations": manifest.get("total_combinations"),
            "cpcv_paths_per_combo": manifest.get("cpcv_paths_per_combo"),
            "total_runs": total_runs,
            "completed_runs": completed_runs,
            "total_ticks": manifest.get("total_ticks"),
            "is_ticks": manifest.get("is_ticks"),
            "oos_ticks": manifest.get("oos_ticks"),
            "matching_mode": manifest.get("matching_mode"),
            "created_at": manifest.get("created_at"),
        }

    def get_optimization_results(self, opt_id: str) -> dict[str, object]:
        opt_dir = self._require_dir(opt_id)
        manifest = self._read_json(opt_dir / "opt_manifest.json")
        run_manager = get_run_manager()
        objective = str(manifest.get("objective", "mean_pnl"))
        min_trades = int(manifest.get("min_trades", 0))

        combo_results: list[dict[str, object]] = []
        for combo in manifest.get("combinations", []):
            overrides = combo["overrides"]
            # Collect IS path PnLs
            is_pnls: list[float] = []
            is_fills: int = 0
            all_completed = True
            for rid in combo.get("is_run_ids", []):
                try:
                    r = run_manager.get_run(rid)
                    if r.get("manifest", {}).get("status") != "completed":
                        all_completed = False
                        continue
                    s = r.get("summary")
                    if isinstance(s, dict):
                        is_pnls.append(float(s.get("final_pnl", 0)))
                        is_fills += int(s.get("total_fills", 0))
                except FileNotFoundError:
                    all_completed = False

            # OOS PnL
            oos_pnl: float | None = None
            oos_rid = combo.get("oos_run_id")
            if oos_rid:
                try:
                    r = run_manager.get_run(oos_rid)
                    if r.get("manifest", {}).get("status") == "completed":
                        s = r.get("summary")
                        if isinstance(s, dict):
                            oos_pnl = float(s.get("final_pnl", 0))
                    else:
                        all_completed = False
                except FileNotFoundError:
                    all_completed = False

            # Compute IS CPCV metrics
            entry: dict[str, object] = {
                "combo_idx": combo["combo_idx"],
                "overrides": overrides,
                "is_n_paths": len(is_pnls),
                "is_total_fills": is_fills,
                "completed": all_completed,
            }

            if is_pnls:
                mean_pnl = statistics.mean(is_pnls)
                median_pnl = statistics.median(is_pnls)
                std_pnl = statistics.stdev(is_pnls) if len(is_pnls) > 1 else 0.0
                min_pnl = min(is_pnls)
                max_pnl = max(is_pnls)
                sharpe = mean_pnl / std_pnl if std_pnl > 0 else (
                    float("inf") if mean_pnl > 0 else 0.0
                )
                pbo = sum(1 for p in is_pnls if p < 0) / len(is_pnls)
                win_rate = sum(1 for p in is_pnls if p >= 0) / len(is_pnls)
                entry["is_mean_pnl"] = round(mean_pnl, 2)
                entry["is_median_pnl"] = round(median_pnl, 2)
                entry["is_std_pnl"] = round(std_pnl, 2)
                entry["is_min_pnl"] = round(min_pnl, 2)
                entry["is_max_pnl"] = round(max_pnl, 2)
                entry["is_sharpe"] = round(sharpe, 4) if sharpe != float("inf") else 999.0
                entry["is_pbo"] = round(pbo, 4)
                entry["is_win_rate"] = round(win_rate, 4)
                entry["is_pnls"] = [round(p, 2) for p in is_pnls]
            else:
                entry.update(is_mean_pnl=None, is_median_pnl=None, is_std_pnl=None,
                             is_min_pnl=None, is_max_pnl=None, is_sharpe=None,
                             is_pbo=None, is_win_rate=None, is_pnls=[])

            entry["oos_pnl"] = round(oos_pnl, 2) if oos_pnl is not None else None

            # IS/OOS ratio (closer to 1.0 = less overfitting)
            if entry["is_mean_pnl"] is not None and oos_pnl is not None:
                is_m = float(entry["is_mean_pnl"])
                if abs(is_m) > 0.01:
                    entry["is_oos_ratio"] = round(oos_pnl / is_m, 4)
                else:
                    entry["is_oos_ratio"] = None
            else:
                entry["is_oos_ratio"] = None

            combo_results.append(entry)

        # -- Rank by objective ----------------------------------------------
        def sort_key(cr: dict[str, object]) -> float:
            if cr.get("is_total_fills", 0) < min_trades:
                return float("-inf")
            if objective == "sharpe":
                v = cr.get("is_sharpe")
                return float(v) if v is not None else float("-inf")
            if objective == "pbo":
                v = cr.get("is_pbo")
                return -float(v) if v is not None else float("-inf")
            # default: mean_pnl
            v = cr.get("is_mean_pnl")
            return float(v) if v is not None else float("-inf")

        combo_results.sort(key=sort_key, reverse=True)
        for rank, cr in enumerate(combo_results):
            cr["rank"] = rank + 1

        best_idx: int | None = combo_results[0]["combo_idx"] if combo_results else None

        # -- Deflated Sharpe (penalise for N trials) ------------------------
        sharpes = [
            float(cr["is_sharpe"])
            for cr in combo_results
            if cr.get("is_sharpe") is not None and cr["is_sharpe"] != 999.0
        ]
        deflated_sharpe: float | None = None
        e_max_sr: float | None = None
        n_trials = len(sharpes)
        if sharpes and n_trials > 1:
            best_sr = max(sharpes)
            ln_n = math.log(max(n_trials, 2))
            e_max_sr = (
                math.sqrt(2.0 * ln_n)
                * (1.0 - _EULER_MASCHERONI / (2.0 * ln_n))
                + _EULER_MASCHERONI / math.sqrt(2.0 * ln_n)
            )
            # Global deflated: probability that best SR exceeds E[max(SR)]
            deflated_sharpe = round(
                _norm_cdf((best_sr - e_max_sr) * math.sqrt(max(n_trials - 1, 1))),
                4,
            )

        # Per-combo DSR: P(SR_i > 0 | N trials tested)
        # DSR_i = Phi((SR_i - E[max(SR)]) * sqrt(T-1))
        for cr in combo_results:
            sr = cr.get("is_sharpe")
            if sr is not None and sr != 999.0 and e_max_sr is not None and n_trials > 1:
                cr["is_dsharpe"] = round(
                    _norm_cdf((float(sr) - e_max_sr) * math.sqrt(max(n_trials - 1, 1))),
                    4,
                )
            else:
                cr["is_dsharpe"] = None

        return {
            "opt_id": opt_id,
            "status": self.get_optimization(opt_id).get("status"),
            "objective": objective,
            "combination_results": combo_results,
            "best_combo_idx": best_idx,
            "deflated_sharpe": deflated_sharpe,
            "n_trials": len(combo_results),
        }

    # -- delete -------------------------------------------------------------

    def delete_optimization(self, opt_id: str) -> None:
        opt_dir = self._require_dir(opt_id)
        manifest = self._read_json(opt_dir / "opt_manifest.json")
        run_manager = get_run_manager()
        for combo in manifest.get("combinations", []):
            for rid in combo.get("is_run_ids", []):
                try:
                    run_manager.delete_run(rid)
                except FileNotFoundError:
                    pass
            oos_rid = combo.get("oos_run_id")
            if oos_rid:
                try:
                    run_manager.delete_run(oos_rid)
                except FileNotFoundError:
                    pass
        shutil.rmtree(opt_dir)

    # -- helpers ------------------------------------------------------------

    def _require_dir(self, opt_id: str) -> Path:
        d = self.opt_root / opt_id
        if not d.exists():
            raise FileNotFoundError(f"Optimization run not found: {opt_id}")
        return d

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))


# -- Singleton --------------------------------------------------------------

_OPT_MANAGER: OptimizationManager | None = None


def get_optimization_manager() -> OptimizationManager:
    global _OPT_MANAGER
    if _OPT_MANAGER is None:
        _OPT_MANAGER = OptimizationManager()
    return _OPT_MANAGER
