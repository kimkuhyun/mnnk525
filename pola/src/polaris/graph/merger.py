"""Neo4j MERGE Cypher 패턴 모음 — P-3.2.

설계 03_스키마_저장소.md §A 4계층 + 21 엣지 + Reification 3-tier 차용.
모든 MERGE 는 idempotent + run-scoped + :LLMExtracted 라벨 격리.

8 패턴:
  1. merge_organization_alias_boost  — 기존 Org 에 alias 보강 (사전·LLM 학습 결과)
  2. merge_product                   — Product :LLMExtracted MERGE
  3. merge_technology                — Technology :LLMExtracted MERGE
  4. merge_chunk_evidence            — Chunk 노드 + 1-hop hasActor/hasObject (T4 lookup-only)
  5. merge_statement_with_provenance — Statement + wasDerivedFrom + wasGeneratedBy
  6. merge_event_with_provenance     — Event + hasActor/hasObject + PROV
  7. merge_relation_tier             — Relation Tier 1/2/3 분기 (4조건 OR)
  8. merge_extraction_activity       — ExtractionActivity (LLM 호출 단위)

사용:
  from polaris.graph.merger import Merger
  with Merger() as m:
      m.product({...}, run_id, llm_extracted=True)
      m.chunk_evidence({...}, run_id)
"""
from __future__ import annotations

import logging
from typing import Optional

from polaris.config import neo4j_driver

# Neo4j unknown label notification silence
logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)
logging.getLogger("neo4j").setLevel(logging.ERROR)


# ────── Cypher 템플릿 (UNWIND 패턴) ──────────

CQ_ORG_ALIAS_BOOST = """
UNWIND $rows AS r
MATCH (o:Organization {corp_code: r.corp_code})
SET o.aliases = [a IN coalesce(o.aliases, []) + r.new_aliases
                 WHERE a IS NOT NULL] ,
    o.last_updated_run_id = r.run_id
"""

# Product / Technology — 전역 entity. 사전 매칭 (extracted_by='alias_dict_v1') 은
# 라벨 면제, LLM 추출 (qwen3.5:9b) 만 :LLMExtracted 부착.
CQ_PRODUCT_BASE = """
UNWIND $rows AS r
MERGE (p:Product {product_id: r.product_id})
  ON CREATE SET p.first_seen_run_id = r.run_id
SET p.name = r.name, p.canonical = r.canonical,
    p.category = r.category,
    p.aliases = coalesce(p.aliases, []) + [a IN r.aliases
                                            WHERE NOT a IN coalesce(p.aliases, [])],
    p.confidence = r.confidence,
    p.extracted_by = r.extracted_by,
    p.source_chunk_id = r.source_chunk_id,
    p.last_updated_run_id = r.run_id
"""

CQ_PRODUCT_LLM_LABEL = """
UNWIND $rows AS r
MATCH (p:Product {product_id: r.product_id})
SET p:LLMExtracted
"""

CQ_TECH_BASE = """
UNWIND $rows AS r
MERGE (t:Technology {tech_id: r.tech_id})
  ON CREATE SET t.first_seen_run_id = r.run_id
SET t.name = r.name, t.canonical = r.canonical,
    t.category = r.category,
    t.node_size_nm = r.node_size_nm,
    t.aliases = coalesce(t.aliases, []) + [a IN r.aliases
                                            WHERE NOT a IN coalesce(t.aliases, [])],
    t.confidence = r.confidence,
    t.extracted_by = r.extracted_by,
    t.source_chunk_id = r.source_chunk_id,
    t.last_updated_run_id = r.run_id
"""

CQ_TECH_LLM_LABEL = """
UNWIND $rows AS r
MATCH (t:Technology {tech_id: r.tech_id})
SET t:LLMExtracted
"""

# Chunk 노드 — T4 lookup-only (1-hop, traverse 금지)
CQ_CHUNK_NODE = """
UNWIND $rows AS r
MERGE (c:Chunk {chunk_id: r.chunk_id, run_id: r.run_id})
  ON CREATE SET c.first_seen_run_id = r.run_id
SET c.corp_code = r.corp_code,
    c.rcept_no = r.rcept_no,
    c.chunk_type = r.chunk_type,
    c.anchor = r.anchor,
    c.embedding_text_hash = r.embedding_text_hash,
    c.ingest_status = r.ingest_status,
    c.last_updated_run_id = r.run_id
"""

