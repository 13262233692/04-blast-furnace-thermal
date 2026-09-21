"""Thermocouple data access layer.

Wraps InfluxDB v2 queries. When ``settings.use_mock`` is set (or the real
server is unreachable) a synthetic generator produces physically plausible
readings so the whole pipeline stays demonstrable offline.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import List, Optional

from .config import settings


@dataclass
class ThermocoupleReading:
    timestamp: float            # epoch seconds of the snapshot
    values: List[float]         # one temperature per thermocouple (degC)


class MockInfluxClient:
    """Generates drifting hot-spot readings for 32 wall thermocouples.

    Snapshots are quantised to ``period`` seconds so repeated polls inside
    the same window return an identical timestamp, mirroring how ``last()``
    behaves against a real InfluxDB bucket between writes.
    """

    def __init__(self, period: float = 2.0) -> None:
        self.n = settings.n_thermocouples
        self._t0 = time.time()
        self.period = period

    def latest(self) -> ThermocoupleReading:
        now = time.time()
        ts = now - (now % self.period)
        t = ts - self._t0
        # Two hot spots slowly orbiting the circumference plus noise-like ripple
        c1 = (0.6 * t) % (2 * math.pi)
        c2 = (math.pi + 0.25 * t) % (2 * math.pi)
        values = []
        for i in range(self.n):
            theta = 2 * math.pi * i / self.n
            d1 = math.atan2(math.sin(theta - c1), math.cos(theta - c1))
            d2 = math.atan2(math.sin(theta - c2), math.cos(theta - c2))
            temp = (
                320.0
                + 90.0 * math.exp(-(d1 ** 2) / 0.35)
                + 55.0 * math.exp(-(d2 ** 2) / 0.6)
                + 6.0 * math.sin(3 * theta + 0.8 * t)
                + 2.0 * math.sin(11 * theta + 2.3 * t)
            )
            values.append(round(temp, 3))
        return ThermocoupleReading(timestamp=ts, values=values)

    def close(self) -> None:  # interface parity
        pass


class InfluxClient:
    """Pulls the newest per-thermocouple snapshot from InfluxDB v2."""

    def __init__(self) -> None:
        from influxdb_client import InfluxDBClient  # deferred import

        self._client = InfluxDBClient(
            url=settings.influx_url,
            token=settings.influx_token,
            org=settings.influx_org,
            timeout=10_000,
        )
        self._query_api = self._client.query_api()

    def latest(self) -> ThermocoupleReading:
        flux = f"""
from(bucket: "{settings.influx_bucket}")
  |> range(start: -{settings.query_window_s}s)
  |> filter(fn: (r) => r._measurement == "{settings.influx_measurement}")
  |> filter(fn: (r) => r._field == "temperature")
  |> last()
"""
        tables = self._query_api.query(flux, org=settings.influx_org)
        values: List[Optional[float]] = [None] * settings.n_thermocouples
        latest_ts = 0.0
        for table in tables:
            for record in table.records:
                idx = int(record.values.get("channel", record.values.get("tc_id", 0)))
                if 0 <= idx < settings.n_thermocouples:
                    values[idx] = float(record.get_value())
                    latest_ts = max(latest_ts, record.get_time().timestamp())
        if any(v is None for v in values):
            missing = [i for i, v in enumerate(values) if v is None]
            raise RuntimeError(f"missing thermocouple channels: {missing}")
        return ThermocoupleReading(
            timestamp=latest_ts or time.time(),
            values=[float(v) for v in values],
        )

    def close(self) -> None:
        self._client.close()


def build_client():
    """Factory: real InfluxDB when configured, mock otherwise."""
    if settings.use_mock:
        return MockInfluxClient()
    try:
        client = InfluxClient()
        client.latest()  # connectivity probe
        return client
    except Exception as exc:  # pragma: no cover - depends on external service
        print(f"[influx_client] falling back to mock: {exc}")
        return MockInfluxClient()
