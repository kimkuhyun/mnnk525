"""GET /api/changes/{corp}?days=60 — 관계 변화 감지.

newItems: claude 외부관계 엣지의 최초등장일이 (오늘-days) 이후인 것.
dropped : edge_snapshot 테이블 최근 2 run 비교 → 직전엔 있고 최신엔 없는 엣지.
          테이블 없거나 run < 2 면 빈 배열.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Query

from ..db import mariadb, neo4j
from ..models import ChangeItem, ChangesData
from ..relations import COMPANY_REL_TYPES, PREDICATE_TO_GROUP

router = APIRouter(tags=["changes"])

logger = logging.getLogger(__name__)

# 외부관계 그룹만 newItems 에 포함
_EXTERNAL_GROUPS = {"compete", "supply", "partner", "dispute"}

# Neo4j: corp 의 claude 외부관계 엣지 (doc_ids, evidence_count, predicate, 상대 이름+id)
_NEO_CYPHER = """
MATCH (c:Organization {corp_code: $corp})-[r]-(o:Organization)
WHERE r.extracted_by = 'claude'
  AND type(r) IN $types
RETURN type(r) AS predicate,
       r.doc_ids AS doc_ids,
       coalesce(r.evidence_count, 1) AS evidence_count,
       coalesce(o.name, o.corp_code, o.ext_id) AS target_name,
       coalesce(o.corp_code, o.ext_id) AS target_id
"""


def _min_date_from_mariadb(conn: Any, doc_ids: list[str]) -> str | None:
    """doc_ids 리스트로 document_unified MIN(DATE(ts)) 조회. 없으면 None."""
    if not doc_ids:
        return None
    placeholders = ",".join(["%s"] * len(doc_ids))
    sql = f"SELECT MIN(DATE(ts)) AS min_date FROM document_unified WHERE doc_id IN ({placeholders})"
    with conn.cursor() as cur:
        cur.execute(sql, doc_ids)
        row = cur.fetchone()
    if row and row.get("min_date"):
        return str(row["min_date"])
    return None


def _fetch_new_items(corp: str, cutoff: date) -> list[ChangeItem]:
    """최초등장일이 cutoff 이후인 외부관계 엣지 목록."""
    with neo4j().session() as s:
        rows = s.run(_NEO_CYPHER, corp=corp, types=COMPANY_REL_TYPES).data()

    if not rows:
        return []

    conn = mariadb()
    results: list[ChangeItem] = []
    try:
        for row in rows:
            predicate = row["predicate"]
            grp = PREDICATE_TO_GROUP.get(predicate)
            if grp not in _EXTERNAL_GROUPS:
                continue
            ev = int(row["evidence_count"] or 1)
            if ev < 2:
                continue  # 단일 기사 엣지(노이즈) 제외 — 2건 이상 근거만 '신규'로

            raw_doc_ids = row["doc_ids"] or []
            # Neo4j list -> Python list
            if isinstance(raw_doc_ids, str):
                raw_doc_ids = [raw_doc_ids]
            doc_ids = [str(d) for d in raw_doc_ids if d]

            first_date_str = _min_date_from_mariadb(conn, doc_ids)
            if not first_date_str:
                continue

            try:
                first_date = date.fromisoformat(first_date_str)
            except ValueError:
                continue

            if first_date < cutoff:
                continue

            results.append(ChangeItem(
                group=grp,
                predicate=predicate,
                target=row["target_name"],
                status="new",
                date=first_date_str,
                evidenceCount=ev,
                targetId=str(row.get("target_id") or ""),
            ))
    finally:
        conn.close()

    # 최초등장일 desc, 동일일자 내 근거수 desc → 상위 25
    results.sort(key=lambda x: (x.date, x.evidenceCount), reverse=True)
    return results[:25]


def _fetch_dropped_items(corp: str) -> list[ChangeItem]:
    """edge_snapshot 최근 2 run 비교 → 직전에 있고 최신엔 없는 엣지."""
    try:
        conn = mariadb()
        try:
            with conn.cursor() as cur:
                # 최근 run 2개 조회
                cur.execute(
                    "SELECT DISTINCT run_ts FROM edge_snapshot "
                    "WHERE corp_code = %s ORDER BY run_ts DESC LIMIT 2",
                    (corp,),
                )
                runs = [r["run_ts"] for r in cur.fetchall()]

            if len(runs) < 2:
                return []

            latest_run, prev_run = runs[0], runs[1]

            with conn.cursor() as cur:
                cur.execute(
                    "SELECT predicate, target FROM edge_snapshot "
                    "WHERE corp_code = %s AND run_ts = %s",
                    (corp, prev_run),
                )
                prev_set = {(r["predicate"], r["target"]) for r in cur.fetchall()}

                cur.execute(
                    "SELECT predicate, target FROM edge_snapshot "
                    "WHERE corp_code = %s AND run_ts = %s",
                    (corp, latest_run),
                )
                latest_set = {(r["predicate"], r["target"]) for r in cur.fetchall()}

            dropped_pairs = prev_set - latest_set
            if not dropped_pairs:
                return []

            items: list[ChangeItem] = []
            for predicate, target_name in dropped_pairs:
                grp = PREDICATE_TO_GROUP.get(predicate)
                if not grp:
                    continue
                items.append(ChangeItem(
                    group=grp,
                    predicate=predicate,
                    target=target_name,
                    status="dropped",
                    date=str(date.today()),
                    evidenceCount=0,
                ))
            return items
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("edge_snapshot 조회 실패 (dropped 빈 배열 반환): %s", exc)
        return []


@router.get("/changes/{corp}", response_model=ChangesData)
def get_changes(
    corp: str,
    days: int = Query(14, ge=1, le=365),
) -> ChangesData:
    """corp 의 관계 변화: newItems (최근 {days}일 신규) + dropped (스냅샷 비교)."""
    cutoff = date.today() - timedelta(days=days)

    new_items = _fetch_new_items(corp, cutoff)
    dropped_items = _fetch_dropped_items(corp)

    return ChangesData(newItems=new_items, dropped=dropped_items)
