from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from prosperity4bt.api.schemas import OfficialLogImportRequest
from prosperity4bt.runners.run_manager import get_run_manager


router = APIRouter(prefix="/api", tags=["exports"])


@router.get("/runs/{run_id}/artifacts/{artifact_name}")
def download_artifact(run_id: str, artifact_name: str) -> FileResponse:
    try:
        path = get_run_manager().get_artifact_path(run_id, artifact_name)
        return FileResponse(path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/imports/official-log")
def import_log(payload: OfficialLogImportRequest) -> dict[str, object]:
    try:
        return get_run_manager().import_official_log(
            run_id=payload.run_id,
            label=payload.label,
            text=payload.text,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/comparisons/{comparison_id}")
def get_comparison(comparison_id: str) -> dict[str, object]:
    try:
        return get_run_manager().get_comparison(comparison_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
