"""Qdrant polaris-chunks 생성 + 임베딩 upsert (멱등).

설계 SSOT: docs/DBdocs/02_qdrant.md.
- 컬렉션: size 1024, Cosine, HNSW m=16 ef_construct=100. payload 인덱스 chunk_id·corp_code·rcept_no·chunk_type(keyword) + doc_date(datetime).
- point id = int(chunk_id, 16) (16hex → uint64).
- vector = bge-m3(embedding_text), payload = {chunk_id, corp_code, rcept_no, chunk_type, section_path, doc_date}.
- doc_date = document_index.date(해당 rcept_no) ISO datetime, 없으면 생략.
- 성공 청크 → chunk_index.ingest_status='ready'.
재실행 안전: 컬렉션 있으면 재생성 안 함, 같은 id upsert.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx
from qdrant_client.models import (
    Distance,
    HnswConfigDiff,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import (  # noqa: E402
    COLLECTION_CHUNKS,
    EMBED_DIM,
    OLLAMA_BASE,
    EMBED_MODEL,
    mariadb_conn,
    ollama_embed,
    qdrant_client,
)

BATCH = 64


def ensure_collection(qc) -> None:
    existing = {c.name for c in qc.get_collections().collections}
    if COLLECTION_CHUNKS in existing:
        print(f"  컬렉션 '{COLLECTION_CHUNKS}' 이미 존재 — 재생성 생략(멱등).")
    else:
        print(f"  컬렉션 '{COLLECTION_CHUNKS}' 생성...")
        qc.create_collection(
            collection_name=COLLECTION_CHUNKS,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
            hnsw_config=HnswConfigDiff(m=16, ef_construct=100),
        )
    # payload 인덱스(이미 있으면 무시) — 멱등
    for field in ("chunk_id", "corp_code", "rcept_no", "chunk_type"):
        try:
            qc.create_payload_index(COLLECTION_CHUNKS, field, PayloadSchemaType.KEYWORD)
        except Exception:
            pass
    try:
        qc.create_payload_index(COLLECTION_CHUNKS, "doc_date", PayloadSchemaType.DATETIME)
    except Exception:
        pass


def load_doc_dates(cur) -> dict[str, str]:
    """rcept_no → doc_date ISO datetime (document_index.date 조인)."""
    cur.execute("SELECT rcept_no, date FROM document_index WHERE date IS NOT NULL")
    out = {}
    for rno, d in cur.fetchall():
        out[rno] = f"{d.isoformat()}T00:00:00Z"
    return out


def fetch_chunks(cur, *, only_pending: bool = True):
    where = "WHERE ingest_status='pending'" if only_pending else ""
    cur.execute(
        "SELECT chunk_id, corp_code, rcept_no, chunk_type, section_path, embedding_text "
        f"FROM chunk_index {where} ORDER BY chunk_id"
    )
    return cur.fetchall()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--all",
        action="store_true",
        help="ready 상태까지 포함해 전체 chunk를 다시 upsert",
    )
    args = ap.parse_args()

    qc = qdrant_client()
    print("[1/3] 컬렉션 보장...")
    ensure_collection(qc)

    conn = mariadb_conn()
    http = httpx.Client(timeout=120)
    try:
        with conn.cursor() as cur:
            doc_dates = load_doc_dates(cur)
            rows = fetch_chunks(cur, only_pending=not args.all)
        total = len(rows)
        scope = "전체" if args.all else "pending"
        print(f"[2/3] 임베딩+upsert 시작 — {scope} 청크 {total}건, 배치 {BATCH}.")

        points: list[PointStruct] = []
        ready_ids: list[str] = []
        done = 0

        def flush(cur):
            nonlocal points, ready_ids
            if not points:
                return
            qc.upsert(collection_name=COLLECTION_CHUNKS, points=points, wait=True)
            cur.executemany(
                "UPDATE chunk_index SET ingest_status='ready' WHERE chunk_id=%s",
                [(cid,) for cid in ready_ids],
            )
            conn.commit()
            points = []
            ready_ids = []

        with conn.cursor() as cur:
            for chunk_id, corp_code, rcept_no, chunk_type, section_path, embedding_text in rows:
                vec = ollama_embed(embedding_text or "", http)
                payload = {
                    "chunk_id": chunk_id,
                    "corp_code": corp_code,
                    "rcept_no": rcept_no,
                    "chunk_type": chunk_type,
                    "section_path": section_path,
                }
                dd = doc_dates.get(rcept_no)
                if dd:
                    payload["doc_date"] = dd
                points.append(
                    PointStruct(id=int(chunk_id, 16), vector=vec, payload=payload)
                )
                ready_ids.append(chunk_id)
                done += 1
                if len(points) >= BATCH:
                    flush(cur)
                    if done % (BATCH * 8) == 0 or done == total:
                        print(f"      진행 {done}/{total} ({done*100//total}%)")
            flush(cur)
            print(f"      진행 {done}/{total} (100%)")

        print("[3/3] 검증...")
        cnt = qc.count(COLLECTION_CHUNKS, exact=True).count
        print(f"  Qdrant '{COLLECTION_CHUNKS}' points = {cnt}")
        with conn.cursor() as cur:
            cur.execute("SELECT ingest_status, COUNT(*) FROM chunk_index GROUP BY ingest_status")
            for st, c in cur.fetchall():
                print(f"  chunk_index ingest_status {st} = {c}")
    finally:
        http.close()
        conn.close()
    print("Qdrant 임베딩 적재 완료.")


if __name__ == "__main__":
    main()
