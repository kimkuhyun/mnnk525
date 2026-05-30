"""LLM 추출 jsonl → 정규화 → 링킹 → Neo4j MERGE (P-3.6).

흐름 (per chunk record):
  1. entities → linker.link → product_id / tech_id / corp_code / person_id
     - 사전 hit (Stage 1): :LLMExtracted 라벨 면제 — Org 라벨 보강 (alias_boost)
     - vector ER (Stage 2): :LLMExtracted 라벨 부착
     - unlinked: unlinked_entities.jsonl 에 기록 (linker 가 처리)
  2. Chunk evidence — (Chunk)-[:hasActor]->(Org/Person), (Chunk)-[:hasObject]->(Product/Tech)
  3. relations → reifier.decide_tier → Statement/Relation/Event
  4. ExtractionActivity 1건 (run_id 단위) + wasGeneratedBy 엣지

산출:
  - Neo4j: Statement/Relation/Event/Product/Technology :LLMExtracted MERGE
  - data/4_dbGoldTest/graph_extracts/{run_id}/load_summary.json

사용:
  polaris graph-load-semantic              # 전체 jsonl 적재
  polaris graph-load-semantic --limit 50   # 50 records 만 (sanity)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from polaris.config import DATA_ROOT, OLLAMA_LLM_MODEL
from polaris.graph.common import canonicalize_name, get_active_run_id, hash16
from polaris.graph.extractors import llm_entity, llm_relation
from polaris.graph.linker import EntityLinker, LinkResult
from polaris.graph.merger import Merger
from polaris.graph.reifier import decide_tier, Tier

PIPELINE_VERSION = "polaris-0.3.0+p3.6"


def _outdir(run_id: str) -> Path:
    p = DATA_ROOT / "4_dbGoldTest" / "graph_extracts" / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def compute_prompt_hash() -> str:
    """entity + relation 프롬프트 (system+user+schema) 텍스트 SHA1[:16].

    marker 기반 MD5 와 달리 프롬프트 텍스트가 바뀌면 hash 도 바뀐다 — 추출 재현성용.
    """
    combined = f"{llm_entity.prompt_hash()}|{llm_relation.prompt_hash()}"
    return hashlib.sha1(combined.encode("utf-8")).hexdigest()[:16]


def _build_product_payload(link: LinkResult, source_chunk_id: str,
                            run_id: str) -> dict:
    """LinkResult → CQ_PRODUCT_BASE payload."""
    return {
        "product_id": link.entity_id,
        "name": link.surface, "canonical": link.canonical,
        "category": "other", "aliases": [link.surface],
        "confidence": link.score,
        "extracted_by": "qwen3.5:9b" if link.stage > 1 else "alias_dict_v1",
        "source_chunk_id": source_chunk_id, "run_id": run_id,
    }


def _build_tech_payload(link: LinkResult, source_chunk_id: str,
                          run_id: str) -> dict:
    return {
        "tech_id": link.entity_id,
        "name": link.surface, "canonical": link.canonical,
        "category": "other", "node_size_nm": None,
        "aliases": [link.surface],
        "confidence": link.score,
        "extracted_by": "qwen3.5:9b" if link.stage > 1 else "alias_dict_v1",
        "source_chunk_id": source_chunk_id, "run_id": run_id,
    }


def _process_chunk_record(record: dict, run_id: str,
                            linker: EntityLinker, m: Merger,
                            activity_id: str, stats: dict):
    """record = {chunk_id, entities, relations, meta} → MERGE 호출."""
    cid = record["chunk_id"]

    # 1) entities → 링킹
    linked: list[LinkResult] = []
    new_products: list[dict] = []
    new_techs: list[dict] = []
    actor_org_edges: list[dict] = []
    actor_person_edges: list[dict] = []
    obj_product_edges: list[dict] = []
    obj_tech_edges: list[dict] = []
    obj_place_edges: list[dict] = []

    def _edge(r: LinkResult) -> dict:
        # Merger.CQ_CHUNK_HAS_* 가 ON CREATE 시 사용. canonical 우선, 없으면 surface.
        return {
            "chunk_id": cid, "run_id": run_id,
            "entity_id": r.entity_id,
            "entity_name": r.canonical or r.surface or r.entity_id,
        }

    for e in record.get("entities", []) or []:
        r = linker.link(e.get("text", ""), e.get("type", ""),
                         source_chunk_id=cid)
        if r is None:
            stats["unlinked_entities"] += 1
            continue
        linked.append(r)
        # 신규 Product/Technology — yaml 에 있으면 Stage1 (사전), 없으면 Stage2 (vector)
        if r.entity_type == "Product":
            new_products.append(_build_product_payload(r, cid, run_id))
            obj_product_edges.append(_edge(r))
        elif r.entity_type == "Technology":
            new_techs.append(_build_tech_payload(r, cid, run_id))
            obj_tech_edges.append(_edge(r))
        elif r.entity_type == "Organization":
            actor_org_edges.append(_edge(r))
        elif r.entity_type == "Person":
            actor_person_edges.append(_edge(r))
        elif r.entity_type == "Place":
            obj_place_edges.append(_edge(r))
    stats["entities_linked"] += len(linked)

    # 2) Product / Technology MERGE (사전 hit 은 라벨 면제, vector ER 은 :LLMExtracted)
    if new_products:
        # 일단 모든 Product 는 :LLMExtracted 부착 (사전 매칭이라도 안전)
        # alias yaml 에 있으면 그래도 confidence 1.0 + extracted_by='alias_dict_v1'
        m.product(new_products, llm_extracted=True)
    if new_techs:
        m.technology(new_techs, llm_extracted=True)

    # 3) Chunk evidence (1-hop)
    if (actor_org_edges or actor_person_edges or obj_product_edges
            or obj_tech_edges or obj_place_edges):
        m.chunk_evidence([], actor_org_edges=actor_org_edges,
                          actor_person_edges=actor_person_edges,
                          object_product_edges=obj_product_edges,
                          object_tech_edges=obj_tech_edges,
                          object_place_edges=obj_place_edges)

    # 4) Relations → reifier → Statement/Relation/Event 적재
    by_text: dict[str, LinkResult] = {l.surface: l for l in linked}
    statements: list[dict] = []
    relations: list[dict] = []
    events: list[dict] = []
    event_actor_edges: list[dict] = []
    event_object_edges: list[dict] = []
    generated_by_targets: list[dict] = []

    for r in record.get("relations", []) or []:
        subj_link = by_text.get(r["subject"])
        obj_link = by_text.get(r["object"])
        if not subj_link or not obj_link:
            stats["relations_unlinked"] += 1
            continue
        pred = r["predicate"]
        conf = float(r.get("self_confidence", 0.0))
        valid_from = (r.get("valid_from") or "").strip() or None
        decision = decide_tier(predicate=pred,
                                has_validity=bool(valid_from),
                                has_confidence=True,
                                evidence_count=1, multi_source=False)
        common = {
            "subject_id": subj_link.entity_id,
            "subject_type": subj_link.entity_type,
            "predicate": pred,
            "object_id": obj_link.entity_id,
            "object_type": obj_link.entity_type,
            "confidence": conf,
            "valid_from": valid_from, "valid_to": None,
            "evidence_count": 1,
            "extracted_by": "qwen3.5:9b",
            "source_chunk_id": cid, "run_id": run_id,
        }
        if decision.tier == Tier.STATEMENT:
            sid = hash16("stmt", subj_link.entity_id, pred, obj_link.entity_id, cid)
            statements.append({**common, "statement_id": sid})
            generated_by_targets.append({"target_id": sid, "target_label": "Statement",
                                          "activity_id": activity_id, "run_id": run_id})
            stats["statements"] += 1
        elif decision.tier == Tier.RELATION:
            rid = hash16("rel", pred, subj_link.entity_id, obj_link.entity_id,
                          valid_from or "", cid)
            relations.append({
                **common,
                "rel_id": rid, "type": pred,
                "from_id": subj_link.entity_id, "from_type": subj_link.entity_type,
                "to_id": obj_link.entity_id, "to_type": obj_link.entity_type,
            })
            generated_by_targets.append({"target_id": rid, "target_label": "Relation",
                                          "activity_id": activity_id, "run_id": run_id})
            stats["relations"] += 1
        elif decision.tier == Tier.EVENT:
            eid = hash16("event", pred, subj_link.entity_id, valid_from or "", cid)
            events.append({
                **common,
                "event_id": eid, "event_type": pred,
                "label": f"{subj_link.entity_id} {pred} {obj_link.entity_id}",
                "date": valid_from, "corp_code": subj_link.entity_id
                       if subj_link.entity_type == "Organization" else None,
                "rcept_no": None,
            })
            if subj_link.entity_type == "Organization":
                event_actor_edges.append({
                    "event_id": eid, "run_id": run_id,
                    "actor_id": subj_link.entity_id, "role": "actor"})
            if obj_link.entity_type == "Organization":
                event_actor_edges.append({
                    "event_id": eid, "run_id": run_id,
                    "actor_id": obj_link.entity_id, "role": "target"})
            if obj_link.entity_type == "Product":
                event_object_edges.append({
                    "event_id": eid, "run_id": run_id,
                    "object_id": obj_link.entity_id, "role": "product"})
            generated_by_targets.append({"target_id": eid, "target_label": "Event",
                                          "activity_id": activity_id, "run_id": run_id})
            stats["events"] += 1

    if statements:
        m.statement_with_provenance(statements)
    if relations:
        m.relation_tier(relations)
    if events:
        m.event_with_provenance(events,
                                  actor_org_edges=event_actor_edges or None,
                                  object_product_edges=event_object_edges or None)
    if generated_by_targets:
        m.generated_by(generated_by_targets)


def run_load(*, limit: Optional[int] = None) -> dict:
    run_id = get_active_run_id()
    out = _outdir(run_id)
    jsonl = out / "llm_extracts.jsonl"
    if not jsonl.is_file():
        print(f"[loader] jsonl 없음: {jsonl}")
        return {"records": 0}

    records = []
    with jsonl.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue
    print(f"[loader] jsonl records: {len(records)}")
    if limit:
        records = records[:limit]
        print(f"[loader] --limit {limit} → {len(records)} 처리")

    activity_id = hash16("activity", run_id, "p3.6", OLLAMA_LLM_MODEL)
    activity = {
        "activity_id": activity_id, "run_id": run_id,
        "extractor": "qwen3.5:9b",
        "pipeline_version": PIPELINE_VERSION,
        "prompt_hash": compute_prompt_hash(),
        "model_temp": 0.0,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "ended_at": None,
        "chunks_processed": len(records),
        "entities_extracted": sum(len(r.get("entities", [])) for r in records),
        "relations_extracted": sum(len(r.get("relations", [])) for r in records),
    }

    linker = EntityLinker(run_id=run_id, enable_vector=False)
    print(f"[loader] linker yaml_index: {len(linker._yaml_index)}")

    stats = {
        "records": 0, "entities_linked": 0, "unlinked_entities": 0,
        "relations_unlinked": 0,
        "statements": 0, "relations": 0, "events": 0,
    }

    t0 = time.time()
    with Merger() as m:
        # ExtractionActivity 1건 적재
        m.extraction_activity([activity])
        for i, rec in enumerate(records, 1):
            _process_chunk_record(rec, run_id, linker, m, activity_id, stats)
            stats["records"] += 1
            if i % 50 == 0:
                print(f"  loaded {i}/{len(records)}  "
                       f"ent={stats['entities_linked']} stmt={stats['statements']} "
                       f"rel={stats['relations']} evt={stats['events']}")
        # 활동 종료시간 갱신
        activity["ended_at"] = datetime.now(timezone.utc).isoformat()
        m.extraction_activity([activity])

    elapsed = time.time() - t0
    linked = stats["entities_linked"]
    unlinked = stats["unlinked_entities"]
    linked_ratio = linked / (linked + unlinked) if (linked + unlinked) else 0.0
    stats["linked_ratio"] = round(linked_ratio, 4)

    print(f"\n=== loader_semantic 완료 ({elapsed:.1f}s) ===")
    for k, v in stats.items():
        if k == "linked_ratio":
            print(f"  {k}: {v:.2%}")
        else:
            print(f"  {k}: {v:,}")
    summary_path = out / "load_summary.json"
    summary_path.write_text(json.dumps({
        "elapsed_sec": round(elapsed, 1), "stats": stats,
        "activity_id": activity_id,
        "prompt_hash": compute_prompt_hash(),
        "pipeline_version": PIPELINE_VERSION,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  summary: {summary_path}")
    return stats


def main():
    parser = argparse.ArgumentParser(description="POLARIS 의미 그래프 jsonl → Neo4j (P-3.6)")
    parser.add_argument("--limit", type=int, default=None, help="처리 records 제한 (sanity)")
    args = parser.parse_args()
    rc = 0
    try:
        s = run_load(limit=args.limit)
        if s.get("records", 0) == 0:
            rc = 1
    except KeyboardInterrupt:
        print("\n[loader] 사용자 중단")
        rc = 130
    return rc


if __name__ == "__main__":
    sys.exit(main())
