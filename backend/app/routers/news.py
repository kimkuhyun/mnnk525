# main.py 에 app.include_router(news.router, prefix='/api') 추가 필요

import json
from fastapi import APIRouter
from ..db import mariadb
from ..models import NewsItem

router = APIRouter(tags=["news"])


@router.get("/news/{corp}", response_model=list[NewsItem])
def get_news(corp: str):
    sql = (
        "SELECT doc_id, title, DATE_FORMAT(ts, '%%Y-%%m-%%d') AS d, url, metadata "
        "FROM document_unified "
        "WHERE corp_code=%s AND source_type='news' "
        "ORDER BY ts DESC LIMIT 50"
    )
    conn = mariadb()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (corp,))
            rows = cur.fetchall()
    finally:
        conn.close()

    items = []
    for row in rows:
        publisher = None
        try:
            meta = row["metadata"]
            if isinstance(meta, str):
                meta = json.loads(meta)
            publisher = meta.get("publisher")
        except Exception:
            pass
        items.append(
            NewsItem(
                docId=row["doc_id"],
                title=row["title"],
                date=row["d"],
                url=row["url"],
                publisher=publisher,
            )
        )
    return items
