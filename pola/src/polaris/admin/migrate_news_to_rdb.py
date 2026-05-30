"""data/rawData/_common/news/*.json → news_raw 테이블 마이그레이션.

idempotent: news_id 가 PK 라 재실행 시 ON DUPLICATE KEY UPDATE 로 덮어쓰기.
"""
from __future__ import annotations
import json, time
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from polaris.config import DATA_ROOT, mariadb_conn

NEWS_DIR = DATA_ROOT / "rawData" / "_common" / "news"

# RSS feed_id → publisher / category 매핑 (POLARIS_NEWS_FEEDS 와 일치)
FEED_META = {
    "hankyung_finance": ("한국경제", "증권"),
    "mk_business":      ("매일경제", "기업/경영"),
    "mk_securities":    ("매일경제", "증권"),
}

# source_feed URL → feed_id 역매핑
URL_TO_FEED = {
    "https://www.hankyung.com/feed/finance": "hankyung_finance",
    "https://www.mk.co.kr/rss/50100032/":   "mk_business",
    "https://www.mk.co.kr/rss/50200011/":   "mk_securities",
}


def _parse_published(s: str):
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
        return dt.replace(tzinfo=None) if dt else None
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=None)
        except Exception:
            continue
    return None


def main():
    if not NEWS_DIR.is_dir():
        print(f"[migrate-news] {NEWS_DIR} 없음 - skip")
        return 0
    files = sorted(NEWS_DIR.glob("*.json"))
    print(f"[migrate-news] raw 파일: {len(files)}")
    if not files:
        return 0

    # 매칭 결과 (news_matched.jsonl) 로드해서 meta 컬럼에 합치기
    matched: dict[str, dict] = {}
    matched_file = DATA_ROOT / "2_Chuck" / "02_meta" / "news_matched.jsonl"
    if matched_file.is_file():
        for ln in matched_file.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
                if r.get("news_id"):
                    matched[r["news_id"]] = r
            except Exception:
                continue
        print(f"[migrate-news] 매칭 결과: {len(matched)}")

    conn = mariadb_conn(); cur = conn.cursor()
    sql = """INSERT INTO news_raw
        (news_id, feed_id, publisher, category, title, url, published, body, meta)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
          title=VALUES(title), url=VALUES(url), published=VALUES(published),
          body=VALUES(body), meta=VALUES(meta)"""
    t0 = time.time()
    n = 0
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        nid = d.get("news_id") or f.stem
        src_feed = d.get("source_feed", "")
        feed_id = URL_TO_FEED.get(src_feed, "")
        publisher, category = FEED_META.get(feed_id, (d.get("source_publisher", ""), ""))
        meta_obj = {}
        if nid in matched:
            m = matched[nid]
            meta_obj = {
                "matched_corps": m.get("matched_corps", []),
                "rule_hits":     m.get("rule_hits", {}),
                "llm_hits":      m.get("llm_hits", {}),
                "method":        m.get("method", ""),
            }
        cur.execute(sql, (
            nid, feed_id, publisher, category,
            d.get("title", "")[:500], d.get("url", "")[:1024],
            _parse_published(d.get("published", "")),
            d.get("text", ""),
            json.dumps(meta_obj, ensure_ascii=False) if meta_obj else None,
        ))
        n += 1
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM news_raw")
    total = cur.fetchone()[0]
    cur.execute("SELECT publisher, COUNT(*) FROM news_raw GROUP BY publisher")
    by_pub = cur.fetchall()
    cur.close(); conn.close()
    print(f"[migrate-news] INSERT: {n} / 전체 news_raw: {total}")
    print(f"[migrate-news] 출처별: {dict(by_pub)}")
    print(f"[migrate-news] 완료 {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
