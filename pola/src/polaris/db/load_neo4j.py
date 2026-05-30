"""Neo4j 적재 — graph_extracts JSONL → 노드·엣지 MERGE.

설계 05 §1.7 / §2.1 entity vs fact 분리:
  🌐 전역 entity (run_id 속성 없음, first_seen/last_updated_run_id 만):
     Organization(=Company), Person, BusinessGroup, MacroIndicator, StatTable, FilingDocument
  ⏱ run-scoped (key, run_id 복합 MERGE):
     Event, Statement, Chunk

엣지는 모두 run_id 속성 보유. PROV-O wasDerivedFrom · wasGeneratedBy 동시 생성.
reification_meta.should_reify=True → :Relation 노드로 reify.

idempotent — MERGE 사용.
"""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path

from polaris.config import neo4j_driver, mariadb_conn, CHUNKS_DIR, META_DIR

GRAPH = CHUNKS_DIR / "graph_extracts"
META = META_DIR

BATCH = 200


def get_standby_run_id() -> str:
    conn = mariadb_conn()
    cur = conn.cursor()
    cur.execute("SELECT standby_run_id FROM active_run_manifest WHERE id=1")
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row or not row[0]:
        raise RuntimeError("standby_run_id 없음 — load_mariadb.py 먼저 실행")
    return row[0]


# ── 1. FilingDocument (document_index.jsonl) — 전역 entity ─────────────────
LOAD_FILING = """
UNWIND $batch AS d
MERGE (f:FilingDocument {rcept_no: d.rcept_no})
ON CREATE SET f.first_seen_run_id = $run_id
SET f.corp_code           = d.corp_code,
    f.doc_type            = d.doc_type,
    f.date                = d.date,
    f.title               = d.title,
    f.snapshot_path       = d.snapshot_path,
    f.summary_short       = d.summary_short,
    f.summary_method      = d.summary_method,
    f.summary_verified    = d.summary_verified,
    f.body_chars          = d.body_chars,
    f.last_updated_run_id = $run_id
"""


# ── 2. 전역 entity (Company/Person/BusinessGroup/MacroIndicator/StatTable) ──
LOAD_COMPANY = """
UNWIND $batch AS e
MERGE (o:Organization:Company {corp_code: e.node_id})
ON CREATE SET o.first_seen_run_id = $run_id
SET o.name                = e.props.name,
    o.jurirno             = e.props.jurirno,
    o.bizrno              = e.props.bizrno,
    o.founded             = e.props.founded,
    o.last_updated_run_id = $run_id
"""

LOAD_PERSON = """
UNWIND $batch AS e
MERGE (p:Person {person_id: e.node_id})
ON CREATE SET p.first_seen_run_id = $run_id
SET p.name                = e.props.name,
    p.birth_ym            = e.props.birth_ym,
    p.sexdstn             = e.props.sexdstn,
    p.last_updated_run_id = $run_id
"""

LOAD_BIZGROUP = """
UNWIND $batch AS e
MERGE (bg:BusinessGroup {unityGrupCode: coalesce(e.props.unity_group_code, e.node_id)})
ON CREATE SET bg.first_seen_run_id = $run_id
SET bg.name                  = e.props.name,
    bg.year                  = e.props.year,
    bg.representative_company = e.props.representative_company,
    bg.designation_date      = e.props.designation_date,
    bg.last_updated_run_id   = $run_id
"""

LOAD_MACRO = """
UNWIND $batch AS e
MERGE (m:MacroIndicator {stat_code: coalesce(e.props.stat_code, e.node_id)})
ON CREATE SET m.first_seen_run_id = $run_id
SET m.name                = e.props.name,
    m.source              = e.props.source,
    m.total_rows          = e.props.total_rows,
    m.latest_time         = e.props.latest_time,
    m.latest_value        = e.props.latest_value,
    m.unit                = e.props.unit,
    m.last_updated_run_id = $run_id
"""

LOAD_STATTABLE = """
UNWIND $batch AS e
MERGE (s:StatTable {list_id: coalesce(e.props.list_id, e.node_id)})
ON CREATE SET s.first_seen_run_id = $run_id
SET s.name                = e.props.name,
    s.source              = e.props.source,
    s.category            = e.props.category,
    s.last_updated_run_id = $run_id
"""


