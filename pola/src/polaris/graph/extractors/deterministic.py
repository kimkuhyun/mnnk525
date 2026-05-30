"""결정론 추출 — 사전 hit 만으로 만들 수 있는 노드/엣지.

LLM 안 쓰고 사전 + 본문 hit 위치만으로:
  1. (Chunk)-[:hasActor]->(Organization|Person)   — 사전 hit 결과 1-hop evidence
  2. (Chunk)-[:hasObject]->(Product|Technology)   — 동일
  3. (Org)-[:PRODUCES]->(Product) 후보             — 같은 청크에 Org + Product 동시 hit
  4. (Org)-[:USES_TECH]->(Technology) 후보         — 같은 청크에 Org + Tech 동시 hit

신뢰도: 1.0 (사전 매칭). :LLMExtracted 라벨 면제.
이건 후보일 뿐 — Tier 1 단순 엣지로 적재 또는 LLM 검증 후 confidence 조정 가능.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from polaris.graph.lexicon import LexiconHit, Matcher


@dataclass
class DeterministicHit:
    """청크 단위 결정론 추출 결과."""
    chunk_id: str
    chunk_run_id: str
    # 1-hop evidence (Chunk→entity)
    actors_org: list[str] = field(default_factory=list)        # corp_code 리스트
    actors_person: list[str] = field(default_factory=list)     # person_id 리스트
    objects_product: list[str] = field(default_factory=list)   # product_id 리스트
    objects_tech: list[str] = field(default_factory=list)      # tech_id 리스트
    # 결정론 관계 후보 (Tier 1 단순 엣지 후보)
    produces_candidates: list[dict] = field(default_factory=list)   # [{org, product}]
    uses_tech_candidates: list[dict] = field(default_factory=list)  # [{org, tech}]


def extract_deterministic(chunk_id: str, chunk_run_id: str,
                           text: str, matcher: Matcher) -> Optional[DeterministicHit]:
    """본문 → DeterministicHit. entity hit 0 이면 None."""
    hits = matcher.scan(text)
    if not hits:
        return None
    by_type: dict[str, list[LexiconHit]] = {}
    for h in hits:
        by_type.setdefault(h.entity_type, []).append(h)

    out = DeterministicHit(chunk_id=chunk_id, chunk_run_id=chunk_run_id)

    # 1-hop evidence — entity_type 별 unique entity_id
    out.actors_org = sorted({h.entity_id for h in by_type.get("Organization", [])})
    out.actors_person = sorted({h.entity_id for h in by_type.get("Person", [])})
    out.objects_product = sorted({h.entity_id for h in by_type.get("Product", [])})
    out.objects_tech = sorted({h.entity_id for h in by_type.get("Technology", [])})

    # 결정론 관계 후보 (cross product — Org × Product, Org × Tech)
    for org_cc in out.actors_org:
        for pid in out.objects_product:
            out.produces_candidates.append({"org": org_cc, "product": pid})
        for tid in out.objects_tech:
            out.uses_tech_candidates.append({"org": org_cc, "tech": tid})

    return out
