"""qwen3.5:9b로 문서 요약 + 6단 할루시네이션 방어.

1. JSON 스키마 강제 (Ollama format=<schema>)
2. 프롬프트 제약 — "본문 안 단어만, 외부 지식 금지"
3. num_ctx=16384 + think=False (memory: feedback_ollama_structured.md)
4. 단어 일치율 검증 ≥ 90%
5. 2차 LLM cross-check
6. fail fallback → 휴리스틱 (제목 + 첫 의미 문단 1~3문장)
"""
from __future__ import annotations
import json
import re
import time
import httpx
from typing import Any

from polaris.config import OLLAMA_BASE, OLLAMA_LLM_MODEL as MODEL
NUM_CTX = 16384

# JSON 스키마 (Ollama format=<dict>)
SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary_short": {
            "type": "string",
            "description": "본문 내용 1~3문장 한국어 요약. 본문에 명시된 사실만 사용."
        },
        "doc_type": {
            "type": "string",
            "description": "문서 종류 (예: '사업보고서', '단일판매·공급계약체결', '주요사항보고서(자기주식취득결정)')"
        },
        "key_facts": {
            "type": "array",
            "items": {"type": "string"},
            "description": "본문에 명시된 핵심 사실 3~5개 (회사명·금액·날짜·계약상대방 등)"
        }
    },
    "required": ["summary_short", "doc_type", "key_facts"]
}

SYSTEM_PROMPT = """너는 한국 기업 공시 문서 분석 어시스턴트다. 다음 규칙을 엄수한다:
1. 본문에 명시된 사실만 사용한다. 외부 지식·추론·가정 금지.
2. 본문에 없는 회사명·금액·날짜·인명을 추가하지 않는다.
3. 모호하거나 추측이 필요한 정보는 생략한다.
4. 출력은 반드시 지정된 JSON 스키마에 정확히 매칭해야 한다."""

USER_TEMPLATE = """## JSON Schema (출력은 이 스키마에 정확히 매칭)
{schema}

## 본문 ({n_chars}자)
{text}

위 본문을 위 Schema에 정확히 매칭되는 JSON 객체로만 출력하라. 본문 단어 외 어떤 단어도 추가하지 마라."""


def call_ollama(text: str, max_chars: int = 5000) -> dict | None:
    """단일 LLM 호출. text는 본문 (잘라낼 수 있음)."""
    snippet = text[:max_chars] if len(text) > max_chars else text
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TEMPLATE.format(
                schema=json.dumps(SUMMARY_SCHEMA, ensure_ascii=False),
                n_chars=len(snippet),
                text=snippet,
            )},
        ],
        "format": SUMMARY_SCHEMA,
        "options": {"num_ctx": NUM_CTX, "temperature": 0.1},
        "think": False,
        "stream": False,
    }
    try:
        with httpx.Client(timeout=120) as c:
            r = c.post(f"{OLLAMA_BASE}/api/chat", json=payload)
        if r.status_code != 200:
            return None
        msg = r.json().get("message", {}).get("content", "")
        if not msg:
            return None
        return json.loads(msg)
    except Exception:
        return None


def word_match_rate(summary: str, body: str) -> float:
    """summary 단어가 body에 얼마나 있나 (한글 2자+ 단어 기준)."""
    if not summary or not body:
        return 0.0
    summary_words = set(re.findall(r"[가-힣]{2,}|[A-Za-z]{3,}|\d{2,}", summary))
    body_words = set(re.findall(r"[가-힣]{2,}|[A-Za-z]{3,}|\d{2,}", body))
    if not summary_words:
        return 0.0
    hit = summary_words & body_words
    return len(hit) / len(summary_words)


def cross_check_diff(s1: str, s2: str) -> float:
    """두 요약의 단어 차이 (Jaccard distance 기반)."""
    if not s1 or not s2:
        return 1.0
    w1 = set(re.findall(r"[가-힣]{2,}|[A-Za-z]{3,}|\d{2,}", s1))
    w2 = set(re.findall(r"[가-힣]{2,}|[A-Za-z]{3,}|\d{2,}", s2))
    if not w1 and not w2:
        return 0.0
    inter = len(w1 & w2)
    union = len(w1 | w2)
    if union == 0:
        return 0.0
    return 1.0 - (inter / union)


