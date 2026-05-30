# POLARIS Backend (FastAPI)

3DB(MariaDB·Qdrant·Neo4j)를 읽어 REST API 제공. **적재는 `pola` CLI**, 여기는 **조회만**.

## 로컬 실행
```powershell
cd backend
copy .env.example .env          # 필요시 DB 주소 수정
uv venv && uv pip install -e .  # 또는 pip install -e .
uv run uvicorn app.main:app --reload --port 8000
```
- 문서(Swagger): http://localhost:8000/docs
- 헬스: http://localhost:8000/api/health
- 3DB 상태: http://localhost:8000/api/db/status  ← pola docker 떠 있어야 ok

## 구조
```
app/
├─ main.py        FastAPI 앱 + CORS + 라우터 등록
├─ config.py      .env 설정 (3DB 접속, CORS)
├─ db.py          3DB 커넥션 (mariadb / qdrant / neo4j)
└─ routers/
   ├─ meta.py     /api/health, /api/db/status
   └─ (추가) dashboard.py, graph.py, ask.py …  ← 화면별 엔드포인트
```

## 화면별 라우터 추가 패턴
`app/routers/dashboard.py` 만들고 `main.py` 에 `include_router`. 데이터는 `db.py` 의 커넥션 사용.
검색/GraphRAG 는 pola 엔진 재사용 가능: `pip install -e ../pola` → `from polaris.retrieve import ...`

## 배포 (도커)
루트 `docker-compose.yml` 에서 backend·frontend·3DB 함께 기동. `.env` 로 서버 DB 주소 주입.
