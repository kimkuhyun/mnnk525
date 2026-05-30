"""GET /api/graph/{corp} — 회사 중심 ego 관계지도 (회사↔회사, 6그룹).

개선:
1) 그룹별 쿼터: 6그룹 각 weight 상위 8개씩 → 분쟁·지배구조 등 모든 그룹 항상 표시.
2) seed = 조회 corp 만 True (SEED_CORPS 전체 X) → 불필요한 떠다니는 별 방지.
3) node.group = 이웃 노드 기준 중심과의 최고 weight 엣지 그룹. 중심 노드는 group=None.
4) node.logo = Google Favicon API URL (도메인 매핑 기반, 없으면 None).
"""
from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter

from ..db import neo4j
from ..models import GraphData, GraphLink, GraphNode
from ..relations import COMPANY_REL_TYPES, DIRECTED, PREDICATE_TO_GROUP, SEED_CORPS

router = APIRouter(tags=["graph"])

GROUP_CAP = 8  # 그룹별 최대 엣지 수

DOMAIN_MAP: dict[str, str] = {
    "삼성전자": "samsung.com",
    "SK하이닉스": "skhynix.com",
    "한미반도체": "hanmisemi.com",
    "엔비디아": "nvidia.com",
    "TSMC": "tsmc.com",
    "애플": "apple.com",
    "구글": "google.com",
    "인텔": "intel.com",
    "마이크론": "micron.com",
    "퀄컴": "qualcomm.com",
    "ASML": "asml.com",
    "LG전자": "lge.com",
    "삼성디스플레이": "samsungdisplay.com",
    "삼성SDI": "samsungsdi.com",
    "삼성전기": "samsungsem.com",
    "마이크로소프트": "microsoft.com",
    "메타": "meta.com",
    "화웨이": "huawei.com",
    "Arm": "arm.com",
    "머크": "merckgroup.com",
}


def _logo(name: str) -> str | None:
    domain = DOMAIN_MAP.get(name)
    if domain:
        return f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
    return None


NEWS_CYPHER = """
MATCH (c:Organization {corp_code: $corp})-[r]-(o:Organization)
WHERE r.extracted_by = 'claude' AND type(r) IN $types
RETURN type(r) AS rtype,
       coalesce(startNode(r).corp_code, startNode(r).ext_id) AS src,
       coalesce(endNode(r).corp_code, endNode(r).ext_id) AS tgt,
       coalesce(o.corp_code, o.ext_id) AS nbId,
       coalesce(o.name, o.corp_code, o.ext_id) AS nbName,
       toFloat(coalesce(r.evidence_count, 1)) AS weight
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
       toFloat(coalesce(r.qota_rt, 1)) AS weight
"""


@router.get("/graph/{corp}", response_model=GraphData)
def graph(corp: str):
    with neo4j().session() as s:
        news_rows = s.run(NEWS_CYPHER, corp=corp, types=COMPANY_REL_TYPES).data()
        dart_rows = s.run(DART_CYPHER, corp=corp, types=COMPANY_REL_TYPES).data()
        seed_rec = s.run(
            "MATCH (c:Organization {corp_code: $corp}) RETURN coalesce(c.name, c.corp_code) AS nm",
            corp=corp,
        ).single()

    all_rows = news_rows + dart_rows

    # ── 1) 그룹별 쿼터: 그룹별 weight 상위 GROUP_CAP 개만 선택 ──
    group_buckets: dict[str, list[dict]] = defaultdict(list)
    for row in all_rows:
        grp = PREDICATE_TO_GROUP.get(row["rtype"])
        if not grp:
            continue
        if row["src"] == row["tgt"]:  # 자기루프 제외
            continue
        group_buckets[grp].append(row)

    selected_rows: list[dict] = []
    for grp, bucket in group_buckets.items():
        bucket.sort(key=lambda r: r["weight"], reverse=True)
        selected_rows.extend(bucket[:GROUP_CAP])

    # ── 2) 엣지 빌드 + 노드 정보 수집 ──
    center_name = SEED_CORPS.get(corp) or (seed_rec["nm"] if seed_rec else corp)
    names: dict[str, str] = {corp: center_name}
    degree: dict[str, int] = defaultdict(int)
    links: list[GraphLink] = []

    # 이웃 노드별 중심과의 최고 weight 엣지 그룹 추적
    nb_best: dict[str, tuple[float, str]] = {}  # nbId -> (best_weight, group)

    for row in selected_rows:
        grp = PREDICATE_TO_GROUP[row["rtype"]]
        links.append(GraphLink(
            source=row["src"],
            target=row["tgt"],
            group=grp,
            weight=row["weight"],
            directed=row["rtype"] in DIRECTED,
        ))
        names.setdefault(row["nbId"], row["nbName"])
        degree[row["src"]] += 1
        degree[row["tgt"]] += 1

        # ── 3) 이웃 노드의 대표 그룹: 중심과의 최고 weight 엣지 그룹 ──
        nb_id = row["nbId"]
        w = row["weight"]
        if nb_id not in nb_best or w > nb_best[nb_id][0]:
            nb_best[nb_id] = (w, grp)

    # ── 노드 목록: 엣지에 등장한 노드 + 중심만 (고아 노드 금지) ──
    nodes: list[GraphNode] = []
    for nid, nm in names.items():
        if nid == corp:
            # 중심 노드: seed=True, group=None
            nodes.append(GraphNode(
                id=nid,
                name=nm,
                seed=True,
                degree=degree.get(nid, 1),
                group=None,
                logo=_logo(nm),
            ))
        else:
            best_grp = nb_best[nid][1] if nid in nb_best else None
            nodes.append(GraphNode(
                id=nid,
                name=nm,
                seed=False,
                degree=degree.get(nid, 1),
                group=best_grp,
                logo=_logo(nm),
            ))

    return GraphData(nodes=nodes, links=links)
