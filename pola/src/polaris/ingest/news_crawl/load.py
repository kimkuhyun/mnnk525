"""뉴스 v2 파이프라인 — news_raw → document_unified → Qdrant · Neo4j · mention_daily.

기존 MACRO 매칭(stage_b4_news)은 폐기. 뉴스를 회사별(corp_code)로 적재하고
검색(Qdrant)·관계(Neo4j Document-ABOUT-Org)·집계(mention_daily)를 정합 키(doc_id)로 연결한다.

정합 키:  doc_id = sha1("news:"+news_id)[:16]
  · MariaDB document_unified.doc_id (PK)
  · Qdrant  point.payload.doc_id  (point.id = int(doc_id,16))
  · Neo4j   (:Document {doc_id})

실행:  uv run python -m polaris.ingest.news_crawl.load
"""
from __future__ import annotations

import hashlib
import json

import httpx
import numpy as np
from qdrant_client.models import Distance, PointStruct, VectorParams

from polaris.config import CORP_NAME_TO_CODE, mariadb_conn, neo4j_driver, qdrant_client
from polaris.embed.bge_m3 import embed_batch, normalize

# 크롤 키워드(news_raw.category) → corp_code. config(.env) 단일 소스.
CORP_MAP = CORP_NAME_TO_CODE
QCOL = "polaris-doc-1024"
VEC = 1024
BATCH = 32


def doc_id_of(news_id: str) -> str:
    return hashlib.sha1(f"news:{news_id}".encode()).hexdigest()[:16]


