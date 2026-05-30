"""graph 평가 — 비교 카테고리 Cypher 정확도 측정.

입력: tests/gold/graph_v1.yml (30 비교 쿼리)
처리: 각 (corp_codes, year, indicator) 로 Neo4j Cypher 실행 →
      반환 corp_code 집합 vs expected_set 비교 → Precision/Recall/F1

출력: ___test/4_dbGoldTest/graph_summary.json + per_query.jsonl

게이트: F1 ≥ 0.95 (deterministic Cypher 이라 거의 1.0 기대).
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path

from polaris.config import neo4j_driver, DATA_ROOT, ROOT as PKG_ROOT

OUT_DIR = DATA_ROOT / "4_dbGoldTest"

CYPHER = """
MATCH (o:Organization)-[:HAS_METRIC]->(m:FinMetric)
WHERE o.corp_code IN $corps
  AND m.year = $year
  AND m.indicator = $indicator
RETURN DISTINCT o.corp_code AS corp_code
"""


def parse_yaml(p: Path) -> list[dict]:
    items, cur = [], None
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("- id:"):
            if cur: items.append(cur)
            cur = {"id": line[5:].strip()}
            continue
        if cur is None: continue
        if line.startswith("  query:"):
            cur["query"] = json.loads(line.split(":", 1)[1].strip())
        elif line.startswith("  category:"):
            cur["category"] = line.split(":", 1)[1].strip()
        elif line.startswith("  corp_codes:"):
            v = line.split(":", 1)[1].strip()
            cur["corp_codes"] = [s.strip() for s in v.strip("[]").split(",") if s.strip()]
        elif line.startswith("  year:"):
            cur["year"] = int(line.split(":", 1)[1].strip())
        elif line.startswith("  indicator:"):
            cur["indicator"] = json.loads(line.split(":", 1)[1].strip())
        elif line.startswith("  expected_set:"):
            v = line.split(":", 1)[1].strip()
            cur["expected_set"] = [s.strip() for s in v.strip("[]").split(",") if s.strip()]
    if cur: items.append(cur)
    return items


def metrics(expected: list[str], retrieved: list[str]) -> dict:
    exp_set = set(expected); ret_set = set(retrieved)
    tp = len(exp_set & ret_set)
    fp = len(ret_set - exp_set)
    fn = len(exp_set - ret_set)
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return {"precision": p, "recall": r, "f1": f1,
            "tp": tp, "fp": fp, "fn": fn,
            "exact": exp_set == ret_set}


def main():
    gold_path = PKG_ROOT / "tests" / "gold" / "graph_v1.yml"
    items = parse_yaml(gold_path)
    print(f"[graph eval] gold: {len(items)} queries")

    drv = neo4j_driver()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    per_q_path = OUT_DIR / "graph_per_query.jsonl"
    f_pq = per_q_path.open("w", encoding="utf-8")

    all_metrics: list[dict] = []
    t0 = time.time()
    with drv.session() as s:
        for i, g in enumerate(items, 1):
            rs = s.run(CYPHER, corps=g["corp_codes"],
                       year=g["year"], indicator=g["indicator"])
            retrieved = [r["corp_code"] for r in rs]
            m = metrics(g["expected_set"], retrieved)
            entry = {
                "id": g["id"], "query": g["query"],
                "year": g["year"], "indicator": g["indicator"],
                "corp_codes": g["corp_codes"],
                "expected_set": g["expected_set"],
                "retrieved": retrieved,
                "metrics": m,
            }
            all_metrics.append(m)
            f_pq.write(json.dumps(entry, ensure_ascii=False) + "\n")
            if i % 10 == 0:
                print(f"  {i}/{len(items)}")
    f_pq.close()
    drv.close()

    # 집계
    n = len(all_metrics)
    avg_p = sum(m["precision"] for m in all_metrics) / n
    avg_r = sum(m["recall"] for m in all_metrics) / n
    avg_f1 = sum(m["f1"] for m in all_metrics) / n
    exact_rate = sum(1 for m in all_metrics if m["exact"]) / n

    summary = {
        "category": "비교 (그래프 영역)",
        "n": n,
        "precision": round(avg_p, 4),
        "recall": round(avg_r, 4),
        "f1": round(avg_f1, 4),
        "exact_match_rate": round(exact_rate, 4),
        "threshold": "f1 >= 0.95",
        "passed": avg_f1 >= 0.95,
        "elapsed_sec": round(time.time() - t0, 1),
    }
    summary_path = OUT_DIR / "graph_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n──────── 그래프 비교 평가 ──────────────────────────────")
    print(f"  N            : {n}")
    print(f"  Precision    : {avg_p:.4f}")
    print(f"  Recall       : {avg_r:.4f}")
    print(f"  F1           : {avg_f1:.4f}")
    print(f"  Exact match  : {exact_rate:.4f}  ({sum(1 for m in all_metrics if m['exact'])}/{n})")
    print(f"  판정          : {'PASS' if summary['passed'] else 'FAIL'} (게이트 F1 >= 0.95)")
    print(f"  per-query    : {per_q_path.relative_to(PKG_ROOT)}")
    print(f"  summary      : {summary_path.relative_to(PKG_ROOT)}")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
