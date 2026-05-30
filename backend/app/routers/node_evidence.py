"""GET /api/node-evidence/{corp}/{node} — 엣지별 근거 드릴다운.

NodeEvidence: corp-node 사이 모든 predicate 별 docs(뉴스+공시) 반환.
동일 회사의 뉴스/DART 조각 노드를 fragment_ids 로 병합해 predicate 별로 통합한다.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter

from ..db import mariadb, neo4j
from ..models import EdgeEvidence, EvidenceDoc, NodeEvidence
from ..relations import DIRECTED, PREDICATE_TO_GROUP

from .node import NODE_NAME_CYPHER, _kind

router = APIRouter(tags=["node_evidence"])
logger = logging.getLogger(__name__)

EDGE_DOC_LIMIT = 50  # 엣지당 최대 문서 수

# corp + node 목록(IN) 으로 조각 전체 엣지 수집 — dart 엣지 필드 포함
EDGE_CYPHER = """
MATCH (a)-[r]-(b)
WHERE (a:Organization OR a:NewsEntity OR a:Company)
  AND (b:Organization OR b:NewsEntity OR b:Company)
  AND coalesce(a.corp_code, a.ext_id) = $corp
  AND coalesce(b.corp_code, b.ext_id) IN $nodes
RETURN type(r) AS rtype,
       r.evidence_count AS evidence_count,
       r.doc_ids AS doc_ids,
       r.extracted_by AS by,
       r.rcept_no AS rcept_no,
       r.qota_rt AS qota_rt,
       r.purps AS purps,
       r.amount AS amount,
       r.first_acq AS first_acq
"""

# Neo4j FilingDocument 조회 (rcept_no 목록)
FILING_CYPHER = """
UNWIND $rcept_nos AS rno
MATCH (f:FilingDocument {rcept_no: rno})
RETURN f.rcept_no AS rcept_no, f.title AS title, f.date AS date,
       f.doc_type AS doc_type, f.summary_short AS summary_short
"""

# Neo4j FilingDocument 단건 조회 (rcept_no)
FILING_SINGLE_CYPHER = """
MATCH (f:FilingDocument {rcept_no: $rcept_no})
RETURN f.rcept_no AS rcept_no, f.title AS title, f.date AS date,
       f.doc_type AS doc_type
