# ADR 010 — Chunk evidence 엣지 부착 실패 복구

**날짜**: 2026-05-27
**상태**: Proposed
**우선순위**: P0

## 결정

`linker.py` 의 entity-chunk 매칭 임계를 단계적 retry 로 변경하고, `merger.py` 의 hasActor/hasObject 부착이 silently skip 하는 부분에 counter+warning 을 도입. 기존 unlinked 23,845건은 마이그레이션 스크립트로 재처리.

## 배경 (진단 수치)

| 측정 | 값 |
|---|---|
| Chunk total (current run) | 65,485 |
| Chunk with evidence edges | ~110 (0.16%) |
| Chunk isolated | 65,375 (99.84%) |
| hasActor edges total | 753 |
| hasObject edges total | 954 |
| Chunk total (all runs) | 234,950 |
| unlinked.jsonl 누적 | 23,845 |

→ vector RAG 가 청크 12개 끌어와도 그중 평균 0.02개만 graph 1-hop 결합 가능. 사실상 graph RAG 무력화.

## 원인 (코드 위치)

1. `src/polaris/graph/linker.py` — entity → corp_code/person_id 매칭 시 *정확 일치* 만. 부분일치(substring) / 임계 단계별 retry 없음.
2. `src/polaris/graph/merger.py:hasActor/hasObject` 부착 시점 — `chunk_id` 가 entity 추출 결과에 없거나 chunk run_id 와 불일치 시 silently 누락.
3. `src/polaris/graph/extractors/` 의 entity 추출 결과 vs chunk 매칭 갭 — alias dict 미커버 회사가 unlinked.jsonl 로 떨어짐.

## 변경 사항

### 코드
- **`src/polaris/graph/linker.py`**
  - `match_entity_to_chunk()` 에 단계적 retry: ① exact name → ② canonical name (㈜/(주) 제거) → ③ alias 사전 → ④ substring (>=4자, 임계 0.85)
  - 매 단계별 매칭 카운터를 stderr 로 출력
- **`src/polaris/graph/merger.py`**
  - hasActor/hasObject MERGE 직전 `assert chunk_id IS NOT NULL` 가드. null 이면 카운터 누적 + warning log
  - 부착된 엣지 수 / 시도 수 / 실패 수 통계 print 추가
- **`src/polaris/graph/extractors/llm_entity.py`**
  - 추출 결과에 `source_chunk_id` 필드 강제 (현재 옵셔널)

### 마이그레이션
- **`scripts/migrate_relink_unlinked.py`** (신설)
  - `unlinked.jsonl` 23,845건 읽어 새 linker 로 재매칭
  - 새로 매칭된 항목은 `relinked.jsonl` 로 분리 + Neo4j 에 hasActor/hasObject 적재
  - 실행 모드: `--dry-run` (카운트만) / `--apply`

### 문서
- 본 ADR 010

## 검증

```cypher
-- target: coverage 0.16% → 30%+
MATCH (c:Chunk) WHERE c.run_id=$active_run
WITH count(c) AS total
MATCH (c:Chunk)-[:hasActor|hasObject]-() WHERE c.run_id=$active_run
RETURN count(DISTINCT c) AS with_edges,
       count(DISTINCT c)*100.0/total AS coverage_pct
```

```
-- 부수 검증: unlinked 잔존
파일: data/.../unlinked.jsonl  현재 23,845 → 목표 5,000 이하
파일: data/.../relinked.jsonl  새로 매칭된 건수
```

## 롤백

- linker.py 의 단계적 retry 는 신구 모드 토글 가능 (`POLARIS_LINKER_STRICT=1`)
- migration 은 dry-run 우선, apply 전 Neo4j snapshot (`neo4j-admin database dump`)