# ── 3. Event (run-scoped) + hasActor + wasDerivedFrom ────────────────────
LOAD_EVENT = """
UNWIND $batch AS ev
MERGE (e:Event {event_id: ev.event_id, run_id: $run_id})
ON CREATE SET e.event_type    = ev.event_type,
              e.label         = ev.props.label,
              e.actor_corp    = ev.props.actor_corp,
              e.rcept_no      = ev.props.rcept_no,
              e.endpoint      = ev.props.endpoint
SET e.pipeline_version = ev.pipeline_version
WITH e, ev
// hasActor → Organization (actor_corp)
WITH e, ev WHERE ev.props.actor_corp IS NOT NULL
MERGE (org:Organization {corp_code: ev.props.actor_corp})
ON CREATE SET org.first_seen_run_id = $run_id, org.last_updated_run_id = $run_id
MERGE (e)-[r:hasActor {run_id: $run_id}]->(org)
ON CREATE SET r.role = 'actor'
WITH e, ev
// wasDerivedFrom → FilingDocument
WITH e, ev WHERE ev.props.rcept_no IS NOT NULL AND ev.props.rcept_no <> ''
MERGE (fd:FilingDocument {rcept_no: ev.props.rcept_no})
ON CREATE SET fd.first_seen_run_id = $run_id, fd.last_updated_run_id = $run_id
MERGE (e)-[d:wasDerivedFrom {run_id: $run_id}]->(fd)
"""


# ── 4. Statement (run-scoped) + subjectOf/objectOf ───────────────────────
LOAD_STATEMENT = """
UNWIND $batch AS st
MERGE (s:Statement {statement_id: st.stmt_id, run_id: $run_id})
ON CREATE SET s.subject    = st.subject,
              s.predicate  = st.predicate,
              s.object     = st.object,
              s.confidence = st.confidence,
              s.source_endpoint = st.source_endpoint
SET s.last_updated_run_id = $run_id
"""


# ── 5. Relations — 단순 엣지 (should_reify=false) ────────────────────────
#       reify=true 는 :Relation 노드로 변환 (다음 사이클 — 본 시연은 단순 엣지만)
LOAD_REL_GENERIC = """
UNWIND $batch AS r
MATCH (from {corp_code: r.from})       WHERE 'Organization' IN labels(from) OR 'Company' IN labels(from)
WITH r, from
OPTIONAL MATCH (to_o:Organization {corp_code: r.to})
OPTIONAL MATCH (to_p:Person {person_id: r.to})
WITH r, from, coalesce(to_o, to_p) AS to_n WHERE to_n IS NOT NULL
CALL apoc.merge.relationship(from, r.type, {run_id: $run_id, rel_id: r.rel_id}, r.props, to_n, {}) YIELD rel
RETURN count(rel)
"""

