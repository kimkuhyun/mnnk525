"""1회성: stale npy 캐시로 누락된 table_nl 청크 벡터 백필.

증상: chunk.table 가 jsonl 을 재생성(38,430)했으나 embed 가 파일단위 skip 으로
      npy(35,020)를 갱신 안 함 → 3,410 청크가 chunk_index='ready' 인데 Qdrant 없음.

처리: jsonl 에는 있고 npy.ids 에 없는 chunk_id 만 임베딩 →
      ① active green 컬렉션에 upsert (run_id=active, ingest_status='ready')
      ② npy + ids.json 에 append (다음 build 재현성)

실행:  uv run python scripts/backfill_table_vectors.py
"""
from __future__ import annotations
import json
from pathlib import Path

import httpx
import numpy as np
from qdrant_client.models import PointStruct

from polaris.config import DATA_ROOT, CHUNKS_DIR, mariadb_conn, qdrant_client
from polaris.embed.bge_m3 import embed_batch, normalize
from polaris.db.load_qdrant import chunk_id_to_uuid

EMB = DATA_ROOT / "2_Chuck" / "04_embeddings"
CORPS = ["00126380", "00161383", "00164779", "00118804"]
CTYPE = "table_nl"
BATCH = 32


def active_run() -> tuple[str, str]:
    conn = mariadb_conn(); cur = conn.cursor()
    cur.execute("SELECT active_run_id, active_qdrant_collection FROM active_run_manifest WHERE id=1")
    rid, col = cur.fetchone()
    cur.close(); conn.close()
    return rid, col


def main() -> None:
    run_id, collection = active_run()
    print(f"[backfill] active run_id={run_id} collection={collection}")
    q = qdrant_client()
    grand = 0
    with httpx.Client(timeout=120) as client:
        for corp in CORPS:
            jsonl = CHUNKS_DIR / corp / f"{CTYPE}.jsonl"
            npy = EMB / corp / f"{CTYPE}.npy"
            idsf = EMB / corp / f"{CTYPE}.ids.json"
            if not (jsonl.is_file() and npy.is_file() and idsf.is_file()):
                print(f"  {corp}: 입력 없음 skip"); continue

            have = set(json.loads(idsf.read_text(encoding="utf-8")))
            # jsonl 순서대로 누락분 수집 (payload 동반)
            miss_ids: list[str] = []
            miss_text: list[str] = []
            miss_pl: list[dict] = []
            with jsonl.open(encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    cid = r.get("chunk_id"); txt = r.get("embedding_text") or ""
                    if not cid or cid in have or not txt.strip():
                        continue
                    pl = (r.get("payload", {}) or {}).copy()
                    pl["chunk_id"] = cid; pl["run_id"] = run_id; pl["ingest_status"] = "ready"
                    miss_ids.append(cid); miss_text.append(txt); miss_pl.append(pl)

            if not miss_ids:
                print(f"  {corp}: 누락 없음 (npy={len(have)})"); continue

            print(f"  {corp}: 누락 {len(miss_ids)} 임베딩…")
            vecs = np.zeros((len(miss_text), 1024), dtype=np.float32)
            for i in range(0, len(miss_text), BATCH):
                embs = embed_batch(client, miss_text[i:i + BATCH])
                vecs[i:i + len(embs)] = np.array(embs, dtype=np.float32)
            vecs = normalize(vecs)
            assert int(np.isnan(vecs).sum()) == 0, "NaN 발생"

            # ① Qdrant upsert (active collection)
            points = [PointStruct(id=chunk_id_to_uuid(c), vector=v.tolist(), payload=p)
                      for c, v, p in zip(miss_ids, vecs, miss_pl)]
            for i in range(0, len(points), 256):
                q.upsert(collection_name=collection, points=points[i:i + 256], wait=True)

            # ② npy + ids append (캐시 정합)
            old = np.load(npy)
            np.save(npy, np.vstack([old, vecs]))
            new_ids = json.loads(idsf.read_text(encoding="utf-8")) + miss_ids
            idsf.write_text(json.dumps(new_ids, ensure_ascii=False), encoding="utf-8")
            print(f"  {corp}: upsert {len(points)} → npy {old.shape[0]}+{len(vecs)}={old.shape[0]+len(vecs)}")
            grand += len(points)

    print(f"\n[backfill] 완료. 추가 {grand} points → {collection}")


if __name__ == "__main__":
    main()
