"""反演结果缓存与增量更新。

缓存策略:
  1. 以数据时间戳为版本号，传感器数据未更新时直接命中缓存，
     不重复执行有限元反演;
  2. 数据更新时做增量反演——以上一时刻的内表面温度解作为
     时序正则化先验，仅求解增量变化，保证相邻帧温度场连续;
  3. 前端通过 since 参数携带已持有的数据版本，服务端返回
     updated=false 时前端跳过重渲染。
"""

from __future__ import annotations

import threading
from typing import Dict, Optional

from .config import settings
from .fem_solver import FemSolver, InversionResult
from .influx_client import SensorReading, create_client


class InversionCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._solver = FemSolver()
        self._client = create_client()
        self._data_ts: float = 0.0                    # 当前缓存对应的数据版本
        self._reading: Optional[SensorReading] = None  # 最近一次传感器快照
        self._results: Dict[int, InversionResult] = {} # level -> 反演结果
        self.reg_lambda = settings.reg_lambda
        self.reg_mu = settings.reg_mu

    # ------------------------------------------------------------------ #
    def _refresh_if_needed(self) -> bool:
        """拉取新数据；有更新则对所有层做增量反演。返回是否有更新。"""
        reading = self._client.fetch_latest(settings.poll_window_seconds)
        if reading is None:
            return False
        if self._reading is not None and reading.timestamp <= self._data_ts:
            return False  # 数据未变，命中缓存

        for level in range(settings.n_levels):
            prev = self._results[level].inner_temp if level in self._results else None
            self._results[level] = self._solver.invert(
                level=level,
                sensor_values=reading.values[level],
                timestamp=reading.timestamp,
                prev_inner=prev,
                reg_lambda=self.reg_lambda,
                reg_mu=self.reg_mu,
            )
        self._reading = reading
        self._data_ts = reading.timestamp
        return True

    # ------------------------------------------------------------------ #
    def get_field(self, level: int, since: float = 0.0) -> dict:
        """获取某层温度场；since 为前端已持有的数据版本。"""
        with self._lock:
            self._refresh_if_needed()
            result = self._results.get(level)
            if result is None:
                return {"updated": False, "level": level, "timestamp": self._data_ts}
            if since and result.timestamp <= since:
                return {"updated": False, "level": level, "timestamp": result.timestamp}
            return {
                "updated": True,
                "level": level,
                "timestamp": result.timestamp,
                "r": result.r.tolist(),
                "theta": result.theta.tolist(),
                "field": result.field.tolist(),
                "inner_temp": result.inner_temp.tolist(),
                "sensor_fit": result.sensor_fit.tolist(),
                "residual": result.residual,
            }

    def get_overview(self) -> dict:
        """各层统计概览，供控制面板显示。"""
        with self._lock:
            self._refresh_if_needed()
            levels = []
            for level in range(settings.n_levels):
                res = self._results.get(level)
                if res is None:
                    continue
                levels.append({
                    "level": level,
                    "inner_avg": float(res.inner_temp.mean()),
                    "inner_max": float(res.inner_temp.max()),
                    "inner_min": float(res.inner_temp.min()),
                    "residual": res.residual,
                })
            return {
                "timestamp": self._data_ts,
                "levels": levels,
                "sensor_values": (
                    self._reading.values.tolist() if self._reading is not None else None
                ),
                "reg_lambda": self.reg_lambda,
                "reg_mu": self.reg_mu,
                "data_source": "mock" if settings.use_mock else "influxdb",
            }

    def update_params(self, reg_lambda: Optional[float], reg_mu: Optional[float]) -> dict:
        """更新正则化参数并强制下一帧重新反演。"""
        with self._lock:
            if reg_lambda is not None:
                self.reg_lambda = float(reg_lambda)
            if reg_mu is not None:
                self.reg_mu = float(reg_mu)
            self._data_ts = 0.0  # 使缓存失效，强制重算
        return {"reg_lambda": self.reg_lambda, "reg_mu": self.reg_mu}


cache = InversionCache()
