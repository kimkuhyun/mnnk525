"""뉴스 적재 — news_matched (MariaDB) → Neo4j NewsArticle + MENTIONS.

+ 사용자 지정 2 URL (investchosun, newsis) 추가 적재 + 본문 entity 추출.

흐름:
  1. 2 URL 뉴스 → news_matched 에 INSERT (수동, body 는 외부 fetch)
  2. news_matched 전체 → Neo4j NewsArticle MERGE
  3. matched_corps → (NewsArticle)-[:MENTIONS]->(Organization) 엣지
  4. Qdrant title embedding (검색용)
  5. (선택) Claude 가 본문 풍부한 뉴스의 entity/event 추출
"""
from __future__ import annotations
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from polaris.config import (
    mariadb_conn, neo4j_driver, qdrant_client,
    OLLAMA_BASE, OLLAMA_EMBED_MODEL,
)

RUN_ID = "20260528_0808_01"
COLLECTION = "polaris-1024-cos-green"


def _hash16(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:16]


def insert_two_urls():
    """사용자 지정 2 URL → news_matched INSERT (본문은 별도 entity 추출에 사용)."""
    items = [
        {
            "news_id": _hash16("investchosun-2026052780200"),
            "url": "https://www.investchosun.com/site/data/html_dir/2026/05/27/2026052780200.html",
            "title": "노태문 대표 사과문에 더 들끓는 삼성전자 DX",
            "published": "2026-05-27 10:00:00",
            "publisher": "인베스트조선",
            "matched_corps": ["00126380"],  # 삼성전자
            "summary": "노태문 DX부문장 사과문 → DX 임직원 반발. DS-DX 보상 격차, 동행노조 1.4만명, 메모리 가격 상승으로 재료비 부담",
        },
        {
            "news_id": _hash16("newsis-NISX20260528_0003647480"),
            "url": "https://www.newsis.com/view/NISX20260528_0003647480",
            "title": "[속보]삼성전자, 차익 매물에 4% 하락…SK하닉도 1% 약세",
            "published": "2026-05-28 09:30:00",
            "publisher": "뉴시스",
            "matched_corps": ["00126380", "00164779"],  # 삼성전자, SK하이닉스
            "summary": "삼성전자 차익 매물로 4% 하락, SK하이닉스도 1% 약세",
        },
    ]
    conn = mariadb_conn(); cur = conn.cursor()
    n = 0
    for it in items:
        try:
            cur.execute("""
                INSERT INTO news_matched
                  (news_id, run_id, url, title, published, publisher,
                   matched_corps, rule_hits, llm_hits, method, pipeline_version)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'manual', 'claude-direct/0.1')
                ON DUPLICATE KEY UPDATE
                  title=VALUES(title), publisher=VALUES(publisher),
                  matched_corps=VALUES(matched_corps)
            """, (it["news_id"], RUN_ID, it["url"], it["title"],
                  it["published"], it["publisher"],
                  json.dumps(it["matched_corps"]), "[]", "[]"))
            n += 1
            print(f"  inserted: {it['title'][:60]}")
        except Exception as ex:
            print(f"  [err] {it['title'][:40]}: {ex}")
    conn.commit(); cur.close(); conn.close()
    return n, items


def load_to_neo4j():
    """news_matched 전체 → Neo4j NewsArticle MERGE + MENTIONS."""
    conn = mariadb_conn(); cur = conn.cursor()
    cur.execute("""SELECT news_id, url, title, published, publisher, matched_corps
                   FROM news_matched""")
    rows = cur.fetchall()
    cur.close(); conn.close()
    print(f"  news_matched rows: {len(rows)}")

    drv = neo4j_driver()
    with drv.session() as s:
        # 인덱스 보장
        s.run("CREATE INDEX news_id IF NOT EXISTS FOR (n:NewsArticle) ON (n.news_id)")

        # batch insert
        BATCH = 100
        batch = []
        for r in rows:
            news_id, url, title, published, publisher, matched_corps = r
            try:
                corps = json.loads(matched_corps) if matched_corps else []
            except Exception:
                corps = []
            date_str = published.strftime("%Y-%m-%d") if published else None
            batch.append({
                "news_id": news_id, "url": url, "title": title,
                "date": date_str, "publisher": publisher,
                "matched_corps": corps,
            })

        n_node = 0; n_edge = 0
        for i in range(0, len(batch), BATCH):
            chunk = batch[i:i+BATCH]
            # NewsArticle MERGE
            s.run("""
                UNWIND $rows AS r
                MERGE (n:NewsArticle {news_id: r.news_id})
                  ON CREATE SET n.first_seen_run_id = $rid
                SET n.url = r.url, n.title = r.title, n.date = r.date,
                    n.publisher = r.publisher, n.run_id = $rid,
                    n.matched_count = size(r.matched_corps),
                    n.last_updated_run_id = $rid
            """, rows=chunk, rid=RUN_ID)
            n_node += len(chunk)

            # MENTIONS 엣지
            edge_rows = []
            for it in chunk:
                for code in it["matched_corps"]:
                    edge_rows.append({"news_id": it["news_id"], "corp_code": code})
            if edge_rows:
                s.run("""
                    UNWIND $rows AS r
                    MATCH (n:NewsArticle {news_id: r.news_id})
                    MATCH (o:Organization {corp_code: r.corp_code})
                    MERGE (n)-[m:MENTIONS]->(o)
                      ON CREATE SET m.first_seen_run_id = $rid
                """, rows=edge_rows, rid=RUN_ID)
                n_edge += len(edge_rows)
    drv.close()
    return n_node, n_edge


