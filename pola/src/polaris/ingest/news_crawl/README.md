# 뉴스 파이프라인 (`news_crawl`)

뉴스 **수집(크롤) → 3DB 적재(v2)**. 회사별(`corp_code`)로 검색·관계·집계까지 연결.
정합 키 **`doc_id = sha1("news:"+news_id)`** 가 MariaDB·Qdrant·Neo4j 를 관통한다.

```
news_raw(크롤)
  └→ document_unified (corp_code·ts·title·url·body·meta)
       ├→ Qdrant polaris-doc-1024   (검색·묻기)
       ├→ Neo4j Document-[:ABOUT]->Organization  (이 기사는 어느 회사 것인가)
       ├→ mention_daily             (회사·일별 집계, evidence_doc_ids)
       └→ [관계 그래프 추출] Claude(Workflow) → graph_load
            ├→ (Document)-[:MENTIONS]->(entity)            (이 기사가 언급한 것)
            └→ (entity)-[SUPPLIES/PARTNERS_WITH/…]->(entity) (사야리식 관계지도)
```

## 재현 (2단계 — 둘 다 멱등, 재실행 안전)
```powershell
$env:PYTHONIOENCODING="utf-8"

# 1) 크롤: 전자신문·한경에서 "삼성전자" 기사, 2026-01-01~, 증분(news_id 중복 skip)
uv run python -m polaris.ingest.news_crawl.run --since 2026-01-01 --sources 전자신문 한국경제 --keyword 삼성전자 --full

# 2) 적재: news_raw → 3DB (upsert·MERGE — 재실행해도 중복 안 쌓임)
uv run python -m polaris.ingest.news_crawl.load
```

## 검증 (3DB 정합)
```powershell
uv run python -c "from polaris.config import mariadb_conn,qdrant_client,neo4j_driver as nd; c=mariadb_conn().cursor(); c.execute('SELECT COUNT(*) FROM document_unified WHERE source_type=\"news\"'); du=c.fetchone()[0]; q=qdrant_client().get_collection('polaris-doc-1024').points_count; s=nd().session(); n=s.run('MATCH (d:Document) RETURN count(d)').single()[0]; print('document_unified',du,'| Qdrant',q,'| Neo4j',n,'→', 'OK' if du==q==n else 'MISMATCH')"
```

## 구조
| 파일 | 역할 |
|---|---|
| `browser` / `sources` / `collect` / `extract` / `store` | **크롤** (CDP+Readability, 증분) |
| `load` | **3DB 적재** (news_raw → document_unified → Qdrant·Neo4j Document/ABOUT·mention_daily) |
| `graph_load` | **관계 그래프 적재** (Claude 추출 jsonl → MENTIONS + 엔티티 관계, 엔티티 링킹) |
| `../../../scripts/news_graph/` | 관계추출 헬퍼 (`export_batches.py` · `extract_workflow.template.js` · `assemble.py`) |

## 관계 그래프 추출 (MENTIONS + 엔티티 관계) — 사야리식 관계지도

뉴스 본문에서 엔티티와 **엔티티 간 관계**를 Claude(Workflow)로 추출 → Neo4j 적재.
씨드사(삼성·SK·한미)는 DART 정형 노드에 **통합**되고, 외국사(엔비디아·ASML 등)는 뉴스 노드로 생성된다.
ADR 021 (Claude-direct): Claude 가 `llm_extracts.jsonl` 작성 → 스크립트가 MERGE. jsonl = 체크포인트.

> **로컬 qwen 금지.** 엔티티 구분("삼성" vs "삼성전자", "HSB"=하트포드스팀보일러)·관계 정확도가
> 너무 낮음. Claude(Workflow 병렬)로 추출. 검증: 삼성 30건 샘플에서 반도체 공급·경쟁·협력 관계
> 정확 포착(qwen 대비 압도적). **전체는 `sonnet`(비용 1/5), 품질 의심 시 30건만 `opus` 샘플.**