LIMIT 1
"""


def _to_dart_doc(rcept_no: str, filing_map: dict[str, dict]) -> EvidenceDoc | None:
    """rcept_no → EvidenceDoc (disclosure). filing_map 에 없으면 None."""
    f = filing_map.get(rcept_no)
    if not f:
        return None
    _ss = f.get("summary_short") or ""
    if _ss.startswith("(LLM") or "호출 실패" in _ss:
        _ss = ""  # 요약 실패 placeholder 는 노출하지 않음 (제목+DART 링크로 충분)
    return EvidenceDoc(
        docId=rcept_no,
        docType="disclosure",
        title=f.get("title") or "",
        date=f.get("date") or "",
        url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",
        publisher="DART",
        snippet=_ss,
    )


@router.get("/node-evidence/{corp}/{node}", response_model=NodeEvidence)
def node_evidence(corp: str, node: str):
    """corp-node 사이 엣지별 근거 문서 드릴다운.

    fragment_ids 로 동일 canonical 조각 전체를 병합해 뉴스 언급 + DART 공시를 함께 반환한다.
    """
    from ..aliases import fragment_ids as _fragment_ids

    # ── 0. fragment_ids: 동일 canonical 조각 수집 ──
    try:
        frag_list: list[str] = _fragment_ids(node)
    except Exception:
        frag_list = [node]

    # ── 1. Neo4j: 노드 이름/kind + 엣지 수집 ──
    with neo4j().session() as s:
        edge_rows = s.run(EDGE_CYPHER, corp=corp, nodes=frag_list).data()
        node_rec = s.run(NODE_NAME_CYPHER, node_id=node).single()

    node_name: str = node
    has_corp_code = False
    if node_rec:
        node_name = node_rec["nm"] or node
        has_corp_code = bool(node_rec["corp_code"])

    kind = _kind(node, has_corp_code, corp)

    if not edge_rows:
        return NodeEvidence(id=node, name=node_name, kind=kind, edges=[])

    # ── 2. predicate 별 머지 ──
    # news 엣지: doc_ids 수집, ev=evidence_count
    # dart 엣지: rcept_nos 수집, stake/purpose/amount 는 최대 qota_rt 기준 대표값
    # {rtype: {"source": "news"|"dart", "ev": int, "doc_ids": [str],
    #          "rcept_nos": [str], "stake": float|None, "purpose": str|None,
    #          "amount": str|None, "max_qota": float}}
    merged: dict[str, dict] = {}
    for row in edge_rows:
        rtype = row["rtype"]
        if not PREDICATE_TO_GROUP.get(rtype):
            continue

        is_dart = (row["by"] is None)
        ids: list[str] = list(row["doc_ids"] or [])
        rcept_no: str | None = row["rcept_no"]
        qota_rt = row["qota_rt"]   # float|None
        purps = row["purps"]
        amount = row["amount"]
        first_acq = row["first_acq"]  # str|None (취득일)
        ev_raw = row["evidence_count"]

        if rtype not in merged:
            merged[rtype] = {
                "source": "dart" if is_dart else "news",
                "ev": int(ev_raw) if ev_raw is not None else 0,
                "doc_ids": ids,
                "rcept_nos": [rcept_no] if rcept_no else [],
                "stake": float(qota_rt) if qota_rt is not None else None,
                "purpose": purps or None,
                "amount": str(amount) if amount is not None else None,
                "first_acq": first_acq or None,
                "max_qota": float(qota_rt) if qota_rt is not None else -1.0,
            }
        else:
            m = merged[rtype]
            # source: 하나라도 news 면 news (혼재 시)
            if not is_dart:
                m["source"] = "news"
            # doc_ids dedup
            seen = set(m["doc_ids"])
            for d in ids:
                if d not in seen:
                    m["doc_ids"].append(d)
                    seen.add(d)
            # rcept_nos dedup
            if rcept_no and rcept_no not in m["rcept_nos"]:
                m["rcept_nos"].append(rcept_no)
            # ev: news 엣지는 evidence_count 우선; dart 엣지도 ev 누적
            if ev_raw is not None:
                m["ev"] = max(m["ev"], int(ev_raw))
            # 대표 stake/purpose/amount/first_acq: max qota_rt 기준
            if qota_rt is not None and float(qota_rt) > m["max_qota"]:
                m["max_qota"] = float(qota_rt)
                m["stake"] = float(qota_rt)
                m["purpose"] = purps or None
                m["amount"] = str(amount) if amount is not None else None
                m["first_acq"] = first_acq or None

    if not merged:
        return NodeEvidence(id=node, name=node_name, kind=kind, edges=[])

    # ── 3. news doc_ids → MariaDB 조회 ──
    all_news_ids: list[str] = []
    for v in merged.values():
        if v["source"] == "news":
            all_news_ids.extend(v["doc_ids"])
    all_news_ids = list(dict.fromkeys(all_news_ids))

    mariadb_docs: dict[str, EvidenceDoc] = {}
    conn = mariadb()
    try:
        with conn.cursor() as cur:
            if all_news_ids:
                ph = ",".join(["%s"] * len(all_news_ids))
                cur.execute(
                    f"SELECT doc_id, title, DATE_FORMAT(ts, '%%Y-%%m-%%d') AS d, "
                    f"url, body, metadata "
                    f"FROM document_unified WHERE doc_id IN ({ph}) ORDER BY ts DESC",
                    all_news_ids,
                )
                for r in cur.fetchall():
                    pub = None
                    try:
                        pub = (json.loads(r["metadata"]) or {}).get("publisher")
                    except Exception:
                        pass
                    mariadb_docs[r["doc_id"]] = EvidenceDoc(
                        docId=r["doc_id"],
                        docType="news",
                        title=r["title"] or "",
                        date=r["d"] or "",
                        url=r["url"] or "",
                        publisher=pub,
                        snippet=(r["body"] or "")[:160],
                    )
    finally:
        conn.close()

    # news doc_ids 중 MariaDB 미존재 → Neo4j FilingDocument 시도 (기존 fallback 유지)
    missing_news_ids = [d for d in all_news_ids if d not in mariadb_docs]
    # dart rcept_nos + missing_news_ids 모두 FilingDocument 조회
    all_rcept_nos: list[str] = list(dict.fromkeys(missing_news_ids))
    for v in merged.values():
        for rno in v.get("rcept_nos", []):
            if rno not in all_rcept_nos:
                all_rcept_nos.append(rno)

    filing_map: dict[str, dict] = {}
    if all_rcept_nos:
        with neo4j().session() as s:
            filing_rows = s.run(FILING_CYPHER, rcept_nos=all_rcept_nos).data()
        for f in filing_rows:
            filing_map[f["rcept_no"]] = f

    # missing news ids → filing_docs (기존 fallback)
    filing_docs: dict[str, EvidenceDoc] = {}
    for mid in missing_news_ids:
        doc = _to_dart_doc(mid, filing_map)
        if doc:
            filing_docs[mid] = doc

    # ── 4. EdgeEvidence 빌드 ──
    edges: list[EdgeEvidence] = []
    for rtype, v in merged.items():
        grp = PREDICATE_TO_GROUP[rtype]
        directed = rtype in DIRECTED
        is_dart_edge = (v["source"] == "dart")

        docs: list[EvidenceDoc] = []

        if is_dart_edge:
            # dart 엣지: rcept_nos → 공시 docs
            for rno in v["rcept_nos"]:
                doc = _to_dart_doc(rno, filing_map)
                if doc:
                    docs.append(doc)
            # evidenceCount = 첨부 공시 docs 수 (qota_rt 를 evidenceCount 로 쓰지 않음)
            ev_count = len(docs)
            stake = v["stake"]
            purpose = v["purpose"]
            amount = v["amount"]
            first_acq = v["first_acq"]
        else:
            # news 엣지: doc_ids → mariadb_docs + filing_docs fallback
            for did in v["doc_ids"]:
                if did in mariadb_docs:
                    docs.append(mariadb_docs[did])
                elif did in filing_docs:
                    docs.append(filing_docs[did])
            # evidenceCount = 수집된 근거 문서 수 (ev 가 있으면 그 값 우선)
            ev_count = v["ev"] if v["ev"] > 0 else len(docs)
            stake = None
            purpose = None
            amount = None
            first_acq = None

        # 날짜 desc 정렬
        docs.sort(key=lambda d: d.date, reverse=True)

        if len(docs) > EDGE_DOC_LIMIT:
            logger.info(
                "node-evidence %s->%s rtype=%s docs=%d > limit=%d, truncating",
                corp, node, rtype, len(docs), EDGE_DOC_LIMIT,
            )
            docs = docs[:EDGE_DOC_LIMIT]

        dates = [d.date for d in docs if d.date]
        first_date = min(dates) if dates else ""
        last_date = max(dates) if dates else ""

        edges.append(EdgeEvidence(
            group=grp,
            predicate=rtype,
            directed=directed,
            evidenceCount=ev_count,
            firstDate=first_date,
            lastDate=last_date,
            docs=docs,
            source=v["source"],
            stake=stake,
            purpose=purpose,
            amount=amount,
            firstAcq=first_acq,
        ))

    return NodeEvidence(id=node, name=node_name, kind=kind, edges=edges)
