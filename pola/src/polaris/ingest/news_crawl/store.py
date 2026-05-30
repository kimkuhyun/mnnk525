"""news_raw 적재 — 기존 스키마/패턴 재사용 (idempotent upsert = 증분 핵심).

news_id = sha1(url)[:16]  (bulk_collect.news_id_from_url 과 동일 규약)
저장처: MariaDB news_raw (SSOT). config.mariadb_conn 재사용.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from email.utils import parsedate_to_datetime

from polaris.config import mariadb_conn


def news_id_from_url(url: str) -> str:
    """뉴스 자연키 = sha1(url)[:16]. 기존 규약과 동일(중복 방지·증분)."""
    return hashlib.sha1((url or "").strip().encode("utf-8")).hexdigest()[:16]


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:  # ISO 8601 (article:published_time / JSON-LD datePublished)
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        pass
    try:  # RFC 2822
        return parsedate_to_datetime(s).replace(tzinfo=None)
    except Exception:
        return None


def already_have(url: str) -> bool:
    """증분: 이미 저장된 URL 이면 True (목록 수집 조기 종료 판단용)."""
    conn = mariadb_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM news_raw WHERE news_id=%s", (news_id_from_url(url),))
    hit = cur.fetchone() is not None
    cur.close()
    conn.close()
    return hit


def upsert(article: dict, publisher: str, category: str) -> str:
    """news_raw 에 INSERT ... ON DUPLICATE KEY UPDATE. news_id 반환."""
    nid = news_id_from_url(article["url"])
    pub_dt = _parse_dt(article.get("published") or article.get("ld_published"))
    meta = {
        k: article.get(k)
        for k in ("og_title", "og_desc", "ld_headline", "publisher_meta")
    }
    conn = mariadb_conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO news_raw
             (news_id, feed_id, publisher, category, title, url, published, body, meta)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON DUPLICATE KEY UPDATE
             title=VALUES(title), body=VALUES(body),
             published=VALUES(published), meta=VALUES(meta)""",
        (
            nid, "crawl", publisher, category,
            (article.get("title") or "")[:500],
            article["url"][:1024], pub_dt, article["body"],
            json.dumps(meta, ensure_ascii=False),
        ),
    )
    conn.commit()
    cur.close()
    conn.close()
    return nid
