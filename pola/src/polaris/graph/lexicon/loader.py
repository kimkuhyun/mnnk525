"""yaml 사전 로더 — 캐시 1회.

위치: src/polaris/data/aliases/{organizations,persons,products,technologies,places}.yml

formats:
  organizations.yml:
    "00126380":
      name: 삼성전자
      aliases: [삼성전자주식회사, Samsung Electronics, ...]
      ticker: ["005930"]
      ambiguous_alone: [삼성, Samsung]
      subsidiaries: [삼성디스플레이, ...]
  products.yml:
    HBM3E:
      canonical: HBM3E
      category: memory_hbm
      aliases: [HBM3E, HBM-3E, 5세대 HBM]
  technologies.yml:
    EUV:
      canonical: EUV
      category: process_lithography
      aliases: [EUV 노광, 극자외선 노광, Extreme Ultraviolet]
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ALIAS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "aliases"


@lru_cache(maxsize=8)
def load_aliases(kind: str) -> dict[str, Any]:
    """kind ∈ {organizations, persons, products, technologies, places}.
    파일 없으면 빈 dict (외부 호출은 안전하게 동작)."""
    path = ALIAS_DIR / f"{kind}.yml"
    if not path.is_file():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"lexicon yaml 로드 실패 ({kind}): {e}")
        return {}


def load_all() -> dict[str, dict[str, Any]]:
    """5종 yaml 모두 로드."""
    return {kind: load_aliases(kind)
            for kind in ("organizations", "persons", "products",
                         "technologies", "places")}


def invalidate_cache():
    """yaml 수정 후 강제 재로드 필요 시."""
    load_aliases.cache_clear()
