"""GET /api/company/{corp} — 회사 프로파일 (노드 클릭 드릴다운).

재무: FinMetric 3,957개 세부계정 중 헤드라인만 선별(매출/영업이익/순이익/자산/부채, 연결 우선·최신연도).
임원: EXECUTIVE_OF / 자회사: INVESTS_IN qota≥50 / 제품: DEVELOPS / 최신뉴스: document_unified.
확장: shareholders(대주주) / stock(주가요약) / overview(기업개요) / disputes(분쟁).
"""
from __future__ import annotations

import json
import re

from fastapi import APIRouter

from ..db import mariadb, neo4j
from ..models import KV, CompanyProfile, DisputeItem, Exec, NewsItem, Shareholder, StockSummary, Subsidiary
from ..relations import SEED_CORPS

router = APIRouter(tags=["company"])

# account_id 기반 헤드라인 8지표 (fundamentals.py 와 동일 매핑)
_FIN_ACCOUNT_LABEL: dict[str, str] = {
    "ifrs-full_Revenue":                                          "매출액",
    "dart_OperatingIncomeLoss":                                   "영업이익",
    "ifrs-full_ProfitLoss":                                       "당기순이익",
    "ifrs-full_Assets":                                           "자산총계",
    "ifrs-full_Liabilities":                                      "부채총계",
    "ifrs-full_Equity":                                           "자본총계",
    "ifrs-full_CashFlowsFromUsedInOperatingActivities":           "영업활동현금흐름",
    "ifrs-full_BasicEarningsLossPerShare":                        "기본주당순이익",
}
_FIN_ACCOUNT_ORDER: list[str] = list(_FIN_ACCOUNT_LABEL.keys())

FIN = """
MATCH (o:Organization {corp_code: $corp})-->(m:FinMetric)
WHERE m.account_id IN $account_ids AND m.reprt_code = '11011'
RETURN m.account_id AS account_id, m.year AS year, m.value AS value, m.fs_div AS fs
"""
EXECS = "MATCH (p:Person)-[r:EXECUTIVE_OF]->(:Organization {corp_code: $corp}) RETURN p.name AS name, r.position AS position LIMIT 60"
SUBS = ("MATCH (:Organization {corp_code: $corp})-[r:INVESTS_IN]->(t:Organization) "
        "RETURN coalesce(t.name, t.corp_code, t.ext_id) AS name, r.qota_rt AS stake")
PRODS = "MATCH (:Organization {corp_code: $corp})-[:DEVELOPS]->(p) RETURN DISTINCT coalesce(p.name, p.ext_id) AS name LIMIT 15"
SHAREHOLDERS = ("MATCH (s)-[r:IS_MAJOR_SHAREHOLDER_OF]->(o:Organization {corp_code: $corp}) "
                "WHERE coalesce(s.name,'') <> '계' AND coalesce(s.name,'') <> '합계' "
                "RETURN coalesce(s.name, s.corp_code, s.ext_id) AS name, r.qota_rt AS stake "
                "ORDER BY coalesce(r.qota_rt, 0) DESC")