# Chunk → hasActor → Organization/Person (사전 hit 결과)
# MERGE 패턴: 결정론 노드(8자리 corp_code)는 기존 매칭, 외부 LLM 노드(X*)는 자동 생성 + :LLMExtracted 격리.
CQ_CHUNK_HAS_ACTOR_ORG = """
UNWIND $rows AS r
MATCH (c:Chunk {chunk_id: r.chunk_id, run_id: r.run_id})
MERGE (o:Organization {corp_code: r.entity_id})
  ON CREATE SET o:LLMExtracted, o.first_seen_run_id = r.run_id,
                o.name = coalesce(r.entity_name, r.entity_id)
MERGE (c)-[h:hasActor]->(o)
  ON CREATE SET h.first_seen_run_id = r.run_id
SET h.run_id = r.run_id, h.last_updated_run_id = r.run_id
"""

CQ_CHUNK_HAS_ACTOR_PERSON = """
UNWIND $rows AS r
MATCH (c:Chunk {chunk_id: r.chunk_id, run_id: r.run_id})
MERGE (p:Person {person_id: r.entity_id})
  ON CREATE SET p:LLMExtracted, p.first_seen_run_id = r.run_id,
                p.name = coalesce(r.entity_name, r.entity_id)
MERGE (c)-[h:hasActor]->(p)
  ON CREATE SET h.first_seen_run_id = r.run_id
SET h.run_id = r.run_id, h.last_updated_run_id = r.run_id
"""

# Chunk → hasObject → Product/Technology/Place
CQ_CHUNK_HAS_OBJECT_PRODUCT = """
UNWIND $rows AS r
MATCH (c:Chunk {chunk_id: r.chunk_id, run_id: r.run_id})
MERGE (p:Product {product_id: r.entity_id})
  ON CREATE SET p:LLMExtracted, p.first_seen_run_id = r.run_id,
                p.name = coalesce(r.entity_name, r.entity_id)
MERGE (c)-[h:hasObject]->(p)
  ON CREATE SET h.first_seen_run_id = r.run_id
SET h.run_id = r.run_id, h.last_updated_run_id = r.run_id
"""

CQ_CHUNK_HAS_OBJECT_TECH = """
UNWIND $rows AS r
MATCH (c:Chunk {chunk_id: r.chunk_id, run_id: r.run_id})
MERGE (t:Technology {tech_id: r.entity_id})
  ON CREATE SET t:LLMExtracted, t.first_seen_run_id = r.run_id,
                t.name = coalesce(r.entity_name, r.entity_id)
MERGE (c)-[h:hasObject]->(t)
  ON CREATE SET h.first_seen_run_id = r.run_id
SET h.run_id = r.run_id, h.last_updated_run_id = r.run_id
"""

# Place 도 evidence edge — hasObject 로 통일 (의미적으로 actor 보단 object)
CQ_CHUNK_HAS_OBJECT_PLACE = """
UNWIND $rows AS r
MATCH (c:Chunk {chunk_id: r.chunk_id, run_id: r.run_id})
MERGE (pl:Place {iso_code: r.entity_id})
  ON CREATE SET pl:LLMExtracted, pl.first_seen_run_id = r.run_id,
                pl.name = coalesce(r.entity_name, r.entity_id)
MERGE (c)-[h:hasObject]->(pl)
  ON CREATE SET h.first_seen_run_id = r.run_id
SET h.run_id = r.run_id, h.last_updated_run_id = r.run_id
"""

# Statement (Tier 2 reification) + PROV-O (wasDerivedFrom + wasGeneratedBy)
CQ_STATEMENT_BASE = """
UNWIND $rows AS r
MERGE (s:Statement:LLMExtracted {statement_id: r.statement_id, run_id: r.run_id})
  ON CREATE SET s.first_seen_run_id = r.run_id
SET s.subject_id = r.subject_id, s.subject_type = r.subject_type,
    s.predicate = r.predicate,
    s.object_id = r.object_id, s.object_type = r.object_type,
    s.confidence = r.confidence,
    s.evidence_count = r.evidence_count,
    s.valid_from = r.valid_from, s.valid_to = r.valid_to,
    s.extracted_by = r.extracted_by,
    s.source_chunk_id = r.source_chunk_id,
    s.last_updated_run_id = r.run_id
"""

