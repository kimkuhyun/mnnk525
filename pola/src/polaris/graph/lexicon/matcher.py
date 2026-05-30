"""Aho-Corasick 통합 automaton — 5 entity_type 한 번에 스캔.

설계:
- 1개 automaton 에 (entity_type, entity_id, surface) 튜플 저장
- ambiguous_alone 사전은 차단 (단독 매칭 X) → 다른 alias 또는 LLM disambiguation 으로 처리
- entity_id 는 entity_type 별 자연키 (corp_code, person_id, product_id 등)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import ahocorasick

from polaris.graph.lexicon.loader import load_all


@dataclass(frozen=True)
class LexiconHit:
    entity_type: str       # Organization / Person / Product / Technology / Place
    entity_id: str         # 자연키 값 (corp_code / person_id / product_id / tech_id / iso_code)
    surface: str           # 본문 표기 그대로
    span_start: int        # 본문 내 시작 offset (Aho-Corasick end_index 에서 역산)
    span_end: int          # 본문 내 종료 offset (exclusive)


class Matcher:
    """5 entity_type 통합 matcher."""

    def __init__(self):
        self._automaton: Optional[ahocorasick.Automaton] = None
        self._ambiguous: set[str] = set()  # 단독 매칭 차단 surface 집합
        self._stats: dict[str, int] = {}    # entity_type → alias 카운트
        self._build()

    def _build(self):
        A = ahocorasick.Automaton()
        aliases = load_all()
        counters: dict[str, int] = {k: 0 for k in
            ("Organization", "Person", "Product", "Technology", "Place")}

        # Organization
        for cc, meta in (aliases.get("organizations") or {}).items():
            cc8 = str(cc).zfill(8) if str(cc).isdigit() else str(cc)
            for name in [meta.get("name", "")] + (meta.get("aliases") or []) \
                        + (meta.get("ticker") or []):
                if not name: continue
                A.add_word(name, ("Organization", cc8, name))
                counters["Organization"] += 1
            for amb in (meta.get("ambiguous_alone") or []):
                self._ambiguous.add(amb)

        # Person — name + aliases (선택)
        for pid, meta in (aliases.get("persons") or {}).items():
            for name in [meta.get("name", "")] + (meta.get("aliases") or []):
                if not name: continue
                A.add_word(name, ("Person", str(pid), name))
                counters["Person"] += 1

        # Product
        for pid, meta in (aliases.get("products") or {}).items():
            canonical = meta.get("canonical") or str(pid)
            for name in [canonical] + (meta.get("aliases") or []):
                if not name: continue
                A.add_word(name, ("Product", str(pid), name))
                counters["Product"] += 1

        # Technology
        for tid, meta in (aliases.get("technologies") or {}).items():
            canonical = meta.get("canonical") or str(tid)
            for name in [canonical] + (meta.get("aliases") or []):
                if not name: continue
                A.add_word(name, ("Technology", str(tid), name))
                counters["Technology"] += 1

        # Place — iso_code 자연키, kor_name + aliases
        for iso, meta in (aliases.get("places") or {}).items():
            for name in [meta.get("kor_name", "")] + (meta.get("aliases") or []):
                if not name: continue
                A.add_word(name, ("Place", str(iso), name))
                counters["Place"] += 1

        if any(counters.values()):
            A.make_automaton()
            self._automaton = A
        self._stats = counters

    @property
    def stats(self) -> dict[str, int]:
        """entity_type 별 alias 총 등록 수."""
        return dict(self._stats)

    def scan(self, text: str, *, longest_only: bool = True) -> list[LexiconHit]:
        """본문 → LexiconHit 리스트. ambiguous surface 는 자동 제외.

        longest_only=True 시 같은 위치에 prefix-매칭 중복은 제거하고 최장만 유지
        (예: 'HBM3E' 본문 → HBM/HBM3/HBM3E 중 HBM3E 만)."""
        if not text or self._automaton is None:
            return []
        raw: list[LexiconHit] = []
        for end_idx, payload in self._automaton.iter(text):
            etype, eid, surface = payload
            if surface in self._ambiguous:
                continue
            start = end_idx - len(surface) + 1
            raw.append(LexiconHit(
                entity_type=etype, entity_id=eid, surface=surface,
                span_start=start, span_end=end_idx + 1,
            ))
        if not longest_only:
            return raw
        # longest-match dedup: 같은 (entity_type) 안에서 다른 hit 에 완전 포함되는 hit 제거
        raw.sort(key=lambda h: (h.span_start, -h.span_end))
        kept: list[LexiconHit] = []
        for h in raw:
            covered = False
            for k in kept:
                if (h.entity_type == k.entity_type
                        and k.span_start <= h.span_start
                        and h.span_end <= k.span_end
                        and (k.span_end - k.span_start) > (h.span_end - h.span_start)):
                    covered = True
                    break
            if not covered:
                kept.append(h)
        return kept

    def scan_by_type(self, text: str) -> dict[str, list[LexiconHit]]:
        """scan() 결과를 entity_type 별로 분류."""
        result: dict[str, list[LexiconHit]] = {}
        for h in self.scan(text):
            result.setdefault(h.entity_type, []).append(h)
        return result


_MATCHER_CACHE: Optional[Matcher] = None


def build_matcher(reload: bool = False) -> Matcher:
    """모듈 단위 캐시. reload=True 시 강제 재빌드 (yaml 변경 후)."""
    global _MATCHER_CACHE
    if reload or _MATCHER_CACHE is None:
        if reload:
            from polaris.graph.lexicon.loader import invalidate_cache
            invalidate_cache()
        _MATCHER_CACHE = Matcher()
    return _MATCHER_CACHE
