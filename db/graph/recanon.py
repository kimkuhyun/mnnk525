"""기존 Product/Technology 노드를 강화된 단어집(entity_normalize)으로 재병합.

- canonical()==None(일반어·조직명) → detach delete.
- 같은 캐논으로 매핑되는 변형 노드들 → APOC mergeNodes 로 하나로(엣지 보존·중복결합).
- 타입 교정(Product↔Technology) 포함. 재추출 불필요 — 그래프 후처리.
멱등: 이미 캐논이면 그룹크기 1이라 변화 없음.
"""
from __future__ import annotations
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from db import neo4j_driver  # noqa: E402
from entity_normalize import canonical  # noqa: E402
from extract_helpers import entity_id  # noqa: E402


def fetch_nodes(s):
    out = []
    for lbl, kf in [("Product", "product_id"), ("Technology", "tech_id")]:
        for r in s.run(f"MATCH (n:{lbl}) RETURN n.{kf} AS k, n.name AS nm").data():
            out.append((lbl, kf, r["k"], r["nm"]))
    return out


def main():
    d = neo4j_driver()
    with d.session() as s:
        nodes = fetch_nodes(s)
        drop = []                       # (label, key)
        groups = defaultdict(list)      # (canon, ctype) -> [(label, kf, key, name)]
        for lbl, kf, key, nm in nodes:
            cano = canonical(nm, lbl)
            if cano is None:
                drop.append((lbl, kf, key))
                continue
            groups[cano].append((lbl, kf, key, nm))

        # 1) 블록리스트 삭제(엣지 함께)
        for lbl, kf, key in drop:
            s.run(f"MATCH (n:{lbl} {{{kf}:$k}}) DETACH DELETE n", k=key)
        print(f"[drop] 일반어/조직명 노드 삭제: {len(drop)}")

        # 2) 그룹 병합
        merged = 0
        for (canon, ctype), members in groups.items():
            kf_t = "product_id" if ctype == "Product" else "tech_id"
            tid = entity_id(canon.lower())
            # 캐논 타겟 노드 보장
            s.run(f"MERGE (c:{ctype} {{{kf_t}:$tid}}) SET c.name=$nm, c.canonical=$cl",
                  tid=tid, nm=canon, cl=canon.lower())
            # 타겟 외 멤버를 타겟으로 merge
            src_ids = [(lbl, kf, key) for (lbl, kf, key, _) in members
                       if not (lbl == ctype and key == tid)]
            for lbl, kf, key in src_ids:
                # 자기 자신이 타겟이면 skip
                if lbl == ctype and key == tid:
                    continue
                s.run(
                    f"""
                    MATCH (c:{ctype} {{{kf_t}:$tid}})
                    MATCH (x:{lbl} {{{kf}:$key}})
                    WHERE elementId(c) <> elementId(x)
                    CALL apoc.refactor.mergeNodes([c, x],
                        {{properties:'discard', mergeRels:true}}) YIELD node
                    RETURN node
                    """, tid=tid, key=key)
                merged += 1
        print(f"[merge] 변형→캐논 병합: {merged}")

        # 3) 라벨 정리: Product/Technology 양쪽 라벨 가진 노드 → 한쪽만
        #    (mergeNodes 가 라벨 결합했을 수 있음). canonical 타입 우선.
        s.run("""
            MATCH (n:Product:Technology)
            REMOVE n:Technology
        """)  # 충돌 시 Product 우선(보수적). 필요시 개별 교정.

        # 검증
        p = s.run("MATCH (n:Product) RETURN count(n)").single()[0]
        t = s.run("MATCH (n:Technology) RETURN count(n)").single()[0]
        print(f"[검증] 재병합 후 노드: Product {p}, Technology {t}")
    d.close()


if __name__ == "__main__":
    main()
