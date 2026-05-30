"""뉴스 그래프 정규화 — :NewsEntity 별칭 병합 + 중복 머지 + 자기루프 제거.

실행:
  uv run python -m polaris.graph.normalize_news_graph

[처리 순서]
  (a) 별칭 병합: organizations.yml 의 name/aliases/ticker 로 :NewsEntity 의
      name/canonical 매칭 → 해당 corp_code :Organization 으로 흡수.
      모든 관계(incoming/outgoing) 및 MENTIONS 를 corp 노드로 재배선.
      같은 type 엣지면 doc_ids 합집합·evidence_count=size 갱신.
      흡수 후 NewsEntity 삭제.

  (b) 중복 머지: 남은 :NewsEntity 중 aggressive-normalize 시 동일하거나
      보수적 포함관계인 쌍을 머지(대표=공식/장문명).
      잘못된 머지 방지를 위해 보수적 기준 적용.

  (c) 자기참조 제거: center corp 흡수로 생긴 자기루프 삭제.

[멱등]
  동일 그래프에 반복 실행 가능. 변경 전후 노드/엣지 수 로깅.

[범위 주의]
  :Organization (DART corp) 은 생성/삭제하지 않음.
  해외법인 약칭(SECA·SGE 등)은 건드리지 않음.
"""
from __future__ import annotations

import re
import sys
from typing import Optional

from polaris.config import neo4j_driver
from polaris.graph.common import canonicalize_name
from polaris.graph.lexicon.loader import load_aliases

# ---------------------------------------------------------------------------
# 별칭 인덱스 구축 (organizations.yml → canonical → corp_code)
# ---------------------------------------------------------------------------

def _build_alias_index() -> dict[str, str]:
    """organizations.yml 의 모든 name/aliases/ticker → canonical → corp_code."""
    idx: dict[str, str] = {}
    data = load_aliases("organizations") or {}
    for entity_key, meta in data.items():
        if not isinstance(meta, dict):
            continue
        eid = str(entity_key).zfill(8) if str(entity_key).isdigit() else str(entity_key)
        names: list[str] = []
        for k in ("name", "canonical", "kor_name"):
            v = meta.get(k)
            if v:
                names.append(v)
        names.extend(meta.get("aliases") or [])
        names.extend(meta.get("ticker") or [])
        ambiguous = set(meta.get("ambiguous_alone") or [])
        for n in names:
            if not n or n in ambiguous:
                continue
            canon = canonicalize_name(n)
            if canon:
                idx.setdefault(canon, eid)
            idx.setdefault(n, eid)
    return idx


# ---------------------------------------------------------------------------
# 보수적 정규화 (중복 머지용) — (주)/공백/특수문자/소문자
# ---------------------------------------------------------------------------

_AGG_CORP_RE = re.compile(
    r"(주식회사|㈜|\(주\)|株式会社|Co\.,?\s*Ltd\.?|Inc\.?|Corp\.?|Ltd\.?|\s+|[^\w가-힣])",
    re.IGNORECASE,
)


def _aggressive_normalize(name: str) -> str:
    """주식회사·(주)·공백·특수문자 제거 후 소문자."""
    if not name:
        return ""
    s = _AGG_CORP_RE.sub("", name)
    return s.lower()


def _is_safe_merge(a: str, b: str) -> bool:
    """두 NewsEntity 이름이 안전하게 머지 가능한가 — 보수적 기준.

    조건:
      1. aggressive-normalize 결과 완전히 동일, 또는
      2. 한쪽이 다른쪽을 포함(포함관계)하고 aggressive-norm 이 prefix/suffix match
         단, 포함자가 2배 이상 길면 차이가 너무 커 skip.
    """
    na, nb = _aggressive_normalize(a), _aggressive_normalize(b)
    if not na or not nb:
        return False
    # aggressive-normalize 결과가 완전히 동일할 때만 머지(공백·(주)·특수문자 차이).
    # 포함관계(prefix/suffix) 규칙은 '마이크로소프트→마이크로소프트연구소', '브이엠→에이치브이엠'
    # 같은 오병합을 유발해 제거 — 서로 다른 엔티티를 합치는 위험이 이득보다 큼.
    return na == nb


# ---------------------------------------------------------------------------
# 카운팅 헬퍼
# ---------------------------------------------------------------------------

def _count_nodes(sess, label: str) -> int:
    return sess.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()["c"]


