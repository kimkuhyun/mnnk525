# ADR 011 — Event PROV (wasDerivedFrom) 100% 누락 복구

**날짜**: 2026-05-27
**상태**: Proposed
**우선순위**: P0

## 결정

`merger.py` 의 `CQ_EVENT_PROV` 쿼리가 source_chunk_id null 시 silently skip 하는 부분에 counter+warning 추가. `extract_events.py` 추출 결과에 chunk_id 보존 강제. 기존 Event 639개는 `backfill_event_prov.py` 로 retroactive 매칭.

## 배경 (진단 수치)

| 측정 | 값 |
|---|---|
| Event total | 639 |
| Event with wasDerivedFrom → Chunk | 0 (0.0%) |
| Event orphan | 639 (100.0%) |
| Statement total | 1,037 |
| Statement with PROV | 271 (26.1%) |
| Statement orphan | 766 (73.9%) |

→ "이 Event(예: M&A·인사·계약) 의 출처가 어느 사업보고서·뉴스인가" 질의 불가. PROV-O 체인 끊김.

## 원인 (코드 위치)

1. `src/polaris/graph/merger.py:219` — `CQ_EVENT_PROV` 가 `MATCH (c:Chunk {chunk_id: e.source_chunk_id})` 패턴. Event 적재 시 `e.source_chunk_id` 가 null 이거나 동일 run_id 의 chunk 가 없으면 MERGE 가 0 rows → 조용히 skip.
2. `src/polaris/graph/extract_events.py` — Event 산출 jsonl 에 `chunk_id` 가 옵셔널. 정형 공시 추출 경로는 chunk_id 매핑 안 함.
3. Event 라벨 100% deterministic (LLM 0건) → 뉴스 본문의 *동적 사건* 자체가 graph 에 없음 (별도 ADR 다룰 가능성).

## 변경 사항

### 코드
- **`src/polaris/graph/merger.py:219` CQ_EVENT_PROV**
  - 변경 전: `MATCH (c:Chunk {chunk_id: e.source_chunk_id}) MERGE (e)-[:wasDerivedFrom]->(c)`
  - 변경 후: source_chunk_id null 시 `WHERE e.source_chunk_id IS NULL` 카운터 증가 + warning print. chunk 미존재 시 `OPTIONAL MATCH` 로 null 캡쳐 후 별도 카운터.
- **`src/polaris/graph/extract_events.py`**
  - 모든 Event 산출 dict 에 `source_chunk_id` 필수 (없으면 추출 단계에서 raise)
  - 정형 공시 → Event 추출 시 해당 공시 청크의 chunk_id 보존 (rcept_no + section_path 키로 lookup)
- **`src/polaris/graph/extractors/llm_event.py`** (있으면)
  - Event 추출 LLM 프롬프트에 `"chunk_id 출력 필수"` 추가

### 마이그레이션
- **`scripts/backfill_event_prov.py`** (신설)
  - 기존 Event 639개 순회. 각 Event 의 `(label, date, corp_code, rcept_no?)` 로 Chunk 후보 검색 → 가장 가까운 Chunk 와 `wasDerivedFrom` 생성
  - 매칭 못 한 Event 는 `event_orphan.jsonl` 로 dump (수동 검토용)
  - 실행 모드: `--dry-run` / `--apply`

### 문서
- 본 ADR 011
- `docs/ARCHITECTURE.md` 의 PROV 섹션 갱신 (검증 쿼리 추가)

## 검증

```cypher
-- target: orphan 100% → 20% 이하
MATCH (e:Event)
OPTIONAL MATCH (e)-[:wasDerivedFrom]->(c:Chunk)
RETURN count(DISTINCT e) AS total,
       count(DISTINCT c) AS with_prov,
       count(DISTINCT CASE WHEN c IS NULL THEN e END) AS orphan
```

```cypher
-- Statement PROV 도 점검 (현재 73.9%)
MATCH (s:Statement)
OPTIONAL MATCH (s)-[:wasDerivedFrom]->(c:Chunk)
RETURN count(s) AS total, count(c) AS with_prov
```

## 롤백

- backfill 은 새 엣지만 추가하므로 destructive 아님. 문제 시 `MATCH ()-[r:wasDerivedFrom]->() WHERE r.backfilled_at IS NOT NULL DELETE r` 로 일괄 회수.
- merger.py 의 counter 는 logging only — 동작 변경 없음.
