"""엣지 스냅샷 — 현재 시드 3사의 claude 외부관계 엣지를 edge_snapshot 테이블에 1 run 으로 기록.

Neo4j 에서 (c{corp_code})-[r{extracted_by:'claude'}]-(o) 를 수집 → MariaDB edge_snapshot 적재.
graph_load / 추출 재실행 후 호출하면 run 이 누적되어 /changes 가 소멸 비교에 활용됨.
멱등 아니어도 됨 (run 별 적재).

실행:  uv run python -m polaris.analyze.snapshot_edges
"""
from __future__ import annotations

import argparse
from datetime import datetime

from polaris.config import mariadb_conn, neo4j_driver

# backend/app/relations.py 와 동기화 유지 (SSOT 미러)
PREDICATE_TO_GROUP: dict[str, str] = {
    "SUPPLIES": "supply", "CUSTOMER_OF": "supply",
    "COMPETES_WITH": "compete",
    "PARTNERS_WITH": "partner", "JV_WITH": "partner", "LICENSES": "partner",
    "INVESTS_IN": "invest", "ACQUIRES": "invest",
    "IS_SUBSIDIARY_OF": "govern", "IS_MAJOR_SHAREHOLDER_OF": "govern", "AFFILIATED_WITH": "govern",
    "LITIGATION": "dispute",
}
COMPANY_REL_TYPES: list[str] = list(PREDICATE_TO_GROUP)

SEED_CORPS: dict[str, str] = {
    "00126380": "삼성전자",
    "00164779": "SK하이닉스",
    "00161383": "한미반도체",
}

# Neo4j 에서 시드사 외부관계 엣지 수집 쿼리
# r.extracted_by = 'claude', type(r) ∈ COMPANY_REL_TYPES
# 양방향 매칭 (-[r]-) 후 시드사 기준으로 필터
_CYPHER = """
MATCH (c:Organization)-[r]-(o:Organization)
WHERE c.corp_code IN $corp_codes
  AND o.corp_code IS NOT NULL
  AND o.corp_code <> c.corp_code
  AND r.extracted_by = 'claude'
  AND type(r) IN $rel_types
RETURN c.corp_code AS corp_code,
       type(r)     AS predicate,
       o.name      AS target,
       o.corp_code AS target_corp_code
"""


def ensure_tables(cur) -> None:
    cur.execute("""CREATE TABLE IF NOT EXISTS edge_snapshot (
        id          BIGINT       NOT NULL AUTO_INCREMENT,
        run_ts      DATETIME     NOT NULL,
        corp_code   VARCHAR(8)   NOT NULL,
        grp         VARCHAR(16)  NOT NULL,
        predicate   VARCHAR(32)  NOT NULL,
        target      VARCHAR(255) NOT NULL,
        PRIMARY KEY (id),
        INDEX idx_edge_snapshot_run_ts (run_ts),
        INDEX idx_edge_snapshot_corp   (corp_code, run_ts)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")


def fetch_edges(run_ts: datetime) -> list[tuple]:
    """Neo4j 에서 시드 3사 claude 엣지 수집 → [(run_ts, corp_code, grp, predicate, target)]."""
    corp_codes = list(SEED_CORPS.keys())
    rel_types = COMPANY_REL_TYPES

    driver = neo4j_driver()
    records: list[tuple] = []
    try:
        with driver.session() as session:
            result = session.run(
                _CYPHER,
                corp_codes=corp_codes,
                rel_types=rel_types,
            )
            for row in result:
                corp_code = row["corp_code"]
                predicate = row["predicate"]
                target = row["target"] or row["target_corp_code"] or ""
                grp = PREDICATE_TO_GROUP.get(predicate, "unknown")
                records.append((run_ts, corp_code, grp, predicate, target))
    finally:
        driver.close()

    return records


def insert_snapshot(cur, rows: list[tuple]) -> int:
    if not rows:
        return 0
    cur.executemany(
        """INSERT INTO edge_snapshot (run_ts, corp_code, grp, predicate, target)
           VALUES (%s, %s, %s, %s, %s)""",
        rows,
    )
    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description="시드 3사 claude 엣지 스냅샷 적재")
    ap.add_argument(
        "--run-ts",
        default=None,
        help="스냅샷 실행시각 (YYYY-MM-DD HH:MM:SS). 미지정시 datetime.now()",
    )
    args = ap.parse_args()

    run_ts: datetime
    if args.run_ts:
        run_ts = datetime.fromisoformat(args.run_ts)
    else:
        run_ts = datetime.now()

    print(f"[snapshot_edges] run_ts={run_ts.isoformat()} 수집 시작")

    rows = fetch_edges(run_ts)
    print(f"[snapshot_edges] Neo4j 엣지 {len(rows)} 건 수집")

    if not rows:
        print("[snapshot_edges] 엣지 없음 — 적재 건너뜀")
        return

    conn = mariadb_conn()
    cur = conn.cursor()
    try:
        ensure_tables(cur)
        conn.commit()
        inserted = insert_snapshot(cur, rows)
        conn.commit()
        print(f"[snapshot_edges] edge_snapshot 적재 {inserted} 행 (run_ts={run_ts.isoformat()})")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
