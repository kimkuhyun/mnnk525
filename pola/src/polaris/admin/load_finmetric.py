"""FinMetric 노드 적재 (설계 03 §C-4 누락분 보완).

소스: ___test/2_Chuck/01_filtered/{corp}/dart/fnlttSinglAcntAll__*.json
출력: Neo4j (Organization)-[:HAS_METRIC]->(FinMetric)

스키마 (설계 03 §C-4):
  FinMetric {
    metric_id: hash(corp+year+indicator+fs_div+sj_div+reprt_code),
    indicator, year, fs_div (OFS/CFS),
    sj_div (BS/IS/CIS/CF/SCE),
    value, unit, account_id, reprt_code, run_id
  }
  HAS_METRIC { run_id, rcept_no, reprt_code, bsns_year, fs_div }
    — 출처 메타를 엣지에도 복제 (1-hop Cypher 검증성).

비교 쿼리 Cypher (예시):
  MATCH (o:Organization)-[:HAS_METRIC]->(m:FinMetric)
  WHERE o.corp_code IN ['00161383','00118804']
    AND m.year=2024 AND m.indicator='부채총계'
    AND m.reprt_code='11011'  // 사업보고서 우선
  RETURN o.name, m.value, m.fs_div
"""
from __future__ import annotations
import hashlib, json, re, sys
from pathlib import Path

from polaris.config import (neo4j_driver, mariadb_conn,
                            FILTERED_DIR as FILTERED, DATA_ROOT, CORPS, get_corp_meta)


def metric_id(corp, year, indicator, fs_div, sj_div, reprt_code):
    s = f"{corp}|{year}|{indicator}|{fs_div}|{sj_div}|{reprt_code}"
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:16]


_NUM_RE = re.compile(r"[\d,.\-△()]+")


