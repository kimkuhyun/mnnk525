"""qwen3.5:9b LLM Relation triple 추출 — strict JSON + 6단 방어.

설계 03 §A-2 RELATION_SCHEMA 차용. Entity 추출 결과를 prompt 에 같이 넣어 정확도 보강.

predicate enum (8종):
  SUPPLIES_TO, COMPETES_WITH, IS_SUBSIDIARY_OF, PRODUCES,
  USES_TECH, HAS_CEO, MERGED_WITH, INVESTED_IN
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
MAX_CHARS = 4000
MIN_CONFIDENCE = 0.5
TEMPERATURE = 0.0

PREDICATES = [
    "SUPPLIES_TO", "COMPETES_WITH", "IS_SUBSIDIARY_OF", "PRODUCES",
    "USES_TECH", "HAS_CEO", "MERGED_WITH", "INVESTED_IN",
]

RELATION_SCHEMA = {
    "type": "object",
    "properties": {
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "entity 표기 그대로"},
                    "subject_type": {
                        "type": "string",
                        "enum": ["Organization", "Person", "Product", "Technology"]
                    },
                    "predicate": {"type": "string", "enum": PREDICATES},
                    "object": {"type": "string"},
                    "object_type": {
                        "type": "string",
                        "enum": ["Organization", "Person", "Product", "Technology"]
                    },
                    "valid_from": {
                        "type": "string",
                        "description": "ISO 날짜 YYYY-MM-DD 또는 빈 문자열"
                    },
                    "evidence_span": {
                        "type": "string",
                        "description": "본문에서 관계 근거 구절 (10~80자, 본문 substring)"
                    },
                    "self_confidence": {
                        "type": "number",
                        "description": "0.0~1.0. 강한 명시=0.9+, 약한 명시=0.6~0.8."
                    }
                },
                "required": ["subject", "subject_type", "predicate",
                              "object", "object_type",
                              "evidence_span", "self_confidence"]
            }
        }
    },
    "required": ["relations"]
}

SYSTEM_PROMPT = """너는 한국 반도체 산업 관계(triple) 추출기다.

규칙:
1. 본문에 명시적 근거가 있는 관계만 추출. 추측·암시·추론·외부지식 금지.
2. predicate 는 정의된 enum 목록에서만 선택 — 그 외 관계 출력 금지.
3. subject·object 는 본문 entity 표기 그대로 사용 (정규화 후처리).
4. evidence_span 에 본문에서 관계 근거 구절(10~80자)을 정확히 발췌. 위조 금지.
5. self_confidence: 강한 명시 ≥ 0.9, 약한 명시 0.6~0.8, 모호 ≤ 0.5.
6. 본문에 없는 관계는 추출하지 마라 (출력 0개 OK).
7. 동일 triple 중복 출력 금지.
8. 출력은 반드시 JSON Schema 매칭."""

USER_TEMPLATE = """## JSON Schema
{schema}

## 추출된 entity (Entity 단계 산출물)
{entities_json}

## 청크 본문 ({n_chars}자)
{text}

위 entity 들 사이의 관계 중, 본문에 명시적으로 단언된 triple 만 추출하라.
JSON 만 출력."""


@lru_cache(maxsize=1)
def prompt_hash() -> str:
    """SYSTEM_PROMPT + USER_TEMPLATE + RELATION_SCHEMA 의 SHA1[:16]. 추출 재현성용."""
    payload = "|".join([
        SYSTEM_PROMPT,
        USER_TEMPLATE,
        json.dumps(RELATION_SCHEMA, sort_keys=True, ensure_ascii=False),
    ])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _validate_triples(relations: list[dict], text: str,
                       entity_texts: set[str]) -> list[dict]:
    out = []
    seen = set()
    allowed_types = {"Organization", "Person", "Product", "Technology"}
    for r in relations:
        subj = (r.get("subject") or "").strip()
        obj = (r.get("object") or "").strip()
        pred = r.get("predicate", "")
        st = r.get("subject_type", "")
        ot = r.get("object_type", "")
        span = (r.get("evidence_span") or "").strip()
        conf = float(r.get("self_confidence", 0.0))
        if not subj or not obj or not span:
            continue
        if pred not in PREDICATES:
            continue
        if st not in allowed_types or ot not in allowed_types:
            continue
        if subj not in text or obj not in text:
            continue
        if span not in text:
            continue
        if conf < MIN_CONFIDENCE:
            continue
        # entity 단계 결과와 일관성 (entity 에서 추출된 surface 만)
        if entity_texts and (subj not in entity_texts or obj not in entity_texts):
            continue
        key = (subj, pred, obj)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "subject": subj, "subject_type": st,
            "predicate": pred,
            "object": obj, "object_type": ot,
            "valid_from": (r.get("valid_from") or "").strip(),
            "evidence_span": span, "self_confidence": conf,
        })
    return out


def call_ollama(text: str, entities: list[dict], *,
                 timeout: int = 90) -> tuple[list[dict], dict]:
    """Relation triple 추출. entities = llm_entity.call_ollama() validated 결과."""
    snippet = text[:MAX_CHARS]
    entity_texts = {e["text"] for e in entities} if entities else set()
    # entity 요약 (LLM 입력)
    entities_short = [{"text": e["text"], "type": e["type"]} for e in entities[:30]]
    payload = {
        "model": OLLAMA_LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TEMPLATE.format(
                schema=json.dumps(RELATION_SCHEMA, ensure_ascii=False),
                entities_json=json.dumps(entities_short, ensure_ascii=False),
                n_chars=len(snippet),
                text=snippet,
            )},
        ],
        "format": RELATION_SCHEMA,
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
        raw = parsed.get("relations", []) or []
        validated = _validate_triples(raw, snippet, entity_texts)
        return validated, {
            **base_meta,
            "raw_count": len(raw),
            "validated_count": len(validated),
            "elapsed_ms": elapsed,
        }
    except Exception as e:
        return [], {**base_meta, "raw_count": 0, "validated_count": 0,
                    "elapsed_ms": int((time.time() - t0) * 1000),
                    "error": f"{type(e).__name__}: {e}"}
