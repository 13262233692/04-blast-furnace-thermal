"""Inversion orchestration: caching and incremental updates.

The service polls the thermocouple data source on demand and keeps the most
recent inversion in memory. Incremental behaviour:

* If the newest data timestamp matches the cached result, the cache is
  returned verbatim (no recomputation).
* If newer data exists, the inversion is warm-started from the previous
  Fourier solution via a temporal regularisation term, which both stabilises
  the estimate and keeps consecutive frames coherent.

Clients pass ``since=<timestamp>``; when nothing changed the API answers with
``updated=false`` and no field payload, saving bandwidth.
"""
from __future__ import annotations

import threading
from typing import Optional, Tuple

import numpy as np

from .fem_solver import FemInversionSolver, InversionResult
from .influx_client import build_client


class InversionService:
    def __init__(self) -> None:
        self._client = build_client()
        self._solver = FemInversionSolver()
        self._lock = threading.Lock()
        self._cached: Optional[InversionResult] = None
        self._g_prev: Optional[np.ndarray] = None
        self._reg_lambda: Optional[float] = None

    def set_reg_lambda(self, value: Optional[float]) -> None:
        with self._lock:
            self._reg_lambda = value

    def get(self, force: bool = False) -> Tuple[InversionResult, bool]:
        """Return (result, recomputed). Recomputes only on fresh data."""
        reading = self._client.latest()
        with self._lock:
            fresh = (
                self._cached is None
                or force
                or reading.timestamp > self._cached.timestamp + 1e-6
            )
            if not fresh:
                return self._cached, False
            result, g = self._solver.solve(
                tc_values=reading.values,
                timestamp=reading.timestamp,
                g_prev=None if (force or self._g_prev is None) else self._g_prev,
                reg_lambda=self._reg_lambda,
            )
            self._cached = result
            self._g_prev = g
            return result, True

    def latest_timestamp(self) -> Optional[float]:
        with self._lock:
            return None if self._cached is None else self._cached.timestamp


_service: Optional[InversionService] = None


def get_service() -> InversionService:
    global _service
    if _service is None:
        _service = InversionService()
    return _service
