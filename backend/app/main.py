"""高炉炉温场反演系统 — FastAPI 入口。

启动：uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api_router import create_router
from .config import load_config
from .fem_solver import FemInversionSolver
from .influx_client import InfluxClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

config = load_config()
app = FastAPI(title="Blast Furnace Thermal Inversion", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    app.state.influx = InfluxClient(config)
    app.state.solver = FemInversionSolver(config)


@app.on_event("shutdown")
def shutdown() -> None:
    app.state.influx.close()


app.include_router(create_router(sensor_ttl_s=config.cache.sensor_ttl_s))
