"""검증·보고 — 테이블/컬렉션 건수 + MariaDB↔Qdrant 샘플 대조."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import COLLECTION_CHUNKS, mariadb_conn, qdrant_client  # noqa: E402


def main() -> None:
    conn = mariadb_conn()
    qc = qdrant_client()
    try:
        with conn.cursor() as cur:
            print("=== MariaDB row counts ===")
            for t in ("dart_raw_index", "document_index", "chunk_index", "fin_metric", "extraction_provenance"):
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                print(f"  {t}: {cur.fetchone()[0]}")

            print("=== dart_raw_index corp 분포 ===")
            cur.execute("SELECT corp_code, COUNT(*) FROM dart_raw_index GROUP BY corp_code")
            print("  ", cur.fetchall())

            print("=== chunk_index ingest_status ===")
            cur.execute("SELECT ingest_status, COUNT(*) FROM chunk_index GROUP BY ingest_status")
            print("  ", cur.fetchall())

            print(f"=== Qdrant '{COLLECTION_CHUNKS}' ===")
            info = qc.get_collection(COLLECTION_CHUNKS)
            cnt = qc.count(COLLECTION_CHUNKS, exact=True).count
            print(f"  points: {cnt}, dim: {info.config.params.vectors.size}, distance: {info.config.params.vectors.distance}")

            print("=== 샘플 대조 (MariaDB chunk_index ↔ Qdrant point) ===")
            cur.execute(
                "SELECT chunk_id, corp_code, rcept_no, chunk_type, section_path, ingest_status "
                "FROM chunk_index ORDER BY chunk_id LIMIT 1"
            )
            row = cur.fetchone()
            chunk_id = row[0]
            print("  MariaDB:", dict(zip(
                ["chunk_id", "corp_code", "rcept_no", "chunk_type", "section_path", "ingest_status"], row)))
            pid = int(chunk_id, 16)
            pts = qc.retrieve(COLLECTION_CHUNKS, ids=[pid], with_payload=True, with_vectors=True)
            if pts:
                p = pts[0]
                print("  Qdrant id:", p.id, "(== int(chunk_id,16):", pid, ")")
                print("  Qdrant payload:", p.payload)
                print("  Qdrant vector dim:", len(p.vector))
            else:
                print("  Qdrant: point 없음!")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
