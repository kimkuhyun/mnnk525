"""Reification 결정 — 4조건 OR 룰 → Tier 1/2/3.

설계 03_스키마_저장소.md §A-5 차용.

Tier 1 — 단순 엣지: 4조건 모두 X (= 사전 매칭 등 결정론 결과만)
Tier 2 — Statement 노드: confidence/validity/evidence_count/multi_source 중 1+ → reify
Tier 2.5 — Relation 노드 (Statement 보다 풍부): 같은 fact 다중 청크 evidence
Tier 3 — Event 노드 (SEM): actor + object + time 동시 (M&A, 출시 등)

LLM 추출은 항상 confidence 있음 → Tier 2/3 reify.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Tier(int, Enum):
    SIMPLE_EDGE = 1
    STATEMENT = 2
    RELATION = 25       # Tier 2.5 (보다 풍부한 엣지 노드)
    EVENT = 3


# Event 후보 predicate (시간 + actor 강함)
EVENT_PREDICATES = {"MERGED_WITH", "INVESTED_IN"}

# Statement / Relation 분류 — Tier 2.5 트리거 조건
RELATION_THRESHOLD_EVIDENCE = 2   # evidence_count ≥ 2 → Relation reify


@dataclass
class TierDecision:
    tier: Tier
    reason: str


def decide_tier(*, predicate: str, has_validity: bool, has_confidence: bool,
                evidence_count: int = 1, multi_source: bool = False) -> TierDecision:
    """4조건 OR 룰 + Event 분기."""
    # Event 우선 (M&A, 투자)
    if predicate in EVENT_PREDICATES:
        return TierDecision(Tier.EVENT, f"predicate={predicate} → Event")

    triggers = []
    if has_validity: triggers.append("validity")
    if has_confidence: triggers.append("confidence")
    if evidence_count > 1: triggers.append(f"evidence={evidence_count}")
    if multi_source: triggers.append("multi_source")

    if not triggers:
        return TierDecision(Tier.SIMPLE_EDGE, "no triggers → Tier1 (단순 엣지)")

    # 다중 트리거 또는 evidence 강함 → Relation (Tier 2.5)
    if evidence_count >= RELATION_THRESHOLD_EVIDENCE or multi_source:
        return TierDecision(Tier.RELATION,
                             f"{'+'.join(triggers)} → Relation (Tier 2.5)")

    # 기본 — Statement
    return TierDecision(Tier.STATEMENT,
                         f"{'+'.join(triggers)} → Statement (Tier 2)")
