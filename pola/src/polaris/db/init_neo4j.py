"""Neo4j 제약·인덱스 초기화.

설계 05 §1.7 / §2.1 — Entity vs Fact 분리:
  🌐 전역 entity 8 (자연키 단독 UNIQUE):
     Organization, Person, Product, NewsArticle, Place, FilingDocument,
     BusinessGroup, FinancialInstrument
  ⏱ run-scoped 5 (자연키, run_id 복합 UNIQUE):
     Event, Statement, ExtractionActivity, FinMetric, Chunk

idempotent — IF NOT EXISTS.
"""
from __future__ import annotations
import sys, time
from pathlib import Path

from polaris.config import neo4j_driver


# 🌐 전역 entity 카드 8 — 자연키 단독 UNIQUE
# ADR 005/006 + P-2.2: NewsArticle 키는 document_id → news_id 통일 (적재 코드 일치)
GLOBAL_ENTITY_CONSTRAINTS = [
    ("Organization", "corp_code"),
    ("Person", "person_id"),
    ("Product", "product_id"),
    ("NewsArticle", "news_id"),
    ("Place", "iso_code"),
    ("FilingDocument", "rcept_no"),
    ("BusinessGroup", "unityGrupCode"),
    ("FinancialInstrument", "instrument_id"),
]

# Deprecated constraints — main() 에서 자동 DROP
DEPRECATED_CONSTRAINTS = [
    "newsarticle_document_id_unique",  # P-2.2: news_id 로 통일
]

# Deprecated indexes — UNIQUE 제약 생성 충돌 회피 (제약이 자동으로 index 생성)
DEPRECATED_INDEXES = [
    "news_id",  # P-2.2: 단순 RANGE → UNIQUE constraint 로 승격
]

# ⏱ run-scoped 카드 5 + P-3.2 Relation 추가 = 6
RUN_SCOPED_CONSTRAINTS = [
    ("Event", ["event_id", "run_id"]),
    ("Statement", ["statement_id", "run_id"]),
    ("ExtractionActivity", ["activity_id", "run_id"]),
    ("FinMetric", ["metric_id", "run_id"]),
    ("Chunk", ["chunk_id", "run_id"]),
    ("Relation", ["rel_id", "run_id"]),   # P-3.2: Tier 2.5 reification
]

# 보조 인덱스 (검색 패턴 가속)
SUPPORTING_INDEXES = [
    # 전역 entity: last_updated_run_id (audit)
    ("Organization", "last_updated_run_id"),
    ("Person", "last_updated_run_id"),
    ("FilingDocument", "last_updated_run_id"),
    # Product/Technology — P-3.2: LLM 추출 보강
    ("Product", "last_updated_run_id"),
    ("Technology", "last_updated_run_id"),
    # run-scoped: run_id 단독 (filter)
    ("Event", "run_id"),
    ("Statement", "run_id"),
    ("ExtractionActivity", "run_id"),
    ("FinMetric", "run_id"),
    ("Chunk", "run_id"),
    # Chunk 검색 보조
    ("Chunk", "ingest_status"),
    ("Chunk", "chunk_type"),
    # P-3.2: LLM 추출 노드 격리 라벨 — 정형 vs 의미 분리
    ("LLMExtracted", "extracted_by"),
    ("LLMExtracted", "confidence"),
]


# Composite 인덱스
COMPOSITE_INDEXES = [
    ("FilingDocument", ["corp_code", "date"]),
    ("FinMetric", ["corp_code", "year"]),
    ("Chunk", ["corp_code", "rcept_no"]),
]


def cypher_safe(label: str, suffix: str) -> str:
    """제약·인덱스 이름 — Cypher 식별자 안전."""
    return f"{label.lower()}_{suffix}"


def main() -> int:
    t0 = time.time()
    driver = neo4j_driver()
    applied = 0
    failed = 0

    with driver.session() as s:
        # 0. Deprecated constraints + indexes DROP (P-2.2 마이그레이션)
        if DEPRECATED_CONSTRAINTS:
            print(f"[init_neo4j] deprecated 제약 DROP ({len(DEPRECATED_CONSTRAINTS)})")
            for cname in DEPRECATED_CONSTRAINTS:
                try:
                    s.run(f"DROP CONSTRAINT {cname} IF EXISTS")
                    print(f"  OK  drop constraint {cname}")
                except Exception as e:
                    print(f"  SKIP {cname}: {e}")
        if DEPRECATED_INDEXES:
            print(f"[init_neo4j] deprecated 인덱스 DROP ({len(DEPRECATED_INDEXES)})")
            for iname in DEPRECATED_INDEXES:
                try:
                    s.run(f"DROP INDEX {iname} IF EXISTS")
                    print(f"  OK  drop index {iname}")
                except Exception as e:
                    print(f"  SKIP {iname}: {e}")

        # 1. 전역 entity UNIQUE (8)
        print(f"[init_neo4j] 전역 entity UNIQUE 제약 ({len(GLOBAL_ENTITY_CONSTRAINTS)})")
        for label, key in GLOBAL_ENTITY_CONSTRAINTS:
            name = cypher_safe(label, f"{key}_unique")
            q = (f"CREATE CONSTRAINT {name} IF NOT EXISTS "
                 f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE")
            try:
                s.run(q)
                applied += 1
                print(f"  OK  {label}.{key} UNIQUE ({name})")
            except Exception as e:
                failed += 1
                print(f"  FAIL {label}.{key}: {e}")

        # 2. run-scoped 복합 UNIQUE (5)
        print(f"\n[init_neo4j] run-scoped 복합 UNIQUE 제약 ({len(RUN_SCOPED_CONSTRAINTS)})")
        for label, keys in RUN_SCOPED_CONSTRAINTS:
            name = cypher_safe(label, "composite_unique")
            cols = ", ".join(f"n.{k}" for k in keys)
            q = (f"CREATE CONSTRAINT {name} IF NOT EXISTS "
                 f"FOR (n:{label}) REQUIRE ({cols}) IS UNIQUE")
            try:
                s.run(q)
                applied += 1
                print(f"  OK  {label} ({','.join(keys)}) UNIQUE")
            except Exception as e:
                failed += 1
                print(f"  FAIL {label}: {e}")

        # 3. 보조 인덱스 (single-property)
        print(f"\n[init_neo4j] 보조 인덱스 ({len(SUPPORTING_INDEXES)})")
        for label, prop in SUPPORTING_INDEXES:
            name = cypher_safe(label, f"{prop}_idx")
            q = (f"CREATE INDEX {name} IF NOT EXISTS "
                 f"FOR (n:{label}) ON (n.{prop})")
            try:
                s.run(q)
                applied += 1
                print(f"  OK  {label}.{prop}")
            except Exception as e:
                failed += 1
                print(f"  FAIL {label}.{prop}: {e}")

        # 4. Composite 인덱스
        print(f"\n[init_neo4j] Composite 인덱스 ({len(COMPOSITE_INDEXES)})")
        for label, props in COMPOSITE_INDEXES:
            name = cypher_safe(label, "_".join(props) + "_idx")
            cols = ", ".join(f"n.{p}" for p in props)
            q = (f"CREATE INDEX {name} IF NOT EXISTS "
                 f"FOR (n:{label}) ON ({cols})")
            try:
                s.run(q)
                applied += 1
                print(f"  OK  {label} ({','.join(props)})")
            except Exception as e:
                failed += 1
                print(f"  FAIL {label} ({','.join(props)}): {e}")

    driver.close()
    elapsed = time.time() - t0
    print(f"\n=== Neo4j init 완료 ({elapsed:.1f}s, applied={applied}, failed={failed}) ===")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
