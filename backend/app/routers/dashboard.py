"""GET /api/dashboard/{corp} — 멘션 추이(mention_daily) + 관계 TOP(뉴스엣지 evidence_count).

감성·연관어는 향후(null). 멘션·관계 없는 회사(SK·한미)는 빈 배열 → 화면 빈 상태.
"""
from __future__ import annotations

from fastapi import APIRouter

from ..db import mariadb_conn, neo4j
from ..models import MentionPoint, RelationTopItem, TrendData
from ..relations import COMPANY_REL_TYPES, PREDICATE_TO_GROUP

router = APIRouter(tags=["dashboard"])

REL_TOP = """
MATCH (c:Organization {corp_code: $corp})-[r]-(o:Organization)
WHERE r.extracted_by = 'claude' AND type(r) IN $types
RETURN type(r) AS rtype,
       coalesce(o.name, o.corp_code, o.ext_id) AS target,
       toFloat(coalesce(r.evidence_count, 1)) AS weight
ORDER BY weight DESC
LIMIT 6
"""


@router.get("/dashboard/{corp}", response_model=TrendData)
def dashboard(corp: str):
    with mariadb_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT DATE_FORMAT(date, '%%Y-%%m-%%d') AS date, mention_cnt AS count "
            "FROM mention_daily WHERE corp_code = %s AND source_type = 'news' ORDER BY date",
            (corp,),
        )
        mentions = [MentionPoint(date=r["date"], count=r["count"]) for r in cur.fetchall()]

    with neo4j().session() as s:
        rows = s.run(REL_TOP, corp=corp, types=COMPANY_REL_TYPES).data()
    rel_top = [
        RelationTopItem(group=PREDICATE_TO_GROUP.get(r["rtype"], "partner"),
                        target=r["target"], weight=r["weight"])
        for r in rows
    ]
    return TrendData(mentions=mentions, relationTop=rel_top)
