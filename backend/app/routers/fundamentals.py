"""GET /api/financials/{corp}, /api/ownership/{corp}, /api/macro — 재무/지분/거시지표."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..db import neo4j
from ..models import FinancialPoint, MacroPoint, OwnershipItem

router = APIRouter(tags=["fundamentals"])

# account_id → 한글 표시명 매핑 (8대 지표)
ACCOUNT_LABEL: dict[str, str] = {
    "ifrs-full_Revenue":                                          "매출액",
    "dart_OperatingIncomeLoss":                                   "영업이익",
    "ifrs-full_ProfitLoss":                                       "당기순이익",
    "ifrs-full_Assets":                                           "자산총계",
    "ifrs-full_Liabilities":                                      "부채총계",
    "ifrs-full_Equity":                                           "자본총계",
    "ifrs-full_CashFlowsFromUsedInOperatingActivities":           "영업활동현금흐름",
    "ifrs-full_BasicEarningsLossPerShare":                        "기본주당순이익",
}

# 출력 순서 보장
ACCOUNT_ORDER: list[str] = list(ACCOUNT_LABEL.keys())

# 거시지표 큐레이션 — 각 stat_code/이름당 대표 1개(total_rows 최대)만. (코드당 수백 하위계열 존재)
MACRO_CURATED_CODES: list[tuple[str, str]] = [
    ("722Y001", "기준금리·여수신금리"),
    ("731Y004", "대원화환율"),
    ("404Y014", "생산자물가지수"),
]
MACRO_CURATED_NAMES: list[tuple[str, str]] = [
    ("소비자물가지수", "소비자물가지수"),
    ("전산업생산", "전산업생산지수"),
    ("경제활동별 GDP", "GDP·GNI"),
    ("국제수지", "국제수지"),
]

# account_id 기반 쿼리: reprt_code='11011'(연간) + account_id IN 8지표
FIN_QUERY = """
MATCH (o:Organization {corp_code: $corp})-[:HAS_METRIC]->(m:FinMetric)
WHERE m.account_id IN $account_ids AND m.reprt_code = '11011'
RETURN m.account_id AS account_id, m.year AS year, m.value AS value, m.fs_div AS fs_div
ORDER BY m.year ASC
"""

# 분기용 쿼리: 4개 reprt_code 모두 조회
FIN_QUARTER_QUERY = """
MATCH (o:Organization {corp_code: $corp})-[:HAS_METRIC]->(m:FinMetric)
WHERE m.account_id IN $account_ids
  AND m.reprt_code IN ['11011', '11012', '11013', '11014']
RETURN m.account_id AS account_id, m.year AS year, m.value AS value,
       m.fs_div AS fs_div, m.reprt_code AS reprt_code
