"""Database switch endpoints.

POST /api/v1/database/switch        - validate quickly, then run migration in bg
GET  /api/v1/database/switch/status - poll progress

ADMIN ONLY. Wire your existing auth/admin dependency into `require_admin`. On an
internet-exposed instance this endpoint must never be reachable by a non-owner,
since it can repoint the whole datastore.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from src.services.database import switch_service as svc

router = APIRouter(prefix="/database", tags=["database"])


async def require_admin(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if getattr(user, "role", "user") not in {"admin", "superadmin"}:
        raise HTTPException(status_code=403, detail="Admin privileges required.")
    return True


class SwitchRequest(BaseModel):
    url: str
    copy_data: bool = False

    @field_validator("url")
    @classmethod
    def _looks_like_pg(cls, v: str) -> str:
        if not v.startswith(("postgresql://", "postgresql+asyncpg://", "postgresql+psycopg://")):
            raise ValueError("URL must be a PostgreSQL connection string.")
        return v


@router.post("/switch", status_code=202, dependencies=[Depends(require_admin)])
async def start_switch(body: SwitchRequest, request: Request):
    settings = request.app.state.settings

    # Quick synchronous validation so obvious errors return immediately (not as
    # a background failure). Connection + pgvector are fast.
    try:
        await svc.validate_connection(body.url)
        await svc.ensure_pgvector(body.url)
    except svc.SwitchError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Source is the currently-active DB (the bundled local one on first switch).
    source_url = settings.DATABASE_URL or settings.database_url_default

    # Run the heavy part in the background. Single-process lite mode => asyncio
    # task is fine. (Don't route through Celery: this is rare, admin-only, and
    # must run in the web process that will self-restart.)
    asyncio.create_task(
        svc.perform_switch(
            target_url=body.url,
            source_url=source_url,
            data_dir=settings.data_dir,
            copy_existing_data=body.copy_data,
            allow_self_restart=getattr(settings, "allow_self_restart", False),
        )
    )
    return {
        "status": "started",
        "copy_data": body.copy_data,
        "poll": "/api/v1/database/switch/status",
    }


@router.get("/switch/status", dependencies=[Depends(require_admin)])
async def switch_status(request: Request):
    settings = request.app.state.settings
    status = svc.read_status(settings.data_dir)
    return status.__dict__
