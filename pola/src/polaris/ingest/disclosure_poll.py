"""pola/src/polaris/ingest/disclosure_poll.py — 수시공시 poller.

시드 3사(삼성전자·SK하이닉스·한미반도체) DART list.json 신규 공시 →
Neo4j FilingDocument MERGE (멱등).

CLI:
    uv run python -m polaris.ingest.disclosure_poll
"""
from __future__ import annotations

import os
import sys
import time
from datetime import date, datetime

import httpx

from polaris.config import DART_API_KEY, neo4j_driver, _env

# ── 시드 3사 (organizations.yml ticker[0] 기준) ──────────────────
SEED_CORPS: list[str] = ["00126380", "00164779", "00161383"]

DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
FALLBACK_START = "2024-01-01"
PAGE_COUNT = 100

# DART status
_STATUS_OK = "000"
_STATUS_NO_DATA = "013"


def _dart_key() -> str:
    key = DART_API_KEY or _env("DART_API_KEY", "")
    if not key:
        raise RuntimeError("DART_API_KEY 가 비어있습니다. pola/.env 확인")
    return key


# ── Neo4j 워터마크 조회 ───────────────────────────────────────────

def _get_watermarks(driver) -> dict[str, str]:
    """corp_code → MAX(FilingDocument.date) or FALLBACK_START."""
    wm: dict[str, str] = {}
    with driver.session() as session:
        for corp in SEED_CORPS:
            result = session.run(
                "MATCH (f:FilingDocument {corp_code: $cc}) "
                "RETURN max(f.date) AS mx",
                cc=corp,
            )
            record = result.single()
            mx = record["mx"] if record else None
            wm[corp] = mx if mx else FALLBACK_START
    return wm


# ── DART list.json 페이지네이션 ──────────────────────────────────

def _fetch_dart_list(
    client: httpx.Client,
    key: str,
    corp: str,
    bgn_de: str,
    end_de: str,
) -> list[dict]:
    """corp_code 기준 bgn_de~end_de 공시 목록 전체 반환."""
    items: list[dict] = []
    page = 1
    while True:
        params = {
            "crtfc_key": key,
            "corp_code": corp,
            "bgn_de": bgn_de,
            "end_de": end_de,
            "page_count": str(PAGE_COUNT),
            "page_no": str(page),
        }
        try:
            resp = client.get(DART_LIST_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            print(f"  [WARN] DART 요청 실패 corp={corp} page={page}: {exc}", file=sys.stderr)
            break

        status = str(data.get("status", ""))
        if status == _STATUS_NO_DATA:
            # 무자료 — 정상 종료
            break
        if status != _STATUS_OK:
            print(
                f"  [WARN] DART status={status!r} msg={data.get('message')!r} "
                f"corp={corp} page={page}",
                file=sys.stderr,
            )
            break

        page_items = data.get("list") or []
        items.extend(page_items)

        total_page = int(data.get("total_page") or 1)
        if page >= total_page or not page_items:
            break
        page += 1
        time.sleep(0.2)

    return items


# ── Neo4j MERGE ──────────────────────────────────────────────────

_MERGE_CQL = """
MERGE (f:FilingDocument {rcept_no: $rcept_no})
ON CREATE SET
  f.date        = $date,
  f.corp_code   = $corp_code,
  f.title       = $title,
  f.doc_type    = $doc_type,
  f.first_seen_run_id = 'track',
  f.source      = 'dart_list'
"""


def _upsert_filings(driver, records: list[dict]) -> int:
    """FilingDocument MERGE — 신규 건만 ON CREATE SET. 반환: 실제 생성 수."""
    if not records:
        return 0
    created = 0
    with driver.session() as session:
        for r in records:
            summary = session.run(_MERGE_CQL, **r).consume()
            created += summary.counters.nodes_created
    return created


# ── rcept_dt 변환 ─────────────────────────────────────────────────

def _to_iso(rcept_dt: str) -> str:
    """'YYYYMMDD' → 'YYYY-MM-DD'. 길이 이상 시 빈 문자열."""
    if len(rcept_dt) == 8 and rcept_dt.isdigit():
        return f"{rcept_dt[:4]}-{rcept_dt[4:6]}-{rcept_dt[6:8]}"
    return ""


# ── 기존 rcept_no 조회 (중복 필터) ───────────────────────────────

def _existing_rcept_nos(driver, corp: str) -> set[str]:
    with driver.session() as session:
        result = session.run(
            "MATCH (f:FilingDocument {corp_code: $cc}) RETURN f.rcept_no AS rno",
            cc=corp,
        )
        return {record["rno"] for record in result}


# ── 메인 ─────────────────────────────────────────────────────────

def track_disclosures() -> None:
    """시드 3사 수시공시 수집 → Neo4j FilingDocument MERGE."""
    key = _dart_key()
    today_str = date.today().strftime("%Y%m%d")

    driver = neo4j_driver()
    try:
        watermarks = _get_watermarks(driver)
        print(f"워터마크: {watermarks}")

        total_new = 0
        with httpx.Client(follow_redirects=True) as client:
            for corp in SEED_CORPS:
                wm = watermarks[corp]
                # 워터마크가 이미 오늘이면 스킵
                bgn_de = wm.replace("-", "")
                end_de = today_str

                if bgn_de > end_de:
                    print(f"  {corp}: 워터마크({wm}) >= 오늘 — 스킵")
                    continue

                print(f"  {corp}: {bgn_de} ~ {end_de} 조회 중...")
                items = _fetch_dart_list(client, key, corp, bgn_de, end_de)
                print(f"    DART 응답: {len(items)}건")

                if not items:
                    continue

                # 기존 rcept_no 로드 (중복 방지)
                existing = _existing_rcept_nos(driver, corp)

                records: list[dict] = []
                for it in items:
                    rno = (it.get("rcept_no") or "").strip()
                    if not rno or rno in existing:
                        continue
                    rcept_dt = (it.get("rcept_dt") or "").strip()
                    report_nm = (it.get("report_nm") or "").strip()
                    records.append({
                        "rcept_no": rno,
                        "date": _to_iso(rcept_dt),
                        "corp_code": corp,
                        "title": report_nm,
                        "doc_type": report_nm,
                    })

                n = _upsert_filings(driver, records)
                print(f"    신규 FilingDocument 생성: {n}건 (후보 {len(records)}건)")
                total_new += n
                time.sleep(0.3)

        print(f"\n완료: 총 신규 FilingDocument {total_new}건")
    finally:
        driver.close()


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    track_disclosures()
