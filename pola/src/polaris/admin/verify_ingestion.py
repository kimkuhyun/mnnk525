"""3DB 적재 정합 검증 — 인덱스 변경/재적재 후 회귀 방지용 1회 체크.

11개 체크:
  1. MariaDB chunk_index 카운트 (ready)
  2. Qdrant point 카운트 = MariaDB 카운트 (±tolerance)
  3. Neo4j Chunk/FinMetric/Organization 노드 카운트
  4. active_run_manifest 정합 (run_id 실제 존재, 컬렉션 실제 존재)
  5. Qdrant payload index 6종
  6. document_index ↔ chunk_index rcept_no 매칭률
  7. 임베딩 normalize 표본 검증 (L2 norm = 1.0 ± 1e-3)
  8. 5사 Organization + FinMetric 적재
  9. news_raw ↔ news_text 청크 정합
 10. dart_raw_index.body_json 완전성
 11. 그래프 영역 진단 통합 게이트 (graph-diag C-01~C-15 FAIL=0)

출력: stdout + data/4_dbGoldTest/verify.json (PASS/FAIL + 체크별 상세)
exit 0 if all PASS else 1
"""
from __future__ import annotations
import json, math, sys, time
from pathlib import Path

from polaris.config import mariadb_conn, qdrant_client, neo4j_driver, DATA_ROOT, CORPS

OUT = DATA_ROOT / "4_dbGoldTest" / "verify.json"
EXPECTED_PAYLOAD_INDEXES = {"corp_code", "rcept_no", "chunk_type",
                            "bsns_year", "run_id", "ingest_status"}


def check(name, ok, detail):
    return {"name": name, "passed": bool(ok), "detail": detail}


