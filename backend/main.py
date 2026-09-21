"""高炉炉温场反演系统 —— FastAPI 应用入口。

启动方式：
    cd backend
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

InfluxDB 通过环境变量配置（缺省时自动使用模拟数据源）：
    INFLUX_URL / INFLUX_TOKEN / INFLUX_ORG / INFLUX_BUCKET
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api_router import InversionCache, build_router
from fem_solver import FemThermalSolver
from influx_client import InfluxThermocoupleClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

app = FastAPI(title="Blast Furnace Thermal Inversion", version="1.0.0")

# 前端 Vite 开发服务器跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 共享组件：InfluxDB 客户端、FEM 求解器、反演缓存
influx_client = InfluxThermocoupleClient()
fem_solver = FemThermalSolver(radius=5.0, n_rings=14, n_angles=64, grid_n=61)
inversion_cache = InversionCache()

app.include_router(build_router(influx_client, fem_solver, inversion_cache))


@app.get("/")
def root() -> dict:
    return {
        "service": "blast-furnace-thermal-inversion",
        "docs": "/docs",
        "endpoints": [
            "/api/health",
            "/api/thermal/raw",
            "/api/thermal/field",
        ],
    }
