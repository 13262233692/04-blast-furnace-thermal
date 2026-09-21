"""FastAPI 反演 API 路由层。

缓存与增量更新策略：
  - InversionCache 以数据时间戳为键缓存最近一次反演结果；
    InfluxDB 数据时间戳未变化时直接命中缓存，不重新求解；
  - 每次真实重算使 version 单调递增，前端轮询时携带
    since_version，若服务端版本未变则返回 updated=false 的
    轻量响应（增量更新，避免重复传输整个温度场网格）。
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Query

from fem_solver import FemThermalSolver, InversionResult
from influx_client import InfluxThermocoupleClient, SensorSnapshot


class InversionCache:
    """反演结果缓存：按数据时间戳去重，按版本号支持增量同步。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.version: int = 0
        self.data_timestamp: float = 0.0  # 已反演的传感器数据时间戳
        self.result: Optional[InversionResult] = None
        self.snapshot: Optional[SensorSnapshot] = None
        self.compute_ms: float = 0.0
        self.hit_count: int = 0   # 缓存命中次数
        self.miss_count: int = 0  # 真实重算次数

    def get_if_fresh(self, data_ts: float) -> Optional[InversionResult]:
        with self._lock:
            if self.result is not None and abs(data_ts - self.data_timestamp) < 1e-6:
                self.hit_count += 1
                return self.result
            return None

    def update(self, data_ts: float, result: InversionResult,
               snapshot: SensorSnapshot, compute_ms: float) -> int:
        with self._lock:
            self.data_timestamp = data_ts
            self.result = result
            self.snapshot = snapshot
            self.compute_ms = compute_ms
            self.version += 1
            self.miss_count += 1
            return self.version

    def stats(self) -> dict:
        with self._lock:
            return {
                "version": self.version,
                "data_timestamp": self.data_timestamp,
                "compute_ms": round(self.compute_ms, 2),
                "cache_hits": self.hit_count,
                "cache_misses": self.miss_count,
            }


def build_router(
    influx: InfluxThermocoupleClient,
    solver: FemThermalSolver,
    cache: InversionCache,
) -> APIRouter:
    router = APIRouter(prefix="/api")

    def _compute_if_stale() -> SensorSnapshot:
        """拉取最新数据；仅当数据时间戳变化时才重新反演。"""
        snap = influx.fetch_latest()
        if cache.get_if_fresh(snap.timestamp) is None:
            t0 = time.perf_counter()
            result = solver.solve(snap.temps)
            compute_ms = (time.perf_counter() - t0) * 1000.0
            cache.update(snap.timestamp, result, snap, compute_ms)
        return snap

    @router.get("/health")
    def health() -> dict:
        return {"status": "ok", "influx": influx.status(), "cache": cache.stats()}

    @router.get("/thermal/raw")
    def thermal_raw() -> dict:
        """最新 32 支热电偶原始读数。"""
        snap = _compute_if_stale()
        return {
            "timestamp": snap.timestamp,
            "source": snap.source,
            "temps": snap.temps,
            "version": cache.version,
        }

    @router.get("/thermal/field")
    def thermal_field(
        since_version: int = Query(0, description="前端已持有的结果版本号"),
    ) -> dict:
        """反演温度场。增量更新：since_version 与服务端一致时
        仅返回 updated=false，不重复传输网格数据。"""
        _compute_if_stale()
        stats = cache.stats()
        if since_version and since_version >= stats["version"]:
            return {
                "updated": False,
                "version": stats["version"],
                "cache": stats,
            }
        result = cache.result
        snap = cache.snapshot
        return {
            "updated": True,
            "version": stats["version"],
            "timestamp": snap.timestamp if snap else 0.0,
            "source": snap.source if snap else "unknown",
            "field": asdict(result),
            "cache": stats,
        }

    return router
