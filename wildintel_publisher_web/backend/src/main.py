"""
WildINTEL Publisher — FastAPI backend entry point.

Creates the app, registers middleware and routers, mounts static files.
"""
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from settings import configure_logging, settings
from api.routers import b2share, camtrapdp, camtrapdp_source, fs, gbif, health, hfh, publish, software, trapper, zenodo

configure_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield


app = FastAPI(title="WildINTEL Publisher API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

for _router in [
    health.router,
    trapper.router,
    camtrapdp.router,
    camtrapdp_source.router,
    fs.router,
    hfh.router,
    zenodo.router,
    b2share.router,
    gbif.router,
    publish.router,
    software.router,
]:
    app.include_router(_router)


def _static_dir() -> Path | None:
    if getattr(sys, "frozen", False):
        candidate = Path(sys._MEIPASS) / "static"  # type: ignore[attr-defined]
    else:
        candidate = Path(__file__).parent.parent / "frontend" / "dist"
    return candidate if candidate.exists() else None


_sd = _static_dir()
if _sd is not None:
    app.mount("/", StaticFiles(directory=str(_sd), html=True), name="static")
