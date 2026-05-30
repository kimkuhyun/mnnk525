"""[DEPRECATED — 구 MACRO 뉴스 경로] 뉴스 본문 → 청킹 + 임베딩 + 3DB 적재.

⚠ 신규는 `polaris.ingest.news_crawl.load`(v2)를 쓴다: 회사별(corp_code) document_unified 경유 +
  polaris-doc-1024 컬렉션. 본 모듈은 corp_code='00000000'(MACRO)·DART 컬렉션에 적재하는 구경로로
  유지보수 비권장(점검보고서 chunk_embed 참조).


입력:
  - MariaDB news_raw 테이블 (SSOT)

청킹 정책 (단순화):
  - **1 뉴스 = 1 청크** (corp 별 분리 안 함)
  - `corp_code = '00000000'` (MACRO, 회사 무관)
  - embedding_text 에 publisher + date + title prefix → 검색 시 회사명 쿼리로 의미 매칭

출력:
  - MariaDB chunk_index INSERT (chunk_type='news_text', ingest_status='ready')
  - Qdrant upsert (vector + payload)
  - Neo4j NewsArticle 노드 (MENTIONS 관계는 없음 - 매칭 안 함)

chunk_id: hash16(news_id)
"""
from __future__ import annotations
import hashlib, time
from datetime import datetime

import httpx

from polaris.config import (
    DATA_ROOT, mariadb_conn, qdrant_client, neo4j_driver,
    OLLAMA_BASE, OLLAMA_EMBED_MODEL, get_active_run,
)

MACRO_CORP = "00000000"
MICRO_MAX_CHARS = 1500
BATCH = 32


def _hash16(*parts: str) -> str:
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _chunk_uuid(chunk_id: str) -> str:
    h = hashlib.md5(chunk_id.encode("utf-8")).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def _parse_published(s: str) -> str:
    if not s:
        return ""
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except Exception:
            continue
    return s[:10]


def build_chunks() -> list[dict]:
    """news_raw 전체 SELECT → 1뉴스=1청크 (corp 매칭 없음)."""
    chunks: list[dict] = []
    conn = mariadb_conn(); cur = conn.cursor()
    cur.execute("""SELECT news_id, title, body, publisher, url, published
                   FROM news_raw""")
    for nid, title, body, publisher, url, published in cur.fetchall():
        body = (body or "").strip()
        if not body:
            continue
        title = (title or "").strip()
        publisher = publisher or ""
        date_str = _parse_published(str(published) if published else "")
        prefix = f"{publisher} {date_str} {title}".strip()
        body_short = body[:MICRO_MAX_CHARS]
        embedding_text = f"{prefix}\n\n{body_short}"
        cid = _hash16("news", nid)
        chunks.append({
            "chunk_id": cid,
            "corp_code": MACRO_CORP,
            "rcept_no": nid[:14],
            "news_id": nid,
            "embedding_text": embedding_text,
            "title": title,
            "publisher": publisher,
            "date": date_str,
            "url": url or "",
        })
    cur.close(); conn.close()
    return chunks


def _existing_ready_chunk_ids() -> set[str]:
    conn = mariadb_conn(); cur = conn.cursor()
    cur.execute("""SELECT chunk_id FROM chunk_index
                   WHERE chunk_type='news_text' AND ingest_status='ready'""")
    out = {r[0] for r in cur.fetchall()}
    cur.close(); conn.close()
    return out


def main():
    run_id, collection = get_active_run()
    print(f"[news-load] active run_id={run_id} collection={collection}")
    chunks_all = build_chunks()
    print(f"[news-load] 전체 뉴스 청크: {len(chunks_all):,} (1뉴스=1청크, corp={MACRO_CORP})")

    existing = _existing_ready_chunk_ids()
    chunks = [c for c in chunks_all if c["chunk_id"] not in existing]
    print(f"[news-load] 신규: {len(chunks)} / cached: {len(chunks_all) - len(chunks)}")
    if not chunks:
        print("[news-load] 신규 없음 - skip")
        return 0

    # 1) 임베딩
    print(f"[news-load] 임베딩 (batch={BATCH})...")
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
    print(f"[news-load] 임베딩 완료: {len(vectors)} ({time.time() - t0:.0f}s)")

    # 2) MariaDB chunk_index
    conn = mariadb_conn(); cur = conn.cursor()
    for c in chunks:
        cur.execute("""INSERT INTO chunk_index
            (chunk_id, run_id, corp_code, rcept_no, chunk_type,
             embedding_text, ingest_status, ready_at)
            VALUES (%s, %s, %s, %s, 'news_text', %s, 'ready', NOW())
            ON DUPLICATE KEY UPDATE
              embedding_text=VALUES(embedding_text),
              ingest_status='ready', ready_at=NOW()""",
            (c["chunk_id"], run_id, c["corp_code"], c["rcept_no"], c["embedding_text"]))
    conn.commit(); cur.close()
    print(f"[news-load] MariaDB INSERT: {len(chunks)} rows")

    # 3) Qdrant upsert
    qc = qdrant_client()
    from qdrant_client.models import PointStruct
    points = []
    for c in chunks:
        v = vectors.get(c["chunk_id"])
        if not v:
            continue
        points.append(PointStruct(
            id=_chunk_uuid(c["chunk_id"]), vector=v,
            payload={
                "chunk_id": c["chunk_id"], "chunk_type": "news_text",
                "corp_code": c["corp_code"], "rcept_no": c["rcept_no"],
                "news_id": c["news_id"],
                "ingest_status": "ready", "run_id": run_id,
                "title": c["title"], "publisher": c["publisher"],
                "date": c["date"], "url": c["url"],
            },
        ))
    for i in range(0, len(points), 100):
        qc.upsert(collection_name=collection, points=points[i:i + 100])
    print(f"[news-load] Qdrant upsert: {len(points)}")

    # 4) Neo4j NewsArticle 노드만 (MENTIONS 없음 - 매칭 제거)
    drv = neo4j_driver()
    with drv.session() as s:
        s.run("CREATE INDEX news_id IF NOT EXISTS FOR (n:NewsArticle) ON (n.news_id)")
        for c in chunks:
            s.run("""MERGE (n:NewsArticle {news_id:$nid})
                       SET n.title=$title, n.publisher=$publisher,
                           n.date=$date, n.url=$url, n.run_id=$rid""",
                  nid=c["news_id"], title=c["title"], publisher=c["publisher"],
                  date=c["date"], url=c["url"], rid=run_id)
    drv.close(); conn.close()
    print(f"[news-load] 완료. total {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
