"""PDF 페이지 인덱스 — text 청크 anchor.page 매핑용.

PyMuPDF로 PDF 페이지별 텍스트 추출 → 청크 본문 첫 80자 검색 → page 번호.
Best-effort: 매칭 실패 시 None.
"""
from __future__ import annotations
import re
from pathlib import Path
from functools import lru_cache

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


def _normalize(s: str) -> str:
    """공백·줄바꿈 정규화 (PDF vs HTML 차이 흡수)."""
    return re.sub(r"\s+", " ", s or "").strip()


@lru_cache(maxsize=200)
def load_pdf_pages(pdf_path_str: str) -> tuple[str, ...]:
    """PDF → 페이지별 정규화 텍스트 tuple. 캐시 적용."""
    if fitz is None: return ()
    p = Path(pdf_path_str)
    if not p.is_file(): return ()
    try:
        doc = fitz.open(p)
        pages = tuple(_normalize(page.get_text()) for page in doc)
        doc.close()
        return pages
    except Exception:
        return ()


def find_page(pdf_path: Path | str, query_text: str, head_chars: int = 80) -> int | None:
    """청크 본문 첫 head_chars 문자 → PDF 페이지 번호 (1-based)."""
    if not pdf_path or not query_text:
        return None
    pages = load_pdf_pages(str(pdf_path))
    if not pages:
        return None
    head = _normalize(query_text)[:head_chars]
    if len(head) < 20:
        return None
    for i, page_text in enumerate(pages, 1):
        if head in page_text:
            return i
    return None
