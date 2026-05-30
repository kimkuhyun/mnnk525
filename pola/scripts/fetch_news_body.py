"""뉴스 본문 fetch + lead 500자 추출 → Neo4j NewsArticle.summary + Qdrant payload.

흐름:
  1. Neo4j NewsArticle (url 있는 것) → URL list
  2. httpx + BeautifulSoup4 로 본문 추출 (article/p/main 태그)
  3. 본문 첫 500자 = summary (자동 lead)
  4. Neo4j NewsArticle.summary 부착
  5. Qdrant payload.summary 추가 + summary 기반 re-embedding (optional)

실패 처리: timeout 5초, 4xx/5xx skip, raw 보존
"""
from __future__ import annotations
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import httpx
import numpy as np
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from polaris.config import neo4j_driver, qdrant_client, OLLAMA_BASE, OLLAMA_EMBED_MODEL

RUN_ID = "20260528_0808_01"
COLLECTION = "polaris-1024-cos-green"
SUMMARY_LEN = 500
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


def extract_body(html: str) -> str:
    """주요 본문 추출 — readability-lxml + BeautifulSoup fallback."""
    # 1) readability-lxml (article 본문 자동 추출, 광고 제거)
    try:
        from readability import Document
        doc = Document(html)
        article_html = doc.summary()
        soup = BeautifulSoup(article_html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer",
                         "aside", "iframe", "form", "button", "a"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 200:
            return text
    except Exception:
        pass

    # 2) fallback: 우선순위 태그
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside",
                     "iframe", "form", "button"]):
        tag.decompose()
    for sel in ["article", "main", "[class*=article-body]",
                "[class*=news-body]", "[itemprop=articleBody]"]:
        nodes = soup.select(sel)
        if nodes:
            text = " ".join(n.get_text(" ", strip=True) for n in nodes)
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > 200:
                return text
    # last fallback: p 태그
    ps = soup.find_all("p")
    text = " ".join(p.get_text(" ", strip=True) for p in ps)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_one(client: httpx.Client, url: str, news_id: str) -> tuple[str | None, str | None]:
    """본문 fetch → (lead_summary, full_body) 반환. fail 시 (None, None)."""
    try:
        r = client.get(url, headers=HEADERS, timeout=8.0, follow_redirects=True)
        if r.status_code >= 400:
            return None, None
        body = extract_body(r.text)
        if len(body) < 100:
            return None, None
        summary = body[:SUMMARY_LEN].strip()
        return summary, body[:5000]
    except Exception:
        return None, None


def main():
    print("=" * 60)
    print("뉴스 본문 fetch + summary 적재")
    print("=" * 60)

    # 1. URL list from Neo4j (re-fetch 모드: all 또는 missing 만)
    import os
    force_all = os.environ.get("FETCH_ALL") == "1"
    drv = neo4j_driver()
    with drv.session() as s:
        if force_all:
            rows = list(s.run("""
                MATCH (n:NewsArticle)
                WHERE n.url IS NOT NULL AND n.url <> ''
                RETURN n.news_id AS news_id, n.url AS url, n.title AS title
            """))
        else:
            rows = list(s.run("""
                MATCH (n:NewsArticle)
                WHERE n.url IS NOT NULL AND n.url <> ''
                  AND (n.summary IS NULL OR n.summary = '')
                RETURN n.news_id AS news_id, n.url AS url, n.title AS title
            """))
    drv.close()
    print(f"  대상 뉴스 (summary 없음): {len(rows)}")

    # 2. fetch
    out_records = []
    failed = []
    t0 = time.time()
    with httpx.Client(timeout=10.0) as client:
        for i, r in enumerate(rows, 1):
            summary, full = fetch_one(client, r["url"], r["news_id"])
            if summary:
                out_records.append({"news_id": r["news_id"], "url": r["url"],
                                    "title": r["title"], "summary": summary,
                                    "body": full})
            else:
                failed.append({"news_id": r["news_id"], "url": r["url"]})
            if i % 20 == 0:
                print(f"  [{i}/{len(rows)}] success={len(out_records)} fail={len(failed)} "
                       f"({time.time()-t0:.0f}s)")

    print(f"\n  fetch 완료: success={len(out_records)} fail={len(failed)} "
           f"({time.time()-t0:.0f}s)")

    # 3. Neo4j summary 부착
    drv = neo4j_driver()
    with drv.session() as s:
        BATCH = 100
        for i in range(0, len(out_records), BATCH):
            sub = out_records[i:i+BATCH]
            s.run("""
                UNWIND $rows AS r
                MATCH (n:NewsArticle {news_id: r.news_id})
                SET n.summary = r.summary,
                    n.body_fetched_at = datetime(),
                    n.summary_len = size(r.summary)
            """, rows=sub)
    drv.close()
    print(f"\n  Neo4j summary 부착: {len(out_records)}")

    # 4. Qdrant payload + re-embed summary
    print("  Qdrant payload + embedding (summary 기반)...")
    qc = qdrant_client()
    from qdrant_client.models import PointStruct
    points = []
    BATCH = 32
    with httpx.Client(timeout=120) as http:
        for i in range(0, len(out_records), BATCH):
            sub = out_records[i:i+BATCH]
            # title + summary 로 embedding
            texts = [f"{r['title']}\n{r['summary']}" for r in sub]
            r2 = http.post(f"{OLLAMA_BASE}/api/embed",
                           json={"model": OLLAMA_EMBED_MODEL, "input": texts})
            r2.raise_for_status()
            embs = r2.json()["embeddings"]
            for j, r in enumerate(sub):
                pid_h = hashlib.md5(("news:" + r["news_id"]).encode()).hexdigest()
                pid = f"{pid_h[0:8]}-{pid_h[8:12]}-{pid_h[12:16]}-{pid_h[16:20]}-{pid_h[20:32]}"
                points.append(PointStruct(
                    id=pid, vector=embs[j],
                    payload={
                        "chunk_id": hashlib.md5(("news:" + r["news_id"]).encode()).hexdigest()[:16],
                        "chunk_type": "news_text",
                        "news_id": r["news_id"],
                        "corp_code": "00000000",
                        "title": r["title"],
                        "summary": r["summary"],
                        "run_id": RUN_ID,
                        "ingest_status": "ready",
                    }
                ))
    UP_BATCH = 128
    for i in range(0, len(points), UP_BATCH):
        qc.upsert(collection_name=COLLECTION, points=points[i:i+UP_BATCH])
    print(f"  Qdrant upserted: {len(points)} (summary embedding)")

    # 5. failed log
    if failed:
        out_dir = Path("data/4_dbGoldTest/news")
        out_dir.mkdir(parents=True, exist_ok=True)
        log_path = out_dir / "fetch_failed.jsonl"
        with log_path.open("w", encoding="utf-8") as f:
            for fl in failed:
                f.write(json.dumps(fl, ensure_ascii=False) + "\n")
        print(f"  failed log: {log_path} ({len(failed)} URLs)")

    print(f"\n  완료. Neo4j summary {len(out_records)}, Qdrant {len(points)}")


if __name__ == "__main__":
    raise SystemExit(main())
