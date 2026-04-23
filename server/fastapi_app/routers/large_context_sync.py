"""Large context sync configuration and status endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..services.large_context_sync.engine import LargeContextSyncBusyError
from ..services.large_context_sync.models import (
    LargeContextIntegrationConfigUpdate,
    LargeContextSyncConfigUpdate,
    ManualRunRequest,
)

router = APIRouter()


def _get_service(request: Request):
    service = getattr(request.app.state, "large_context_sync_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Large context sync service is unavailable")
    return service


@router.get("/config")
async def get_large_context_sync_config(request: Request):
    service = _get_service(request)
    return {"config": service.get_config().model_dump()}


@router.put("/config")
async def update_large_context_sync_config(request: Request, body: LargeContextSyncConfigUpdate):
    service = _get_service(request)
    config = service.update_config(enabled=body.enabled, interval_minutes=body.interval_minutes)
    return {"ok": True, "config": config.model_dump()}


@router.put("/integrations/{integration_id}")
async def update_large_context_sync_integration(
    request: Request,
    integration_id: str,
    body: LargeContextIntegrationConfigUpdate,
):
    service = _get_service(request)
    try:
        config = service.update_integration_config(
            integration_id,
            enabled=body.enabled,
            interval_minutes=body.interval_minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "integration": config.model_dump()}


@router.get("/status")
async def get_large_context_sync_status(request: Request):
    service = _get_service(request)
    return service.get_status()


@router.post("/run")
async def run_large_context_sync(request: Request, body: ManualRunRequest | None = None):
    service = _get_service(request)
    try:
        result = await service.run_now(body)
    except LargeContextSyncBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "run": result.model_dump()}


@router.get("/providers")
async def list_large_context_sync_providers(request: Request):
    service = _get_service(request)
    return {"providers": service.list_providers()}
