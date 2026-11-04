from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from prosperity4bt.api.schemas import OptimizationCreateRequest
from prosperity4bt.runners.optimization_manager import get_optimization_manager
from prosperity4bt.runners.param_discovery import create_modified_trader, discover_parameters

router = APIRouter(prefix="/api/research/optimization", tags=["optimization"])


@router.get("/discover")
def discover_params(trader_path: str = Query(...)) -> list[dict[str, object]]:
    try:
        return discover_parameters(trader_path)
    except FileNotFoundError:
        raise HTTPException(404, f"Trader file not found: {trader_path}")
    except SyntaxError as exc:
        raise HTTPException(400, f"Syntax error in trader file: {exc}")


@router.post("")
def create_optimization(req: OptimizationCreateRequest) -> dict[str, object]:
    mgr = get_optimization_manager()
    try:
        return mgr.start_optimization(
            trader_path=req.trader_path,
            round_days=[rd.model_dump() for rd in req.round_days],
            parameters=[p.model_dump() for p in req.parameters],
            search_method=req.search_method,
            search_budget=req.search_budget,
            objective=req.objective,
            is_fraction=req.is_fraction,
            cpcv_n=req.cpcv_n,
            cpcv_k=req.cpcv_k,
            purge_groups=req.purge_groups,
            embargo_pct=req.embargo_pct,
            matching_mode=req.matching_mode,
            fill_probability=req.fill_probability,
            activity_boost=req.activity_boost,
            sigma=req.sigma,
            edge_fill_boost=req.edge_fill_boost,
            random_seed=req.random_seed,
            limit_overrides=req.limit_overrides,
            data_roots=req.data_roots,
            time_limit_ms=req.time_limit_ms,
            min_trades=req.min_trades,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("")
def list_optimizations() -> list[dict[str, object]]:
    return get_optimization_manager().list_optimizations()


@router.get("/{opt_id}")
def get_optimization(opt_id: str) -> dict[str, object]:
    try:
        return get_optimization_manager().get_optimization(opt_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Optimization not found: {opt_id}")


@router.get("/{opt_id}/results")
def get_optimization_results(opt_id: str) -> dict[str, object]:
    try:
        return get_optimization_manager().get_optimization_results(opt_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Optimization not found: {opt_id}")


@router.delete("/{opt_id}")
def delete_optimization(opt_id: str) -> dict[str, str]:
    try:
        get_optimization_manager().delete_optimization(opt_id)
        return {"status": "deleted"}
    except FileNotFoundError:
        raise HTTPException(404, f"Optimization not found: {opt_id}")


class ExportTraderRequest(BaseModel):
    overrides: dict[str, float]


@router.post("/{opt_id}/export-trader")
def export_trader(opt_id: str, req: ExportTraderRequest) -> PlainTextResponse:
    """Generate a modified trader .py file with the given parameter overrides."""
    mgr = get_optimization_manager()
    try:
        opt_dir = mgr._require_dir(opt_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Optimization not found: {opt_id}")

    manifest = mgr._read_json(opt_dir / "opt_manifest.json")
    trader_path = manifest.get("trader_path")
    if not trader_path:
        raise HTTPException(400, "No trader path in optimization manifest")

    from pathlib import Path
    import tempfile
    tmp = Path(tempfile.mktemp(suffix=".py"))
    try:
        create_modified_trader(str(trader_path), req.overrides, str(tmp))
        content = tmp.read_text(encoding="utf-8")
    finally:
        if tmp.exists():
            tmp.unlink()

    return PlainTextResponse(content, media_type="text/x-python")
