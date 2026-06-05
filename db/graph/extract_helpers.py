"""POLARIS 비정형 관계 추출 적재 헬퍼 (Claude-direct 추출용, 재사용 인프라).

Claude(에이전트)가 청크 본문을 읽고 판단해 뽑은 엔티티·엣지를 멱등하게 적재한다.
- Product/Technology MERGE (결정론 id = sha1(canonical)[:16])
- Organization 매칭 (3사 corp_code 또는 needs_er er_name 노드)
- 비정형 엣지 MERGE + 근거속성(extracted_by='claude', chunk_id, rcept_no, confidence)
- extraction_provenance(MariaDB) 멱등 INSERT
- 커버리지 원장 extract_ledger.jsonl (DB 스키마 추가 금지 — 파일 원장)

DB 스키마 변경 금지. 설계 SSOT = docs/DBdocs/03_neo4j.md, 01_mariadb.md §2.5.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from db import (
    CORP_NAME,
    mariadb_conn,
    neo4j_driver,
    normalize_corp_name,
)

LEDGER_PATH = Path(__file__).resolve().parent / "extract_ledger.jsonl"

# 허용 엣지 타입 (03_neo4j.md §2-2)
EDGE_TYPES = {"PRODUCES", "USES_TECH", "SUPPLIES_TO", "RELATED_PARTY", "hasObject"}

# corp_code ← 정규화 이름 역인덱스 (Organization 매칭용)
# 3사 + extra28(corps.tsv) + Neo4j 의 모든 corp_code 노드 이름(㈜ 변형 포함)을 모아
# 본문에 등장한 회사명을 실제 corp_code 노드로 연결한다(needs_er 중복 방지).
def _build_corp_index() -> dict:
    idx = {normalize_corp_name(nm): cc for cc, nm in CORP_NAME.items()}
    tsv = Path(__file__).resolve().parent.parent / "extra28" / "corps.tsv"
    if tsv.exists():
        for line in tsv.read_text(encoding="utf-8").splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) >= 2:
                k = normalize_corp_name(parts[1].strip())
                if k:
                    idx.setdefault(k, parts[0].strip())
    try:
        drv = neo4j_driver()
        with drv.session() as s:
            for rec in s.run(
                "MATCH (o:Organization) WHERE o.corp_code IS NOT NULL "
                "AND o.name IS NOT NULL RETURN o.corp_code AS cc, o.name AS nm"
            ):
                k = normalize_corp_name(rec["nm"])
                if k:
                    idx.setdefault(k, rec["cc"])
    except Exception:
        pass
    return idx


_CORP_BY_ERNAME = _build_corp_index()


# ── 결정론 id ──────────────────────────────────────────────
def entity_id(canonical: str) -> str:
    """Product/Technology 결정론 id = sha1(canonical)[:16]."""
    return hashlib.sha1((canonical or "").strip().lower().encode("utf-8")).hexdigest()[:16]


def prov_id(subject_id: str, predicate: str, object_id: str, chunk_id: str) -> str:
    """provenance 결정론 id = sha1(subject|predicate|object|chunk)[:32]. 멱등 키."""
    key = f"{subject_id}|{predicate}|{object_id}|{chunk_id}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:32]


# ── MariaDB: 청크 조회 ─────────────────────────────────────
def get_chunks(where_sql: str) -> list[dict]:
    """chunk_index 행 리스트(embedding_text 포함). where_sql = 'WHERE ...' 절 그대로."""
    conn = mariadb_conn()
    cur = conn.cursor(pymysql_cursor_dict())
    cur.execute(
        "SELECT chunk_id, corp_code, rcept_no, chunk_type, section_path, "
        "embedding_text, token_count, ingest_status "
        f"FROM chunk_index {where_sql}"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return list(rows)


def pymysql_cursor_dict():
    import pymysql.cursors
    return pymysql.cursors.DictCursor


# ── Neo4j: 엔티티 MERGE ────────────────────────────────────
def resolve_org(name: str) -> dict:
    """회사명 → 매칭 식별자. 3사면 {'mode':'corp','corp_code':..,'id':corp_code},
    아니면 {'mode':'er','er_name':..,'id':er_name}. 빈 이름이면 None."""
    er = normalize_corp_name(name)
    if not er:
        return None
    cc = _CORP_BY_ERNAME.get(er)
    if cc:
        return {"mode": "corp", "corp_code": cc, "er_name": er, "id": cc, "name": name}
    return {"mode": "er", "er_name": er, "id": er, "name": name}


def merge_entity(driver, label: str, canonical: str, name: str = None, extra: dict = None) -> str:
    """Product/Technology MERGE. id = sha1(canonical)[:16]. canonical=ER 키(소문자).
    반환: 생성/매칭된 entity id."""
    assert label in ("Product", "Technology"), label
    key_field = "product_id" if label == "Product" else "tech_id"
    eid = entity_id(canonical)
    props = {"name": name or canonical, "canonical": canonical.strip().lower()}
    if extra:
        props.update(extra)
    cy = (
        f"MERGE (e:{label} {{{key_field}:$eid}}) "
        "SET e += $props "
        "RETURN e." + key_field + " AS id"
    )
    with driver.session() as s:
        s.run(cy, eid=eid, props=props)
    return eid


def merge_org_node(driver, org: dict) -> None:
    """needs_er Organization 노드 보장(corp_code 노드는 이미 존재하므로 건드리지 않음)."""
    if org["mode"] == "corp":
        return  # 이미 존재
    with driver.session() as s:
        s.run(
            "MERGE (o:Organization {er_name:$er, has_corp_code:false}) "
            "ON CREATE SET o.name=$name, o.needs_er=true, o.has_corp_code=false",
            er=org["er_name"], name=org["name"],
        )


# ── Neo4j: 엣지 MERGE (근거속성 부착) ──────────────────────
def _org_match_clause(var: str, org: dict, pkey: str):
    """org dict → (cypher fragment, params). var=노드변수, pkey=파라미터접두."""
    if org["mode"] == "corp":
        return (
            f"MERGE ({var}:Organization {{corp_code:${pkey}_corp}})",
            {f"{pkey}_corp": org["corp_code"]},
        )
    return (
        f"MERGE ({var}:Organization {{er_name:${pkey}_er, has_corp_code:false}}) "
        f"ON CREATE SET {var}.name=${pkey}_name, {var}.needs_er=true, {var}.has_corp_code=false",
        {f"{pkey}_er": org["er_name"], f"{pkey}_name": org["name"]},
    )


def add_edge(driver, rel_type: str, from_match: dict, to_match: dict,
             chunk_id: str, rcept_no: str, confidence: float,
             relation_type: str = None, extracted_by: str = "claude") -> None:
    """비정형 엣지 멱등 MERGE + 근거속성 SET.

    from_match / to_match: {'kind':'org','org':<resolve_org dict>}
                        또는 {'kind':'entity','label':'Product'|'Technology','id':eid}
                        또는 {'kind':'chunk','chunk_id':...}  (hasObject 출발점)
    """
    assert rel_type in EDGE_TYPES, rel_type
    params = {
        "chunk_id": chunk_id,
        "rcept_no": rcept_no,
        "confidence": float(confidence),
        "extracted_by": extracted_by,
    }
    clauses = []

    def node_clause(var, m, pkey):
        if m["kind"] == "org":
            frag, p = _org_match_clause(var, m["org"], pkey)
            params.update(p)
            return frag
        if m["kind"] == "entity":
            kf = "product_id" if m["label"] == "Product" else "tech_id"
            params[f"{pkey}_id"] = m["id"]
            return f"MERGE ({var}:{m['label']} {{{kf}:${pkey}_id}})"
        if m["kind"] == "chunk":
            params[f"{pkey}_cid"] = m["chunk_id"]
            return f"MATCH ({var}:Chunk {{chunk_id:${pkey}_cid}})"
        raise ValueError(m)

    clauses.append(node_clause("a", from_match, "a"))
    clauses.append(node_clause("b", to_match, "b"))
    set_extra = ", r.relation_type=$relation_type" if relation_type else ""
    if relation_type:
        params["relation_type"] = relation_type
    cy = (
        "\n".join(clauses)
        + f"\nMERGE (a)-[r:{rel_type}]->(b)"
        + "\nSET r.extracted_by=$extracted_by, r.chunk_id=$chunk_id, "
          "r.rcept_no=$rcept_no, r.confidence=$confidence" + set_extra
    )
    with driver.session() as s:
        s.run(cy, **params)


# ── MariaDB: provenance 원장 ───────────────────────────────
def write_provenance(conn, subject_id: str, predicate: str, object_id: str,
                     chunk_id: str, rcept_no: str, confidence: float,
                     extracted_by: str = "claude") -> str:
    """extraction_provenance 멱등 INSERT(ON DUP). prov_id = 결정론. 반환 prov_id."""
    pid = prov_id(subject_id, predicate, object_id, chunk_id)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO extraction_provenance "
        "(prov_id, subject_id, predicate, object_id, chunk_id, rcept_no, extracted_by, confidence) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON DUPLICATE KEY UPDATE confidence=VALUES(confidence), rcept_no=VALUES(rcept_no), "
        "extracted_by=VALUES(extracted_by)",
        (pid, subject_id, predicate, object_id, chunk_id, rcept_no, extracted_by, float(confidence)),
    )
    cur.close()
    return pid


# ── 커버리지 원장 (jsonl 파일) ─────────────────────────────
def mark_processed(chunk_id: str, n_ent: int, n_edge: int,
                   rcept_no: str = None, section_path: str = None) -> None:
    """extract_ledger.jsonl 갱신 append. 같은 chunk_id 줄은 마지막 것이 유효(중복 시 갱신)."""
    rec = {
        "chunk_id": chunk_id,
        "n_ent": n_ent,
        "n_edge": n_edge,
        "rcept_no": rcept_no,
        "section_path": section_path,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def ledger_processed_ids() -> set[str]:
    """원장에 기록된 chunk_id 집합(마지막 줄 기준)."""
    if not LEDGER_PATH.exists():
        return set()
    ids = set()
    for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ids.add(json.loads(line)["chunk_id"])
        except Exception:
            continue
    return ids
