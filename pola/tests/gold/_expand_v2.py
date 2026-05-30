"""gold v1.yml → v2.yml 확장: expected_chunk_ids 를 자연키 단위로.

문제: v1 은 chunk_id 1개만 정답으로 라벨. 하지만 같은 자연키(corp, year, account_id)
      에 분기별·시점별 다른 값 청크가 평균 8개 존재. 임의로 1개를 라벨하면 다른
      valid 청크가 top-1 차지해도 recall=0 으로 잡힘.

룰:
  - 정형수치/시계열/비교: chunk_index 본문에서 account_id 추출 → 같은 (corp, year,
    account_id, variant) 의 모든 chunk_id 를 expected 에 합침
  - 출처_충돌_검증: 같은 (corp, year, endpoint) 의 모든 청크 (여러 감사인·KAM 포함)
  - 시점/자유서술/no_answer: v1 그대로

저장: tests/gold/v2.yml + diff 로그
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
from collections import defaultdict

from polaris.config import mariadb_conn, ROOT
V1 = ROOT / "tests" / "gold" / "v1.yml"
V2 = ROOT / "tests" / "gold" / "v2.yml"

re_acc = re.compile(r"account_id=([A-Za-z0-9_\-]+)")
re_variant_in_id = re.compile(r"")


def parse_v1() -> list[dict]:
    items, cur = [], None
    for line in V1.read_text(encoding="utf-8").splitlines():
        if line.startswith("- id:"):
            if cur: items.append(cur)
            cur = {"id": line[5:].strip()}
            continue
        if cur is None: continue
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
    if cur: items.append(cur)
    return items


def build_natural_key_index(conn) -> dict:
    """{(corp, year, account_id, endpoint, variant): [chunk_id, ...]}"""
    cur = conn.cursor()
    cur.execute("""
        SELECT chunk_id, corp_code, bsns_year, endpoint, variant, embedding_text
        FROM chunk_index
        WHERE endpoint='fnlttSinglAcntAll' AND chunk_type='table_nl'
    """)
    idx: dict = defaultdict(list)
    for cid, corp, year, ep, var, txt in cur.fetchall():
        m = re_acc.search(txt or "")
        if not m: continue
        acc = m.group(1)
        idx[(corp, year, acc, ep, var)].append(cid)
    cur.close()
    return idx


def build_audit_endpoint_index(conn) -> dict:
    """{(corp, year, endpoint): [chunk_id, ...]} — 감사의견 등 모든 청크."""
    cur = conn.cursor()
    cur.execute("""
        SELECT chunk_id, corp_code, bsns_year, endpoint
        FROM chunk_index
        WHERE endpoint='accnutAdtorNmNdAdtOpinion' AND chunk_type='table_nl'
    """)
    idx: dict = defaultdict(list)
    for cid, corp, year, ep in cur.fetchall():
        idx[(corp, year, ep)].append(cid)
    cur.close()
    return idx


def chunk_natural_key(conn, chunk_id: str) -> tuple | None:
    """청크 1개의 (corp, year, account_id, endpoint, variant) 추출."""
    cur = conn.cursor()
    cur.execute("""
        SELECT corp_code, bsns_year, endpoint, variant, embedding_text
        FROM chunk_index WHERE chunk_id=%s LIMIT 1
    """, (chunk_id,))
    r = cur.fetchone(); cur.close()
    if not r: return None
    corp, year, ep, var, txt = r
    m = re_acc.search(txt or "")
    acc = m.group(1) if m else None
    return (corp, year, acc, ep, var)


def main():
    conn = mariadb_conn()
    print("[v2 expand] 자연키 인덱스 빌드...")
    fin_idx = build_natural_key_index(conn)
    audit_idx = build_audit_endpoint_index(conn)
    print(f"  fin 자연키: {len(fin_idx)} 키")
    print(f"  audit 자연키: {len(audit_idx)} 키")

    items = parse_v1()
    expanded = 0
    stats = defaultdict(int)
    for it in items:
        cat = it["category"]
        old_ids = list(it.get("expected_chunk_ids", []))
        new_ids = set(old_ids)

        if cat in ("정형수치", "시계열", "비교"):
            # 각 old chunk_id 의 자연키 → 같은 키 모든 chunk_id 추가
            for cid in old_ids:
                nk = chunk_natural_key(conn, cid)
                if nk:
                    new_ids.update(fin_idx.get(nk, []))
        elif cat == "출처_충돌_검증":
            # corp, year, endpoint 동일한 모든 청크 (여러 감사인·KAM 분할 등)
            for cid in old_ids:
                cur = conn.cursor()
                cur.execute("SELECT corp_code, bsns_year, endpoint FROM chunk_index WHERE chunk_id=%s", (cid,))
                r = cur.fetchone(); cur.close()
                if r:
                    new_ids.update(audit_idx.get((r[0], r[1], r[2]), []))

        # 변경량
        added = len(new_ids) - len(old_ids)
        if added > 0: expanded += 1
        stats[cat] += added
        it["expected_chunk_ids"] = sorted(new_ids)

    print(f"\n  확장된 쿼리: {expanded}/{len(items)}")
    print("  카테고리별 추가 chunk_id 합계:")
    for c, n in stats.items(): print(f"    {c}: +{n}")

    # YAML 출력
    lines = ["# gold v2 — expected_chunk_ids 자연키 단위 확장",
             "# 생성: tests/gold/_expand_v2.py",
             f"# 총 {len(items)} queries", ""]
    for g in items:
        lines.append(f"- id: {g['id']}")
        lines.append(f"  query: {json.dumps(g['query'], ensure_ascii=False)}")
        lines.append(f"  category: {g['category']}")
        lines.append(f"  no_answer: {str(g.get('no_answer', False)).lower()}")
        if g.get("expected_chunk_ids"):
            lines.append(f"  expected_chunk_ids: [{', '.join(g['expected_chunk_ids'])}]")
        else:
            lines.append(f"  expected_chunk_ids: []")
        if g.get("expected_corp_codes"):
            lines.append(f"  expected_corp_codes: [{', '.join(g['expected_corp_codes'])}]")
        if g.get("note"):
            lines.append(f"  note: {json.dumps(g['note'], ensure_ascii=False)}")
    V2.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n[저장] {V2.relative_to(ROOT)}")
    conn.close()


if __name__ == "__main__":
    main()
