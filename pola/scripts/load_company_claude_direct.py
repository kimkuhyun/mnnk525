"""ADR 021 Claude-direct 통합 적재 스크립트.

한 회사의 chunk + Claude 추출 → 3DB 적재 + 정형 그래프 + P0 backfill 까지 전체 자동.

전제:
  1. 디스크에 data/2_Chuck/{01_filtered, 03_chunks, 04_embeddings}/{corp_code}/ 존재
  2. data/rawData/{corp_code}/dart/ 에 DART API JSON 존재 (정형 추출용)
  3. .env 의 POLARIS_CORPS 에 corp_code 포함
  4. (Claude 추출 단계) data/4_dbGoldTest/graph_extracts/claude-direct-{corp}-{date}/llm_extracts.jsonl 존재

3 단계:
  --stage=chunk     : chunk 적재 (Qdrant + MariaDB + Neo4j Chunk)
  --stage=structural: 정형 그래프 (load-finmetric + graph-extract + P0 backfill)
  --stage=load-claude: Claude llm_extracts.jsonl → Neo4j MERGE + Org dup cleanup
  --stage=all       : 위 3개 순차 실행 (Claude 추출 jsonl 이 있어야 last stage 동작)

사용:
  # 1단계: chunk 적재 (Claude 추출 전)
  python scripts/load_company_claude_direct.py --corp 00161383 --run-id 20260528_0808_01 --stage chunk

  # 2단계: 정형 그래프
  python scripts/load_company_claude_direct.py --corp 00161383 --run-id 20260528_0808_01 --stage structural

  # (수동) Claude 가 llm_extracts.jsonl 작성

  # 3단계: Claude 추출 적재
  python scripts/load_company_claude_direct.py --corp 00161383 --run-id 20260528_0808_01 --stage load-claude

  # 또는 한 번에 (Claude 추출 jsonl 이 이미 있을 때)
  python scripts/load_company_claude_direct.py --corp 00161383 --run-id 20260528_0808_01 --stage all
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from polaris.config import mariadb_conn, neo4j_driver, qdrant_client
from polaris.graph.linker import EntityLinker, LinkResult
from polaris.graph.merger import Merger
from polaris.graph.reifier import decide_tier, Tier
from polaris.graph.common import hash16


# ─────────────────────────────────────────────────────
# Stage 1: chunk 적재 (디스크 → 3DB)
# ─────────────────────────────────────────────────────

def load_chunks_from_disk(corp: str) -> dict:
    """data/2_Chuck/03_chunks/{corp}/{text.jsonl,table_nl.jsonl} → chunk_id → record."""
    base = Path(f"data/2_Chuck/03_chunks/{corp}")
    out = {}
    for fname in ["text.jsonl", "table_nl.jsonl"]:
        p = base / fname
        if not p.is_file():
            continue
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("chunk_id"):
                    out[r["chunk_id"]] = r
    return out


def load_embeddings_from_disk(corp: str) -> dict:
    """data/2_Chuck/04_embeddings/{corp}/{text,table_nl}.{npy,ids.json} → chunk_id → vector."""
    base = Path(f"data/2_Chuck/04_embeddings/{corp}")
    out = {}
    for stem in ["text", "table_nl"]:
        npy = base / f"{stem}.npy"
        ids_json = base / f"{stem}.ids.json"
        if not (npy.is_file() and ids_json.is_file()):
            continue
        arr = np.load(npy)
        ids = json.loads(ids_json.read_text(encoding="utf-8"))
        if isinstance(ids, dict):
            ids = list(ids.keys())
        for i, cid in enumerate(ids):
            if i < arr.shape[0]:
                out[cid] = arr[i].tolist()
    return out


def insert_mariadb(records, run_id):
    conn = mariadb_conn(); cur = conn.cursor()
    n = 0; errs = 0
    for rec in records:
        cid = rec["chunk_id"]
        ct = rec.get("chunk_type", "text_micro")
        pl = rec.get("payload") or {}
        try:
            cur.execute("""
                INSERT IGNORE INTO chunk_index
                  (chunk_id, run_id, corp_code, rcept_no, chunk_type, endpoint,
                   variant, bsns_year, reprt_code, fs_div, section_path, token_count)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (cid, run_id, pl.get("corp_code"), pl.get("rcept_no") or "",
                  ct, pl.get("endpoint") or "", pl.get("variant") or "",
                  pl.get("bsns_year"), pl.get("reprt_code") or "",
                  pl.get("fs_div") or "", pl.get("section_path") or "",
                  len(rec.get("embedding_text", "") or "") // 4))
            n += 1
        except Exception:
            errs += 1
    conn.commit(); cur.close(); conn.close()
    return n, errs


def upsert_qdrant(records, emb, run_id, collection="polaris-1024-cos-green"):
    from qdrant_client.models import PointStruct
    qc = qdrant_client()
    points = []
    for rec in records:
        cid = rec["chunk_id"]
        if cid not in emb:
            continue
        pl_orig = rec.get("payload") or {}
        payload = {
            "chunk_id": cid, "run_id": run_id,
            "chunk_type": rec.get("chunk_type", "text_micro"),
            **pl_orig, "ingest_status": "ready",
        }
        pid = int(hashlib.sha1(cid.encode()).hexdigest()[:15], 16)
        points.append(PointStruct(id=pid, vector=emb[cid], payload=payload))
    BATCH = 256; n = 0
    for i in range(0, len(points), BATCH):
        qc.upsert(collection_name=collection, points=points[i:i+BATCH])
        n += len(points[i:i+BATCH])
    return n


def merge_neo4j_chunks(records, run_id):
    drv = neo4j_driver(); n = 0
    with drv.session() as s:
        BATCH = 500
        rows = []
        for rec in records:
            cid = rec["chunk_id"]
            pl = rec.get("payload") or {}
            rows.append({
                "chunk_id": cid, "run_id": run_id,
                "corp_code": pl.get("corp_code"),
                "rcept_no": pl.get("rcept_no", "") or "",
                "chunk_type": rec.get("chunk_type", "text_micro"),
                "anchor": pl.get("section_path", "") or "",
                "ingest_status": "ready",
                "embedding_text_hash": "",
            })
        for i in range(0, len(rows), BATCH):
            s.run("""
                UNWIND $rows AS r
                MERGE (c:Chunk {chunk_id: r.chunk_id, run_id: r.run_id})
                  ON CREATE SET c.first_seen_run_id = r.run_id
                SET c.corp_code = r.corp_code, c.rcept_no = r.rcept_no,
                    c.chunk_type = r.chunk_type, c.anchor = r.anchor,
                    c.ingest_status = r.ingest_status,
                    c.embedding_text_hash = r.embedding_text_hash,
                    c.last_updated_run_id = r.run_id
            """, rows=rows[i:i+BATCH])
            n += len(rows[i:i+BATCH])
    drv.close()
    return n


def stage_chunk(corp, run_id):
    """Stage 1: chunk 디스크 → 3DB."""
    print(f"\n{'='*60}\nStage 1: chunk 적재 (corp={corp}, run_id={run_id})\n{'='*60}")
    chunks = load_chunks_from_disk(corp)
    emb = load_embeddings_from_disk(corp)
    records = list(chunks.values())
    print(f"  chunks: {len(records)}, embeddings: {len(emb)}")
    if not records:
        print("  [error] no chunks on disk"); return False
    n_mdb, errs_mdb = insert_mariadb(records, run_id)
    print(f"  MariaDB chunk_index: {n_mdb} inserted ({errs_mdb} errors)")
    n_qd = upsert_qdrant(records, emb, run_id) if emb else 0
    print(f"  Qdrant green:        {n_qd} upserted")
    n_neo = merge_neo4j_chunks(records, run_id)
    print(f"  Neo4j Chunk:         {n_neo} merged")
    return True


# ─────────────────────────────────────────────────────
# Stage 2: 정형 그래프 + P0 backfill
# ─────────────────────────────────────────────────────

def stage_structural(corp, run_id, company_name=""):
    """Stage 2: POLARIS load-finmetric + graph-extract + P0 backfill."""
    print(f"\n{'='*60}\nStage 2: 정형 그래프 + P0 backfill (corp={corp})\n{'='*60}")

    # load-finmetric (POLARIS CLI)
    env = {**os.environ, "POLARIS_TARGET_RUN_ID": run_id, "PYTHONIOENCODING": "utf-8"}
    print("\n--- 2a. load-finmetric ---")
    r = subprocess.run(["polaris", "load-finmetric"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env, timeout=900)
    print(r.stdout[-500:])
    if r.returncode != 0:
        print(f"  [warn] load-finmetric rc={r.returncode}: {r.stderr[-500:]}")

    print("\n--- 2b. graph-extract (결정론, persons/shareholders/invests/ftc_groups/events) ---")
    r = subprocess.run(["polaris", "graph-extract", "--only",
                        "persons,shareholders,invests,ftc_groups,events"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env, timeout=900)
    print(r.stdout[-1000:])
    if r.returncode != 0:
        print(f"  [warn] graph-extract rc={r.returncode}: {r.stderr[-500:]}")

    # P0 backfill (FilingDocument, has_chunk, reports, table_nl→Org)
    print("\n--- 2c. P0 backfill (FilingDocument + has_chunk + reports + table_nl→Org) ---")
    drv = neo4j_driver()
    with drv.session() as s:
        r = s.run("""
            MATCH (c:Chunk) WHERE c.corp_code=$code
              AND c.rcept_no IS NOT NULL AND c.rcept_no <> ''
            WITH DISTINCT c.corp_code AS code, c.rcept_no AS rcept
            MERGE (d:FilingDocument {rcept_no: rcept})
              ON CREATE SET d:BackfilledStub, d.corp_code = code,
                            d.doc_type = 'unknown_stub',
                            d.title = 'auto-backfilled (' + rcept + ')',
                            d.first_seen_run_id = $rid + '_backfill',
                            d.summary_method = 'backfill', d.summary_verified = false
              ON MATCH SET d.corp_code = coalesce(d.corp_code, code)
            RETURN count(d) AS n
        """, code=corp, rid=run_id).single()
        print(f"  FilingDoc backfill: {r['n']}")

        r = s.run("""
            MATCH (d:FilingDocument), (c:Chunk)
            WHERE d.corp_code=$code AND d.rcept_no=c.rcept_no AND c.corp_code=$code
            MERGE (d)-[h:has_chunk]->(c)
            ON CREATE SET h.first_seen_run_id = $rid + '_backfill'
            RETURN count(h) AS n
        """, code=corp, rid=run_id).single()
        print(f"  has_chunk:          {r['n']}")

        if company_name:
            s.run("""
                MERGE (o:Organization {corp_code:$code})
                ON CREATE SET o.name=$name, o.first_seen_run_id=$rid
            """, code=corp, name=company_name, rid=run_id)

        r = s.run("""
            MATCH (o:Organization {corp_code:$code}), (d:FilingDocument {corp_code:$code})
            MERGE (o)-[r:reports]->(d)
            ON CREATE SET r.first_seen_run_id = $rid + '_backfill'
            RETURN count(r) AS n
        """, code=corp, rid=run_id).single()
        print(f"  reports:            {r['n']}")

        r = s.run("""
            MATCH (c:Chunk {chunk_type:'table_nl', corp_code:$code})
            MATCH (o:Organization {corp_code:$code})
            MERGE (c)-[h:hasActor {role:'document_subject'}]->(o)
            ON CREATE SET h.first_seen_run_id = $rid + '_backfill',
                          h.run_id = $rid + '_backfill'
            RETURN count(h) AS n
        """, code=corp, rid=run_id).single()
        print(f"  table_nl → Org:     {r['n']}")
    drv.close()
    return True


# ─────────────────────────────────────────────────────
# Stage 3: Claude llm_extracts.jsonl → Neo4j MERGE
# ─────────────────────────────────────────────────────

def _sha10(t): return hashlib.sha1(t.encode("utf-8")).hexdigest()[:10].upper()
def _synth(et, c):
    p = {"Organization":"XCLAUDE_","Person":"PCLAUDE_","Product":"PRCLAUDE_",
         "Technology":"TCLAUDE_","Place":"PLCLAUDE_"}.get(et,"ECLAUDE_")
    return p + _sha10(c)

def _link(linker, ent, cid):
    s = ent.get("text",""); et = ent.get("type","")
    cn = ent.get("canonical") or s
    if not s or not et: return None
    r = linker.link(s, et, source_chunk_id=cid)
    if r: return r
    if cn and cn != s:
        r = linker.link(cn, et, source_chunk_id=cid)
        if r: return LinkResult(r.entity_id, r.entity_type, r.score, r.stage, s, cn)
    return LinkResult(_synth(et, cn), et, 0.8, 4, s, cn)


def stage_load_claude(corp, run_id, extract_dir):
    """Stage 3: Claude llm_extracts.jsonl → Neo4j MERGE + Event PROV + Org dup cleanup."""
    print(f"\n{'='*60}\nStage 3: Claude 추출 적재 (corp={corp})\n{'='*60}")

    jsonl = Path(extract_dir) / "llm_extracts.jsonl"
    if not jsonl.is_file():
        print(f"  [error] missing {jsonl}"); return False
    records = [json.loads(l) for l in jsonl.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"  records: {len(records)}")

    aid = hash16("activity", run_id, f"claude-direct-{corp}")
    activity = {
        "activity_id": aid, "run_id": run_id, "extractor": "claude-direct",
        "pipeline_version": "polaris-claude-direct/0.1", "prompt_hash": "manual",
        "model_temp": 0.0, "started_at": datetime.now(timezone.utc).isoformat(),
        "ended_at": None, "chunks_processed": len(records),
        "entities_extracted": sum(len(r.get("entities",[])) for r in records),
        "relations_extracted": sum(len(r.get("relations",[])) for r in records),
    }

    linker = EntityLinker(run_id=run_id, enable_vector=True)
    stats = {"records":0, "ent_yaml":0, "ent_vec":0, "ent_syn":0, "stmt":0, "evt":0}
    canon = {}

    # Skip "default_only" pattern — entities=[Org corp_name] 만, relations/events 없는 chunk
    # (fill_remaining 같은 자동 보강은 noise 증가 → 검색 정밀도 저하)
    SKIP_DEFAULT_ONLY = True
    skipped_default = 0

    t0 = time.time()
    with Merger() as m:
        m.extraction_activity([activity])
        for i, rec in enumerate(records, 1):
            cid = rec["chunk_id"]; entities = rec.get("entities") or []
            rels = rec.get("relations") or []
            evts = rec.get("events") or []
            if not entities and not rels and not evts:
                stats["records"] += 1; continue
            # default_only pattern detect
            if (SKIP_DEFAULT_ONLY and len(entities) == 1
                and entities[0].get("type") == "Organization"
                and not rels and not evts):
                skipped_default += 1
                stats["records"] += 1; continue

            new_products, new_techs = [], []
            ae_org, ae_per = [], []
            oe_prod, oe_tech, oe_place = [], [], []
            by_text = {}

            for e in entities:
                r = _link(linker, e, cid)
                if not r: continue
                by_text[e.get("text","")] = r
                if r.stage == 1: stats["ent_yaml"] += 1
                elif r.stage == 2: stats["ent_vec"] += 1
                else: stats["ent_syn"] += 1
                cn = e.get("canonical") or e.get("text","")
                if cn: canon.setdefault(cn, set()).add(e.get("text",""))
                edge = {"chunk_id":cid, "run_id":run_id,
                        "entity_id":r.entity_id,
                        "entity_name":r.canonical or r.surface or r.entity_id}
                if r.entity_type == "Product":
                    new_products.append({"product_id":r.entity_id,
                        "name":r.canonical or r.surface,
                        "canonical":r.canonical or r.surface,
                        "category":"other",
                        "aliases":[r.surface] if r.surface != r.canonical else [],
                        "confidence":r.score,
                        "extracted_by":"claude-direct" if r.stage == 4 else "alias_dict_v1",
                        "source_chunk_id":cid, "run_id":run_id})
                    oe_prod.append(edge)
                elif r.entity_type == "Technology":
                    new_techs.append({"tech_id":r.entity_id,
                        "name":r.canonical or r.surface,
                        "canonical":r.canonical or r.surface,
                        "category":"other","node_size_nm":None,
                        "aliases":[r.surface] if r.surface != r.canonical else [],
                        "confidence":r.score,
                        "extracted_by":"claude-direct" if r.stage == 4 else "alias_dict_v1",
                        "source_chunk_id":cid, "run_id":run_id})
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
            for r in rec.get("relations") or []:
                sl = by_text.get(r["subject"]); ol = by_text.get(r["object"])
                if not sl:
                    sl = LinkResult(_synth("Organization", r["subject"]),
                                    "Organization", 0.7, 4, r["subject"], r["subject"])
                if not ol:
                    ol = LinkResult(_synth("Organization", r["object"]),
                                    "Organization", 0.7, 4, r["object"], r["object"])
                pred = r["predicate"]; conf = float(r.get("self_confidence", 0.9))
                d = decide_tier(predicate=pred, has_validity=False,
                                has_confidence=True, evidence_count=1, multi_source=False)
                common = {"subject_id":sl.entity_id, "subject_type":sl.entity_type,
                          "predicate":pred, "object_id":ol.entity_id,
                          "object_type":ol.entity_type, "confidence":conf,
                          "valid_from":None, "valid_to":None, "evidence_count":1,
                          "extracted_by":"claude-direct",
                          "source_chunk_id":cid, "run_id":run_id}
                if d.tier == Tier.STATEMENT:
                    sid = hash16("stmt", sl.entity_id, pred, ol.entity_id, cid)
                    statements.append({**common, "statement_id":sid})
                    gb.append({"target_id":sid, "target_label":"Statement",
                               "activity_id":aid, "run_id":run_id})
                    stats["stmt"] += 1
                elif d.tier == Tier.EVENT:
                    eid = hash16("event", pred, sl.entity_id, "", cid)
                    events.append({**common, "event_id":eid, "event_type":pred,
                                   "label":f"{sl.canonical} {pred} {ol.canonical}",
                                   "date":None,
                                   "corp_code":sl.entity_id if sl.entity_type=="Organization" else None,
                                   "rcept_no":None})
                    if sl.entity_type == "Organization":
                        event_ae.append({"event_id":eid, "run_id":run_id,
                                         "actor_id":sl.entity_id, "role":"actor"})
                    if ol.entity_type == "Product":
                        event_oe.append({"event_id":eid, "run_id":run_id,
                                         "object_id":ol.entity_id, "role":"product"})
                    gb.append({"target_id":eid, "target_label":"Event",
                               "activity_id":aid, "run_id":run_id})
                    stats["evt"] += 1

            for ev in rec.get("events") or []:
                actor_ids = []
                for a in ev.get("actors", []):
                    l = by_text.get(a)
                    if l and l.entity_type == "Organization":
                        actor_ids.append(l.entity_id)
                obj_ids = []
                for o in ev.get("objects", []):
                    l = by_text.get(o)
                    if l: obj_ids.append((l.entity_id, l.entity_type))
                lbl = ev.get("label",""); et = ev.get("event_type", "general")
                eid = hash16("event_top", lbl, cid, et)
                events.append({"event_id":eid, "event_type":et,
                               "label":lbl[:200], "date":None,
                               "corp_code":actor_ids[0] if actor_ids else None,
                               "rcept_no":None,
                               "subject_id":actor_ids[0] if actor_ids else None,
                               "subject_type":"Organization" if actor_ids else None,
                               "predicate":et, "object_id":None, "object_type":None,
                               "confidence":0.92, "valid_from":None, "valid_to":None,
                               "evidence_count":1, "extracted_by":"claude-direct",
                               "source_chunk_id":cid, "run_id":run_id})
                for a in actor_ids:
                    event_ae.append({"event_id":eid, "run_id":run_id,
                                     "actor_id":a, "role":"actor"})
                for oid, ot in obj_ids:
                    if ot == "Organization":
                        event_ae.append({"event_id":eid, "run_id":run_id,
                                         "actor_id":oid, "role":"target"})
                    elif ot == "Product":
                        event_oe.append({"event_id":eid, "run_id":run_id,
                                         "object_id":oid, "role":"product"})
                gb.append({"target_id":eid, "target_label":"Event",
                           "activity_id":aid, "run_id":run_id})
                stats["evt"] += 1

            if statements: m.statement_with_provenance(statements)
            if events:
                m.event_with_provenance(events,
                                         actor_org_edges=event_ae or None,
                                         object_product_edges=event_oe or None)
            if gb: m.generated_by(gb)
            stats["records"] += 1
            if i % 30 == 0:
                print(f"  loaded {i}/{len(records)} stmt={stats['stmt']} evt={stats['evt']}")

        activity["ended_at"] = datetime.now(timezone.utc).isoformat()
        m.extraction_activity([activity])

    print(f"\n  load 완료 ({time.time()-t0:.1f}s)")
    for k, v in stats.items(): print(f"    {k}: {v:,}")
    if skipped_default:
        print(f"    skipped (default_only Org-only chunks): {skipped_default:,}")

    # canonical_clusters.json
    canon_out = {k: sorted(list(v)) for k, v in sorted(canon.items())}
    canon_path = Path(extract_dir) / "canonical_clusters.json"
    canon_path.write_text(json.dumps(canon_out, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    print(f"  canonical_clusters: {len(canon_out)} → {canon_path}")

    # ===== Post-load: Org dup cleanup + Event PROV backfill =====
    print("\n--- Post-load: Org dup cleanup ---")
    drv = neo4j_driver()
    def code_prio(c):
        if c and len(c)==8 and c.isdigit(): return 0
        if c and c.startswith("X") and not c.startswith("XCLAUDE_") and len(c)<=10: return 1
        if c and c.startswith("XCLAUDE_"): return 2
        if c and len(c)==16: return 3
        if c and c.startswith("unknown_"): return 4
        return 5
    with drv.session() as s:
        dups = list(s.run("""
            MATCH (o:Organization) WHERE o.name IS NOT NULL AND o.name <> ''
            WITH o.name AS nm, collect(DISTINCT o.corp_code) AS codes
            WHERE size(codes) > 1
            RETURN nm, codes
        """))
        merged = 0
        for d in dups:
            codes = sorted(d["codes"], key=code_prio)
            canon = codes[0]
            for dup in codes[1:]:
                try:
                    s.run("""
                        MATCH (c:Organization {corp_code:$c}), (d:Organization {corp_code:$d})
                        WITH c, d WHERE c <> d
                        CALL apoc.refactor.mergeNodes([c,d],
                            {properties:'discard', mergeRels:true})
                        YIELD node RETURN node
                    """, c=canon, d=dup)
                    merged += 1
                except Exception:
                    pass
        print(f"  Org dup merged: {merged}")

        # Event PROV backfill (orphan event → chunk 또는 filing)
        print("\n--- Post-load: Event PROV backfill ---")
        r = s.run("""
            MATCH (e:Event) WHERE NOT EXISTS((e)-[:wasDerivedFrom]->(:Chunk))
              AND e.rcept_no IS NOT NULL AND e.rcept_no <> ''
            MATCH (c:Chunk {rcept_no: e.rcept_no, corp_code: e.corp_code})
            WITH e, c LIMIT 200
            MERGE (e)-[w:wasDerivedFrom]->(c)
            ON CREATE SET w.first_seen_run_id = $rid + '_backfill',
                          w.source = 'rcept_no_match'
            RETURN count(w) AS n
        """, rid=run_id).single()
        print(f"  Event-Chunk PROV backfill: {r['n']}")
        r = s.run("""
            MATCH (e:Event) WHERE NOT EXISTS((e)-[:wasDerivedFrom]->(:Chunk))
              AND e.rcept_no IS NOT NULL AND e.rcept_no <> ''
            MATCH (d:FilingDocument {rcept_no: e.rcept_no})
            MERGE (e)-[w:wasDerivedFrom]->(d)
            ON CREATE SET w.first_seen_run_id = $rid + '_backfill',
                          w.source = 'rcept_no_match_filing'
            RETURN count(w) AS n
        """, rid=run_id).single()
        print(f"  Event-Filing PROV backfill: {r['n']}")
    drv.close()
    return True


# ─────────────────────────────────────────────────────
# Verification (전체 stage 끝나면)
# ─────────────────────────────────────────────────────

def verify(corp, run_id):
    print(f"\n{'='*60}\n검증 (corp={corp})\n{'='*60}")
    drv = neo4j_driver()
    with drv.session() as s:
        qs = [
            (f"Chunk total", f"MATCH (c:Chunk {{corp_code:'{corp}'}}) RETURN count(c) AS n"),
            (f"본문 chunk total",
             f"MATCH (c:Chunk {{corp_code:'{corp}'}}) WHERE c.chunk_type IN ['text_micro','text_macro'] RETURN count(c) AS n"),
            (f"본문 with Claude entity (run_id={run_id})",
             f"MATCH (c:Chunk {{corp_code:'{corp}'}}) WHERE c.chunk_type IN ['text_micro','text_macro'] AND EXISTS {{(c)-[h:hasActor|hasObject]-() WHERE h.run_id='{run_id}' AND coalesce(h.role,'') <> 'document_subject'}} RETURN count(c) AS n"),
            (f"FinMetric", f"MATCH (o:Organization {{corp_code:'{corp}'}})-[:HAS_METRIC]->(f:FinMetric) RETURN count(f) AS n"),
            (f"FilingDocument", f"MATCH (d:FilingDocument {{corp_code:'{corp}'}}) RETURN count(d) AS n"),
            (f"has_chunk edges", f"MATCH (:FilingDocument {{corp_code:'{corp}'}})-[h:has_chunk]->(:Chunk) RETURN count(h) AS n"),
            (f"reports edges", f"MATCH (:Organization {{corp_code:'{corp}'}})-[r:reports]->(:FilingDocument) RETURN count(r) AS n"),
            ("전체 Org dup", "MATCH (o:Organization) WHERE o.name IS NOT NULL AND o.name <> '' WITH o.name AS nm, collect(DISTINCT o.corp_code) AS codes WHERE size(codes) > 1 RETURN count(*) AS n"),
            (f"Statement (this run)", f"MATCH (s:Statement {{run_id:'{run_id}'}}) WHERE s.subject_id='{corp}' OR s.object_id='{corp}' RETURN count(s) AS n"),
            (f"Statement PROV", f"MATCH (s:Statement {{run_id:'{run_id}'}})-[:wasDerivedFrom]->(:Chunk) WHERE s.subject_id='{corp}' OR s.object_id='{corp}' RETURN count(*) AS n"),
            (f"Event (this corp)", f"MATCH (e:Event {{corp_code:'{corp}'}}) RETURN count(e) AS n"),
            (f"Event PROV", f"MATCH (e:Event {{corp_code:'{corp}'}})-[:wasDerivedFrom]->() RETURN count(*) AS n"),
        ]
        for label, q in qs:
            r = s.run(q).single()
            v = list(r.values())[0]
            print(f"  {label:45s} {v:>8,}")
    drv.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corp", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--stage", choices=["chunk", "structural", "load-claude", "all"],
                    default="all")
    ap.add_argument("--name", default="", help="회사명 (Org 노드 ensure 시 사용)")
    ap.add_argument("--extract-dir", default="",
                    help="Claude 추출 디렉터리 (default: data/4_dbGoldTest/graph_extracts/claude-direct-{corp}-{date})")
    args = ap.parse_args()

    extract_dir = args.extract_dir or f"data/4_dbGoldTest/graph_extracts/claude-direct-{args.corp}-20260528"

    if args.stage in ("chunk", "all"):
        if not stage_chunk(args.corp, args.run_id):
            return 1
    if args.stage in ("structural", "all"):
        if not stage_structural(args.corp, args.run_id, company_name=args.name):
            return 1
    if args.stage in ("load-claude", "all"):
        if not Path(extract_dir).is_dir():
            print(f"\n[skip] {extract_dir} 없음 — Claude 추출 jsonl 작성 후 --stage=load-claude 재실행")
        else:
            if not stage_load_claude(args.corp, args.run_id, extract_dir):
                return 1

    verify(args.corp, args.run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
