# Changelog

## 0.3.0 — 2026-05-25 (저녁)

### Changed — 뉴스 매칭 단계 폐지 (단순화)
- 뉴스 청크 정책 변경: **1 뉴스 = 1 청크**, `corp_code='00000000'` (MACRO). 회사 매칭 단계 (룰+LLM 3차) 완전 제거.
- 검색 시 회사명을 쿼리에 직접 넣어 **벡터 의미 매칭** — 룰이 못 잡는 암시·자회사 언급도 자동으로 잡힘.
- 신규 회사 추가해도 뉴스 재매칭 단계 불필요. `build --skip-init` 단순화.
- `stage_b4_news.py`, `news_matching.py` 파일은 유지 (향후 매칭 부활 옵션 보존, 호출 안 함).

### Changed — PDF 다운로드 정책 좁힘
- documents 단계: **사업·반기·분기 보고서 3종만** PDF/HTML 다운로드 (이전 catalog/8 KEEP 37종 → 3종으로 좁힘).
- 자기주식·임원변동·대규모기업집단·정정공시 등은 DART JSON 으로 충분 → PDF 안 받음.
- 정리 스크립트 `scripts/cleanup_documents.py` — 기존 PDF 중 3종 외 일괄 제거 (7사 합쳐 148개 제거).
- `_is_key_report` 함수 단순화: `("사업보고서", "반기보고서", "분기보고서")` substring 매칭만.

### Changed — LLM 모델 환경변수화
- 모든 LLM 호출 (`news_matching.classify_news_llm`, `llm_summarize`) 이 `OLLAMA_LLM_MODEL` 환경변수 사용. 하드코딩 제거.
- default 모델: `qwen3.6:27b` → **`qwen3.5:9b`** (가벼움). 외부 GPU 서버 / 더 큰 모델 쓰려면 `.env` 의 `OLLAMA_BASE` + `OLLAMA_LLM_MODEL` 만 변경.
- `news_matching` 의 LLM_SYSTEM prompt + CLASSIFY_SCHEMA enum 도 **CORPS 기반 동적 생성**. 신규 회사 추가하면 LLM 도 자동 인식.

### Added — verify 10/10 (RDB 본문 정합 추가)
- 09 `news_raw <-> news_text` 청크 정합 — RDB 매칭된 뉴스 수 ≤ Qdrant 청크 수
- 10 `dart_raw_index.body_json` 완전성 — 모든 row 의 body_json NOT NULL
- 02 체크 개선: Qdrant 카운트 조회 시 `run_id=active` 필터 → 옛 청크 섞여있어도 정확 비교

### Added — 신규 회사 자동화
- `polaris build` 가 `.env CORPS` vs Neo4j Organization 비교 → 신규 회사 감지 시 자동 처리 (뉴스 매칭 폐지 이후엔 단순히 Organization MERGE 만).
- `load_finmetric` 가 CORPS 전체 Organization 노드 자동 MERGE (idempotent). 신규 회사도 자동 생성.
- `load_finmetric` 이 raw (`DATA_ROOT/rawData/{cc}/dart`) 우선 읽고 정제본 (`FILTERED/{cc}/dart`) fallback. 신규 회사 정제 단계 없어도 동작.
- `polaris build` 의 load 순서 강제: `mariadb → qdrant → neo4j` (standby_run_id 발급 후 SELECT).
- `scripts/add_company.ps1` — 회사 추가 1줄 자동화 (`.\\scripts\\add_company.ps1 -CorpCode 00160843`).

### Fixed — CLI sys.argv 격리
- 모든 typer 명령 (`verify`, `promote-run`, `init-db`, `load`, `eval`, `graph-eval`, `load-source/news/krx/...`, `reembed-*`, `mark-boilerplate`) 안쪽 모듈 `main()` 호출 전에 `sys.argv` 격리 → argparse unrecognized error 해소.
- `verify_ingestion` 02 체크가 Qdrant 카운트 조회 시 `run_id=active` 필터 적용 → 옛 청크 + 새 청크 섞인 컬렉션에서 정확한 비교.
- verify FAIL 8 (Organization missing) 자동 해결 — load_finmetric 의 Organization MERGE 로.

### Changed
- 패키지 폴더 구조 정리: `mnnk525/pola/` 안에 모든 코드·데이터. 깃 레포 루트는 `mnnk525/` (다른 모듈 확장 여지).
- 모든 코드 path 가 `polaris.config.DATA_ROOT` 기반 상대경로로 통일. 옛 하드코딩 (`ZZZF/___test/1_rawData/...`) 제거.
- 데이터 폴더 통합: `rawData/` 단일 폴더에 DART · documents · KRX · _common 모두 (옛 `1_rawData + rawData` 분리 폐지).

### Added — RDB 본문 저장 (SSOT)
- **news_raw** 테이블 — 뉴스 원문 (title, body, url, published, publisher, category, meta JSON) RDB 단일 저장.
  - `polaris.admin.migrate_news_to_rdb` — 기존 raw json 150건 일괄 import.
  - `bulk_collect` 가 새 뉴스 받을 때 파일 + DB 동시 저장 (`_news_raw_insert`).
  - `stage_b4_news` / `load-source news` 가 RDB 에서 SELECT.
- **dart_raw_index.body_json** 컬럼 (LONGTEXT) — DART JSON 본문 RDB 저장.
  - `polaris.admin.migrate_dart_to_rdb` — 기존 4,551건 일괄 import (35초).
  - `load_dart_raw_index` 가 body_json 함께 INSERT.
- raw_path 형식 통일: `___test/1_rawData/...` → `rawData/...` (DATA_ROOT 기준).

