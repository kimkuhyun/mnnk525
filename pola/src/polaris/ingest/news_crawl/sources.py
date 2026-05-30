"""언론사 × 수집대상 정의.

방식 = B(키워드 검색): "삼성전자" 검색 → 전 분야에서 삼성 기사만. 본문 추출 낭비 0.
  - 검색 결과는 전부 삼성 관련이라 섹션 전체 추출(89% 버림)보다 효율적.
  - 검색은 중복 70%·과거로 느리지만(목록만), STALE 종료로 since 범위만 수집.
  - 섹션 전체 수집[A]은 아래 주석 보존(산업 배경 전체가 필요할 때).

전자신문 검색 (실측):
  검색 URL = https://search.etnews.com/etnews/search.html?kwd={키워드}&pageNum={N}
  기사 URL = https://www.etnews.com/{YYYYMMDD+6}   (절대 URL, 날짜 박힘)
  페이지네이션 = pageNum   (page/pageNo 등은 안 먹힘)
  ⚠ 날짜 GET 필터(startDate/endDate)는 서버가 무시(JS 전용) → date_ordered=False + STALE 로 범위 제한
"""
from __future__ import annotations

from dataclasses import dataclass

ETNEWS_ARTICLE_RE = r"/20\d{12}(?:[?#]|$)"


@dataclass(frozen=True)
class Section:
    publisher: str          # news_raw.publisher
    section: str            # news_raw.category (B=검색키워드, A=분야)
    list_url: str           # 목록/검색 URL. "{page}" 자리에 페이지 번호
    link_selector: str      # 기사 링크 CSS 셀렉터
    article_re: str = ETNEWS_ARTICLE_RE
    date_ordered: bool = False  # 전자신문 목록은 날짜 섞임 → STALE 종료
    max_pages: int = 500        # 검색은 과거로 느림 → 넉넉히(STALE 가 먼저 끊음)


# ─────────────────────────────────────────────────────────────────────
# B. 키워드 검색 (현재) — 검색결과 = 전부 삼성, 본문 추출 낭비 0
# ─────────────────────────────────────────────────────────────────────
_ETSEARCH = "https://search.etnews.com/etnews/search.html?kwd={kwd}&pageNum={{page}}"

SOURCES: list[Section] = [
    # 전자신문 — 검색 search.html, pageNum, 기사 /20260529...
    Section("전자신문", "삼성전자", _ETSEARCH.format(kwd="삼성전자"),
            "a[href*='/2026']"),
    # 한국경제 — 뉴스전용 검색 search.news, page 페이지네이션, 기사 /article/{YYYYMMDD+4}
    Section("한국경제", "삼성전자",
            "https://search.hankyung.com/apps.frm/search.news?query=삼성전자&page={page}",
            "a[href*='/article/']", article_re=r"/article/\d{10,}"),
    # 매일경제 — 더보기 AJAX 방식 → collect more_button 전략 필요 (다음 단계)
    # Section("매일경제", "삼성전자", "https://www.mk.co.kr/search?word=삼성전자", "li a[href*='/news/']", ...),
]


# ─────────────────────────────────────────────────────────────────────
# A. 섹션 전체 수집 (보존) — 산업 배경/경쟁사 맥락 전체가 필요하면 위 대신 사용.
#    검색 대비 본문 89% 가 비-삼성이라 키워드 필터로 버려짐(비효율).
#    _ET = "https://www.etnews.com/news/section.html?id1={id1}&page={{page}}"
#    SOURCES = [
#        Section("전자신문", "산업/IT", _ET.format(id1="03"), "a[href*='/2026']"),  # IT
#        Section("전자신문", "산업/IT", _ET.format(id1="06"), "a[href*='/2026']"),  # 전자
#        Section("전자신문", "경제",   _ET.format(id1="02"), "a[href*='/2026']"),
#    ]
# ─────────────────────────────────────────────────────────────────────


def select_sources(
    publishers: list[str] | None = None,
    sections: list[str] | None = None,
) -> list[Section]:
    """CLI 필터: 언론사/키워드(섹션) 부분집합. 둘 다 None 이면 전체."""
    rows = SOURCES
    if publishers:
        rows = [s for s in rows if s.publisher in publishers]
    if sections:
        rows = [s for s in rows if s.section in sections]
    return rows
