"""Neo4j Chunk 노드 적재 — P-3.2 (T4 lookup-only).

MariaDB chunk_index (ingest_status='ready', active run_id) → Neo4j (:Chunk).
의미 그래프 LLM 추출 결과의 evidence 링크 anchor 역할.

T4 화이트리스트:
  허용 1-hop: (Chunk)-[:wasDerivedFrom]->(FilingDocument|NewsArticle),
              (Chunk)-[:hasActor]->(Org|Person),
              (Chunk)-[:hasObject]->(Product|Technology)
  금지: Chunk→Chunk, 다단 hop, MATCH 의 traverse pattern.

idempotent — 같은 (chunk_id, run_id) 면 SET 만 갱신.
"""
from __future__ import annotations

import hashlib
import sys
import time

from polaris.config import mariadb_conn
from polaris.graph.common import get_active_run_id
from polaris.graph.merger import Merger

BATCH = 1000


def _hash16(s: str) -> str:
    return hashlib.md5((s or "").encode("utf-8")).hexdigest()[:16]


def collect(run_id: str) -> list[dict]:
    """active run_id 의 모든 ready 청크 → ChunkRef payload."""
    conn = mariadb_conn(); cur = conn.cursor()
    cur.execute("""
        SELECT chunk_id, corp_code, rcept_no, chunk_type, section_path,
               embedding_text, ingest_status
        FROM chunk_index
        WHERE run_id = %s AND ingest_status = 'ready'
    """, (run_id,))
    rows = []
    for cid, cc, rno, ctype, spath, etext, status in cur.fetchall():
        rows.append({
            "chunk_id": cid,
            "run_id": run_id,
            "corp_code": cc or "00000000",
            "rcept_no": rno or "",
            "chunk_type": ctype,
            "anchor": spath or "",
            "embedding_text_hash": _hash16(etext or ""),
            "ingest_status": status or "ready",
        })
    cur.close(); conn.close()
    return rows


def main() -> int:
    t0 = time.time()
    run_id = get_active_run_id()
    print(f"[load_chunk_nodes] active run_id = {run_id}")

    chunks = collect(run_id)
    print(f"[load_chunk_nodes] 적재 후보: {len(chunks):,} chunks")
    if not chunks:
        return 0

    with Merger() as m:
        # Chunk 노드만 적재 (1-hop evidence 엣지는 의미 추출 단계에서)
        for i in range(0, len(chunks), BATCH):
            batch = chunks[i:i + BATCH]
            m.chunk_evidence(batch)
            print(f"  loaded {min(i + BATCH, len(chunks)):,} / {len(chunks):,}")

    print(f"[load_chunk_nodes] 완료. {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
