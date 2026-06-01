"""POLARIS 백엔드 — 공시 GraphRAG 에이전트 (스캐폴드).

현재: 헬스체크 + 3-DB 연결 상태. 이후 GraphRAG 에이전트 엔드포인트를 여기 추가.
실행: uv run uvicorn app.main:app --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import mariadb_conn, neo4j, qdrant

app = FastAPI(title="POLARIS Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/db/status")
def db_status():
    """3-DB 연결 상태 (배포·셋업 점검용)."""
    out: dict[str, str] = {}

    try:
        with mariadb_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        out["mariadb"] = "ok"
    except Exception as e:  # noqa: BLE001
        out["mariadb"] = f"error: {e}"

    try:
        with neo4j().session() as s:
            s.run("RETURN 1").single()
        out["neo4j"] = "ok"
    except Exception as e:  # noqa: BLE001
        out["neo4j"] = f"error: {e}"

    try:
        qdrant().get_collections()
        out["qdrant"] = "ok"
    except Exception as e:  # noqa: BLE001
        out["qdrant"] = f"error: {e}"

    return out
