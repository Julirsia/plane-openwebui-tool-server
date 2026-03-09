from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.deps import get_plane_client
from app.routes.health import router as health_router
from app.routes.tools import router as tools_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    try:
        client = get_plane_client()
    except RuntimeError:
        return
    await client.close()


app = FastAPI(
    title="Plane OpenWebUI MCP Thin Adapter",
    version="0.2.0",
    description="Compatibility-first thin adapter for Plane ticket operations.",
    lifespan=lifespan,
)
app.include_router(health_router)
app.include_router(tools_router)
