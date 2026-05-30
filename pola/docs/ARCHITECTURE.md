# Architecture

## 3DB 역할 분리 (4-Tier 격리)

| DB | Tier | 역할 |
|---|---|---|
| **Qdrant** | T2 (의미 검색) | 청크 벡터 (bge-m3 1024d cosine) + payload index 6종 |
| **MariaDB** | T3 (원본·메타·SSOT) | `chunk_index` 청크 텍스트, `document_index` 문서 메타, `news_raw` 뉴스 원문, `dart_raw_index.body_json` DART JSON 원문, `active_run_manifest` 라우팅 |
| **Neo4j** | T1 (정형 사실) | `(Organization)-[:HAS_METRIC]->(FinMetric)` 결정론 그래프. 비교 쿼리 100% 정확. `NewsArticle` 노드도 적재 |

비교 쿼리 ("A vs B 2024년 부채총계") = T1 영역, Cypher 한 줄로 답.
의미 검색 (자유서술/시계열/출처충돌/뉴스) = T2 영역, 하이브리드 검색.

## 원본 저장 정책 (SSOT)

| 데이터 | 저장 위치 | 비고 |
|---|---|---|
| 뉴스 본문 | MariaDB `news_raw.body` (LONGTEXT) | RDB 가 SSOT. raw json 파일은 백업·캐시 |
| DART JSON 원문 | MariaDB `dart_raw_index.body_json` (LONGTEXT) | RDB 가 SSOT. 파일 (`rawData/{cc}/dart/*.json`) 은 백업 |
| 사업·반기·분기 보고서 (HTML/PDF) | 파일 (`rawData/{cc}/documents/{rno}/`) | RDB 엔 `document_index.snapshot_path` 만. PDF 는 사업/반기/분기 3종만 다운로드 (그 외 공시는 DART JSON 으로 충분) |
| 청크 텍스트 | MariaDB `chunk_index.embedding_text` | 본문 1500자 + Contextual prefix. 벡터는 Qdrant |

bulk_collect 가 새로 수집 시 file + RDB 동시 저장. 기존 파일 데이터는 `polaris.admin.migrate_news_to_rdb` / `migrate_dart_to_rdb` 로 일괄 import.

## 검색 파이프라인 (벡터)

```
Query
 → 메타 추출 (corp_code / year / endpoint)
 → Qdrant filter + Dense top-50 (bge-m3)
 → BM25 top-50 (rank-bm25 인메모리)
 → RRF 융합 (k=60)
 → Cross-encoder Rerank (bge-reranker-v2-m3)
 → top-10 청크
```

자유서술 카테고리는 BM25/Rerank skip (의미 검색 단독이 더 효과적).
비교 카테고리는 sub-query 분해 + corp 별 균등 분배.

## 청킹 정책

### DART 표·텍스트 — Contextual Retrieval (Anthropic 2024)

기본 청크 텍스트 `content` 만 임베딩하면 자유서술 쿼리 ("한미반도체 1. 사업의 개요") 와 매칭 약함.

```
embedding_text = "{corp_name} {doc_type} {section_headings}\n\n{content}"
```

→ 자유서술 0.567 → 0.867 도약 (+0.30, 다른 어떤 기법보다 큰 효과).

표 청크 (`chunk/table.py`) 도 동일 패턴 적용 (`{corp_name} {year} {endpoint}/{variant}` prefix).

### 뉴스 — 1 뉴스 = 1 청크 (단순화, 매칭 없음)

- 회사 매칭 단계 제거 (예전 룰+LLM 3차 매칭 폐기)
- 모든 뉴스를 `corp_code='00000000'` (MACRO) 으로 단일 청크화
- 검색 시 회사명을 쿼리에 직접 넣어 **벡터 의미 매칭**
- 신규 회사 추가해도 뉴스 재매칭·재인덱싱 불필요 (회사명이 본문에 있으면 자동으로 의미 검색에 잡힘)

`embedding_text = "{publisher} {date} {title}\n\n{body[:1500]}"` — 회사명 prefix 없음.

### KRX — 월별 OHLCV 요약 청크

`(corp, year_month)` 1청크. 이번달 청크는 매일 OHLCV 누적되므로 항상 재임베딩, 과거달은 chunk_id ready 면 skip.

## 평가 게이트