CQ_STATEMENT_PROV = """
UNWIND $rows AS r
MATCH (s:Statement {statement_id: r.statement_id, run_id: r.run_id})
MATCH (c:Chunk {chunk_id: r.source_chunk_id, run_id: r.run_id})
MERGE (s)-[wd:wasDerivedFrom]->(c)
  ON CREATE SET wd.first_seen_run_id = r.run_id
SET wd.run_id = r.run_id
"""

# Event (Tier 3 reification) + hasActor + hasObject + PROV
CQ_EVENT_BASE = """
UNWIND $rows AS r
MERGE (ev:Event:LLMExtracted {event_id: r.event_id, run_id: r.run_id})
  ON CREATE SET ev.first_seen_run_id = r.run_id
SET ev.event_type = r.event_type, ev.label = r.label,
    ev.date = r.date, ev.corp_code = r.corp_code,
    ev.rcept_no = r.rcept_no,
    ev.confidence = r.confidence,
    ev.evidence_count = r.evidence_count,
    ev.valid_from = r.valid_from, ev.valid_to = r.valid_to,
    ev.extracted_by = r.extracted_by,
    ev.source_chunk_id = r.source_chunk_id,
    ev.last_updated_run_id = r.run_id
"""

CQ_EVENT_HAS_ACTOR_ORG = """
UNWIND $rows AS r
MATCH (ev:Event {event_id: r.event_id, run_id: r.run_id})
MATCH (o:Organization {corp_code: r.actor_id})
MERGE (ev)-[ha:hasActor {role: r.role}]->(o)
  ON CREATE SET ha.first_seen_run_id = r.run_id
SET ha.run_id = r.run_id
"""

CQ_EVENT_HAS_OBJECT_PRODUCT = """
UNWIND $rows AS r
MATCH (ev:Event {event_id: r.event_id, run_id: r.run_id})
MATCH (p:Product {product_id: r.object_id})
MERGE (ev)-[ho:hasObject {role: r.role}]->(p)
  ON CREATE SET ho.first_seen_run_id = r.run_id
SET ho.run_id = r.run_id
"""

# ADR 011 — CQ_EVENT_PROV 강화:
# 1) source_chunk_id null 행은 별도 카운터 (skip 이유 분류)
# 2) Chunk run_id 강제 매칭을 ANY-run lookup 으로 완화 (Chunk 는 unique chunk_id 라 같은 본문)
# 3) MATCH → OPTIONAL MATCH 로 변경해서 RETURN count() 로 적재 통계 가능
CQ_EVENT_PROV = """
UNWIND $rows AS r
WITH r WHERE r.source_chunk_id IS NOT NULL AND r.source_chunk_id <> ''
MATCH (ev:Event {event_id: r.event_id, run_id: r.run_id})
OPTIONAL MATCH (c:Chunk {chunk_id: r.source_chunk_id})
WITH ev, c, r WHERE c IS NOT NULL
MERGE (ev)-[wd:wasDerivedFrom]->(c)
  ON CREATE SET wd.first_seen_run_id = r.run_id
SET wd.run_id = r.run_id
RETURN count(wd) AS linked
"""

# ADR 011 — Statement PROV 도 같은 패턴 (74% orphan)
CQ_STATEMENT_PROV_V2 = """
UNWIND $rows AS r
WITH r WHERE r.source_chunk_id IS NOT NULL AND r.source_chunk_id <> ''
MATCH (s:Statement {statement_id: r.statement_id, run_id: r.run_id})
OPTIONAL MATCH (c:Chunk {chunk_id: r.source_chunk_id})
WITH s, c, r WHERE c IS NOT NULL
MERGE (s)-[wd:wasDerivedFrom]->(c)
  ON CREATE SET wd.first_seen_run_id = r.run_id
SET wd.run_id = r.run_id
RETURN count(wd) AS linked
"""