# APOC 없을 때 fallback — 타입별 분기
REL_BY_TYPE = {
    "EXECUTIVE_OF": """
        UNWIND $batch AS r
        MATCH (p:Person {person_id: r.from})
        MATCH (o:Organization {corp_code: r.to})
        MERGE (p)-[e:EXECUTIVE_OF {run_id: $run_id, rel_id: r.rel_id}]->(o)
        SET e.position    = r.props.position,
            e.tenure_end  = r.props.tenure_end,
            e.rcept_no    = r.props.rcept_no
    """,
    "IS_MAJOR_SHAREHOLDER_OF": """
        UNWIND $batch AS r
        OPTIONAL MATCH (from_p:Person {person_id: r.from})
        OPTIONAL MATCH (from_o:Organization {corp_code: r.from})
        WITH r, coalesce(from_p, from_o) AS from_n WHERE from_n IS NOT NULL
        MATCH (o:Organization {corp_code: r.to})
        MERGE (from_n)-[e:IS_MAJOR_SHAREHOLDER_OF {run_id: $run_id, rel_id: r.rel_id}]->(o)
        SET e.qota_rt     = r.props.qota_rt,
            e.as_of       = r.props.as_of,
            e.rcept_no    = r.props.rcept_no
    """,
    "INVESTS_IN": """
        UNWIND $batch AS r
        MATCH (a:Organization {corp_code: r.from})
        OPTIONAL MATCH (b_o:Organization {corp_code: r.to})
        WITH r, a, b_o
        // b가 Org 매칭 안 되면 임시 placeholder 노드 (corp_code 도 그대로)
        FOREACH (_ IN CASE WHEN b_o IS NULL THEN [1] ELSE [] END |
            MERGE (b2:Organization {corp_code: r.to})
            ON CREATE SET b2.first_seen_run_id = $run_id, b2.last_updated_run_id = $run_id, b2.name = r.props.investee_name
        )
        WITH r, a
        MATCH (b:Organization {corp_code: r.to})
        MERGE (a)-[e:INVESTS_IN {run_id: $run_id, rel_id: r.rel_id}]->(b)
        SET e.frst_acqs_de  = r.props.frst_acqs_de,
            e.invstmnt_purps= r.props.invstmnt_purps,
            e.qota_rt       = r.props.qota_rt,
            e.acntbk_amount = r.props.acntbk_amount,
            e.rcept_no      = r.props.rcept_no
    """,
    "AFFILIATED_WITH": """
        UNWIND $batch AS r
        // r.from 이 'unknown_xxx' 면 placeholder Organization 생성 (FTC 계열사 중 corp_code 미매칭)
        MERGE (o:Organization {corp_code: r.from})
        ON CREATE SET o.name = coalesce(r.props.affiliate_name, r.from),
                      o.first_seen_run_id = $run_id, o.last_updated_run_id = $run_id,
                      o.unlinked = true
        WITH r, o
        // r.to 의 'BG_' prefix 제거 후 BusinessGroup 매칭
        WITH r, o, CASE WHEN r.to STARTS WITH 'BG_' THEN substring(r.to, 3) ELSE r.to END AS bg_code
        MERGE (bg:BusinessGroup {unityGrupCode: bg_code})
        ON CREATE SET bg.first_seen_run_id = $run_id, bg.last_updated_run_id = $run_id
        MERGE (o)-[e:AFFILIATED_WITH {run_id: $run_id, rel_id: r.rel_id}]->(bg)
        SET e.year     = r.props.year,
            e.rcept_no = r.props.rcept_no
    """,
    # hasActor 는 Event 적재 시 함께 처리됨 (LOAD_EVENT 참조).
    # 별도 적재 시에도 안전하게 MERGE.
    "hasActor": """
        UNWIND $batch AS r
        MATCH (e:Event {event_id: r.from, run_id: $run_id})
        OPTIONAL MATCH (to_o:Organization {corp_code: r.to})
        OPTIONAL MATCH (to_p:Person {person_id: r.to})
        WITH e, r, coalesce(to_o, to_p) AS to_n WHERE to_n IS NOT NULL
        MERGE (e)-[edge:hasActor {run_id: $run_id, rel_id: r.rel_id}]->(to_n)
        SET edge.role = coalesce(r.props.role, 'actor')
    """,
}


def chunked(it, size: int):
    buf = []
    for x in it:
        buf.append(x)
        if len(buf) >= size:
            yield buf; buf = []
    if buf:
        yield buf


