"""GET /api/activity/{corp}, /api/sentiment/{corp}, /api/relation-top/{corp} — 인사이트."""
from __future__ import annotations

from fastapi import APIRouter

from ..db import mariadb, neo4j
from ..models import ActivityItem, RelationTop, SentimentPoint
from ..relations import COMPANY_REL_TYPES, PREDICATE_TO_GROUP

router = APIRouter(tags=["insights"])


@router.get("/relation-top/{corp}", response_model=list[RelationTop])
def get_relation_top(corp: str) -> list[RelationTop]:
    """Neo4j 그래프에서 evidence_count 가중치 상위 5 관계 반환 (그룹 중복 허용, 자기루프 제외)."""
    cypher = (
        "MATCH (c:Organization {corp_code: $corp})-[r]-(o:Organization) "
        "WHERE r.extracted_by = 'claude' AND type(r) IN $types "
        "RETURN type(r) AS rtype, "
        "coalesce(o.corp_code, o.ext_id) AS nodeId, "
        "coalesce(o.name, o.corp_code, o.ext_id) AS target, "
        "coalesce(o.corp_code, o.ext_id) AS rawId, "
        "toInteger(coalesce(r.evidence_count, 1)) AS ec"
    )
    with neo4j().session() as session:
        result = session.run(cypher, corp=corp, types=COMPANY_REL_TYPES)
        rows = [
            {
                "rtype": rec["rtype"],
                "nodeId": rec["nodeId"],
                "target": rec["target"],
                "rawId": rec["rawId"],
                "ec": rec["ec"],
            }
            for rec in result
        ]

    # 자기루프 제거
    rows = [r for r in rows if r["rawId"] != corp]

    if not rows:
        return []

    rows.sort(key=lambda x: x["ec"], reverse=True)
    top = rows[:5]

    return [
        RelationTop(
            nodeId=r["nodeId"],
            target=r["target"],
            group=PREDICATE_TO_GROUP.get(r["rtype"], "etc"),
            predicate=r["rtype"],
            evidenceCount=r["ec"],
        )
        for r in top
    ]


@router.get("/activity/{corp}", response_model=list[ActivityItem])
def get_activity(corp: str) -> list[ActivityItem]:
    # 1) Neo4j 에서 관계 수집
    cypher = (
        "MATCH (c:Organization {corp_code: $corp})-[r]-(o:Organization) "
        "WHERE r.extracted_by = 'claude' AND type(r) IN $types "
        "RETURN type(r) AS rtype, "
        "coalesce(o.name, o.corp_code, o.ext_id) AS target, "
        "toInteger(coalesce(r.evidence_count, 1)) AS ec, "
        "r.doc_ids AS doc_ids"
    )
    with neo4j().session() as session:
        result = session.run(cypher, corp=corp, types=COMPANY_REL_TYPES)
        rels = [
            {
                "rtype": rec["rtype"],
                "target": rec["target"],
                "ec": rec["ec"],
                "doc_ids": rec["doc_ids"] or [],
            }
            for rec in result
        ]

    if not rels:
        return []

    # 2) 모든 doc_ids 모아 MariaDB 에서 날짜 한 번에 조회
    all_doc_ids: list[str] = []
    for rel in rels:
        all_doc_ids.extend(rel["doc_ids"])
    all_doc_ids = list(set(all_doc_ids))

    doc_date: dict[str, str] = {}
    if all_doc_ids:
        placeholders = ",".join(["%s"] * len(all_doc_ids))
        conn = mariadb()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT doc_id, DATE_FORMAT(MAX(ts), '%%Y-%%m-%%d') AS d "
                    f"FROM document_unified WHERE doc_id IN ({placeholders}) GROUP BY doc_id",
                    tuple(all_doc_ids),
                )
                for row in cur.fetchall():
                    doc_date[row["doc_id"]] = row["d"]
        except Exception:
            pass
        finally:
            conn.close()

    # 3) 관계별 대표 날짜·docId 결정
    items: list[ActivityItem] = []
    for rel in rels:
        best_date: str | None = None
        best_doc: str | None = None
        for did in rel["doc_ids"]:
            d = doc_date.get(did)
            if d and (best_date is None or d > best_date):
                best_date = d
                best_doc = did
        group = PREDICATE_TO_GROUP.get(rel["rtype"], "etc")
        items.append(
            ActivityItem(
                date=best_date or "",
                group=group,
                predicate=rel["rtype"],
                target=rel["target"],
                evidenceCount=rel["ec"],
                docId=best_doc,
            )
        )

    items.sort(key=lambda x: x.date, reverse=True)
    return items[:40]


@router.get("/sentiment/{corp}", response_model=list[SentimentPoint])
def get_sentiment(corp: str) -> list[SentimentPoint]:
    conn = mariadb()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DATE_FORMAT(date, '%%Y-%%m-%%d') d, pos, neg, neu "
                "FROM sentiment_daily WHERE corp_code=%s ORDER BY date",
                (corp,),
            )
            rows = cur.fetchall()
        return [SentimentPoint(date=r["d"], pos=r["pos"], neg=r["neg"], neu=r["neu"]) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()