def _count_rels(sess) -> int:
    return sess.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]


# ---------------------------------------------------------------------------
# (c) 자기루프 제거
# ---------------------------------------------------------------------------

def _remove_self_loops(sess) -> int:
    r = sess.run(
        "MATCH (n)-[r]->(n) DELETE r RETURN count(r) AS c"
    ).single()
    return r["c"] if r else 0


# ---------------------------------------------------------------------------
# (a) 별칭 병합 — NewsEntity → Organization 흡수
# ---------------------------------------------------------------------------

REWIRE_INCOMING_Q = """
MATCH (src)-[old_r:{rtype}]->(ne:NewsEntity {{ext_id: $ne_ext_id}})
MATCH (corp:Organization {{{keyprop}: $corp_id}})
WHERE elementId(src) <> elementId(corp)
MERGE (src)-[new_r:{rtype}]->(corp)
ON CREATE SET new_r = properties(old_r),
              new_r.doc_ids = coalesce(old_r.doc_ids, []),
              new_r.evidence_count = size(coalesce(old_r.doc_ids, []))
ON MATCH SET  new_r.doc_ids = apoc.coll.toSet(
                coalesce(new_r.doc_ids, []) + coalesce(old_r.doc_ids, [])),
              new_r.evidence_count = size(apoc.coll.toSet(
                coalesce(new_r.doc_ids, []) + coalesce(old_r.doc_ids, [])))
DELETE old_r
"""

REWIRE_OUTGOING_Q = """
MATCH (ne:NewsEntity {{ext_id: $ne_ext_id}})-[old_r:{rtype}]->(tgt)
MATCH (corp:Organization {{{keyprop}: $corp_id}})
WHERE elementId(tgt) <> elementId(corp)
MERGE (corp)-[new_r:{rtype}]->(tgt)
ON CREATE SET new_r = properties(old_r),
              new_r.doc_ids = coalesce(old_r.doc_ids, []),
              new_r.evidence_count = size(coalesce(old_r.doc_ids, []))
ON MATCH SET  new_r.doc_ids = apoc.coll.toSet(
                coalesce(new_r.doc_ids, []) + coalesce(old_r.doc_ids, [])),
              new_r.evidence_count = size(apoc.coll.toSet(
                coalesce(new_r.doc_ids, []) + coalesce(old_r.doc_ids, [])))
DELETE old_r
"""

REWIRE_MENTIONS_Q = """
MATCH (doc:Document)-[old_m:MENTIONS]->(ne:NewsEntity {ext_id: $ne_ext_id})
MATCH (corp:Organization {corp_code: $corp_id})
MERGE (doc)-[new_m:MENTIONS]->(corp)
ON CREATE SET new_m = properties(old_m)
DELETE old_m
"""

# APOC 없는 환경 대비 fallback (doc_ids 단순 concat + distinct)
REWIRE_INCOMING_NOAPOC_Q = """
MATCH (src)-[old_r:{rtype}]->(ne:NewsEntity {{ext_id: $ne_ext_id}})
MATCH (corp:Organization {{{keyprop}: $corp_id}})
WHERE elementId(src) <> elementId(corp)
WITH src, corp, old_r, type(old_r) AS rt, properties(old_r) AS props
MERGE (src)-[new_r:{rtype}]->(corp)
ON CREATE SET new_r = props
ON MATCH SET  new_r.doc_ids = [x IN coalesce(new_r.doc_ids,[]) + coalesce(old_r.doc_ids,[]) | x],
              new_r.evidence_count = size([x IN coalesce(new_r.doc_ids,[]) + coalesce(old_r.doc_ids,[]) | x])
DELETE old_r
"""

REWIRE_OUTGOING_NOAPOC_Q = """
MATCH (ne:NewsEntity {{ext_id: $ne_ext_id}})-[old_r:{rtype}]->(tgt)
MATCH (corp:Organization {{{keyprop}: $corp_id}})
WHERE elementId(tgt) <> elementId(corp)
MERGE (corp)-[new_r:{rtype}]->(tgt)
ON CREATE SET new_r = properties(old_r)
ON MATCH SET  new_r.doc_ids = [x IN coalesce(new_r.doc_ids,[]) + coalesce(old_r.doc_ids,[]) | x],
              new_r.evidence_count = size([x IN coalesce(new_r.doc_ids,[]) + coalesce(old_r.doc_ids,[]) | x])
DELETE old_r
"""