def iter_jsonl(p: Path):
    if not p.is_file():
        return
    with p.open(encoding="utf-8") as f:
        for line in f:
            try:
                yield json.loads(line)
            except Exception:
                continue


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-relations", action="store_true",
                    help="관계 적재 skip (스키마 디버깅용)")
    args = ap.parse_args()

    t0 = time.time()
    run_id = get_standby_run_id()
    print(f"[load_neo4j] run_id={run_id}")
    driver = neo4j_driver()
    stats = {}

    with driver.session() as sess:

        # 1. FilingDocument
        print("\n[1/5] FilingDocument (전역)")
        docs = []
        for r in iter_jsonl(META / "document_index.jsonl"):
            docs.append({
                "rcept_no": r["rcept_no"], "corp_code": r["corp_code"],
                "doc_type": r.get("doc_type"), "date": r.get("date"),
                "title": r.get("title"), "snapshot_path": r.get("snapshot_path"),
                "summary_short": r.get("summary_short"),
                "summary_method": r.get("summary_method"),
                "summary_verified": bool(r.get("summary_verified")),
                "body_chars": r.get("body_chars"),
            })
        n = 0
        for b in chunked(docs, BATCH):
            sess.run(LOAD_FILING, batch=b, run_id=run_id)
            n += len(b)
        stats["FilingDocument"] = n
        print(f"  {n}")

        # 2. 전역 entity 별 적재
        print("\n[2/5] 전역 entity (Company/Person/BusinessGroup/MacroIndicator/StatTable)")
        by_label: dict[str, list] = {}
        for e in iter_jsonl(GRAPH / "entities.jsonl"):
            by_label.setdefault(e["label"], []).append({
                "node_id": e["node_id"], "props": e.get("properties", {}),
            })
        loader_map = {
            "Company": LOAD_COMPANY, "Person": LOAD_PERSON,
            "BusinessGroup": LOAD_BIZGROUP, "MacroIndicator": LOAD_MACRO,
            "StatTable": LOAD_STATTABLE,
        }
        for label, q in loader_map.items():
            items = by_label.get(label, [])
            n = 0
            for b in chunked(items, BATCH):
                sess.run(q, batch=b, run_id=run_id)
                n += len(b)
            stats[label] = n
            print(f"  {label}: {n}")

        # 3. Event (run-scoped) — hasActor + wasDerivedFrom 동시
        print("\n[3/5] Event (run-scoped)")
        events = []
        for e in iter_jsonl(GRAPH / "events.jsonl"):
            events.append({
                "event_id": e["event_id"], "event_type": e["event_type"],
                "props": e.get("properties", {}),
                "pipeline_version": (e.get("properties", {})
                                      .get("wasGeneratedBy", {})
                                      .get("pipeline_version", "")),
            })
        n = 0
        for b in chunked(events, BATCH):
            sess.run(LOAD_EVENT, batch=b, run_id=run_id)
            n += len(b)
        stats["Event"] = n
        print(f"  {n}")

        # 4. Statement (run-scoped)
        print("\n[4/5] Statement (run-scoped)")
        stmts = []
        seen = set()
        for s in iter_jsonl(GRAPH / "statements.jsonl"):
            key = s["stmt_id"]
            if key in seen:
                continue
            seen.add(key)
            stmts.append({
                "stmt_id": s["stmt_id"], "subject": s["subject"],
                "predicate": s["predicate"], "object": s["object"],
                "confidence": s.get("confidence", 1.0),
                "source_endpoint": s.get("source_endpoint"),
            })
        n = 0
        for b in chunked(stmts, BATCH):
            sess.run(LOAD_STATEMENT, batch=b, run_id=run_id)
            n += len(b)
        stats["Statement"] = n
        print(f"  {n} (unique stmt_id)")

        # 5. Relations — 타입별 분기
        if args.skip_relations:
            print("\n[5/5] Relations: SKIPPED (--skip-relations)")
        else:
            print("\n[5/5] Relations (타입별)")
            rels_by_type: dict[str, list] = {}
            for r in iter_jsonl(GRAPH / "relations.jsonl"):
                rels_by_type.setdefault(r["type"], []).append({
                    "rel_id": r["rel_id"], "type": r["type"],
                    "from": r["from"], "to": r["to"],
                    "props": r.get("properties", {}),
                })
            for rtype, items in rels_by_type.items():
                q = REL_BY_TYPE.get(rtype)
                if not q:
                    print(f"  {rtype}: 미지원 타입 — skip ({len(items)})")
                    continue
                n = 0
                for b in chunked(items, BATCH):
                    sess.run(q, batch=b, run_id=run_id)
                    n += len(b)
                stats[f"rel_{rtype}"] = n
                print(f"  {rtype}: {n}")

    driver.close()
    elapsed = time.time() - t0
    print(f"\n=== Neo4j 적재 완료 ({elapsed:.1f}s, run_id={run_id}) ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
