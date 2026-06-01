"""POLARIS 적재 공통 헬퍼 — MariaDB conn, Qdrant client, Ollama embed.

접속정보는 작업 지시의 실제 값을 우선 사용(.env 의 Blue/Green 등 구값 무시).
외부 인터넷 금지 — 로컬 DB / 로컬 Ollama 만.
"""
from __future__ import annotations

import time

import httpx
import pymysql
from qdrant_client import QdrantClient

# ── 접속 정보 (실제 가동 컨테이너) ──────────────────────────
MARIADB = dict(
    host="localhost",
    port=3307,
    user="polaris",
    password="polaris_dev_only",
    database="polaris",
    charset="utf8mb4",
)
QDRANT_URL = "http://localhost:6333"
OLLAMA_BASE = "http://localhost:11434"
EMBED_MODEL = "bge-m3"  # bge-m3:latest 와 동일 태그
EMBED_DIM = 1024
# bge-m3 컨텍스트는 8192 토큰. 한국어는 char당 토큰>1 이라 긴 청크는 컨텍스트 초과(500).
# 임베딩 입력만 안전 절단(원문 전문은 MariaDB chunk_index 에 보존). 5000자 여유.
EMBED_CHAR_LIMIT = 5000

COLLECTION_CHUNKS = "polaris-chunks"

# 회사 폴더명 → corp_code
CORP_CODE = {
    "삼성전자": "00126380",
    "SK하이닉스": "00164779",
    "한미반도체": "00161383",
}


def mariadb_conn() -> pymysql.connections.Connection:
    return pymysql.connect(**MARIADB, autocommit=False)


def qdrant_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL, timeout=120)


def ollama_embed(text: str, client: httpx.Client | None = None) -> list[float]:
    """단일 텍스트 임베딩(1024d). 로컬 Ollama bge-m3.

    - 긴 입력은 EMBED_CHAR_LIMIT 로 절단(컨텍스트 초과 500 방지). 절단 후에도
      컨텍스트 초과 500 이 나면 입력을 절반으로 줄여 재시도.
    - 일시적 오류는 짧게 backoff 재시도.
    """
    own = client is None
    if own:
        client = httpx.Client(timeout=120)
    prompt = (text or "")[:EMBED_CHAR_LIMIT]
    if not prompt.strip():
        prompt = " "  # 빈 텍스트 방지
    try:
        last_err: Exception | None = None
        for attempt in range(5):
            try:
                r = client.post(
                    f"{OLLAMA_BASE}/api/embeddings",
                    json={"model": EMBED_MODEL, "prompt": prompt},
                )
                if r.status_code == 500 and "context length" in r.text:
                    # 여전히 컨텍스트 초과 → 입력 절반으로
                    prompt = prompt[: max(500, len(prompt) // 2)]
                    continue
                r.raise_for_status()
                vec = r.json()["embedding"]
                if len(vec) != EMBED_DIM:
                    raise ValueError(f"임베딩 차원 불일치: {len(vec)} != {EMBED_DIM}")
                return vec
            except (httpx.HTTPError, ValueError) as e:
                last_err = e
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"임베딩 실패(재시도 소진): {last_err}")
    finally:
        if own:
            client.close()
