"""pola/src/polaris/ingest/ir_report_ingest.py — IR/정기보고서 원문 적재 + Ollama 요약 → MariaDB ir_report.

대상: 시드 3사(삼성전자·SK하이닉스·한미반도체) 최근 사업보고서/반기보고서/분기보고서 3건씩.
원문 우선순위:
  1) pola/data/ir_raw/{rcept_no}.txt 수동 파일
  2) DART document.xml API → ZIP 해제 → XML 태그 제거
요약: Ollama(OLLAMA_LLM_MODEL, think=False, num_ctx=16384) 한국어 5~8줄 핵심 요약.
멱등: summary 있으면 skip (--force 시 재요약).

CLI:
    uv run python -m polaris.ingest.ir_report_ingest
    uv run python -m polaris.ingest.ir_report_ingest --force
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys
import zipfile
from datetime import datetime

import httpx

from polaris.config import (
    DART_API_KEY,
    OLLAMA_BASE,
    OLLAMA_LLM_MODEL,
    _env,
    mariadb_conn,
    neo4j_driver,
)

# ── 상수 ─────────────────────────────────────────────────────────────

SEED_CORPS: list[str] = ["00126380", "00164779", "00161383"]
CORP_NAMES: dict[str, str] = {
    "00126380": "삼성전자",
    "00164779": "SK하이닉스",
    "00161383": "한미반도체",
}

DART_DOC_URL = "https://opendart.fss.or.kr/api/document.xml"
IR_RAW_DIR_ENV = "POLARIS_IR_RAW_DIR"   # override 가능

# DART 문서 최대 시도 크기 (바이트). 응답이 너무 크면 텍스트 앞부분만 사용.
MAX_RAW_CHARS = 8000
TOP_N_PER_CORP = 3


# ── 테이블 보장 ────────────────────────────────────────────────────

def ensure_tables(cur) -> None:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ir_report (
            rcept_no    VARCHAR(20)  NOT NULL,
            corp_code   VARCHAR(8)   NOT NULL,
            doc_type    VARCHAR(255),
            date        DATE,
            title       TEXT,
            raw_text    MEDIUMTEXT,
            summary     TEXT,
            source      VARCHAR(32),
            ingested_at DATETIME,
            PRIMARY KEY (rcept_no)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


# ── Neo4j 대상 조회 ────────────────────────────────────────────────

def _query_filing_docs(driver) -> list[dict]:
    """시드 3사별 '사업보고서|반기보고서|분기보고서' date desc 상위 3건씩."""
    results: list[dict] = []
    with driver.session() as session:
        for corp in SEED_CORPS:
            records = session.run(
                """
                MATCH (f:FilingDocument {corp_code: $cc})
                WHERE f.doc_type =~ '.*(사업보고서|반기보고서|분기보고서).*'
                RETURN f.rcept_no AS rcept_no,
                       f.corp_code AS corp_code,
                       f.doc_type  AS doc_type,
                       f.date      AS date,
                       f.title     AS title
                ORDER BY f.date DESC
                LIMIT $n
                """,
                cc=corp,
                n=TOP_N_PER_CORP,
            ).data()
            for r in records:
                results.append({
                    "rcept_no": r.get("rcept_no") or "",
                    "corp_code": r.get("corp_code") or corp,
                    "doc_type": r.get("doc_type") or "",
                    "date": r.get("date") or "",
                    "title": r.get("title") or "",
                })
    return results


# ── 원문 확보 ──────────────────────────────────────────────────────

def _ir_raw_dir() -> str:
    """수동 raw 파일 디렉토리. 환경변수 override 또는 pola/data/ir_raw."""
    env_dir = _env(IR_RAW_DIR_ENV, "")
    if env_dir:
        return env_dir
    # __file__ 기준: pola/src/polaris/ingest/ir_report_ingest.py → pola/
    pola_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
    )
    return os.path.join(pola_root, "data", "ir_raw")


def _read_manual_file(rcept_no: str) -> str | None:
    """pola/data/ir_raw/{rcept_no}.txt 존재 시 텍스트 반환."""
    path = os.path.join(_ir_raw_dir(), f"{rcept_no}.txt")
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception as exc:
            print(f"  [WARN] 수동 파일 읽기 실패 {path}: {exc}", file=sys.stderr)
    return None


def _strip_xml_tags(xml: str) -> str:
    text = re.sub(r"<[^>]+>", " ", xml)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _fetch_dart_doc(client: httpx.Client, rcept_no: str, key: str) -> str | None:
    """DART document.xml API → ZIP 해제 → XML 태그 제거 텍스트. 실패 시 None."""
    try:
        resp = client.get(
            DART_DOC_URL,
            params={"crtfc_key": key, "rcept_no": rcept_no},
            timeout=60,
        )
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        # 키 오류 등 JSON 응답이 오는 경우 처리
        if "json" in content_type or "text" in content_type:
            print(
                f"  [WARN] DART doc API 비정상 응답 rcept_no={rcept_no}: {resp.text[:200]}",
                file=sys.stderr,
            )
            return None
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        parts: list[str] = []
        for name in zf.namelist():
            if name.lower().endswith(".xml"):
                raw_bytes = zf.read(name)
                try:
                    xml_text = raw_bytes.decode("utf-8", errors="replace")
                except Exception:
                    xml_text = raw_bytes.decode("cp949", errors="replace")
                parts.append(_strip_xml_tags(xml_text))
        if not parts:
            return None
        return "\n\n".join(parts)
    except Exception as exc:
        print(f"  [WARN] DART 원문 다운로드 실패 rcept_no={rcept_no}: {exc}", file=sys.stderr)
        return None


def _get_raw_text(client: httpx.Client, rcept_no: str, dart_key: str) -> tuple[str | None, str]:
    """원문과 source('manual'|'dart') 반환. 확보 불가 시 (None, '')."""
    text = _read_manual_file(rcept_no)
    if text:
        return text, "manual"
    if dart_key:
        text = _fetch_dart_doc(client, rcept_no, dart_key)
        if text:
            return text, "dart"
    return None, ""


# ── Ollama 요약 ────────────────────────────────────────────────────

_SUMMARY_PROMPT = (
    "다음은 '{corp}' 의 IR/정기보고서 원문 앞부분이다.\n"
    "아래 지침에 따라 한국어 불릿 3~5개로 질적 하이라이트를 작성하라.\n"
    "\n"
    "[지침]\n"
    "- 각 줄은 반드시 '- ' 로 시작하라.\n"
    "- 다룰 주제: 사업 전략·방향, 신규 또는 확대 사업, 주요 리스크, 향후 전망(언급된 경우에만).\n"
    "- 매출·영업이익 등 재무 실적 수치 나열은 금지. 수치가 필요하면 맥락 설명에 최소한으로만 인용.\n"
    "- 보고서에 명시된 사실만 기술하고, 추측·해석·평가는 절대 금지.\n"
    "- 불릿 3~5개, 각 불릿 1~2문장. 그 외 서두·서명·제목 등 부가 텍스트 출력 금지.\n"
    "\n"
    "[보고서 원문]\n{text}"
)

MODEL = OLLAMA_LLM_MODEL or "qwen3.5:9b"


def _summarize(client: httpx.Client, corp_name: str, raw_text: str) -> str:
    prompt = _SUMMARY_PROMPT.format(
        corp=corp_name,
        text=raw_text[:MAX_RAW_CHARS],
    )
    r = client.post(
        f"{OLLAMA_BASE}/api/chat",
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "think": False,
            "stream": False,
            "options": {"temperature": 0, "num_ctx": 16384},
        },
        timeout=180,
    )
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


# ── MariaDB upsert ─────────────────────────────────────────────────

def _upsert_ir_report(cur, row: dict) -> None:
    cur.execute(
        """
        INSERT INTO ir_report
            (rcept_no, corp_code, doc_type, date, title, raw_text, summary, source, ingested_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            raw_text    = VALUES(raw_text),
            summary     = VALUES(summary),
            source      = VALUES(source),
            ingested_at = VALUES(ingested_at)
        """,
        (
            row["rcept_no"],
            row["corp_code"],
            row["doc_type"],
            row["date"] or None,
            row["title"],
            row["raw_text"],
            row["summary"],
            row["source"],
            row["ingested_at"],
        ),
    )


def _has_summary(cur, rcept_no: str) -> bool:
    cur.execute(
        "SELECT summary FROM ir_report WHERE rcept_no = %s",
        (rcept_no,),
    )
    row = cur.fetchone()
    return bool(row and row[0])


# ── 기존 stub 적재 (raw 없어도 메타 기록) ──────────────────────────

def _upsert_stub(cur, doc: dict) -> None:
    """raw_text/summary 없이 메타만 INSERT IGNORE."""
    cur.execute(
        """
        INSERT IGNORE INTO ir_report
            (rcept_no, corp_code, doc_type, date, title, raw_text, summary, source, ingested_at)
        VALUES (%s, %s, %s, %s, %s, NULL, NULL, 'stub', %s)
        """,
        (
            doc["rcept_no"],
            doc["corp_code"],
            doc["doc_type"],
            doc["date"] or None,
            doc["title"],
            datetime.now(),
        ),
    )


# ── 메인 ──────────────────────────────────────────────────────────

def ingest(force: bool = False) -> None:
    dart_key = DART_API_KEY or _env("DART_API_KEY", "")
    if not dart_key:
        print("[WARN] DART_API_KEY 없음 — 수동 파일만 사용합니다.", file=sys.stderr)

    # Neo4j 대상 조회
    driver = neo4j_driver()
    try:
        docs = _query_filing_docs(driver)
    finally:
        driver.close()

    if not docs:
        print("[ir_report_ingest] Neo4j FilingDocument 에 대상 보고서 없음.")
        return

    print(f"[ir_report_ingest] 대상 {len(docs)}건 (모델={MODEL})")

    conn = mariadb_conn()
    cur = conn.cursor()
    ensure_tables(cur)
    conn.commit()

    processed = skipped = failed = 0

    with httpx.Client(follow_redirects=True) as client:
        for doc in docs:
            rcept_no = doc["rcept_no"]
            corp_code = doc["corp_code"]
            corp_name = CORP_NAMES.get(corp_code, corp_code)

            if not force and _has_summary(cur, rcept_no):
                print(f"  skip (already summarized): {rcept_no} {doc['doc_type']}")
                skipped += 1
                continue

            print(f"  처리 중: {rcept_no} [{corp_name}] {doc['doc_type']}")

            # 원문 확보
            try:
                raw_text, source = _get_raw_text(client, rcept_no, dart_key)
            except Exception as exc:
                print(f"  [ERROR] 원문 확보 예외 rcept_no={rcept_no}: {exc}", file=sys.stderr)
                _upsert_stub(cur, doc)
                conn.commit()
                failed += 1
                continue

            if not raw_text:
                print(f"  [WARN] 원문 없음 — stub 기록: {rcept_no}")
                _upsert_stub(cur, doc)
                conn.commit()
                failed += 1
                continue

            # Ollama 요약
            try:
                summary = _summarize(client, corp_name, raw_text)
            except Exception as exc:
                print(f"  [ERROR] 요약 실패 rcept_no={rcept_no}: {exc}", file=sys.stderr)
                # raw_text 는 있으므로 summary 없이 적재
                summary = ""

            _upsert_ir_report(cur, {
                "rcept_no": rcept_no,
                "corp_code": corp_code,
                "doc_type": doc["doc_type"],
                "date": doc["date"],
                "title": doc["title"],
                "raw_text": raw_text,
                "summary": summary,
                "source": source,
                "ingested_at": datetime.now(),
            })
            conn.commit()
            processed += 1
            print(f"  완료: {rcept_no} source={source} summary={len(summary)}자")

    cur.close()
    conn.close()
    print(
        f"\n[ir_report_ingest] 완료 — 처리:{processed} / skip:{skipped} / 실패:{failed}"
    )


# ── CLI ───────────────────────────────────────────────────────────

def main() -> None:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    ap = argparse.ArgumentParser(description="IR/정기보고서 원문 적재 + Ollama 요약 → ir_report")
    ap.add_argument(
        "--force",
        action="store_true",
        help="이미 summary 있는 건도 재요약",
    )
    args = ap.parse_args()
    ingest(force=args.force)


if __name__ == "__main__":
    main()