def _has_apoc(sess) -> bool:
    try:
        r = sess.run("RETURN apoc.coll.toSet([1,1,2]) AS s").single()
        return r is not None
    except Exception:
        return False


def _fetch_rel_types(sess, ne_ext_id: str, direction: str) -> list[str]:
    """NewsEntity 의 incoming/outgoing 관계 타입 목록."""
    if direction == "in":
        q = "MATCH ()-[r]->(ne:NewsEntity {ext_id:$eid}) RETURN DISTINCT type(r) AS t"
    else:
        q = "MATCH (ne:NewsEntity {ext_id:$eid})-[r]->() RETURN DISTINCT type(r) AS t"
    return [row["t"] for row in sess.run(q, eid=ne_ext_id)]


def _get_keyprop(corp_id: str) -> str:
    """corp_code 가 8자리 숫자면 corp_code, X 접두면 동일 (corp_code 로 저장됨)."""
    return "corp_code"


def absorb_news_entity_into_org(sess, ne_ext_id: str, corp_id: str, use_apoc: bool) -> None:
    """단일 NewsEntity 를 Organization 으로 흡수 (재배선 + 삭제)."""
    keyprop = _get_keyprop(corp_id)
    # incoming 관계 재배선
    for rtype in _fetch_rel_types(sess, ne_ext_id, "in"):
        if rtype == "MENTIONS":
            sess.run(REWIRE_MENTIONS_Q, ne_ext_id=ne_ext_id, corp_id=corp_id)
            continue
        if use_apoc:
            q = REWIRE_INCOMING_Q.format(rtype=rtype, keyprop=keyprop)
        else:
            q = REWIRE_INCOMING_NOAPOC_Q.format(rtype=rtype, keyprop=keyprop)
        sess.run(q, ne_ext_id=ne_ext_id, corp_id=corp_id)
    # outgoing 관계 재배선
    for rtype in _fetch_rel_types(sess, ne_ext_id, "out"):
        if use_apoc:
            q = REWIRE_OUTGOING_Q.format(rtype=rtype, keyprop=keyprop)
        else:
            q = REWIRE_OUTGOING_NOAPOC_Q.format(rtype=rtype, keyprop=keyprop)
        sess.run(q, ne_ext_id=ne_ext_id, corp_id=corp_id)
    # NewsEntity 삭제 (관계 이미 제거됨)
    sess.run("MATCH (ne:NewsEntity {ext_id:$eid}) DETACH DELETE ne", eid=ne_ext_id)


def phase_a_alias_merge(sess, alias_idx: dict[str, str], use_apoc: bool) -> int:
    """(a) 별칭 병합. 흡수된 NewsEntity 수 반환."""
    # 모든 NewsEntity 의 name·canonical 가져오기
    rows = sess.run(
        "MATCH (ne:NewsEntity) "
        "RETURN ne.ext_id AS eid, ne.name AS name, ne.canonical AS canon"
    ).data()

    absorbed = 0
    for row in rows:
        eid = row["eid"]
        if not eid:
            continue
        name = row.get("name") or ""
        canon = row.get("canon") or name

        # 매칭 시도: canonical → name → raw name
        corp_id: Optional[str] = None
        for candidate in (canonicalize_name(name), canonicalize_name(canon), name, canon):
            if candidate and candidate in alias_idx:
                corp_id = alias_idx[candidate]
                break

        if corp_id is None:
            continue

        # Organization 존재 확인
        org_exists = sess.run(
            "MATCH (o:Organization {corp_code:$cid}) RETURN count(o) AS c",
            cid=corp_id
        ).single()["c"]
        if not org_exists:
            continue

        print(f"  [alias-absorb] {name!r}({eid}) -> corp_code={corp_id}", file=sys.stderr)
        absorb_news_entity_into_org(sess, eid, corp_id, use_apoc)
        absorbed += 1

    return absorbed


# ---------------------------------------------------------------------------
# (b) 중복 머지 — 남은 NewsEntity 간
# ---------------------------------------------------------------------------

