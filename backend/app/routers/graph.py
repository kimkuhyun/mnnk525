"""GET /api/graph/{corp}          — 회사 중심 ego 관계지도 (외부관계 중심 + 지배구조 collapse).
GET /api/graph/meta/{corp}/{kind} — collapse 된 meta 멤버 노드 펼치기.

설계 원칙:
- 외부관계 중심(compete/supply/partner/dispute): 실명 이웃, 그룹별 GROUP_CAP 상위 엣지.
- 지배구조·계열 collapse: govern + '약칭 자회사' invest 이웃을 단일 meta 노드로.
  단, 명명 계열(로고 있음 OR subsidiaries_named 정식 목록)은 일반 노드 유지.
- 노드 kind 판정: seed > org(corp_code 보유) > person/product(ext_id 접두어) > news_entity.
"""
from __future__ import annotations

import re
from collections import defaultdict

from fastapi import APIRouter

from .. import aliases
from ..db import neo4j
from ..models import GraphData, GraphLink, GraphNode
from ..relations import COMPANY_REL_TYPES, DIRECTED, PREDICATE_TO_GROUP, SEED_CORPS

router = APIRouter(tags=["graph"])

GROUP_CAP = 12  # 그룹별 최대 엣지 수

# 약칭 자회사 판정 정규식: 알파벳 2~8자, 숫자·하이픈 가능
_ABBR_RE = re.compile(r"^[A-Za-z][A-Za-z0-9\-]{1,7}$")


def _logo(name: str) -> str | None:
    domain = aliases.domain_of(name)
    if domain:
        return f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
    return None


def _kind(node_id: str, node_name: str, corp: str) -> str:
    """노드 ID/이름으로 kind 판정."""
    if node_id == corp or node_id in SEED_CORPS:
        return "seed"
    ext = str(node_id)
    if ext.startswith("news:per"):
        return "person"
    if ext.startswith("news:prod"):
        return "product"
    # corp_code 패턴: 순수 숫자 8자리
    if re.match(r"^\d{8}$", ext):
        return "org"
    # ext_id 이지만 news:per/news:prod 아닌 경우
    if ext.startswith("news:"):
        return "news_entity"
    return "org"


# 자기참조 판정: (주)/㈜/주식회사/공백 제거 후 center 와 동일하면 자기 자신
_SELF_SUFFIX_RE = re.compile(r"(주식회사|㈜|\(주\)|\(주식회사\)|\s+)")


def _norm_self(name: str) -> str:
    return _SELF_SUFFIX_RE.sub("", name or "")


def _is_self_ref(nb_name: str, center_name: str) -> bool:
    """이웃 이름이 중심 회사의 자기참조(예: '삼성전자(주)')인지."""
    a, b = _norm_self(nb_name), _norm_self(center_name)
    return bool(a) and a == b


_FUND_KEYWORDS = ("신기술투자조합", "SVIC", "투자조합", "펀드")


def _is_fund(node_name: str) -> bool:
    """펀드/조합 노드 판정 (삼성벤처투자 CVC 등 그래프 노이즈)."""
    return any(kw in node_name for kw in _FUND_KEYWORDS)


def _is_collapse_candidate(node_id: str, node_name: str) -> bool:
    """govern/invest 이웃 중 meta 로 접어야 할 노드 판정.

    1) 펀드/조합 패턴 → 무조건 collapse(True).
    2) yaml 에 알려진 엔티티(known_names)거나 로고(domain)가 있으면 유지(False).
    3) 그 외 약칭 정규식(_ABBR_RE) 매칭 시 collapse(True).
    """
    if _is_fund(node_name):
        return True
    if _norm_self(node_name).lower() in aliases.known_names():
        return False
    if _logo(node_name) is not None:
        return False
    return bool(_ABBR_RE.match(node_name))


NEWS_CYPHER = """
MATCH (c:Organization {corp_code: $corp})-[r]-(o:Organization)
WHERE r.extracted_by = 'claude' AND type(r) IN $types
  AND coalesce(r.evidence_count, 1) >= 2
RETURN type(r) AS rtype,
       coalesce(startNode(r).corp_code, startNode(r).ext_id) AS src,
       coalesce(endNode(r).corp_code, endNode(r).ext_id) AS tgt,
       coalesce(o.corp_code, o.ext_id) AS nbId,
       coalesce(o.name, o.corp_code, o.ext_id) AS nbName,
       coalesce(toFloat(r.evidence_count), 1.0) AS weight
"""