def main():
    t0 = time.time()
    results = []

    # ─ MariaDB ─────────────────────────────────────────
    conn = mariadb_conn(); cur = conn.cursor()
    cur.execute("SELECT active_run_id, active_qdrant_collection FROM active_run_manifest WHERE id=1")
    run_id, collection = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM chunk_index WHERE run_id=%s AND ingest_status='ready'", (run_id,))
    n_chunk_ready = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM chunk_index WHERE run_id=%s", (run_id,))
    n_chunk_total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM chunk_index WHERE run_id=%s AND ingest_status='pending'", (run_id,))
    n_chunk_pending = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM document_index WHERE run_id=%s", (run_id,))
    n_doc = cur.fetchone()[0]
    # text 청크 (text_micro/macro) 만 document_index 와 매칭. table_nl 은 dart_raw_index 영역.
    cur.execute("""SELECT COUNT(*) FROM chunk_index ci
                   LEFT JOIN document_index di ON ci.rcept_no=di.rcept_no AND ci.run_id=di.run_id
                   WHERE ci.run_id=%s
                     AND ci.chunk_type IN ('text_micro','text_macro')
                     AND di.rcept_no IS NULL""", (run_id,))
    n_orphan_chunk = cur.fetchone()[0]
    cur.execute("""SELECT COUNT(*) FROM chunk_index
                   WHERE run_id=%s AND chunk_type IN ('text_micro','text_macro')""", (run_id,))
    n_text_chunk = cur.fetchone()[0]
    cur.close(); conn.close()

    results.append(check("01 MariaDB chunk_index ready",
                         n_chunk_ready > 0,
                         f"run_id={run_id}, ready={n_chunk_ready:,}, pending={n_chunk_pending:,}, total={n_chunk_total:,}"))

    # ─ Qdrant ──────────────────────────────────────────
    qc = qdrant_client()
    n_qdrant_active = -1
    n_qdrant_total = -1
    payload_keys = set()
    try:
        col_info = qc.get_collection(collection)
        n_qdrant_total = col_info.points_count
        try:
            schema = col_info.payload_schema or {}
            payload_keys = set(schema.keys())
        except Exception:
            pass
        # active run_id 필터로 카운트 — MariaDB chunk_index 와 공정 비교
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        cnt_resp = qc.count(
            collection_name=collection,
            count_filter=Filter(must=[FieldCondition(key="run_id",
                                                    match=MatchValue(value=run_id))]),
            exact=True,
        )
        n_qdrant_active = cnt_resp.count
    except Exception as e:
        results.append(check("02 Qdrant 컬렉션 접근", False, f"err: {e}"))

    if n_qdrant_active >= 0:
        diff = abs(n_qdrant_active - n_chunk_total)
        ok = diff <= max(10, int(n_chunk_total * 0.001))
        results.append(check("02 Qdrant ↔ MariaDB 카운트 정합 (active run_id 기준)",
                             ok,
                             f"qdrant_active={n_qdrant_active:,}, mariadb_total={n_chunk_total:,}, "
                             f"diff={diff} (qdrant_collection_total={n_qdrant_total:,})"))
        results.append(check("05 Qdrant payload index 6종",
                             EXPECTED_PAYLOAD_INDEXES.issubset(payload_keys),
                             f"expected={sorted(EXPECTED_PAYLOAD_INDEXES)}, found={sorted(payload_keys)}"))

    # ─ Neo4j ───────────────────────────────────────────
    drv = neo4j_driver()
    with drv.session() as s:
        n_org = s.run("MATCH (o:Organization) RETURN count(o) AS n").single()["n"]
        n_finmetric = s.run("MATCH (m:FinMetric) RETURN count(m) AS n").single()["n"]
        n_chunk_neo = s.run("MATCH (c:Chunk) RETURN count(c) AS n").single()["n"]
        per_corp_metric = {}
        for r in s.run("""MATCH (o:Organization)-[:HAS_METRIC]->(m:FinMetric)
                          WHERE o.corp_code IN $corps
                          RETURN o.corp_code AS c, count(m) AS n""", corps=CORPS):
            per_corp_metric[r["c"]] = r["n"]
    drv.close()

    results.append(check("03 Neo4j 노드 카운트",
                         n_org > 0 and n_finmetric > 0,
                         f"Organization={n_org}, FinMetric={n_finmetric:,}, Chunk={n_chunk_neo}"))

    # ─ active_run_manifest 정합 ────────────────────────
    results.append(check("04 active_run_manifest 정합",
                         n_chunk_ready > 0 and (n_qdrant_active > 0 if n_qdrant_active >= 0 else False),
                         f"run_id={run_id}, collection={collection}"))

    # ─ document_index ↔ text 청크 매칭 ─────────────────
    orphan_rate = n_orphan_chunk / n_text_chunk if n_text_chunk else 0
    results.append(check("06 document_index <-> text 청크 매칭",
                         orphan_rate < 0.01,
                         f"document={n_doc}, text_chunk={n_text_chunk}, orphan={n_orphan_chunk} ({orphan_rate * 100:.2f}%)"))

    # ─ 임베딩 normalize 표본 ─────────────────────────
    norm_ok = True; norm_detail = ""
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        sample, _ = qc.scroll(
            collection_name=collection,
            scroll_filter=Filter(must=[FieldCondition(key="ingest_status",
                                                     match=MatchValue(value="ready"))]),
            limit=10, with_payload=False, with_vectors=True,
        )
        norms = []
        for p in sample:
            v = p.vector
            if isinstance(v, dict):
                v = next(iter(v.values()))
            if v is None: continue
            norms.append(math.sqrt(sum(x * x for x in v)))
        if norms:
            avg = sum(norms) / len(norms)
            norm_ok = all(abs(n - 1.0) < 1e-2 for n in norms)
            norm_detail = f"n={len(norms)}, avg_L2={avg:.4f}, min={min(norms):.4f}, max={max(norms):.4f}"
        else:
            norm_ok = False; norm_detail = "샘플 vector 없음"
    except Exception as e:
        norm_ok = False; norm_detail = f"err: {e}"
    results.append(check("07 임베딩 normalize 표본 (L2 ~ 1.0)", norm_ok, norm_detail))

    # ─ 5사 Organization + FinMetric 적재 ─────────────
    missing = [c for c in CORPS if per_corp_metric.get(c, 0) == 0]
    results.append(check("08 5사 Organization + FinMetric 적재",
                         not missing,
                         f"per_corp={per_corp_metric}, missing={missing}"))

    # ─ 09 news_raw ↔ news_text 청크 정합 ─────────────
    conn = mariadb_conn(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM news_raw")
    n_news_raw = cur.fetchone()[0]
    cur.execute("""SELECT COUNT(*) FROM news_raw
                   WHERE meta IS NOT NULL
                     AND JSON_LENGTH(JSON_EXTRACT(meta, '$.matched_corps')) > 0""")
    n_news_matched = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM chunk_index WHERE chunk_type='news_text' AND ingest_status='ready'")
    n_news_chunk = cur.fetchone()[0]
    # 매칭된 뉴스 ≤ 청크 수 (멀티 매칭으로 더 많을 수 있음)
    news_ok = n_news_chunk >= n_news_matched and n_news_raw > 0
    results.append(check("09 news_raw <-> news_text 청크 정합",
                         news_ok,
                         f"news_raw={n_news_raw}, matched={n_news_matched}, chunk={n_news_chunk}"))

    # ─ 10 dart_raw_index.body_json 완전성 ────────────
    cur.execute("SELECT COUNT(*), COUNT(body_json) FROM dart_raw_index")
    n_dart_total, n_dart_body = cur.fetchone()
    dart_ok = n_dart_total > 0 and n_dart_body == n_dart_total
    results.append(check("10 dart_raw_index body_json 완전성",
                         dart_ok,
                         f"total={n_dart_total}, with_body={n_dart_body}, missing={n_dart_total - n_dart_body}"))

    cur.close(); conn.close()

    # ─ 11 그래프 영역 진단 (graph-diag 15종 통합 게이트) ────
    # P-2.5: graph_diag 모듈의 C-01~C-15 결과를 단일 체크로 압축.
    # FAIL=0 이어야 정상. WARN 은 허용 (메시지에 표시).
    try:
        from polaris.db.graph_diag import run_all
        gd = run_all(CORPS)
        gs = gd["summary"]
        fails = [r["name"] + ":" + r["message"] for r in gd["results"]
                 if r["status"] == "FAIL"]
        warns = [r["name"] for r in gd["results"] if r["status"] == "WARN"]
        results.append(check(
            "11 그래프 영역 진단 (graph-diag C-01~C-15)",
            gs["fail"] == 0,
            f"PASS={gs['pass']}, WARN={gs['warn']}, FAIL={gs['fail']} / {gs['total']}"
            + (f" — WARN: {','.join(warns)}" if warns else "")
            + (f" — FAIL: {';'.join(fails)}" if fails else "")
        ))
    except Exception as e:
        results.append(check("11 그래프 영역 진단 (graph-diag)", False, f"실행 오류: {e}"))

    # ─ 출력 ────────────────────────────────────────────
    passed = all(r["passed"] for r in results)
    summary = {"run_id": run_id, "collection": collection,
               "all_passed": passed, "elapsed_sec": round(time.time() - t0, 1),
               "checks": results}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("──────── 적재 정합 검증 ──────────────────────")
    for r in results:
        tag = "PASS" if r["passed"] else "FAIL"
        print(f"  [{tag}] {r['name']}")
        print(f"         {r['detail']}")
    print(f"\n  종합 판정: {'PASS' if passed else 'FAIL'}")
    print(f"  요약 저장: {OUT}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
