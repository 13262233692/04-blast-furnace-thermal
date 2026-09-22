"""系统配置：InfluxDB 连接、热电偶布局、FEM 网格与反演参数。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class InfluxConfig:
    url: str = os.getenv("INFLUX_URL", "http://localhost:8086")
    token: str = os.getenv("INFLUX_TOKEN", "my-token")
    org: str = os.getenv("INFLUX_ORG", "steel-plant")
    bucket: str = os.getenv("INFLUX_BUCKET", "blast-furnace")
    measurement: str = os.getenv("INFLUX_MEASUREMENT", "thermocouple")
    # mock=true 时无 InfluxDB 也能运行（内置炉温模拟器）
    mock: bool = os.getenv("INFLUX_MOCK", "true").lower() == "true"
    timeout_ms: int = int(os.getenv("INFLUX_TIMEOUT_MS", "5000"))


@dataclass(frozen=True)
class GeometryConfig:
    """炉壁横截面几何（r-z 平面简化为矩形计算域）。"""
    r_inner: float = 0.0        # 热面（炉内侧）半径偏移 m
    r_outer: float = 1.2        # 冷面（炉壳侧）m，壁厚 1.2 m
    z_bottom: float = 0.0       # 炉壁监测段底部 m
    z_top: float = 12.0         # 炉壁监测段顶部 m
    # 32 支热电偶：8 个高度层 x 4 个径向深度
    tc_rows: int = 8
    tc_cols: int = 4
    tc_depths: tuple = (0.15, 0.45, 0.75, 1.05)  # 距热面距离 m


@dataclass(frozen=True)
class FemConfig:
    n_radial: int = 24          # 径向单元数
    n_axial: int = 48           # 轴向单元数
    conductivity: float = 2.5   # 炉衬等效导热系数 W/(m·K)
    h_outer: float = 15.0       # 炉壳外表面对流换热系数 W/(m^2·K)
    t_ambient: float = 35.0     # 环境温度 °C
    reg_lambda: float = 1e-3    # Tikhonov 正则化系数（可被 API 覆盖）


@dataclass(frozen=True)
class CacheConfig:
    result_ttl_s: float = 30.0          # 反演结果缓存 TTL
    sensor_ttl_s: float = 5.0           # 传感器数据缓存 TTL
    incremental_tol: float = 1e-6       # 相对变化小于该值视为无增量


@dataclass(frozen=True)
class AppConfig:
    influx: InfluxConfig = field(default_factory=InfluxConfig)
    geometry: GeometryConfig = field(default_factory=GeometryConfig)
    fem: FemConfig = field(default_factory=FemConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)


def load_config() -> AppConfig:
    return AppConfig()
