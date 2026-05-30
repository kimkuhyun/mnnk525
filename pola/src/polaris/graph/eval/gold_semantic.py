"""의미 그래프 평가 — P/R/F1 게이트 (F1 ≥ 0.75).

gold yaml: tests/gold/graph_semantic_v1.yml
   카테고리: entity / relation / event / entity_linking
   query_type: chunk_to_entities / triple_extraction / event_extraction / alias_to_corp_code

게이트 (`SEMANTIC_GATES`):
  entity         : P≥0.80, R≥0.70, F1≥0.75
  relation       : P≥0.75, R≥0.65, F1≥0.70
  event          : P≥0.80, R≥0.70, F1≥0.75
  entity_linking : P≥0.90, R≥0.85, F1≥0.87

산출:
  data/4_dbGoldTest/graph_semantic_eval/{run_id}/per_query.jsonl + summary.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from polaris.config import DATA_ROOT, neo4j_driver
from polaris.graph.common import get_active_run_id

logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)
logging.getLogger("neo4j").setLevel(logging.ERROR)

GOLD_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent \
            / "tests" / "gold" / "graph_semantic_v1.yml"

SEMANTIC_GATES = {
    "entity":         {"P": 0.80, "R": 0.70, "F1": 0.75},
    "relation":       {"P": 0.75, "R": 0.65, "F1": 0.70},
    "event":          {"P": 0.80, "R": 0.70, "F1": 0.75},
    "entity_linking": {"P": 0.90, "R": 0.85, "F1": 0.87},
}


@dataclass
class Metrics:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 0.0

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


def _gate_status(metrics: Metrics, category: str) -> str:
    g = SEMANTIC_GATES[category]
    if (metrics.precision >= g["P"] and metrics.recall >= g["R"]
            and metrics.f1 >= g["F1"]):
        return "PASS"
    return "FAIL"


# ────── 카테고리별 평가 ──────

def evaluate_entity(item: dict, session) -> Metrics:
    """chunk_id → 추출된 entities 와 expected_entities 비교."""
    chunk_id = item["chunk_id"]
    run_id = get_active_run_id()
    # Chunk 의 hasActor + hasObject 1-hop 결과
    found: set[tuple[str, str]] = set()
    for r in session.run("""
        MATCH (c:Chunk {chunk_id: $cid, run_id: $rid})
        OPTIONAL MATCH (c)-[:hasActor|hasObject]->(e)
        WHERE e IS NOT NULL
        RETURN labels(e) AS lbs, e.corp_code AS cc, e.person_id AS pid,
               e.product_id AS prod, e.tech_id AS tech, e.iso_code AS iso,
               e.name AS name
    """, cid=chunk_id, rid=run_id):
        lbs = [l for l in (r["lbs"] or []) if l != "LLMExtracted"]
        label = lbs[0] if lbs else "?"
        eid = r["cc"] or r["pid"] or r["prod"] or r["tech"] or r["iso"]
        if label and eid:
            found.add((label, eid))

    expected: set[tuple[str, str]] = set()
    for e in item.get("expected_entities", []):
        et = e.get("type", "")
        # corp_code 직접 명시 우선, 없으면 canonical 매칭은 별도 처리
        eid = (e.get("corp_code") or e.get("person_id")
               or e.get("product_id") or e.get("tech_id") or e.get("iso_code")
               or e.get("canonical") or "")
        if et and eid:
            expected.add((et, eid))

    return Metrics(
        tp=len(found & expected),
        fp=len(found - expected),
        fn=len(expected - found),
    )


def evaluate_relation(item: dict, session) -> Metrics:
    """chunk_id → 추출된 triples (Statement/Relation 노드) 와 expected 비교."""
    chunk_id = item["chunk_id"]
    run_id = get_active_run_id()
    found: set[tuple[str, str, str]] = set()
    for r in session.run("""
        MATCH (s:Statement {run_id: $rid})
        WHERE s.source_chunk_id = $cid
        RETURN s.subject_id AS subj, s.predicate AS pred, s.object_id AS obj
        UNION
        MATCH (rel:Relation {run_id: $rid})
        WHERE rel.source_chunk_id = $cid
        RETURN rel.from_id AS subj, rel.type AS pred, rel.to_id AS obj
    """, cid=chunk_id, rid=run_id):
        if r["subj"] and r["pred"] and r["obj"]:
            found.add((r["subj"], r["pred"], r["obj"]))

    expected: set[tuple[str, str, str]] = set()
    for t in item.get("expected_triples", []):
        # 양 형식 지원: subject/object (기존) 또는 subject_id/object_id (auto_label)
        subj = t.get("subject") or t.get("subject_id") or ""
        obj = t.get("object") or t.get("object_id") or ""
        pred = t.get("predicate", "")
        if subj and pred and obj:
            expected.add((subj, pred, obj))

    return Metrics(
        tp=len(found & expected),
        fp=len(found - expected),
        fn=len(expected - found),
    )


def evaluate_event(item: dict, session) -> Metrics:
    chunk_id = item["chunk_id"]
    run_id = get_active_run_id()
    found: set[tuple[str, str]] = set()
    for r in session.run("""
        MATCH (ev:Event {run_id: $rid})
        WHERE ev.source_chunk_id = $cid
        RETURN ev.event_type AS et, ev.corp_code AS cc
    """, cid=chunk_id, rid=run_id):
        if r["et"]:
            found.add((r["et"], r["cc"] or ""))

    expected: set[tuple[str, str]] = set()
    # 양 형식 지원: expected_event (단수 dict) 또는 expected_events (복수 list)
    raw_events = item.get("expected_events") or (
        [item["expected_event"]] if item.get("expected_event") else []
    )
    for ev in raw_events:
        if not isinstance(ev, dict):
            continue
        et = ev.get("type") or ev.get("event_type") or ""
        actor = (ev.get("actor_buyer") or ev.get("corp_code")
                 or ev.get("subject_id") or "")
        if et:
            expected.add((et, actor))

    return Metrics(
        tp=len(found & expected),
        fp=len(found - expected),
        fn=len(expected - found),
    )


def evaluate_entity_linking(item: dict) -> Metrics:
    """alias → corp_code: linker.Stage1 단독 채점 (vector 미사용)."""
    from polaris.graph.linker import EntityLinker
    linker = EntityLinker(run_id="eval-stage", enable_vector=False)
    alias = item.get("alias", "")
    expected = item.get("expected_corp_code", "")
    if not alias or not expected:
        return Metrics()
    r = linker.link(alias, "Organization", source_chunk_id="eval")
    if r and r.entity_id == expected:
        return Metrics(tp=1)
    if r and r.entity_id != expected:
        return Metrics(fp=1, fn=1)
    return Metrics(fn=1)


# ────── runner ──────

def run_eval(gold_path: Path = GOLD_PATH, out_dir: Optional[Path] = None) -> dict:
    if not gold_path.is_file():
        print(f"[eval] gold yaml 없음: {gold_path}")
        return {}
    items = yaml.safe_load(gold_path.read_text(encoding="utf-8")) or []
    print(f"[eval] gold items: {len(items)}")

    out_dir = out_dir or (DATA_ROOT / "4_dbGoldTest" / "graph_semantic_eval"
                            / get_active_run_id())
    out_dir.mkdir(parents=True, exist_ok=True)

    by_cat: dict[str, Metrics] = defaultdict(Metrics)
    per_query_path = out_dir / "per_query.jsonl"
    drv = neo4j_driver()

    with per_query_path.open("w", encoding="utf-8") as fp:
        with drv.session() as s:
            for it in items:
                cat = it.get("category", "")
                if cat == "entity":
                    m = evaluate_entity(it, s)
                elif cat == "relation":
                    m = evaluate_relation(it, s)
                elif cat == "event":
                    m = evaluate_event(it, s)
                elif cat == "entity_linking":
                    m = evaluate_entity_linking(it)
                else:
                    continue
                by_cat[cat].tp += m.tp
                by_cat[cat].fp += m.fp
                by_cat[cat].fn += m.fn
                fp.write(json.dumps({
                    "id": it.get("id", ""), "category": cat,
                    "tp": m.tp, "fp": m.fp, "fn": m.fn,
                    "P": round(m.precision, 3), "R": round(m.recall, 3),
                    "F1": round(m.f1, 3),
                }, ensure_ascii=False) + "\n")
    drv.close()

    summary = {"per_category": {}, "gates": SEMANTIC_GATES}
    overall_pass = True
    for cat, met in by_cat.items():
        status = _gate_status(met, cat)
        summary["per_category"][cat] = {
            "P": round(met.precision, 3),
            "R": round(met.recall, 3),
            "F1": round(met.f1, 3),
            "tp": met.tp, "fp": met.fp, "fn": met.fn,
            "status": status,
        }
        if status == "FAIL":
            overall_pass = False
    summary["overall_pass"] = overall_pass

    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                              encoding="utf-8")

    print("\n=== 의미 그래프 평가 ===")
    for cat, s in summary["per_category"].items():
        print(f"  [{s['status']}] {cat:<15} P={s['P']:.2f} R={s['R']:.2f} "
               f"F1={s['F1']:.2f}  (tp={s['tp']} fp={s['fp']} fn={s['fn']})")
    print(f"\n  종합: {'PASS' if overall_pass else 'FAIL'}")
    print(f"  per_query: {per_query_path}")
    print(f"  summary  : {summary_path}")
    return summary


def main():
    parser = argparse.ArgumentParser(description="POLARIS 의미 그래프 평가 (P-3.7)")
    parser.add_argument("--gold", type=str, default=str(GOLD_PATH))
    args = parser.parse_args()
    s = run_eval(gold_path=Path(args.gold))
    return 0 if s.get("overall_pass") else 1


if __name__ == "__main__":
    sys.exit(main())