| 영역 | 기준 | 결과 |
|---|---|---|
| **벡터** (`polaris eval`) | Recall@10 ≥ 0.85, 6 카테고리 | 6/6 PASS |
| **그래프** (`polaris graph-eval`) | F1 ≥ 0.95 | 30/30 exact (F1=1.0) |
| **정합성** (`polaris verify`) | 3DB 카운트·body_json·뉴스 정합 | **10/10** PASS |

## 전체 파이프라인 (수집 → 적재 → 평가)

```
[ A. 수집 ]   polaris ingest --only dart,documents,krx,news,bok,kosis,ftc
  - DART API → data/rawData/{cc}/dart/ + dart_raw_index.body_json (RDB)
  - HTML/PDF → data/rawData/{cc}/documents/ (사업·반기·분기 3종만)
  - 뉴스 RSS → data/rawData/_common/news/ + news_raw (RDB SSOT)
  - KRX/BOK/KOSIS/FTC → data/rawData/_common/{src}/

[ B. 청킹·임베딩 ]   polaris build (또는 load + load-source all)
  - DART 표  → table_nl  (Contextual prefix)
  - DART 본문 → text_micro/macro  (Contextual prefix)
  - 뉴스 → news_text (1뉴스=1청크, corp=00000000)
  - KRX → krx_ohlcv (회사·월별 요약)
  - 모두 bge-m3 (Ollama) → 1024d L2-norm

[ C. 적재 ]   build 안에 통합
  - Qdrant (벡터 + payload 6종)
  - MariaDB (chunk_index + document_index + news_raw + dart_raw_index)
  - Neo4j (Organization + FinMetric + NewsArticle)
  - active_run_manifest standby → active (polaris promote-run)

[ D. 평가 ]
  polaris verify     → 적재 정합 10/10
  polaris eval       → 벡터 6/6
  polaris graph-eval → 그래프 F1=1.0
```

## 회사 추가 흐름 (자동화)

`.env POLARIS_CORPS` 에 corp_code 추가 → `polaris build --skip-init` 가 자동으로:
1. `.env CORPS` vs Neo4j Organization 비교 → 신규 회사 감지
2. `load-finmetric` 이 신규 Organization 노드 MERGE (idempotent)
3. 신규 회사 DART JSON 으로 FinMetric 자동 적재
4. 뉴스는 매칭 없는 단순 구조라 재매칭 단계 불필요

→ verify 10/10 PASS, 검색·평가 즉시 가능.

## 의미 그래프 (Phase 3) — LLM 추출 + 라벨 격리

비정형 본문 (사업보고서·뉴스) 에서 의미 추출 → `:LLMExtracted` 라벨로 정형과 격리 (ADR 008).

```
청크 (text_micro/macro, news_text)
  ↓ lexicon Matcher (Aho-Corasick 통합, 5 entity_type)
  ↓ filter (트리거 + entity hit ≥ 2 → LLM_PATH, 통과율 < 30%)
  ↓ llm_entity → llm_relation (qwen3.5:9b strict JSON, 6단 방어)
  ↓ linker (Stage 1 yaml → Stage 2 vector ER → Stage 4 unlinked)
  ↓ reifier (4조건 OR → Tier 1/2/3)
  ↓ Neo4j MERGE
     Product/Technology :LLMExtracted
     Statement (단순 fact)
     Relation (Tier 2.5 — multi-source/validity)
     Event (M&A, INVESTED_IN 등 SEM)
     Chunk 1-hop evidence (hasActor/hasObject)
     ExtractionActivity + wasGeneratedBy (PROV-O)
```

**검색 통합** (`retrieve/graph_aug.py`):
1. Qdrant top-k chunk_id
2. `augment_with_graph(chunk_ids)` → 1-hop 컨텍스트 (회사·인물·제품·기술·이벤트)
3. LLM 응답 prompt 에 컨텍스트 첨부 → 출처 강제 인용 강화

**평가** (`polaris graph-semantic-eval`):
- 카테고리 4종: entity / relation / event / entity_linking
- 게이트: entity F1≥0.75, relation F1≥0.70, linking F1≥0.87
- 골드셋: `tests/gold/graph_semantic_v1.yml` (시작 N=10 → N=50)

**alias 사전** (`src/polaris/data/aliases/*.yml`):
- organizations.yml (한국 8사 + 글로벌 18사, 103 alias)
- persons.yml (CEO·임원 stub; 실제는 extract_persons.py 자동 갱신)
- products.yml / technologies.yml / places.yml (도메인 어휘 357 alias)

`.env CORPS` 추가 후 의미 그래프 채움: `polaris graph-extract-semantic` → `polaris graph-load-semantic`.
