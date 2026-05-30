"""GET /api/briefing/{corp} — 최신 일별요약 + 헤드라인 + 수시공시."""
from __future__ import annotations

import json

from fastapi import APIRouter

from ..db import mariadb, neo4j
from ..models import BriefingData, DisclosureItem, NewsItem

router = APIRouter(tags=["briefing"])

_ENSURE_DIGEST = """
CREATE TABLE IF NOT EXISTS news_daily_summary (
    corp_code VARCHAR(8) NOT NULL,
    date DATE NOT NULL,
    summary TEXT,
    article_count INT,
    PRIMARY KEY (corp_code, date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

FILING_QUERY = """
MATCH (f:FilingDocument {corp_code: $corp})
RETURN f.date AS date,
       f.doc_type AS doc_type,
       f.title AS title,
       f.summary_short AS summary_short,
       f.rcept_no AS rcept_no
ORDER BY f.date DESC
LIMIT 10
"""


def _pub(metadata) -> str | None:
    """document_unified.metadata(JSON) 에서 publisher 추출."""
    try:
        m = metadata
        if isinstance(m, str):
            m = json.loads(m)
        return (m or {}).get("publisher")
    except Exception:
        return None


@router.get("/briefing/{corp}", response_model=BriefingData)
def get_briefing(corp: str) -> BriefingData:
    """최신 일별요약(1행) + 그 날짜 뉴스 헤드라인 2건 + 수시공시 10건."""

    # ── MariaDB: 최신 news_daily_summary 1행 ──
    summary_date: str | None = None
    summary_text: str | None = None
    article_count: int = 0
    headlines: list[NewsItem] = []

    conn = mariadb()
    try:
        with conn.cursor() as cur:
            cur.execute(_ENSURE_DIGEST)
        conn.commit()

        with conn.cursor() as cur:
            cur.execute(
                "SELECT DATE_FORMAT(date, '%%Y-%%m-%%d') AS date, summary, article_count "
                "FROM news_daily_summary "
                "WHERE corp_code = %s "
                "ORDER BY date DESC LIMIT 1",
                (corp,),
            )
            row = cur.fetchone()

        if row:
            summary_date = row["date"]
            summary_text = row["summary"]
            article_count = int(row["article_count"] or 0)

            # 그 날짜의 뉴스 헤드라인 2건
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT doc_id, title, DATE_FORMAT(ts, '%%Y-%%m-%%d') AS d, url, metadata "
                    "FROM document_unified "
                    "WHERE corp_code = %s AND source_type = 'news' "
                    "  AND DATE_FORMAT(ts, '%%Y-%%m-%%d') = %s "
                    "ORDER BY ts DESC LIMIT 2",
                    (corp, summary_date),
                )
                for r in cur.fetchall():
                    headlines.append(
                        NewsItem(
                            docId=r["doc_id"],
                            title=r["title"] or "",
                            date=r["d"] or "",
                            url=r["url"] or "",
                            publisher=_pub(r.get("metadata")),
                        )
                    )
    except Exception:
        pass
    finally:
        conn.close()

    # ── Neo4j: FilingDocument 수시공시 10건 ──
    disclosures: list[DisclosureItem] = []
    try:
        with neo4j().session() as s:
            filing_rows = s.run(FILING_QUERY, corp=corp).data()
        for f in filing_rows:
            disclosures.append(
                DisclosureItem(
                    date=str(f["date"]) if f["date"] else "",
                    docType=str(f["doc_type"]) if f["doc_type"] else "",
                    title=str(f["title"]) if f["title"] else "",
                    summary=str(f["summary_short"]) if f["summary_short"] else None,
                    rcept=str(f["rcept_no"]) if f["rcept_no"] else None,
                )
            )
    except Exception:
        pass

    return BriefingData(
        date=summary_date,
        summary=summary_text,
        articleCount=article_count,
        headlines=headlines,
        disclosures=disclosures,
    )
