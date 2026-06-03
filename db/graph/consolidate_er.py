# -*- coding: utf-8 -*-
"""needs_er 노드 → corp_code 노드 병합 (오염 정리).

Stage5 Wave1-2 는 resolve_org 가 3사만 알던 시점에 돌아, 28개사 이름이
needs_er 노드에 붙었다(비정형 엣지가 실제 corp_code 노드와 분리됨).
여기서 er_name 이 31개사 중 하나로 해소되는 needs_er 노드를 그 corp_code
노드로 apoc.refactor.mergeNodes(엣지 이동)한다. corp 노드 속성 유지.
멱등(이미 병합된 건 needs_er 노드가 없으니 스킵).
"""
import sys
sys.path.insert(0, "graph")
import extract_helpers as H  # noqa: E402  (_CORP_BY_ERNAME, neo4j_driver)
from db import neo4j_driver  # noqa: E402

IDX = H._CORP_BY_ERNAME  # {normalize(name): corp_code}  (3사+28사+graph names)


def main():
    drv = neo4j_driver()
    merged = 0
    skipped = 0
    with drv.session() as s:
        # corp_code 노드가 실제 존재하는 코드 집합
        corp_codes = {r["cc"] for r in s.run(
            "MATCH (o:Organization) WHERE o.corp_code IS NOT NULL RETURN o.corp_code AS cc")}
        # needs_er 노드들
        ers = [(r["er"], r["nm"]) for r in s.run(
            "MATCH (o:Organization) WHERE coalesce(o.needs_er,false)=true "
            "AND o.er_name IS NOT NULL RETURN o.er_name AS er, o.name AS nm")]
        print(f"needs_er 노드 {len(ers)}개, corp_code 노드 {len(corp_codes)}개")
        for er, nm in ers:
            cc = IDX.get(er)
            if not cc or cc not in corp_codes:
                skipped += 1
                continue
            # corp 노드와 er 노드 병합 (corp 우선 → 속성 유지, 엣지 이동)
            res = s.run(
                "MATCH (corp:Organization {corp_code:$cc}) "
                "MATCH (er:Organization {er_name:$er}) WHERE coalesce(er.needs_er,false)=true "
                "WITH corp, er WHERE id(corp) <> id(er) "
                "CALL apoc.refactor.mergeNodes([corp, er], "
                "  {properties:'discard', mergeRels:true}) YIELD node "
                "RETURN node.corp_code AS cc",
                cc=cc, er=er)
            if res.single():
                merged += 1
                print(f"  병합: needs_er '{er}'({nm}) -> {cc}")
        # 병합 후 corp 노드의 needs_er 플래그 정리
        s.run("MATCH (o:Organization) WHERE o.corp_code IS NOT NULL "
              "SET o.needs_er=false, o.has_corp_code=true")
    print(f"\n병합 {merged}개, 스킵(외부사 등) {skipped}개")


if __name__ == "__main__":
    main()