DART_CYPHER = """
MATCH (c:Organization {corp_code: $corp})-[r]-(o:Organization)
WHERE r.extracted_by IS NULL AND type(r) IN $types
  AND NOT (type(r) = 'INVESTS_IN' AND coalesce(r.qota_rt, 0) <= 0)
RETURN type(r) AS rtype,
       coalesce(startNode(r).corp_code, startNode(r).ext_id) AS src,
       coalesce(endNode(r).corp_code, endNode(r).ext_id) AS tgt,
       coalesce(o.corp_code, o.ext_id) AS nbId,
       coalesce(o.name, o.corp_code, o.ext_id) AS nbName,
       coalesce(toFloat(r.qota_rt), 1.0) AS weight
"""

# meta 펼치기용: govern + invest 이웃 전체 (제한 없음)
META_MEMBERS_CYPHER = """
MATCH (c:Organization {corp_code: $corp})-[r]-(o:Organization)
WHERE type(r) IN ['IS_SUBSIDIARY_OF','IS_MAJOR_SHAREHOLDER_OF','AFFILIATED_WITH','INVESTS_IN']
RETURN type(r) AS rtype,
       coalesce(startNode(r).corp_code, startNode(r).ext_id) AS src,
       coalesce(endNode(r).corp_code, endNode(r).ext_id) AS tgt,
       coalesce(o.corp_code, o.ext_id) AS nbId,
       coalesce(o.name, o.corp_code, o.ext_id) AS nbName,
       coalesce(toFloat(r.evidence_count), toFloat(r.qota_rt), 1.0) AS weight,
       o.corp_code AS nbCorpCode
"""

META_TOP = 30  # meta 펼칩 시 개별 노드로 보여줄 최대 멤버 수


def _is_named_member(nb_id: str, nb_name: str, nb_corp_code: str | None) -> bool:
    """정식 명명 계열사 판정: corp_code 8자리 보유 OR 로고 있음 OR aliases.known_names 포함."""
    if nb_corp_code and re.match(r"^\d{8}$", str(nb_corp_code)):
        return True
    if _logo(nb_name) is not None:
        return True
    if _norm_self(nb_name).lower() in aliases.known_names():
        return True
    return False


