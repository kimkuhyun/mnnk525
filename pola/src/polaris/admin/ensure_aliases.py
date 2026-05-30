"""신규 회사 alias 사전 자동 추가 — 의미 그래프 entity linking Stage 1 보강.

CORPS vs organizations.yml 비교 → 누락 corp_code 만 corps.json lookup 으로
결정론 변형 alias 와 함께 yaml 끝에 append. idempotent.

- 변형 규칙(한국 기업 표기 흔한 패턴):
    canonical, (주)canonical, canonical(주), canonical주식회사, 주식회사canonical
- ticker 는 corps.json 의 stock_code 1개.
- 영문·약어·자회사 등 specific alias 는 운영자 수동 보강 (자동화 어려움).

호출처: polaris build 안에서 자동 실행 (load 이전).
캐시 무효화: load_aliases.cache_clear() 자동.

상위 호환: organizations.yml 이 dict 형태 (`"<corp_code>": {name, aliases, ...}`) 라는 가정.
plain text append 로 들여쓰기·따옴표 스타일을 기존과 일치시킴 (PyYAML dump 안 씀).
"""
from __future__ import annotations
from pathlib import Path

import yaml

from polaris.config import CORPS, get_corp_meta
from polaris.graph.lexicon.loader import ALIAS_DIR, invalidate_cache

YAML_PATH = ALIAS_DIR / "organizations.yml"


def build_default_aliases(name: str) -> list[str]:
    """결정론 변형 — 한국 기업명 흔한 표기 5종."""
    n = name.strip()
    if not n:
        return []
    out = [n,
           f"(주){n}",
           f"{n}(주)",
           f"{n}주식회사",
           f"주식회사{n}"]
    # 중복 제거 (canonical 이 이미 "(주)" prefix 포함하는 경우 등)
    seen, uniq = set(), []
    for a in out:
        if a not in seen:
            seen.add(a); uniq.append(a)
    return uniq


def yaml_inline_str(s: str) -> str:
    """yaml flow scalar — 특수문자 있으면 따옴표 감싸기."""
    if any(c in s for c in ":#-?,&*!|>%@`{}[],\"'"):
        return '"' + s.replace('"', '\\"') + '"'
    return s


def ensure_aliases(corps: list[str] | None = None) -> dict:
    """yaml 에서 누락된 corp_code 자동 추가.

    Returns: {added: [...], skipped_existing: [...], missing_meta: [...]}
    """
    corps = list(corps or CORPS)
    if not YAML_PATH.is_file():
        # yaml 자체가 없으면 skip — 의미 그래프 모듈 비활성 환경
        return {"added": [], "skipped_existing": [], "missing_meta": [],
                "note": f"yaml not found: {YAML_PATH}"}

    existing = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or {}
    added, skipped, missing = [], [], []
    blocks: list[str] = []
    for cc in corps:
        cc8 = str(cc).zfill(8) if str(cc).isdigit() else str(cc)
        if cc8 in existing:
            skipped.append(cc8)
            continue
        meta = get_corp_meta(cc8)
        name = (meta.get("corp_name") or "").strip()
        stock = (meta.get("stock_code") or "").strip()
        if not name:
            missing.append(cc8)
            continue
        aliases = build_default_aliases(name)
        block_lines = [f'"{cc8}":',
                       f"  name: {yaml_inline_str(name)}",
                       "  aliases:"]
        for a in aliases:
            block_lines.append(f"    - {yaml_inline_str(a)}")
        if stock:
            block_lines.append(f'  ticker: ["{stock}"]')
        block_lines.append("  source: auto_added_by_polaris_build")
        blocks.append("\n".join(block_lines))
        added.append(cc8)

    if blocks:
        with YAML_PATH.open("a", encoding="utf-8") as f:
            f.write("\n\n# ────── 자동 추가 (polaris build) ──────\n")
            f.write("\n\n".join(blocks))
            f.write("\n")
        invalidate_cache()

    return {"added": added, "skipped_existing": skipped, "missing_meta": missing}


def main() -> int:
    """CLI 단독 호출 — polaris ensure-aliases."""
    result = ensure_aliases()
    if result["added"]:
        print(f"[ensure_aliases] 추가 {len(result['added'])}건: {result['added']}")
    if result["skipped_existing"]:
        print(f"[ensure_aliases] 이미 존재 {len(result['skipped_existing'])}건 (skip)")
    if result["missing_meta"]:
        print(f"[ensure_aliases] corps.json 미등록 {len(result['missing_meta'])}건: {result['missing_meta']}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
