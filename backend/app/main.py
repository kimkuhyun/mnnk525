"""POLARIS API 진입점 (FastAPI).

실행: uv run uvicorn app.main:app --reload   (또는 pip 설치 후)
문서: http://localhost:8000/docs
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import meta

app = FastAPI(title="POLARIS API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router, prefix="/api")
# 화면별 라우터는 여기에 추가:
# app.include_router(dashboard.router, prefix="/api")
# app.include_router(graph.router, prefix="/api")


@app.get("/")
def root():
    return {"service": "POLARIS API", "docs": "/docs", "health": "/api/health"}
