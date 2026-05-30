"""보일러플레이트 청크 soft-delete (ingest_status='ready' → 'pending').

대상: chunk_index 중 text_micro/text_macro 이면서 token_count<50 AND
      "기재.*않습니다 / 기재.*생략 / 참고하시기 바랍니다 / 본 항목.*기재 /
       해당사항 없음" 패턴 매칭.

처리:
  1. MariaDB chunk_index.ingest_status = 'pending' UPDATE
  2. Qdrant 동일 청크의 payload.ingest_status = 'pending' (set_payload)

효과:
  - run_gold.py 검색 filter (ingest_status='ready') 에서 자동 제외
  - 인덱스 자체는 그대로 (롤백 가능, SQL UPDATE 한 줄 + Qdrant set_payload)

용도: 청킹 단계 수정 전 빠른 검증. 효과 검증되면 run_stage_c2.py 본격 수정.

롤백: UPDATE chunk_index SET ingest_status='ready' WHERE chunk_id IN (...) AND ingest_status='pending';
      (마킹된 chunk_id 목록은 출력 JSON 으로 저장)
"""
from __future__ import annotations
import hashlib, json, sys
from pathlib import Path

from polaris.config import mariadb_conn, qdrant_client, DATA_ROOT

OUT_LOG = DATA_ROOT / "4_dbGoldTest" / "_boilerplate_marked.json"

PATTERNS = [
    "%기재%않습니다%",
    "%기재를 생략%",
    "%기재하지 않%",
    "%기재하지 아니%",
    "%참고하시기 바랍니다%",
    "%본 항목%기재%",
    "%해당사항%없%",
]


def chunk_id_to_uuid(chunk_id: str) -> str:
    h = hashlib.md5(chunk_id.encode("utf-8")).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def main(dry_run: bool = False):
    conn = mariadb_conn()
    cur = conn.cursor()
    cur.execute(
        f"""SELECT chunk_id, run_id, token_count, LEFT(embedding_text, 100)
            FROM chunk_index
            WHERE ingest_status='ready'
              AND chunk_type IN ('text_micro','text_macro')
              AND token_count < 50
              AND ({' OR '.join(['embedding_text LIKE %s'] * len(PATTERNS))})""",
        PATTERNS,
    )
    rows = cur.fetchall()
    cur.close()
    print(f"[mark_boilerplate] {len(rows)} 청크 마킹 후보")

    if not rows:
        conn.close()
        return 0

    targets = [{"chunk_id": cid, "run_id": rid, "tc": tc, "head": head[:60]}
               for cid, rid, tc, head in rows]
    OUT_LOG.parent.mkdir(parents=True, exist_ok=True)
    OUT_LOG.write_text(json.dumps(targets, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    print(f"[mark_boilerplate] 로그 → {OUT_LOG.relative_to(ROOT)}")

    if dry_run:
        print("[mark_boilerplate] DRY-RUN — 실제 변경 없음")
        conn.close()
        return 0

    # MariaDB UPDATE
    cur = conn.cursor()
    chunk_ids = [r[0] for r in rows]
    ph = ",".join(["%s"] * len(chunk_ids))
    cur.execute(
        f"UPDATE chunk_index SET ingest_status='pending' WHERE chunk_id IN ({ph}) AND ingest_status='ready'",
        chunk_ids,
    )
    n_sql = cur.rowcount
    conn.commit()
    cur.close()
    print(f"[mark_boilerplate] MariaDB UPDATE: {n_sql} rows")

    # Qdrant set_payload
    cur = conn.cursor()
    cur.execute(
        "SELECT active_qdrant_collection FROM active_run_manifest WHERE id=1"
    )
    collection = cur.fetchone()[0]
    cur.close()
    conn.close()

    qc = qdrant_client()
    uuid_ids = [chunk_id_to_uuid(cid) for cid in chunk_ids]
    qc.set_payload(
        collection_name=collection,
        payload={"ingest_status": "pending"},
        points=uuid_ids,
    )
    print(f"[mark_boilerplate] Qdrant set_payload: {len(uuid_ids)} points ({collection})")
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    sys.exit(main(dry_run=args.dry_run))