MERGE_NE_INCOMING_Q = """
MATCH (src)-[old_r:{rtype}]->(survivor:NewsEntity {{ext_id: $survivor_eid}})
WHERE elementId(src) <> elementId(survivor)
MATCH (dup:NewsEntity {{ext_id: $dup_eid}})
MATCH (src2)-[old_r2:{rtype}]->(dup)
WHERE elementId(src2) = elementId(src)
WITH src, survivor, old_r, old_r2
SET old_r.doc_ids = [x IN coalesce(old_r.doc_ids,[]) + coalesce(old_r2.doc_ids,[]) | x],
    old_r.evidence_count = size([x IN coalesce(old_r.doc_ids,[]) + coalesce(old_r2.doc_ids,[]) | x])
DELETE old_r2
"""

MERGE_NE_OUTGOING_Q = """
MATCH (survivor:NewsEntity {{ext_id: $survivor_eid}})-[old_r:{rtype}]->(tgt)
MATCH (dup:NewsEntity {{ext_id: $dup_eid}})-[old_r2:{rtype}]->(tgt2)
WHERE elementId(tgt) = elementId(tgt2)
SET old_r.doc_ids = [x IN coalesce(old_r.doc_ids,[]) + coalesce(old_r2.doc_ids,[]) | x],
    old_r.evidence_count = size([x IN coalesce(old_r.doc_ids,[]) + coalesce(old_r2.doc_ids,[]) | x])
DELETE old_r2
"""

REWIRE_NE_INCOMING_Q = """
MATCH (src)-[old_r:{rtype}]->(dup:NewsEntity {{ext_id: $dup_eid}})
MATCH (survivor:NewsEntity {{ext_id: $survivor_eid}})
WHERE elementId(src) <> elementId(survivor)
MERGE (src)-[new_r:{rtype}]->(survivor)
ON CREATE SET new_r = properties(old_r)
ON MATCH SET  new_r.doc_ids = [x IN coalesce(new_r.doc_ids,[]) + coalesce(old_r.doc_ids,[]) | x],
              new_r.evidence_count = size([x IN coalesce(new_r.doc_ids,[]) + coalesce(old_r.doc_ids,[]) | x])
DELETE old_r
"""

REWIRE_NE_OUTGOING_Q = """
MATCH (dup:NewsEntity {{ext_id: $dup_eid}})-[old_r:{rtype}]->(tgt)
MATCH (survivor:NewsEntity {{ext_id: $survivor_eid}})
WHERE elementId(tgt) <> elementId(survivor)
MERGE (survivor)-[new_r:{rtype}]->(tgt)
ON CREATE SET new_r = properties(old_r)
ON MATCH SET  new_r.doc_ids = [x IN coalesce(new_r.doc_ids,[]) + coalesce(old_r.doc_ids,[]) | x],
              new_r.evidence_count = size([x IN coalesce(new_r.doc_ids,[]) + coalesce(old_r.doc_ids,[]) | x])
DELETE old_r
"""

REWIRE_NE_MENTIONS_Q = """
MATCH (doc:Document)-[old_m:MENTIONS]->(dup:NewsEntity {ext_id: $dup_eid})
MATCH (survivor:NewsEntity {ext_id: $survivor_eid})
MERGE (doc)-[new_m:MENTIONS]->(survivor)
ON CREATE SET new_m = properties(old_m)
DELETE old_m
"""


def _pick_survivor(name_a: str, eid_a: str, name_b: str, eid_b: str) -> tuple[str, str, str, str]:
    """두 NewsEntity 중 대표(survivor) 결정 — 공식명/장문명 우선."""
    # 더 긴 이름을 대표로 (= 더 구체적이라 가정)
    if len(name_a) >= len(name_b):
        return eid_a, name_a, eid_b, name_b
    return eid_b, name_b, eid_a, name_a


def merge_two_news_entities(sess, survivor_eid: str, dup_eid: str) -> None:
    """dup 의 모든 관계를 survivor 로 이동 후 dup 삭제."""
    for rtype in _fetch_rel_types(sess, dup_eid, "in"):
        if rtype == "MENTIONS":
            sess.run(REWIRE_NE_MENTIONS_Q, dup_eid=dup_eid, survivor_eid=survivor_eid)
            continue
        sess.run(REWIRE_NE_INCOMING_Q.format(rtype=rtype),
                 dup_eid=dup_eid, survivor_eid=survivor_eid)
    for rtype in _fetch_rel_types(sess, dup_eid, "out"):
        sess.run(REWIRE_NE_OUTGOING_Q.format(rtype=rtype),
                 dup_eid=dup_eid, survivor_eid=survivor_eid)
    sess.run("MATCH (ne:NewsEntity {ext_id:$eid}) DETACH DELETE ne", eid=dup_eid)


