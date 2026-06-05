"""연결 28개사 재무 적재 — extra_finance/raw → MariaDB fin_metric + Neo4j.

멱등. 각 회사는 자기 corp_code 로만(오염 금지). 수치는 DART 응답 그대로.

1) MariaDB fin_metric upsert (graph/load_finmetric.py 와 동일 규칙).
2) Neo4j: 기존 needs_er Organization 노드(이름 변형 포함)에 corp_code 부여 + needs_er=false.
   새 Organization 노드 만들지 않음(기존 지분/계열 엣지 보존).
   FinMetric + HAS_METRIC(Org→FinMetric). v3: FilingDocument/DERIVED_FROM 제거(출처=rcept_no 속성).
3) 재무없는 비상장사는 corp_code 만 부여, FinMetric 생략.

실행: cd db && uv run python extra_finance/load_extra_finance.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "graph"))

from db import mariadb_conn, metric_id, neo4j_driver, parse_number  # noqa: E402

RAW = HERE / "raw"
REPRT_CODE = "11011"

# ── 28개사: corp_code → ER 검증된 이름 변형 토큰 목록 ──
# 각 회사의 needs_er 노드를 이름으로 찾기 위한 "정규화 후 부분일치" 스템(distinctive).
# 다른 회사와 절대 겹치지 않는 토큰만 사용(오염 방지). 공백 제거·소문자 비교.
# 한 회사에 변형 여러 개면(SK/에스케이) 모두 같은 corp_code 부여.
TARGETS: dict[str, dict] = {
    "00126362": {"name": "삼성SDI", "stems": ["삼성sdi"]},
    "00126371": {"name": "삼성전기", "stems": ["삼성전기"]},
    "00126186": {"name": "삼성에스디에스", "stems": ["삼성에스디에스"]},
    "00912006": {"name": "삼성디스플레이", "stems": ["삼성디스플레이"]},
    "00149655": {"name": "삼성물산", "stems": ["삼성물산"]},
    "00126256": {"name": "삼성생명보험", "stems": ["삼성생명보험"]},
    "00139214": {"name": "삼성화재해상보험", "stems": ["삼성화재해상보험"]},
    "00126478": {"name": "삼성중공업", "stems": ["삼성중공업"]},
    "00877059": {"name": "삼성바이오로직스", "stems": ["삼성바이오로직스"]},
    "00148276": {"name": "제일기획", "stems": ["제일기획"]},
    "00158501": {"name": "에스원", "stems": ["에스원"]},
    "00165680": {"name": "호텔신라", "stems": ["호텔신라"]},
    "00181712": {"name": "SK", "stems": []},  # 'SK' 단독 — 부분일치 위험 → 정확매칭만(아래 EXACT)
    "01596425": {"name": "SK스퀘어", "stems": ["sk스퀘어"]},
    "01555631": {"name": "에스케이키파운드리", "stems": ["에스케이키파운드리", "sk키파운드리"]},
    "01265516": {"name": "에스케이하이닉스시스템아이씨",
                 "stems": ["에스케이하이닉스시스템아이씨", "sk하이닉스시스템아이씨", "sk하이닉스시스템ic"]},
    "00652706": {"name": "에스케이하이스텍", "stems": ["에스케이하이스텍", "sk하이스텍"]},
    "00415390": {"name": "에스케이하이이엔지", "stems": ["에스케이하이이엔지", "sk하이이엔지"]},
    "00560070": {"name": "한미네트웍스", "stems": ["한미네트웍스"]},
    "01241987": {"name": "한화세미텍", "stems": ["한화세미텍"]},
    "00118804": {"name": "동진쎄미켐", "stems": ["동진쎄미켐"]},
    "01489648": {"name": "솔브레인", "stems": ["솔브레인"]},
    "01135941": {"name": "원익아이피에스", "stems": ["원익아이피에스", "원익ips"]},
    "00216647": {"name": "원익홀딩스", "stems": ["원익홀딩스"]},
    "01261893": {"name": "케이씨텍", "stems": ["케이씨텍"]},
    "00411048": {"name": "에스앤에스텍", "stems": ["에스앤에스텍"]},
    "00223434": {"name": "에프에스티", "stems": ["에프에스티"]},
    "01478712": {"name": "대덕전자", "stems": ["대덕전자"]},
}
# 'SK' 처럼 짧아 부분일치가 위험한 경우 — 정규화 이름 정확매칭(er_name) 으로만.
EXACT_ER = {"00181712": "sk"}

UPSERT_SQL = """
INSERT INTO fin_metric
  (metric_id, corp_code, rcept_no, bsns_year, reprt_code, account_id, value, unit, fs_div)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE
  value=VALUES(value), unit=VALUES(unit), bsns_year=VALUES(bsns_year),
  reprt_code=VALUES(reprt_code), rcept_no=VALUES(rcept_no), fs_div=VALUES(fs_div)
