# Benchmarks

**측정**: 2026-05-25 · 200 쿼리 / 7 카테고리 / `tests/gold/v3.yml` + `graph_v1.yml`
**대상**: 반도체 8사 (5사 + DB하이텍 + 리노공업 + 이오테크닉스).
골드셋 자체는 옛 5사 기준이라 신규 3사 평가는 후속 (`graph_v1.yml` 확장 필요).

## 결론
**벡터 6/6 + 그래프 1/1 = 7/7 PASS + 적재 정합 10/10 PASS**

## 벡터 게이트 (`polaris eval`)

| 카테고리 | N | Recall@10 | MRR | nDCG@10 | 판정 |
|---|---|---|---|---|---|
| 정형수치 | 40 | **0.891** | 0.933 | 0.895 | ✅ PASS |
| 시계열 | 30 | **1.000** | 0.373 | 0.521 | ✅ PASS |
| 자유서술 | 30 | **0.867** | 0.399 | 0.515 | ✅ PASS |
| 출처충돌 | 20 | **1.000** | 1.000 | 1.000 | ✅ PASS |
| 시점 | 20 | **1.000** | 0.588 | 0.691 | ✅ PASS |
| no_answer | 30 | (avg 0.0) | — | — | ✅ PASS |

기준: Recall@10 ≥ 0.85 (no_answer 는 avg_top_score < 0.5).

## 그래프 게이트 (`polaris graph-eval`)

| 카테고리 | N | Precision | Recall | F1 | Exact |
|---|---|---|---|---|---|
| 비교 (Neo4j) | 30 | 1.000 | 1.000 | **1.000** | 30/30 ✅ |

**24,217 FinMetric 노드** (8사 합계, 5사 18,506 + 신규 3사 5,711). Cypher 결정론으로 100% 정확.

## 적재 정합 (`polaris verify`)

| # | 체크 | 결과 |
|---|---|---|
| 01 | MariaDB chunk_index ready | 41,324 (DART + 뉴스 + KRX + BOK + KOSIS + FTC) |
| 02 | Qdrant ↔ MariaDB (active run_id) | diff=0 |
| 03 | Neo4j Organization 649 / FinMetric 24,217 / Chunk 0 | PASS |
| 04 | active_run_manifest 정합 | PASS |
| 05 | Qdrant payload index 6종 | PASS |
| 06 | document_index ↔ text 청크 (orphan 0%) | PASS |
| 07 | 임베딩 L2 norm ≈ 1.0 | PASS |
| 08 | 8사 Organization + FinMetric (missing=[]) | PASS |
| 09 | news_raw 150 ↔ news_text chunk 150 (1뉴스=1청크) | PASS |
| 10 | dart_raw_index.body_json 16,753/16,753 | PASS |

**10/10 PASS**.

## 시작 → 최종 개선

| 카테고리 | 초기 | 최종 | Δ |
|---|---|---|---|
| 정형수치 | 0.580 | 0.860 | **+0.28** |
| 시계열 | 0.600 | 0.933 | **+0.33** |
| 자유서술 | 0.633 | 0.867 | **+0.23** |
| 출처충돌 | 0.700 | 1.000 | **+0.30** |
| 비교 | 0.290 → vector 0.639 → Neo4j 1.000 |

평균 +0.23. 큰 leverage 순:
1. **Contextual Retrieval prefix** (자유서술 +0.30)
2. **Cross-encoder Rerank** (정형/시계열 +0.13~0.33)
3. **BM25 + Dense + RRF** (+0.13)
4. **메타 사전 필터** (+0.10)
5. **FinMetric 적재 + Cypher** (비교 +0.36, 그 다음 그래프로 1.0)
