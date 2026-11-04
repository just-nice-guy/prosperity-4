from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from prosperity4bt.api.routes_data import router as data_router
from prosperity4bt.api.routes_exports import router as exports_router
from prosperity4bt.api.routes_cpcv import router as cpcv_router
from prosperity4bt.api.routes_monte_carlo import router as mc_router
from prosperity4bt.api.routes_optimization import router as optimization_router
from prosperity4bt.api.routes_runs import router as runs_router
from prosperity4bt.api.routes_settings import router as settings_router
from prosperity4bt.api.routes_synthetics import router as synthetics_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Suppress the CancelledError that Starlette raises during clean shutdown."""
    yield
    # Drain any pending asyncio tasks so uvicorn's signal handler doesn't
    # emit a noisy CancelledError traceback on Ctrl+C.
    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.sleep(0)


app = FastAPI(
    title="Prosperity 4 Backtester",
    version="0.1.0",
    description="Local backtester, API and run explorer for Prosperity 4.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(data_router)
app.include_router(runs_router)
app.include_router(exports_router)
app.include_router(mc_router)
app.include_router(cpcv_router)
app.include_router(optimization_router)
app.include_router(settings_router)
app.include_router(synthetics_router)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