def _to_float(v) -> float | None:
    """숫자/숫자문자열 → float, 빈문자열·None·비숫자 → None (qota_rt 가 '' 인 경우 방어)."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _dedup_shareholders(rows: list[dict], limit: int = 10):
    """정규화 이름으로 중복 제거(최대 지분 유지), 한 글자/합계 제외 → (name, stake) 상위 N."""
    best: dict[str, tuple[str, float | None]] = {}
    for r in rows:
        nm = (r.get("name") or "").strip()
        if len(nm) < 2:
            continue
        key = re.sub(r"\s+|㈜|\(주\)|\(특별계정\)", "", nm)
        stk = _to_float(r.get("stake"))
        cur = best.get(key)
        if cur is None or (stk is not None and (cur[1] is None or stk > cur[1])):
            best[key] = (nm, stk)
    return sorted(best.values(), key=lambda x: (x[1] or 0), reverse=True)[:limit]


# 출자처 분류: 투자조합·펀드 / 해외법인(약칭) / 기타(운영·계열)
_ABBR_SUB_RE = re.compile(r"^[A-Za-z][A-Za-z0-9\-.&]{1,9}$")
_FUND_SUB_RE = re.compile(r"(조합|투자신탁|펀드|사모|유한책임)")


def _classify_sub(name: str) -> str:
    if _FUND_SUB_RE.search(name):
        return "fund"
    if _ABBR_SUB_RE.match(name):
        return "overseas"
    return "other"


def _summarize_subs(rows: list[dict], top: int = 6):
    """대표 운영·계열 상위 top + 분류 카운트 요약행(stake=None). 평면 수천건 → 정리."""
    groups = {"fund": 0, "overseas": 0, "other": 0}
    other_best: dict[str, float | None] = {}  # 이름 기준 중복 제거(필링별 중복 엣지)
    for r in rows:
        nm = (r.get("name") or "").strip()
        if not nm:
            continue
        cat = _classify_sub(nm)
        groups[cat] += 1
        if cat == "other":
            st = _to_float(r.get("stake"))
            if nm not in other_best or (st is not None and (other_best[nm] is None or st > other_best[nm])):
                other_best[nm] = st
    uniq = sorted(other_best.items(), key=lambda x: (x[1] or 0), reverse=True)
    out: list[tuple[str, float | None]] = list(uniq[:top])
    rest_other = max(0, len(other_best) - len(out))
    if groups["overseas"]:
        out.append((f"해외 출자법인 {groups['overseas']}건", None))
    if groups["fund"]:
        out.append((f"투자조합·펀드 {groups['fund']}건", None))
    if rest_other:
        out.append((f"기타 출자 {rest_other}건", None))
    return out


def _summarize_shareholders(rows: list[dict], top: int = 6):
    """대주주 상위 top(지분율) + '외 N인 · 특수관계인' 요약행(stake=None)."""
    ded = _dedup_shareholders(rows, limit=100000)
    out = list(ded[:top])
    more = len(ded) - len(out)
    if more > 0:
        out.append((f"외 {more}인 · 특수관계인", None))
    return out


ORG_OVERVIEW = ("MATCH (o:Organization {corp_code: $corp}) "
                "RETURN o.stock_code AS stock_code, o.founded AS founded, o.jurirno AS jurirno")
DISPUTES = ("MATCH (o:Organization {corp_code: $corp})-[r:LITIGATION]-(x) "
            "RETURN coalesce(x.name, x.corp_code, x.ext_id) AS target, "
            "coalesce(r.evidence_count, 1) AS evidence_count LIMIT 10")

_ENSURE_STOCK = """
CREATE TABLE IF NOT EXISTS stock_daily (
    corp_code VARCHAR(8) NOT NULL,
    date DATE NOT NULL,
    close DOUBLE,
    change_pct DOUBLE,
    volume BIGINT,
    PRIMARY KEY (corp_code, date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


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


def _fetch_stock(corp: str) -> StockSummary | None:
    conn = mariadb()
    try:
        with conn.cursor() as cur:
            cur.execute(_ENSURE_STOCK)
        conn.commit()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DATE_FORMAT(date, '%%Y-%%m-%%d') AS d, close, change_pct "
                "FROM stock_daily WHERE corp_code=%s ORDER BY date DESC LIMIT 30",
                (corp,),
            )
            rows = cur.fetchall()
        if not rows:
            return None
        latest = rows[0]
        spark = [float(r["close"]) for r in reversed(rows) if r["close"] is not None]
        return StockSummary(
            lastClose=float(latest["close"]),
            changePct=float(latest["change_pct"]) if latest["change_pct"] is not None else None,
            asOf=latest["d"],
            spark=spark,
        )
    except Exception:
        return None
    finally:
        conn.close()


@router.get("/company/{corp}", response_model=CompanyProfile)
def company(corp: str):
    with neo4j().session() as s:
        name_row = s.run("MATCH (o:Organization {corp_code: $corp}) RETURN coalesce(o.name, o.corp_code) AS nm", corp=corp).single()
        fin_rows = s.run(FIN, corp=corp, account_ids=_FIN_ACCOUNT_ORDER).data()
        exec_rows = s.run(EXECS, corp=corp).data()
        subs = [Subsidiary(name=n, stake=st) for n, st in _summarize_subs(s.run(SUBS, corp=corp).data())]
        products = [r["name"] for r in s.run(PRODS, corp=corp).data() if r["name"]]
        shareholder_rows = s.run(SHAREHOLDERS, corp=corp).data()
        overview_row = s.run(ORG_OVERVIEW, corp=corp).single()
        dispute_rows = s.run(DISPUTES, corp=corp).data()

    name = SEED_CORPS.get(corp) or (name_row["nm"] if name_row else corp)

    # 임원 — 이름 중복 제거(여러 run/직책)
    execs, seen = [], set()
    for r in exec_rows:
        if r["name"] and r["name"] not in seen:
            seen.add(r["name"])
            execs.append(Exec(name=r["name"], position=r["position"]))

    # 재무 — account_id 기반, 최신연도·CFS 우선·MAX(abs(value))
    fin_best: dict[str, tuple] = {}  # account_id -> (year, fs_priority, abs_val, raw_val)
    for r in fin_rows:
        acct = r["account_id"]
        val = r["value"]
        if val is None:
            continue
        year = int(r["year"]) if r["year"] is not None else 0
        fs_pri = 1 if r["fs"] == "CFS" else 0
        abs_val = abs(float(val))
        cur = fin_best.get(acct)
        if cur is None or (year, fs_pri, abs_val) > (cur[0], cur[1], cur[2]):
            fin_best[acct] = (year, fs_pri, abs_val, val)
    finance = [
        KV(label=_FIN_ACCOUNT_LABEL[acct], value=fmt_won(fin_best[acct][3]))
        for acct in _FIN_ACCOUNT_ORDER
        if acct in fin_best
    ]

    # 대주주 — qota_rt(지분율) 기준 중복 제거·정렬
    shareholders = [Shareholder(name=nm, stake=stk) for nm, stk in _summarize_shareholders(shareholder_rows)]

    # 기업개요 KV (값 있는 것만)
    overview: list[KV] = []
    if overview_row:
        if overview_row.get("stock_code"):
            overview.append(KV(label="종목코드", value=str(overview_row["stock_code"])))
        if overview_row.get("founded"):
            overview.append(KV(label="설립", value=str(overview_row["founded"])))
        if overview_row.get("jurirno"):
            overview.append(KV(label="법인번호", value=str(overview_row["jurirno"])))

    # 분쟁
    disputes = [
        DisputeItem(target=r["target"] or "불명", evidenceCount=int(r["evidence_count"] or 1))
        for r in dispute_rows
    ]

    # 주가 요약
    stock = _fetch_stock(corp)

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

    return CompanyProfile(
        code=corp, name=name, finance=finance, execs=execs[:20],
        subsidiaries=subs, products=products, recentNews=news,
        shareholders=shareholders, stock=stock, overview=overview, disputes=disputes,
    )
