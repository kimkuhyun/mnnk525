"""Cypher 진단 15종 (C-01~C-15) 라이브러리.

정형 그래프 무결성·확장성 점검. 모두 read-only.
사용: polaris graph-diag [--json]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from polaris.config import CORPS, DATA_ROOT, neo4j_driver

# Neo4j unknown label/relationship 경고는 진단 출력에 noise 라 silence
logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)
logging.getLogger("neo4j").setLevel(logging.ERROR)


# 보고서 코드: 11013=1Q, 11012=Reg(반기), 11014=3Q, 11011=Annual(사업)
EXPECTED_REPRT_CODES = ["11011", "11012", "11013", "11014"]
EXPECTED_YEARS = [2024, 2025, 2026]  # 사용자 우선순위: 2024(과거 참조), 2025(핵심), 2026(1분기)

# (year, reprt_code) — 발표 시점 고려. 2026은 1분기만 expected.
EXPECTED_YEAR_REPRT: list[tuple[int, str]] = [
    (2024, "11013"), (2024, "11012"), (2024, "11014"), (2024, "11011"),
    (2025, "11013"), (2025, "11012"), (2025, "11014"), (2025, "11011"),
    (2026, "11013"),  # 1분기만 (반기/3Q/사업보고서 미발표)
]
EXPECTED_FS_DIV = {"OFS", "CFS"}
EXPECTED_SJ_DIV = {"BS", "BS1", "BS2", "IS", "IS1", "IS2", "CIS", "CIS1", "CIS2",
                   "CF", "CF1", "CF2", "SCE", "SCE1", "SCE2"}


def _ok(name: str, message: str, payload: dict | None = None) -> dict:
    return {"name": name, "status": "PASS", "message": message, "payload": payload or {}}


def _fail(name: str, message: str, payload: dict | None = None) -> dict:
    return {"name": name, "status": "FAIL", "message": message, "payload": payload or {}}


def _warn(name: str, message: str, payload: dict | None = None) -> dict:
    return {"name": name, "status": "WARN", "message": message, "payload": payload or {}}


# ---------------- C-01 Organization 적재 완전성 ----------------

def c01_organization_completeness(session, env_corps: list[str]) -> dict:
    """env CORPS 의 모든 회사가 Neo4j Organization 노드로 있는가."""
    in_db = [r["cc"] for r in session.run(
        "MATCH (o:Organization) RETURN o.corp_code AS cc"
    )]
    missing = [c for c in env_corps if c not in in_db]
    extra_count = len([c for c in in_db if c not in env_corps])
    if missing:
        return _fail("C-01", f"env CORPS 중 {len(missing)}개 누락",
                     {"missing": missing, "in_db_total": len(in_db), "extra_count": extra_count})
    return _ok("C-01", f"env {len(env_corps)}사 모두 적재 (Neo4j 전체 {len(in_db)})",
               {"env_count": len(env_corps), "in_db_total": len(in_db), "extra_count": extra_count})


# ---------------- C-02 Organization 필수 속성 누락 ----------------

def c02_organization_required_attrs(session, env_corps: list[str]) -> dict:
    """env CORPS Organization 의 name/stock_code/jurirno/bizrno 결측."""
    rows = session.run("""
        MATCH (o:Organization) WHERE o.corp_code IN $cc
        RETURN o.corp_code AS cc,
               o.name AS name, o.stock_code AS stock_code,
               o.jurirno AS jurirno, o.bizrno AS bizrno
    """, cc=env_corps).data()
    missing_name = [r["cc"] for r in rows if not r.get("name")]
    missing_stock = [r["cc"] for r in rows if not r.get("stock_code")]
    missing_jurirno = [r["cc"] for r in rows if not r.get("jurirno")]
    missing_bizrno = [r["cc"] for r in rows if not r.get("bizrno")]
    payload = {"missing_name": missing_name, "missing_stock": missing_stock,
               "missing_jurirno": missing_jurirno, "missing_bizrno": missing_bizrno}
    if missing_name or missing_stock:
        return _fail("C-02", f"name 누락 {len(missing_name)}, stock 누락 {len(missing_stock)}",
                     payload)
    if missing_jurirno or missing_bizrno:
        return _warn("C-02", f"jurirno 누락 {len(missing_jurirno)}, bizrno 누락 {len(missing_bizrno)} (corps.json 미보강)",
                     payload)
    return _ok("C-02", "필수 속성 모두 채워짐", payload)


# ---------------- C-03 회사별 FinMetric 분포 ----------------

def c03_finmetric_per_corp(session, env_corps: list[str]) -> dict:
    rows = session.run("""
        MATCH (o:Organization) WHERE o.corp_code IN $cc
        OPTIONAL MATCH (o)-[:HAS_METRIC]->(m:FinMetric)
        RETURN o.corp_code AS cc, o.name AS name,
               count(m) AS total,
               count(DISTINCT m.year) AS years,
               count(DISTINCT m.reprt_code) AS reprts
        ORDER BY total DESC
    """, cc=env_corps).data()
    if not rows:
        return _fail("C-03", "FinMetric 없음", {})
    totals = [r["total"] for r in rows]
    avg = sum(totals) / len(totals) if totals else 0
    # 평균 ±50% 이내가 정상 (한 회사만 너무 적으면 누락 의심)
    outliers = [r["cc"] for r in rows if avg and (r["total"] < avg * 0.3 or r["total"] > avg * 3)]
    payload = {"per_corp": rows, "avg": int(avg), "outliers": outliers}
    if any(r["total"] == 0 for r in rows):
        zeros = [r["cc"] for r in rows if r["total"] == 0]
        return _fail("C-03", f"FinMetric 0건 회사 {len(zeros)}", payload | {"zeros": zeros})
    if outliers:
        return _warn("C-03", f"분포 이상 회사 {len(outliers)} (avg {int(avg)} 대비 ±70% 초과)", payload)
    return _ok("C-03", f"분포 균일 (avg {int(avg)}/회사)", payload)


# ---------------- C-04 회사·연도·보고서 매트릭스 cover-rate ----------------

def c04_year_reprt_cover(session, env_corps: list[str]) -> dict:
    """회사 × EXPECTED_YEAR_REPRT 매트릭스 cover. 80% 이상 정상."""
    rows = session.run("""
        MATCH (o:Organization) WHERE o.corp_code IN $cc
        OPTIONAL MATCH (o)-[:HAS_METRIC]->(m:FinMetric)
        RETURN o.corp_code AS cc,
               collect(DISTINCT [m.year, m.reprt_code]) AS pairs
    """, cc=env_corps).data()
    total_cells = len(env_corps) * len(EXPECTED_YEAR_REPRT)
    filled = 0
    per_corp_cover = {}
    for r in rows:
        pairs_set = {tuple(p) for p in r["pairs"] if p and p[0] is not None}
        c = sum(1 for yr in EXPECTED_YEAR_REPRT if yr in pairs_set)
        per_corp_cover[r["cc"]] = c
        filled += c
    cover = filled / total_cells if total_cells else 0
    payload = {"cover_rate": round(cover, 3), "filled": filled, "total": total_cells,
               "per_corp_cells": per_corp_cover, "expected_per_corp": len(EXPECTED_YEAR_REPRT)}
    if cover < 0.5:
        return _fail("C-04", f"cover-rate {cover:.1%} < 50% (심각한 데이터 누락)", payload)
    if cover < 0.8:
        return _warn("C-04", f"cover-rate {cover:.1%} (50~80% — 일부 연도/보고서 누락)", payload)
    return _ok("C-04", f"cover-rate {cover:.1%} (≥80%)", payload)


# ---------------- C-05 FinMetric 고아 ----------------

def c05_orphan_finmetric(session) -> dict:
    rows = session.run("""
        MATCH (m:FinMetric)
        WHERE NOT (m)<-[:HAS_METRIC]-(:Organization)
        RETURN count(m) AS n
    """).single()
    n = rows["n"]
    if n > 0:
        return _fail("C-05", f"고아 FinMetric {n}개", {"orphan_count": n})
    return _ok("C-05", "고아 노드 없음", {"orphan_count": 0})


# ---------------- C-06 fs_div / sj_div 분포 정합 ----------------

def c06_fs_sj_div_sanity(session) -> dict:
    rows = session.run("""
        MATCH (m:FinMetric)
        RETURN m.fs_div AS fs, m.sj_div AS sj, m.reprt_code AS rc, count(*) AS n
        ORDER BY n DESC
    """).data()
    unexpected_fs = [r for r in rows if r["fs"] and r["fs"] not in EXPECTED_FS_DIV]
    unexpected_sj = [r for r in rows if r["sj"] and r["sj"] not in EXPECTED_SJ_DIV]
    unexpected_rc = [r for r in rows if r["rc"] and r["rc"] not in EXPECTED_REPRT_CODES]
    payload = {"distinct_combinations": len(rows),
               "unexpected_fs": unexpected_fs[:10],
               "unexpected_sj": unexpected_sj[:10],
               "unexpected_rc": unexpected_rc[:10]}
    if unexpected_fs or unexpected_sj or unexpected_rc:
        return _warn("C-06", f"예상 외 값 — fs {len(unexpected_fs)}, sj {len(unexpected_sj)}, rc {len(unexpected_rc)}",
                     payload)
    return _ok("C-06", f"fs_div/sj_div/reprt_code 모두 expected 셋 내 ({len(rows)} 조합)", payload)


# ---------------- C-07 metric_id 충돌 ----------------

def c07_metric_id_collisions(session) -> dict:
    rows = session.run("""
        MATCH (m:FinMetric)
        WITH m.metric_id AS id, count(*) AS n WHERE n > 1
        RETURN id, n ORDER BY n DESC LIMIT 20
    """).data()
    if rows:
        return _fail("C-07", f"metric_id 충돌 {len(rows)}", {"collisions": rows})
    return _ok("C-07", "metric_id 충돌 없음", {})


# ---------------- C-08 HAS_METRIC 엣지 run_id 일관성 ----------------

def c08_has_metric_run_id(session) -> dict:
    r = session.run("""
        MATCH (o:Organization)-[h:HAS_METRIC]->(m:FinMetric)
        WHERE h.run_id IS NOT NULL AND m.run_id IS NOT NULL
              AND h.run_id <> m.run_id
        RETURN count(*) AS mismatch
    """).single()
    n = r["mismatch"]
    if n > 0:
        return _fail("C-08", f"HAS_METRIC run_id mismatch {n}", {"mismatch": n})
    return _ok("C-08", "HAS_METRIC run_id 일관", {})


# ---------------- C-09 FinMetric ↔ FilingDocument 연결 (Provenance) ----------------

def c09_finmetric_filingdocument_link(session) -> dict:
    """FinMetric 에 rcept_no 가 있고 DERIVED_FROM 엣지가 있는가."""
    r = session.run("""
        MATCH (m:FinMetric)
        RETURN count(m) AS total,
               sum(CASE WHEN m.rcept_no IS NOT NULL THEN 1 ELSE 0 END) AS with_rcept,
               sum(CASE WHEN (m)-[:DERIVED_FROM]->(:FilingDocument) THEN 1 ELSE 0 END) AS with_edge
    """).single()
    total = r["total"]
    with_rcept = r["with_rcept"]
    with_edge = r["with_edge"]
    payload = {"total": total, "with_rcept": with_rcept, "with_edge": with_edge}
    if total == 0:
        return _warn("C-09", "FinMetric 없음", payload)
    rcept_pct = with_rcept / total
    if rcept_pct < 0.95:
        return _fail("C-09", f"PROV 끊김: rcept_no {rcept_pct:.1%} (S-01 적용 전)", payload)
    return _ok("C-09", f"PROV 연결 {with_edge}/{total} (rcept_no {rcept_pct:.1%})", payload)


# ---------------- C-10 Person / EXECUTIVE_OF 회사별 분포 ----------------

def c10_person_executive(session, env_corps: list[str]) -> dict:
    rows = session.run("""
        UNWIND $cc AS corp
        MATCH (o:Organization {corp_code: corp})
        OPTIONAL MATCH (p:Person)-[:EXECUTIVE_OF]->(o)
        RETURN corp AS cc, count(p) AS executives
        ORDER BY executives DESC
    """, cc=env_corps).data()
    zeros = [r["cc"] for r in rows if r["executives"] == 0]
    payload = {"per_corp": rows, "zeros": zeros}
    if zeros:
        return _fail("C-10", f"EXECUTIVE_OF 0건 회사 {len(zeros)} (P-2.3 extract_persons 미실행)",
                     payload)
    return _ok("C-10", f"모든 회사 EXECUTIVE_OF ≥1", payload)


# ---------------- C-11 BusinessGroup ↔ AFFILIATED_WITH ↔ Organization ----------------

def c11_affiliated_with(session, env_corps: list[str]) -> dict:
    rows = session.run("""
        UNWIND $cc AS corp
        MATCH (o:Organization {corp_code: corp})
        OPTIONAL MATCH (o)-[:AFFILIATED_WITH]->(bg:BusinessGroup)
        RETURN corp AS cc, collect(bg.name)[..5] AS groups, count(bg) AS n
    """, cc=env_corps).data()
    zeros = [r["cc"] for r in rows if r["n"] == 0]
    payload = {"per_corp": rows, "zeros": zeros}
    if zeros:
        return _warn("C-11", f"AFFILIATED_WITH 0건 회사 {len(zeros)} (P-2.3 extract_ftc_groups 미실행 또는 비계열사)",
                     payload)
    return _ok("C-11", "모든 회사 AFFILIATED_WITH ≥1", payload)


# ---------------- C-12 LLMExtracted vs 정형 충돌 ----------------

def c12_llmextracted_isolation(session) -> dict:
    """LLMExtracted 격리 — ADR 008 정책:
    - 정형 한국 회사 (8자리 숫자 corp_code) Organization 에 :LLMExtracted 부착 금지
    - FinMetric 에 절대 부착 금지
    - 외부 회사 (X로 시작) 는 :Organization:LLMExtracted 혼합 정상."""
    conflicts = session.run("""
        MATCH (n)
        WHERE 'LLMExtracted' IN labels(n)
          AND (
            ('Organization' IN labels(n) AND n.corp_code =~ '\\d{8}')
            OR 'FinMetric' IN labels(n)
          )
        RETURN labels(n) AS lbs, n.corp_code AS cc, count(*) AS n
    """).data()
    if conflicts:
        return _fail("C-12", f"LLMExtracted 정형 충돌 {len(conflicts)}건",
                     {"conflicts": conflicts})
    total_llm = session.run(
        "MATCH (n:LLMExtracted) RETURN count(n) AS n"
    ).single()["n"]
    ext_org = session.run(
        "MATCH (n:Organization:LLMExtracted) RETURN count(n) AS n"
    ).single()["n"]
    return _ok("C-12",
               f"격리 OK (total LLMExtracted={total_llm}, external Org={ext_org})",
               {"total_llmextracted": total_llm, "external_org": ext_org})


# ---------------- C-13 인덱스/제약 카탈로그 점검 ----------------

EXPECTED_CONSTRAINTS = {
    "Organization": "corp_code", "Person": "person_id",
    "BusinessGroup": "unityGrupCode", "FilingDocument": "rcept_no",
    "FinancialInstrument": "instrument_id", "Product": "product_id",
    "Place": "iso_code",
    # NewsArticle 키는 P-2.2 후 news_id 로 변경 (현재 document_id)
}


def c13_constraints_catalog(session) -> dict:
    rows = session.run(
        "SHOW CONSTRAINTS YIELD name, labelsOrTypes, properties, type"
    ).data()
    by_label_prop = {(r["labelsOrTypes"][0], r["properties"][0]): r["name"]
                     for r in rows if r["labelsOrTypes"] and r["properties"]}
    missing = []
    for label, prop in EXPECTED_CONSTRAINTS.items():
        if (label, prop) not in by_label_prop:
            missing.append(f"{label}.{prop}")
    payload = {"total": len(rows), "missing": missing}
    if missing:
        return _fail("C-13", f"제약 누락 {len(missing)}: {missing}", payload)
    return _ok("C-13", f"제약 카탈로그 OK ({len(rows)} constraints)", payload)


# ---------------- C-14 NewsArticle 자연키 일관성 ----------------

def c14_newsarticle_keys(session) -> dict:
    r = session.run("""
        MATCH (n:NewsArticle)
        RETURN count(*) AS total,
               sum(CASE WHEN n.news_id IS NULL THEN 1 ELSE 0 END) AS no_news_id,
               sum(CASE WHEN n.document_id IS NULL THEN 1 ELSE 0 END) AS no_document_id
    """).single()
    total = r["total"]
    no_news = r["no_news_id"]
    no_doc = r["no_document_id"]
    payload = {"total": total, "no_news_id": no_news, "no_document_id": no_doc}
    if total == 0:
        return _warn("C-14", "NewsArticle 없음", payload)
    # P-2.2 미적용 상태: 제약은 document_id, 적재는 news_id → no_document_id 가 많을 것
    if no_news > 0:
        return _fail("C-14", f"news_id 누락 {no_news}/{total} (P-2.2 통일 필요)", payload)
    if no_doc > 0:
        return _warn("C-14", f"document_id 누락 {no_doc}/{total} — P-2.2 후 정상 (제약 news_id로 이동)", payload)
    return _ok("C-14", "news_id/document_id 양립 일관", payload)


# ---------------- C-15 run_id 분포 (Blue/Green 슬롯 점유) ----------------

def c15_run_id_distribution(session) -> dict:
    rows = session.run("""
        MATCH (m:FinMetric) RETURN m.run_id AS run, count(*) AS n
        ORDER BY n DESC LIMIT 20
    """).data()
    payload = {"finmetric_per_run": rows, "distinct_runs": len(rows)}
    if len(rows) > 3:
        return _warn("C-15", f"FinMetric run_id 슬롯 {len(rows)}개 (cleanup 권장)", payload)
    return _ok("C-15", f"FinMetric run_id 슬롯 {len(rows)}개", payload)


# ---------------- runner ----------------

DIAGNOSTICS = [
    ("C-01", c01_organization_completeness, ["env_corps"]),
    ("C-02", c02_organization_required_attrs, ["env_corps"]),
    ("C-03", c03_finmetric_per_corp, ["env_corps"]),
    ("C-04", c04_year_reprt_cover, ["env_corps"]),
    ("C-05", c05_orphan_finmetric, []),
    ("C-06", c06_fs_sj_div_sanity, []),
    ("C-07", c07_metric_id_collisions, []),
    ("C-08", c08_has_metric_run_id, []),
    ("C-09", c09_finmetric_filingdocument_link, []),
    ("C-10", c10_person_executive, ["env_corps"]),
    ("C-11", c11_affiliated_with, ["env_corps"]),
    ("C-12", c12_llmextracted_isolation, []),
    ("C-13", c13_constraints_catalog, []),
    ("C-14", c14_newsarticle_keys, []),
    ("C-15", c15_run_id_distribution, []),
]


def run_all(env_corps: list[str], corp_filter: str | None = None) -> dict:
    drv = neo4j_driver()
    results: list[dict] = []
    effective_corps = [corp_filter] if corp_filter else env_corps
    with drv.session() as s:
        for name, fn, args in DIAGNOSTICS:
            try:
                kwargs = {"env_corps": effective_corps} if "env_corps" in args else {}
                res = fn(s, **kwargs) if kwargs else fn(s)
            except Exception as e:
                res = _fail(name, f"실행 오류: {e}", {"error": str(e)})
            results.append(res)
    drv.close()
    summary = {
        "pass": sum(1 for r in results if r["status"] == "PASS"),
        "warn": sum(1 for r in results if r["status"] == "WARN"),
        "fail": sum(1 for r in results if r["status"] == "FAIL"),
        "total": len(results),
    }
    return {
        "timestamp": datetime.now().isoformat(),
        "env_corps": effective_corps,
        "summary": summary,
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="POLARIS Neo4j 그래프 진단 (C-01~C-15)")
    parser.add_argument("--json", action="store_true", help="JSON 만 출력 (파이핑용)")
    parser.add_argument("--corp", type=str, default=None,
                        help="단일 회사 corp_code 만 진단 (없으면 .env CORPS 전체)")
    parser.add_argument("--out", type=str, default=None,
                        help="결과 JSON 저장 경로 (없으면 data/4_dbGoldTest/graph_diag.json)")
    args = parser.parse_args()

    report = run_all(CORPS, corp_filter=args.corp)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print("──────── 그래프 진단 (Neo4j 정형 영역) ──────────────────────")
        print(f"  env_corps={report['env_corps']}")
        s = report["summary"]
        print(f"  PASS={s['pass']}, WARN={s['warn']}, FAIL={s['fail']} / total={s['total']}")
        print()
        for r in report["results"]:
            mark = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}[r["status"]]
            print(f"  {mark} {r['name']}: {r['message']}")
        print()

    out_path = Path(args.out) if args.out else DATA_ROOT / "4_dbGoldTest" / "graph_diag.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8")
    if not args.json:
        print(f"  요약 저장: {out_path}")

    return 1 if report["summary"]["fail"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
