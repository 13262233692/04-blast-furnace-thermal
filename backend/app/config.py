"""Central configuration, overridable via environment variables."""
from __future__ import annotations

import os


class Settings:
    # InfluxDB connection
    influx_url: str = os.getenv("INFLUX_URL", "http://localhost:8086")
    influx_token: str = os.getenv("INFLUX_TOKEN", "")
    influx_org: str = os.getenv("INFLUX_ORG", "steel-plant")
    influx_bucket: str = os.getenv("INFLUX_BUCKET", "furnace")
    influx_measurement: str = os.getenv("INFLUX_MEASUREMENT", "thermocouple")
    # Fall back to a synthetic data generator when no real InfluxDB is reachable
    use_mock: bool = os.getenv("USE_MOCK_INFLUX", "true").lower() == "true"

    # Furnace geometry (metres) and thermocouple layout
    n_thermocouples: int = 32
    r_inner: float = 4.5        # hot-face (inner wall) radius
    r_tc: float = 5.1           # thermocouple embedment radius
    r_outer: float = 5.8        # outer shell radius

    # FEM mesh resolution
    mesh_nr: int = 14           # radial layers in the wall
    mesh_nt: int = 96           # angular divisions

    # Inversion regularisation
    reg_lambda: float = float(os.getenv("REG_LAMBDA", "5e-3"))
    temporal_lambda: float = float(os.getenv("TEMPORAL_LAMBDA", "2e-2"))
    n_fourier_modes: int = 8    # parameterisation of the hot-face temperature

    # Heatmap output grid
    grid_n: int = 121

    # Query window for the latest thermocouple snapshot
    query_window_s: int = int(os.getenv("QUERY_WINDOW_S", "120"))


settings = Settings()
