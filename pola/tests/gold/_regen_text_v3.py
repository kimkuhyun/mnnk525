"""v2.yml → v3.yml: 자유서술 골드만 재생성.

문제: v1/v2 의 자유서술 expected 가 chunk_summary > 50자 만 보고 뽑혀서,
      본문 청크 길이는 무시됨. 결과적으로 "기재 생략" 같은 14~31토큰 보일러플레이트
      청크가 expected 로 들어와 측정이 부정확.

수정: chunk_index.token_count >= 50 필터 추가 → 본문 있는 청크만 정답으로.
      다른 카테고리(정형수치/시계열/비교/no_answer/충돌/시점)는 v2 그대로.

저장: tests/gold/v3.yml (seed=42 동일)
"""
from __future__ import annotations
import json, random, re, sys
from pathlib import Path
from collections import defaultdict

from polaris.config import mariadb_conn, ROOT
V1 = ROOT / "tests" / "gold" / "v1.yml"
V2 = ROOT / "tests" / "gold" / "v2.yml"
V3 = ROOT / "tests" / "gold" / "v3.yml"

CORP_NAMES = {"00126380": "삼성전자", "00164779": "SK하이닉스",
              "00118804": "동진쎄미켐", "01489648": "솔브레인",
              "00161383": "한미반도체"}

random.seed(42)


def parse_yaml(p: Path) -> list[dict]:
    items, cur = [], None
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("- id:"):
            if cur:
                items.append(cur)
            cur = {"id": line[5:].strip()}
            continue
        if cur is None:
            continue
        if line.startswith("  query:"):
            cur["query"] = json.loads(line.split(":", 1)[1].strip())
        elif line.startswith("  category:"):
            cur["category"] = line.split(":", 1)[1].strip()
        elif line.startswith("  no_answer:"):
            cur["no_answer"] = line.split(":", 1)[1].strip() == "true"
        elif line.startswith("  expected_chunk_ids:"):
            v = line.split(":", 1)[1].strip()
            cur["expected_chunk_ids"] = [s.strip() for s in v.strip("[]").split(",") if s.strip()]
        elif line.startswith("  expected_corp_codes:"):
            v = line.split(":", 1)[1].strip()
            cur["expected_corp_codes"] = [s.strip() for s in v.strip("[]").split(",") if s.strip()]
        elif line.startswith("  note:"):
            cur["note"] = json.loads(line.split(":", 1)[1].strip())
    if cur:
        items.append(cur)
    return items


def gen_freetext(conn, n: int = 30) -> list[dict]:
    """자유서술 골드 — chunk_summary > 50자 AND chunk_index.token_count >= 50.

    보일러플레이트 ("기재 생략" 등 짧은 안내문) 청크는 제외.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT ci.chunk_id, ci.corp_code, cs.summary, ci.section_path, ci.token_count
        FROM chunk_index ci
        JOIN chunk_summary cs ON ci.chunk_id = cs.chunk_id AND ci.run_id = cs.run_id
        WHERE ci.chunk_type IN ('text_micro', 'text_macro')
          AND CHAR_LENGTH(cs.summary) > 50
          AND ci.token_count >= 50
          AND ci.ingest_status = 'ready'
        ORDER BY RAND()
        LIMIT %s
    """, (n * 4,))  # over-sample
    rows = cur.fetchall()
    cur.close()
    out: list[dict] = []
    seen: set = set()
    for cid, corp, summ, sp, tc in rows:
        m = re.search(r"'([^']+)' 섹션", summ)
        if not m:
            continue
        topic = m.group(1).strip()
        if len(topic) < 4 or topic in seen:
            continue
        if any(skip in topic for skip in ("개요", "기타", "내용")) and len(topic) < 8:
            continue
        seen.add(topic)
        query = f"{CORP_NAMES[corp]} {topic}"
        out.append({"query": query, "category": "자유서술",
                    "expected_chunk_ids": [cid],
                    "expected_corp_codes": [corp], "no_answer": False})
        if len(out) >= n:
            break
    return out


def main():
    print("[v3 regen] v2.yml + v1.yml 비교 expected 로드 + 자유서술 재생성")
    items = parse_yaml(V2)
    v1_items = parse_yaml(V1)
    print(f"  v2 총 항목: {len(items)}")
    n_text_v2 = sum(1 for it in items if it["category"] == "자유서술")
    print(f"  자유서술 v2: {n_text_v2}")

    conn = mariadb_conn()
    new_text = gen_freetext(conn, n=30)
    conn.close()
    print(f"  자유서술 v3 재생성: {len(new_text)}")
    for i, it in enumerate(new_text, 1):
        it["id"] = f"자유서술_{i:03d}"

    # 비교는 v2.yml 의 자연키 확장 그대로 유지 (벡터 평가 게이트에서는 제외,
    # 그래프 DB 평가용 reference 로 보존)

    # v2 의 자유서술 제거, 카테고리 순서 유지
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_cat[it["category"]].append(it)
    by_cat["자유서술"] = new_text  # 교체

    ordered_cats = ["정형수치", "시계열", "비교", "자유서술",
                    "no_answer", "출처_충돌_검증", "시점"]
    merged: list[dict] = []
    for c in ordered_cats:
        merged.extend(by_cat.get(c, []))
    # 누락 카테고리 보강
    for c, lst in by_cat.items():
        if c not in ordered_cats:
            merged.extend(lst)

    lines = ["# gold v3 — 자유서술 expected 보일러플레이트 제거 (token_count>=50)",
             "# 생성: tests/gold/_regen_text_v3.py / 다른 카테고리는 v2 그대로",
             f"# 총 {len(merged)} queries", ""]
    for g in merged:
        lines.append(f"- id: {g['id']}")
        lines.append(f"  query: {json.dumps(g['query'], ensure_ascii=False)}")
        lines.append(f"  category: {g['category']}")
        lines.append(f"  no_answer: {str(g.get('no_answer', False)).lower()}")
        if g.get("expected_chunk_ids"):
            lines.append(f"  expected_chunk_ids: [{', '.join(g['expected_chunk_ids'])}]")
        else:
            lines.append("  expected_chunk_ids: []")
        if g.get("expected_corp_codes"):
            lines.append(f"  expected_corp_codes: [{', '.join(g['expected_corp_codes'])}]")
        if g.get("note"):
            lines.append(f"  note: {json.dumps(g['note'], ensure_ascii=False)}")
    V3.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n[저장] {V3.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
