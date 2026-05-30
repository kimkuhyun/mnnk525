"""기사 URL 수집 — 섹션/검색 목록을 페이지네이션하며 기사 링크를 모은다.

목록 정렬에 따라 종료 전략이 다르다(Section.date_ordered):
  • date_ordered=True  (섹션, 날짜 내림차순): since 이전/기수집 기사를 만나면 즉시 종료.
  • date_ordered=False (검색, 대략 최신순·페이지 내 섞임): since 이후는 모두 수집하되,
      'since 이전 기사만 있는 페이지'가 STALE_PAGE_LIMIT 번 연속되면 종료(과거 진입으로 판단).
      ※ 전자신문 검색은 날짜 GET 필터가 안 먹어, 이 방식으로 범위를 좁힌다.

link_selector 로 1차 추림 → article_re 로 기사 URL 확정(메뉴/광고 링크 제외).
"""
from __future__ import annotations

import random
import re
import time
from datetime import date
from urllib.parse import urljoin

from playwright.sync_api import BrowserContext

from .sources import Section
from .store import already_have

_DATE_RE = re.compile(r"(20\d{2})(\d{2})(\d{2})\d{4,}")  # 전자 /20260529000133 · 한경 /article/202605207871
PAGE_SLEEP_RANGE = (1.5, 3.0)  # 목록 페이지 요청 사이 랜덤 텀 (차단 방지)
STALE_PAGE_LIMIT = 4           # (검색) 연속 N페이지가 모두 since 이전이면 종료


def _url_date(url: str) -> date | None:
    """기사 URL 의 날짜(/YYYYMMDD......) 파싱. 없으면 None."""
    m = _DATE_RE.search(url)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def collect_urls(
    ctx: BrowserContext,
    section: Section,
    since: date,
    stop_on_seen: bool = True,
) -> list[str]:
    """목록 page 1..max_pages 순회 → since 이후 기사 URL 리스트."""
    page = ctx.new_page()
    art_re = re.compile(section.article_re)
    seen: set[str] = set()
    urls: list[str] = []
    stale_pages = 0
    try:
        for pno in range(1, section.max_pages + 1):
            # 요청 — 일시 에러(ERR_EMPTY_RESPONSE 등)는 backoff 재시도, 3회 실패면 종료
            ok = False
            for attempt in range(3):
                try:
                    page.goto(
                        section.list_url.format(page=pno),
                        wait_until="domcontentloaded",
                        timeout=25000,
                    )
                    ok = True
                    break
                except Exception as e:
                    wait = random.uniform(4, 8) * (attempt + 1)
                    print(f"    p{pno} 요청 실패 {type(e).__name__} ({attempt+1}/3) → {wait:.0f}s 후 재시도")
                    time.sleep(wait)
            if not ok:
                print(f"    p{pno} 3회 실패 → 여기까지 수집({len(urls)}건)하고 종료")
                break
            time.sleep(random.uniform(*PAGE_SLEEP_RANGE))  # 페이지 요청마다 텀

            links = page.query_selector_all(section.link_selector)
            if not links:
                break  # 더 이상 페이지 없음

            # link_selector → article_re 로 기사 URL 확정 + 중복 제거
            page_urls: list[str] = []
            for a in links:
                href = a.get_attribute("href")
                if not href:
                    continue
                u = urljoin(section.list_url, href)
                if not art_re.search(u) or u in seen:
                    continue
                seen.add(u)
                page_urls.append(u)
            if not page_urls:
                break  # 기사 링크 없음 = 결과 끝

            # since 이후만 추림
            in_range = [u for u in page_urls
                        if not (_url_date(u) and _url_date(u) < since)]
            fresh = [u for u in in_range
                     if not (stop_on_seen and already_have(u))]
            urls.extend(fresh)

            if section.date_ordered:
                # 엄격 최신순(섹션): 오래됨 or 기수집 도달 시 즉시 종료
                hit_old = any(_url_date(u) and _url_date(u) < since for u in page_urls)
                if hit_old or (stop_on_seen and len(fresh) < len(in_range)):
                    break
            else:
                # 비정렬(검색): since 이전만 있는 페이지가 연속되면 과거 진입 → 종료
                if in_range:
                    stale_pages = 0
                else:
                    stale_pages += 1
                    if stale_pages >= STALE_PAGE_LIMIT:
                        break
    finally:
        page.close()
    return urls
