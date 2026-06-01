"""POLARIS 정형 그래프 로더 공통 헬퍼 — MariaDB conn, Neo4j driver, 결정론 id·숫자파싱.

외부 인터넷 금지(로컬 DB만). LLM 호출 금지(전부 결정론).
접속정보는 작업 지시의 실제 값 사용.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pymysql
from neo4j import GraphDatabase

# ── 접속 정보 (실제 가동 컨테이너) ──────────────────────────
MARIADB = dict(
    host="localhost",
    port=3307,
    user="polaris",
    password="polaris_dev_only",
    database="polaris",
    charset="utf8mb4",
)
NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "polaris_dev_only")

# 회사 폴더명 → corp_code
CORP_CODE = {
    "삼성전자": "00126380",
    "SK하이닉스": "00164779",
    "한미반도체": "00161383",
}
# 역매핑 / 정식 회사명(company.json 기준)
CORP_NAME = {
    "00126380": "삼성전자(주)",
    "00164779": "SK하이닉스(주)",
    "00161383": "한미반도체(주)",
}

# 사업보고서 rcept (XII 종속회사 표 파싱 대상) — 회사폴더별
BIZ_REPORT_RCEPT = {
    "삼성전자": ["20250311001085", "20260310002820"],
    "SK하이닉스": ["20250319000665", "20260317000635"],
    "한미반도체": ["20250313001171", "20260312001230"],
}

RAW_DIR = Path(r"C:\Users\kimkuhyn\Desktop\mnnk525\db\raw")


def mariadb_conn() -> pymysql.connections.Connection:
    return pymysql.connect(**MARIADB, autocommit=False)


def neo4j_driver():
    d = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    d.verify_connectivity()
    return d


# ── 결정론 id 생성 ─────────────────────────────────────────
def person_id(corp_code: str, name: str, birth_ym: str = "") -> str:
    """임원·개인주주 결정론 id = sha1(corp_code|name|birth_ym)[:16]."""
    key = f"{corp_code}|{(name or '').strip()}|{(birth_ym or '').strip()}"
    return "p_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def metric_id(corp_code: str, rcept_no: str, fs_div: str, account_id: str) -> str:
    """재무지표 결정론 id (VARCHAR(32) 이내). sha1 앞 24hex + 접두."""
    key = f"{corp_code}|{rcept_no}|{fs_div}|{account_id}"
    return "fm_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:24]


def name_org_key(name: str) -> str:
    """corp_code 없는 회사용 정규화 이름 키(needs_er 노드 식별)."""
    return normalize_corp_name(name)


# ── 숫자·이름 파싱 ─────────────────────────────────────────
_NUM_CLEAN = re.compile(r"[^\d.\-]")


def parse_number(raw) -> float | None:
    """콤마 제거, △/괄호/선행- = 음수. 빈값·'-' → None."""
    if raw is None:
        return None
    s = str(raw).strip()
    if s in ("", "-", "–", "—", "N/A", "해당없음"):
        return None
    neg = False
    if "△" in s or "▲" in s:
        neg = True
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    s = s.replace(",", "").replace("△", "").replace("▲", "").strip()
    s = _NUM_CLEAN.sub("", s)
    if s in ("", "-", ".", "-."):
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return -abs(v) if neg else v


def parse_qota_rt(raw) -> float | None:
    return parse_number(raw)


_SUFFIX = re.compile(r"(주식회사|㈜|\(주\)|주\)|\(유\)|유한회사|Co\.,?\s*Ltd\.?|Inc\.?|Corp\.?|Ltd\.?|LLC|GmbH)", re.IGNORECASE)


def normalize_corp_name(name: str) -> str:
    """ER 키용 정규화: 법인 접미사·공백·괄호주석 제거 후 소문자."""
    if not name:
        return ""
    s = name.strip()
    # 괄호 약어 (SEA) 등 제거
    s = re.sub(r"\([^)]*\)", "", s)
    s = _SUFFIX.sub("", s)
    s = re.sub(r"\s+", "", s)
    return s.strip().lower()
