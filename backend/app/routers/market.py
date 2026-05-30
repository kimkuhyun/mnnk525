"""GET /api/stock/{corp} — 시장 데이터."""
from __future__ import annotations

from fastapi import APIRouter

from ..db import mariadb
from ..models import StockPoint
from ..relations import SEED_CORPS

router = APIRouter(tags=["market"])

SEED_SET = set(SEED_CORPS.keys())

_ENSURE_STOCK = """
CREATE TABLE IF NOT EXISTS stock_daily (
    corp_code VARCHAR(8) NOT NULL,
    date DATE NOT NULL,
    close DOUBLE,
    change_pct DOUBLE,
    volume BIGINT,
    PRIMARY KEY (corp_code, date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def _ensure_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(_ENSURE_STOCK)
    conn.commit()


@router.get("/stock/{corp}", response_model=list[StockPoint])
def get_stock(corp: str) -> list[StockPoint]:
    conn = mariadb()
    try:
        _ensure_tables(conn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DATE_FORMAT(date, '%%Y-%%m-%%d') AS date, close, change_pct, volume "
                "FROM stock_daily "
                "WHERE corp_code=%s AND date >= '2026-01-01' "
                "ORDER BY date ASC",
                (corp,),
            )
            rows = cur.fetchall()
        return [
            StockPoint(
                date=r["date"],
                close=r["close"],
                changePct=r["change_pct"],
                volume=r["volume"],
            )
            for r in rows
        ]
    except Exception:
        return []
    finally:
        conn.close()


