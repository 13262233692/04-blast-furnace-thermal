"""FastAPI 路由：传感器数据、炉温场反演、缓存状态。"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from .fem_solver import FemInversionSolver
from .influx_client import InfluxClient, SensorFrame


class InversionConfigPatch(BaseModel):
    reg_lambda: Optional[float] = Field(default=None, gt=0, description="正则化系数")


def get_influx(request: Request) -> InfluxClient:
    return request.app.state.influx


def get_solver(request: Request) -> FemInversionSolver:
    return request.app.state.solver


def create_router(sensor_ttl_s: float = 5.0) -> APIRouter:
    router = APIRouter(prefix="/api")
    # 传感器帧短 TTL 缓存，避免前端高频轮询打满 InfluxDB
    _sensor_cache: dict = {"frame": None, "at": 0.0}

    def _latest_frame(influx: InfluxClient) -> SensorFrame:
        now = time.time()
        if _sensor_cache["frame"] is not None and now - _sensor_cache["at"] < sensor_ttl_s:
            return _sensor_cache["frame"]
        frame = influx.fetch_latest()
        _sensor_cache.update(frame=frame, at=now)
        return frame

    @router.get("/health")
    def health(influx: InfluxClient = Depends(get_influx)):
        return {
            "status": "ok",
            "influx_live": influx.is_live,
            "time": time.time(),
        }

    @router.get("/sensors/latest")
    def sensors_latest(influx: InfluxClient = Depends(get_influx)):
        return _latest_frame(influx).as_dict()

    @router.get("/thermal-field")
    def thermal_field(
        lam: Optional[float] = Query(default=None, gt=0, description="正则化系数"),
        influx: InfluxClient = Depends(get_influx),
        solver: FemInversionSolver = Depends(get_solver),
    ):
        frame = _latest_frame(influx)
        result = solver.invert(frame.values, frame.timestamp, lam=lam)
        payload = result.as_dict()
        payload["sensor_source"] = frame.source
        return payload

    @router.get("/cache/stats")
    def cache_stats(solver: FemInversionSolver = Depends(get_solver)):
        return solver.cache_stats()

    @router.post("/inversion/config")
    def update_config(
        patch: InversionConfigPatch,
        solver: FemInversionSolver = Depends(get_solver),
    ):
        # 正则化系数按请求生效，这里仅返回当前生效值与缓存状态
        return {
            "reg_lambda": patch.reg_lambda,
            "cache": solver.cache_stats(),
        }

    return router
