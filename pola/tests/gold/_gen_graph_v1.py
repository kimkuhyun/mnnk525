"""graph_v1.yml 생성 — 비교 카테고리 Cypher 평가용.

v3.yml 의 비교 카테고리 30 쿼리에서:
  query: "한미반도체 vs 동진쎄미켐 2024년 부채총계"
  → (corp_codes, year, indicator) 추출 → Cypher 평가 입력

골드셋 형식:
  - id: 비교_001
    query: "..."
    corp_codes: [00161383, 00118804]
    year: 2024
    indicator: "부채총계"
    expected_set: ["00161383", "00118804"]   # Cypher 결과의 corp_code 집합

평가: scripts/eval/run_gold_graph.py 가 위 (corp_codes, year, indicator) 로 Cypher 실행 →
      반환 노드의 corp_code 집합이 expected_set 과 일치하면 PASS.
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

from polaris.config import ROOT
V3 = ROOT / "tests" / "gold" / "v3.yml"
OUT = ROOT / "tests" / "gold" / "graph_v1.yml"

CORP_NAMES = {"삼성전자": "00126380", "SK하이닉스": "00164779",
              "동진쎄미켐": "00118804", "솔브레인": "01489648",
              "한미반도체": "00161383", "에스케이하이닉스": "00164779"}


def parse_v3():
    items, cur = [], None
    for line in V3.read_text(encoding="utf-8").splitlines():
        if line.startswith("- id:"):
            if cur: items.append(cur)
            cur = {"id": line[5:].strip()}
            continue
        if cur is None: continue
        if line.startswith("  query:"):
            cur["query"] = json.loads(line.split(":", 1)[1].strip())
        elif line.startswith("  category:"):
            cur["category"] = line.split(":", 1)[1].strip()
        elif line.startswith("  expected_corp_codes:"):
            v = line.split(":", 1)[1].strip()
            cur["expected_corp_codes"] = [s.strip() for s in v.strip("[]").split(",") if s.strip()]
    if cur: items.append(cur)
    return items


_RE_VS = re.compile(r"(.+?)\s*vs\s*(.+?)\s+(\d{4})년\s+(.+)")


def parse_compare_query(q: str):
    """비교 쿼리에서 (corp1, corp2, year, indicator) 추출."""
    m = _RE_VS.match(q.strip())
    if not m:
        return None
    c1, c2, y, ind = m.group(1).strip(), m.group(2).strip(), int(m.group(3)), m.group(4).strip()
    code1 = CORP_NAMES.get(c1)
    code2 = CORP_NAMES.get(c2)
    if not code1 or not code2:
        return None
    return {"corp_codes": sorted([code1, code2]), "year": y, "indicator": ind}


def main():
    items = parse_v3()
    compare = [it for it in items if it.get("category") == "비교"]
    print(f"v3 비교 카테고리: {len(compare)}")
    out = []
    skipped = []
    for it in compare:
        parsed = parse_compare_query(it["query"])
        if not parsed:
            skipped.append(it["id"])
            continue
        out.append({
            "id": it["id"],
            "query": it["query"],
            "category": "비교",
            "corp_codes": parsed["corp_codes"],
            "year": parsed["year"],
            "indicator": parsed["indicator"],
            "expected_set": parsed["corp_codes"],  # corp_code 집합 일치 검증
        })
    print(f"파싱 성공: {len(out)} / 실패: {len(skipped)}")
    if skipped:
        print(f"  skipped: {skipped}")

    lines = [
        "# graph_v1 — 비교 카테고리 Cypher 평가셋",
        "# 생성: tests/gold/_gen_graph_v1.py / v3.yml 의 비교 카테고리 추출",
        f"# 총 {len(out)} queries", ""
    ]
    for g in out:
        lines.append(f"- id: {g['id']}")
        lines.append(f"  query: {json.dumps(g['query'], ensure_ascii=False)}")
        lines.append(f"  category: 비교")
        lines.append(f"  corp_codes: [{', '.join(g['corp_codes'])}]")
        lines.append(f"  year: {g['year']}")
        lines.append(f"  indicator: {json.dumps(g['indicator'], ensure_ascii=False)}")
        lines.append(f"  expected_set: [{', '.join(g['expected_set'])}]")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[저장] {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