"""


def _raw_files(corp_code: str) -> list[Path]:
    return sorted(RAW.glob(f"{corp_code}_*_{REPRT_CODE}_*.json"))


def _fs_div(path: Path) -> str:
    return "CFS" if path.stem.endswith("_CFS") else "OFS"


def parse_corp_metrics(corp_code: str):
    """corp_code 의 raw 파일 → (maria_rows, neo_rows). 자기 corp_code 만(오염 방지)."""
    maria_rows: list[tuple] = []
    neo_rows: list[dict] = []
    seen: set[str] = set()
    for f in _raw_files(corp_code):
        fs_div = _fs_div(f)
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if obj.get("status") != "000":
            continue
        for row in obj.get("list") or []:
            # 오염 방지: 응답 corp_code 가 파일 corp_code 와 다르면 스킵
            row_corp = (row.get("corp_code") or "").strip()
            if row_corp and row_corp != corp_code:
                continue
            account_id = (row.get("account_id") or "").strip()
            if not account_id or account_id == "-":
                continue
            if len(account_id) > 255:
                account_id = account_id[:255]
            rcept_no = (row.get("rcept_no") or "").strip()
            byr = (row.get("bsns_year") or "").strip()
            try:
                bsns_year = int(byr) if byr else None
            except ValueError:
                bsns_year = None
            reprt_code = (row.get("reprt_code") or "").strip() or REPRT_CODE
            value = parse_number(row.get("thstrm_amount"))
            unit = (row.get("currency") or "KRW").strip() or "KRW"
            mid = metric_id(corp_code, rcept_no, fs_div, account_id)
            if mid in seen:
                continue
            seen.add(mid)
            maria_rows.append((mid, corp_code, rcept_no, bsns_year, reprt_code,
                               account_id, value, unit, fs_div))
            neo_rows.append({"metric_id": mid, "account_id": account_id,
                             "bsns_year": bsns_year, "value": value, "unit": unit,
                             "corp_code": corp_code, "rcept_no": rcept_no})
    return maria_rows, neo_rows


def find_org_nodes(s, corp_code: str) -> list[str]:
    """corp_code 회사의 기존 needs_er Organization 노드 name 목록(변형 포함)."""
    t = TARGETS[corp_code]
    stems = [x.lower() for x in t["stems"]]
    # 멱등: 아직 corp_code 없는 노드 + 이미 이 corp_code 부여된 노드(재실행 시) 매칭
    rows = s.run(
        "MATCH (o:Organization) WHERE o.corp_code IS NULL OR o.corp_code = $cc "
        "RETURN o.name AS name, o.er_name AS er, elementId(o) AS eid",
        cc=corp_code,
    ).data()
    matched_eids: list[str] = []
    matched_names: list[str] = []
    for r in rows:
        nm_norm = (r["name"] or "").replace(" ", "").lower()
        er = (r["er"] or "")
        hit = False
        if corp_code in EXACT_ER and er == EXACT_ER[corp_code]:
            hit = True
        for st in stems:
            if st and st in nm_norm:
                hit = True
                break
        if hit:
            matched_eids.append(r["eid"])
            matched_names.append(r["name"])
    return matched_eids, matched_names


def main() -> None:
    conn = mariadb_conn()
    cur = conn.cursor()
    d = neo4j_driver()

    report = []
    total_maria = 0
    total_fm = 0

    with d.session() as s:
        for corp_code, t in TARGETS.items():
            maria_rows, neo_rows = parse_corp_metrics(corp_code)

            # 1) MariaDB upsert
            if maria_rows:
                for i in range(0, len(maria_rows), 1000):
                    cur.executemany(UPSERT_SQL, maria_rows[i:i + 1000])
                conn.commit()
            total_maria += len(maria_rows)

            # 2) 기존 needs_er 노드 → corp_code 부여 (변형 여럿이면 하나로 MERGE)
            #    Organization.corp_code 는 UNIQUENESS 제약 → 변형 노드들을 한 노드로
            #    apoc.refactor.mergeNodes(기존 지분/계열 엣지 전부 보존) 후 corp_code 부여.
            eids, names = find_org_nodes(s, corp_code)
            if not eids:
                report.append({"corp_code": corp_code, "name": t["name"],
                               "rows": len(maria_rows), "nodes": [],
                               "warn": "그래프 노드 없음"})
                continue
            if len(eids) > 1:
                # 변형 노드 병합: 첫 노드 생존, 나머지 엣지를 거기로(중복 관계 합침)
                s.run(
                    """
                    MATCH (o:Organization) WHERE elementId(o) IN $eids
                    WITH collect(o) AS nodes
                    CALL apoc.refactor.mergeNodes(
                        nodes,
                        {properties:'discard', mergeRels:true}) YIELD node
                    SET node.corp_code=$cc, node.needs_er=false, node.has_corp_code=true
                    RETURN node
                    """,
                    eids=eids, cc=corp_code,
                )
            else:
                s.run(
                    "MATCH (o:Organization) WHERE elementId(o) IN $eids "
                    "SET o.corp_code=$cc, o.needs_er=false, o.has_corp_code=true",
                    eids=eids, cc=corp_code,
                )

            # 3) FinMetric + HAS_METRIC + DERIVED_FROM (재무 있을 때만)
            #    변형 노드가 여럿이면 corp_code 매칭으로 모두에 연결됨(HAS_METRIC).
            if neo_rows:
                # v3: FilingDocument/DERIVED_FROM 제거 — 출처는 FinMetric.rcept_no 속성.
                for i in range(0, len(neo_rows), 500):
                    batch = neo_rows[i:i + 500]
                    s.run(
                        """
                        UNWIND $rows AS row
                        MERGE (m:FinMetric {metric_id: row.metric_id})
                        SET m.account_id=row.account_id, m.bsns_year=row.bsns_year,
                            m.value=row.value, m.unit=row.unit, m.rcept_no=row.rcept_no
                        WITH m, row
                        MATCH (o:Organization {corp_code: row.corp_code})
                        MERGE (o)-[:HAS_METRIC]->(m)
                        """,
                        rows=batch,
                    )
                total_fm += len(neo_rows)

            report.append({"corp_code": corp_code, "name": t["name"],
                           "rows": len(maria_rows), "nodes": names,
                           "warn": "" if neo_rows else "재무없음(corp_code만 부여)"})

    cur.close()
    conn.close()
    d.close()

    print(f"\n=== 적재 완료: MariaDB {total_maria}행, Neo4j FinMetric {total_fm} ===")
    have = sum(1 for r in report if r["rows"] > 0)
    print(f"재무 확보 {have}/{len(TARGETS)} 개사\n")
    print(f"{'회사':<18}{'corp_code':<12}{'재무행':>7}  연결노드 / 비고")
    for r in report:
        nodes = ", ".join(r["nodes"]) if r["nodes"] else "(없음)"
        warn = f"  ⚠{r['warn']}" if r["warn"] else ""
        print(f"{r['name']:<18}{r['corp_code']:<12}{r['rows']:>7}  {nodes}{warn}")
    (HERE / "load_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
