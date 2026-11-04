from __future__ import annotations

from fastapi import APIRouter, HTTPException

from prosperity4bt.api.schemas import CpcvCreateRequest
from prosperity4bt.runners.cpcv_manager import get_cpcv_manager


router = APIRouter(prefix="/api/research", tags=["cpcv"])


@router.post("/cpcv")
def create_cpcv_run(payload: CpcvCreateRequest) -> dict[str, object]:
    manager = get_cpcv_manager()
    try:
        return manager.start_cpcv_run(
            trader_path=payload.trader_path,
            round_days=[item.model_dump() for item in payload.round_days],
            n_groups=payload.n_groups,
            k_test_groups=payload.k_test_groups,
            purge_groups=payload.purge_groups,
            embargo_pct=payload.embargo_pct,
            matching_mode=payload.matching_mode,
            fill_probability=payload.fill_probability,
            activity_boost=payload.activity_boost,
            sigma=payload.sigma,
            edge_fill_boost=payload.edge_fill_boost,
            random_seed=payload.random_seed,
            limit_overrides=payload.limit_overrides,
            data_roots=payload.data_roots,
            time_limit_ms=payload.time_limit_ms,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/cpcv")
def list_cpcv_runs() -> list[dict[str, object]]:
    return get_cpcv_manager().list_cpcv_runs()


@router.get("/cpcv/{cpcv_id}")
def get_cpcv_run(cpcv_id: str) -> dict[str, object]:
    try:
        return get_cpcv_manager().get_cpcv_run(cpcv_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/cpcv/{cpcv_id}/results")
def get_cpcv_results(cpcv_id: str) -> dict[str, object]:
    try:
        return get_cpcv_manager().get_cpcv_results(cpcv_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/cpcv/{cpcv_id}")
def delete_cpcv_run(cpcv_id: str) -> dict[str, object]:
    try:
        get_cpcv_manager().delete_cpcv_run(cpcv_id)
        return {"deleted": cpcv_id}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
