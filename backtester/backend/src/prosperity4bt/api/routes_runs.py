from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from prosperity4bt.api.schemas import RunCreateRequest
from prosperity4bt.runners.run_manager import get_run_manager


router = APIRouter(prefix="/api", tags=["runs"])


@router.post("/runs")
def create_run(payload: RunCreateRequest) -> dict[str, object]:
    manager = get_run_manager()
    try:
        return manager.start_run(
            trader_path=payload.trader_path,
            round_days=[item.model_dump() for item in payload.round_days],
            matching_mode=payload.matching_mode,
            fill_probability=payload.fill_probability,
            activity_boost=payload.activity_boost,
            random_seed=payload.random_seed,
            sigma=payload.sigma,
            edge_fill_boost=payload.edge_fill_boost,
            limit_overrides=payload.limit_overrides,
            data_roots=payload.data_roots,
            time_limit_ms=payload.time_limit_ms,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs")
def list_runs() -> list[dict[str, object]]:
    return get_run_manager().list_runs()


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, object]:
    try:
        return get_run_manager().get_run(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/timeline")
def get_timeline(
    run_id: str,
    product: str | None = None,
    round_num: int | None = Query(default=None),
    day_num: int | None = Query(default=None),
) -> list[dict[str, str]]:
    try:
        return get_run_manager().read_timeline(run_id, product=product, round_num=round_num, day_num=day_num)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/orderbook")
def get_orderbook(
    run_id: str,
    timestamp: int,
    product: str,
    round_num: int | None = Query(default=None),
    day_num: int | None = Query(default=None),
) -> dict[str, object]:
    try:
        return get_run_manager().get_orderbook_snapshot(
            run_id=run_id,
            timestamp=timestamp,
            product=product,
            round_num=round_num,
            day_num=day_num,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/trades")
def get_trades(
    run_id: str,
    product: str | None = None,
    timestamp: int | None = None,
    round_num: int | None = Query(default=None),
    day_num: int | None = Query(default=None),
) -> dict[str, list[dict[str, object]]]:
    try:
        return get_run_manager().read_trades(
            run_id=run_id,
            product=product,
            timestamp=timestamp,
            round_num=round_num,
            day_num=day_num,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/logs")
def get_logs(run_id: str) -> dict[str, object]:
    try:
        return get_run_manager().read_logs(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/runs")
def clear_all_runs() -> dict[str, object]:
    count = get_run_manager().delete_all_runs()
    return {"deleted": count}


@router.delete("/runs/{run_id}")
def delete_run(run_id: str) -> dict[str, object]:
    try:
        get_run_manager().delete_run(run_id)
        return {"deleted": run_id}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/artifacts")
def list_artifacts(run_id: str) -> list[dict[str, object]]:
    try:
        return get_run_manager().list_artifacts(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
