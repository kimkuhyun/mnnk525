"""Cross-DB 일관성 검증 (gold 200 retrieval 직전 smoke test).

검증 항목:
  1. Qdrant points 수 == MariaDB chunk_index rows (run_id 별)
  2. 임의 chunk_id 1개로 3 DB round-trip 가능?
  3. Neo4j Chunk 노드는 본 시연에 적재하지 않음 (T4 lookup-only, 본 시연은 lookup 안 함)
     → 대신 Event/Person/Org 등 핵심 노드 카운트 출력
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

from polaris.config import (
    mariadb_conn, qdrant_client, neo4j_driver,
    QDRANT_COLLECTION_ACTIVE, QDRANT_COLLECTION_STANDBY,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", choices=("active", "standby"), default="standby")
    args = ap.parse_args()

    # 1. 어느 컬렉션 / run_id 인가
    conn = mariadb_conn()
    cur = conn.cursor()
    cur.execute(f"SELECT {args.slot}_run_id, {args.slot}_qdrant_collection FROM active_run_manifest WHERE id=1")
    row = cur.fetchone()
    if not row or not row[0]:
        print(f"[verify] {args.slot} 슬롯 비어 있음")
        return 1
    run_id, qcol = row
    print(f"[verify] slot={args.slot} run_id={run_id} qdrant={qcol}\n")

    # 2. MariaDB count
    cur.execute("SELECT COUNT(*), SUM(ingest_status='ready') FROM chunk_index WHERE run_id=%s", (run_id,))
    mdb_total, mdb_ready = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM document_index WHERE run_id=%s", (run_id,))
    mdb_docs = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM chunk_summary WHERE run_id=%s", (run_id,))
    mdb_sum = cur.fetchone()[0]
    cur.close(); conn.close()

    # 3. Qdrant count
    qc = qdrant_client()
    info = qc.get_collection(qcol)
    qd_total = info.points_count

    # ingest_status='ready' filtered count
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    flt = Filter(must=[
        FieldCondition(key="run_id", match=MatchValue(value=run_id)),
        FieldCondition(key="ingest_status", match=MatchValue(value="ready")),
    ])
    qd_ready = qc.count(qcol, count_filter=flt, exact=True).count

    # 4. Neo4j counts
    drv = neo4j_driver()
    neo_counts = {}
    with drv.session() as s:
        for lbl in ("Organization", "Person", "BusinessGroup", "MacroIndicator",
                    "StatTable", "FilingDocument"):
            r = s.run(f"MATCH (n:{lbl}) RETURN count(n) AS c").single()
            neo_counts[lbl] = r["c"] if r else 0
        # run-scoped
        for lbl in ("Event", "Statement"):
            r = s.run(f"MATCH (n:{lbl} {{run_id: $rid}}) RETURN count(n) AS c", rid=run_id).single()
            neo_counts[lbl] = r["c"] if r else 0
        # rels (run_id)
        for rtype in ("EXECUTIVE_OF", "IS_MAJOR_SHAREHOLDER_OF", "INVESTS_IN",
                      "AFFILIATED_WITH", "hasActor", "wasDerivedFrom"):
            r = s.run(
                f"MATCH ()-[r:{rtype} {{run_id: $rid}}]->() RETURN count(r) AS c",
                rid=run_id
            ).single()
            neo_counts[f"rel_{rtype}"] = r["c"] if r else 0
    drv.close()

    print("── 카운트 비교 ──────────────────────────────────────────────")
    print(f"MariaDB chunk_index    total = {mdb_total:>7}  ready = {mdb_ready or 0:>7}")
    print(f"MariaDB document_index total = {mdb_docs:>7}")
    print(f"MariaDB chunk_summary  total = {mdb_sum:>7}")
    print(f"Qdrant  '{qcol}'        total = {qd_total:>7}  ready = {qd_ready:>7}")
    print()
    print("── Neo4j 노드/엣지 ──────────────────────────────────────────")
    for k, v in neo_counts.items():
        print(f"  {k:<32} {v:>7}")

    # 5. chunk_id 일관성 검증
    print("\n── Cross-DB chunk_id 일관성 ─────────────────────────────────")
    # 가장 단순한 비교: MariaDB total == Qdrant total
    if mdb_total == qd_total:
        print(f"  ✓ MariaDB({mdb_total}) == Qdrant({qd_total})")
    else:
        print(f"  ✗ 불일치: MariaDB({mdb_total}) ≠ Qdrant({qd_total})")
    if (mdb_ready or 0) == qd_ready:
        print(f"  ✓ ready: MariaDB({mdb_ready or 0}) == Qdrant({qd_ready})")
    else:
        print(f"  ⚠ ready 불일치: MariaDB({mdb_ready or 0}) vs Qdrant({qd_ready})")

    # 6. 샘플 round-trip 1건
    print("\n── 샘플 round-trip ─────────────────────────────────────────")
    conn = mariadb_conn(); cur = conn.cursor()
    cur.execute(
        "SELECT chunk_id, corp_code, chunk_type, embedding_text "
        "FROM chunk_index WHERE run_id=%s AND chunk_type='text_micro' LIMIT 1",
        (run_id,)
    )
    sample = cur.fetchone()
    cur.close(); conn.close()
    if sample:
        cid, corp, ctype, txt = sample
        print(f"  chunk_id={cid} corp={corp} type={ctype}")
        print(f"  text snippet: {txt[:100] if txt else '(empty)'}")
        # Qdrant lookup
        import hashlib
        uid = hashlib.md5(cid.encode("utf-8")).hexdigest()
        uid = f"{uid[0:8]}-{uid[8:12]}-{uid[12:16]}-{uid[16:20]}-{uid[20:32]}"
        try:
            pts = qc.retrieve(qcol, ids=[uid], with_payload=True, with_vectors=False)
            if pts:
                print(f"  ✓ Qdrant retrieve OK: payload.corp={pts[0].payload.get('corp_code')} "
                      f"payload.chunk_type={pts[0].payload.get('chunk_type')}")
            else:
                print(f"  ✗ Qdrant retrieve 빈 결과")
        except Exception as e:
            print(f"  ✗ Qdrant 오류: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
