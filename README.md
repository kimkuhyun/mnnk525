# POLARIS

> **흩어진 기업 정보(공시·뉴스·특허·통계)를 엮어 "관계 지도"로 보여주는 기업 관계 인텔리전스.**
> 1차 시드 = 반도체 3사(삼성전자·SK하이닉스·한미반도체).

---

## 띄우기

### ① 도커

```powershell
docker compose up -d --build
```
→ 프런트 `http://localhost` · API `http://localhost:8000/docs` · 3DB 포함.
**`npm install`·`uvicorn` 직접 실행 불필요** (도커가 빌드).

### ② 개발 모드 

```powershell
docker compose up -d mariadb qdrant neo4j      # 3DB만 도커로

# 백엔드 (새 터미널)   → http://localhost:8000/docs
cd backend ; uv run uvicorn app.main:app --reload

# 프런트 (새 터미널)   → http://localhost:5173
cd frontend ; npm install ; npm run dev        # npm install 은 첫 1회만
```
→ 진입화면 **시작하기** → 대시보드.

## 구조

| 폴더 | 역할 |
|---|---|
| `pola/` | **데이터 적재 CLI + RAG 엔진** (3DB 적재·검색·그래프) |
| `backend/` | **FastAPI** — 3DB 조회 → REST API (`/api/...`) |
| `frontend/` | **React + Vite** — 화면 (진입화면·대시보드 등) |

> 적재(`pola`)와 서비스(`backend`/`frontend`)는 분리. 서버 DB에 **로컬 CLI로 원격 적재** 가능.

## 처음부터 재현 (전체 파이프라인 — 다른 PC·다른 사람도 로컬로)

> 모든 단계 로컬·멱등. LLM 단계(관계 추출·감성)는 **로컬 Ollama(qwen)** 로 돌리거나, 커밋된
> 추출 산출(`news_extracts/*.jsonl`)로 LLM 없이 재현 가능. ⚠️ Windows 는 `$env:PYTHONIOENCODING="utf-8"` 필수.

```powershell
# 0) 3DB 띄우기
docker compose up -d mariadb qdrant neo4j

# 1) pola 준비 (적재 엔진)
cd pola ; uv sync --extra cuda ; copy .env.example .env   # .env 에 DART_API_KEY 등 입력
$env:PYTHONIOENCODING="utf-8"

# 2) DART 정형·통계 (공시·재무·지분·임원·KRX·BOK·KOSIS·FTC)
uv run polaris build ; uv run polaris promote-run ; uv run polaris verify   # 11/11 PASS

# 3) 뉴스 크롤 → 3DB (회사별 키워드. DART build 이후에!)
uv run python -m polaris.ingest.news_crawl.run --since 2026-01-01 --sources 전자신문 한국경제 --keyword 삼성전자 --full
uv run python -m polaris.ingest.news_crawl.load

# 4) 관계 그래프 (MENTIONS + 엔티티 관계)
#    (a) 커밋된 추출로 즉시 재현 — LLM 불필요:
uv run python -m polaris.ingest.news_crawl.graph_load --input full_00126380.jsonl
#    (b) 새로 추출하려면: export_batches → Claude(Workflow) 또는 로컬 qwen → assemble → graph_load
#        (상세: src/polaris/ingest/news_crawl/README.md)

# 5) 감성·주가·일별요약 — 모두 로컬 재현
uv run python -m polaris.analyze.sentiment    # → sentiment_daily (Ollama qwen)
uv run python -m polaris.analyze.stock_load   # → stock_daily (KRX JSON 멱등 적재)
uv run python -m polaris.analyze.daily_digest # → news_daily_summary (Ollama qwen, 재개가능)

# 6) 서비스
cd ../backend ; uv run uvicorn app.main:app --reload     # http://localhost:8000/docs
cd ../frontend ; npm install ; npm run dev               # http://localhost:5173
```

화면: 진입 → **시작하기** → 워크스페이스(관계지도 마인드맵 + 트렌드 탭 + 행보 타임라인). 백엔드 API가 채움:
`/api/graph` `/api/dashboard` `/api/company` `/api/activity`
`/api/stock/{corp}` `/api/relation-top/{corp}` `/api/daily-digest/{corp}` `/api/news-timeline/{corp}`
`/api/sentiment` `/api/news` `/api/evidence`.

