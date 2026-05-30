"""GET /api/ir-reports/{corp} — IR 보고서 목록."""
from __future__ import annotations

import logging

from fastapi import APIRouter

from ..db import mariadb
from ..models import IrReport

router = APIRouter(tags=["ir"])
logger = logging.getLogger(__name__)

# init_mariadb.sql §15 와 동일 스키마 유지 (DDL 드리프트 방지 — docs/DBdocs/디비설계.md 가 SSOT).
_ENSURE_IR_REPORT = """
CREATE TABLE IF NOT EXISTS ir_report (
    rcept_no    VARCHAR(20)  NOT NULL,
    corp_code   VARCHAR(8)   NOT NULL,
    doc_type    VARCHAR(255) DEFAULT NULL,
    date        DATE         DEFAULT NULL,
    title       TEXT         DEFAULT NULL,
    raw_text    MEDIUMTEXT   DEFAULT NULL,
    summary     TEXT         DEFAULT NULL,
    source      VARCHAR(32)  DEFAULT NULL,
    ingested_at DATETIME     DEFAULT NULL,
    PRIMARY KEY (rcept_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def _ensure_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(_ENSURE_IR_REPORT)
    conn.commit()


@router.get("/ir-reports/{corp}", response_model=list[IrReport])
def get_ir_reports(corp: str) -> list[IrReport]:
    """MariaDB ir_report 에서 corp_code 기준 최신 10건 반환."""
    conn = mariadb()
    try:
        _ensure_tables(conn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT rcept_no, corp_code, doc_type, "
                "DATE_FORMAT(date, '%%Y-%%m-%%d') AS date, "
                "title, summary, source "
                "FROM ir_report "
                "WHERE corp_code=%s "
                "ORDER BY date DESC LIMIT 10",
                (corp,),
            )
            rows = cur.fetchall()
        return [
            IrReport(
                rceptNo=r["rcept_no"],
                corpCode=r["corp_code"],
                docType=r["doc_type"],
                date=r["date"],
                title=r["title"],
                summary=r["summary"],
                source=r["source"],
            )
            for r in rows
        ]
    except Exception as exc:
        logger.warning("ir_report 조회 실패 (corp=%s): %s", corp, exc)
        return []
    finally:
        conn.close()
