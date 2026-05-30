"""qwen3.5:9b LLM Entity 추출 — strict JSON schema + 6단 방어.

설계 03 §A-2 ENTITY_SCHEMA 차용. chunk/lib/llm_summarize.py 의 Ollama 호출 패턴 재사용.

6단 방어:
  1. JSON schema strict (Ollama format=<schema>)
  2. 시스템 프롬프트 — 본문만, 추론 금지
  3. evidence_span 본문 substring 검증 (없으면 reject)
  4. entity text 본문 substring 검증
  5. type enum 검증 (Organization/Person/Product/Technology/Place)
  6. self_confidence < 0.5 reject
"""
from __future__ import annotations

import hashlib
import json
import time
from functools import lru_cache
from typing import Optional

import httpx

from polaris.config import OLLAMA_BASE, OLLAMA_LLM_MODEL

NUM_CTX = 8192
MAX_CHARS = 4000          # 본문 잘라내기 (LLM 호출 부담 완화)
MIN_CONFIDENCE = 0.5
TEMPERATURE = 0.0

ENTITY_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "본문에 등장한 표기 그대로 (10자 이내 권장)"
                    },
                    "type": {
                        "type": "string",
                        "enum": ["Organization", "Person", "Product",
                                  "Technology", "Place"]
                    },
                    "category": {
                        "type": "string",
                        "description": ("Product/Technology 인 경우만 카테고리. "
                                         "memory_hbm/memory_dram/memory_nand/foundry/"
                                         "process_lithography/process_packaging/material/equipment 등")
                    },
                    "evidence_span": {
                        "type": "string",
                        "description": "본문에서 entity 등장 구절 (10~50자 발췌, 본문에 substring 존재)"
                    },
                    "self_confidence": {
                        "type": "number",
                        "description": "0.0~1.0. 본문에 명시적 단언 = 0.9+, 약한 명시 = 0.6~0.8."
                    }
                },
                "required": ["text", "type", "evidence_span", "self_confidence"]
            }
        }
    },
    "required": ["entities"]
}

SYSTEM_PROMPT = """너는 한국 반도체 산업 도메인 entity 추출기다.

규칙:
1. 본문에 명시적으로 등장한 entity 만 추출. 추론·외부지식·가정 금지.
2. 회사명·인명은 본문 표기 그대로 (정규화는 후처리).
3. 제품: HBM, DRAM, NAND, 갤럭시 등 구체적 제품/제품군만. "메모리 사업"·"반도체"·"제품" 같은 일반 명사 제외.
4. 기술: EUV, 포토레지스트, TC본더, CoWoS 등 공정·재료·장비. "기술", "공정" 같은 일반 명사 제외.
5. 장소: 국가·도시. ISO 코드 매핑 가능한 수준.
6. 본문에 entity 0개면 빈 배열 출력.
7. 출력은 반드시 JSON Schema 매칭.
8. evidence_span 은 본문에서 그대로 발췌 (위조 금지)."""

USER_TEMPLATE = """## JSON Schema
{schema}

## 청크 본문 ({n_chars}자)
{text}

위 본문에서 한국 반도체 산업 관련 entity (회사·인물·제품·기술·장소) 만 추출하라.
JSON 만 출력."""


@lru_cache(maxsize=1)
def prompt_hash() -> str:
    """SYSTEM_PROMPT + USER_TEMPLATE + ENTITY_SCHEMA 의 SHA1[:16]. 추출 재현성용."""
    payload = "|".join([
        SYSTEM_PROMPT,
        USER_TEMPLATE,
        json.dumps(ENTITY_SCHEMA, sort_keys=True, ensure_ascii=False),
    ])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _validate_hits(entities: list[dict], text: str) -> list[dict]:
    """6단 방어 — substring + type enum + confidence."""
    allowed_types = {"Organization", "Person", "Product", "Technology", "Place"}
    out = []
    for e in entities:
        et = e.get("type", "")
        txt = (e.get("text") or "").strip()
        span = (e.get("evidence_span") or "").strip()
        conf = float(e.get("self_confidence", 0.0))
        if et not in allowed_types:
            continue
        if not txt or not span:
            continue
        if txt not in text:
            continue
        if span not in text:
            continue
        if conf < MIN_CONFIDENCE:
            continue
        out.append({
            "text": txt, "type": et,
            "category": (e.get("category") or "").strip(),
            "evidence_span": span, "self_confidence": conf,
        })
    return out


def call_ollama(text: str, *, timeout: int = 60) -> tuple[list[dict], dict]:
    """Entity 추출 1회 호출. return (validated_entities, meta).

    meta: {raw_count, validated_count, elapsed_ms, error?}
    """
    snippet = text[:MAX_CHARS]
    payload = {
        "model": OLLAMA_LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TEMPLATE.format(
                schema=json.dumps(ENTITY_SCHEMA, ensure_ascii=False),
                n_chars=len(snippet),
                text=snippet,
            )},
        ],
        "format": ENTITY_SCHEMA,
        "options": {"num_ctx": NUM_CTX, "temperature": TEMPERATURE},
        "think": False,
        "stream": False,
    }
    base_meta = {
        "model": OLLAMA_LLM_MODEL,
        "temperature": TEMPERATURE,
        "prompt_hash": prompt_hash(),
    }
    t0 = time.time()
    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.post(f"{OLLAMA_BASE}/api/chat", json=payload)
        elapsed = int((time.time() - t0) * 1000)
        if r.status_code != 200:
            return [], {**base_meta, "raw_count": 0, "validated_count": 0,
                        "elapsed_ms": elapsed, "error": f"http_{r.status_code}"}
        msg = r.json().get("message", {}).get("content", "")
        if not msg:
            return [], {**base_meta, "raw_count": 0, "validated_count": 0,
                        "elapsed_ms": elapsed, "error": "empty_message"}
        parsed = json.loads(msg)
        raw = parsed.get("entities", []) or []
        validated = _validate_hits(raw, snippet)
        return validated, {
            **base_meta,
            "raw_count": len(raw),
            "validated_count": len(validated),
            "elapsed_ms": elapsed,
        }
    except (json.JSONDecodeError, httpx.HTTPError, Exception) as e:
        return [], {**base_meta, "raw_count": 0, "validated_count": 0,
                    "elapsed_ms": int((time.time() - t0) * 1000),
                    "error": f"{type(e).__name__}: {e}"}
