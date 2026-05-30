"""table_nl 청크 in-place 재임베딩 (Contextual prefix 적용).

run_stage_c1.py 의 embedding_text 정책:
  prefix = f"{corp_name} {year_label} {endpoint}/{variant}"
  embedding_text = f"{prefix}\\n\\n{content}"

기존 적재 청크는 prefix 없는 본문만 임베딩됨 → 신규 정책으로 재임베딩.
chunk_id 동일 (raw content 기반). Qdrant point id 도 동일 → vector 만 갱신.

40,000+ 청크. bge-m3 batch=32, ~25~30분.
"""
from __future__ import annotations
import hashlib, json, sys, time
from pathlib import Path

import httpx

from polaris.config import (
    mariadb_conn, qdrant_client, OLLAMA_BASE, OLLAMA_EMBED_MODEL,
    get_corp_meta,
)

BATCH = 32


def chunk_id_to_uuid(chunk_id: str) -> str:
    h = hashlib.md5(chunk_id.encode("utf-8")).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def main():
    conn = mariadb_conn(); cur = conn.cursor()
    cur.execute("SELECT active_run_id, active_qdrant_collection FROM active_run_manifest WHERE id=1")
    run_id, collection = cur.fetchone()
    cur.close()
    print(f"[reembed-table] active run_id={run_id} collection={collection}")

    cur = conn.cursor()
    cur.execute("""SELECT chunk_id, embedding_text, corp_code, bsns_year,
                          endpoint, variant
                   FROM chunk_index
                   WHERE chunk_type='table_nl'
                     AND ingest_status='ready'
                     AND run_id=%s""", (run_id,))
    rows = cur.fetchall()
    cur.close()
    print(f"[reembed-table] table_nl ready chunks: {len(rows):,}")
    if not rows:
        conn.close()
        return 0

    # 새 embedding_text 계산
    # 단 raw_content 가 이미 새 prefix 포함된 경우(재실행) 중복 방지: 첫줄에 corp_name 있으면 skip.
    plan: list[tuple[str, str, str]] = []
    skipped_prefixed = 0
    for cid, raw_text, corp, year, endpoint, variant in rows:
        meta = get_corp_meta(corp)
        corp_name = meta.get("corp_name", corp)
        year_label = str(year) if year else "공시일자"
        prefix = f"{corp_name} {year_label} {endpoint}/{variant}".strip()
        # 재실행 안전: 이미 prefix 적용된 청크는 raw_text 첫 줄이 prefix로 시작
        first_line = (raw_text or "").split("\n", 1)[0] if raw_text else ""
        if first_line.startswith(corp_name) and endpoint in first_line:
            skipped_prefixed += 1
            continue
        new_text = f"{prefix}\n\n{raw_text}"
        plan.append((cid, chunk_id_to_uuid(cid), new_text))

    print(f"[reembed-table] 적용 후보: {len(plan):,} (이미 prefix 적용된 청크 skip: {skipped_prefixed:,})")
    if not plan:
        conn.close()
        return 0

    # Qdrant payload 보존 (재임베딩이라 payload 그대로)
    qc = qdrant_client()
    print(f"[reembed-table] Qdrant payload retrieve ({len(plan):,})...")
    uuids = [u for _, u, _ in plan]
    payload_by_uuid: dict[str, dict] = {}
    for i in range(0, len(uuids), 500):
        pts = qc.retrieve(collection_name=collection,
                          ids=uuids[i:i + 500],
                          with_payload=True, with_vectors=False)
        for p in pts:
            payload_by_uuid[str(p.id)] = p.payload or {}
        if (i // 500) % 5 == 0:
            print(f"  payload {i + 500:,} / {len(uuids):,}")

    # 임베딩 + Qdrant upsert
    print(f"[reembed-table] 임베딩 재생성 (batch={BATCH})...")
    from qdrant_client.models import PointStruct
    t0 = time.time()
    total = len(plan)
    upserted = 0
    with httpx.Client(timeout=120) as http:
        for i in range(0, total, BATCH):
            batch = plan[i:i + BATCH]
            texts = [t for _, _, t in batch]
            r = http.post(
                f"{OLLAMA_BASE}/api/embed",
                json={"model": OLLAMA_EMBED_MODEL, "input": texts},
            )
            r.raise_for_status()
            embs = r.json()["embeddings"]
            points = []
            for (cid, uuid, _), v in zip(batch, embs):
                pl = payload_by_uuid.get(uuid, {})
                points.append(PointStruct(id=uuid, vector=v, payload=pl))
            qc.upsert(collection_name=collection, points=points)
            upserted += len(points)
            if (i // BATCH) % 20 == 0:
                elapsed = time.time() - t0
                eta = elapsed / (upserted / total) - elapsed if upserted else 0
                print(f"  {upserted:,} / {total:,}  ({elapsed:.0f}s, ETA {eta:.0f}s)")

    print(f"[reembed-table] Qdrant upsert: {upserted:,} points ({time.time() - t0:.0f}s)")

    # MariaDB chunk_index.embedding_text UPDATE
    print("[reembed-table] MariaDB chunk_index.embedding_text UPDATE ...")
    cur = conn.cursor()
    for cid, _, new_text in plan:
        cur.execute(
            "UPDATE chunk_index SET embedding_text=%s WHERE chunk_id=%s AND run_id=%s",
            (new_text, cid, run_id),
        )
    conn.commit()
    cur.close()
    conn.close()
    print(f"[reembed-table] 완료. total {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
