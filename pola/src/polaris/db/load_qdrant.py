"""Qdrant 적재 — vector + payload, ingest_status workflow.

입력:
  ___test/2_Chuck/03_chunks/{corp}/{table_nl,text}.jsonl  (payload + chunk_id)
  ___test/2_Chuck/04_embeddings/{corp}/{type}.npy + .ids.json

룰:
  1. 적재 시 ingest_status='pending'
  2. 모든 corp/type 완료 후 일괄 'ready' 갱신
  3. 검색은 active 컬렉션 + ingest_status='ready' 강제 (RunScopedSession 룰)

run_id 는 MariaDB active_run_manifest standby 슬롯에서 읽음 → 일관성 보장.
"""
from __future__ import annotations
import argparse, hashlib, json, sys, time
from pathlib import Path

import numpy as np

from polaris.config import (qdrant_client, mariadb_conn, QDRANT_COLLECTION_STANDBY,
                            DATA_ROOT, CHUNKS_DIR, CORPS)

CHUNKS = CHUNKS_DIR
EMB = DATA_ROOT / "2_Chuck" / "04_embeddings"
UPSERT_BATCH = 256


def get_standby_run_id() -> str:
    conn = mariadb_conn()
    cur = conn.cursor()
    cur.execute("SELECT standby_run_id FROM active_run_manifest WHERE id=1")
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row or not row[0]:
        raise RuntimeError("standby_run_id 없음 — load_mariadb.py 먼저 실행해야 함")
    return row[0]


def chunk_id_to_uuid(chunk_id: str) -> str:
    """Qdrant point id 는 정수 또는 UUID. chunk_id(16자hex)를 결정론 UUID 로 변환."""
    h = hashlib.md5(chunk_id.encode("utf-8")).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def upsert_corp_type(client, run_id: str, corp: str, ctype: str) -> dict:
    """단일 corp/type 적재 → ingest_status='pending'."""
    from qdrant_client.models import PointStruct
    jsonl = CHUNKS / corp / f"{ctype}.jsonl"
    npy = EMB / corp / f"{ctype}.npy"
    ids_json = EMB / corp / f"{ctype}.ids.json"

    if not (jsonl.is_file() and npy.is_file() and ids_json.is_file()):
        return {"status": "missing_input"}

    arr = np.load(npy)
    ids = json.loads(ids_json.read_text(encoding="utf-8"))
    if len(arr) != len(ids):
        return {"status": "size_mismatch", "arr": len(arr), "ids": len(ids)}

    # chunk_id → payload 매핑 (jsonl 읽기)
    payloads: dict[str, dict] = {}
    with jsonl.open(encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            cid = r.get("chunk_id")
            if cid:
                pl = r.get("payload", {}).copy()
                pl["chunk_id"] = cid
                pl["run_id"] = run_id
                pl["ingest_status"] = "pending"
                payloads[cid] = pl

    points = []
    skipped = 0
    for cid, vec in zip(ids, arr):
        pl = payloads.get(cid)
        if not pl:
            skipped += 1
            continue
        points.append(PointStruct(
            id=chunk_id_to_uuid(cid),
            vector=vec.tolist(),
            payload=pl,
        ))

    n = 0
    for i in range(0, len(points), UPSERT_BATCH):
        # 각 배치를 wait=True 로 적용 확정 (이전: wait=False 후 마지막 1포인트만 flush → 내구성 착시)
        client.upsert(
            collection_name=QDRANT_COLLECTION_STANDBY,
            points=points[i:i + UPSERT_BATCH],
            wait=True,
        )
        n += min(UPSERT_BATCH, len(points) - i)
    return {"status": "ok", "n": n, "skipped": skipped}


def mark_ready(client, run_id: str) -> int:
    """본 run_id 의 모든 point 를 ingest_status='ready' 로 일괄 갱신.

    + MariaDB chunk_index 도 ready 로 동기 갱신 + active_run_manifest 의
      standby_status='ready_to_promote' 로 전이. → 다음 단계는 promote_run.py.
    """
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    flt = Filter(must=[
        FieldCondition(key="run_id", match=MatchValue(value=run_id)),
    ])
    # qdrant-client 1.18+ : set_payload 가 points 인자(필터 또는 id 리스트) 필수
    client.set_payload(
        collection_name=QDRANT_COLLECTION_STANDBY,
        payload={"ingest_status": "ready"},
        points=flt,
        wait=True,
    )
    info = client.get_collection(QDRANT_COLLECTION_STANDBY)

    # MariaDB 측 ingest_status='ready' 동기 갱신 + standby_status='ready_to_promote'
    conn = mariadb_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE chunk_index SET ingest_status='ready', ready_at=NOW() WHERE run_id=%s",
        (run_id,),
    )
    cur.execute(
        "UPDATE active_run_manifest SET standby_status='ready_to_promote' WHERE id=1",
    )
    conn.commit()
    cur.close(); conn.close()

    return info.points_count


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-ready", action="store_true",
                    help="ingest_status='pending' 까지만 (smoke 용)")
    ap.add_argument("--use-active", action="store_true",
                    help="standby 대신 active_run_id 사용 (운영 회복 케이스).")
    args = ap.parse_args()

    t0 = time.time()
    if args.use_active:
        from polaris.config import mariadb_conn
        conn = mariadb_conn(); cur = conn.cursor()
        cur.execute("SELECT active_run_id FROM active_run_manifest WHERE id=1")
        run_id = cur.fetchone()[0]
        cur.close(); conn.close()
    else:
        run_id = get_standby_run_id()
    print(f"[load_qdrant] run_id={run_id} → collection={QDRANT_COLLECTION_STANDBY}")
    client = qdrant_client()
    overall = []
    total_n = 0
    for corp in CORPS:
        for ctype in ("table_nl", "text"):
            stats = upsert_corp_type(client, run_id, corp, ctype)
            stats.update({"corp": corp, "type": ctype})
            overall.append(stats)
            if stats.get("status") == "ok":
                total_n += stats["n"]
                print(f"  {corp}/{ctype}: {stats['n']} 적재 (skipped={stats.get('skipped',0)})")
            else:
                print(f"  {corp}/{ctype}: {stats.get('status')}")

    if not args.no_ready:
        print(f"\n[load_qdrant] ingest_status='ready' 일괄 갱신…")
        n_ready = mark_ready(client, run_id)
        print(f"  컬렉션 총 points: {n_ready}")
    else:
        print(f"\n[load_qdrant] --no-ready: ingest_status='pending' 유지")

    elapsed = time.time() - t0
    print(f"\n=== Qdrant 적재 완료 ({elapsed:.1f}s, run_id={run_id}, 적재 {total_n}) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