def upsert_qdrant_titles():
    """뉴스 title embedding → Qdrant (RAG 검색용)."""
    conn = mariadb_conn(); cur = conn.cursor()
    cur.execute("SELECT news_id, title, publisher, published FROM news_matched")
    rows = cur.fetchall()
    cur.close(); conn.close()

    qc = qdrant_client()
    from qdrant_client.models import PointStruct
    # title embedding (date + publisher + title prefix)
    print(f"  뉴스 title 임베딩: {len(rows)}")
    BATCH = 32
    points = []
    with httpx.Client(timeout=120) as http:
        for i in range(0, len(rows), BATCH):
            sub = rows[i:i+BATCH]
            texts = []
            for r in sub:
                date_str = r[3].strftime("%Y-%m-%d") if r[3] else ""
                texts.append(f"{r[2]} {date_str} {r[1] or ''}")
            r2 = http.post(f"{OLLAMA_BASE}/api/embed",
                           json={"model": OLLAMA_EMBED_MODEL, "input": texts})
            r2.raise_for_status()
            embs = r2.json()["embeddings"]
            for j, r in enumerate(sub):
                pid_h = hashlib.md5(("news:" + r[0]).encode()).hexdigest()
                pid = f"{pid_h[0:8]}-{pid_h[8:12]}-{pid_h[12:16]}-{pid_h[16:20]}-{pid_h[20:32]}"
                points.append(PointStruct(
                    id=pid, vector=embs[j],
                    payload={
                        "chunk_id": _hash16("news:" + r[0]),
                        "chunk_type": "news_text",
                        "news_id": r[0], "corp_code": "00000000",
                        "title": r[1], "publisher": r[2],
                        "date": r[3].strftime("%Y-%m-%d") if r[3] else None,
                        "run_id": RUN_ID, "ingest_status": "ready",
                    }
                ))
    BATCH_UP = 128
    for i in range(0, len(points), BATCH_UP):
        qc.upsert(collection_name=COLLECTION, points=points[i:i+BATCH_UP])
    return len(points)


def main():
    print("=" * 60)
    print("뉴스 적재 — 2 URL + news_matched → Neo4j + Qdrant")
    print("=" * 60)

    print("\n[1] 2 URL 추가 INSERT")
    n_ins, items = insert_two_urls()
    print(f"  → {n_ins} 신규 / 업데이트")

    print("\n[2] Neo4j NewsArticle + MENTIONS 적재")
    n_node, n_edge = load_to_neo4j()
    print(f"  → NewsArticle {n_node} merged, MENTIONS {n_edge} edges")

    print("\n[3] Qdrant title 임베딩 upsert")
    n_qd = upsert_qdrant_titles()
    print(f"  → {n_qd} points")

    # 검증
    drv = neo4j_driver()
    print("\n=== 검증 ===")
    with drv.session() as s:
        for label, q in [
            ("NewsArticle 총수", "MATCH (n:NewsArticle) RETURN count(n) AS n"),
            ("MENTIONS 엣지", "MATCH (:NewsArticle)-[m:MENTIONS]->() RETURN count(m) AS n"),
            ("Samsung 매칭 뉴스", "MATCH (n:NewsArticle)-[:MENTIONS]->(o:Organization {corp_code:'00126380'}) RETURN count(n) AS n"),
            ("한미 매칭 뉴스", "MATCH (n:NewsArticle)-[:MENTIONS]->(o:Organization {corp_code:'00161383'}) RETURN count(n) AS n"),
            ("SK 매칭 뉴스", "MATCH (n:NewsArticle)-[:MENTIONS]->(o:Organization {corp_code:'00164779'}) RETURN count(n) AS n"),
            ("publishers", "MATCH (n:NewsArticle) RETURN DISTINCT n.publisher AS p, count(n) AS c ORDER BY c DESC"),
        ]:
            for r in s.run(q):
                d = dict(r)
                print(f"  {label:30s} {d}")
                if label not in ("publishers",): break
    drv.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
