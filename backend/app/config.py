import os
from dataclasses import dataclass


@dataclass
class Settings:
    """集中管理运行配置，全部可用环境变量覆盖。"""

    # InfluxDB
    influx_url: str = os.getenv("INFLUX_URL", "")
    influx_token: str = os.getenv("INFLUX_TOKEN", "")
    influx_org: str = os.getenv("INFLUX_ORG", "steel-plant")
    influx_bucket: str = os.getenv("INFLUX_BUCKET", "blast_furnace")
    influx_measurement: str = os.getenv("INFLUX_MEASUREMENT", "thermocouple")

    # 高炉几何与传感器布局: 32 支热电偶 = 4 个轴向层 x 8 个周向方位
    n_levels: int = 4
    n_azimuth: int = 8
    r_inner: float = 4.5        # 炉膛内半径 (m)
    r_outer: float = 5.5        # 炉壁外半径 (m)
    sensor_radius_ratio: float = 0.7  # 热电偶埋入深度(距内表面比例)

    # 炉壁材料与冷却边界
    conductivity: float = 1.8       # 炉衬导热系数 W/(m*K)
    conv_coeff: float = 25.0        # 外壁对流换热系数 W/(m^2*K)
    ambient_temp: float = 60.0      # 环境/冷却介质温度 (°C)

    # 反演正则化参数
    reg_lambda: float = 5e-3        # Tikhonov 平滑正则化
    reg_mu: float = 2e-2            # 时序增量正则化(相对上一时刻解)

    # 轮询与缓存
    poll_window_seconds: int = 300  # 默认拉取最近 5 分钟数据
    cache_ttl_seconds: int = 3600

    @property
    def use_mock(self) -> bool:
        return not self.influx_url


settings = Settings()
