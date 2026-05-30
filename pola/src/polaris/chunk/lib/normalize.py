"""HTML/DART JSON 정규화 — APIpipe_미완성/polaris/pipeline/chunk_text.py·chunk_table.py 재사용.

Pipeline 02 §4-b·§4-a 명세에 따라 노이즈 제거·단위 표준화·null 가드.
"""
from __future__ import annotations
import re
from typing import Any

# =========================================================================
# HTML 본문 노이즈 정규화 — chunk_text.py 76~96줄 그대로
# =========================================================================

# 한자 병기 괄호: (株式), (株式; 주식), (代表理事) 등
_HANJA_PAREN_RE = re.compile(r"\(\s*[^()]*[一-鿿][^()]*\)")
# 페이지 번호: "- 12 -", "12", "p. 12"
_PAGE_NUM_RE = re.compile(r"^\s*(?:-\s*)?(?:p\.?\s*)?\d{1,4}(?:\s*-)?\s*$", re.IGNORECASE)
# 다중 공백·탭
_MULTI_SPACE_RE = re.compile(r"[ \t]+")
# 다중 개행 (3+ 연속) → 2개
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
# Zero-width 문자 · NBSP
_ZW_RE = re.compile(r"[​‌‍﻿ ]")


def normalize_text(text: str) -> str:
    """청크 본문 노이즈 정규화.

    1) zero-width·NBSP 제거
    2) 한자 병기 괄호 제거 (株式) → ""
    3) 줄 단위 페이지 번호 제거
    4) 다중 공백·탭 → 단일 공백
    5) 줄별 strip + 다중 개행 압축
    """
    if not text:
        return ""
    t = _ZW_RE.sub("", text)
    t = _HANJA_PAREN_RE.sub("", t)
    lines = [ln for ln in t.split("\n") if not _PAGE_NUM_RE.match(ln)]
    t = "\n".join(lines)
    t = _MULTI_SPACE_RE.sub(" ", t)
    t = "\n".join(ln.strip() for ln in t.split("\n"))
    t = _MULTI_NEWLINE_RE.sub("\n\n", t)
    return t.strip()


# =========================================================================
# DART JSON 정규화 — chunk_table.py 43~95줄 그대로
# =========================================================================

def to_int(v: Any) -> int | None:
    """문자열·콤마·공백·None → int. 음수 괄호 표기 지원."""
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if not s or s in ("-", "—"):
        return None
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return int(float(s))
    except (ValueError, OverflowError):
        return None


def normalize_date(s: str | None) -> str:
    """2024.03.20 / 20240320 / 2024-03-20 → 2024-03-20."""
    if not s:
        return ""
    s = str(s).strip()
    m = re.match(r"^(\d{4})[.\-/]?(\d{2})[.\-/]?(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return s


def is_empty_value(v: Any) -> bool:
    """null/공백/대시 등 의미 없는 값 식별."""
    if v is None:
        return True
    s = str(v).strip()
    return s in ("", "-", "—", "None", "null", "N/A")


# =========================================================================
# HTML 본문 추출 — body.html → 깨끗한 텍스트
# =========================================================================

from html.parser import HTMLParser


class _BodyExtractor(HTMLParser):
    """DART body.html의 <SECTION>·<P>·<TITLE> 텍스트 추출. <TABLE> 무시 (사용자 의도)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0  # <TABLE>·<SCRIPT>·<STYLE> 내부 깊이
        self.skip_tags = {"table", "script", "style"}

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() in self.skip_tags:
            self.skip_depth += 1

    def handle_endtag(self, tag: str):
        if tag.lower() in self.skip_tags and self.skip_depth > 0:
            self.skip_depth -= 1

    def handle_data(self, data: str):
        if self.skip_depth == 0:
            self.parts.append(data)


def extract_body_text(html: str) -> str:
    """DART body.html → 표 제외한 본문 텍스트. normalize_text 적용 후 반환."""
    if not html:
        return ""
    e = _BodyExtractor()
    try:
        e.feed(html)
    except Exception:
        pass
    raw = "\n".join(e.parts)
    return normalize_text(raw)