ORDER BY m.year ASC
"""

# stock 지표 account_id 집합 (시점값, 누적 차감 금지)
STOCK_ACCOUNT_IDS: set[str] = {
    "ifrs-full_Assets",
    "ifrs-full_Liabilities",
    "ifrs-full_Equity",
}

OWNERSHIP_SUBS_QUERY = """
MATCH (o:Organization {corp_code: $corp})-[r:INVESTS_IN]->(t:Organization)
RETURN coalesce(t.name, t.corp_code, t.ext_id) AS name, r.qota_rt AS stake
"""

OWNERSHIP_SH_QUERY = """
MATCH (s)-[r:IS_MAJOR_SHAREHOLDER_OF]->(o:Organization {corp_code: $corp})
WHERE coalesce(s.name,'') <> '계' AND coalesce(s.name,'') <> '합계'
RETURN coalesce(s.name, s.corp_code, s.ext_id) AS name, r.qota_rt AS stake
ORDER BY coalesce(r.qota_rt, 0) DESC
"""

MACRO_ONE_BY_CODE = """
MATCH (m:MacroIndicator)
WHERE m.stat_code = $code AND m.latest_value IS NOT NULL
RETURN m.latest_value AS value, m.unit AS unit, m.latest_time AS asof, m.source AS source
ORDER BY coalesce(m.total_rows, 0) DESC LIMIT 1
"""

MACRO_ONE_BY_NAME = """
MATCH (m:MacroIndicator)
WHERE m.name CONTAINS $kw AND m.latest_value IS NOT NULL
RETURN m.latest_value AS value, m.unit AS unit, m.latest_time AS asof, m.source AS source
ORDER BY coalesce(m.total_rows, 0) DESC LIMIT 1
"""


def _pick_best_rows(rows: list[dict], key_fields: tuple) -> dict[tuple, dict]:
    """(account_id, year[, reprt_code]) 키 단위 CFS 우선 · MAX(abs(value)) 선택."""
    best: dict[tuple, dict] = {}
    for r in rows:
        acct = r["account_id"]
        year = int(r["year"]) if r["year"] is not None else 0
        val = r["value"]
        fs = r["fs_div"]
        if val is None:
            continue
        key = tuple(r[f] if f != "year" else year for f in key_fields)
        ex = best.get(key)
        if ex is None:
            best[key] = {**r, "year": year}
        else:
            if fs == "CFS" and ex["fs_div"] != "CFS":
                best[key] = {**r, "year": year}
            elif fs == ex["fs_div"]:
                if abs(float(val)) > abs(float(ex["value"])):
                    best[key] = {**r, "year": year}
    return best


@router.get("/financials/{corp}", response_model=list[FinancialPoint])
def get_financials(
    corp: str,
    period: str = Query(default="annual", description="annual | quarter"),
) -> list[FinancialPoint]:
    """8대 account_id 기반 재무지표.

    period='annual'(기본): reprt_code='11011', FinancialPoint.period='FY'.
    period='quarter': 4개 reprt_code 조회 후 flow 지표는 누적 차감으로 분기값 환산,
                      stock 지표(자산/부채/자본총계)는 각 reprt 시점값 그대로.
    CFS 우선·없으면 OFS, 동일 fs_div 내 MAX(abs(value)).
    """
    if period != "quarter":
        # ── annual (기존 동작 100% 유지) ──────────────────────────────────
        with neo4j().session() as s:
            rows = s.run(FIN_QUERY, corp=corp, account_ids=ACCOUNT_ORDER).data()

        best = _pick_best_rows(rows, ("account_id", "year"))

        acct_order = {a: i for i, a in enumerate(ACCOUNT_ORDER)}
        sorted_items = sorted(
            best.values(),
            key=lambda x: (acct_order.get(x["account_id"], 99), x["year"]),
        )
        return [
            FinancialPoint(
                indicator=ACCOUNT_LABEL[item["account_id"]],
                year=item["year"],
                value=float(item["value"]),
                fsDiv=item["fs_div"],
                period="FY",
            )
            for item in sorted_items
            if item["account_id"] in ACCOUNT_LABEL
        ]

    # ── quarter ────────────────────────────────────────────────────────────
    with neo4j().session() as s:
        rows = s.run(FIN_QUARTER_QUERY, corp=corp, account_ids=ACCOUNT_ORDER).data()

    # (account_id, year, reprt_code) 단위 CFS 우선 · MAX(abs) 선택
    best_q = _pick_best_rows(rows, ("account_id", "year", "reprt_code"))

    # best_q → {(account_id, year): {reprt_code: value, fs_div: ...}} 구조로 재편
    # fs_div는 동일 (account_id, year) 내 CFS 우선 정책상 통일됨
    by_acct_year: dict[tuple[str, int], dict[str, float | None]] = {}
    fsdiv_map: dict[tuple[str, int], str] = {}

    for key, item in best_q.items():
        acct = item["account_id"]
        year = item["year"]
        reprt = item["reprt_code"]
        val = float(item["value"])
        fs = item["fs_div"]

        ay_key = (acct, year)
        if ay_key not in by_acct_year:
            by_acct_year[ay_key] = {}
            fsdiv_map[ay_key] = fs
        else:
            # CFS 우선: 이미 CFS면 유지, OFS였는데 CFS 들어오면 교체
            if fs == "CFS" and fsdiv_map[ay_key] != "CFS":
                fsdiv_map[ay_key] = "CFS"
        by_acct_year[ay_key][reprt] = val

    # 분기값 계산
    # reprt_code 저장값: 11013=1Q, 11012=2Q, 11014=3Q (각 단일분기), 11011=연간(FY)
    # → flow 지표는 Q1~Q3 그대로, Q4=연간-(Q1+Q2+Q3). (검증: 분기합 == 연간)
    QUARTER_MAP = {
        "1Q": "11013",
        "2Q": "11012",
        "3Q": "11014",
        "4Q": "11011",
    }
    QUARTER_ORDER = ["1Q", "2Q", "3Q", "4Q"]

    results: list[dict] = []
    for (acct, year), reprt_vals in by_acct_year.items():
        is_stock = acct in STOCK_ACCOUNT_IDS
        fs = fsdiv_map[(acct, year)]

        for q_label in QUARTER_ORDER:
            reprt = QUARTER_MAP[q_label]
            base_val = reprt_vals.get(reprt)
            if base_val is None:
                continue  # 해당 reprt 누락 → 분기 건너뜀

            if is_stock:
                # stock 지표: 각 reprt 의 시점값 그대로
                q_val = base_val
            else:
                # flow 지표: 저장된 11013/11012/11014 는 이미 단일분기(Q1/Q2/Q3) 값.
                if q_label in ("1Q", "2Q", "3Q"):
                    q_val = base_val  # 단일분기 값 그대로
                else:  # 4Q = 연간(11011) - (Q1+Q2+Q3)
                    q1 = reprt_vals.get("11013")
                    q2 = reprt_vals.get("11012")
                    q3 = reprt_vals.get("11014")
                    if q1 is None or q2 is None or q3 is None:
                        continue
                    q_val = base_val - (q1 + q2 + q3)

            results.append({
                "account_id": acct,
                "year": year,
                "value": q_val,
                "fs_div": fs,
                "period": q_label,
            })

    acct_order = {a: i for i, a in enumerate(ACCOUNT_ORDER)}
    period_order = {p: i for i, p in enumerate(QUARTER_ORDER)}
    results.sort(key=lambda x: (x["year"], period_order.get(x["period"], 9), acct_order.get(x["account_id"], 99)))

    return [
        FinancialPoint(
            indicator=ACCOUNT_LABEL[item["account_id"]],
            year=item["year"],
            value=float(item["value"]),
            fsDiv=item["fs_div"],
            period=item["period"],
        )
        for item in results
        if item["account_id"] in ACCOUNT_LABEL
    ]


@router.get("/ownership/{corp}", response_model=list[OwnershipItem])
def get_ownership(corp: str) -> list[OwnershipItem]:
    """자회사/출자(INVESTS_IN) + 대주주(IS_MAJOR_SHAREHOLDER_OF) 합쳐서 반환."""
    with neo4j().session() as s:
        sub_rows = s.run(OWNERSHIP_SUBS_QUERY, corp=corp).data()
        sh_rows = s.run(OWNERSHIP_SH_QUERY, corp=corp).data()

    from .company import _summarize_shareholders, _summarize_subs
    result: list[OwnershipItem] = []
    for nm, stk in _summarize_subs(sub_rows):
        result.append(OwnershipItem(name=nm, stake=stk, kind="subsidiary"))
    for nm, stk in _summarize_shareholders(sh_rows):
        result.append(OwnershipItem(name=nm, stake=stk, kind="shareholder"))
    return result


def _macro_point(label: str, rec) -> MacroPoint | None:
    if not rec or rec["value"] is None:
        return None
    return MacroPoint(
        name=label,
        value=str(rec["value"]),
        unit=str(rec["unit"]) if rec["unit"] else None,
        asOf=str(rec["asof"]) if rec["asof"] else None,
        source=str(rec["source"]) if rec["source"] else None,
    )


@router.get("/macro", response_model=list[MacroPoint])
def get_macro() -> list[MacroPoint]:
    """큐레이션 거시지표 최신값(코드/이름당 대표 1개). corp 파라미터 없음."""
    result: list[MacroPoint] = []
    with neo4j().session() as s:
        for code, label in MACRO_CURATED_CODES:
            mp = _macro_point(label, s.run(MACRO_ONE_BY_CODE, code=code).single())
            if mp:
                result.append(mp)
        for kw, label in MACRO_CURATED_NAMES:
            mp = _macro_point(label, s.run(MACRO_ONE_BY_NAME, kw=kw).single())
            if mp:
                result.append(mp)
    return result
