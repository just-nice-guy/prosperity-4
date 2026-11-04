"""API endpoints for synthetic backtest datasets.

Each trader version's results live under
  Stage1/Round1/synthetic_datasets/results/<label>/{manifest.json, *.log}

Endpoints:
  GET  /api/synthetics/traders                — list available trader scripts
  GET  /api/synthetics/labels                 — list trader labels with cached results
  GET  /api/synthetics?label=<L>              — list datasets for label L
  GET  /api/synthetics/{label}/{scenario}/log — full Prosperity-format log JSON
  POST /api/synthetics/run                    — re-run backtests for chosen trader
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/synthetics", tags=["synthetics"])

# REPO root: this file is backend/src/prosperity4bt/api/routes_synthetics.py
REPO = Path(__file__).resolve().parents[5]
RESULTS_BASE = REPO / "Stage1" / "Round1" / "synthetic_datasets" / "results"
TRADER_DIR = REPO / "Stage1" / "Round1" / "pepper"
RUN_SCRIPT = REPO / "Stage1" / "Round1" / "synthetic_datasets" / "run_synthetic_backtests.py"


@router.get("/traders")
def list_traders() -> dict[str, list[dict]]:
    """List all *.py trader files in Stage1/Round1/pepper/."""
    traders = []
    for p in sorted(TRADER_DIR.glob("trader*.py")):
        traders.append({
            "name": p.stem,
            "filename": p.name,
            "path": str(p),
        })
    return {"traders": traders}


@router.get("/labels")
def list_labels() -> dict[str, list[dict]]:
    """List all trader labels that have cached results."""
    labels = []
    if RESULTS_BASE.exists():
        for d in sorted(RESULTS_BASE.iterdir()):
            if not d.is_dir():
                continue
            mf = d / "manifest.json"
            if not mf.exists():
                continue
            try:
                m = json.loads(mf.read_text(encoding="utf-8"))
                n = len(m.get("datasets", []))
                pnls = [d_.get("pnl", 0) for d_ in m.get("datasets", [])]
                mean_pnl = sum(pnls) / max(1, len(pnls))
                labels.append({
                    "label": d.name,
                    "trader_path": m.get("trader_path", ""),
                    "n_datasets": n,
                    "mean_pnl": mean_pnl,
                })
            except json.JSONDecodeError:
                continue
    return {"labels": labels}


@router.get("")
def list_synthetics(label: str = Query(...)) -> dict[str, object]:
    """List all dataset summaries for a given trader label."""
    manifest_path = RESULTS_BASE / label / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail=f"No results for label '{label}'")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid manifest.json")
    return {**manifest, "results_dir": str(RESULTS_BASE / label)}


@router.get("/{label}/{scenario}/log")
def get_synthetic_log(label: str, scenario: str) -> dict:
    """Return the full Prosperity-format log JSON for a given scenario+label."""
    log_path = RESULTS_BASE / label / f"{scenario}.log"
    if not log_path.exists():
        raise HTTPException(status_code=404,
                            detail=f"Scenario '{scenario}' not found for label '{label}'")
    try:
        return json.loads(log_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"Invalid log file")


class RunRequest(BaseModel):
    trader_path: str
    label: str | None = None


@router.post("/run")
def run_backtests(req: RunRequest) -> dict:
    """Trigger synchronous re-run of all synthetic backtests for given trader."""
    trader = Path(req.trader_path)
    if not trader.exists():
        raise HTTPException(status_code=400, detail=f"Trader file not found: {trader}")
    label = req.label or trader.stem
    cmd = [
        sys.executable, str(RUN_SCRIPT),
        "--trader", str(trader),
        "--label", label,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(REPO),
            timeout=300, encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Backtest run timed out")
    if result.returncode != 0:
        raise HTTPException(status_code=500,
                            detail=f"Run failed: {result.stderr[:500]}")
    # Load fresh manifest
    manifest_path = RESULTS_BASE / label / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=500, detail="Manifest not produced")
    return json.loads(manifest_path.read_text(encoding="utf-8"))
