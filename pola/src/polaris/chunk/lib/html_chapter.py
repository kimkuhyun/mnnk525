"""HTML 본문 → 챕터(섹션) 단위 추출.

옛 chunk_text.py의 화이트리스트 + heading 파싱 로직을 평문 body_clean.txt에 맞춰 단순화.

화이트리스트 (Pipeline 02 §4-b):
- II  사업의 내용
- III.4  재무제표 주석 (III.3, III.5 등도)
- IV  이사회·감사위원회
- V   감사인의 감사의견
- XI  그 외 참고사항

HTML 본문 안 표는 무시 (사용자 의도) — extract_body_text가 이미 <TABLE> 제거함.
"""
from __future__ import annotations
import re

# Roman + Arabic 헤딩
_ROMAN_RE = re.compile(r"^\s*([IVXLCDM]+)\.\s+(.+?)\s*$")
_ARABIC_RE = re.compile(r"^\s*(\d+)\.\s+(.+?)\s*$")
_HANGUL_RE = re.compile(r"^\s*([가-힣])\.\s+(.+?)\s*$")

WHITELIST_ROMANS = {"II", "IV", "V", "XI"}
WHITELIST_III_NUMS = {"3", "4", "5"}
WHITELIST_III_KW = "주석"


def parse_heading(line: str) -> tuple[str, str, str] | None:
    """라인이 헤딩인지 분류. (kind, key, body) 반환 or None."""
    t = (line or "").strip()
    if not t: return None
    for kind, regex in [("roman", _ROMAN_RE), ("arabic", _ARABIC_RE), ("hangul", _HANGUL_RE)]:
        m = regex.match(t)
        if m:
            return kind, m.group(1), m.group(2).strip()
    return None


def extract_sections(body_text: str) -> list[dict]:
    """body_clean.txt → 화이트리스트 섹션 list.

    Returns: [{"section_path": ["II", "1"], "headings": [...], "text": "...", "start_line": int, "end_line": int}, ...]
    """
    lines = body_text.split("\n") if body_text else []
    sections = []
    current_path = []        # 현재 섹션 경로 [Roman, Arabic, Hangul, ...]
    current_headings = []
    current_lines: list[str] = []
    current_start = 0

    def flush():
        if current_path and current_lines and is_whitelisted(current_path, current_headings):
            txt = "\n".join(current_lines).strip()
            if len(txt) >= 30:
                sections.append({
                    "section_path": list(current_path),
                    "headings": list(current_headings),
                    "text": txt,
                    "start_line": current_start,
                    "end_line": current_start + len(current_lines),
                })

    for i, line in enumerate(lines):
        h = parse_heading(line)
        if h:
            kind, key, body = h
            # Roman → 새 top-level (이전 flush)
            if kind == "roman":
                flush()
                current_path = [key]
                current_headings = [f"{key}. {body}"]
                current_lines = []
                current_start = i + 1
                continue
            # Arabic → 두 번째 level
            if kind == "arabic" and current_path:
                flush()
                current_path = [current_path[0], key]
                current_headings = [current_headings[0] if current_headings else "", f"{key}. {body}"]
                current_lines = []
                current_start = i + 1
                continue
            # Hangul → 세 번째 level
            if kind == "hangul" and len(current_path) >= 2:
                flush()
                current_path = [current_path[0], current_path[1], key]
                current_headings = current_headings[:2] + [f"{key}. {body}"]
                current_lines = []
                current_start = i + 1
                continue
        current_lines.append(line)

    flush()
    return sections


def is_whitelisted(section_path: list[str], headings: list[str]) -> bool:
    """화이트리스트 통과 여부 (Pipeline 02 §4-b)."""
    if not section_path: return False
    top = section_path[0]
    if top in WHITELIST_ROMANS:
        return True
    if top == "III" and len(section_path) >= 2:
        sub = section_path[1]
        if sub in WHITELIST_III_NUMS:
            return True
        if len(headings) >= 2 and WHITELIST_III_KW in headings[1]:
            return True
    return False