def phase_b_dedup_news_entities(sess) -> int:
    """(b) 남은 NewsEntity 간 중복 머지. 머지된 쌍 수 반환."""
    rows = sess.run(
        "MATCH (ne:NewsEntity) "
        "RETURN ne.ext_id AS eid, coalesce(ne.name, ne.canonical, '') AS name"
    ).data()

    # (eid, name) 목록
    entities: list[tuple[str, str]] = [(r["eid"], r["name"]) for r in rows if r["eid"]]

    merged = 0
    deleted_eids: set[str] = set()

    for i in range(len(entities)):
        eid_a, name_a = entities[i]
        if eid_a in deleted_eids:
            continue
        for j in range(i + 1, len(entities)):
            eid_b, name_b = entities[j]
            if eid_b in deleted_eids:
                continue
            if not _is_safe_merge(name_a, name_b):
                continue
            # 실제로 두 노드 모두 살아있는지 확인
            still_alive = sess.run(
                "MATCH (a:NewsEntity {ext_id:$ea}) MATCH (b:NewsEntity {ext_id:$eb}) "
                "RETURN count(a)+count(b) AS c",
                ea=eid_a, eb=eid_b
            ).single()["c"]
            if still_alive < 2:
                continue
            s_eid, s_name, d_eid, d_name = _pick_survivor(name_a, eid_a, name_b, eid_b)
            print(f"  [ne-dedup] survivor={s_name!r}({s_eid}) <- dup={d_name!r}({d_eid})",
                  file=sys.stderr)
            merge_two_news_entities(sess, s_eid, d_eid)
            deleted_eids.add(d_eid)
            # name_a 대표로 갱신(생존자가 a 일 수 있으므로)
            if d_eid == eid_a:
                entities[i] = (s_eid, s_name)
                eid_a, name_a = s_eid, s_name
            merged += 1

    return merged


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

def run() -> dict:
    drv = neo4j_driver()
    stats: dict = {}

    with drv.session() as sess:
        # 사전 카운트
        ne_before = _count_nodes(sess, "NewsEntity")
        rels_before = _count_rels(sess)
        print(f"[normalize] 시작 — NewsEntity:{ne_before}  전체관계:{rels_before}", file=sys.stderr)

        use_apoc = _has_apoc(sess)
        if not use_apoc:
            print("[normalize] APOC 미설치 — doc_ids 합집합 단순화 모드", file=sys.stderr)

        alias_idx = _build_alias_index()
        print(f"[normalize] 별칭 인덱스 항목 수: {len(alias_idx)}", file=sys.stderr)

        # (a) 별칭 병합
        absorbed = phase_a_alias_merge(sess, alias_idx, use_apoc)
        print(f"[normalize] (a) 별칭 흡수: {absorbed}개 NewsEntity -> Organization", file=sys.stderr)

        # (c) 자기루프 제거 (흡수 직후)
        loops1 = _remove_self_loops(sess)
        print(f"[normalize] (c-1) 자기루프 제거: {loops1}개", file=sys.stderr)

        # (b) 중복 머지
        deduped = phase_b_dedup_news_entities(sess)
        print(f"[normalize] (b) 중복 머지: {deduped}쌍", file=sys.stderr)

        # (c) 자기루프 재제거 (b 에서 생길 수 있음)
        loops2 = _remove_self_loops(sess)
        print(f"[normalize] (c-2) 자기루프 제거: {loops2}개", file=sys.stderr)

        # 사후 카운트
        ne_after = _count_nodes(sess, "NewsEntity")
        rels_after = _count_rels(sess)

        stats = {
            "ne_before": ne_before,
            "ne_after": ne_after,
            "ne_removed": ne_before - ne_after,
            "alias_absorbed": absorbed,
            "dedup_merged": deduped,
            "self_loops_removed": loops1 + loops2,
            "rels_before": rels_before,
            "rels_after": rels_after,
        }

    drv.close()
    return stats


def main() -> None:
    print("=== POLARIS 뉴스 그래프 정규화 ===")
    st = run()
    print("\n[결과]")
    for k, v in st.items():
        print(f"  {k}: {v}")
    print("완료.")


if __name__ == "__main__":
    main()
