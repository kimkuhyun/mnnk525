"""트리거 키워드 — LLM 호출 사전 필터의 하나.

본문에 다음 키워드 1개라도 포함 + entity hit ≥ 2 인 청크만 LLM 호출.
통과율 < 30% 목표 (≈7,000 LLM 호출).

카테고리:
  events     : M&A·증자·계약·정정공시 등 (Event 후보)
  relations  : 공급·경쟁·자회사·생산 (Relation 후보)
  tech       : 도입·적용·전환 (USES_TECH 후보)
"""
from __future__ import annotations

TRIGGER_KEYWORDS: dict[str, list[str]] = {
    "events": [
        # M&A
        "인수", "합병", "M&A", "취득", "분할", "분할합병", "흡수합병",
        "주식 교환", "주식교환", "주식 이전", "주식이전",
        # 자본
        "증자", "유상증자", "무상증자", "감자", "유무상증자", "전환사채",
        "신주인수권", "교환사채", "사채 발행", "자기주식",
        # 영업
        "영업양수", "영업양도", "영업 양수", "영업 양도", "양수도",
        "공급계약", "단일판매", "공급 계약", "수주",
        # 임원·지분
        "임원 변경", "이사회 결의", "사내이사", "사외이사", "대표이사 선임",
        "최대주주 변경", "지분 매각", "지분 인수",
        # 시장
        "상장", "상장폐지", "코스피 이전",
        # 위기
        "부도", "법정관리", "회생절차", "정정공시", "해산", "소송",
    ],
    "relations": [
        "공급", "납품", "협력사", "협력업체", "공급망", "공급사",
        "고객사", "주요 고객", "원료 공급",
        "경쟁", "라이벌", "시장 점유율",
        "자회사", "관계회사", "계열사", "지분 보유",
        "생산", "제조", "출시", "양산", "개발",
        "조달", "구매",
    ],
    "tech": [
        "도입", "적용", "전환", "개발 완료", "양산 적용",
        "EUV", "ArF", "GAA", "FinFET", "HBM", "DRAM", "NAND",
        "CoWoS", "TC 본더", "TC본더", "포토레지스트", "감광액",
        "파운드리", "패키징", "후공정", "전공정",
        "노광", "식각", "증착",
    ],
}

# 전체 키워드 단일 set (빠른 hit 검사용)
_ALL_TRIGGERS_SET: set[str] = {kw for kws in TRIGGER_KEYWORDS.values() for kw in kws}


def has_trigger(text: str) -> bool:
    """본문에 트리거 키워드 1개라도 포함되면 True."""
    if not text:
        return False
    return any(kw in text for kw in _ALL_TRIGGERS_SET)


def list_triggers(text: str) -> dict[str, list[str]]:
    """카테고리별 hit 트리거 — 디버깅·통계용."""
    if not text:
        return {}
    result: dict[str, list[str]] = {}
    for cat, kws in TRIGGER_KEYWORDS.items():
        hits = [kw for kw in kws if kw in text]
        if hits:
            result[cat] = hits
    return result
