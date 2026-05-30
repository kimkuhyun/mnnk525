"""GET /api/company/{corp} — 회사 프로파일 (노드 클릭 드릴다운).

재무: FinMetric 3,957개 세부계정 중 헤드라인만 선별(매출/영업이익/순이익/자산/부채, 연결 우선·최신연도).
임원: EXECUTIVE_OF / 자회사: INVESTS_IN qota≥50 / 제품: DEVELOPS / 최신뉴스: document_unified.
"""
from __future__ import annotations

import json

from fastapi import APIRouter

from ..db import mariadb, neo4j
from ..models import KV, CompanyProfile, Exec, NewsItem, Subsidiary
from ..relations import SEED_CORPS

router = APIRouter(tags=["company"])

HEADLINE = ["매출액", "영업이익", "당기순이익", "자산총계", "부채총계"]

FIN = """
MATCH (o:Organization {corp_code: $corp})-->(m:FinMetric)
WHERE m.indicator IN $headline
RETURN m.indicator AS ind, m.year AS year, m.value AS value, m.fs_div AS fs
"""
EXECS = "MATCH (p:Person)-[r:EXECUTIVE_OF]->(:Organization {corp_code: $corp}) RETURN p.name AS name, r.position AS position LIMIT 60"
SUBS = ("MATCH (:Organization {corp_code: $corp})-[r:INVESTS_IN]->(t:Organization) "
        "WHERE coalesce(r.qota_rt, 0) >= 50 "
        "RETURN coalesce(t.name, t.corp_code) AS name, r.qota_rt AS stake ORDER BY r.qota_rt DESC LIMIT 20")
PRODS = "MATCH (:Organization {corp_code: $corp})-[:DEVELOPS]->(p) RETURN DISTINCT coalesce(p.name, p.ext_id) AS name LIMIT 15"


def fmt_won(v) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return str(v)
    sign, n = ("-" if n < 0 else ""), abs(n)
    if n >= 1e12:
        return f"{sign}{n / 1e12:.1f}조원"
    if n >= 1e8:
        return f"{sign}{n / 1e8:,.0f}억원"
    return f"{sign}{n:,.0f}원"


@router.get("/company/{corp}", response_model=CompanyProfile)
def company(corp: str):
    with neo4j().session() as s:
        name_row = s.run("MATCH (o:Organization {corp_code: $corp}) RETURN coalesce(o.name, o.corp_code) AS nm", corp=corp).single()
        fin_rows = s.run(FIN, corp=corp, headline=HEADLINE).data()
        exec_rows = s.run(EXECS, corp=corp).data()
        subs = [Subsidiary(name=r["name"], stake=r["stake"]) for r in s.run(SUBS, corp=corp).data()]
        products = [r["name"] for r in s.run(PRODS, corp=corp).data() if r["name"]]

    name = SEED_CORPS.get(corp) or (name_row["nm"] if name_row else corp)

    # 임원 — 이름 중복 제거(여러 run/직책)
    execs, seen = [], set()
    for r in exec_rows:
        if r["name"] and r["name"] not in seen:
            seen.add(r["name"])
            execs.append(Exec(name=r["name"], position=r["position"]))

    # 재무 — 헤드라인별 최신연도·연결(CFS) 우선
    best: dict[str, tuple] = {}
    for r in fin_rows:
        score = (r["year"] or 0, 1 if r["fs"] == "CFS" else 0)
        if r["ind"] not in best or score > best[r["ind"]][0]:
            best[r["ind"]] = (score, r["value"])
    finance = [KV(label=ind, value=fmt_won(best[ind][1])) for ind in HEADLINE if ind in best]

    conn = mariadb()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT doc_id, title, DATE_FORMAT(ts, '%%Y-%%m-%%d') AS d, url, metadata "
            "FROM document_unified WHERE corp_code = %s AND source_type = 'news' ORDER BY ts DESC LIMIT 10",
            (corp,),
        )
        news = []
        for r in cur.fetchall():
            pub = None
            try:
                pub = (json.loads(r["metadata"]) or {}).get("publisher")
            except Exception:
                pass
            news.append(NewsItem(docId=r["doc_id"], title=r["title"] or "", date=r["d"] or "", url=r["url"] or "", publisher=pub))
    conn.close()

    return CompanyProfile(code=corp, name=name, finance=finance, execs=execs[:20],
                          subsidiaries=subs, products=products, recentNews=news)
