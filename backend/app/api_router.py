"""REST API for the thermal-field inversion system."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from .fem_solver import InversionResult
from .inversion_service import get_service

router = APIRouter(prefix="/api")


class InversionResponse(BaseModel):
    updated: bool
    timestamp: float
    grid_n: Optional[int] = None
    x: Optional[List[float]] = None
    y: Optional[List[float]] = None
    field: Optional[List[List[Optional[float]]]] = None
    hot_face: Optional[List[float]] = None
    theta: Optional[List[float]] = None
    tc_theta: Optional[List[float]] = None
    tc_values: Optional[List[float]] = None
    residual: Optional[float] = None


def _to_response(result: InversionResult, updated: bool, full: bool) -> InversionResponse:
    if not full:
        return InversionResponse(updated=False, timestamp=result.timestamp)
    return InversionResponse(
        updated=updated,
        timestamp=result.timestamp,
        grid_n=result.grid_n,
        x=result.x,
        y=result.y,
        field=result.field,
        hot_face=result.hot_face,
        theta=result.theta,
        tc_theta=result.tc_theta,
        tc_values=result.tc_values,
        residual=result.residual,
    )


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/inversion/latest", response_model=InversionResponse)
def latest(since: Optional[float] = Query(default=None)) -> InversionResponse:
    """Latest inversion. Incremental: pass ``since`` to skip unchanged payloads."""
    service = get_service()
    result, recomputed = service.get()
    if since is not None and result.timestamp <= since + 1e-6:
        return _to_response(result, updated=False, full=False)
    return _to_response(result, updated=recomputed, full=True)


@router.post("/inversion/refresh", response_model=InversionResponse)
def refresh(reg_lambda: Optional[float] = Query(default=None, gt=0)) -> InversionResponse:
    """Force a recomputation, optionally overriding the regularisation weight."""
    service = get_service()
    if reg_lambda is not None:
        service.set_reg_lambda(reg_lambda)
    result, _ = service.get(force=True)
    return _to_response(result, updated=True, full=True)


@router.get("/thermocouples")
def thermocouples() -> dict:
    """Latest raw thermocouple readings and their angular positions."""
    result, _ = get_service().get()
    return {
        "timestamp": result.timestamp,
        "tc_theta": result.tc_theta,
        "tc_values": result.tc_values,
    }
