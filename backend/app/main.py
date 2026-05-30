"""POLARIS API 진입점 (FastAPI).

실행: uv run uvicorn app.main:app --reload   (또는 pip 설치 후)
문서: http://localhost:8000/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import briefing, changes, company, dashboard, digest, evidence, fundamentals, graph, insights, ir, market, meta, news, node, node_evidence
from .routers import track
from .scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="POLARIS API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router, prefix="/api")
app.include_router(graph.router, prefix="/api")
app.include_router(node.router, prefix="/api")
app.include_router(node_evidence.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(company.router, prefix="/api")
app.include_router(fundamentals.router, prefix="/api")
app.include_router(evidence.router, prefix="/api")
app.include_router(news.router, prefix="/api")
app.include_router(insights.router, prefix="/api")
app.include_router(market.router, prefix="/api")
app.include_router(digest.router, prefix="/api")
app.include_router(briefing.router, prefix="/api")
app.include_router(track.router, prefix="/api")
app.include_router(changes.router, prefix="/api")
app.include_router(ir.router, prefix="/api")


@app.get("/")
def root():
    return {"service": "POLARIS API", "docs": "/docs", "health": "/api/health"}
