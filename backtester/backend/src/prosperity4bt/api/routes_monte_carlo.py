from __future__ import annotations

from fastapi import APIRouter, HTTPException

from prosperity4bt.api.schemas import MonteCarloCreateRequest
from prosperity4bt.runners.mc_manager import get_mc_manager


router = APIRouter(prefix="/api/research", tags=["monte-carlo"])


@router.post("/monte-carlo")
def create_mc_run(payload: MonteCarloCreateRequest) -> dict[str, object]:
    manager = get_mc_manager()
    try:
        return manager.start_mc_run(
            trader_path=payload.trader_path,
            round_days=[item.model_dump() for item in payload.round_days],
            num_paths=payload.num_paths,
            base_seed=payload.base_seed,
            fill_probability=payload.fill_probability,
            activity_boost=payload.activity_boost,
            sigma=payload.sigma,
            edge_fill_boost=payload.edge_fill_boost,
            limit_overrides=payload.limit_overrides,
            data_roots=payload.data_roots,
            time_limit_ms=payload.time_limit_ms,
            fill_skip_prob=payload.fill_skip_prob,
            adverse_selection=payload.adverse_selection,
            min_fill_fraction=payload.min_fill_fraction,
            max_fill_fraction=payload.max_fill_fraction,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/monte-carlo")
def list_mc_runs() -> list[dict[str, object]]:
    return get_mc_manager().list_mc_runs()


@router.get("/monte-carlo/{mc_id}")
def get_mc_run(mc_id: str) -> dict[str, object]:
    try:
        return get_mc_manager().get_mc_run(mc_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/monte-carlo/{mc_id}/results")
def get_mc_results(mc_id: str) -> dict[str, object]:
    try:
        return get_mc_manager().get_mc_results(mc_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/monte-carlo/{mc_id}")
def delete_mc_run(mc_id: str) -> dict[str, object]:
    try:
        get_mc_manager().delete_mc_run(mc_id)
        return {"deleted": mc_id}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