@router.get("/graph/meta/{corp}/{kind}", response_model=GraphData)
def graph_meta(corp: str, kind: str):
    """collapse 된 meta 멤버 노드들 + center 연결 엣지 — 펼치기용.

    상위 META_TOP(30)개만 개별 노드로, 나머지는 '외 N개' etc 노드 1개로 집계.
    펀드/조합 패턴(is_fund=True) 은 랭킹 후순위로 밀리므로 30개 초과 시 etc 에 흡수.
    """
    with neo4j().session() as s:
        rows = s.run(META_MEMBERS_CYPHER, corp=corp).data()
        seed_rec = s.run(
            "MATCH (c:Organization {corp_code: $corp}) RETURN coalesce(c.name, c.corp_code) AS nm",
            corp=corp,
        ).single()

    center_name = SEED_CORPS.get(corp) or (seed_rec["nm"] if seed_rec else corp)

    # ── 1) 유효 멤버 수집 (자기루프·자기참조 제거) ──
    member_meta: dict[str, dict] = {}  # nbId -> {name, weight, group, src, tgt, rtype, corp_code}

    for row in rows:
        grp = PREDICATE_TO_GROUP.get(row["rtype"])
        if not grp:
            continue
        nb_id = row["nbId"]
        nb_name = row["nbName"]
        if row["src"] == row["tgt"]:
            continue
        if _is_self_ref(nb_name, center_name):
            continue
        # 동일 nbId 가 여러 행이면 weight 최대값으로 갱신
        w = row["weight"] or 1.0
        if nb_id not in member_meta or w > member_meta[nb_id]["weight"]:
            member_meta[nb_id] = {
                "name": nb_name,
                "weight": w,
                "group": grp,
                "src": row["src"],
                "tgt": row["tgt"],
                "rtype": row["rtype"],
                "corp_code": row.get("nbCorpCode"),
            }

    # ── 2) 랭킹: 펀드=False 우선, 그다음 weight 내림차순 ──
    ranked = sorted(
        member_meta.items(),
        key=lambda kv: (
            1 if _is_fund(kv[1]["name"]) else 0,  # 펀드는 후순위
            -kv[1]["weight"],
        ),
    )

    top_members = ranked[:META_TOP]
    etc_members = ranked[META_TOP:]
    etc_count = len(etc_members)

    # ── 3) 링크·노드 빌드 ──
    nodes: list[GraphNode] = []
    links: list[GraphLink] = []
    degree: dict[str, int] = defaultdict(int)

    for nb_id, meta in top_members:
        links.append(GraphLink(
            source=meta["src"], target=meta["tgt"],
            group=meta["group"], weight=meta["weight"],
            directed=meta["rtype"] in DIRECTED,
        ))
        degree[meta["src"]] += 1
        degree[meta["tgt"]] += 1

    # etc 잔여 노드 링크 (center ↔ etc)
    etc_id = f"__etc:govern:{corp}"
    if etc_count > 0:
        links.append(GraphLink(
            source=corp, target=etc_id,
            group="govern", weight=float(etc_count),
            directed=False,
        ))
        degree[corp] += 1
        degree[etc_id] = 1

    # ── 4) 노드 목록 ──
    # center
    nodes.append(GraphNode(
        id=corp, name=center_name, seed=True,
        degree=degree.get(corp, 1), group=None,
        logo=_logo(center_name),
        kind="seed", count=None,
    ))

    # 상위 멤버
    seen_nodes: set[str] = {corp}
    for nb_id, meta in top_members:
        if nb_id in seen_nodes:
            continue
        seen_nodes.add(nb_id)
        nodes.append(GraphNode(
            id=nb_id, name=meta["name"], seed=False,
            degree=degree.get(nb_id, 1), group=meta["group"],
            logo=_logo(meta["name"]),
            kind=_kind(nb_id, meta["name"], corp), count=None,
        ))

    # etc 잔여 노드 (kind='etc' — 클릭해도 펼침 없음)
    if etc_count > 0:
        nodes.append(GraphNode(
            id=etc_id, name=f"외 {etc_count}개", seed=False,
            degree=1, group="govern",
            logo=None,
            kind="etc", count=etc_count,
        ))

    # 댕글링 링크 제거
    _node_ids = {n.id for n in nodes}
    links = [lk for lk in links if lk.source in _node_ids and lk.target in _node_ids]

    return GraphData(nodes=nodes, links=links)


