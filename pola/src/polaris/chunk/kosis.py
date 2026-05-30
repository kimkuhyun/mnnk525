"""KOSIS (통계청) 메타 카탈로그 → 청크 + 3DB 적재.

KOSIS API 활용신청 제약으로 실제 통계값은 못 받고 통계표 목록(메타)만 적재.
검색 시 사용자가 "어떤 KOSIS 통계표가 있나" 정도 답변 가능.

입력: {DATA_ROOT}/rawData/_common/kosis/list_{카테고리}.json
출력: MariaDB chunk_index (chunk_type='kosis_meta', corp_code='00000000')
      + Qdrant payload

청크 1개 = KOSIS 통계표 1건. Contextual prefix: "통계청 [카테고리명] [통계표명]".
"""
from __future__ import annotations
import hashlib, json, time
from pathlib import Path

import httpx

from polaris.config import (
    DATA_ROOT, mariadb_conn, qdrant_client,
    OLLAMA_BASE, OLLAMA_EMBED_MODEL, get_active_run,
)

KOSIS_DIR = DATA_ROOT / "rawData" / "_common" / "kosis"
MACRO_CORP = "00000000"  # 거시 데이터 sentinel
BATCH = 32

KOSIS_CATEGORY_NAMES = {
    "A": "인구·가구", "B": "노동", "C": "소득·소비·자산",
    "D": "보건·사회", "F": "교육·훈련", "J": "농림·수산",
    "K": "광공업·에너지", "L": "건설·주택·국토",
    "M": "교통·물류·정보통신", "N": "무역·외환·국제수지",
    "O": "기업경영", "P": "금융", "Q": "재정",
    "R": "물가", "S": "환경",
}


def _hash16(*parts: str) -> str:
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _chunk_uuid(chunk_id: str) -> str:
    h = hashlib.md5(chunk_id.encode("utf-8")).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def build_chunks() -> list[dict]:
    chunks = []
    if not KOSIS_DIR.is_dir():
        return chunks
    for jf in sorted(KOSIS_DIR.glob("list_*.json")):
        cat_code = jf.stem.replace("list_", "")
        cat_name = KOSIS_CATEGORY_NAMES.get(cat_code, cat_code)
        try:
            rows = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        for r in rows or []:
            list_id = (r.get("LIST_ID") or "").strip()
            list_nm = (r.get("LIST_NM") or "").strip()
            vw_nm = (r.get("VW_NM") or "").strip()
            if not list_id or not list_nm:
                continue
            cid = _hash16("kosis", list_id)
            text = (
                f"통계청 KOSIS {vw_nm} {cat_name}\n"
                f"{list_nm} (통계표 코드: {list_id})\n"
                f"실제 통계값은 KOSIS 사이트 활용신청 후 조회 가능."
            )
            chunks.append({
                "chunk_id": cid,
                "list_id": list_id,
                "list_name": list_nm,
                "category_code": cat_code,
                "category_name": cat_name,
                "vw_name": vw_nm,
                "embedding_text": text,
            })
    return chunks


def main():
    run_id, collection = get_active_run()
    print(f"[kosis-load] active run_id={run_id} collection={collection}")
    chunks = build_chunks()
    print(f"[kosis-load] 청크: {len(chunks):,}")
    if not chunks:
        return 0

    # 임베딩
    print(f"[kosis-load] 임베딩 (batch={BATCH})...")
    vectors: dict[str, list[float]] = {}
    t0 = time.time()
    with httpx.Client(timeout=120) as http:
        for i in range(0, len(chunks), BATCH):
            batch = chunks[i:i + BATCH]
            texts = [c["embedding_text"] for c in batch]
            r = http.post(f"{OLLAMA_BASE}/api/embed",
                          json={"model": OLLAMA_EMBED_MODEL, "input": texts})
            r.raise_for_status()
            for c, v in zip(batch, r.json()["embeddings"]):
                vectors[c["chunk_id"]] = v
    print(f"[kosis-load] 임베딩 완료: {len(vectors)} ({time.time() - t0:.0f}s)")

    # MariaDB INSERT
    conn = mariadb_conn(); cur = conn.cursor()
    for c in chunks:
        cur.execute("""INSERT INTO chunk_index
            (chunk_id, run_id, corp_code, rcept_no, chunk_type,
             embedding_text, ingest_status, ready_at)
            VALUES (%s, %s, %s, %s, 'kosis_meta', %s, 'ready', NOW())
            ON DUPLICATE KEY UPDATE
              embedding_text=VALUES(embedding_text),
              ingest_status='ready', ready_at=NOW()""",
            (c["chunk_id"], run_id, MACRO_CORP, c["list_id"][:14],
             c["embedding_text"]))
    conn.commit(); cur.close(); conn.close()
    print(f"[kosis-load] MariaDB INSERT: {len(chunks)}")

    # Qdrant upsert
    qc = qdrant_client()
    from qdrant_client.models import PointStruct
    points = []
    for c in chunks:
        v = vectors.get(c["chunk_id"])
        if not v: continue
        points.append(PointStruct(
            id=_chunk_uuid(c["chunk_id"]), vector=v,
            payload={
                "chunk_id": c["chunk_id"], "chunk_type": "kosis_meta",
                "corp_code": MACRO_CORP, "rcept_no": c["list_id"][:14],
                "ingest_status": "ready", "run_id": run_id,
                "kosis_list_id": c["list_id"],
                "kosis_list_name": c["list_name"],
                "kosis_category": c["category_name"],
            },
        ))
    for i in range(0, len(points), 100):
        qc.upsert(collection_name=collection, points=points[i:i + 100])
    print(f"[kosis-load] Qdrant upsert: {len(points)}")
    print(f"[kosis-load] 완료. {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
