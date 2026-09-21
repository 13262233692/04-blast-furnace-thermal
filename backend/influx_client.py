"""InfluxDB 时序数据接入层。

负责从 InfluxDB 拉取高炉炉壁 32 支热电偶的温度数据。
当 InfluxDB 不可达（或未配置）时自动降级为内置模拟数据源，
保证反演流水线与前端联调随时可用。
"""

from __future__ import annotations

import logging
import math
import os
import random
import time
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger("influx_client")

N_SENSORS = 32  # 炉壁周向均布 32 支热电偶


@dataclass
class SensorSnapshot:
    """一个时刻的 32 支热电偶读数。"""

    timestamp: float  # 数据时间戳（秒，来自 InfluxDB 的 _time）
    temps: List[float]  # 长度 32，单位 ℃
    source: str = "influxdb"  # influxdb / mock


class MockThermocoupleGenerator:
    """模拟数据源：带周向热点、缓慢漂移与测量噪声的炉壁温度。

    按 report_interval 对齐时间戳，模拟现场 DCS 固定周期上报：
    同一周期内多次拉取返回相同快照，便于验证缓存与增量更新。
    """

    def __init__(self, n_sensors: int = N_SENSORS, report_interval: float = 5.0) -> None:
        self.n = n_sensors
        self.report_interval = report_interval
        self._t0 = time.time()

    def latest(self) -> SensorSnapshot:
        now = time.time()
        ts = now - (now % self.report_interval)  # 周期对齐的时间戳
        t = ts - self._t0
        rng = random.Random(int(ts))  # 同一周期内噪声可复现
        # 两个周向热点缓慢移动，模拟炉内气流分布偏析
        hot1 = 2.0 * math.pi * (0.15 + 0.02 * math.sin(t / 300.0))
        hot2 = 2.0 * math.pi * (0.65 + 0.03 * math.cos(t / 420.0))
        drift = 12.0 * math.sin(t / 600.0)
        temps = []
        for k in range(self.n):
            theta = 2.0 * math.pi * k / self.n
            base = 320.0 + drift
            peak1 = 55.0 * math.exp(-((math.atan2(math.sin(theta - hot1), math.cos(theta - hot1))) ** 2) / 0.18)
            peak2 = 35.0 * math.exp(-((math.atan2(math.sin(theta - hot2), math.cos(theta - hot2))) ** 2) / 0.30)
            noise = rng.gauss(0.0, 0.8)
            temps.append(round(base + peak1 + peak2 + noise, 2))
        return SensorSnapshot(timestamp=ts, temps=temps, source="mock")


class InfluxThermocoupleClient:
    """从 InfluxDB 查询热电偶温度；失败时降级到模拟源。

    期望的 InfluxDB 数据结构（measurement: thermocouple）：
        tag:   sensor_id = "TC00" .. "TC31"
        field: temperature (float, ℃)
    """

    def __init__(
        self,
        url: Optional[str] = None,
        token: Optional[str] = None,
        org: Optional[str] = None,
        bucket: Optional[str] = None,
        measurement: str = "thermocouple",
        n_sensors: int = N_SENSORS,
    ) -> None:
        self.url = url or os.getenv("INFLUX_URL", "http://localhost:8086")
        self.token = token or os.getenv("INFLUX_TOKEN", "")
        self.org = org or os.getenv("INFLUX_ORG", "steel")
        self.bucket = bucket or os.getenv("INFLUX_BUCKET", "blast_furnace")
        self.measurement = measurement
        self.n = n_sensors
        self._query_api = None
        self._mock = MockThermocoupleGenerator(n_sensors)
        self._last_snapshot: Optional[SensorSnapshot] = None
        self._connect()

    def _connect(self) -> None:
        if not self.token:
            logger.warning("未配置 INFLUX_TOKEN，使用模拟数据源")
            return
        try:
            from influxdb_client import InfluxDBClient

            client = InfluxDBClient(url=self.url, token=self.token, org=self.org, timeout=5000)
            self._query_api = client.query_api()
            logger.info("已连接 InfluxDB: %s bucket=%s", self.url, self.bucket)
        except Exception as exc:  # noqa: BLE001
            logger.warning("InfluxDB 连接失败，降级为模拟数据源: %s", exc)
            self._query_api = None

    def _query_window(self, start: str) -> Optional[SensorSnapshot]:
        """查询时间窗内每支热电偶的最新值，聚合为一个快照。"""
        flux = (
            f'from(bucket: "{self.bucket}")\n'
            f"  |> range(start: {start})\n"
            f'  |> filter(fn: (r) => r._measurement == "{self.measurement}")\n'
            f'  |> filter(fn: (r) => r._field == "temperature")\n'
            f"  |> last()"
        )
        tables = self._query_api.query(flux, org=self.org)
        temps: List[Optional[float]] = [None] * self.n
        latest_ts = 0.0
        for table in tables:
            for record in table.records:
                sid = record.values.get("sensor_id", "")
                if sid.startswith("TC"):
                    idx = int(sid[2:])
                    if 0 <= idx < self.n:
                        temps[idx] = float(record.get_value())
                        latest_ts = max(latest_ts, record.get_time().timestamp())
        if latest_ts == 0.0 or any(v is None for v in temps):
            return None
        return SensorSnapshot(timestamp=latest_ts, temps=[float(v) for v in temps])

    def fetch_latest(self) -> SensorSnapshot:
        """拉取最新快照。增量更新语义：时间戳未变时返回缓存快照，
        上层据此判断是否需要重新反演。"""
        if self._query_api is not None:
            try:
                snap = self._query_window(start="-5m")
                if snap is not None:
                    self._last_snapshot = snap
                    return snap
                logger.warning("InfluxDB 查询无完整数据，沿用上一快照或模拟源")
            except Exception as exc:  # noqa: BLE001
                logger.warning("InfluxDB 查询失败: %s", exc)
        if self._last_snapshot is not None and self._last_snapshot.source == "influxdb":
            return self._last_snapshot
        snap = self._mock.latest()
        self._last_snapshot = snap
        return snap

    def status(self) -> dict:
        return {
            "backend": "influxdb" if self._query_api is not None else "mock",
            "url": self.url,
            "bucket": self.bucket,
            "n_sensors": self.n,
        }
