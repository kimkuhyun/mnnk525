"""사전 기반 매칭 — 의미 그래프 추출 사전 필터.

구성:
  loader   : yaml 사전 (organizations/persons/products/technologies/places) 로드 + 캐시
  matcher  : Aho-Corasick automaton 통합 — entity_type 별 hit + ambiguous 차단
  triggers : 본문에 도메인 트리거 키워드 (합병/공급/출시 등) 존재 검사

사용:
  from polaris.graph.lexicon import build_matcher, has_trigger
  m = build_matcher()           # yaml 로드 + automaton 빌드 (캐시 1회)
  hits = m.scan(text)            # list[LexiconHit]
  if has_trigger(text): ...
"""
from polaris.graph.lexicon.loader import (
    load_aliases, load_all, ALIAS_DIR,
)
from polaris.graph.lexicon.matcher import (
    LexiconHit, Matcher, build_matcher,
)
from polaris.graph.lexicon.triggers import (
    TRIGGER_KEYWORDS, has_trigger, list_triggers,
)

__all__ = [
    "load_aliases", "load_all", "ALIAS_DIR",
    "LexiconHit", "Matcher", "build_matcher",
    "TRIGGER_KEYWORDS", "has_trigger", "list_triggers",
]