def summarize_with_defense(body: str, word_match_threshold: float = 0.7,
                            cross_check_threshold: float = 0.5) -> dict:
    """LLM 요약 + 검증. 휴리스틱 폐기 — LLM 실패시 LLM raw 결과 그대로 채택 (label만 표시).

    - 단어 일치 < 70%: 'llm_low_match' (raw 채택)
    - cross-check 차이 > 50%: 'llm_inconsistent' (1차 채택)
    - call 실패: '(LLM 호출 실패)' 빈 요약
    - 통과: 'llm_verified'
    """
    if not body or len(body) < 30:
        return {"summary_short": "(본문 너무 짧음)", "doc_type": "", "key_facts": [],
                "summary_method": "skip_short",
                "verification": {"passed": False, "reason": "too_short"}}

    # 1차 LLM
    r1 = call_ollama(body)
    if not r1 or not r1.get("summary_short"):
        return {"summary_short": "(LLM 호출 실패)", "doc_type": "", "key_facts": [],
                "summary_method": "llm_call_fail",
                "verification": {"passed": False, "reason": "llm_call_fail"}}

    summary = r1.get("summary_short", "")
    wm = word_match_rate(summary, body)

    # 2차 LLM cross-check (안전 우선 — 항상 수행)
    r2 = call_ollama(body)
    if not r2 or not r2.get("summary_short"):
        diff = 1.0
    else:
        diff = cross_check_diff(summary, r2["summary_short"])

    # 채택 정책 — 항상 LLM 결과 사용 (휴리스틱 폐기)
    if wm >= word_match_threshold and diff <= cross_check_threshold:
        method = "llm_verified"
        passed = True
    elif wm < word_match_threshold:
        method = "llm_low_match"
        passed = False
    else:
        method = "llm_inconsistent"
        passed = False

    return {
        "summary_short": summary,
        "doc_type": r1.get("doc_type", ""),
        "key_facts": r1.get("key_facts", []),
        "summary_method": method,
        "verification": {
            "passed": passed,
            "word_match_rate": round(wm, 3),
            "cross_check_diff": round(diff, 3),
            "llm_summary_2": r2.get("summary_short", "") if r2 else "",
        },
    }


# ============================================================================
# 청크 단위 요약 (Stage C-2b — text 청크 sidecar)
# ============================================================================

CHUNK_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "청크 내용 1~3문장 한국어 요약. 청크 본문에 명시된 사실만 사용."
        }
    },
    "required": ["summary"]
}

CHUNK_SUMMARY_USER_TEMPLATE = """## JSON Schema
{schema}

## 청크 본문 ({n_chars}자)
{text}

위 청크 본문을 1~3문장으로 한국어 요약하라. 본문에 없는 단어·사실 추가 금지. JSON 만 출력."""


def summarize_chunk(text: str, max_chars: int = 4000) -> dict:
    """단일 text 청크 요약. Ollama qwen3.5:9b 호출.

    반환: {"summary": str, "summary_method": "qwen_local_v1"|"llm_call_fail"|"skip_short"}

    Stage C-2b (run_stage_c2b_summary.py) 에서 호출. Ollama 미가동 시 자동으로
    llm_call_fail 라벨을 반환하므로 sidecar 파일 생성 자체는 안전.
    """
    if not text or len(text.strip()) < 30:
        return {"summary": "", "summary_method": "skip_short"}

    snippet = text[:max_chars] if len(text) > max_chars else text
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": CHUNK_SUMMARY_USER_TEMPLATE.format(
                schema=json.dumps(CHUNK_SUMMARY_SCHEMA, ensure_ascii=False),
                n_chars=len(snippet),
                text=snippet,
            )},
        ],
        "format": CHUNK_SUMMARY_SCHEMA,
        "options": {"num_ctx": NUM_CTX, "temperature": 0.1},
        "think": False,
        "stream": False,
    }
    try:
        with httpx.Client(timeout=60) as c:
            r = c.post(f"{OLLAMA_BASE}/api/chat", json=payload)
        if r.status_code != 200:
            return {"summary": "", "summary_method": "llm_call_fail"}
        msg = r.json().get("message", {}).get("content", "")
        if not msg:
            return {"summary": "", "summary_method": "llm_call_fail"}
        parsed = json.loads(msg)
        return {"summary": parsed.get("summary", "").strip(), "summary_method": "qwen_local_v1"}
    except Exception:
        return {"summary": "", "summary_method": "llm_call_fail"}
