from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.deps import get_plane_client
from app.routes.health import router as health_router
from app.routes.meta import router as meta_router
from app.routes.tickets import router as tickets_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    try:
        client = get_plane_client()
    except RuntimeError:
        return
    await client.close()


app = FastAPI(
    title="Plane OpenWebUI Tool Server",
    version="0.1.0",
    description="Internal-only Plane tool server for OpenWebUI ticket operations.",
    lifespan=lifespan,
)
app.include_router(health_router)
app.include_router(meta_router)
app.include_router(tickets_router)
