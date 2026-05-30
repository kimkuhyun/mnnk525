"""POLARIS 전역 설정 — .env 1회 로드 + DB 클라이언트 헬퍼 + 도메인 상수.

원칙:
- 모든 비밀·포트·회사 목록은 .env 에서 로드. 코드에 하드코딩 X.
- 회사 추가/변경 시 .env 만 수정. 코드 변경 불필요.
- DB 클라이언트는 lazy import (test 환경에서 불필요한 의존성 회피).
"""
from __future__ import annotations
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # pola/


# ─── .env 로더 (외부 의존성 없이) ─────────────────────────────
def _strip_inline_comment(v: str) -> str:
    if v.startswith(('"', "'")):
        quote = v[0]
        end = v.find(quote, 1)
        if end > 0:
            return v[1:end]
        return v[1:]
    for i, ch in enumerate(v):
        if ch == "#" and (i == 0 or v[i - 1].isspace()):
            v = v[:i]
            break
    return v.strip()


def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    with env_path.open(encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = _strip_inline_comment(v.strip())
            if k and k not in os.environ:
                os.environ[k] = v


_load_env()


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# ─── 데이터 디렉토리 (DART JSON·정제·청크·임베딩 산출물) ─────
# .env 의 POLARIS_DATA_ROOT 가 있으면 우선. 없으면 pola/data 기본.
DATA_ROOT = Path(_env("POLARIS_DATA_ROOT")) if _env("POLARIS_DATA_ROOT") else (ROOT / "data")
FILTERED_DIR = DATA_ROOT / "2_Chuck" / "01_filtered"     # DART JSON
META_DIR = DATA_ROOT / "2_Chuck" / "02_meta"             # document_index.jsonl 등
CLEAN_DIR = DATA_ROOT / "2_Chuck" / "02_clean"           # HTML body_clean
CHUNKS_DIR = DATA_ROOT / "2_Chuck" / "03_chunks"         # chunk jsonl
EMBED_DIR = DATA_ROOT / "2_Chuck" / "04_embed"           # 임베딩 산출물


# ─── Qdrant ───────────────────────────────────────────────────
QDRANT_HOST = _env("QDRANT_HOST", "localhost")
QDRANT_HTTP_PORT = int(_env("QDRANT_HTTP_PORT", "6333"))
QDRANT_COLLECTION_ACTIVE = _env("QDRANT_COLLECTION_ACTIVE", "polaris-1024-cos-blue")
QDRANT_COLLECTION_STANDBY = _env("QDRANT_COLLECTION_STANDBY", "polaris-1024-cos-green")
QDRANT_URL = f"http://{QDRANT_HOST}:{QDRANT_HTTP_PORT}"


# ─── Neo4j ────────────────────────────────────────────────────
NEO4J_BOLT_URI = _env("NEO4J_BOLT_URI", "bolt://localhost:7687")
NEO4J_USER = _env("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = _env("NEO4J_PASSWORD", "polaris_dev_only")


# ─── MariaDB ──────────────────────────────────────────────────
MARIADB_HOST = _env("MARIADB_HOST", "localhost")
MARIADB_PORT = int(_env("MARIADB_PORT", "3307"))
MARIADB_DATABASE = _env("MARIADB_DATABASE", "polaris")
MARIADB_USER = _env("MARIADB_USER", "polaris")
MARIADB_PASSWORD = _env("MARIADB_PASSWORD", "polaris_dev_only")


# ─── Ollama (임베딩 + LLM) ────────────────────────────────────
OLLAMA_BASE = _env("OLLAMA_BASE", "http://localhost:11434")
OLLAMA_EMBED_MODEL = _env("OLLAMA_EMBED_MODEL", "bge-m3:latest")
OLLAMA_LLM_MODEL = _env("OLLAMA_LLM_MODEL", "qwen3.5:9b")


# ─── Rerank ───────────────────────────────────────────────────
RERANK_MODEL = _env("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")


# ─── DART ─────────────────────────────────────────────────────
DART_API_KEY = _env("DART_API_KEY", "")


# ─── 회사 목록 (CSV) ─────────────────────────────────────────
# 새 회사 추가: .env 의 POLARIS_CORPS / POLARIS_CORP_NAMES 만 갱신
def _csv(name: str, fallback: list[str]) -> list[str]:
    raw = _env(name, "")
    if not raw:
        return list(fallback)
    return [x.strip() for x in raw.split(",") if x.strip()]


CORPS: list[str] = _csv("POLARIS_CORPS",
                        ["00126380", "00164779", "00118804", "01489648", "00161383"])

# ─── P-2.4 S-09: CORPS_ALL vs CORPS_ACTIVE 분리 ───────────────
# CORPS_ALL    : 적재 대상 전체 (그래프·청크에 들어가는 회사)
# CORPS_ACTIVE : 검색·평가에 노출되는 회사 (subset)
# 둘 다 미설정이면 POLARIS_CORPS 로 fallback (기존 동작 유지).
CORPS_ALL: list[str] = _csv("POLARIS_CORPS_ALL", CORPS)
CORPS_ACTIVE: list[str] = _csv("POLARIS_CORPS_ACTIVE", CORPS_ALL)

# ─── corps.json (DART 마스터) 조회 ────────────────────────────
# 회사명·stock_code·isin 자동 매핑 → .env 에는 corp_code 만 두면 충분.
# 기본: 패키지 내장(src/polaris/data/corps.json). .env 의 POLARIS_CORP_DB 로 override.
_PKG_CORP_DB = Path(__file__).resolve().parent / "data" / "corps.json"
_env_corp_db = _env("POLARIS_CORP_DB", "")
CORP_DB_PATH = Path(_env_corp_db) if _env_corp_db else _PKG_CORP_DB


def _load_corp_db() -> dict[str, dict]:
    """corps.json → {corp_code(8자리): {corp_name, stock_code, isin?, modify_date}}.
    파일 없으면 빈 dict (호출자가 fallback)."""
    if not CORP_DB_PATH or not CORP_DB_PATH.is_file():
        return {}
    import json
    with CORP_DB_PATH.open(encoding="utf-8") as f:
        rows = json.load(f)
    out = {}
    for r in rows:
        cc = (r.get("corp_code") or "").zfill(8)
        if not cc:
            continue
        out[cc] = {
            "corp_name": r.get("corp_name", "").strip(),
            "stock_code": r.get("stock_code", "").strip().zfill(6) if r.get("stock_code") else "",
            "modify_date": r.get("modify_date", ""),
        }
    return out


_CORP_DB: dict[str, dict] | None = None


def corp_lookup(corp_code: str) -> dict:
    """corp_code → {corp_name, stock_code, modify_date}. 캐시 1회 로드."""
    global _CORP_DB
    if _CORP_DB is None:
        _CORP_DB = _load_corp_db()
    return _CORP_DB.get(corp_code.zfill(8), {})


def get_corp_meta(corp_code: str) -> dict:
    """corp_code → 전체 메타. corps.json 우선, 없으면 5사 fallback."""
    m = corp_lookup(corp_code)
    if m:
        return {"corp_code": corp_code.zfill(8), **m}
    _fallback = {
        "00126380": {"corp_name": "삼성전자", "stock_code": "005930"},
        "00164779": {"corp_name": "SK하이닉스", "stock_code": "000660"},
        "00118804": {"corp_name": "동진쎄미켐", "stock_code": "005290"},
        "01489648": {"corp_name": "솔브레인", "stock_code": "357780"},
        "00161383": {"corp_name": "한미반도체", "stock_code": "042700"},
    }
    return {"corp_code": corp_code.zfill(8), **_fallback.get(corp_code.zfill(8), {})}


# CORP_NAMES / CORP_NAME_TO_CODE 자동 채움 (corps.json 우선, .env override 가능)
_explicit_names = _csv("POLARIS_CORP_NAMES", [])  # 명시 override
if _explicit_names and len(_explicit_names) == len(CORPS):
    CORP_NAMES = dict(zip(CORPS, _explicit_names))
else:
    CORP_NAMES = {cc: get_corp_meta(cc).get("corp_name", cc) for cc in CORPS}
CORP_NAME_TO_CODE: dict[str, str] = {n: c for c, n in CORP_NAMES.items() if n}
if "SK하이닉스" in CORP_NAME_TO_CODE:
    CORP_NAME_TO_CODE.setdefault("에스케이하이닉스", CORP_NAME_TO_CODE["SK하이닉스"])


# ─── 카테고리별 검색·평가 정책 ────────────────────────────────
# v18 final 결과로 검증된 best practice.
CATEGORY_ENDPOINTS = {
    "정형수치": ["fnlttSinglAcntAll"],
    "시계열": ["fnlttSinglAcntAll"],
    "비교": ["fnlttSinglAcntAll"],
    "시점": ["exctvSttus", "outcmpnyDrctrNdChangeSttus"],
    "출처_충돌_검증": ["accnutAdtorNmNdAdtOpinion"],
    "자유서술": None,
}
CATEGORY_CHUNK_TYPES = {"자유서술": ["text_micro", "text_macro"]}
CATEGORY_BM25_DISABLE = {"자유서술"}  # BM25 가 자유서술에 역효과
CATEGORY_RERANK_DISABLE = {"자유서술", "비교"}
CATEGORY_CORP_BALANCED = {"비교"}
NON_VECTOR_GATE = {"비교"}  # 그래프 영역, 벡터 게이트 제외


# ─── 클라이언트 헬퍼 (lazy import) ────────────────────────────
def qdrant_client():
    from qdrant_client import QdrantClient
    return QdrantClient(url=QDRANT_URL, timeout=60)


def neo4j_driver():
    from neo4j import GraphDatabase
    return GraphDatabase.driver(NEO4J_BOLT_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def mariadb_conn(user: str | None = None, password: str | None = None,
                 database: str | None = None):
    import pymysql
    return pymysql.connect(
        host=MARIADB_HOST, port=MARIADB_PORT,
        user=user or MARIADB_USER,
        password=password or MARIADB_PASSWORD,
        database=database or MARIADB_DATABASE,
        charset="utf8mb4", autocommit=False,
    )


def get_active_run() -> tuple[str, str]:
    """active run_id 와 active qdrant collection 조회.

    환경변수 override 우선순위 (build 안에서만 사용):
      POLARIS_TARGET_RUN_ID — graph-extract / load-finmetric / load-chunk-nodes 가
                              standby_run_id 로 적재하도록 강제. 평소(검색·진단) 미설정.
    """
    target = os.environ.get("POLARIS_TARGET_RUN_ID", "").strip()
    conn = mariadb_conn(); cur = conn.cursor()
    if target:
        cur.execute("SELECT standby_qdrant_collection FROM active_run_manifest WHERE id=1")
        col = cur.fetchone()[0]
        cur.close(); conn.close()
        return target, col
    cur.execute("SELECT active_run_id, active_qdrant_collection FROM active_run_manifest WHERE id=1")
    row = cur.fetchone()
    cur.close(); conn.close()
    return row[0], row[1]
