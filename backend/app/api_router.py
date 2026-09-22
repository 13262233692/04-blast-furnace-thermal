"""FastAPI 路由: 反演结果查询、概览统计与参数调节。"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .cache_manager import cache
from .config import settings

router = APIRouter(prefix="/api")


class RegParams(BaseModel):
    reg_lambda: Optional[float] = Field(default=None, gt=0)
    reg_mu: Optional[float] = Field(default=None, ge=0)


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "data_source": "mock" if settings.use_mock else "influxdb"}


@router.get("/inversion/field")
def get_field(
    level: int = Query(default=0, ge=0),
    since: float = Query(default=0.0, ge=0.0),
) -> dict:
    """获取指定层温度场。since 为前端已持有数据的时间戳，用于增量更新。"""
    if level >= settings.n_levels:
        raise HTTPException(status_code=404, detail=f"level 超出范围 [0, {settings.n_levels})")
    return cache.get_field(level=level, since=since)


@router.get("/inversion/overview")
def get_overview() -> dict:
    """各层反演统计与原始传感器读数。"""
    return cache.get_overview()


@router.post("/inversion/params")
def update_params(params: RegParams) -> dict:
    """调节正则化参数，下一帧强制重新反演。"""
    return cache.update_params(params.reg_lambda, params.reg_mu)
