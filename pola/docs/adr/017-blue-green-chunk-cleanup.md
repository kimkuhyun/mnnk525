# ADR 017 — Blue/Green promote 시 옛 run Chunk cleanup

**날짜**: 2026-05-27
**상태**: Proposed
**우선순위**: P1

## 결정

`promote_run.py` 에 옛 run 의 Chunk + 관련 엣지 cascade delete 단계 추가. 기존 stale chunk 169,465건은 일회성 cleanup 스크립트로 정리.

## 배경 (진단 수치)

| 측정 | 값 |
|---|---|
| Chunk total (전체) | 234,950 |
| Chunk (active_run_id) | 65,485 |
| Stale chunk | **169,465** |
| 누적 run 수 | 4 |
| active_run_manifest.standby_status | `cleanup_pending` |

→ blue/green 패턴이 *그린만 누적되는* 상태. 디스크/메모리 낭비 + 옛 run 의 청크가 쿼리에 섞일 위험.

## 원인 (코드 위치)

1. `src/polaris/db/promote_run.py` — `active_run_manifest` 만 swap. Neo4j Chunk 노드의 cleanup 단계 없음.
2. standby_status 가 `cleanup_pending` 인 채로 남아 있어 다음 promote 도 막힘.

## 변경 사항

### Blue/Green 정책 (재정의)
```
active_run         : 사용자 쿼리에 보이는 run
standby_run        : 다음 promote 대상 (cleanup 끝난 상태여야 함)
older_runs         : 그 외 — DROP 대상

쿼리/검색은 active 만, 적재는 standby 에. promote 후 옛 active 는 standby 자리로 이동하고
직전 standby (older) 는 cleanup 후 사라짐.
```

### 코드
- **`src/polaris/db/promote_run.py`**
  - swap 직후 `_cleanup_older_runs(drop_run_ids)` 호출:
    ```cypher
    MATCH (c:Chunk) WHERE c.run_id IN $drop DETACH DELETE c
    MATCH (m:FinMetric) WHERE m.run_id IN $drop DETACH DELETE m
    MATCH (s:Statement) WHERE s.run_id IN $drop DETACH DELETE s
    MATCH (e:Event) WHERE e.run_id IN $drop DETACH DELETE e
    ```
  - swap 결과 `cleanup_pending` 표시 → cleanup 완료 시 `cleaned` 로 갱신
- **신설 `src/polaris/db/cleanup_run.py`** — 단일 run 의 Chunk/Metric/Statement/Event 모두 cascade delete

### 마이그레이션 (일회성)
- **`scripts/cleanup_stale_chunks.py`** (신설)
  - `MATCH (c:Chunk) WHERE NOT c.run_id IN [active, standby] DETACH DELETE c` 등
  - `--dry-run` 으로 카운트 미리보기, `--apply` 로 실행
  - 실행 후 `MATCH (c:Chunk) RETURN count(DISTINCT c.run_id), count(c)` 검증

### 문서
- 본 ADR 017
- `docs/ARCHITECTURE.md` 의 "blue/green lifecycle" 섹션 갱신

## 검증

```cypher
-- target: run_count ≤ 2 (active + standby 만)
MATCH (c:Chunk)
RETURN count(DISTINCT c.run_id) AS run_count, count(c) AS total_chunks
-- 기대: run_count=2, total ≈ 130,000 (active + standby)
```

```sql
-- MariaDB
SELECT active_run_id, standby_run_id, standby_status FROM active_run_manifest WHERE id=1;
-- standby_status: 'ready_to_promote' 또는 'cleaned'
```

## 롤백

- ⚠️ **cleanup 은 destructive (DETACH DELETE)** — 실행 전 Neo4j snapshot 필수
- 한 번 삭제하면 옛 run 청크 복구 불가 (재적재만 가능)
- `--dry-run` 으로 카운트 확인 후 명시적 `--apply` 만 실행
