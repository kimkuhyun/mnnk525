"""Neo4j 제약 생성 — 03_neo4j.md §4-1 그대로. 멱등(IF NOT EXISTS)."""
from __future__ import annotations

from db import neo4j_driver

CONSTRAINTS = [
    ("org_corp_code", "Organization", "corp_code"),
    ("person_id", "Person", "person_id"),
    ("filing_rcept_no", "FilingDocument", "rcept_no"),
    ("finmetric_id", "FinMetric", "metric_id"),
    ("product_id", "Product", "product_id"),
    ("tech_id", "Technology", "tech_id"),
    ("activity_key", "ExtractionActivity", "activity_id"),
    ("chunk_key", "Chunk", "chunk_id"),
    ("statement_key", "Statement", "statement_id"),
    ("event_key", "Event", "event_id"),
]


def main() -> None:
    d = neo4j_driver()
    with d.session() as s:
        for name, label, prop in CONSTRAINTS:
            cy = (
                f"CREATE CONSTRAINT {name} IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
            )
            s.run(cy)
            print(f"[constraint] {name} ({label}.{prop})")
        # name 키 임시 Organization 노드(needs_er) 조회 가속용 인덱스
        s.run(
            "CREATE INDEX org_er_name IF NOT EXISTS FOR (o:Organization) ON (o.er_name)"
        )
        print("[index] org_er_name (Organization.er_name)")
    d.close()
    print("제약/인덱스 생성 완료.")


if __name__ == "__main__":
    main()
