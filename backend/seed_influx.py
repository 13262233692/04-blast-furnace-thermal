"""数据采集模拟器：以固定周期向 InfluxDB 写入 32 支热电偶温度。

用于在没有真实 DCS/采集网关时构造端到端数据链路：
    export INFLUX_URL=http://localhost:8086
    export INFLUX_TOKEN=<your-token>
    export INFLUX_ORG=steel
    export INFLUX_BUCKET=blast_furnace
    python seed_influx.py --interval 5
"""

from __future__ import annotations

import argparse
import logging
import os
import time

from influx_client import MockThermocoupleGenerator, N_SENSORS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("seed_influx")


def main() -> None:
    parser = argparse.ArgumentParser(description="热电偶数据采集模拟器")
    parser.add_argument("--interval", type=float, default=5.0, help="写入周期（秒）")
    args = parser.parse_args()

    from influxdb_client import InfluxDBClient, Point
    from influxdb_client.client.write_api import SYNCHRONOUS

    client = InfluxDBClient(
        url=os.getenv("INFLUX_URL", "http://localhost:8086"),
        token=os.getenv("INFLUX_TOKEN", ""),
        org=os.getenv("INFLUX_ORG", "steel"),
    )
    bucket = os.getenv("INFLUX_BUCKET", "blast_furnace")
    write_api = client.write_api(write_options=SYNCHRONOUS)
    gen = MockThermocoupleGenerator(report_interval=args.interval)

    logger.info("开始向 %s/%s 写入 %d 支热电偶数据，周期 %.1fs",
                client.url, bucket, N_SENSORS, args.interval)
    while True:
        snap = gen.latest()
        points = [
            Point("thermocouple")
            .tag("sensor_id", f"TC{k:02d}")
            .field("temperature", temp)
            .time(int(snap.timestamp * 1e9))
            for k, temp in enumerate(snap.temps)
        ]
        write_api.write(bucket=bucket, record=points)
        logger.info("已写入 %d 点, ts=%.0f, 范围 %.1f~%.1f ℃",
                    len(points), snap.timestamp, min(snap.temps), max(snap.temps))
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
