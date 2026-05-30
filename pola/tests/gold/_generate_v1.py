"""tests/gold/v1.yml 자동 생성 — 적재된 chunk_index 에서 200개 골드 합성.

이건 사람 라벨 골드의 완전 대체가 아니라, **retrieval 회귀 테스트용 baseline**.
적재 단계마다 같은 쿼리로 같은 청크가 retrieval 되는지 확인하는 게 목적.

설계 §C-6 카테고리:
  정형수치 40 / 시계열 30 / 비교 30 / 자유서술 30 / no-answer 30 / 충돌 20 / 시점 20 = 200

생성 룰 (수동 라벨 없이 데이터 구조로부터 합성):
- 정형수치: fnlttSinglAcntAll 의 (corp, year, account_nm) → "{corp} {year} {account_nm}"
- 시계열  : variant=comparison 청크 → "{corp} {account_nm} 추이"
- 비교    : 같은 (year, account_id) 의 2개 회사 쌍 → "{c1} vs {c2} {account_nm}"
- 자유서술: text_micro/macro 의 section_headings → 헤딩 자체를 쿼리로
- no-answer: 5사 외 회사 + DART 미공시 endpoint → 정답 없음
- 충돌    : 같은 fact 가 다중 출처에 다른 값 (현재 데이터엔 적어서 placeholder)
- 시점    : 특정 rcept_no/date 의 임원·주주 → "{date} 기준 {corp} 임원"

각 골드 항목:
  id, query, category, expected_chunk_ids (1~N), expected_corp_codes, no_answer
"""
from __future__ import annotations
import json, random, sys
from pathlib import Path

from polaris.config import mariadb_conn

OUT = Path(__file__).parent / "v1.yml"
random.seed(42)

CORP_NAMES = {"00126380":"삼성전자","00164779":"SK하이닉스","00118804":"동진쎄미켐",
              "01489648":"솔브레인","00161383":"한미반도체"}


def fetch_all(sql, *args):
    conn = mariadb_conn(); cur = conn.cursor()
    cur.execute(sql, args)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows


def gold_정형수치(n=40):
    """fnlttSinglAcntAll 의 variant=full 청크 — 수치 1개."""
    rows = fetch_all("""
        SELECT chunk_id, corp_code, embedding_text, bsns_year
        FROM chunk_index
        WHERE endpoint='fnlttSinglAcntAll'
          AND chunk_type='table_nl'
          AND embedding_text LIKE '%%사업보고서%%'
          AND bsns_year IS NOT NULL
        ORDER BY RAND()
        LIMIT %s
    """, n * 3)  # over-sample, 필터링 후 cut
    out = []
    for cid, corp, txt, year in rows:
        # "삼성전자(00126380)의 2024년 사업보고서 별도재무제표 손익계산서 항목 '매출액'..."
        import re
        m = re.search(r"항목 '([^']+)'", txt)
        if not m: continue
        acc = m.group(1)
        if "(공시되지" in acc: continue
        query = f"{CORP_NAMES[corp]} {year}년 {acc}"
        out.append({"query": query, "category": "정형수치", "expected_chunk_ids": [cid],
                    "expected_corp_codes": [corp], "no_answer": False})
        if len(out) >= n: break
    return out


def gold_시계열(n=30):
    """variant=comparison 청크 — 3기 추이."""
    rows = fetch_all("""
        SELECT chunk_id, corp_code, embedding_text, bsns_year
        FROM chunk_index
        WHERE variant='comparison' AND chunk_type='table_nl'
        ORDER BY RAND()
        LIMIT %s
    """, n * 2)
    import re
    out = []
    for cid, corp, txt, year in rows:
        m = re.search(r"(별도|연결)\s+(\S+)\s+3기 추이", txt)
        if not m: continue
        acc = m.group(2)
        query = f"{CORP_NAMES[corp]} {acc} 추이"
        out.append({"query": query, "category": "시계열", "expected_chunk_ids": [cid],
                    "expected_corp_codes": [corp], "no_answer": False})
        if len(out) >= n: break
    return out


