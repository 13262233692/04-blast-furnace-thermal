"""InfluxDB 数据接入层。

负责从 InfluxDB 拉取 32 支热电偶的最新温度；当 `INFLUX_MOCK=true`
或连接失败时，自动降级为内置炉温模拟器，保证系统可独立运行。
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass

import numpy as np

from .config import AppConfig

logger = logging.getLogger(__name__)

SENSOR_IDS = [f"tc_{i:02d}" for i in range(1, 33)]  # tc_01 .. tc_32


@dataclass
class SensorFrame:
    """一帧热电偶采样数据。"""
    timestamp: float                 # 采样时间戳（秒）
    values: np.ndarray               # shape (32,)，与 SENSOR_IDS 对齐
    source: str                      # "influxdb" | "mock"

    def as_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "sensor_ids": SENSOR_IDS,
            "values": [round(float(v), 3) for v in self.values],
            "source": self.source,
        }


class MockFurnaceSimulator:
    """高炉炉温模拟器：生成带漂移与噪声的 32 通道炉壁温度。

    热面温度沿高度呈炉腹-炉腰-炉身分布，随时间缓慢波动，
    经一维导热衰减后得到各埋深处热电偶读数。
    """

    def __init__(self, config: AppConfig):
        geo = config.geometry
        self._depths = np.asarray(geo.tc_depths, dtype=float)
        rows = geo.tc_rows
        self._heights = np.linspace(
            geo.z_bottom + 0.75, geo.z_top - 0.75, rows
        )
        self._t0 = time.time()

    def _hot_face_profile(self, t: float) -> np.ndarray:
        z = self._heights
        base = 950.0 + 350.0 * np.exp(-((z - 4.5) / 2.2) ** 2)   # 炉腹高温区
        base += 120.0 * np.exp(-((z - 9.0) / 1.8) ** 2)          # 炉身中部
        drift = 40.0 * math.sin(t / 300.0) + 15.0 * np.sin(t / 47.0 + z)
        return base + drift

    def read(self) -> SensorFrame:
        t = time.time() - self._t0
        hot = self._hot_face_profile(t)                          # (rows,)
        k, thick = 2.5, 1.2
        ambient = 35.0
        frames = []
        for depth in self._depths:
            # 稳态一维导热近似：线性衰减到炉壳侧
            decay = 1.0 - depth / thick
            temp = ambient + (hot - ambient) * decay
            frames.append(temp)
        values = np.stack(frames, axis=1).reshape(-1)            # (rows*cols,)
        values += np.random.normal(0.0, 0.8, size=values.shape)  # 测量噪声
        return SensorFrame(timestamp=time.time(), values=values, source="mock")


class InfluxClient:
    """InfluxDB 2.x 客户端封装，带 mock 降级。"""

    def __init__(self, config: AppConfig):
        self._cfg = config.influx
        self._mock = MockFurnaceSimulator(config)
        self._client = None
        self._query_api = None
        if not self._cfg.mock:
            self._try_connect()

    def _try_connect(self) -> None:
        try:
            from influxdb_client import InfluxDBClient

            self._client = InfluxDBClient(
                url=self._cfg.url,
                token=self._cfg.token,
                org=self._cfg.org,
                timeout=self._cfg.timeout_ms,
            )
            self._query_api = self._client.query_api()
            logger.info("InfluxDB connected: %s", self._cfg.url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("InfluxDB unavailable, fallback to mock: %s", exc)
            self._client = None
            self._query_api = None

    @property
    def is_live(self) -> bool:
        return self._query_api is not None

    def fetch_latest(self) -> SensorFrame:
        """拉取 32 支热电偶最新一帧数据。"""
        if not self.is_live:
            return self._mock.read()
        try:
            return self._fetch_latest_influx()
        except Exception as exc:  # noqa: BLE001
            logger.warning("InfluxDB query failed, fallback to mock: %s", exc)
            return self._mock.read()

    def _fetch_latest_influx(self) -> SensorFrame:
        flux = f'''
from(bucket: "{self._cfg.bucket}")
  |> range(start: -5m)
  |> filter(fn: (r) => r._measurement == "{self._cfg.measurement}")
  |> filter(fn: (r) => r._field == "temperature")
  |> last()
'''
        tables = self._query_api.query(flux, org=self._cfg.org)
        latest: dict[str, tuple[float, float]] = {}
        for table in tables:
            for record in table.records:
                sid = record.values.get("sensor_id", "")
                ts = record.get_time().timestamp()
                if sid not in latest or ts > latest[sid][0]:
                    latest[sid] = (ts, float(record.get_value()))
        values = np.full(len(SENSOR_IDS), np.nan)
        timestamps = []
        for i, sid in enumerate(SENSOR_IDS):
            if sid in latest:
                timestamps.append(latest[sid][0])
                values[i] = latest[sid][1]
        if np.isnan(values).any():
            raise RuntimeError("missing thermocouple channels in InfluxDB")
        return SensorFrame(
            timestamp=max(timestamps) if timestamps else time.time(),
            values=values,
            source="influxdb",
        )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
