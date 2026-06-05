"""Product↔Technology 교차중복 해소 — 같은 이름이 Product·Technology 양쪽 노드로 갈린 것을
   의미에 맞는 한 라벨로 병합(엣지 보존, APOC mergeNodes).

분류 원칙(extract_prompt.py 정의):
- Technology = 공정·인터페이스/표준·플랫폼/소프트웨어·form factor·추상기술 (아래 TECH_SET).
- Product = 완제품·부품·원자재/소재·장비·서비스 (그 외 전부 — 다수).

병합: winner 라벨 노드에 loser 노드 엣지를 합치고 loser 라벨 제거. 멱등.
실행: cd db/graph && PYTHONIOENCODING=utf-8 uv run --project .. python dedup_product_tech.py
"""
from __future__ import annotations

from db import neo4j_driver

# Technology 로 통일할 이름(정규화: lower+trim). 그 외 교차중복은 전부 Product 로.
TECH_SET = {
    "ai", "ald", "ale", "ar", "vr", "automotive grade", "battery recycling",
    "bixby", "cvd", "cloud", "digital cockpit", "디지털 콕핏", "dry strip",
    "dry etch", "드라이식각", "euv", "euvo", "galaxy ai",
    "galaxy ecosystem", "gemini", "iot", "knox", "lte", "metal plating",
    "on-device ai", "pi curing", "pi cure", "pcie gen6", "provisual engine",
    "rie", "sawing", "micro saw", "secs/gem", "smartthings", "socamm2", "lpcamm",
    "samsung health", "samsung wallet", "telematics", "텔레매틱스", "ufs", "ecc",
    "건조공정", "세정공정", "반도체 공정", "반도체공정", "차세대 공정", "증착",
    "열처리", "식각", "자동화", "robotics", "스마트홈 플랫폼", "noa",
    "ipcs edge control", "industrial temp", "display 제조", "디스플레이 제조",
    "반도체 제조", "solar cell 제조", "package test", "6-side inspection",
    "laser marking", "knox",
}


def main() -> None:
    d = neo4j_driver()
    with d.session() as s:
        pairs = s.run(
            "MATCH (p:Product),(t:Technology) "
            "WHERE toLower(trim(p.name))=toLower(trim(t.name)) "
            "RETURN elementId(p) AS pid, elementId(t) AS tid, p.name AS name"
        ).data()
        print(f"[info] 교차중복 쌍 {len(pairs)}개")

        to_product = to_tech = 0
        for row in pairs:
            norm = (row["name"] or "").strip().lower()
            keep_tech = norm in TECH_SET
            # winner 먼저, loser 나중 → winner 노드로 병합되고 loser 라벨만 제거
            keep_id = row["tid"] if keep_tech else row["pid"]
            drop_id = row["pid"] if keep_tech else row["tid"]
            drop_label = "Product" if keep_tech else "Technology"
            s.run(
                "MATCH (a) WHERE elementId(a)=$keep "
                "MATCH (b) WHERE elementId(b)=$drop "
                "CALL apoc.refactor.mergeNodes([a,b],{mergeRels:true, properties:'discard'}) "
                "YIELD node "
                f"REMOVE node:{drop_label} "
                "RETURN node",
                keep=keep_id, drop=drop_id,
            )
            if keep_tech:
                to_tech += 1
            else:
                to_product += 1
        print(f"[ok] 병합 완료 — Product 로 {to_product} · Technology 로 {to_tech}")

        # 검증
        left = s.run(
            "MATCH (p:Product),(t:Technology) "
            "WHERE toLower(trim(p.name))=toLower(trim(t.name)) "
            "RETURN count(DISTINCT toLower(trim(p.name))) AS c"
        ).single()["c"]
        print(f"[verify] 남은 교차중복: {left}")
    d.close()


if __name__ == "__main__":
    main()