def gold_비교(n=30):
    """같은 (year, account_nm) 의 2개 corp full 청크 쌍 → 둘 다 expected."""
    rows = fetch_all("""
        SELECT chunk_id, corp_code, endpoint, embedding_text, bsns_year
        FROM chunk_index
        WHERE endpoint='fnlttSinglAcntAll' AND variant='full' AND chunk_type='table_nl'
          AND bsns_year IN (2024, 2025)
        LIMIT 8000
    """)
    # account_nm 추출 후 (year, acc_nm) 기준 corp 쌍 매칭
    import re, itertools
    by_key: dict = {}
    for cid, corp, ep, txt, year in rows:
        m = re.search(r"항목 '([^']+)'", txt)
        if not m: continue
        acc = m.group(1)
        if "(공시되지" in acc: continue
        by_key.setdefault((year, acc), []).append((cid, corp))
    pairs = []
    for k, lst in by_key.items():
        if len(lst) >= 2:
            for c1, c2 in itertools.combinations(lst, 2):
                if c1[1] == c2[1]: continue
                pairs.append((k, c1, c2))
    random.shuffle(pairs)
    out = []
    for (year, acc), (cid1, corp1), (cid2, corp2) in pairs[:n]:
        query = f"{CORP_NAMES[corp1]} vs {CORP_NAMES[corp2]} {year}년 {acc}"
        out.append({"query": query, "category": "비교", "expected_chunk_ids": [cid1, cid2],
                    "expected_corp_codes": [corp1, corp2], "no_answer": False})
    return out


def gold_자유서술(n=30):
    """text_micro/macro — chunk_summary.summary 에서 첫 명사구를 쿼리로."""
    rows = fetch_all("""
        SELECT ci.chunk_id, ci.corp_code, cs.summary, ci.section_path
        FROM chunk_index ci
        JOIN chunk_summary cs ON ci.chunk_id=cs.chunk_id AND ci.run_id=cs.run_id
        WHERE ci.chunk_type IN ('text_micro','text_macro')
          AND CHAR_LENGTH(cs.summary) > 50
        ORDER BY RAND()
        LIMIT %s
    """, n * 3)
    import re
    out = []
    seen = set()
    for cid, corp, summ, sp in rows:
        # claude_temp 포맷: "{corp} {doc_type}의 '{section}' 섹션에서 ..."
        m = re.search(r"'([^']+)' 섹션", summ)
        if not m: continue
        topic = m.group(1).strip()
        # 너무 일반적·짧은 헤딩 제외
        if len(topic) < 4 or topic in seen: continue
        if any(skip in topic for skip in ("개요", "기타", "내용")) and len(topic) < 8: continue
        seen.add(topic)
        query = f"{CORP_NAMES[corp]} {topic}"
        out.append({"query": query, "category": "자유서술", "expected_chunk_ids": [cid],
                    "expected_corp_codes": [corp], "no_answer": False})
        if len(out) >= n: break
    return out


def gold_no_answer(n=30):
    """5사 외 회사 + 미공시 endpoint — 정답 없음 (검색 후 top-k 가 낮은 점수여야 함)."""
    out_corps = [("LG화학", "051910"), ("SK이노베이션", "096770"),
                 ("HD현대중공업", "329180"), ("포스코홀딩스", "005490"),
                 ("카카오", "035720"), ("네이버", "035420")]
    fields = ["2024년 매출액", "2023년 자산총계", "2024년 영업이익",
              "임원 현황", "감사의견", "최대주주 지분율"]
    out = []
    for _ in range(n):
        c, _ = random.choice(out_corps)
        f = random.choice(fields)
        out.append({"query": f"{c} {f}", "category": "no_answer",
                    "expected_chunk_ids": [], "expected_corp_codes": [],
                    "no_answer": True})
    return out


