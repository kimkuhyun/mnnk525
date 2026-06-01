"""정형 적재 검증·보고 — Neo4j 라벨/엣지 카운트 + MariaDB fin_metric + 샘플 Cypher."""
from __future__ import annotations

from db import mariadb_conn, neo4j_driver

SAMSUNG = "00126380"


def main() -> None:
    d = neo4j_driver()
    with d.session() as s:
        print("===== Neo4j 라벨별 노드 수 =====")
        rows = s.run(
            "MATCH (n) UNWIND labels(n) AS l RETURN l AS label, count(*) AS c ORDER BY c DESC"
        )
        for r in rows:
            print(f"  {r['label']:18s} {r['c']}")

        print("\n===== Neo4j 엣지타입별 수 =====")
        rows = s.run("MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c ORDER BY c DESC")
        for r in rows:
            print(f"  {r['t']:26s} {r['c']}")

        print("\n===== needs_er(임시 회사) 노드 수 =====")
        r = s.run("MATCH (o:Organization {needs_er:true}) RETURN count(*) AS c").single()
        print(f"  needs_er Organization: {r['c']}")

        # (a) 삼성 지분 1~2홉 + 도착회사
        print("\n===== (a) 삼성 IS_MAJOR_SHAREHOLDER_OF/INVESTS_IN 1~2홉 (상위 10) =====")
        rows = s.run(
            """
            MATCH (root:Organization {corp_code:$cc})
            MATCH path = (root)-[:IS_MAJOR_SHAREHOLDER_OF|INVESTS_IN*1..2]->(t:Organization)
            RETURN length(path) AS hop,
                   [n IN nodes(path) | n.name] AS 경로,
                   t.name AS 도착회사
            ORDER BY hop, 도착회사 LIMIT 10
            """,
            cc=SAMSUNG,
        )
        for r in rows:
            print(f"  hop={r['hop']} {r['경로']} -> {r['도착회사']}")

        # (b) 삼성 HAS_METRIC 매출 FinMetric
        print("\n===== (b) 삼성 HAS_METRIC 매출(ifrs-full_Revenue) FinMetric =====")
        rows = s.run(
            """
            MATCH (o:Organization {corp_code:$cc})-[:HAS_METRIC]->(m:FinMetric)
            WHERE m.account_id = 'ifrs-full_Revenue'
            OPTIONAL MATCH (m)-[:DERIVED_FROM]->(f:FilingDocument)
            RETURN m.bsns_year AS 연도, m.value AS 매출, m.unit AS 단위,
                   f.rcept_no AS 원문, m.metric_id AS metric_id
            ORDER BY 연도 DESC, 매출 DESC LIMIT 8
            """,
            cc=SAMSUNG,
        )
        for r in rows:
            print(f"  {r['연도']} 매출={r['매출']} {r['단위']} (rcept={r['원문']})")

        # reports / has_chunk 연결 수
        print("\n===== reports / has_chunk 연결 수 =====")
        r = s.run("MATCH ()-[r:reports]->() RETURN count(r) AS c").single()
        print(f"  reports: {r['c']}")
        r = s.run("MATCH ()-[r:has_chunk]->() RETURN count(r) AS c").single()
        print(f"  has_chunk: {r['c']}")
    d.close()

    conn = mariadb_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM fin_metric")
    print(f"\n===== MariaDB fin_metric 행수: {cur.fetchone()[0]} =====")
    cur.execute(
        "SELECT corp_code, fs_div, COUNT(*) FROM fin_metric GROUP BY corp_code, fs_div ORDER BY corp_code, fs_div"
    )
    for cc, fs, c in cur.fetchall():
        print(f"  {cc} {fs}: {c}")
    cur.execute(
        "SELECT corp_code, bsns_year, value FROM fin_metric "
        "WHERE account_id='ifrs-full_Revenue' AND fs_div='CFS' ORDER BY corp_code, bsns_year DESC LIMIT 12"
    )
    print("  -- 매출(CFS) 샘플 --")
    for cc, yr, val in cur.fetchall():
        print(f"     {cc} {yr} : {val}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
