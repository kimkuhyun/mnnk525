"""검색 결과 의미 그래프 1-hop 컨텍스트 보강 — P-3.8.

흐름:
  1. Qdrant top-k chunk_id 검색 (외부)
  2. 본 모듈 augment_with_graph(chunk_ids) → 의미 그래프 1-hop 컨텍스트 dict
  3. LLM 응답 prompt 에 컨텍스트 첨부 → 출처 강제 인용

T4 화이트리스트 준수: Chunk 1-hop only.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from polaris.config import neo4j_driver
from polaris.graph.common import get_active_run_id

logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)
logging.getLogger("neo4j").setLevel(logging.ERROR)


@dataclass
class ChunkContext:
    chunk_id: str
    actors_org: list[dict] = field(default_factory=list)    # [{corp_code, name}]
    actors_person: list[dict] = field(default_factory=list)
    objects_product: list[dict] = field(default_factory=list)
    objects_tech: list[dict] = field(default_factory=list)
    derived_from: list[dict] = field(default_factory=list)   # FilingDocument/NewsArticle
    statements: list[dict] = field(default_factory=list)     # 이 청크가 evidence 인 statement
    events: list[dict] = field(default_factory=list)


def augment_with_graph(chunk_ids: list[str],
                        run_id: Optional[str] = None) -> dict[str, ChunkContext]:
    """청크 ID 리스트 → 각 청크의 1-hop 의미 그래프 컨텍스트."""
    if not chunk_ids:
        return {}
    run_id = run_id or get_active_run_id()
    result: dict[str, ChunkContext] = {cid: ChunkContext(chunk_id=cid)
                                          for cid in chunk_ids}
    drv = neo4j_driver()
    with drv.session() as s:
        # 1) hasActor → Organization
        for r in s.run("""
            UNWIND $cids AS cid
            MATCH (c:Chunk {chunk_id: cid, run_id: $rid})-[:hasActor]->(o:Organization)
            RETURN cid AS cid, o.corp_code AS cc, o.name AS name
        """, cids=chunk_ids, rid=run_id):
            result[r["cid"]].actors_org.append({"corp_code": r["cc"], "name": r["name"]})

        # 2) hasActor → Person
        for r in s.run("""
            UNWIND $cids AS cid
            MATCH (c:Chunk {chunk_id: cid, run_id: $rid})-[:hasActor]->(p:Person)
            RETURN cid AS cid, p.person_id AS pid, p.name AS name
        """, cids=chunk_ids, rid=run_id):
            result[r["cid"]].actors_person.append({"person_id": r["pid"], "name": r["name"]})

        # 3) hasObject → Product
        for r in s.run("""
            UNWIND $cids AS cid
            MATCH (c:Chunk {chunk_id: cid, run_id: $rid})-[:hasObject]->(p:Product)
            RETURN cid AS cid, p.product_id AS pid, p.name AS name,
                   p.category AS cat
        """, cids=chunk_ids, rid=run_id):
            result[r["cid"]].objects_product.append({
                "product_id": r["pid"], "name": r["name"], "category": r["cat"]})

        # 4) hasObject → Technology
        for r in s.run("""
            UNWIND $cids AS cid
            MATCH (c:Chunk {chunk_id: cid, run_id: $rid})-[:hasObject]->(t:Technology)
            RETURN cid AS cid, t.tech_id AS tid, t.name AS name, t.category AS cat
        """, cids=chunk_ids, rid=run_id):
            result[r["cid"]].objects_tech.append({
                "tech_id": r["tid"], "name": r["name"], "category": r["cat"]})

        # 5) Statement / Event 가 이 청크를 evidence 로 가진 경우
        for r in s.run("""
            UNWIND $cids AS cid
            MATCH (st:Statement {run_id: $rid})-[:wasDerivedFrom]->(c:Chunk {chunk_id: cid, run_id: $rid})
            RETURN cid AS cid, st.subject_id AS subj, st.predicate AS pred,
                   st.object_id AS obj, st.confidence AS conf
        """, cids=chunk_ids, rid=run_id):
            result[r["cid"]].statements.append({
                "subject": r["subj"], "predicate": r["pred"],
                "object": r["obj"], "confidence": r["conf"]})

        for r in s.run("""
            UNWIND $cids AS cid
            MATCH (ev:Event {run_id: $rid})-[:wasDerivedFrom]->(c:Chunk {chunk_id: cid, run_id: $rid})
            RETURN cid AS cid, ev.event_type AS et, ev.label AS label,
                   ev.date AS date
        """, cids=chunk_ids, rid=run_id):
            result[r["cid"]].events.append({
                "event_type": r["et"], "label": r["label"], "date": r["date"]})
    drv.close()
    return result


def render_context_block(ctx: ChunkContext, max_each: int = 5) -> str:
    """LLM 프롬프트에 첨부할 1-hop 컨텍스트 텍스트 블록."""
    lines = [f"[chunk:{ctx.chunk_id}]"]
    if ctx.actors_org:
        names = [f"{o['name']}({o['corp_code']})" for o in ctx.actors_org[:max_each]]
        lines.append(f"  관련 회사: {', '.join(names)}")
    if ctx.actors_person:
        names = [p["name"] for p in ctx.actors_person[:max_each]]
        lines.append(f"  관련 인물: {', '.join(names)}")
    if ctx.objects_product:
        names = [f"{p['name']}({p['category']})" for p in ctx.objects_product[:max_each]]
        lines.append(f"  제품: {', '.join(names)}")
    if ctx.objects_tech:
        names = [f"{t['name']}({t['category']})" for t in ctx.objects_tech[:max_each]]
        lines.append(f"  기술: {', '.join(names)}")
    if ctx.statements:
        for s in ctx.statements[:max_each]:
            lines.append(f"  fact: {s['subject']} -[{s['predicate']}]-> {s['object']} (conf={s['confidence']:.2f})")
    if ctx.events:
        for e in ctx.events[:max_each]:
            lines.append(f"  event: {e['event_type']} @ {e['date']} — {e['label']}")
    return "\n".join(lines)
