"""청크 분기 정책 + 통과율 측정.

3 분기:
  DROP        : 결정론 그래프가 이미 처리한 청크 (재무 표·시계열·매크로)
  DETERMINISTIC: 사전 hit 만으로 충분 (entity_hit ≥ 3 high-confidence)
  LLM_PATH    : 트리거 + entity hit ≥ 2 (LLM 호출 대상, 통과율 < 30% 목표)
  SKIP        : entity 0 또는 너무 짧음 (의미 추출 가치 X)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from polaris.graph.lexicon import Matcher, has_trigger


class ChunkClass(str, Enum):
    DROP = "DROP"                  # 정형 처리 완료 — 의미 추출 대상 X
    DETERMINISTIC = "DETERMINISTIC"  # 사전 hit 충분 — LLM 불필요
    LLM_PATH = "LLM_PATH"          # LLM 호출 대상
    SKIP = "SKIP"                  # entity 부족 — 의미 추출 가치 X


# 결정론 그래프 이미 처리한 청크 (의미 추출 대상 X)
CHUNK_DROP_TYPES = {
    "table_nl",     # DART 재무 표 (5종 모두 — endpoint로 구분 가능하지만 단순화)
    "krx_ohlcv",    # 주가 시계열
    "bok_macro",    # 거시지표
    "kosis_meta",   # 통계청
    "ftc_meta",     # 공정위 (이미 정형 그래프에서 BusinessGroup 채움)
}

# LLM PATH 자격 — 본문 청크만
LLM_ELIGIBLE_TYPES = {"text_micro", "text_macro", "news_text"}

# 최소 본문 길이 (너무 짧으면 의미 추출 가치 X)
MIN_TEXT_CHARS = 80


@dataclass
class ChunkDecision:
    chunk_id: str
    klass: ChunkClass
    entity_hits: int = 0
    trigger_hit: bool = False
    reason: str = ""


def classify_chunk(chunk_id: str, chunk_type: str, text: str,
                   matcher: Matcher) -> ChunkDecision:
    """단일 청크 분기 결정. matcher 는 build_matcher() 결과 재사용."""
    if chunk_type in CHUNK_DROP_TYPES:
        return ChunkDecision(chunk_id, ChunkClass.DROP, reason=f"chunk_type={chunk_type}")
    if not text or len(text) < MIN_TEXT_CHARS:
        return ChunkDecision(chunk_id, ChunkClass.SKIP, reason=f"too_short({len(text or '')}c)")

    hits = matcher.scan(text)
    n_hits = len(hits)
    trig = has_trigger(text)

    # DETERMINISTIC: 사전 hit ≥ 3 + 트리거 0 — 사전 매칭 결과로 충분
    if n_hits >= 3 and not trig:
        return ChunkDecision(chunk_id, ChunkClass.DETERMINISTIC,
                              entity_hits=n_hits, trigger_hit=False,
                              reason="hits≥3 no_trigger")

    # LLM_PATH: 트리거 hit + entity hit ≥ 2
    if trig and n_hits >= 2:
        return ChunkDecision(chunk_id, ChunkClass.LLM_PATH,
                              entity_hits=n_hits, trigger_hit=True,
                              reason="trigger+hits≥2")

    # 그 외 — SKIP
    return ChunkDecision(chunk_id, ChunkClass.SKIP,
                          entity_hits=n_hits, trigger_hit=trig,
                          reason=f"hits={n_hits} trig={trig}")


def scan_corpus_stats(chunks: Iterable[dict], matcher: Matcher) -> dict:
    """전체 청크 스캔 → 분기 통계 (실제 LLM 호출 비용 추정).

    chunks: [{chunk_id, chunk_type, text}, ...]
    return: {DROP: N, DETERMINISTIC: N, LLM_PATH: N, SKIP: N, total: N,
             llm_path_ratio: float, samples: {klass: [chunk_id...]}}
    """
    counters: dict[str, int] = {c.value: 0 for c in ChunkClass}
    samples: dict[str, list[str]] = {c.value: [] for c in ChunkClass}
    total = 0
    for ch in chunks:
        total += 1
        d = classify_chunk(ch["chunk_id"], ch["chunk_type"], ch.get("text", ""),
                            matcher)
        counters[d.klass.value] += 1
        if len(samples[d.klass.value]) < 5:
            samples[d.klass.value].append(ch["chunk_id"])
    llm_ratio = counters[ChunkClass.LLM_PATH.value] / total if total else 0.0
    return {
        **counters,
        "total": total,
        "llm_path_ratio": round(llm_ratio, 4),
        "samples": samples,
    }
