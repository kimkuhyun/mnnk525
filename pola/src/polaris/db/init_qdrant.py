"""Qdrant 컬렉션 + payload index 초기화 (Blue/Green standby).

설계 05 §3:
- 컬렉션: polaris-1024-cos-blue (active) / polaris-1024-cos-green (standby)
- 벡터: 1024d cosine
- payload index 6종: corp_code, rcept_no, chunk_type, bsns_year, run_id, ingest_status

idempotent — 이미 있으면 skip.
"""
from __future__ import annotations
import sys, time
from pathlib import Path

from polaris.config import (
    qdrant_client, QDRANT_COLLECTION_ACTIVE, QDRANT_COLLECTION_STANDBY,
)

VECTOR_SIZE = 1024
DISTANCE = "Cosine"

# payload index 정의 (key → schema)
PAYLOAD_INDEX = [
    ("corp_code",      "keyword"),
    ("rcept_no",       "keyword"),
    ("chunk_type",     "keyword"),
    ("bsns_year",      "integer"),
    ("run_id",         "keyword"),
    ("ingest_status",  "keyword"),
    ("endpoint",       "keyword"),
]


def ensure_collection(client, name: str) -> str:
    """컬렉션 없으면 생성, 있으면 skip. payload index 도 멱등하게 적용."""
    from qdrant_client.models import Distance, VectorParams

    existing = {c.name for c in client.get_collections().collections}
    if name in existing:
        action = "exists"
    else:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        action = "created"

    # payload index (idempotent — 이미 있으면 무시)
    for field, schema in PAYLOAD_INDEX:
        try:
            client.create_payload_index(
                collection_name=name,
                field_name=field,
                field_schema=schema,
            )
        except Exception:
            # 이미 존재 등 — skip
            pass

    info = client.get_collection(name)
    return f"{action} (points={info.points_count}, vectors={VECTOR_SIZE}d {DISTANCE})"


def main() -> int:
    t0 = time.time()
    client = qdrant_client()
    print(f"[init_qdrant] target = {QDRANT_COLLECTION_ACTIVE} (active) + "
          f"{QDRANT_COLLECTION_STANDBY} (standby)")
    for col in (QDRANT_COLLECTION_ACTIVE, QDRANT_COLLECTION_STANDBY):
        res = ensure_collection(client, col)
        print(f"  {col}: {res}")
    print(f"\n=== Qdrant init 완료 ({time.time()-t0:.1f}s) ===")
    print(f"  payload index: {[f for f,_ in PAYLOAD_INDEX]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