def parse_amount(raw):
    """thstrm_amount 정수 파싱. '△123,456' 또는 '(123,456)' = 음수."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s in ("-", "—"):
        return None
    neg = False
    if s.startswith("△") or s.startswith("-"):
        neg = True
        s = s.lstrip("△-")
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    s = s.replace(",", "").replace(" ", "")
    try:
        v = int(float(s))
        return -v if neg else v
    except (ValueError, TypeError):
        return None


def get_active_run_id():
    """환경변수 POLARIS_TARGET_RUN_ID 가 있으면 그것을 사용 (build 안에서 standby_run_id 강제용)."""
    import os
    target = os.environ.get("POLARIS_TARGET_RUN_ID", "").strip()
    if target:
        return target
    conn = mariadb_conn(); cur = conn.cursor()
    cur.execute("SELECT active_run_id FROM active_run_manifest WHERE id=1")
    rid = cur.fetchone()[0]
    cur.close(); conn.close()
    return rid


def ensure_index(session):
    session.run("CREATE INDEX finmetric_id IF NOT EXISTS FOR (m:FinMetric) ON (m.metric_id)")
    session.run("CREATE INDEX finmetric_lookup IF NOT EXISTS FOR (m:FinMetric) ON (m.year, m.indicator)")
    session.run("CREATE INDEX org_corp IF NOT EXISTS FOR (o:Organization) ON (o.corp_code)")


def ensure_organizations(session, corps):
    """CORPS 의 모든 회사에 대해 Organization 노드 idempotent MERGE.
    신규 회사 추가 시 자동으로 Organization 노드 생성."""
    n = 0
    for cc in corps:
        meta = get_corp_meta(cc)
        session.run("""MERGE (o:Organization {corp_code: $cc})
                       SET o.name = $name,
                           o.stock_code = $stock""",
                    cc=cc, name=meta.get("corp_name", cc),
                    stock=meta.get("stock_code", ""))
        n += 1
    print(f"[finmetric] Organization MERGE: {n} (신규 포함)")


def collect_batch():
    """전체 CORPS × fnlttSinglAcntAll JSON → 적재용 row 리스트.
    raw (DATA_ROOT/rawData) 우선, 없으면 FILTERED (옛 정제 산출물) fallback."""
    rows = []
    for corp in CORPS:
        for base in (DATA_ROOT / "rawData" / corp / "dart",
                     FILTERED / corp / "dart"):
            if base.is_dir():
                dart_dir = base
                break
        else:
            continue
        for jf in sorted(dart_dir.glob("fnlttSinglAcntAll__*.json")):
            doc = json.loads(jf.read_text(encoding="utf-8"))
            if doc.get("status") != "ok":
                continue
            params = doc.get("params", {})
            try:
                bsns_year = int(params.get("bsns_year", 0))
            except (TypeError, ValueError):
                continue
            fs_div = params.get("fs_div", "")
            reprt_code = params.get("reprt_code", "")
            for r in doc.get("data", {}).get("list", []) or []:
                indicator = (r.get("account_nm") or "").strip()
                if not indicator or indicator.startswith("(") or "공시되지" in indicator:
                    continue
                value = parse_amount(r.get("thstrm_amount"))
                if value is None:
                    continue
                sj_div = r.get("sj_div", "")
                account_id = (r.get("account_id") or "").strip()
                if account_id == "-표준계정코드 미사용-":
                    account_id = ""
                # rcept_no 는 응답 list[i].rcept_no 에 있음 (PROV-O 추적용)
                rcept_no = (r.get("rcept_no") or "").strip()
                mid = metric_id(corp, bsns_year, indicator, fs_div, sj_div, reprt_code)
                rows.append({
                    "corp": corp, "mid": mid, "indicator": indicator,
                    "year": bsns_year, "fs_div": fs_div, "sj_div": sj_div,
                    "value": value, "account_id": account_id,
                    "reprt_code": reprt_code, "rcept_no": rcept_no,
                })
    return rows


def main():
    run_id = get_active_run_id()
    print(f"[finmetric] active run_id = {run_id}")
    print("[finmetric] DART JSON 스캔 …")
    rows = collect_batch()
    print(f"[finmetric] 적재 후보: {len(rows):,} rows")
    if not rows:
        return 0

    drv = neo4j_driver()
    with drv.session() as s:
        ensure_index(s)
        ensure_organizations(s, CORPS)
        # UNWIND batch
        BATCH = 500
        for i in range(0, len(rows), BATCH):
            batch = rows[i:i + BATCH]
            for r in batch:
                r["run_id"] = run_id
            # 1단계: FinMetric MERGE + HAS_METRIC 단일 엣지 (run_id mismatch 방지)
            s.run("""
            UNWIND $rows AS r
            MATCH (o:Organization {corp_code: r.corp})
            MERGE (m:FinMetric {metric_id: r.mid})
              SET m.indicator = r.indicator,
                  m.year = r.year,
                  m.fs_div = r.fs_div,
                  m.sj_div = r.sj_div,
                  m.value = r.value,
                  m.account_id = r.account_id,
                  m.reprt_code = r.reprt_code,
                  m.rcept_no = r.rcept_no,
                  m.run_id = r.run_id,
                  m.unit = 'KRW'
            MERGE (o)-[h:HAS_METRIC]->(m)
              ON CREATE SET h.first_seen_run_id = r.run_id
            SET h.run_id = r.run_id, h.last_updated_run_id = r.run_id,
                h.rcept_no = r.rcept_no,
                h.reprt_code = r.reprt_code,
                h.bsns_year = r.year,
                h.fs_div = r.fs_div
            """, rows=batch)
            # 2단계: DERIVED_FROM 엣지 (FilingDocument 존재 시만, PROV-O)
            s.run("""
            UNWIND $rows AS r
            WITH r WHERE r.rcept_no IS NOT NULL AND r.rcept_no <> ''
            MATCH (m:FinMetric {metric_id: r.mid})
            MATCH (fd:FilingDocument {rcept_no: r.rcept_no})
            MERGE (m)-[d:DERIVED_FROM]->(fd)
              ON CREATE SET d.first_seen_run_id = r.run_id
            SET d.run_id = r.run_id
            """, rows=batch)
            print(f"  loaded {min(i + BATCH, len(rows)):,} / {len(rows):,}")

        # 3단계: 옛 mismatch HAS_METRIC 엣지 cleanup
        # (이전 코드가 MERGE (o)-[h:HAS_METRIC {run_id: ...}]->(m) 로 만든 중복 엣지)
        # 같은 (o,m) 사이에 엣지 1개만 남도록 dedup
        cleanup = s.run("""
        MATCH (o:Organization)-[h:HAS_METRIC]->(m:FinMetric)
        WITH o, m, collect(h) AS edges
        WHERE size(edges) > 1
        WITH o, m, edges[0] AS keep, edges[1..] AS dups
        FOREACH (d IN dups | DELETE d)
        RETURN count(*) AS pairs_deduped
        """).single()
        print(f"[finmetric] HAS_METRIC dedup: {cleanup['pairs_deduped']} (o,m) pairs")

    drv.close()
    print(f"[finmetric] 완료. {len(rows):,} FinMetric 노드")
    return 0


if __name__ == "__main__":
    sys.exit(main())
