"""계정 사전 — 한국어 재무용어 → IFRS account_id (함정 C 해결).

배경: fin_metric.account_id 는 IFRS 택소노미 원본명(`ifrs-full_Revenue`)이라
사용자의 "매출"을 그 코드로 번역해야 쿼리가 된다. 단답식 재무질문 라우팅의 첫 관문.

용도:
- resolve_account("매출") -> "ifrs-full_Revenue"  (질문어휘→코드, 쿼리 전 번역)
- LLM 슬롯필링 프롬프트에 ACCOUNTS 목록(한국어명)을 넣어 모델이 account_id 를 고르게 함.

규약(함정 A): 재무 단건 조회는 항상 연간·연결 기본 필터를 건다.
  reprt_code='11011'(사업보고서=연간), fs_div='CFS'(연결). 분기/별도는 질문이 명시할 때만.
  정확한 값의 SSOT = MariaDB fin_metric (Neo4j FinMetric 은 멀티홉 탐색용 미러).

수록 범위: 현재 3사(+extra) 데이터에 실재하는 account_id 만(검증됨). 확장 시 fin_metric
GROUP BY account_id 로 빈도 확인 후 추가.
"""
from __future__ import annotations

# 재무 단건 조회 기본 필터 (함정 A — 중복값 8개 중 정답 1개 집기)
DEFAULT_REPRT_CODE = "11011"  # 사업보고서(연간). 11012=반기·11013=1분기·11014=3분기
DEFAULT_FS_DIV = "CFS"        # 연결. OFS=별도

REPRT_LABELS = {
    "11011": "연간(사업보고서)",
    "11012": "반기",
    "11013": "1분기",
    "11014": "3분기",
}
FS_LABELS = {"CFS": "연결", "OFS": "별도"}

# account_id -> (대표 한국어명, 재무제표, [별칭...])
#   재무제표: PL=손익계산서 · BS=재무상태표 · CF=현금흐름표
ACCOUNTS: dict[str, tuple[str, str, list[str]]] = {
    # ── 손익계산서 (PL) ──
    "ifrs-full_Revenue": ("매출액", "PL", ["매출", "수익", "매출고", "영업수익", "sales", "revenue"]),
    "ifrs-full_CostOfSales": ("매출원가", "PL", ["원가", "cost of sales"]),
    "ifrs-full_GrossProfit": ("매출총이익", "PL", ["매출총손익", "gross profit"]),
    "dart_OperatingIncomeLoss": ("영업이익", "PL", ["영업손익", "영업이익률", "operating income", "operating profit"]),
    "ifrs-full_ProfitLossBeforeTax": ("법인세차감전순이익", "PL", ["세전이익", "법인세비용차감전순이익", "세전순이익", "pretax income"]),
    "ifrs-full_IncomeTaxExpenseContinuingOperations": ("법인세비용", "PL", ["법인세", "income tax"]),
    "ifrs-full_ProfitLoss": ("당기순이익", "PL", ["순이익", "당기순손익", "당기순손실", "net income", "net profit"]),
    "ifrs-full_FinanceIncome": ("금융수익", "PL", ["finance income"]),
    "ifrs-full_FinanceCosts": ("금융비용", "PL", ["금융원가", "finance costs"]),
    "ifrs-full_BasicEarningsLossPerShare": ("기본주당이익", "PL", ["주당순이익", "기본주당순이익", "eps", "주당이익"]),
    # ── 재무상태표 (BS) ──
    "ifrs-full_Assets": ("자산총계", "BS", ["총자산", "자산", "total assets"]),
    "ifrs-full_CurrentAssets": ("유동자산", "BS", ["current assets"]),
    "ifrs-full_NoncurrentAssets": ("비유동자산", "BS", ["noncurrent assets"]),
    "ifrs-full_Liabilities": ("부채총계", "BS", ["총부채", "부채", "total liabilities"]),
    "ifrs-full_CurrentLiabilities": ("유동부채", "BS", ["current liabilities"]),
    "ifrs-full_NoncurrentLiabilities": ("비유동부채", "BS", ["noncurrent liabilities"]),
    "ifrs-full_Equity": ("자본총계", "BS", ["총자본", "자기자본", "자본", "total equity", "순자산"]),
    "ifrs-full_IssuedCapital": ("자본금", "BS", ["발행자본", "issued capital"]),
    "ifrs-full_RetainedEarnings": ("이익잉여금", "BS", ["유보금", "retained earnings"]),
    "ifrs-full_CashAndCashEquivalents": ("현금및현금성자산", "BS", ["현금", "현금성자산", "cash"]),
    "ifrs-full_PropertyPlantAndEquipment": ("유형자산", "BS", ["설비자산", "ppe", "property plant and equipment"]),
    "ifrs-full_Inventories": ("재고자산", "BS", ["재고", "inventory", "inventories"]),
    # ── 현금흐름표 (CF) ──
    "ifrs-full_CashFlowsFromUsedInOperatingActivities": ("영업활동현금흐름", "CF", ["영업현금흐름", "영업활동으로인한현금흐름", "operating cash flow", "ocf"]),
}


def _norm(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "")


# 역인덱스: 정규화된 한국어명·별칭 -> account_id (1회 구축)
_LOOKUP: dict[str, str] = {}
for _aid, (_ko, _stmt, _aliases) in ACCOUNTS.items():
    _LOOKUP[_norm(_ko)] = _aid
    for _al in _aliases:
        _LOOKUP.setdefault(_norm(_al), _aid)


def resolve_account(term: str) -> str | None:
    """질문어휘 -> account_id. 완전일치 우선, 없으면 부분포함 매칭. 못 찾으면 None."""
    key = _norm(term)
    if not key:
        return None
    if key in _LOOKUP:
        return _LOOKUP[key]
    # 부분 포함(예: "삼성전자 매출액은" 안에서 "매출액" 찾기)
    for alias, aid in _LOOKUP.items():
        if alias and alias in key:
            return aid
    return None


def account_label(account_id: str) -> str:
    """account_id -> 대표 한국어명(없으면 원본 코드)."""
    rec = ACCOUNTS.get(account_id)
    return rec[0] if rec else account_id


def list_accounts() -> list[str]:
    """LLM 슬롯필링 프롬프트용 — '한국어명(account_id)' 목록."""
    return [f"{ko}({aid})" for aid, (ko, _s, _a) in ACCOUNTS.items()]