# Relation Tier 2.5 — Statement 보다 풍부 (valid_from + conf + multi_source 중 다수)
# 노드 자체로 reify (Tier 1 단순 엣지가 아닌 케이스)
CQ_RELATION_BASE = """
UNWIND $rows AS r
MERGE (rel:Relation:LLMExtracted {rel_id: r.rel_id, run_id: r.run_id})
  ON CREATE SET rel.first_seen_run_id = r.run_id
SET rel.type = r.type,
    rel.from_id = r.from_id, rel.from_type = r.from_type,
    rel.to_id = r.to_id, rel.to_type = r.to_type,
    rel.confidence = r.confidence,
    rel.evidence_count = r.evidence_count,
    rel.valid_from = r.valid_from, rel.valid_to = r.valid_to,
    rel.extracted_by = r.extracted_by,
    rel.source_chunk_id = r.source_chunk_id,
    rel.last_updated_run_id = r.run_id
"""

# ExtractionActivity (PROV-O) — LLM 호출 단위
CQ_EXTRACTION_ACTIVITY = """
UNWIND $rows AS r
MERGE (a:ExtractionActivity {activity_id: r.activity_id, run_id: r.run_id})
  ON CREATE SET a.first_seen_run_id = r.run_id
SET a.extractor = r.extractor,
    a.pipeline_version = r.pipeline_version,
    a.prompt_hash = r.prompt_hash,
    a.model_temp = r.model_temp,
    a.started_at = r.started_at,
    a.ended_at = r.ended_at,
    a.chunks_processed = r.chunks_processed,
    a.entities_extracted = r.entities_extracted,
    a.relations_extracted = r.relations_extracted,
    a.last_updated_run_id = r.run_id
"""

# Statement / Event / Relation → wasGeneratedBy → ExtractionActivity
CQ_GENERATED_BY = """
UNWIND $rows AS r
MATCH (a:ExtractionActivity {activity_id: r.activity_id, run_id: r.run_id})
CALL {
  WITH r, a
  OPTIONAL MATCH (s:Statement {statement_id: r.target_id, run_id: r.run_id})
  WHERE r.target_label = 'Statement'
  FOREACH (_ IN CASE WHEN s IS NULL THEN [] ELSE [1] END |
    MERGE (s)-[wg:wasGeneratedBy]->(a)
    ON CREATE SET wg.run_id = r.run_id
  )
}
CALL {
  WITH r, a
  OPTIONAL MATCH (ev:Event {event_id: r.target_id, run_id: r.run_id})
  WHERE r.target_label = 'Event'
  FOREACH (_ IN CASE WHEN ev IS NULL THEN [] ELSE [1] END |
    MERGE (ev)-[wg:wasGeneratedBy]->(a)
    ON CREATE SET wg.run_id = r.run_id
  )
}
CALL {
  WITH r, a
  OPTIONAL MATCH (rel:Relation {rel_id: r.target_id, run_id: r.run_id})
  WHERE r.target_label = 'Relation'
  FOREACH (_ IN CASE WHEN rel IS NULL THEN [] ELSE [1] END |
    MERGE (rel)-[wg:wasGeneratedBy]->(a)
    ON CREATE SET wg.run_id = r.run_id
  )
}
"""


