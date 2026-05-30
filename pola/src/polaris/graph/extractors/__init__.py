"""의미 그래프 추출기 — 결정론 + LLM 분리.

deterministic.py : 사전 hit 만으로 추출 가능한 패턴 (Org+Product → PRODUCES 등). 신뢰 1.0.
filter.py        : 청크 분기 정책 (DROP / DETERMINISTIC / LLM PATH) + 통과율 측정.
llm_entity.py    : qwen3.5:9b strict JSON Entity 추출 (P-3.4)
llm_relation.py  : qwen3.5:9b Relation triple 추출 (P-3.4)
ner_filter.py    : (옵션) KoNLPy mecab 형태소 NER 후보 — Windows 환경 까다로워 후순위

순서: filter → deterministic → (LLM PATH 만) llm_entity → llm_relation
"""
from polaris.graph.extractors.deterministic import (
    DeterministicHit, extract_deterministic,
)
from polaris.graph.extractors.filter import (
    CHUNK_DROP_TYPES, classify_chunk, ChunkClass, scan_corpus_stats,
)

__all__ = [
    "DeterministicHit", "extract_deterministic",
    "CHUNK_DROP_TYPES", "classify_chunk", "ChunkClass", "scan_corpus_stats",
]
