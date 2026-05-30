"""뉴스 본문 LLM 추출(jsonl) → Neo4j MENTIONS + 엔티티간 관계 (사야리식 관계지도).

입력: {DATA_ROOT}/4_dbGoldTest/news_extracts/{name}.jsonl
  레코드: {doc_id, entities:[{text,type}], relations:[{subject,predicate,object,evidence,confidence}]}

흐름 (per doc):
  1. 엔티티 링킹 — EntityLinker (Stage1 alias 사전 + Stage2 vector ER)
     · 링크 성공 → 기존 정형 노드(corp_code/person_id/product_id…) 재사용
     · 링크 실패 → 정규화명 기반 결정론 노드 생성 (:NewsEntity:LLMExtracted)
  2. (Document)-[:MENTIONS]->(entity)
  3. (subject)-[:PREDICATE {evidence,confidence,doc_ids}]->(object)   ※ doc_ids 집합 → 멱등 + 근거 누적

교정:
  · EXECUTIVE_OF 의 subject 가 Organization 이면 UNIT_OF 로 (인물 전용 관계 보호)
  · 발행사 자기홍보(한경/전자신문 자체 서비스) 등은 추출 단계 프롬프트에서 억제

실행:
  uv run python -m polaris.ingest.news_crawl.graph_load --input sample.jsonl
  uv run python -m polaris.ingest.news_crawl.graph_load --input full.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from polaris.config import DATA_ROOT, neo4j_driver, get_active_run
from polaris.graph.common import canonicalize_name
from polaris.graph.linker import EntityLinker

EXTRACTS = DATA_ROOT / "4_dbGoldTest" / "news_extracts"

# ── 노이즈 필터 ─────────────────────────────────────────────────────
_NOISE_REPEAT_RE = re.compile(r"(.{1,10})\1{2,}")  # 같은 패턴 3회+ 연속
_HAS_KO_EN = re.compile(r"[가-힣a-zA-Z]")           # 한글·영문 최소 1자


def is_noise(surface: str) -> bool:
    """True 이면 해당 surface 를 엔티티로 적재하지 않는다.

    규칙:
      1. 길이 < 2 또는 > 40
      2. 한글·영문 글자가 하나도 없음 (순수 기호·숫자)
      3. 같은 토큰(1~10자) 이 3회 이상 연속 반복
    """
    s = (surface or "").strip()
    if len(s) < 2 or len(s) > 40:
        return True
    if not _HAS_KO_EN.search(s):
        return True
    if _NOISE_REPEAT_RE.search(s):
        return True
    return False


KEYPROP = {"Organization": "corp_code", "Person": "person_id",
           "Product": "product_id", "Technology": "tech_id", "Place": "iso_code"}
SHORT = {"Organization": "org", "Person": "per", "Product": "prod",
         "Technology": "tech", "Place": "plc"}
PREDICATES = {"SUPPLIES", "CUSTOMER_OF", "PARTNERS_WITH", "COMPETES_WITH",
              "INVESTS_IN", "ACQUIRES", "JV_WITH", "DEVELOPS", "EXECUTIVE_OF",
              "LICENSES", "LITIGATION", "UNIT_OF"}
EXTRACTED_BY = "claude"  # 모델 무관(샘플 opus·전체 sonnet) — 뉴스 추출 출처 식별자


# ── 엔티티 해석 (링킹 + 미링크 노드 키) ─────────────────────────────
def resolve(linker: EntityLinker, surface: str, etype: str, cache: dict,
            st: dict | None = None) -> dict | None:
    """surface → 노드 정보. 노이즈면 None 반환하고 st['noise_dropped'] 증가."""
    key = (surface or "").strip(), (etype or "").strip()
    if not key[0] or not key[1]:
        return None
    # 방어적 노이즈 필터
    if is_noise(key[0]):
        if st is not None:
            st["noise_dropped"] = st.get("noise_dropped", 0) + 1
        return None
    if key in cache:
        return cache[key]
    r = linker.link(key[0], key[1], source_chunk_id="news")
    if r:
        rv = {"label": r.entity_type, "keyprop": KEYPROP.get(r.entity_type, "ext_id"),
              "keyval": r.entity_id, "name": surface, "linked": True, "etype": r.entity_type}
    else:
        canon = canonicalize_name(surface)
        rv = {"label": etype, "keyprop": "ext_id",
              "keyval": f"news:{SHORT.get(etype, 'ent')}:{canon}",
              "name": surface, "linked": False, "etype": etype}
    cache[key] = rv
    return rv


def merge_node(sess, rv: dict, run_id: str) -> str:
    """노드 MERGE → elementId. 미링크는 :NewsEntity:LLMExtracted 부착."""
    if rv["linked"]:
        # alias 링크됐으나 노드가 비어있으면(외국사 X코드 등) 이름 보강
        q = (f"MERGE (n:{rv['label']} {{{rv['keyprop']}: $v}}) "
             f"SET n.last_seen_news_run = $run, n.name = coalesce(n.name, $name) "
             f"RETURN elementId(n) AS eid")
        return sess.run(q, v=rv["keyval"], name=rv["name"], run=run_id).single()["eid"]
    q = (f"MERGE (n:{rv['label']} {{ext_id: $v}}) "
         f"ON CREATE SET n:NewsEntity, n:LLMExtracted, n.name = $name, "
         f"  n.canonical = $name, n.first_seen_news_run = $run "
         f"SET n.last_seen_news_run = $run RETURN elementId(n) AS eid")
    return sess.run(q, v=rv["keyval"], name=rv["name"], run=run_id).single()["eid"]


MENTIONS_Q = (
    "MATCH (d:Document {doc_id: $doc}) "
    "MATCH (n) WHERE elementId(n) = $eid "
    "MERGE (d)-[m:MENTIONS]->(n) "
    "ON CREATE SET m.run_id = $run, m.extracted_by = $by"
)


def rel_query(rtype: str) -> str:
    # rtype 은 PREDICATES 화이트리스트에서만 → 문자열 보간 안전
    return (
        "MATCH (a) WHERE elementId(a) = $a "
        "MATCH (b) WHERE elementId(b) = $b "
        f"MERGE (a)-[r:{rtype}]->(b) "
        "ON CREATE SET r.doc_ids = [$doc], r.evidence = $ev, r.confidence = $conf, "
        "  r.extracted_by = $by, r.first_run = $run "
        "ON MATCH SET r.doc_ids = CASE WHEN $doc IN r.doc_ids THEN r.doc_ids "
        "                              ELSE r.doc_ids + $doc END "
        "SET r.evidence_count = size(r.doc_ids), r.last_run = $run"
    )


def fix_predicate(pred: str, subj_etype: str) -> str | None:
    if pred not in PREDICATES:
        return None
    # EXECUTIVE_OF 는 Person→Org 전용. subject 가 조직이면 부서/자회사 관계로 교정.
    if pred == "EXECUTIVE_OF" and subj_etype != "Person":
        return "UNIT_OF"
    return pred


def load(input_name: str) -> dict:
    path = EXTRACTS / input_name
    if not path.is_file():
        raise SystemExit(f"입력 없음: {path}")
    records = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

    run_id, _ = get_active_run()
    linker = EntityLinker(run_id=run_id, enable_vector=True)
    cache: dict = {}
    st = {"docs": 0, "mentions": 0, "rels": 0, "linked": 0, "news_node": 0,
          "rel_dropped": 0, "doc_missing": 0, "noise_dropped": 0}

    drv = neo4j_driver()
    with drv.session() as sess:
        for rec in records:
            doc = rec.get("doc_id")
            if not doc:
                continue
            # Document 존재 확인 (news load 가 먼저 만들어야 함)
            if not sess.run("MATCH (d:Document {doc_id:$d}) RETURN count(d)", d=doc).single()[0]:
                st["doc_missing"] += 1
                continue

            eid_by_surface: dict[str, str] = {}
            for e in rec.get("entities", []) or []:
                rv = resolve(linker, e.get("text"), e.get("type"), cache, st)
                if not rv:
                    continue
                eid = merge_node(sess, rv, run_id)
                eid_by_surface[e["text"]] = eid
                st["linked" if rv["linked"] else "news_node"] += 1
                sess.run(MENTIONS_Q, doc=doc, eid=eid, run=run_id, by=EXTRACTED_BY)
                st["mentions"] += 1

            for r in rec.get("relations", []) or []:
                subj, obj = r.get("subject"), r.get("object")
                # 가드: 자기루프·빈 주체/대상·confidence<=0 노이즈 제거
                if not subj or not obj or subj == obj or float(r.get("confidence", 0) or 0) <= 0:
                    st["rel_dropped"] += 1
                    continue
                a_eid = eid_by_surface.get(subj)
                b_eid = eid_by_surface.get(obj)
                # subject/object 가 entities 누락 시 즉석 해석 (object 가 빠진 케이스 구제)
                if a_eid is None and subj:
                    rv = resolve(linker, subj, _guess_type(subj), cache, st)
                    if rv:
                        a_eid = merge_node(sess, rv, run_id); eid_by_surface[subj] = a_eid
                if b_eid is None and obj:
                    rv = resolve(linker, obj, _guess_type(obj), cache, st)
                    if rv:
                        b_eid = merge_node(sess, rv, run_id); eid_by_surface[obj] = b_eid
                if a_eid is None or b_eid is None:
                    st["rel_dropped"] += 1
                    continue
                subj_etype = next((e.get("type") for e in rec.get("entities", []) if e.get("text") == subj), "Organization")
                pred = fix_predicate(r.get("predicate", ""), subj_etype)
                if not pred:
                    st["rel_dropped"] += 1
                    continue
                sess.run(rel_query(pred), a=a_eid, b=b_eid, doc=doc,
                         ev=(r.get("evidence") or "")[:200],
                         conf=float(r.get("confidence", 0.0)),
                         by=EXTRACTED_BY, run=run_id)
                st["rels"] += 1
            st["docs"] += 1
    drv.close()
    return st


def _guess_type(surface: str) -> str:
    # object 가 entities 에 없을 때 보수적으로 Organization 가정 (대부분 기관/회사)
    return "Organization"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="sample.jsonl", help="news_extracts/ 내 jsonl 파일명")
    args = ap.parse_args()
    print(f"=== 뉴스 그래프 적재 (MENTIONS + 관계) — {args.input} ===")
    st = load(args.input)
    for k, v in st.items():
        print(f"  {k}: {v}")
    print("완료. (Document)-[:MENTIONS]->(entity) + (entity)-[관계]->(entity)")


if __name__ == "__main__":
    main()
