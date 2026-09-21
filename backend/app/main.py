"""FastAPI entrypoint for the blast-furnace thermal inversion service."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api_router import router

app = FastAPI(title="Blast Furnace Thermal Field Inversion", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
def warmup() -> None:
    # Build FEM operators and run one inversion so the first request is fast
    from .inversion_service import get_service

    get_service().get()