### Storage policy
| 데이터 | 위치 | 비고 |
|---|---|---|
| 뉴스 본문 | `news_raw.body` (RDB) | SSOT. 파일은 백업 |
| DART JSON | `dart_raw_index.body_json` (RDB) | SSOT. 파일은 백업 |
| HTML/PDF | 파일 `rawData/{cc}/documents/` | RDB 엔 경로만 (50~500GB 부담) |
| 청크 텍스트 | `chunk_index.embedding_text` (1500자) | 벡터는 Qdrant |

## 0.1.0 — 2026-05-25
초기 패키지화. zzzf 실험 코드 → src/polaris 모듈 구조로 이동.

### Highlights
- **벡터 게이트 6/6 PASS** (자유서술 0.567 → 0.867 도약, Contextual Retrieval 적용)
- **그래프 게이트 30/30 exact** (F1 1.0, Cypher 결정론)
- **적재 정합 8/8 PASS** (3DB 카운트·payload index·임베딩 norm 등)

### Added
- `polaris` CLI 단일 진입점 (typer, 11개 명령)
- 수집·적재 파이프라인:
  - `polaris ingest [--stage a/b1/b2/b3/b4/all]` — DART 수집 + HTML 정제 + document_index
  - `polaris init-db [--db ...]` — 3DB 스키마 초기화
  - `polaris load [--db ...]` — 청크·메타·그래프 적재
  - `polaris promote-run` — 블루/그린 스위치
- 검증·평가:
  - `polaris verify` — 3DB 적재 정합 8/8
  - `polaris eval` — 벡터 6/6 (BM25+Dense+RRF+Rerank 일괄)
  - `polaris graph-eval` — Neo4j Cypher F1=1.0
- 운영 도구:
  - `polaris load-finmetric` — DART JSON → Neo4j FinMetric 18,077 노드
  - `polaris load-news` — 뉴스 본문 청킹·임베딩·3DB 적재 (한경/매경 3 RSS)
  - `polaris load-kosis` — KOSIS 통계표 메타 청킹·적재
  - `polaris load-bok` — BOK 한국은행 거시 시계열 청킹·적재
  - `polaris load-krx` — KRX 5사 일별 OHLCV 월별 청킹·적재
  - `polaris load-ftc` — FTC 공정위 대규모기업집단 청킹·적재
  - `polaris mark-boilerplate` — token<50 보일러플레이트 soft-delete
  - `polaris reembed-text` / `polaris reembed-table` — Contextual prefix 재임베딩

### Data Sources (6종, 43,189 청크)
DART(40k 표 + 686 텍스트) + 뉴스(75, 한경+매경 3 RSS) + KOSIS(244) + BOK(1,582) + KRX(85) + FTC(29)

### Fixed
- 한경 RSS (`hankyung.com/feed/finance`) 가 escape 안 된 `&` 와 `&nbsp;` 등 HTML named entity 를 그대로 둬 feedparser SAX 가 `undefined entity` 로 entries=0 반환하던 문제. `_sanitize_rss` + `fetch_feed_parsed` 추가 ([bulk_collect.py:662](src/polaris/ingest/bulk_collect.py:662)). 한경 50건 / 매경 100건 / 매칭 46건 / 청크 75개.

### CLI 통합
- `polaris ingest` 가 bulk_collect 옵션 (`--only`, `--skip`, `--corp-codes`, `--from-year`, `--to-year`, `--news-since`, `--profile`) 을 직접 받음. 신규 회사 추가 시 `polaris ingest --only dart,krx --from-year 2024` 한 줄.
- `polaris load-source <name|all>` 신규 — 뉴스/KRX/BOK/KOSIS/FTC 5종 청킹·적재를 단일 명령. 기존 `load-news/load-krx/...` 는 hidden alias 유지.
- `polaris build` 신규 — init-db + load + load-source all + load-finmetric 통합. Quickstart 6줄 → 2줄 (`ingest` → `build`). promote-run 은 검증 후 별도 (안전).
- `polaris load-source news` 가 stage_b4 (회사 매칭) 자동 선행. 매일 cron 시 사용자가 별도 호출 불필요.
- README 갱신 - 새 회사 추가 흐름 (`.env` 1줄 + 명령 3개) + 매일 cron 흐름 명시.

### Incremental (매일 cron 안전)
- `stage_b4_news`: 기존 `news_matched.jsonl` 로드 → 같은 news_id 는 LLM·룰 호출 skip. 일일 6분 → 0초.
- `polaris load-news`: MariaDB ready 인 `news_text` chunk_id skip. 일일 임베딩 75건 → 0건.
- `bulk_collect` KRX: 작년 `daily_ohlcv_{y}.json` 모두 존재 시 올해치만 FDR 호출 (`effective_start`). 매일 2년치 → 올해치만.
- `polaris load-krx`: 이번달 (`YYYY-MM`) 청크는 OHLCV 누적되므로 항상 재임베딩, 과거달은 chunk_id ready 면 skip. 임베딩 85건 → 5건.
- `src/polaris/config.py` — `.env` 1회 로드 + 회사 목록 분리 (하드코딩 제거)
- GPU 백엔드 분기: `[cuda] / [rocm] / [cpu] / [directml]`
- Dockerfile + docker-compose (3DB)

### Changed
- 청킹 `embedding_text` 정책: 본문만 → `"{corp} {doc_type} {section_headings}\n\n{content}"` (Contextual Retrieval, Anthropic 2026 표준)
- `run_stage_c1.py` (표) + `run_stage_c2.py` (텍스트) 모두 적용

### Known Limitations
- 비교 카테고리 = Neo4j Cypher 영역. 벡터 게이트에서 제외 (별도 게이트로 측정).
- LLM 답변 + RAGAS (Faithfulness) 는 다음 마일스톤.
