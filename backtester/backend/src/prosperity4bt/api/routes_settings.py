from __future__ import annotations

import os

import psutil
from fastapi import APIRouter
from pydantic import BaseModel, Field

from prosperity4bt.config.settings import get_runtime_settings, save_runtime_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


class RuntimeSettingsUpdate(BaseModel):
    max_concurrent_runs: int = Field(4, ge=1, le=32)
    cleanup_temp_traders: bool = True
    max_optimization_combos: int = Field(200, ge=1, le=1000)
    max_total_runs: int = Field(2000, ge=1, le=10000)
    cpu_limit: int = Field(0, ge=0, le=128)
    ram_limit_mb: int = Field(0, ge=0, le=131072)


@router.get("")
def get_settings_api() -> dict[str, object]:
    return get_runtime_settings()


@router.put("")
def update_settings_api(req: RuntimeSettingsUpdate) -> dict[str, object]:
    return save_runtime_settings(req.model_dump())


@router.get("/system-info")
def get_system_info() -> dict[str, object]:
    """Return live system resource information."""
    vm = psutil.virtual_memory()
    cpu_count_logical = os.cpu_count() or 1
    cpu_count_physical = psutil.cpu_count(logical=False) or cpu_count_logical
    cpu_pct = psutil.cpu_percent(interval=0.3)

    # Count running backtester workers
    worker_count = 0
    worker_pids: list[int] = []
    worker_rss_total = 0
    try:
        for proc in psutil.process_iter(["pid", "cmdline", "memory_info"]):
            cmdline = proc.info.get("cmdline") or []
            if any("prosperity4bt.runners.worker" in c for c in cmdline):
                worker_count += 1
                worker_pids.append(proc.info["pid"])
                mem = proc.info.get("memory_info")
                if mem:
                    worker_rss_total += mem.rss
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    return {
        "cpu_logical": cpu_count_logical,
        "cpu_physical": cpu_count_physical,
        "cpu_percent": round(cpu_pct, 1),
        "ram_total_mb": round(vm.total / (1024 * 1024)),
        "ram_available_mb": round(vm.available / (1024 * 1024)),
        "ram_used_mb": round(vm.used / (1024 * 1024)),
        "ram_percent": round(vm.percent, 1),
        "worker_count": worker_count,
        "worker_pids": worker_pids,
        "worker_ram_mb": round(worker_rss_total / (1024 * 1024)),
    }
