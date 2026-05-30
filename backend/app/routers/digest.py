"""GET /api/daily-digest/{corp} — 일별 뉴스 요약 + 대표 헤드라인."""
from __future__ import annotations

import json

from fastapi import APIRouter

from ..db import mariadb
from ..models import DailyDigestItem, NewsItem

router = APIRouter(tags=["digest"])


def _pub(metadata) -> str | None:
    """document_unified.metadata(JSON) 에서 publisher 추출 (news.py 와 동일 방식)."""
    try:
        m = metadata
        if isinstance(m, str):
            m = json.loads(m)
        return (m or {}).get("publisher")
    except Exception:
        return None

_ENSURE_DIGEST = """
CREATE TABLE IF NOT EXISTS news_daily_summary (
    corp_code VARCHAR(8) NOT NULL,
    date DATE NOT NULL,
    summary TEXT,
    article_count INT,
    PRIMARY KEY (corp_code, date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def _ensure_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(_ENSURE_DIGEST)
    conn.commit()


@router.get("/daily-digest/{corp}", response_model=list[DailyDigestItem])
def get_daily_digest(corp: str) -> list[DailyDigestItem]:
    conn = mariadb()
    try:
        _ensure_tables(conn)

        # 1) news_daily_summary 에서 요약 목록 (최신순)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DATE_FORMAT(date, '%%Y-%%m-%%d') AS date, summary, article_count "
                "FROM news_daily_summary "
                "WHERE corp_code=%s "
                "ORDER BY date DESC",
                (corp,),
            )
            summaries = cur.fetchall()

        if not summaries:
            return []

        # 2) 각 날짜의 대표 헤드라인 0~2개 — document_unified 에서 한 번에 가져오기
        dates = [r["date"] for r in summaries]
        placeholders = ",".join(["%s"] * len(dates))

        with conn.cursor() as cur:
            cur.execute(
                f"SELECT doc_id, title, DATE_FORMAT(ts, '%%Y-%%m-%%d') AS date, url, metadata "
                f"FROM document_unified "
                f"WHERE corp_code=%s AND source_type='news' "
                f"  AND DATE_FORMAT(ts, '%%Y-%%m-%%d') IN ({placeholders}) "
                f"ORDER BY ts DESC",
                (corp, *dates),
            )
            news_rows = cur.fetchall()

        # 날짜별로 그룹화 (최대 2개씩)
        from collections import defaultdict
        news_by_date: dict[str, list[NewsItem]] = defaultdict(list)
        for row in news_rows:
            d = row["date"]
            if len(news_by_date[d]) < 2:
                news_by_date[d].append(
                    NewsItem(
                        docId=row["doc_id"],
                        title=row["title"] or "",
                        date=d,
                        url=row["url"] or "",
                        publisher=_pub(row.get("metadata")),
                    )
                )

        return [
            DailyDigestItem(
                date=r["date"],
                summary=r["summary"] or "",
                articleCount=r["article_count"] or 0,
                headlines=news_by_date.get(r["date"], []),
            )
            for r in summaries
        ]
    except Exception:
        return []
    finally:
        conn.close()
