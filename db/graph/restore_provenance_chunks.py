"""근거 청크 복원 — 관계엣지가 chunk_id로 참조하나 노드가 없는 Chunk 를 MariaDB 에서 재생성.

배경: 그래프 다이어트 때 FilingDocument 삭제로 has_chunk 가 끊겨 근거청크가 '엣지 0'으로 보였고,
그걸 고아로 오인해 삭제 → 관계엣지 chunk_id 참조가 끊김(CLAUDE.md 4번 역추적 계약 위반).
복원: MariaDB chunk_index(+document_index date)에서 메타를 가져와 Chunk 노드 MERGE.

멱등. 실행: cd db/graph && PYTHONIOENCODING=utf-8 uv run --project .. python restore_provenance_chunks.py
"""
from __future__ import annotations

from db import mariadb_conn, neo4j_driver


def main() -> None:
    d = neo4j_driver()
    with d.session() as s:
        dangling = [
            r["cid"] for r in s.run(
                "MATCH ()-[r]->() WHERE r.chunk_id IS NOT NULL "
                "AND NOT exists{(c:Chunk{chunk_id:r.chunk_id})} "
                "RETURN DISTINCT r.chunk_id AS cid"
            )
        ]
    print(f"[info] 복원 대상 chunk_id {len(dangling)}개")
    if not dangling:
        d.close()
        return

    conn = mariadb_conn()
    cur = conn.cursor()
    rows = []
    for i in range(0, len(dangling), 1000):
        batch = dangling[i:i + 1000]
        ph = ",".join(["%s"] * len(batch))
        cur.execute(
            "SELECT ci.chunk_id, ci.corp_code, ci.rcept_no, ci.chunk_type, "
            "ci.section_path, di.date AS doc_date "
            "FROM chunk_index ci LEFT JOIN document_index di ON ci.rcept_no=di.rcept_no "
            f"WHERE ci.chunk_id IN ({ph})",
            batch,
        )
        rows.extend(cur.fetchall())
    cur.close()
    conn.close()
    print(f"[info] MariaDB 메타 {len(rows)}행 조회")

    neo_rows = [
        {
            "chunk_id": r[0], "corp_code": r[1], "rcept_no": r[2],
            "chunk_type": r[3], "section_path": r[4],
            "doc_date": r[5].isoformat() if r[5] else None,
        }
        for r in rows
    ]

    def flush(tx, batch):
        tx.run(
            "UNWIND $rows AS row "
            "MERGE (c:Chunk {chunk_id: row.chunk_id}) "
            "SET c.corp_code=row.corp_code, c.rcept_no=row.rcept_no, "
            "    c.chunk_type=row.chunk_type, c.section_path=row.section_path, "
            "    c.doc_date=row.doc_date",
            rows=batch,
        )

    with d.session() as s:
        for i in range(0, len(neo_rows), 500):
            s.execute_write(flush, neo_rows[i:i + 500])
        left = s.run(
            "MATCH ()-[r]->() WHERE r.chunk_id IS NOT NULL "
            "AND NOT exists{(c:Chunk{chunk_id:r.chunk_id})} RETURN count(r) AS c"
        ).single()["c"]
    d.close()
    print(f"[ok] Chunk {len(neo_rows)}개 복원. 남은 끊긴근거엣지: {left}")


if __name__ == "__main__":
    main()
