"""일회성 백필 — 기존 Neo4j FinMetric 노드에 reprt_code·fs_div 채우기.

배경(함정 B): load_finmetric.py 구버전이 Neo4j 투영 시 reprt_code·fs_div를 누락 →
같은 (corp_code, account_id, bsns_year)에 값이 여러 개인데 연결/연간 구분이 그래프에서 불가.
MariaDB fin_metric(metric_id 공유키)이 SSOT라 거기서 백필한다(raw 파일 의존 없음).

멱등: 이미 채워졌으면 같은 값 SET. load_finmetric.py 신버전은 처음부터 두 필드를 넣으므로
재적재 시엔 이 스크립트 불필요(기존 데이터 1회 보정용).

실행: cd db/graph && PYTHONIOENCODING=utf-8 uv run --project .. python backfill_finmetric_props.py
"""
from __future__ import annotations

from db import mariadb_conn, neo4j_driver


def main() -> None:
    conn = mariadb_conn()
    cur = conn.cursor()
    cur.execute("SELECT metric_id, reprt_code, fs_div FROM fin_metric")
    rows = [
        {"metric_id": mid, "reprt_code": rc, "fs_div": fd}
        for (mid, rc, fd) in cur.fetchall()
    ]
    cur.close()
    conn.close()
    print(f"[info] MariaDB fin_metric {len(rows)}행 로드")

    d = neo4j_driver()

    def flush(tx, batch):
        res = tx.run(
            """
            UNWIND $rows AS row
            MATCH (m:FinMetric {metric_id: row.metric_id})
            SET m.reprt_code = row.reprt_code, m.fs_div = row.fs_div
            RETURN count(m) AS updated
            """,
            rows=batch,
        )
        return res.single()["updated"]

    updated = 0
    with d.session() as s:
        for i in range(0, len(rows), 1000):
            updated += s.execute_write(flush, rows[i:i + 1000])
    d.close()
    print(f"[ok] Neo4j FinMetric 백필: {updated}건에 reprt_code·fs_div SET")


if __name__ == "__main__":
    main()
