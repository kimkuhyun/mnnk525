"""5 추출기 공유 유틸 — raw JSON 로더, hash, MERGE 헬퍼."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Iterable

from polaris.config import DATA_ROOT, CORPS, get_corp_meta, neo4j_driver

# Neo4j unknown label warning 등 silence
logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)
logging.getLogger("neo4j").setLevel(logging.ERROR)


# ────── hash + 정규화 ─────────────────────────────────────────

def hash16(*parts: str) -> str:
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()[:16]


_NORM_RE = re.compile(r"\s+")
_CORP_SUFFIX_RE = re.compile(r"(주식회사|㈜|\(주\)|株式会社|Co\.,?\s*Ltd\.?|Inc\.?|Corp\.?|Ltd\.?)",
                              re.IGNORECASE)


def canonicalize_name(name: str) -> str:
    """회사명 정규화 — (주)·주식회사·㈜·공백 제거. 매칭 정확도 향상용."""
    if not name:
        return ""
    s = _CORP_SUFFIX_RE.sub("", str(name))
    s = _NORM_RE.sub(" ", s).strip()
    return s


def parse_amount(raw) -> int | None:
    """'1,234,567' 또는 '△123' → int. 실패 시 None."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s in ("-", "—"):
        return None
    neg = s.startswith("△") or s.startswith("-")
    s = s.lstrip("△-").replace(",", "").replace(" ", "")
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    try:
        v = int(float(s))
        return -v if neg else v
    except (ValueError, TypeError):
        return None


def parse_rate(raw) -> float | None:
    """'23.7' → 23.7. 실패 시 None."""
    if raw is None:
        return None
    try:
        return float(str(raw).replace(",", "").replace("%", "").strip())
    except (ValueError, TypeError):
        return None


def parse_date_loose(raw) -> str | None:
    """'1977.01.01' / '20250311' / '2025-03-11' → 'YYYY-MM-DD'. 실패 시 None."""
    if not raw:
        return None
    s = str(raw).strip().replace(".", "-").replace("/", "-")
    s = re.sub(r"\s+", "", s)
    # YYYYMMDD
    if re.fullmatch(r"\d{8}", s):
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


# ────── DART raw 순회 ────────────────────────────────────────

def iter_dart_raw(endpoint: str, corp_codes: list[str] | None = None) -> Iterable[tuple[str, dict]]:
    """rawData/{cc}/dart/{endpoint}__*.json 모두 yield. (corp_code, doc)."""
    corps = corp_codes if corp_codes is not None else CORPS
    for cc in corps:
        base = DATA_ROOT / "rawData" / cc / "dart"
        if not base.is_dir():
            continue
        for jf in sorted(base.glob(f"{endpoint}__*.json")):
            try:
                doc = json.loads(jf.read_text(encoding="utf-8"))
            except Exception:
                continue
            if doc.get("status") != "ok":
                continue
            yield cc, doc


def iter_rows(doc: dict) -> Iterable[dict]:
    rows = (doc.get("data", {}) or {}).get("list") or []
    for r in rows:
        if isinstance(r, dict):
            yield r


# ────── corp_code lookup (회사명·jurirno → corp_code) ──────

_CORP_INDEX_BY_NAME: dict[str, str] = {}
_CORP_INDEX_BY_JURIRNO: dict[str, str] = {}


def _build_corp_indexes():
    if _CORP_INDEX_BY_NAME:
        return
    from polaris.config import _load_corp_db
    try:
        all_corps = _load_corp_db()
    except Exception:
        all_corps = {}
    for cc, meta in all_corps.items():
        cn = canonicalize_name(meta.get("corp_name", ""))
        if cn:
            _CORP_INDEX_BY_NAME.setdefault(cn, cc)
        jur = (meta.get("jurir_no") or "").strip()
        if jur:
            _CORP_INDEX_BY_JURIRNO[jur] = cc


def lookup_corp_code_by_name(name: str) -> str | None:
    _build_corp_indexes()
    cn = canonicalize_name(name)
    return _CORP_INDEX_BY_NAME.get(cn)


def lookup_corp_code_by_jurirno(jurirno: str) -> str | None:
    _build_corp_indexes()
    return _CORP_INDEX_BY_JURIRNO.get((jurirno or "").strip())


# ────── active run_id ────────────────────────────────────────

def get_active_run_id() -> str:
    """그래프 적재 대상 run_id 조회.

    우선순위:
      1) 환경변수 POLARIS_TARGET_RUN_ID — build 안에서 graph-extract 호출 직전에 standby_run_id 로 override (적재 정합 보장)
      2) active_run_manifest.active_run_id — 단독 호출 시 (검색·진단 용도)
    """
    import os
    target = os.environ.get("POLARIS_TARGET_RUN_ID", "").strip()
    if target:
        return target
    from polaris.config import mariadb_conn
    conn = mariadb_conn(); cur = conn.cursor()
    cur.execute("SELECT active_run_id FROM active_run_manifest WHERE id=1")
    rid = cur.fetchone()[0]
    cur.close(); conn.close()
    return rid


# ────── Neo4j 세션 컨텍스트 ─────────────────────────────────

class GraphSession:
    """driver + session context. with 블록 안에서 self.s 사용."""
    def __init__(self):
        self.drv = None
        self.s = None

    def __enter__(self):
        self.drv = neo4j_driver()
        self.s = self.drv.session()
        return self

    def __exit__(self, *exc):
        if self.s: self.s.close()
        if self.drv: self.drv.close()
