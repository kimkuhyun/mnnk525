"""GET /api/evidence?source&target&group — 엣지(관계) 근거 기사.

뉴스엣지 doc_ids → document_unified 조회. source/target = 그래프 노드 id(corp_code 또는 ext_id).
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Query

from ..db import mariadb_conn, neo4j
from ..models import EvidenceItem
from ..relations import GROUP_TO_PREDICATES

router = APIRouter(tags=["evidence"])

DOC_IDS = """
MATCH (a:Organization)-[r]-(b:Organization)
WHERE coalesce(a.corp_code, a.ext_id) = $source
  AND coalesce(b.corp_code, b.ext_id) = $target
  AND type(r) IN $types AND r.extracted_by = 'claude'
RETURN r.doc_ids AS doc_ids
"""


@router.get("/evidence", response_model=list[EvidenceItem])
def evidence(source: str = Query(...), target: str = Query(...), group: str = Query(...)):
    types = GROUP_TO_PREDICATES.get(group, [])
    if not types:
        return []

    doc_ids: list[str] = []
    with neo4j().session() as s:
        for row in s.run(DOC_IDS, source=source, target=target, types=types).data():
            if row["doc_ids"]:
                doc_ids.extend(row["doc_ids"])
    doc_ids = list(dict.fromkeys(doc_ids))  # 중복 제거(순서 보존)
    if not doc_ids:
        return []

    out: list[EvidenceItem] = []
    with mariadb_conn() as conn, conn.cursor() as cur:
        ph = ",".join(["%s"] * len(doc_ids))
        cur.execute(
            f"SELECT doc_id, title, DATE_FORMAT(ts, '%%Y-%%m-%%d') AS d, url, body, metadata "
            f"FROM document_unified WHERE doc_id IN ({ph}) ORDER BY ts DESC",
            doc_ids,
        )
        for r in cur.fetchall():
            pub = None
            try:
                pub = (json.loads(r["metadata"]) or {}).get("publisher")
            except Exception:
                pass
            out.append(EvidenceItem(
                docId=r["doc_id"], title=r["title"] or "", date=r["d"] or "",
                url=r["url"] or "", publisher=pub, snippet=(r["body"] or "")[:120],
            ))
    return out
