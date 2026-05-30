"""GET /api/node/{corp}/{node} — 노드 상세 (이게 뭔지·왜 잡혔는지).

center(corp)와 node 사이의 관계 + 근거 기사 + 회사 프로파일(kind=seed/org 일 때).
동일 회사의 뉴스 노드·DART 노드 조각을 fragment_ids 로 병합해 함께 반환한다.
"""
from __future__ import annotations

import json
import re

from fastapi import APIRouter

from ..db import mariadb_conn, neo4j
from ..models import CompanyProfile, EvidenceItem, NodeDetail, NodeRelation
from ..relations import PREDICATE_TO_GROUP, DIRECTED, SEED_CORPS

router = APIRouter(tags=["node"])

EVIDENCE_LIMIT = 8  # 근거기사 상위 N

# center-node 사이 모든 관계 엣지 (doc_ids 포함) — node 목록 IN 파라미터 버전
RELATIONS_CYPHER = """
MATCH (a)-[r]-(b)
WHERE (a:Organization OR a:NewsEntity OR a:Company)
  AND (b:Organization OR b:NewsEntity OR b:Company)
  AND coalesce(a.corp_code, a.ext_id) = $corp
  AND coalesce(b.corp_code, b.ext_id) IN $nodes
RETURN type(r) AS rtype,
       coalesce(startNode(r).corp_code, startNode(r).ext_id) AS src,
       coalesce(endNode(r).corp_code, endNode(r).ext_id) AS tgt,
       toInteger(coalesce(r.evidence_count, r.qota_rt, 1)) AS evCount,
       r.doc_ids AS doc_ids,
       r.extracted_by AS by
"""

NODE_NAME_CYPHER = """
MATCH (o)
WHERE (o:Organization OR o:NewsEntity OR o:Company)
  AND coalesce(o.corp_code, o.ext_id) = $node_id
RETURN coalesce(o.name, o.corp_code, o.ext_id) AS nm, o.corp_code AS corp_code
LIMIT 1
"""


def _kind(node_id: str, has_corp_code: bool, corp: str) -> str:
    if node_id == corp or node_id in SEED_CORPS:
        return "seed"
    if has_corp_code:
        return "org"
    ext = str(node_id)
    if ext.startswith("news:per"):
        return "person"
    if ext.startswith("news:prod"):
        return "product"
    if ext.startswith("news:"):
        return "news_entity"
    if re.match(r"^\d{8}$", ext):
        return "org"
    return "news_entity"


@router.get("/node/{corp}/{node}", response_model=NodeDetail)
def node_detail(corp: str, node: str):
    """center(corp)와 node 사이의 관계 + 근거기사 + 프로파일.

    동일 회사의 뉴스/DART 조각 노드를 fragment_ids 로 병합해 전체 출처를 통합 반환한다.
    canonical 이 없거나 조각 수집 실패 시 단일 노드로 fallback.
    """
    from ..aliases import fragment_ids as _fragment_ids

    # ── fragment_ids: 같은 canonical 이름 조각 전체 수집 ──
    try:
        frag_list: list[str] = _fragment_ids(node)
    except Exception:
        frag_list = [node]

    with neo4j().session() as s:
        rel_rows = s.run(RELATIONS_CYPHER, corp=corp, nodes=frag_list).data()
        node_rec = s.run(NODE_NAME_CYPHER, node_id=node).single()

    # 노드 이름 / corp_code 유무
    node_name: str = node
    has_corp_code = False
    if node_rec:
        node_name = node_rec["nm"] or node
        has_corp_code = bool(node_rec["corp_code"])

    # corp_code 를 가진 조각이 있으면 프로파일용 corp_code 확보
    profile_node: str = node
    if not has_corp_code and len(frag_list) > 1:
        try:
            with neo4j().session() as s:
                for fid in frag_list:
                    rec = s.run(NODE_NAME_CYPHER, node_id=fid).single()
                    if rec and rec["corp_code"]:
                        profile_node = fid
                        has_corp_code = True
                        break
        except Exception:
            pass

    kind = _kind(node, has_corp_code, corp)
    is_seed = node in SEED_CORPS

    # ── relations 빌드 — (group, predicate, target) 기준 dedup, source 유지 ──
    # dedup_key -> best row (news 우선, evidence 최대)
    dedup: dict[tuple[str, str, str], dict] = {}

    for row in rel_rows:
        grp = PREDICATE_TO_GROUP.get(row["rtype"])
        if not grp:
            continue
        # target_id: corp 가 src 이면 tgt 가 대상, 아니면 src 가 대상
        raw_tgt = row["tgt"] if row["src"] == corp else row["src"]
        # 조각 id 를 원본 node id 로 정규화 (표시용)
        target_id = node if raw_tgt in frag_list else raw_tgt

        rel_source = "dart" if row.get("by") is None else "news"
        key = (grp, row["rtype"], target_id)

        if key not in dedup:
            dedup[key] = {
                "grp": grp,
                "rtype": row["rtype"],
                "target": target_id,
                "evCount": row["evCount"] or 1,
                "source": rel_source,
                "doc_ids": list(row["doc_ids"] or []),
            }
        else:
            m = dedup[key]
            # news 출처 우선
            if rel_source == "news":
                m["source"] = "news"
            # evCount 최대
            m["evCount"] = max(m["evCount"], row["evCount"] or 1)
            # doc_ids union
            seen = set(m["doc_ids"])
            for d in (row["doc_ids"] or []):
                if d not in seen:
                    m["doc_ids"].append(d)
                    seen.add(d)

    relations: list[NodeRelation] = []
    all_doc_ids: list[str] = []
    for v in dedup.values():
        relations.append(NodeRelation(
            group=v["grp"],
            predicate=v["rtype"],
            target=v["target"],
            evidenceCount=v["evCount"],
            directed=v["rtype"] in DIRECTED,
            source=v["source"],
        ))
        all_doc_ids.extend(v["doc_ids"])

    # doc_ids 중복 제거(순서 보존)
    doc_ids = list(dict.fromkeys(all_doc_ids))

    # ── 근거기사 조회 (MariaDB) ──
    evidence: list[EvidenceItem] = []
    if doc_ids:
        with mariadb_conn() as conn, conn.cursor() as cur:
            ph = ",".join(["%s"] * len(doc_ids))
            cur.execute(
                f"SELECT doc_id, title, DATE_FORMAT(ts, '%%Y-%%m-%%d') AS d, "
                f"url, body, metadata "
                f"FROM document_unified WHERE doc_id IN ({ph}) ORDER BY ts DESC LIMIT %s",
                (*doc_ids, EVIDENCE_LIMIT),
            )
            for r in cur.fetchall():
                pub = None
                try:
                    pub = (json.loads(r["metadata"]) or {}).get("publisher")
                except Exception:
                    pass
                evidence.append(EvidenceItem(
                    docId=r["doc_id"],
                    title=r["title"] or "",
                    date=r["d"] or "",
                    url=r["url"] or "",
                    publisher=pub,
                    snippet=(r["body"] or "")[:120],
                ))

    # ── 프로파일 (seed/org + corp_code 보유 시) ──
    profile: CompanyProfile | None = None
    if kind in ("seed", "org") and has_corp_code:
        try:
            from .company import company as _company
            profile = _company(profile_node)
        except Exception:
            profile = None

    return NodeDetail(
        id=node,
        name=node_name,
        kind=kind,
        isSeed=is_seed,
        relations=relations,
        evidence=evidence,
        profile=profile,
    )
