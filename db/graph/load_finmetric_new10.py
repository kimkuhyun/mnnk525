"""신규 10사 재무 적재 — db/raw/{folder}/ds003/fnlttSinglAcntAll__*.json
→ MariaDB fin_metric + Neo4j FinMetric/HAS_METRIC.

load_finmetric.py 와 동일 파싱. 차이: 대상=신규10사(corps.tsv 폴더), 그리고
FilingDocument/DERIVED_FROM 미생성(v3 다이어트 — 출처는 FinMetric.rcept_no 속성).
reprt_code·fs_div 속성 포함(멀티홉 재무 중복방지 필터키). 멱등 upsert.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

GRAPH_DIR = Path(__file__).resolve().parent
if str(GRAPH_DIR) not in sys.path:
    sys.path.insert(0, str(GRAPH_DIR))

from db import mariadb_conn, metric_id, neo4j_driver, parse_number

DB_DIR = GRAPH_DIR.parent
RAW_DIR = DB_DIR / "raw"
CORPS_TSV = DB_DIR / "extra28" / "corps.tsv"

NEW10 = {
    "00105873", "00105961", "00138020", "00139889", "00152686",
    "00158219", "00227333", "00301246", "00445054", "00447609",
}

UPSERT_SQL = """
INSERT INTO fin_metric
  (metric_id, corp_code, rcept_no, bsns_year, reprt_code, account_id, value, unit, fs_div)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE
  value=VALUES(value), unit=VALUES(unit), bsns_year=VALUES(bsns_year),
  reprt_code=VALUES(reprt_code), rcept_no=VALUES(rcept_no), fs_div=VALUES(fs_div)
"""


def _folder_map() -> dict[str, str]:
    m: dict[str, str] = {}
    for line in CORPS_TSV.read_text(encoding="utf-8").splitlines()[1:]:
        parts = line.strip().split("\t")
        if len(parts) >= 2 and parts[0].strip() in NEW10:
            m[parts[0].strip()] = parts[1].strip()
    return m


def _fs_div(path: Path) -> str:
    n = path.stem
    return "OFS" if n.endswith("_OFS") else "CFS"


def main() -> None:
    folders = _folder_map()
    print(f"[대상] {len(folders)}개사: {list(folders.values())}")
    conn = mariadb_conn()
    cur = conn.cursor()
    d = neo4j_driver()

    maria_rows: list[tuple] = []
    neo_rows: list[dict] = []
    seen: set[str] = set()

    for corp_code, folder in folders.items():
        d3 = RAW_DIR / folder / "ds003"
        if not d3.exists():
            print(f"  [{folder}] ds003 없음"); continue
        for f in sorted(d3.glob("fnlttSinglAcntAll__*.json")):
            fs_div = _fs_div(f)
            try:
                obj = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if obj.get("status") != "000":
                continue
            for row in obj.get("list") or []:
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
                reprt_code = (row.get("reprt_code") or "").strip()
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
                                 "reprt_code": reprt_code, "fs_div": fs_div,
                                 "corp_code": corp_code, "rcept_no": rcept_no})

    for i in range(0, len(maria_rows), 1000):
        cur.executemany(UPSERT_SQL, maria_rows[i:i + 1000])
    conn.commit()
    print(f"[ok] MariaDB fin_metric upsert {len(maria_rows)}건")

    def flush_fm(tx, rows):
        tx.run(
            """
            UNWIND $rows AS row
            MERGE (m:FinMetric {metric_id: row.metric_id})
            SET m.account_id=row.account_id, m.bsns_year=row.bsns_year,
                m.value=row.value, m.unit=row.unit,
                m.reprt_code=row.reprt_code, m.fs_div=row.fs_div, m.rcept_no=row.rcept_no
            WITH m, row
            MATCH (o:Organization {corp_code: row.corp_code})
            MERGE (o)-[:HAS_METRIC]->(m)
            """,
            rows=rows,
        )

    with d.session() as s:
        for i in range(0, len(neo_rows), 500):
            s.execute_write(flush_fm, neo_rows[i:i + 500])
    print(f"[ok] Neo4j FinMetric MERGE {len(neo_rows)}건 + HAS_METRIC (FilingDocument 없음)")

    cur.close()
    conn.close()
    d.close()
    print(f"=== 신규10사 재무 완료: {len(maria_rows)} metric ===")


if __name__ == "__main__":
    main()
