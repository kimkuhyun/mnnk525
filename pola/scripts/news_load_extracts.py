"""뉴스 Claude-direct 추출(llm_extracts.jsonl) → Neo4j 의미 엣지 적재.

전제: 뉴스 Chunk 노드가 이미 존재(news_graphrag_build.py chunk-nodes).
파이프라인 재사용: linker(별칭→ID) + reifier(tier) + merger(MERGE+PROV).
(Chunk)-[:hasActor/hasObject]->entity, Statement/Event :LLMExtracted 생성.

입력: data/4_dbGoldTest/news_bench/parts/extract_b*.jsonl (합쳐서)
"""
from __future__ import annotations
import glob
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from polaris.graph.linker import EntityLinker, LinkResult
from polaris.graph.merger import Merger
from polaris.graph.reifier import decide_tier, Tier
from polaris.graph.common import hash16

RUN_ID = "20260528_0808_01"
PARTS = Path("data/4_dbGoldTest/news_bench/parts")
import hashlib


def _sha10(t): return hashlib.sha1(t.encode("utf-8")).hexdigest()[:10].upper()
def _synth(et, c):
    p = {"Organization": "XCLAUDE_", "Person": "PCLAUDE_", "Product": "PRCLAUDE_",
         "Technology": "TCLAUDE_", "Place": "PLCLAUDE_"}.get(et, "ECLAUDE_")
    return p + _sha10(c)


def _link(linker, ent, cid):
    s = ent.get("text", ""); et = ent.get("type", "")
    cn = ent.get("canonical") or s
    if not s or not et:
        return None
    r = linker.link(s, et, source_chunk_id=cid)
    if r:
        return r
    if cn and cn != s:
        r = linker.link(cn, et, source_chunk_id=cid)
        if r:
            return LinkResult(r.entity_id, r.entity_type, r.score, r.stage, s, cn)
    return LinkResult(_synth(et, cn), et, 0.8, 4, s, cn)