@router.get("/graph/{corp}", response_model=GraphData)
def graph(corp: str):
    """외부관계 중심 ego 뷰 + 지배구조·계열 collapse meta 노드."""
    with neo4j().session() as s:
        news_rows = s.run(NEWS_CYPHER, corp=corp, types=COMPANY_REL_TYPES).data()
        dart_rows = s.run(DART_CYPHER, corp=corp, types=COMPANY_REL_TYPES).data()
        seed_rec = s.run(
            "MATCH (c:Organization {corp_code: $corp}) RETURN coalesce(c.name, c.corp_code) AS nm",
            corp=corp,
        ).single()

    center_name = SEED_CORPS.get(corp) or (seed_rec["nm"] if seed_rec else corp)
    all_rows = news_rows + dart_rows

    # ── 1) 그룹별 버킷 분류 (자기루프·자기참조 이웃 제외) ──
    group_buckets: dict[str, list[dict]] = defaultdict(list)
    for row in all_rows:
        grp = PREDICATE_TO_GROUP.get(row["rtype"])
        if not grp:
            continue
        if row["src"] == row["tgt"]:
            continue
        if _is_self_ref(row["nbName"], center_name):
            continue  # '삼성전자(주)' 같은 자기참조 노드 제거
        group_buckets[grp].append(row)

    # ── 2) 지배구조/계열 collapse 대상 수집 ──
    # govern 이웃 전체 + invest 중 약칭 자회사 → meta 후보
    meta_members: dict[str, str] = {}  # nbId -> nbName (collapse 대상)
    invest_keep: list[dict] = []       # invest 중 일반 노드로 유지할 행

    for row in group_buckets.get("govern", []):
        nb_id = row["nbId"]
        nb_name = row["nbName"]
        meta_members[nb_id] = nb_name

    for row in group_buckets.get("invest", []):
        nb_id = row["nbId"]
        nb_name = row["nbName"]
        if _is_collapse_candidate(nb_id, nb_name):
            meta_members[nb_id] = nb_name
        else:
            invest_keep.append(row)

    # ── 3) 선택 행: compete/supply/partner/dispute(cap 적용) + invest 유지분 ──
    EXTERNAL_GROUPS = {"compete", "supply", "partner", "dispute"}
    selected_rows: list[dict] = []
    for grp in EXTERNAL_GROUPS:
        bucket = group_buckets.get(grp, [])
        bucket.sort(key=lambda r: r["weight"], reverse=True)
        selected_rows.extend(bucket[:GROUP_CAP])

    # invest 유지분 cap 적용
    invest_keep.sort(key=lambda r: r["weight"], reverse=True)
    selected_rows.extend(invest_keep[:GROUP_CAP])

    # collapse 후보가 외부관계(경쟁/공급/협력/분쟁) 엣지도 가지면 일반 노드로 노출 →
    # meta 에서 제외 (그래야 그 엣지의 끝점이 노드로 존재 → 댕글링 링크 방지)
    _selected_ids = {row["nbId"] for row in selected_rows}
    meta_members = {k: v for k, v in meta_members.items() if k not in _selected_ids}

    # ── 4) 엣지·노드 빌드 ──
    center_name = SEED_CORPS.get(corp) or (seed_rec["nm"] if seed_rec else corp)
    names: dict[str, str] = {corp: center_name}
    degree: dict[str, int] = defaultdict(int)
    links: list[GraphLink] = []
    nb_best: dict[str, tuple[float, str]] = {}  # nbId -> (best_weight, group)

    for row in selected_rows:
        grp = PREDICATE_TO_GROUP[row["rtype"]]
        links.append(GraphLink(
            source=row["src"], target=row["tgt"],
            group=grp, weight=row["weight"],
            directed=row["rtype"] in DIRECTED,
        ))
        names.setdefault(row["nbId"], row["nbName"])
        degree[row["src"]] += 1
        degree[row["tgt"]] += 1
        nb_id = row["nbId"]
        w = row["weight"]
        if nb_id not in nb_best or w > nb_best[nb_id][0]:
            nb_best[nb_id] = (w, grp)

    # ── 5) meta 노드 + 1엣지 (collapse 멤버가 있을 때만) ──
    meta_id = f"__meta:govern:{corp}"
    meta_count = len(meta_members)
    if meta_count > 0:
        links.append(GraphLink(
            source=corp, target=meta_id,
            group="govern", weight=float(meta_count),
            directed=False,
        ))
        degree[corp] += 1
        degree[meta_id] = 1

    # ── 6) 노드 목록 ──
    nodes: list[GraphNode] = []

    # 중심 노드
    nodes.append(GraphNode(
        id=corp, name=center_name, seed=True,
        degree=degree.get(corp, 1), group=None,
        logo=_logo(center_name),
        kind="seed", count=None,
    ))

    # 이웃 노드 (meta collapse 대상은 제외)
    for nid, nm in names.items():
        if nid == corp:
            continue
        if nid in meta_members:
            continue  # collapse
        best_grp = nb_best[nid][1] if nid in nb_best else None
        nodes.append(GraphNode(
            id=nid, name=nm, seed=False,
            degree=degree.get(nid, 1), group=best_grp,
            logo=_logo(nm),
            kind=_kind(nid, nm, corp), count=None,
        ))

    # meta 노드
    if meta_count > 0:
        nodes.append(GraphNode(
            id=meta_id, name="지배구조·계열", seed=False,
            degree=1, group="govern",
            logo=None,
            kind="meta", count=meta_count,
        ))

    # 댕글링 링크 제거: 양끝이 실제 노드 목록에 있는 엣지만 (collapse/필터로 빠진 노드 참조 방지)
    _node_ids = {n.id for n in nodes}
    links = [lk for lk in links if lk.source in _node_ids and lk.target in _node_ids]

    return GraphData(nodes=nodes, links=links)
