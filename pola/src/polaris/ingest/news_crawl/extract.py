"""본문 + 메타 추출 — Playwright 렌더 HTML → Readability 본문 + og/JSON-LD 메타.

Readability 가 언론사별 레이아웃을 흡수하므로 언론사마다 본문 파서를 짤 필요가 없다.
(유지보수 핵심) 날짜/제목은 메타태그·JSON-LD 에서 정확히 가져온다.
"""
from __future__ import annotations

import json
import re

from playwright.sync_api import Page


def _meta(page: Page) -> dict:
    """og:* 메타태그 + JSON-LD(NewsArticle) 에서 보조 메타 추출."""
    def og(prop: str) -> str | None:
        el = page.query_selector(f'meta[property="{prop}"]')
        return el.get_attribute("content") if el else None

    meta = {
        "og_title": og("og:title"),
        "og_desc": og("og:description"),
        "published": og("article:published_time"),
        "publisher_meta": og("og:site_name"),
        "ld_headline": None,
        "ld_published": None,
    }
    for el in page.query_selector_all('script[type="application/ld+json"]'):
        try:
            data = json.loads(el.inner_text())
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            if isinstance(it, dict) and it.get("@type") in ("NewsArticle", "Article"):
                meta["ld_headline"] = meta["ld_headline"] or it.get("headline")
                meta["ld_published"] = meta["ld_published"] or it.get("datePublished")
    return meta


def extract_article(page: Page, url: str) -> dict | None:
    """url 을 열어 Readability 본문 + 메타 반환. 추출 실패/너무 짧으면 None."""
    from lxml import html as lxhtml
    from readability import Document

    page.goto(url, wait_until="domcontentloaded", timeout=20000)
    raw = page.content()
    try:
        doc = Document(raw)
        title = doc.short_title()
        body_html = doc.summary()
        body = re.sub(r"\s+", " ", " ".join(lxhtml.fromstring(body_html).itertext())).strip()
    except Exception:
        return None

    if len(body) < 100:  # 본문 추출 실패(광고/리스트 페이지 등)로 간주
        return None

    result = {"url": url, "title": title, "body": body, **_meta(page)}
    # published 메타가 없으면(전자신문 등) URL 날짜에서 보강: /20260529... → 2026-05-29
    if not result.get("published"):
        m = re.search(r"/(20\d{2})(\d{2})(\d{2})\d+", url)
        if m:
            result["published"] = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return result
