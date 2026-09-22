"""InfluxDB 数据访问层。

负责从 InfluxDB 拉取 32 支热电偶的时序温度数据。
未配置 INFLUX_URL 时自动切换为 MockInfluxClient，生成物理合理的
模拟数据，便于前后端联调与演示。
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from .config import settings


@dataclass
class SensorReading:
    """某一时刻全部热电偶的快照。"""

    timestamp: float                      # 数据时间戳 (epoch 秒)
    values: np.ndarray                    # shape (n_levels, n_azimuth), 单位 °C


class InfluxClient:
    """封装 influxdb-client 的查询逻辑。"""

    def __init__(self) -> None:
        from influxdb_client import InfluxDBClient

        self._client = InfluxDBClient(
            url=settings.influx_url,
            token=settings.influx_token,
            org=settings.influx_org,
        )
        self._query_api = self._client.query_api()

    def fetch_latest(self, window_seconds: int) -> Optional[SensorReading]:
        """查询最近 window_seconds 内每支热电偶的最新值。"""
        flux = (
            f'from(bucket: "{settings.influx_bucket}")'
            f"|> range(start: -{window_seconds}s)"
            f'|> filter(fn: (r) => r._measurement == "{settings.influx_measurement}")'
            f"|> filter(fn: (r) => r._field == \"temperature\")"
            f"|> last()"
        )
        tables = self._query_api.query(flux, org=settings.influx_org)
        values = np.full((settings.n_levels, settings.n_azimuth), np.nan)
        latest_ts = 0.0
        for table in tables:
            for record in table.records:
                level = int(record.values.get("level", 0))
                azimuth = int(record.values.get("azimuth", 0))
                if 0 <= level < settings.n_levels and 0 <= azimuth < settings.n_azimuth:
                    values[level, azimuth] = float(record.get_value())
                    latest_ts = max(latest_ts, record.get_time().timestamp())
        if np.isnan(values).all():
            return None
        # 个别缺测点用同层均值填补，避免反演矩阵奇异
        for lv in range(settings.n_levels):
            row = values[lv]
            if np.isnan(row).any():
                fill = np.nanmean(row) if not np.isnan(row).all() else settings.ambient_temp
                row[np.isnan(row)] = fill
        return SensorReading(timestamp=latest_ts, values=values)

    def close(self) -> None:
        self._client.close()


class MockInfluxClient:
    """模拟数据源: 构造一个带热点漂移的炉内温度场，正演到热电偶位置。

    数据按 5 秒粒度分桶: 同一桶内多次拉取返回相同时间戳与数值，
    用于演示缓存命中与增量更新行为。
    """

    BUCKET_SECONDS = 5

    def fetch_latest(self, window_seconds: int) -> SensorReading:
        bucket = int(time.time() // self.BUCKET_SECONDS)
        ts = float(bucket * self.BUCKET_SECONDS)
        rng = np.random.default_rng(bucket)  # 同桶内噪声可复现
        n_az = settings.n_azimuth
        angles = np.arange(n_az) * 2.0 * math.pi / n_az
        values = np.zeros((settings.n_levels, n_az))
        # 两个缓慢移动的周向热点，模拟炉内气流偏行
        phase = [0.02 * bucket, 2.4 + 0.013 * bucket]
        for lv in range(settings.n_levels):
            # 各层基础壁温不同(炉腹高、炉喉低)
            row = np.full(n_az, 420.0 - 45.0 * lv)
            for k, amp in enumerate((55.0, 30.0)):
                row += amp * np.cos(angles - phase[k] - 0.3 * lv)
            row += rng.normal(0.0, 1.5, n_az)  # 测量噪声
            values[lv] = row
        return SensorReading(timestamp=ts, values=values)


def create_client():
    """工厂函数: 有配置用真实 InfluxDB，否则用 Mock。"""
    if settings.use_mock:
        return MockInfluxClient()
    return InfluxClient()
