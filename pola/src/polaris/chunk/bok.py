"""BOK (한국은행 ECOS) 거시 시계열 → 청크 + 3DB 적재.

입력: {DATA_ROOT}/rawData/_common/bok/{STAT_CODE}_{cycle}_{start}_{end}.json
청킹: 같은 (STAT_CODE, ITEM) = 1 시계열 청크. TIME 모아서 NL 요약.

예시 청크:
  "한국은행 기준금리 (722Y001/0101000) 월별 시계열 2025-01~2026-12
   2025-01: 3.00%, 2025-02: 3.00%, ..., 2026-12: 2.50%
   최근값 2.50%, 평균 2.85%, 최저 2.50%, 최고 3.50%"
"""
from __future__ import annotations
import hashlib, json, time
from collections import defaultdict
from pathlib import Path

import httpx

from polaris.config import (
    DATA_ROOT, mariadb_conn, qdrant_client, neo4j_driver,
    OLLAMA_BASE, OLLAMA_EMBED_MODEL, get_active_run,
)

BOK_DIR = DATA_ROOT / "rawData" / "_common" / "bok"
MACRO_CORP = "00000000"
BATCH = 32


def _hash16(*parts: str) -> str:
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _chunk_uuid(chunk_id: str) -> str:
    h = hashlib.md5(chunk_id.encode("utf-8")).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def _fmt_time(t: str) -> str:
    """202501 → 2025-01, 20250115 → 2025-01-15."""
    t = (t or "").strip()
    if len(t) == 6: return f"{t[:4]}-{t[4:6]}"
    if len(t) == 8: return f"{t[:4]}-{t[4:6]}-{t[6:8]}"
    return t


def _fmt_val(v: str, unit: str) -> str:
    try:
        f = float(v)
        if f == int(f): return f"{int(f)}{unit}"
        return f"{f:.3f}{unit}".rstrip("0").rstrip(".") + (unit if not unit else "")
    except (ValueError, TypeError):
        return f"{v}{unit}"


def build_chunks() -> list[dict]:
    chunks = []
    if not BOK_DIR.is_dir():
        return chunks
    for jf in sorted(BOK_DIR.glob("*.json")):
        try:
            doc = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows = doc.get("StatisticSearch", {}).get("row", []) or []
        if not rows:
            continue
        # (stat_code, item_name1) 그룹화
        groups: dict[tuple, list] = defaultdict(list)
        for r in rows:
            key = (r.get("STAT_CODE", ""), r.get("ITEM_NAME1", "") or "전체",
                   r.get("ITEM_NAME2", "") or "", r.get("ITEM_NAME3", "") or "")
            groups[key].append(r)
        for (stat_code, item1, item2, item3), grp in groups.items():
            grp = sorted(grp, key=lambda x: x.get("TIME", ""))
            unit = (grp[0].get("UNIT_NAME") or "").strip()
            stat_name = grp[0].get("STAT_NAME", "").strip()
            full_item = " > ".join(x for x in [item1, item2, item3] if x)
            # 시계열 요약
            samples = []
            for r in grp[-24:]:  # 최근 24 포인트
                samples.append(f"{_fmt_time(r.get('TIME', ''))}: {r.get('DATA_VALUE', '')}{unit}")
            # 통계
            try:
                vals = [float(r.get("DATA_VALUE")) for r in grp if r.get("DATA_VALUE")]
                stats_line = (f"최근값 {vals[-1]:.2f}{unit}, 평균 {sum(vals)/len(vals):.2f}{unit}, "
                              f"최저 {min(vals):.2f}{unit}, 최고 {max(vals):.2f}{unit}, n={len(vals)}") if vals else ""
            except (ValueError, TypeError):
                stats_line = f"n={len(grp)}"
            head_time = _fmt_time(grp[0].get("TIME", ""))
            tail_time = _fmt_time(grp[-1].get("TIME", ""))
            text = (
                f"한국은행 ECOS {stat_name} ({stat_code} {full_item}) "
                f"{head_time}~{tail_time}\n\n"
                f"{stats_line}\n"
                f"최근 시계열: {', '.join(samples)}"
            )
            cid = _hash16("bok", stat_code, item1, item2, item3)
            chunks.append({
                "chunk_id": cid,
                "stat_code": stat_code,
                "stat_name": stat_name,
                "item": full_item,
                "unit": unit,
                "time_range": f"{head_time}~{tail_time}",
                "embedding_text": text,
            })
    return chunks


def main():
    run_id, collection = get_active_run()
    print(f"[bok-load] active run_id={run_id} collection={collection}")
    chunks = build_chunks()
    print(f"[bok-load] 청크: {len(chunks):,}")
    if not chunks:
        return 0

    print(f"[bok-load] 임베딩 (batch={BATCH})...")
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
    print(f"[bok-load] 임베딩 완료: {len(vectors)} ({time.time() - t0:.0f}s)")

    conn = mariadb_conn(); cur = conn.cursor()
    for c in chunks:
        cur.execute("""INSERT INTO chunk_index
            (chunk_id, run_id, corp_code, rcept_no, chunk_type,
             embedding_text, ingest_status, ready_at)
            VALUES (%s, %s, %s, %s, 'bok_macro', %s, 'ready', NOW())
            ON DUPLICATE KEY UPDATE
              embedding_text=VALUES(embedding_text),
              ingest_status='ready', ready_at=NOW()""",
            (c["chunk_id"], run_id, MACRO_CORP, c["stat_code"][:14],
             c["embedding_text"]))
    conn.commit(); cur.close()
    print(f"[bok-load] MariaDB INSERT: {len(chunks)}")

    qc = qdrant_client()
    from qdrant_client.models import PointStruct
    points = []
    for c in chunks:
        v = vectors.get(c["chunk_id"])
        if not v: continue
        points.append(PointStruct(
            id=_chunk_uuid(c["chunk_id"]), vector=v,
            payload={
                "chunk_id": c["chunk_id"], "chunk_type": "bok_macro",
                "corp_code": MACRO_CORP, "rcept_no": c["stat_code"][:14],
                "ingest_status": "ready", "run_id": run_id,
                "stat_code": c["stat_code"], "stat_name": c["stat_name"],
                "item": c["item"], "unit": c["unit"],
                "time_range": c["time_range"],
            },
        ))
    for i in range(0, len(points), 100):
        qc.upsert(collection_name=collection, points=points[i:i + 100])
    print(f"[bok-load] Qdrant upsert: {len(points)}")

    # Neo4j MacroIndicator 노드 (이미 12개 존재, MERGE)
    drv = neo4j_driver()
    with drv.session() as s:
        s.run("CREATE INDEX macro_stat IF NOT EXISTS FOR (m:MacroIndicator) ON (m.stat_code)")
        for c in chunks:
            s.run("""MERGE (m:MacroIndicator {stat_code:$sc, item:$it})
                       SET m.stat_name=$sn, m.unit=$u, m.time_range=$tr, m.run_id=$rid""",
                  sc=c["stat_code"], it=c["item"], sn=c["stat_name"],
                  u=c["unit"], tr=c["time_range"], rid=run_id)
    drv.close()
    conn.close()
    print(f"[bok-load] Neo4j MacroIndicator MERGE: {len(chunks)}")
    print(f"[bok-load] 완료. {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
