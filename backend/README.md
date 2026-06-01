# POLARIS Backend

한국 공시(DART) 기반 **GraphRAG 에이전트** 백엔드. FastAPI + 3-DB(MariaDB·Neo4j·Qdrant) + Claude.

## 요구사항
- Python 3.11, [uv](https://docs.astral.sh/uv/)
- 3-DB 실행: 저장소 루트에서 `docker compose up -d`

## 설치 & 실행
```bash
uv sync                  # 의존성 설치 (.venv 자동 생성)
cp .env.example .env     # 환경변수 (기본값은 docker-compose와 동일)
uv run uvicorn app.main:app --port 8000
```
개발 중 자동 리로드: `uv run uvicorn app.main:app --reload --port 8000`

확인:
- http://localhost:8000/api/health
- http://localhost:8000/api/db/status  (3-DB 연결 상태)

## 구조
```
app/
  config.py   # .env 설정 (3-DB · Ollama · Claude)
  db.py       # 3-DB 연결 헬퍼 (mariadb_conn / neo4j / qdrant)
  main.py     # FastAPI 앱 (health, db/status) — 이후 GraphRAG 엔드포인트 추가
```

## 환경변수
`.env.example` 참조. 핵심: 3-DB 접속, `OLLAMA_BASE`(임베딩 bge-m3), `ANTHROPIC_API_KEY`(에이전트).

## 다음 단계 (예정)
질문 → (Qdrant 의미검색 + Neo4j 관계탐색) → 근거(rcept_no) 붙은 답변 에이전트 엔드포인트.
