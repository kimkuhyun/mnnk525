"""단어집·단위 정규화 (B-7).

청크 본문 마지막 단계에서 적용:
1. 단위 정규화 — 470,900,000,000원 → "470,900,000,000원 (약 470.9조원)"
2. 약어 풀이 — HBM → "HBM(고대역폭메모리)", KSIC → "KSIC(한국표준산업분류)"
"""
from __future__ import annotations
import re

# =========================================================================
# 단위 정규화
# =========================================================================

# 큰 숫자 패턴: 1,234,567,890원 또는 1234567890원
_KRW_RE = re.compile(r"(?<![,\d])([+-]?\d{1,3}(?:,\d{3})+|[+-]?\d{4,})원(?!\(약)")
# 비율: 12.5% 또는 0.123
_PCT_RE = re.compile(r"([+-]?\d+\.\d+)%")


def _scale(n: int) -> str | None:
    """원 단위 정수 → '조/억/만' 표기."""
    abs_n = abs(n)
    if abs_n >= 10**12: return f"{n/1e12:.1f}조원"
    if abs_n >= 10**8: return f"{n/1e8:.1f}억원"
    if abs_n >= 10**4: return f"{n/1e4:.1f}만원"
    return None


def normalize_units(text: str) -> str:
    """본문 안 큰 숫자 → (약 N.N조원) 보강."""
    if not text:
        return text

    def repl(m: re.Match) -> str:
        raw = m.group(1)
        try:
            n = int(raw.replace(",", "").replace("+", ""))
        except ValueError:
            return m.group(0)
        scale = _scale(n)
        if scale is None:
            return m.group(0)
        return f"{raw}원 (약 {scale})"

    return _KRW_RE.sub(repl, text)


# =========================================================================
# 약어 사전
# =========================================================================

# 약어 → 풀이름 (한국 반도체·공시 도메인)
ACRONYMS: dict[str, str] = {
    # 반도체·기술
    "HBM": "고대역폭메모리",
    "DRAM": "동적 RAM",
    "NAND": "낸드플래시",
    "SSD": "솔리드스테이트드라이브",
    "PCB": "인쇄회로기판",
    "FAB": "반도체공장",
    "EUV": "극자외선노광",
    "CMP": "화학적기계연마",
    "ALD": "원자층증착",
    "CVD": "화학기상증착",
    "PVD": "물리기상증착",
    "DX": "디바이스경험",
    "DS": "디바이스솔루션",
    "SDC": "삼성디스플레이",
    # 공시·재무
    "KSIC": "한국표준산업분류",
    "IFRS": "국제회계기준",
    "K-IFRS": "한국채택국제회계기준",
    "KAM": "핵심감사사항",
    "EPS": "주당순이익",
    "BPS": "주당순자산",
    "ROE": "자기자본이익률",
    "ROA": "총자산이익률",
    "OPM": "영업이익률",
    "PER": "주가수익비율",
    "PBR": "주가순자산비율",
    "ESG": "환경·사회·지배구조",
    "M&A": "인수합병",
    "CB": "전환사채",
    "BW": "신주인수권부사채",
    "CP": "기업어음",
    "EB": "교환사채",
    # 보상
    "PSU": "성과연동주식보상",
    "OPI": "성과인센티브",
    "LTI": "장기인센티브",
    "ESOP": "우리사주조합",
    # 기업집단·공정위
    "FTC": "공정거래위원회",
    "BOK": "한국은행",
    "KOSIS": "통계청 국가통계포털",
    "DART": "전자공시시스템",
    # 거래·시장
    "KRX": "한국거래소",
    "KOSPI": "코스피",
    "KOSDAQ": "코스닥",
    "OTC": "장외시장",
    "IPO": "기업공개",
    "VC": "벤처캐피털",
}

# (\bACR\b) 패턴으로 word boundary 사용 — 일부 영문 토큰만 매칭
_ACRO_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in sorted(ACRONYMS, key=len, reverse=True)) + r")\b")


def expand_acronyms(text: str) -> str:
    """약어 → 약어(풀이름). 단, 이미 풀이 있으면 skip."""
    if not text:
        return text

    def repl(m: re.Match) -> str:
        ac = m.group(1)
        ko = ACRONYMS[ac]
        # 이미 "HBM(고대역폭메모리)" 같은 형태면 skip
        end = m.end()
        if end < len(text) and text[end] == "(":
            return ac
        return f"{ac}({ko})"

    return _ACRO_RE.sub(repl, text)


# =========================================================================
# 통합 — 청크 본문 마지막 처리
# =========================================================================

def apply_lexicon(text: str) -> str:
    """청크 본문에 단위 정규화 + 약어 풀이 적용."""
    if not text:
        return text
    return expand_acronyms(normalize_units(text))