def gold_충돌(n=20):
    """현재 데이터엔 의도적 충돌 없음 — placeholder 로 같은 사실 다중 출처 케이스 생성.

    예: 같은 회사 같은 년도 매출액이 별도/연결 다르게 나오는 경우 → 의도 충돌 N/A
    대신 같은 사실이 분기/사업보고서 양쪽에 나오는 케이스 (정상이나 retrieval 정합 확인용)
    """
    rows = fetch_all("""
        SELECT chunk_id, corp_code, embedding_text, bsns_year, reprt_code
        FROM chunk_index
        WHERE endpoint='accnutAdtorNmNdAdtOpinion' AND chunk_type='table_nl'
        ORDER BY RAND()
        LIMIT %s
    """, n * 2)
    out = []
    seen_pair = set()
    for cid, corp, txt, year, rc in rows:
        key = (corp, year)
        if key in seen_pair: continue
        seen_pair.add(key)
        query = f"{CORP_NAMES[corp]} {year}년 감사의견"
        out.append({"query": query, "category": "출처_충돌_검증",
                    "expected_chunk_ids": [cid], "expected_corp_codes": [corp],
                    "no_answer": False,
                    "note": "분기·사업보고서 다중 출처 — 정답 1건"})
        if len(out) >= n: break
    return out


def gold_시점(n=20):
    """특정 date 기준 임원·주주 — 시점 정확성 확인."""
    rows = fetch_all("""
        SELECT chunk_id, corp_code, embedding_text, bsns_year
        FROM chunk_index
        WHERE endpoint='exctvSttus' AND chunk_type='table_nl' AND bsns_year IS NOT NULL
        ORDER BY RAND()
        LIMIT %s
    """, n * 2)
    out = []
    seen = set()
    for cid, corp, txt, year in rows:
        import re
        m = re.search(r"임원\s+'([^']+)'", txt)
        if not m: continue
        nm = m.group(1)
        if (corp, year, nm) in seen: continue
        seen.add((corp, year, nm))
        query = f"{year}년 기준 {CORP_NAMES[corp]} 임원 {nm}"
        out.append({"query": query, "category": "시점", "expected_chunk_ids": [cid],
                    "expected_corp_codes": [corp], "no_answer": False})
        if len(out) >= n: break
    return out


def main():
    print("[gold v1 생성]")
    gold = []
    for name, fn, n in [
        ("정형수치", gold_정형수치, 40),
        ("시계열",   gold_시계열,   30),
        ("비교",     gold_비교,     30),
        ("자유서술", gold_자유서술, 30),
        ("no_answer", gold_no_answer, 30),
        ("충돌",     gold_충돌,     20),
        ("시점",     gold_시점,     20),
    ]:
        items = fn(n)
        for i, it in enumerate(items, 1):
            it["id"] = f"{name}_{i:03d}"
        gold.extend(items)
        print(f"  {name}: {len(items)}/{n}")

    # YAML 출력 (간단 직접 작성 — pyyaml 의존 회피)
    lines = ["# gold v1 — POLARIS retrieval baseline (200 queries)",
             "# 생성: tests/gold/_generate_v1.py  / seed=42",
             "# 7 카테고리 분배 + 정답 chunk_id 라벨 (적재된 데이터 기반)",
             f"# 총 {len(gold)} queries", ""]
    for g in gold:
        lines.append(f"- id: {g['id']}")
        lines.append(f"  query: {json.dumps(g['query'], ensure_ascii=False)}")
        lines.append(f"  category: {g['category']}")
        lines.append(f"  no_answer: {str(g['no_answer']).lower()}")
        if g.get("expected_chunk_ids"):
            lines.append(f"  expected_chunk_ids: [{', '.join(g['expected_chunk_ids'])}]")
        else:
            lines.append(f"  expected_chunk_ids: []")
        if g.get("expected_corp_codes"):
            lines.append(f"  expected_corp_codes: [{', '.join(g['expected_corp_codes'])}]")
        if g.get("note"):
            lines.append(f"  note: {json.dumps(g['note'], ensure_ascii=False)}")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n[저장] {OUT.relative_to(Path.cwd())}")
    print(f"  총 {len(gold)} queries")


if __name__ == "__main__":
    main()