### 0) 전제 — 해당 회사 뉴스가 3DB 에 있어야 (그리고 DART build 이후)
```powershell
$env:PYTHONIOENCODING="utf-8"
uv run python -m polaris.ingest.news_crawl.run --since 2026-01-01 --sources 전자신문 한국경제 --keyword SK하이닉스 --full
uv run python -m polaris.ingest.news_crawl.load          # 3DB (DART build 이후!)
```

### 1) 배치 파일 생성 → 2) Workflow 추출 → 3) 조립 → 4) 그래프 적재
```powershell
# 1) 배치화 (corp_code 단위). DIR/N 출력됨
uv run python scripts/news_graph/export_batches.py 00164779

# 2) Workflow 추출 (이 대화에서 어시스턴트가 실행)
#    scripts/news_graph/extract_workflow.template.js 의 DIR·N·MODEL 채워 Workflow 툴로 구동
#    → 결과 .output 파일 (result.docs = [{doc_id,entities,relations}])

# 3) 조립 + 정제 (자기루프·conf0 제거, 커버리지 점검)
uv run python scripts/news_graph/assemble.py <.output경로> 00164779
#    → data/4_dbGoldTest/news_extracts/full_00164779.jsonl

# 4) 그래프 적재 (멱등 — doc_ids 집합으로 중복 방지)
uv run python -m polaris.ingest.news_crawl.graph_load --input full_00164779.jsonl
```
- predicate 11종 통제 어휘: SUPPLIES·CUSTOMER_OF·PARTNERS_WITH·COMPETES_WITH·INVESTS_IN·ACQUIRES·JV_WITH·DEVELOPS·EXECUTIVE_OF·LICENSES·LITIGATION
- 누락 doc(에이전트가 가끔 1~2건 빠뜨림)은 `assemble.py` 가 보고 → 단건 jsonl 만들어 `graph_load` 로 백필
- 관계 엣지는 `extracted_by='claude'` + `evidence_count`(근거 기사 수=엣지 강도) 보유 → 정형(DART) 엣지와 구분

### 검증 쿼리 (관계지도)
```powershell
# 관계 타입 분포 + 씨드사 ego-graph (근거수 순)
uv run python -c "from polaris.config import neo4j_driver; s=neo4j_driver().session(); [print(r['t'],r['c']) for r in s.run(\"MATCH ()-[r]->() WHERE r.extracted_by='claude' AND type(r)<>'MENTIONS' RETURN type(r) t,count(*) c ORDER BY c DESC\")]"
```

### 엔티티 링킹 개선 (피드백 루프 — 회사 늘릴수록 정확)
- `EntityLinker` 가 alias 사전 + 벡터 ER 로 링크. 실패분 → `data/4_dbGoldTest/graph_extracts/{run}/unlinked_entities.jsonl`
- 자주 나오는 미링크/이름변형(예 `현대차`=`현대자동차`, 외국사)을 `organizations.yml` alias 에 추가 → 다음 회사부터 자동 정형 통합 (그래프 파편화 감소)

## 새 회사/언론사/키워드 추가
- 언론사: `sources.py` 의 `SOURCES` 에 `Section(...)` 추가
- 회사: `load.py` 의 `CORP_MAP` 에 `"회사명": "corp_code"` 추가 → `run`(키워드) → `load` → 위 관계 그래프 4단계

## ⚠️ 메모
- `CORP_MAP` corp_code 는 `corps.json` 확정값 (삼성 00126380 · SK 00164779 · 한미반도체 00161383)
- **실행 순서**: DART `build` → 뉴스 `load` → 관계 그래프(`export_batches`→Workflow→`assemble`→`graph_load`).
  build 가 `:Organization:Company` 정형 노드를 먼저 만들어야 뉴스 `MERGE (o:Organization {corp_code})` 가
  정형 노드에 매칭됨 (순서 바뀌면 라벨 충돌·고아 노드)
- 삼성 1차 결과(2026-05-30): 문서 2069 · MENTIONS 13,056 · 관계 엣지 2,992 · 뉴스노드 3,745
