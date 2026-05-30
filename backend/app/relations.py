"""관계 predicate → 6그룹 매핑 (프론트 src/lib/relations.ts 의 백엔드 미러, SSOT)."""
from __future__ import annotations

# Neo4j 관계타입 → 화면 6그룹
PREDICATE_TO_GROUP: dict[str, str] = {
    "SUPPLIES": "supply", "CUSTOMER_OF": "supply",
    "COMPETES_WITH": "compete",
    "PARTNERS_WITH": "partner", "JV_WITH": "partner", "LICENSES": "partner",
    "INVESTS_IN": "invest", "ACQUIRES": "invest",
    "IS_SUBSIDIARY_OF": "govern", "IS_MAJOR_SHAREHOLDER_OF": "govern", "AFFILIATED_WITH": "govern",
    "LITIGATION": "dispute",
}

# 회사↔회사 그래프에 그릴 관계타입 (인물 EXECUTIVE_OF, 제품 DEVELOPS 는 그래프 제외 → 패널)
COMPANY_REL_TYPES: list[str] = list(PREDICATE_TO_GROUP)

# 방향성 있는 관계 (화살표 표시)
DIRECTED: set[str] = {
    "SUPPLIES", "CUSTOMER_OF", "INVESTS_IN", "ACQUIRES",
    "IS_SUBSIDIARY_OF", "IS_MAJOR_SHAREHOLDER_OF",
}

# 그룹 → predicate 목록 (근거 조회 시 그룹으로 역매핑)
GROUP_TO_PREDICATES: dict[str, list[str]] = {}
for _p, _g in PREDICATE_TO_GROUP.items():
    GROUP_TO_PREDICATES.setdefault(_g, []).append(_p)

# 1차 시드 3사 (노드 강조용)
SEED_CORPS: dict[str, str] = {
    "00126380": "삼성전자",
    "00164779": "SK하이닉스",
    "00161383": "한미반도체",
}
