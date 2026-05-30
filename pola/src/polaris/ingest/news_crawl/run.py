"""뉴스 크롤러 오케스트레이션 (CLI).

    uv run python -m polaris.ingest.news_crawl.run \
        --since 2026-01-01 --sources 전자신문 --keyword 삼성전자

옵션:
    --since YYYY-MM-DD  이 날짜부터 (기본 2026-01-01)
    --sources ...       언론사 필터 (생략 시 전체)
    --sections ...      분야 필터 (생략 시 전체)
    --keyword KW        제목+본문에 KW 포함된 기사만 저장 (예: 삼성전자). 생략 시 전부.
    --full              증분 끄고 전체 재수집
    --cdp URL           CDP 주소 (기본 http://localhost:9222)
"""
from __future__ import annotations

import argparse
import random
import time
from datetime import date, datetime

from .browser import browser_session
from .collect import collect_urls
from .extract import extract_article
from .sources import select_sources
from .store import upsert

SLEEP_RANGE = (1.0, 3.0)  # 기사 본문 요청 사이 랜덤 텀 (차단 방지)


def _published_ok(article: dict, since: date) -> bool:
    """게시일이 since 이후인지. 날짜 못 읽으면 통과(보수적)."""
    raw = article.get("published") or article.get("ld_published")
    if not raw:
        return True
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date() >= since
    except Exception:
        return True


def main() -> None:
    ap = argparse.ArgumentParser(description="POLARIS 뉴스 크롤러 (섹션+Readability, 증분)")
    ap.add_argument("--since", default="2026-01-01")
    ap.add_argument("--sources", nargs="*")
    ap.add_argument("--sections", nargs="*")
    ap.add_argument("--keyword", help="제목+본문에 이 키워드 포함된 기사만 저장 (예: 삼성전자)")
    ap.add_argument("--full", action="store_true", help="증분 끄고 전체 재수집")
    ap.add_argument("--cdp", default="http://localhost:9222")
    args = ap.parse_args()

    since = date.fromisoformat(args.since)
    targets = select_sources(args.sources, args.sections)
    if not targets:
        print("대상 섹션이 없습니다. sources.py 의 SOURCES 를 확인하세요.")
        return

    print(f"대상 {len(targets)}개 섹션 · since={since} · 키워드={args.keyword or '(전체)'} "
          f"· 증분={'OFF' if args.full else 'ON'}")
    stats = {"urls": 0, "saved": 0, "skip_old": 0, "skip_kw": 0, "fail": 0}

    with browser_session(args.cdp) as ctx:
        for sec in targets:
            print(f"\n[{sec.publisher} · {sec.section}] URL 수집…")
            urls = collect_urls(ctx, sec, since, stop_on_seen=not args.full)
            stats["urls"] += len(urls)
            print(f"  {len(urls)}건 → 본문 추출")

            page = ctx.new_page()
            try:
                for i, url in enumerate(urls, 1):
                    try:
                        art = extract_article(page, url)
                        if not art:
                            stats["fail"] += 1
                            continue
                        if not _published_ok(art, since):
                            stats["skip_old"] += 1
                            continue
                        if args.keyword and args.keyword not in (
                            (art.get("title") or "") + " " + (art.get("body") or "")
                        ):
                            stats["skip_kw"] += 1
                            continue
                        upsert(art, sec.publisher, sec.section)
                        stats["saved"] += 1
                    except Exception as e:
                        stats["fail"] += 1
                        print(f"    실패 {url}: {e}")
                    time.sleep(random.uniform(*SLEEP_RANGE))
                    if i % 20 == 0:
                        print(f"    {i}/{len(urls)} (저장 {stats['saved']}, 키워드제외 {stats['skip_kw']})")
            finally:
                page.close()

    print(f"\n=== 완료 === URL {stats['urls']} · 저장 {stats['saved']} · "
          f"키워드제외 {stats['skip_kw']} · 오래됨 {stats['skip_old']} · 실패 {stats['fail']}")


if __name__ == "__main__":
    main()
