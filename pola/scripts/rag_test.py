"""RAG 통합 검증 — 7 시나리오 × 4 layer.

Layer 1: Vector RAG (Qdrant) — 질의 → chunk hit
Layer 2: Graph 1-hop — chunk → entity (hasActor/hasObject)
Layer 3: 정형+비정형 추론 — Statement/Event 추적
Layer 4: PROV — 모든 결과가 chunk 로 추적 가능한지
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import httpx
import numpy as np
from polaris.config import neo4j_driver, qdrant_client
from polaris.embed.bge_m3 import embed_batch, normalize

QDRANT_COLLECTION = "polaris-1024-cos-green"
RUN_ID = "20260528_0808_01"
TOP_K = 5


SCENARIOS = [
    ("S1", "삼성전자 HBM4 DDR5 AI 반도체 전략", "AI 반도체 전략"),
    ("S2", "Harman Sound United 인수", "M&A 이벤트"),
    ("S3", "Galaxy Z 폴드7 출시 폴더블", "신제품 출시"),
    ("S4", "삼성전자 자회사 종속기업 목록", "지배구조"),
    ("S5", "삼성전자 공급사 Qualcomm 솔브레인", "공급망"),
    ("S6", "한미반도체 HBM TC BONDER", "다른 회사 (extracted 안 한 경우 의도적 빈약)"),
    ("S7", "Harman 미국 법무부 벌금 제재", "리스크 이벤트"),
]


def embed_one(query: str) -> list[float]:
    with httpx.Client(timeout=60) as c:
        return normalize(np.array([embed_batch(c, [query])[0]]))[0].tolist()


def search_qdrant(qc, query: str, top_k: int = TOP_K) -> list[dict]:
    vec = embed_one(query)
    results = qc.query_points(
        collection_name=QDRANT_COLLECTION,
        query=vec, limit=top_k,
        with_payload=True,
    ).points
    out = []
    for p in results:
        anchor = p.payload.get("anchor", "")
        if isinstance(anchor, list): anchor = " > ".join(str(x) for x in anchor)
        if not isinstance(anchor, str): anchor = str(anchor or "")
        out.append({"chunk_id": p.payload.get("chunk_id"),
                    "score": float(p.score),
                    "corp_code": p.payload.get("corp_code"),
                    "chunk_type": p.payload.get("chunk_type"),
                    "anchor": anchor[:80]})
    return out


def chunk_entities(sess, chunk_id: str) -> dict:
    """1-hop entity 가져오기."""
    r = sess.run("""
        MATCH (c:Chunk {chunk_id: $cid})
        OPTIONAL MATCH (c)-[ha:hasActor]->(actor)
        WITH c, collect(DISTINCT {name: actor.name, code: coalesce(actor.corp_code, actor.person_id),
                                  label: head(labels(actor))}) AS actors
        OPTIONAL MATCH (c)-[ho:hasObject]->(obj)
        WITH c, actors,
             collect(DISTINCT {name: obj.name, code: coalesce(obj.product_id, obj.tech_id, obj.iso_code),
                               label: head(labels(obj))}) AS objects
        RETURN actors, objects
    """, cid=chunk_id).single()
    return {
        "actors": [a for a in (r["actors"] if r else []) if a.get("name")],
        "objects": [o for o in (r["objects"] if r else []) if o.get("name")],
    }


def chunk_statements(sess, chunk_id: str) -> list[dict]:
    """이 chunk 기반으로 만들어진 Statement / Event."""
    out = []
    for r in sess.run("""
        MATCH (s:Statement)-[:wasDerivedFrom]->(c:Chunk {chunk_id: $cid})
        RETURN s.subject_id AS subj, s.predicate AS pred, s.object_id AS obj, s.confidence AS conf
        LIMIT 5
    """, cid=chunk_id):
        out.append({"kind": "Statement", **dict(r)})
    for r in sess.run("""
        MATCH (e:Event)-[:wasDerivedFrom]->(c:Chunk {chunk_id: $cid})
        RETURN e.label AS label, e.event_type AS etype
        LIMIT 5
    """, cid=chunk_id):
        out.append({"kind": "Event", **dict(r)})
    return out


def main():
    print("=" * 80)
    print("RAG 통합 검증 — Claude-direct 적재 후 (삼성전자 본문)")
    print("=" * 80)

    qc = qdrant_client()
    drv = neo4j_driver()

    summary = []
    with drv.session() as sess:
        for sid, query, intent in SCENARIOS:
            print(f"\n{'─' * 80}")
            print(f"[{sid}] {intent}")
            print(f"  Query: {query}")
            print(f"  {'─' * 76}")

            # Layer 1: vector search
            t0 = time.time()
            hits = search_qdrant(qc, query)
            t_vec = time.time() - t0
            print(f"  L1 Vector (top {TOP_K}, {t_vec:.2f}s):")
            for h in hits:
                print(f"    {h['score']:.3f} | {h['chunk_id']} | "
                       f"{h['chunk_type']:10s} | {h['anchor'][:60]}")

            # Layer 2: graph 1-hop on top hit
            top_chunk = hits[0]["chunk_id"] if hits else None
            if not top_chunk:
                print(f"  L2: no top hit"); continue

            t0 = time.time()
            ents = chunk_entities(sess, top_chunk)
            t_g1 = time.time() - t0
            print(f"  L2 Graph 1-hop ({t_g1*1000:.0f}ms) — chunk={top_chunk}:")
            print(f"    Actors  ({len(ents['actors'])}): " +
                   ", ".join(f"{a['name']}[{a['label']}]" for a in ents['actors'][:5]))
            print(f"    Objects ({len(ents['objects'])}): " +
                   ", ".join(f"{o['name']}[{o['label']}]" for o in ents['objects'][:5]))

            # Layer 3: Statement / Event from chunk
            stmts = chunk_statements(sess, top_chunk)
            print(f"  L3 Reified ({len(stmts)}):")
            for s in stmts[:5]:
                if s['kind'] == 'Statement':
                    print(f"    [Stmt] {s['subj']} -[{s['pred']}]-> {s['obj']} (conf={s['conf']:.2f})")
                else:
                    print(f"    [Event] {s['etype']}: {s['label'][:80]}")

            # Layer 4: PROV — top hit 의 wasGeneratedBy
            r = sess.run("""
                MATCH (s:Statement)-[:wasDerivedFrom]->(c:Chunk {chunk_id: $cid})
                OPTIONAL MATCH (s)-[:wasGeneratedBy]->(a:ExtractionActivity)
                RETURN count(s) AS stmts, count(a) AS with_activity
            """, cid=top_chunk).single()
            prov_ok = r['stmts'] == r['with_activity']
            print(f"  L4 PROV: stmts={r['stmts']} with_activity={r['with_activity']} "
                   f"{'✓' if prov_ok else '✗'}")

            # 평가
            quality = "✓ good" if (
                hits and len(ents['actors']) + len(ents['objects']) > 0
            ) else "△ weak" if hits else "✗ no hit"
            summary.append((sid, intent, quality, top_chunk,
                            len(ents['actors'])+len(ents['objects']),
                            len(stmts)))

    drv.close()

    # ===== 요약 =====
    print(f"\n{'=' * 80}")
    print("요약")
    print(f"{'=' * 80}")
    print(f"{'ID':4s} {'Quality':10s} {'Top Chunk':20s} {'Ents':5s} {'Reified':8s} Intent")
    for sid, intent, quality, cid, n_ent, n_stmt in summary:
        print(f"{sid:4s} {quality:10s} {cid:20s} {n_ent:5d} {n_stmt:8d} {intent}")


if __name__ == "__main__":
    main()
