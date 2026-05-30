"""organizations.yml 기반 alias 사전 — 1회 로드 캐시.

제공:
  known_names  : set[str]              — 모든 항목의 name + aliases 를 정규화한 집합.
  domain_of(name) -> str|None          — name/alias(정규화) → 그 항목의 domain 값.
  canonical_key(name) -> str|None      — 정규화명이 known_names 에 있으면 정규화 키 반환.
  fragment_ids(node_id) -> list[str]   — Neo4j 에서 동일 canonical 로 묶이는 모든 노드 id 수집.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

_YML_PATH = (
    Path(__file__).resolve().parents[2]
    / "pola"
    / "src"
    / "polaris"
    / "data"
    / "aliases"
    / "organizations.yml"
)

_STRIP_RE = re.compile(r"(주식회사|㈜|\(주\)|\(주식회사\)|\s+)")


def _norm(text: str) -> str:
    """공백/㈜/(주)/소문자 제거 정규화."""
    return _STRIP_RE.sub("", (text or "")).lower()


@lru_cache(maxsize=1)
def _load() -> tuple[set[str], dict[str, str]]:
    """(known_names_set, norm_to_domain_dict) 튜플 반환. lru_cache 로 1회만 실행."""
    known: set[str] = set()
    norm_domain: dict[str, str] = {}

    try:
        with open(_YML_PATH, encoding="utf-8") as f:
            data: dict = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return known, norm_domain

    for entry in data.values():
        if not isinstance(entry, dict):
            continue

        name: str = entry.get("name", "")
        aliases: list = entry.get("aliases", []) or []
        domain: str | None = entry.get("domain")

        candidates = [name] + [str(a) for a in aliases]

        for cand in candidates:
            normed = _norm(cand)
            if normed:
                known.add(normed)
                if domain and normed not in norm_domain:
                    norm_domain[normed] = domain

    return known, norm_domain


@property  # type: ignore[misc]
def _known_names_prop() -> set[str]:  # noqa: F811
    return _load()[0]


# ── 공개 인터페이스 ──────────────────────────────────────────────────────

def known_names() -> set[str]:
    """모든 항목 name + aliases 를 정규화한 집합."""
    return _load()[0]


def domain_of(name: str) -> str | None:
    """name 또는 alias(정규화) 에 해당하는 domain 반환. 없으면 None."""
    _, norm_domain = _load()
    return norm_domain.get(_norm(name))


def canonical_key(name: str) -> str | None:
    """이름을 정규화한 뒤 known_names 에 있으면 정규화 키 반환, 없으면 None.

    KB 게이트: organizations.yml 에 등록된 이름만 canonical 로 인정해 오매칭 방지.
    """
    normed = _norm(name)
    if not normed:
        return None
    return normed if normed in known_names() else None


# Neo4j 조각 수집 Cypher — Organization/NewsEntity/Company 전체 대상
_FRAGMENT_CYPHER = """
MATCH (n)
WHERE (n:Organization OR n:NewsEntity OR n:Company)
  AND any(lbl IN labels(n) WHERE lbl IN ['Organization','NewsEntity','Company'])
  AND ( any(nm IN [n.name, n.corp_code, n.ext_id] WHERE nm IS NOT NULL
           AND toLower(apoc.text.replace(
                 apoc.text.replace(
                   apoc.text.replace(
                     apoc.text.replace(coalesce(nm,''), '주식회사', ''),
                   '㈜', ''), '(주)', ''), '\\s+', ''))
               = $canonical_key)
  )
RETURN coalesce(n.corp_code, n.ext_id) AS node_id, n.corp_code AS corp_code
"""

# apoc 없는 환경을 위한 대체 Cypher (이름만 비교)
_FRAGMENT_CYPHER_NOAPOC = """
MATCH (n)
WHERE (n:Organization OR n:NewsEntity OR n:Company)
RETURN coalesce(n.corp_code, n.ext_id) AS node_id,
       n.corp_code AS corp_code,
       coalesce(n.name, n.corp_code, n.ext_id) AS nm
"""


def fragment_ids(node_id_or_name: str) -> list[str]:
    """대상 노드와 동일 canonical 을 갖는 모든 조각 노드 id 목록 반환.

    - canonical_key 가 없으면 [node_id_or_name] 만 반환 (단일 노드 fallback).
    - Neo4j 조회 실패 시 동일하게 단일 fallback.
    """
    from .db import neo4j  # 순환 임포트 방지 — 함수 내 지연 임포트

    # 1) 이름 조회: node_id_or_name 이 id 일 수 있으므로 Neo4j 에서 이름 먼저 확보
    try:
        with neo4j().session() as s:
            rec = s.run(
                "MATCH (n) WHERE (n:Organization OR n:NewsEntity OR n:Company)"
                " AND coalesce(n.corp_code, n.ext_id) = $nid"
                " RETURN coalesce(n.name, n.corp_code, n.ext_id) AS nm LIMIT 1",
                nid=node_id_or_name,
            ).single()
        name_str: str = rec["nm"] if rec else node_id_or_name
    except Exception:
        name_str = node_id_or_name

    ck = canonical_key(name_str)
    if not ck:
        return [node_id_or_name]

    # 2) canonical_key 로 같은 정규화 이름을 가진 모든 노드 수집
    try:
        with neo4j().session() as s:
            rows = s.run(_FRAGMENT_CYPHER_NOAPOC).data()

        result: list[str] = []
        for row in rows:
            nm = row.get("nm") or ""
            if _norm(nm) == ck:
                nid = row.get("node_id")
                if nid:
                    result.append(str(nid))

        # 원본 id 가 빠진 경우 보장
        if node_id_or_name not in result:
            result.insert(0, node_id_or_name)
        return result if result else [node_id_or_name]
    except Exception:
        return [node_id_or_name]
