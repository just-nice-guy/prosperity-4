from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import asdict
from pathlib import Path

from prosperity4bt.adapters.official_log_importer import import_official_log
from prosperity4bt.config.settings import get_settings
from prosperity4bt.core.engine import DayRequest, EngineConfig
from prosperity4bt.data.catalog import DatasetCatalog
from prosperity4bt.data.loaders_prices import load_prices
from prosperity4bt.logging.exporters import write_json


class RunManager:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.runs_root = self.settings.artifacts_root
        self.db_root = self.settings.workspace_root / "db"
        self.comparisons_root = self.db_root / "comparisons"
        self.comparisons_root.mkdir(parents=True, exist_ok=True)

    def start_run(
        self,
        trader_path: str,
        round_days: list[dict[str, int]],
        matching_mode: str = "prosperity",
        fill_probability: float = 0.005,
        activity_boost: float = 0.003,
        random_seed: int | None = None,
        sigma: float = 0.0,
        limit_overrides: dict[str, int] | None = None,
        data_roots: list[str] | None = None,
        time_limit_ms: int | None = None,
        fill_skip_prob: float = 0.0,
        adverse_selection: float = 0.0,
        min_fill_fraction: float = 0.5,
        max_fill_fraction: float = 1.0,
        edge_fill_boost: float = 0.0,
        mc_parent: str | None = None,
        day_tick_ranges: dict[str, list[tuple[int, int]]] | None = None,
    ) -> dict[str, object]:
        run_id = uuid.uuid4().hex[:12]
        run_directory = self.runs_root / run_id
        run_directory.mkdir(parents=True, exist_ok=True)

        config = EngineConfig(
            trader_path=trader_path,
            round_days=[
                DayRequest(round_num=int(item["round_num"]), day_num=int(item["day_num"]))
                for item in round_days
            ],
            limit_overrides=limit_overrides or {},
            data_roots=data_roots or [],
            time_limit_ms=int(time_limit_ms or self.settings.time_limit_ms),
            matching_mode=matching_mode,
            fill_probability=fill_probability,
            activity_boost=activity_boost,
            random_seed=random_seed,
            sigma=sigma,
            run_id=run_id,
            fill_skip_prob=fill_skip_prob,
            adverse_selection=adverse_selection,
            min_fill_fraction=min_fill_fraction,
            max_fill_fraction=max_fill_fraction,
            edge_fill_boost=edge_fill_boost,
            day_tick_ranges=day_tick_ranges,
        )
        worker_payload = asdict(config) | {
            "run_directory": str(run_directory),
        }
        config_path = run_directory / "worker_config.json"
        config_path.write_text(json.dumps(worker_payload, indent=2), encoding="utf-8")

        manifest = {
            "run_id": run_id,
            "status": "running",
            "trader_path": trader_path,
            "datasets": round_days,
            "matching_mode": matching_mode,
            **({"mc_parent": mc_parent} if mc_parent else {}),
        }
        write_json(run_directory / "manifest.json", manifest)

        env = os.environ.copy()
        src_path = self.settings.repo_root / "backtester" / "backend" / "src"
        env["PYTHONPATH"] = str(src_path) + os.pathsep + env.get("PYTHONPATH", "")

        stdout_handle = (run_directory / "worker.stdout.log").open("w", encoding="utf-8")
        stderr_handle = (run_directory / "worker.stderr.log").open("w", encoding="utf-8")
        subprocess.Popen(
            [sys.executable, "-m", "prosperity4bt.runners.worker", "--config", str(config_path)],
            cwd=self.settings.repo_root / "backtester" / "backend",
            env=env,
            stdout=stdout_handle,
            stderr=stderr_handle,
        )
        stdout_handle.close()
        stderr_handle.close()
        return self.get_run(run_id)

    def list_runs(self, include_mc_children: bool = False) -> list[dict[str, object]]:
        runs: list[dict[str, object]] = []
        if not self.runs_root.exists():
            return runs
        for run_directory in sorted(
            [path for path in self.runs_root.iterdir() if path.is_dir()],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        ):
            try:
                run = self.get_run(run_directory.name)
                if not include_mc_children:
                    manifest = run.get("manifest", {})
                    if manifest.get("mc_parent"):
                        continue
                runs.append(run)
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                continue
        return runs

    def get_run(self, run_id: str) -> dict[str, object]:
        run_directory = self._require_run_directory(run_id)
        manifest = self._read_json(run_directory / "manifest.json")
        summary_path = run_directory / "summary.json"
        config_path = run_directory / "run_config.json"
        worker_config_path = run_directory / "worker_config.json"
        try:
            config = (
                self._read_json(config_path)
                if config_path.exists()
                else self._read_json(worker_config_path) if worker_config_path.exists() else None
            )
        except (json.JSONDecodeError, OSError):
            config = None

        try:
            summary = self._read_json(summary_path) if summary_path.exists() else None
        except (json.JSONDecodeError, OSError):
            summary = None

        return {
            "run_id": run_id,
            "manifest": manifest,
            "summary": summary,
            "config": config,
        }

    def read_timeline(
        self,
        run_id: str,
        product: str | None = None,
        round_num: int | None = None,
        day_num: int | None = None,
    ) -> list[dict[str, str]]:
        rows = self._read_csv(self._require_run_directory(run_id) / "activity.csv")
        return [
            row
            for row in rows
            if (product is None or row.get("product") == product)
            and (round_num is None or int(row.get("round_num", 0)) == round_num)
            and (day_num is None or int(row.get("day_num", 0)) == day_num)
        ]

    def read_trades(
        self,
        run_id: str,
        product: str | None = None,
        timestamp: int | None = None,
        round_num: int | None = None,
        day_num: int | None = None,
    ) -> dict[str, list[dict[str, object]]]:
        data = self._read_json(self._require_run_directory(run_id) / "trades.json")
        return {
            section: [
                row
                for row in rows
                if (product is None or row.get("symbol") == product)
                and (timestamp is None or int(row.get("timestamp", -1)) == timestamp)
                and (round_num is None or int(row.get("round_num", 0)) == round_num)
                and (day_num is None or int(row.get("day_num", 0)) == day_num)
            ]
            for section, rows in data.items()
        }

    def read_logs(self, run_id: str) -> dict[str, object]:
        run_directory = self._require_run_directory(run_id)
        sandbox_path = run_directory / "sandbox.log"
        decision_path = run_directory / "decision_trace.jsonl"
        events_path = run_directory / "events.jsonl"
        return {
            "sandbox": sandbox_path.read_text(encoding="utf-8") if sandbox_path.exists() else "",
            "decision_trace": self._read_jsonl(decision_path),
            "events": self._read_jsonl(events_path),
        }

    def list_artifacts(self, run_id: str) -> list[dict[str, object]]:
        run_directory = self._require_run_directory(run_id)
        items: list[dict[str, object]] = []
        for path in sorted(run_directory.iterdir()):
            if path.is_file():
                items.append(
                    {
                        "name": path.name,
                        "path": str(path),
                        "size_bytes": path.stat().st_size,
                    }
                )
        return items

    def get_artifact_path(self, run_id: str, artifact_name: str) -> Path:
        path = self._require_run_directory(run_id) / artifact_name
        if not path.exists():
            raise FileNotFoundError(f"Artifact not found: {artifact_name}")
        return path

    def get_orderbook_snapshot(
        self,
        run_id: str,
        timestamp: int,
        product: str,
        round_num: int | None = None,
        day_num: int | None = None,
    ) -> dict[str, object]:
        run = self.get_run(run_id)
        config = run["config"] or {}
        data_roots = [Path(item) for item in config.get("data_roots", [])] if config.get("data_roots") else None
        catalog = DatasetCatalog(data_roots)

        for selection in config.get("round_days", []):
            item_round = int(selection["round_num"])
            item_day = int(selection["day_num"])
            if round_num is not None and item_round != round_num:
                continue
            if day_num is not None and item_day != day_num:
                continue
            files = catalog.resolve(item_round, item_day)
            for snapshot in load_prices(files.prices_file):
                if snapshot.timestamp == timestamp and snapshot.product == product:
                    return {
                        "round_num": item_round,
                        "day_num": item_day,
                        "timestamp": timestamp,
                        "product": product,
                        "bid_prices": snapshot.bid_prices,
                        "bid_volumes": snapshot.bid_volumes,
                        "ask_prices": snapshot.ask_prices,
                        "ask_volumes": snapshot.ask_volumes,
                        "mid_price": snapshot.mid_price,
                    }
        raise FileNotFoundError(f"No orderbook snapshot for run={run_id}, product={product}, timestamp={timestamp}")

    def import_official_log(self, run_id: str, label: str, text: str) -> dict[str, object]:
        imported = import_official_log(text=text, label=label)
        comparison_id = uuid.uuid4().hex[:12]
        run = self.get_run(run_id)
        summary = run.get("summary") or {}
        comparison = {
            "comparison_id": comparison_id,
            "run_id": run_id,
            "label": label,
            "local": {
                "final_pnl": (summary.get("final_pnl") if isinstance(summary, dict) else None),
                "trade_count": len(self.read_trades(run_id)["own_trades"]),
                "status": (summary.get("status") if isinstance(summary, dict) else None),
            },
            "official": {
                "activity_rows": len(imported.activity_rows),
                "trade_count": len(imported.trade_rows),
                "derived_final_pnl": _extract_official_final_pnl(imported.activity_rows),
            },
            "diff": {
                "trade_count_delta": len(self.read_trades(run_id)["own_trades"]) - len(imported.trade_rows),
                "final_pnl_delta": _safe_delta(
                    (summary.get("final_pnl") if isinstance(summary, dict) else None),
                    _extract_official_final_pnl(imported.activity_rows),
                ),
            },
            "official_log": {
                "sandbox_lines": imported.sandbox_lines,
                "activity_rows": imported.activity_rows,
                "trade_rows": imported.trade_rows,
            },
        }
        path = self.comparisons_root / f"{comparison_id}.json"
        write_json(path, comparison)
        return comparison

    def delete_run(self, run_id: str) -> None:
        run_directory = self._require_run_directory(run_id)
        shutil.rmtree(run_directory)

    def delete_all_runs(self) -> int:
        if not self.runs_root.exists():
            return 0
        count = 0
        for run_directory in [p for p in self.runs_root.iterdir() if p.is_dir()]:
            # Skip MC child runs — they are owned by the MC manager
            manifest_path = run_directory / "manifest.json"
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    if manifest.get("mc_parent"):
                        continue
                except (json.JSONDecodeError, OSError):
                    pass
            shutil.rmtree(run_directory)
            count += 1
        return count

    def get_comparison(self, comparison_id: str) -> dict[str, object]:
        path = self.comparisons_root / f"{comparison_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Comparison not found: {comparison_id}")
        return self._read_json(path)

    def _require_run_directory(self, run_id: str) -> Path:
        run_directory = self.runs_root / run_id
        if not run_directory.exists():
            raise FileNotFoundError(f"Run not found: {run_id}")
        return run_directory

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, object]]:
        if not path.exists():
            return []
        rows: list[dict[str, object]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows


_RUN_MANAGER: RunManager | None = None


def get_run_manager() -> RunManager:
    global _RUN_MANAGER
    if _RUN_MANAGER is None:
        _RUN_MANAGER = RunManager()
    return _RUN_MANAGER


def _extract_official_final_pnl(activity_rows: list[dict[str, str]]) -> float | None:
    if not activity_rows:
        return None
    last_row = activity_rows[-1]
    for key in ("profit_and_loss", "profitAndLoss", "pnl", "P&L"):
        if key in last_row and last_row[key] not in ("", None):
            return float(last_row[key])
    return None


def _safe_delta(left: object, right: object) -> float | None:
    if left is None or right is None:
        return None
    return float(left) - float(right)
