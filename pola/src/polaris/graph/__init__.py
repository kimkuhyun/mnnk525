"""의미·관계 그래프 영역 추출기.

정형 영역(FinMetric) 외, DART raw json + FTC XML 에서 결정론적으로
Person/EXECUTIVE_OF, IS_MAJOR_SHAREHOLDER_OF, INVESTS_IN/IS_SUBSIDIARY,
BusinessGroup/AFFILIATED_WITH, Event/wasDerivedFrom 노드·엣지 추출 후
Neo4j MERGE (idempotent, run-scoped).

LLM 사용 X — Phase 3 의미 그래프(LLMExtracted)와 라벨 격리.
"""
