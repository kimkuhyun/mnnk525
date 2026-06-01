# POLARIS

> **한국 공시(DART) 기반 GraphRAG 에이전트.** 질문하면 벡터(의미검색)+그래프(관계탐색)로 찾아 **공시 근거(rcept_no)까지 붙여** 답한다. 지분·재무·관계를 한 번에.
> 대상 3사: 삼성전자(00126380) · SK하이닉스(00164779) · 한미반도체(00161383).
> 목적: AI 엔지니어링 학습 / 포트폴리오.

---

## 구조

| 폴더 | 역할 |
|---|---|
| `db/` | DART 수집 → 청킹 → 임베딩 → 3-DB 적재 → Claude 추출 (uv) |
| `backend/` | FastAPI 서빙 — GraphRAG 에이전트 API (uv) |
| `frontend/` | React + Vite — 진입화면(Landing) |
| `docs/DBdocs/` | **DB 설계 SSOT** (`README` + `01_mariadb` + `02_qdrant` + `03_neo4j`) |
| `docker-compose.yml` | 3-DB(MariaDB·Neo4j·Qdrant)만. 적재/서빙은 분리 |

> 데이터 소스 = **DART 공시 단일**. 적재(`db/`)와 서빙(`backend`/`frontend`)은 분리 — 서버 배포 시 git에서 받아 기동.

## 3-DB

| DB | 포트 | 역할 |
|---|---|---|
| MariaDB | 3307 | 원본(`dart_raw_index`) · 청크(`chunk_index`) · 재무(`fin_metric`) · 근거(`extraction_provenance`) |
| Qdrant | 6333 | 청크 임베딩 의미검색 (`polaris-chunks`, bge-m3 1024d Cosine) |
| Neo4j | 7687 | 관계 그래프 — 지분·임원·재무(정형) + 공급·제품(추출). 지분+재무 1급 |

교차키: `corp_code` · `rcept_no` · `chunk_id`. 출처구분: `extracted_by='claude'`(추출) / `NULL`(DART 사실). 상세 → `docs/DBdocs/`.

## 띄우기

```bash
# 1) 3-DB (루트)
docker compose up -d

# 2) 백엔드 (서빙)
cd backend
uv sync
cp .env.example .env          # 기본값은 docker-compose와 동일
uv run uvicorn app.main:app --port 8000
#   확인: http://localhost:8000/api/health , /api/db/status

# 3) 프런트 (진입화면)
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

## 데이터 적재

DART 공시를 받아 3-DB에 적재하는 파이프라인은 `db/` 에서 담당:
**DART fetch → 청킹(산문 800/80 + 섹션 프리픽스, 표는 table_nl) → bge-m3 임베딩 → Qdrant/MariaDB/Neo4j 적재 → Claude 관계 추출(근거 PROV)**.
`db/.env` 에 `DART_API_KEY` · 대상 `POLARIS_CORPS` 가 있다. (Windows 한국어 출력 시 `PYTHONIOENCODING=utf-8`)

## 현재 상태 (작업 중)

- `backend/` — health / db-status 스캐폴드. GraphRAG 에이전트 엔드포인트(질문 → 그래프+벡터 → 근거 답변)는 작업 예정.
- `db/` — DART 로더 작업 예정 (`.env` 보존됨).
- `frontend/` — 진입화면(Landing)만. 워크스페이스는 추후.
- 데이터 — DART 재수집 예정.

> 설계 단일 진실(SSOT)은 `docs/DBdocs/`. 변경 시 그곳을 먼저 갱신한다.
