"""뉴스 크롤러 — Playwright(CDP attach) + Readability 본문 추출 + 증분 저장.

RSS는 최근분만 노출되어 과거(2026-01-01~) 수집이 안 되므로, 언론사 섹션 목록을
직접 페이지네이션하며 기사 URL을 모으고, Readability로 본문을 통일 추출한다.

흐름:
    sources(언론사×섹션) → collect(URL 수집) → extract(본문+메타) → store(news_raw upsert)

실행:
    uv run python -m polaris.ingest.news_crawl.run --since 2026-01-01 \
        --sources 전자신문 --sections 산업/IT

자세한 사용법(크롬 CDP 실행 포함)은 같은 폴더 README.md 참고.
"""
from .sources import Section, SOURCES, select_sources

__all__ = ["Section", "SOURCES", "select_sources"]
