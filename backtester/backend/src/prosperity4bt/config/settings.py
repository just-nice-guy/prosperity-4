from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


@dataclass(frozen=True)
class Settings:
    repo_root: Path
    workspace_root: Path
    default_data_roots: tuple[Path, ...]
    artifacts_root: Path
    mc_runs_root: Path
    cpcv_runs_root: Path
    optimization_runs_root: Path
    time_limit_ms: int = 900


def get_settings() -> Settings:
    repo_root = _repo_root()
    workspace_root = repo_root / "backtester" / "backend" / "workspace"
    return Settings(
        repo_root=repo_root,
        workspace_root=workspace_root,
        default_data_roots=(
            repo_root / "Stage2" / "initial data",
        ),
        artifacts_root=workspace_root / "runs",
        mc_runs_root=workspace_root / "mc_runs",
        cpcv_runs_root=workspace_root / "cpcv_runs",
        optimization_runs_root=workspace_root / "optimization_runs",
    )


# ── Runtime settings (persisted to JSON, mutable) ─────────────────────────

_RUNTIME_SETTINGS_FILE = "runtime_settings.json"

_DEFAULT_RUNTIME: dict[str, object] = {
    "max_concurrent_runs": max(1, os.cpu_count() // 2 if os.cpu_count() else 2),
    "cleanup_temp_traders": True,
    "max_optimization_combos": 200,
    "max_total_runs": 2000,
    "cpu_limit": 0,       # 0 = no limit (use max_concurrent_runs)
    "ram_limit_mb": 0,    # 0 = no limit
}


def _runtime_path() -> Path:
    return get_settings().workspace_root / _RUNTIME_SETTINGS_FILE


def get_runtime_settings() -> dict[str, object]:
    path = _runtime_path()
    result = dict(_DEFAULT_RUNTIME)
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            result.update(stored)
        except (json.JSONDecodeError, OSError):
            pass
    return result


def save_runtime_settings(data: dict[str, object]) -> dict[str, object]:
    path = _runtime_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = dict(_DEFAULT_RUNTIME)
    merged.update(data)
    path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return merged
