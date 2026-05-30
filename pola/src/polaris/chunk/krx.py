"""KRX 5사 일별 OHLCV → 월별 요약 청크 + 3DB 적재.

입력: {DATA_ROOT}/rawData/{corp_code}/krx/daily_ohlcv_{year}.json
청킹: (corp, year, month) = 1 청크. 월별 OHLCV 요약 + 거래량.

예시:
  "삼성전자(00126380) 2025-05 일별주가 요약
   거래일 21일, 시가 75,000원, 종가 78,500원 (+4.67%), 최고 80,200원, 최저 73,800원
   평균 거래량 12,345,678주, 총 거래량 259,259,238주"
"""
from __future__ import annotations
import hashlib, json, time
from collections import defaultdict
from datetime import date
from pathlib import Path

import httpx

from polaris.config import (
    DATA_ROOT, mariadb_conn, qdrant_client,
    OLLAMA_BASE, OLLAMA_EMBED_MODEL, get_active_run,
    CORPS, get_corp_meta,
)

RAW_BASE = DATA_ROOT / "rawData"
BATCH = 32


def _hash16(*parts: str) -> str:
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _chunk_uuid(chunk_id: str) -> str:
    h = hashlib.md5(chunk_id.encode("utf-8")).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def build_chunks() -> list[dict]:
    chunks = []
    for corp in CORPS:
        meta = get_corp_meta(corp)
        corp_name = meta.get("corp_name", corp)
        krx_dir = RAW_BASE / corp / "krx"
        if not krx_dir.is_dir():
            continue
        for jf in sorted(krx_dir.glob("daily_ohlcv_*.json")):
            try:
                doc = json.loads(jf.read_text(encoding="utf-8"))
            except Exception:
                continue
            year = doc.get("year")
            rows = doc.get("rows", []) or []
            if not rows or not year:
                continue
            # 월별 그룹화
            by_month: dict[str, list] = defaultdict(list)
            for r in rows:
                bd = (r.get("basDd") or "").strip()
                if len(bd) < 6: continue
                ym = f"{bd[:4]}-{bd[4:6]}"
                by_month[ym].append(r)
            for ym, mrows in sorted(by_month.items()):
                if not mrows: continue
                mrows = sorted(mrows, key=lambda x: x.get("basDd", ""))
                opens = [r.get("open") for r in mrows if r.get("open") is not None]
                closes = [r.get("close") for r in mrows if r.get("close") is not None]
                highs = [r.get("high") for r in mrows if r.get("high") is not None]
                lows = [r.get("low") for r in mrows if r.get("low") is not None]
                vols = [r.get("volume") for r in mrows if r.get("volume") is not None]
                if not closes: continue
                first_open = opens[0] if opens else closes[0]
                last_close = closes[-1]
                month_change_pct = (last_close - first_open) / first_open * 100 if first_open else 0
                text = (
                    f"{corp_name}({corp}) {ym} 일별주가 요약\n"
                    f"거래일 {len(mrows)}일, "
                    f"시가 {first_open:,.0f}원, 종가 {last_close:,.0f}원 ({month_change_pct:+.2f}%), "
                    f"최고 {max(highs):,.0f}원, 최저 {min(lows):,.0f}원\n"
                    f"평균 거래량 {int(sum(vols)/len(vols)):,}주, "
                    f"총 거래량 {sum(vols):,}주"
                )
                cid = _hash16("krx", corp, ym)
                chunks.append({
                    "chunk_id": cid,
                    "corp_code": corp,
                    "year_month": ym,
                    "year": year,
                    "embedding_text": text,
                })
    return chunks


def _existing_ready_chunk_ids() -> set[str]:
    """MariaDB 에 이미 ready 인 krx_ohlcv chunk_id (증분 skip)."""
    conn = mariadb_conn(); cur = conn.cursor()
    cur.execute("""SELECT chunk_id FROM chunk_index
                   WHERE chunk_type='krx_ohlcv' AND ingest_status='ready'""")
    out = {r[0] for r in cur.fetchall()}
    cur.close(); conn.close()
    return out


def main():
    run_id, collection = get_active_run()
    print(f"[krx-load] active run_id={run_id} collection={collection}")
    chunks_all = build_chunks()
    print(f"[krx-load] 전체 청크: {len(chunks_all):,}")
    if not chunks_all:
        return 0

    # 증분: 이번달 청크는 매일 OHLCV 추가되므로 항상 재임베딩,
    # 과거달은 마감되어 변하지 않으므로 chunk_id ready 면 skip.
    current_ym = date.today().strftime("%Y-%m")
    existing = _existing_ready_chunk_ids()
    chunks = [c for c in chunks_all
              if c["year_month"] == current_ym or c["chunk_id"] not in existing]
    skipped = len(chunks_all) - len(chunks)
    print(f"[krx-load] 신규/갱신 청크: {len(chunks)} / 과거달 cached: {skipped}")
    if not chunks:
        print("[krx-load] 신규 없음 - skip")
        return 0

    print(f"[krx-load] 임베딩 (batch={BATCH})...")
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
    print(f"[krx-load] 임베딩 완료: {len(vectors)} ({time.time() - t0:.0f}s)")

    conn = mariadb_conn(); cur = conn.cursor()
    for c in chunks:
        cur.execute("""INSERT INTO chunk_index
            (chunk_id, run_id, corp_code, rcept_no, chunk_type, bsns_year,
             embedding_text, ingest_status, ready_at)
            VALUES (%s, %s, %s, %s, 'krx_ohlcv', %s, %s, 'ready', NOW())
            ON DUPLICATE KEY UPDATE
              embedding_text=VALUES(embedding_text),
              ingest_status='ready', ready_at=NOW()""",
            (c["chunk_id"], run_id, c["corp_code"], c["year_month"][:14],
             c["year"], c["embedding_text"]))
    conn.commit(); cur.close(); conn.close()
    print(f"[krx-load] MariaDB INSERT: {len(chunks)}")

    qc = qdrant_client()
    from qdrant_client.models import PointStruct
    points = []
    for c in chunks:
        v = vectors.get(c["chunk_id"])
        if not v: continue
        points.append(PointStruct(
            id=_chunk_uuid(c["chunk_id"]), vector=v,
            payload={
                "chunk_id": c["chunk_id"], "chunk_type": "krx_ohlcv",
                "corp_code": c["corp_code"], "rcept_no": c["year_month"][:14],
                "bsns_year": c["year"], "year_month": c["year_month"],
                "ingest_status": "ready", "run_id": run_id,
            },
        ))
    for i in range(0, len(points), 100):
        qc.upsert(collection_name=collection, points=points[i:i + 100])
    print(f"[krx-load] Qdrant upsert: {len(points)}")
    print(f"[krx-load] 완료. {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
