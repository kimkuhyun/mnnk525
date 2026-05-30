"""POLARIS ↔ KGGen 어댑터 (ADR 020 Phase A).

KGGen 의 generate() 가 DSPy + Ollama qwen3.5 와 호환이 불안정해서,
KGGen 의 *cluster() / aggregate() 만* plugin 으로 사용한다.

흐름:
    POLARIS llm_extracts.jsonl (여러 청크)
        → chunk_jsonl_to_graph()           청크별 Graph
        → KGGen.aggregate(graphs)          하나로 통합
        → KGGen.cluster(g, context=...)    entity·predicate 정규화 (canonical merge)
        → cluster 결과를 POLARIS merger 가 쓰는 형식으로 변환

POLARIS 의 기존 추출 (qwen3.5:9b) 결과는 quality OK 이고 (어제 fix 후 mojibake 없음),
다만 surface 변형 (삼성전자 vs 삼성전자(주)) 이 같은 corp_code 로 모이지 못함.
cluster() 가 이걸 자동 정규화해서 ADR 012 의 *corp_code 4갈래 분기* 문제 해결.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from kg_gen.models import Graph  # type: ignore


def chunk_record_to_graph(record: dict) -> Graph:
    """POLARIS llm_extracts.jsonl 한 줄 → KGGen Graph 객체.

    record 형식 (POLARIS llm_entity.py 출력):
      {
        "chunk_id": "...",
        "entities": [{"text": "삼성전자", "type": "Organization", ...}, ...],
        "relations": [{"subject": "이재용", "predicate": "EXECUTIVE_OF",
                       "object": "삼성전자", "self_confidence": 0.9}, ...]
      }
    """
    entities: set[str] = set()
    edges: set[str] = set()
    relations: set[tuple[str, str, str]] = set()

    for e in record.get("entities") or []:
        t = (e.get("text") or "").strip()
        if t and len(t) >= 2:
            entities.add(t)
    for r in record.get("relations") or []:
        s = (r.get("subject") or "").strip()
        p = (r.get("predicate") or "").strip()
        o = (r.get("object") or "").strip()
        if not (s and p and o):
            continue
        entities.add(s)
        entities.add(o)
        edges.add(p)
        relations.add((s, p, o))

    return Graph(entities=entities, edges=edges, relations=relations)


def load_chunk_graphs(jsonl_path: Path) -> list[Graph]:
    """llm_extracts.jsonl → 청크별 Graph list (빈 청크 제외)."""
    out: list[Graph] = []
    with jsonl_path.open(encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            g = chunk_record_to_graph(rec)
            # 완전 빈 청크는 aggregate 비용 절감 차원에서 제외
            if g.entities or g.relations:
                out.append(g)
    return out


def clustered_graph_to_polaris(
    g: Graph, *, source_chunk_id_map: dict[tuple[str, str, str], str] | None = None
) -> dict:
    """KGGen cluster() 결과 → POLARIS merger 가 받는 dict 형식.

    cluster 결과의 핵심 두 가지:
      g.entity_clusters: {canonical_name: {surface1, surface2, ...}}
      g.edge_clusters:   {canonical_predicate: {variant1, variant2, ...}}

    source_chunk_id_map: optional — 원본 추출 시 (s, p, o) → chunk_id 맵.
        Merger 의 hasActor/hasObject 부착 시 chunk_id 가 필요.
    """
    # entity → canonical 매핑 역색인
    surface_to_canonical: dict[str, str] = {}
    if g.entity_clusters:
        for canonical, surfaces in g.entity_clusters.items():
            surface_to_canonical[canonical] = canonical
            for s in surfaces:
                surface_to_canonical[s] = canonical
    # predicate → canonical
    pred_to_canonical: dict[str, str] = {}
    if g.edge_clusters:
        for canonical, variants in g.edge_clusters.items():
            pred_to_canonical[canonical] = canonical
            for v in variants:
                pred_to_canonical[v] = canonical

    def C(s: str, m: dict[str, str]) -> str:
        return m.get(s, s)

    canonical_entities = sorted({C(e, surface_to_canonical) for e in g.entities})
    canonical_relations: list[dict] = []
    for s, p, o in g.relations:
        canonical_relations.append({
            "subject": C(s, surface_to_canonical),
            "subject_surface": s,
            "predicate": C(p, pred_to_canonical),
            "predicate_surface": p,
            "object": C(o, surface_to_canonical),
            "object_surface": o,
            "source_chunk_id": (source_chunk_id_map or {}).get((s, p, o), ""),
        })

    return {
        "entities": canonical_entities,
        "relations": canonical_relations,
        "entity_clusters": (
            {k: sorted(v) for k, v in g.entity_clusters.items()}
            if g.entity_clusters else {}
        ),
        "edge_clusters": (
            {k: sorted(v) for k, v in g.edge_clusters.items()}
            if g.edge_clusters else {}
        ),
    }


def build_source_chunk_map(jsonl_path: Path) -> dict[tuple[str, str, str], str]:
    """(s, p, o) → chunk_id 매핑. cluster 후 출처 chunk 추적용."""
    m: dict[tuple[str, str, str], str] = {}
    with jsonl_path.open(encoding="utf-8") as fp:
        for line in fp:
            try:
                rec = json.loads(line.strip())
            except (json.JSONDecodeError, ValueError):
                continue
            cid = rec.get("chunk_id") or ""
            if not cid:
                continue
            for r in rec.get("relations") or []:
                s = (r.get("subject") or "").strip()
                p = (r.get("predicate") or "").strip()
                o = (r.get("object") or "").strip()
                if s and p and o:
                    m.setdefault((s, p, o), cid)
    return m