def main():
    files = sorted(glob.glob(str(PARTS / "extract_b*.jsonl")))
    records = []
    for f in files:
        for line in Path(f).read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    print(f"[news-load] extract files: {len(files)} | records: {len(records)}")

    aid = hash16("activity", RUN_ID, "claude-news")
    activity = {
        "activity_id": aid, "run_id": RUN_ID, "extractor": "claude-direct-news",
        "pipeline_version": "polaris-claude-direct/0.1", "prompt_hash": "manual",
        "model_temp": 0.0, "started_at": datetime.now(timezone.utc).isoformat(),
        "ended_at": None, "chunks_processed": len(records),
        "entities_extracted": sum(len(r.get("entities", [])) for r in records),
        "relations_extracted": sum(len(r.get("relations", [])) for r in records),
    }
    linker = EntityLinker(run_id=RUN_ID, enable_vector=True)
    stats = {"records": 0, "ent_yaml": 0, "ent_vec": 0, "ent_syn": 0, "stmt": 0, "evt": 0}
    t0 = time.time()
    with Merger() as m:
        m.extraction_activity([activity])
        for i, rec in enumerate(records, 1):
            cid = rec["chunk_id"]
            entities = rec.get("entities") or []
            rels = rec.get("relations") or []
            evts = rec.get("events") or []
            if not entities and not rels and not evts:
                stats["records"] += 1; continue
            new_products, new_techs = [], []
            ae_org, ae_per, oe_prod, oe_tech, oe_place = [], [], [], [], []
            by_text = {}
            for e in entities:
                r = _link(linker, e, cid)
                if not r:
                    continue
                by_text[e.get("text", "")] = r
                if r.stage == 1: stats["ent_yaml"] += 1
                elif r.stage == 2: stats["ent_vec"] += 1
                else: stats["ent_syn"] += 1
                edge = {"chunk_id": cid, "run_id": RUN_ID, "entity_id": r.entity_id,
                        "entity_name": r.canonical or r.surface or r.entity_id}
                if r.entity_type == "Product":
                    new_products.append({"product_id": r.entity_id, "name": r.canonical or r.surface,
                        "canonical": r.canonical or r.surface, "category": "other",
                        "aliases": [r.surface] if r.surface != r.canonical else [],
                        "confidence": r.score, "extracted_by": "claude-direct" if r.stage == 4 else "alias_dict_v1",
                        "source_chunk_id": cid, "run_id": RUN_ID})
                    oe_prod.append(edge)
                elif r.entity_type == "Technology":
                    new_techs.append({"tech_id": r.entity_id, "name": r.canonical or r.surface,
                        "canonical": r.canonical or r.surface, "category": "other", "node_size_nm": None,
                        "aliases": [r.surface] if r.surface != r.canonical else [],
                        "confidence": r.score, "extracted_by": "claude-direct" if r.stage == 4 else "alias_dict_v1",
                        "source_chunk_id": cid, "run_id": RUN_ID})
                    oe_tech.append(edge)
                elif r.entity_type == "Organization": ae_org.append(edge)
                elif r.entity_type == "Person": ae_per.append(edge)
                elif r.entity_type == "Place": oe_place.append(edge)
            if new_products: m.product(new_products, llm_extracted=True)
            if new_techs: m.technology(new_techs, llm_extracted=True)
            if (ae_org or ae_per or oe_prod or oe_tech or oe_place):
                m.chunk_evidence([], actor_org_edges=ae_org, actor_person_edges=ae_per,
                                 object_product_edges=oe_prod, object_tech_edges=oe_tech,
                                 object_place_edges=oe_place)
            statements, events, event_ae, event_oe, gb = [], [], [], [], []
            for r in rels:
                sl = by_text.get(r["subject"]); ol = by_text.get(r["object"])
                if not sl:
                    sl = LinkResult(_synth("Organization", r["subject"]), "Organization", 0.7, 4, r["subject"], r["subject"])
                if not ol:
                    ol = LinkResult(_synth("Organization", r["object"]), "Organization", 0.7, 4, r["object"], r["object"])
                pred = r["predicate"]; conf = float(r.get("self_confidence", 0.9))
                d = decide_tier(predicate=pred, has_validity=False, has_confidence=True, evidence_count=1, multi_source=False)
                common = {"subject_id": sl.entity_id, "subject_type": sl.entity_type, "predicate": pred,
                          "object_id": ol.entity_id, "object_type": ol.entity_type, "confidence": conf,
                          "valid_from": None, "valid_to": None, "evidence_count": 1,
                          "extracted_by": "claude-direct", "source_chunk_id": cid, "run_id": RUN_ID}
                if d.tier == Tier.EVENT:
                    eid = hash16("event", pred, sl.entity_id, "", cid)
                    events.append({**common, "event_id": eid, "event_type": pred,
                                   "label": f"{sl.canonical} {pred} {ol.canonical}", "date": None,
                                   "corp_code": sl.entity_id if sl.entity_type == "Organization" else None, "rcept_no": None})
                    if sl.entity_type == "Organization":
                        event_ae.append({"event_id": eid, "run_id": RUN_ID, "actor_id": sl.entity_id, "role": "actor"})
                    if ol.entity_type == "Product":
                        event_oe.append({"event_id": eid, "run_id": RUN_ID, "object_id": ol.entity_id, "role": "product"})
                    gb.append({"target_id": eid, "target_label": "Event", "activity_id": aid, "run_id": RUN_ID})
                    stats["evt"] += 1
                else:
                    sid = hash16("stmt", sl.entity_id, pred, ol.entity_id, cid)
                    statements.append({**common, "statement_id": sid})
                    gb.append({"target_id": sid, "target_label": "Statement", "activity_id": aid, "run_id": RUN_ID})
                    stats["stmt"] += 1
            for ev in evts:
                actor_ids = []
                for a in ev.get("actors", []):
                    l = by_text.get(a)
                    if l and l.entity_type == "Organization":
                        actor_ids.append(l.entity_id)
                obj_ids = [(by_text[o].entity_id, by_text[o].entity_type) for o in ev.get("objects", []) if by_text.get(o)]
                lbl = ev.get("label", ""); et = ev.get("event_type", "general")
                eid = hash16("event_top", lbl, cid, et)
                events.append({"event_id": eid, "event_type": et, "label": lbl[:200], "date": None,
                               "corp_code": actor_ids[0] if actor_ids else None, "rcept_no": None,
                               "subject_id": actor_ids[0] if actor_ids else None,
                               "subject_type": "Organization" if actor_ids else None,
                               "predicate": et, "object_id": None, "object_type": None, "confidence": 0.92,
                               "valid_from": None, "valid_to": None, "evidence_count": 1,
                               "extracted_by": "claude-direct", "source_chunk_id": cid, "run_id": RUN_ID})
                for a in actor_ids:
                    event_ae.append({"event_id": eid, "run_id": RUN_ID, "actor_id": a, "role": "actor"})
                for oid, ot in obj_ids:
                    if ot == "Product":
                        event_oe.append({"event_id": eid, "run_id": RUN_ID, "object_id": oid, "role": "product"})
                gb.append({"target_id": eid, "target_label": "Event", "activity_id": aid, "run_id": RUN_ID})
                stats["evt"] += 1
            if statements: m.statement_with_provenance(statements)
            if events: m.event_with_provenance(events, actor_org_edges=event_ae or None, object_product_edges=event_oe or None)
            if gb: m.generated_by(gb)
            stats["records"] += 1
        activity["ended_at"] = datetime.now(timezone.utc).isoformat()
        m.extraction_activity([activity])
    print(f"[news-load] done ({time.time()-t0:.1f}s)")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
