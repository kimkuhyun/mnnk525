# POLARIS

반도체 기업 GraphRAG. Qdrant + MariaDB + Neo4j + bge-m3 + Contextual Retrieval.

**상태**: 6 소스 · 8사 (5사 + DB하이텍·리노공업·이오테크닉스) · 41,324 청크. 벡터 6/6 + 그래프 F1=1.0 + 적재 정합 **10/10**.

## 폴더 구조

```
pola/                         # 패키지 루트
├── src/polaris/              # 코드
├── data/                     # raw + 청크/임베딩 산출물
│   ├── rawData/{cc}/         #   DART · documents (PDF/HTML) · KRX
│   ├── rawData/_common/      #   news · ftc · bok · kosis
│   ├── 2_Chuck/              #   정제 · 청크 · 임베딩
│   └── 4_dbGoldTest/         #   평가 산출물 (verify.json 등)
├── docs/APIdocs/             # API 메타카탈로그 xlsx
├── docker/                   # 3DB docker-compose
├── tests/gold/               # 평가 골드셋 (v3.yml, graph_v1.yml)
├── pyproject.toml
└── .env                      # API 키, DB 접속, POLARIS_CORPS 등
```

- 모든 경로는 패키지 루트(`pola/`) 상대. `__file__` 기반 자동 계산이라 OS·환경 무관.
- 데이터 위치 바꾸려면 `.env` 의 `POLARIS_DATA_ROOT=<절대경로>` 만 지정 (비우면 `pola/data/` 기본).

## Quickstart

```powershell
# 1. 의존성 (GPU 백엔드 1개 선택)
pip install -e .[cuda]        # NVIDIA
pip install -e .[directml]    # Windows + AMD GPU
pip install -e .[cpu]         # CPU only

# 2. 환경 + 3DB
cp .env.example .env
docker compose -f docker/docker-compose.yml up -d

# 3. raw 수집 → 적재 → 스위치 → 검증
polaris ingest                  # 6종 raw 수집 (DART/뉴스/KRX/BOK/KOSIS/FTC)
polaris build                   # standby 컬렉션에 적재 (init-db + load + load-source all + load-finmetric)
polaris promote-run             # standby → active 스위치 (검색 노출)
polaris verify                  # 3DB 정합 10/10 (active 기준)

# 4. 평가
polaris eval                    # 벡터 6/6
polaris graph-eval              # 그래프 F1=1.0
```

## 새 회사 추가 — `.env` 한 줄 + 명령 3개

```powershell
# 1) .env 의 POLARIS_CORPS 에 corp_code 추가 (corps.json 자동 매핑)
#    POLARIS_CORPS=00126380,00164779,...,00160843,00369657

# 2) 신규 회사 raw 만 수집 (캐시 skip)
polaris ingest --only dart,krx,documents --from-year 2024

# 3) 적재 + 스위치 + 검증 (build 가 신규 회사 자동 감지 → 뉴스 재매칭 + Organization MERGE 자동)
polaris build --skip-init     # DART + KRX + 뉴스 매칭 + FinMetric + Organization
polaris promote-run           # standby → active
polaris verify                # 10/10 PASS
```

`build --skip-init` 가 자동으로 처리:
- `.env CORPS` vs Neo4j Organization 비교 → 신규 회사 있으면 `news_raw.meta` 무효화 → 뉴스 재매칭
- `load-finmetric` 이 모든 회사 Organization 노드 MERGE (idempotent)
- KRX/뉴스/BOK/KOSIS/FTC 5종 source 자동 청크

## CLI 명령

| 명령 | 용도 |
|---|---|
| `polaris ingest [OPTIONS]` | raw 수집 (DART/뉴스/KRX/BOK/KOSIS/FTC). 옵션: `--only`, `--corp-codes`, `--from-year`, `--profile`, `--stage b1~b4` |
| `polaris build [OPTIONS]` | init-db + load + load-source all + load-finmetric 통합. `--skip-init`, `--sources none/news,krx,...` |
| `polaris init-db [--db all]` | 3DB 스키마 초기화 (build 안에 포함됨, 단독 호출 가능) |
| `polaris load [--db all]` | DART 청크·메타·그래프 적재 (build 안에 포함됨) |
| `polaris load-source <name\|all>` | 뉴스/KRX/BOK/KOSIS/FTC 5종 청킹·적재 (build 안에 포함됨) |
| `polaris load-finmetric` | Neo4j FinMetric 18,077 노드 (비교 Cypher 쿼리용, build 안에 포함됨) |
| `polaris promote-run` | 블루/그린 active 스위치 (검증 후 별도 실행) |
| `polaris verify` | 적재 정합 8/8 검증 |
| `polaris eval [--tag T]` | 벡터 골드셋 평가 (BM25+Dense+RRF+Rerank) |
| `polaris graph-eval` | 그래프 Cypher 평가 (비교 카테고리) |
| `polaris mark-boilerplate` | 보일러플레이트 청크 soft-delete |
| `polaris reembed-text` / `reembed-table` | 청크 재임베딩 (Contextual prefix) |

## 매일 cron — 증분 안전

```powershell
polaris ingest --only news,krx     # 1~2분 (캐시로 신규만)
polaris load-source news           # 새 뉴스 회사 매칭 + 적재 (LLM 캐시)
polaris load-source krx            # 이번달 청크만 갱신
polaris verify                     # 정합 재확인
```

모든 단계가 **로컬 파일 캐시 + chunk_id 결정론** 기반이라 매일 돌려도 row 중복 안 쌓임.

## 원본 저장 정책 (SSOT)

| 데이터 | 저장 위치 | 비고 |
|---|---|---|
| **뉴스 본문** | MariaDB `news_raw.body` (LONGTEXT) | RDB 가 SSOT. raw json 파일은 백업·캐시 |
| **DART JSON 원문** | MariaDB `dart_raw_index.body_json` (LONGTEXT) | RDB 가 SSOT. 파일 (`rawData/{cc}/dart/*.json`) 은 백업 |
| **사업보고서 HTML/PDF** | 파일 (`rawData/{cc}/documents/`) | RDB 엔 `document_index.snapshot_path` 만 (50~500GB 부담 큼) |
| **청크 텍스트** | MariaDB `chunk_index.embedding_text` | 1500자 잘림. 벡터는 Qdrant |

새 뉴스/DART 수집 시 자동으로 RDB INSERT (`bulk_collect`). 기존 데이터는 `polaris migrate-news` / `polaris migrate-dart` 로 일괄 마이그레이션 가능.

## 문서

- [INSTALL](docs/INSTALL.md) — GPU별 설치 (CUDA/ROCm/CPU/DirectML)
- [ARCHITECTURE](docs/ARCHITECTURE.md) — 3DB 역할 + 검색 파이프라인
- [BENCHMARKS](docs/BENCHMARKS.md) — 평가 결과 + 개선 이력
- [ADR](docs/adr/) — 결정 이력
  - 001 Contextual Retrieval / 002 비교 → 그래프 분리 / 003 BM25 자유서술 비활성
  - 004 RDB SSOT (news + DART JSON) / 005 뉴스 매칭 제거 / 006 PDF 3종 only
- [CHANGELOG](CHANGELOG.md)
