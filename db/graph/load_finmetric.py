"""정형 재무 적재 — fnlttSinglAcntAll → MariaDB fin_metric + Neo4j FinMetric.

MariaDB: fin_metric(metric_id PK, corp_code, rcept_no, bsns_year, reprt_code,
                    account_id, value, unit, fs_div). 멱등 upsert.
Neo4j: FinMetric(metric_id, account_id, bsns_year, value, unit)
       + HAS_METRIC(Org→FinMetric) + DERIVED_FROM(FinMetric→FilingDocument).

수치는 JSON 그대로(LLM 생성 금지). value = thstrm_amount(당기) 결정론 파싱.
계정 전수 적재(수치는 결정론). fs_div = 파일명 CFS/OFS.
"""
from __future__ import annotations

import json
from pathlib import Path

from db import CORP_CODE, RAW_DIR, mariadb_conn, metric_id, neo4j_driver, parse_number

DS003 = "ds003"

UPSERT_SQL = """
INSERT INTO fin_metric
  (metric_id, corp_code, rcept_no, bsns_year, reprt_code, account_id, value, unit, fs_div)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE
  value=VALUES(value), unit=VALUES(unit), bsns_year=VALUES(bsns_year),
  reprt_code=VALUES(reprt_code), rcept_no=VALUES(rcept_no), fs_div=VALUES(fs_div)
"""


def _all_files(folder: str) -> list[Path]:
    d = RAW_DIR / folder / DS003
    if not d.exists():
        return []
    return sorted(d.glob("fnlttSinglAcntAll__*.json"))


def _fs_div(path: Path) -> str:
    name = path.stem
    if name.endswith("_CFS"):
        return "CFS"
    if name.endswith("_OFS"):
        return "OFS"
    return "CFS"


def main() -> None:
    conn = mariadb_conn()
    cur = conn.cursor()
    d = neo4j_driver()

    total_rows = 0
    fm_nodes = 0
    maria_rows: list[tuple] = []
    neo_rows: list[dict] = []  # {metric_id, account_id, bsns_year, value, unit, corp_code, rcept_no}
    seen: set[str] = set()

    for folder, corp_code in CORP_CODE.items():
        for f in _all_files(folder):
            fs_div = _fs_div(f)
            try:
                obj = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if obj.get("status") != "000":
                continue
            for row in obj.get("list") or []:
                account_id = (row.get("account_id") or "").strip()
                if not account_id or account_id == "-":
                    continue
                # account_id 는 스키마상 VARCHAR(128). 초과(>128)는 일부 비핵심
                # 지분법 OCII 세부계정뿐 — 스키마 SSOT 유지 위해 스킵(결정론).
                if len(account_id) > 128:
                    continue
                rcept_no = (row.get("rcept_no") or "").strip()
                bsns_year_raw = (row.get("bsns_year") or "").strip()
                try:
                    bsns_year = int(bsns_year_raw) if bsns_year_raw else None
                except ValueError:
                    bsns_year = None
                reprt_code = (row.get("reprt_code") or "").strip()
                value = parse_number(row.get("thstrm_amount"))
                unit = (row.get("currency") or "KRW").strip() or "KRW"

                mid = metric_id(corp_code, rcept_no, fs_div, account_id)
                # 동일 metric_id 중복(같은 파일 내 ord 다름 등) → 마지막 값 유지
                if mid in seen:
                    continue
                seen.add(mid)

                maria_rows.append((
                    mid, corp_code, rcept_no, bsns_year, reprt_code,
                    account_id, value, unit, fs_div,
                ))
                neo_rows.append({
                    "metric_id": mid, "account_id": account_id,
                    "bsns_year": bsns_year, "value": value, "unit": unit,
                    "corp_code": corp_code, "rcept_no": rcept_no,
                })
                total_rows += 1

    # ── MariaDB upsert (배치) ──
    BATCH = 1000
    for i in range(0, len(maria_rows), BATCH):
        cur.executemany(UPSERT_SQL, maria_rows[i:i + BATCH])
    conn.commit()
    print(f"[ok] MariaDB fin_metric upsert {len(maria_rows)}건")

    # ── Neo4j FinMetric + HAS_METRIC + DERIVED_FROM (배치) ──
    def flush_fm(tx, rows):
        tx.run(
            """
            UNWIND $rows AS row
            MERGE (m:FinMetric {metric_id: row.metric_id})
            SET m.account_id=row.account_id, m.bsns_year=row.bsns_year,
                m.value=row.value, m.unit=row.unit
            WITH m, row
            MATCH (o:Organization {corp_code: row.corp_code})
            MERGE (o)-[:HAS_METRIC]->(m)
            WITH m, row
            WHERE row.rcept_no IS NOT NULL AND row.rcept_no <> ''
            MERGE (f:FilingDocument {rcept_no: row.rcept_no})
            MERGE (m)-[:DERIVED_FROM]->(f)
            """,
            rows=rows,
        )

    with d.session() as s:
        for i in range(0, len(neo_rows), 500):
            s.execute_write(flush_fm, neo_rows[i:i + 500])
            fm_nodes += len(neo_rows[i:i + 500])
    print(f"[ok] Neo4j FinMetric MERGE {fm_nodes}건 + HAS_METRIC + DERIVED_FROM")

    cur.close()
    conn.close()
    d.close()
    print(f"=== load_finmetric 완료: 총 {total_rows} metric ===")


if __name__ == "__main__":
    main()
