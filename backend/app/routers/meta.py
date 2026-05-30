"""헬스체크 + 3DB 연결 상태 — 프론트 연동/배포 점검용."""
from __future__ import annotations

from fastapi import APIRouter

from ..db import mariadb, neo4j, qdrant

router = APIRouter(tags=["meta"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/db/status")
def db_status():
    """3DB 각각 연결되는지 확인 (배포 후 점검용)."""
    out: dict[str, str] = {}
    try:
        conn = mariadb(); cur = conn.cursor(); cur.execute("SELECT 1"); cur.fetchone(); conn.close()
        out["mariadb"] = "ok"
    except Exception as e:
        out["mariadb"] = f"fail: {str(e)[:80]}"
    try:
        qdrant().get_collections()
        out["qdrant"] = "ok"
    except Exception as e:
        out["qdrant"] = f"fail: {str(e)[:80]}"
    try:
        with neo4j().session() as s:
            s.run("RETURN 1").single()
        out["neo4j"] = "ok"
    except Exception as e:
        out["neo4j"] = f"fail: {str(e)[:80]}"
    return out
