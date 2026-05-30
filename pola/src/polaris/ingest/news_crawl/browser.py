"""Playwright 브라우저 세션 — CDP attach 우선, 실패 시 launch 폴백.

팀 공용 설계: 각자 크롬을 디버그 모드로 띄워두면 그 세션에 attach 한다.
    chrome.exe --remote-debugging-port=9222 --user-data-dir="%TEMP%\\polaris_chrome"

attach 의 이점:
  - 실제 브라우저라 봇 차단 회피에 유리
  - 평소 쓰던 로그인/세션 그대로 활용
크롬을 안 띄워뒀으면 자동으로 headless 브라우저를 launch (혼자 빠르게 돌릴 때).
"""
from __future__ import annotations

import contextlib

from playwright.sync_api import sync_playwright

CDP_URL = "http://localhost:9222"


@contextlib.contextmanager
def browser_session(cdp_url: str = CDP_URL, headless: bool = False):
    """BrowserContext 를 yield. attach 우선(실제 크롬 = 차단 회피에 강함).

    크롬을 디버그모드로 띄워두면 그 세션에 붙는다:
        chrome.exe --remote-debugging-port=9222 --user-data-dir="%TEMP%\\polaris_chrome"
    안 띄워뒀으면 headful 브라우저를 새로 띄운다(headless 아님 — 화면에 보임).
    """
    with sync_playwright() as p:
        attached = False
        browser = None
        try:
            browser = p.chromium.connect_over_cdp(cdp_url)
            attached = True
            print(f"  [browser] CDP attach 성공 → {cdp_url} (실제 크롬 세션에 연결)")
        except Exception:
            print("  [browser] ⚠ CDP attach 실패 — 크롬을 디버그모드로 안 띄운 듯.")
            print("            headful 브라우저를 새로 띄웁니다(attach 가 차단 회피엔 더 강함).")
            browser = p.chromium.launch(headless=headless)
        try:
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            yield ctx
        finally:
            # attach 한 사용자 브라우저는 닫지 않음. 우리가 launch 한 것만 정리.
            if not attached and browser is not None:
                browser.close()
