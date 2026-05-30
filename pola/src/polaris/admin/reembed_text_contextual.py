"""text_micro/text_macro 청크 in-place 재임베딩.

run_stage_c2.py 의 embedding_text 정책 변경 (Contextual Retrieval prefix 추가)
→ 기존 적재 청크의 임베딩을 새 정책으로 재생성. chunk_id 는 동일 (raw content 기반).

처리:
  1. MariaDB chunk_index 에서 text 청크 + 메타 + document_index JOIN
  2. Qdrant retrieve 로 section_headings 가져옴
  3. 새 embedding_text = "{corp_name} {doc_type} {section_headings}\n\n{raw_content}"
  4. bge-m3 (Ollama) 임베딩
  5. Qdrant set_vectors (point id 동일, vector 만 갱신)
  6. MariaDB chunk_index.embedding_text UPDATE

active run 의 ready 청크만. 686개 기준 약 4~5분 (batch=32).
"""
from __future__ import annotations
import hashlib, json, sys, time
from pathlib import Path

import httpx

from polaris.config import (
    mariadb_conn, qdrant_client, OLLAMA_BASE, OLLAMA_EMBED_MODEL,
)
BATCH = 32


def chunk_id_to_uuid(chunk_id: str) -> str:
    h = hashlib.md5(chunk_id.encode("utf-8")).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def main():
    conn = mariadb_conn()
    cur = conn.cursor()
    cur.execute("SELECT active_run_id, active_qdrant_collection FROM active_run_manifest WHERE id=1")
    run_id, collection = cur.fetchone()
    cur.close()
    print(f"[reembed] active run_id={run_id} collection={collection}")

    cur = conn.cursor()
    cur.execute("""
        SELECT ci.chunk_id, ci.embedding_text, ci.section_path,
               di.doc_type, di.corp_name
        FROM chunk_index ci
        LEFT JOIN document_index di
          ON ci.rcept_no=di.rcept_no AND ci.run_id=di.run_id
        WHERE ci.chunk_type IN ('text_micro','text_macro')
          AND ci.ingest_status='ready'
          AND ci.run_id=%s
    """, (run_id,))
    rows = cur.fetchall()
    cur.close()
    print(f"[reembed] text chunks (ready, active run): {len(rows)}")
    if not rows:
        conn.close()
        return 0

    # Qdrant 에서 section_headings 가져오기 (payload.anchor.section_headings 또는 payload.section_headings)
    qc = qdrant_client()
    uuids = [chunk_id_to_uuid(r[0]) for r in rows]
    print(f"[reembed] Qdrant retrieve {len(uuids)} payloads...")
    qpoints = qc.retrieve(collection_name=collection, ids=uuids, with_payload=True, with_vectors=False)
    payload_by_uuid = {str(p.id): p.payload for p in qpoints}

    # 새 embedding_text 생성
    plan: list[tuple[str, str, str]] = []  # (chunk_id, uuid, new_embedding_text)
    for cid, raw_text, sp, doc_type, corp_name in rows:
        uuid = chunk_id_to_uuid(cid)
        pl = payload_by_uuid.get(uuid, {})
        # 이미 contextual prefix 가 있으면 raw 본문은 그대로 사용
        # (raw_text 는 chunk_index 에 저장된 기존 embedding_text == 본문)
        headings = pl.get("section_headings") or pl.get("anchor", {}).get("section_headings") or []
        heading_str = " > ".join(headings) if headings else (sp or "").replace("/", "-")
        prefix = f"{corp_name or ''} {doc_type or ''} {heading_str}".strip()
        new_text = f"{prefix}\n\n{raw_text}"
        plan.append((cid, uuid, new_text))

    print(f"[reembed] 임베딩 재생성 (batch={BATCH})...")
    new_vectors: dict[str, list[float]] = {}
    t0 = time.time()
    with httpx.Client(timeout=120) as http:
        for i in range(0, len(plan), BATCH):
            batch_items = plan[i:i + BATCH]
            texts = [t for _, _, t in batch_items]
            r = http.post(
                f"{OLLAMA_BASE}/api/embed",
                json={"model": OLLAMA_EMBED_MODEL, "input": texts},
            )
            r.raise_for_status()
            embs = r.json()["embeddings"]
            for (_, uuid, _), v in zip(batch_items, embs):
                new_vectors[uuid] = v
            if (i // BATCH) % 5 == 0:
                print(f"  {i + len(batch_items)}/{len(plan)} ({time.time() - t0:.0f}s)")
    print(f"[reembed] 임베딩 완료: {len(new_vectors)} vectors ({time.time() - t0:.0f}s)")

    # Qdrant upsert (vector 갱신)
    from qdrant_client.models import PointStruct
    print("[reembed] Qdrant upsert ...")
    points = []
    for cid, uuid, _ in plan:
        if uuid not in new_vectors:
            continue
        # 기존 payload 보존 (재인덱싱 아니라 vector 만 교체)
        pl = payload_by_uuid.get(uuid, {})
        points.append(PointStruct(id=uuid, vector=new_vectors[uuid], payload=pl))
    # 배치 upsert
    for i in range(0, len(points), 100):
        qc.upsert(collection_name=collection, points=points[i:i + 100])
    print(f"[reembed] Qdrant upsert: {len(points)} points")

    # MariaDB chunk_index.embedding_text UPDATE
    print("[reembed] MariaDB chunk_index.embedding_text UPDATE ...")
    cur = conn.cursor()
    for cid, _, new_text in plan:
        cur.execute(
            "UPDATE chunk_index SET embedding_text=%s WHERE chunk_id=%s AND run_id=%s",
            (new_text, cid, run_id),
        )
    conn.commit()
    cur.close()
    conn.close()
    print(f"[reembed] 완료. total {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