class Merger:
    """Neo4j MERGE 컨텍스트. with 블록 안에서 8 패턴 메서드 호출."""

    BATCH = 500

    def __init__(self):
        self.drv = None
        self.s = None

    def __enter__(self):
        self.drv = neo4j_driver()
        self.s = self.drv.session()
        return self

    def __exit__(self, *exc):
        if self.s: self.s.close()
        if self.drv: self.drv.close()

    def _batch(self, rows: list[dict]):
        for i in range(0, len(rows), self.BATCH):
            yield rows[i:i + self.BATCH]

    # ── 1 ──
    def org_alias_boost(self, rows: list[dict]) -> None:
        """rows: [{corp_code, new_aliases: [...], run_id}, ...]"""
        for b in self._batch(rows):
            self.s.run(CQ_ORG_ALIAS_BOOST, rows=b)

    # ── 2 ──
    def product(self, rows: list[dict], *, llm_extracted: bool = False) -> None:
        """rows: [{product_id, name, canonical, category, aliases, confidence,
                  extracted_by, source_chunk_id, run_id}, ...]"""
        for b in self._batch(rows):
            self.s.run(CQ_PRODUCT_BASE, rows=b)
            if llm_extracted:
                self.s.run(CQ_PRODUCT_LLM_LABEL, rows=b)

    # ── 3 ──
    def technology(self, rows: list[dict], *, llm_extracted: bool = False) -> None:
        for b in self._batch(rows):
            self.s.run(CQ_TECH_BASE, rows=b)
            if llm_extracted:
                self.s.run(CQ_TECH_LLM_LABEL, rows=b)

    # ── 4 ──
    def chunk_evidence(self, chunks: list[dict],
                       actor_org_edges: Optional[list[dict]] = None,
                       actor_person_edges: Optional[list[dict]] = None,
                       object_product_edges: Optional[list[dict]] = None,
                       object_tech_edges: Optional[list[dict]] = None,
                       object_place_edges: Optional[list[dict]] = None) -> None:
        """T4 Chunk 노드 + 1-hop evidence 엣지. 다단 hop 금지."""
        for b in self._batch(chunks):
            self.s.run(CQ_CHUNK_NODE, rows=b)
        for edges, cq in [
            (actor_org_edges, CQ_CHUNK_HAS_ACTOR_ORG),
            (actor_person_edges, CQ_CHUNK_HAS_ACTOR_PERSON),
            (object_product_edges, CQ_CHUNK_HAS_OBJECT_PRODUCT),
            (object_tech_edges, CQ_CHUNK_HAS_OBJECT_TECH),
            (object_place_edges, CQ_CHUNK_HAS_OBJECT_PLACE),
        ]:
            if not edges:
                continue
            for b in self._batch(edges):
                self.s.run(cq, rows=b)

    # ── 5 ──
    def statement_with_provenance(self, rows: list[dict]) -> None:
        """Statement + wasDerivedFrom (Chunk). wasGeneratedBy 는 generated_by().

        ADR 011: source_chunk_id null / Chunk 미존재를 counter 로 추적.
        """
        attempted = 0
        skipped_null = 0
        linked = 0
        for b in self._batch(rows):
            self.s.run(CQ_STATEMENT_BASE, rows=b)
            for row in b:
                attempted += 1
                if not row.get("source_chunk_id"):
                    skipped_null += 1
            # V2: skipped null 행은 WITH WHERE 로 자동 제외, 결과의 linked 카운트 집계
            res = self.s.run(CQ_STATEMENT_PROV_V2, rows=b)
            for r in res:
                linked += r.get("linked", 0) or 0
        import sys
        print(f"[merger] Statement PROV — attempted={attempted} "
              f"skipped_null={skipped_null} linked={linked} "
              f"orphan_estimate={attempted - skipped_null - linked}",
              file=sys.stderr)

    # ── 6 ──
    def event_with_provenance(self, events: list[dict],
                              actor_org_edges: Optional[list[dict]] = None,
                              object_product_edges: Optional[list[dict]] = None) -> None:
        """ADR 011: Event PROV 적재 통계 출력."""
        attempted = 0
        skipped_null = 0
        linked = 0
        for b in self._batch(events):
            self.s.run(CQ_EVENT_BASE, rows=b)
            for row in b:
                attempted += 1
                if not row.get("source_chunk_id"):
                    skipped_null += 1
            res = self.s.run(CQ_EVENT_PROV, rows=b)
            for r in res:
                linked += r.get("linked", 0) or 0
        import sys
        print(f"[merger] Event PROV — attempted={attempted} "
              f"skipped_null={skipped_null} linked={linked} "
              f"orphan_estimate={attempted - skipped_null - linked}",
              file=sys.stderr)
        for edges, cq in [
            (actor_org_edges, CQ_EVENT_HAS_ACTOR_ORG),
            (object_product_edges, CQ_EVENT_HAS_OBJECT_PRODUCT),
        ]:
            if not edges:
                continue
            for b in self._batch(edges):
                self.s.run(cq, rows=b)

    # ── 7 ──
    def relation_tier(self, rows: list[dict]) -> None:
        """Tier 2.5 Relation 노드 적재. reifier 가 Tier 결정 후 호출."""
        for b in self._batch(rows):
            self.s.run(CQ_RELATION_BASE, rows=b)

    # ── 8 ──
    def extraction_activity(self, rows: list[dict]) -> None:
        for b in self._batch(rows):
            self.s.run(CQ_EXTRACTION_ACTIVITY, rows=b)

    def generated_by(self, rows: list[dict]) -> None:
        """PROV-O wasGeneratedBy 엣지 (Statement/Event/Relation → ExtractionActivity).
        rows: [{activity_id, target_id, target_label, run_id}, ...]"""
        for b in self._batch(rows):
            self.s.run(CQ_GENERATED_BY, rows=b)