# ── 스키마 보장 (ERD §8.2) ──────────────────────────────────────────
def ensure_schema() -> None:
    conn = mariadb_conn()
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS document_unified (
        doc_id       VARCHAR(32) PRIMARY KEY,
        source_type  VARCHAR(20) NOT NULL,
        origin_id    VARCHAR(64),
        corp_code    VARCHAR(8),
        ts           DATETIME,
        title        VARCHAR(500),
        url          VARCHAR(1024),
        body         LONGTEXT,
        metadata     JSON,
        lang         VARCHAR(8)  DEFAULT 'ko',
        credibility  VARCHAR(8)  DEFAULT 'mid',
        ingested_at  DATETIME    DEFAULT CURRENT_TIMESTAMP,
        KEY idx_corp_ts (corp_code, ts),
        KEY idx_source (source_type)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    cur.execute("""CREATE TABLE IF NOT EXISTS mention_daily (
        corp_code        VARCHAR(8)  NOT NULL,
        date             DATE        NOT NULL,
        source_type      VARCHAR(20) NOT NULL,
        mention_cnt      INT         DEFAULT 0,
        evidence_doc_ids JSON,
        PRIMARY KEY (corp_code, date, source_type)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    conn.commit()
    cur.close()
    conn.close()


def ensure_qdrant() -> None:
    q = qdrant_client()
    names = [c.name for c in q.get_collections().collections]
    if QCOL not in names:
        q.create_collection(QCOL, vectors_config=VectorParams(size=VEC, distance=Distance.COSINE))


# ── ① news_raw → document_unified ──────────────────────────────────
def step1_unified() -> int:
    conn = mariadb_conn()
    cur = conn.cursor()
    cur.execute("SELECT news_id, publisher, category, title, url, published, body, meta FROM news_raw")
    rows = cur.fetchall()
    n = 0
    for nid, pub, cat, title, url, published, body, meta in rows:
        corp = CORP_MAP.get(cat or "")
        if not corp:
            continue  # 매핑 안 되는 키워드는 skip
        did = doc_id_of(nid)
        md = {"publisher": pub, "url": url}
        try:
            md.update(json.loads(meta) if meta else {})
        except Exception:
            pass
        cur.execute("""INSERT INTO document_unified
            (doc_id, source_type, origin_id, corp_code, ts, title, url, body, metadata)
            VALUES (%s,'news',%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE title=VALUES(title), body=VALUES(body),
              ts=VALUES(ts), url=VALUES(url), metadata=VALUES(metadata)""",
            (did, nid, corp, published, (title or "")[:500], (url or "")[:1024],
             body or "", json.dumps(md, ensure_ascii=False)))
        n += 1
    conn.commit()
    cur.close()
    conn.close()
    return n


# ── ② document_unified → Qdrant (임베딩) ───────────────────────────
def step2_qdrant() -> int:
    conn = mariadb_conn()
    cur = conn.cursor()
    cur.execute("""SELECT doc_id, corp_code, ts, title, url, body, metadata
                   FROM document_unified WHERE source_type='news'""")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    if not rows:
        return 0
    q = qdrant_client()
    total = 0
    with httpx.Client(timeout=120) as client:
        for i in range(0, len(rows), BATCH):
            batch = rows[i:i + BATCH]
            texts = []
            for _did, _corp, ts, title, _url, body, md in batch:
                pub = ""
                try:
                    pub = (json.loads(md) if md else {}).get("publisher", "")
                except Exception:
                    pass
                # 뉴스 embedding_text = "{publisher} {date} {title}\n\n{body[:1500]}" (ARCHITECTURE)
                texts.append(f"{pub} {str(ts)[:10]} {title}\n\n{(body or '')[:1500]}")
            vecs = normalize(np.array(embed_batch(client, texts), dtype=np.float32))
            points = [
                PointStruct(
                    id=int(did, 16),
                    vector=vec.tolist(),
                    payload={"doc_id": did, "source_type": "news", "corp_code": corp,
                             "ts": str(ts), "title": title, "url": url},
                )
                for (did, corp, ts, title, url, _b, _m), vec in zip(batch, vecs)
            ]
            q.upsert(QCOL, points=points)
            total += len(points)
            if (i // BATCH) % 10 == 0:
                print(f"     임베딩 {total}/{len(rows)}")
    return total


# ── ③ document_unified → Neo4j (Document + ABOUT) ──────────────────
def step3_neo4j() -> int:
    conn = mariadb_conn()
    cur = conn.cursor()
    cur.execute("SELECT doc_id, corp_code, ts, title, url FROM document_unified WHERE source_type='news'")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    drv = neo4j_driver()
    with drv.session() as s:
        for i in range(0, len(rows), 500):
            batch = [{"doc_id": d, "corp": c, "ts": str(t), "title": ti, "url": u}
                     for d, c, t, ti, u in rows[i:i + 500]]
            s.run("""UNWIND $rows AS r
                MERGE (o:Organization {corp_code: r.corp})
                MERGE (d:Document {doc_id: r.doc_id})
                  SET d.source_type='news', d.ts=r.ts, d.title=r.title, d.url=r.url,
                      d.corp_code=r.corp, d:NewsArticle
                MERGE (d)-[:ABOUT]->(o)""", rows=batch)
    return len(rows)


# ── ④ mention_daily 집계 ───────────────────────────────────────────
def step4_mention_daily() -> int:
    conn = mariadb_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM mention_daily WHERE source_type='news'")
    cur.execute("""INSERT INTO mention_daily (corp_code, date, source_type, mention_cnt, evidence_doc_ids)
        SELECT corp_code, DATE(ts), 'news', COUNT(*), JSON_ARRAYAGG(doc_id)
        FROM document_unified
        WHERE source_type='news' AND ts IS NOT NULL
        GROUP BY corp_code, DATE(ts)""")
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM mention_daily WHERE source_type='news'")
    n = cur.fetchone()[0]
    cur.close()
    conn.close()
    return n


def main() -> None:
    print("=== 뉴스 v2 파이프라인 (news_raw → 3DB) ===")
    ensure_schema()
    ensure_qdrant()
    print(f"  ① document_unified : {step1_unified()} 건")
    print(f"  ② Qdrant 임베딩     : {step2_qdrant()} 건")
    print(f"  ③ Neo4j Document    : {step3_neo4j()} 건 (Document-ABOUT-Org)")
    print(f"  ④ mention_daily     : {step4_mention_daily()} 행 (회사·일별 집계)")
    print("\n완료. 정합 키 doc_id 로 3DB 연결됨. MENTIONS(세부 관계)는 별도 추출(LLM/Claude).")


if __name__ == "__main__":
    main()
