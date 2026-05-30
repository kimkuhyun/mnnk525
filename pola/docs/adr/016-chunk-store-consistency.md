# ADR 016 — Qdrant ↔ Neo4j Chunk 일관성 (양방향 sync)

**날짜**: 2026-05-27
**상태**: Proposed
**우선순위**: P3

## 결정

`load_neo4j.py` / `load_qdrant.py` 에 invariant 검증 + skip counter 추가. 마이그레이션 스크립트로 한쪽에만 있는 chunk 양방향 정리.

## 배경 (진단 수치)

| 측정 | 값 |
|---|---|
| Qdrant points (active collection) | 68,051 |
| Neo4j Chunk (active run) | 65,485 |
| Qdrant only | **2,566** |
| Neo4j only | 0 |
| Δ (Qdrant 우위) | +2,566 (단방향 누락) |

→ vector RAG 가 청크 매칭 후 `/api/chunk/{id}` 호출 시 404 발생 가능 (실제로 데모 중 발견됨 — Neo4j Chunk 노드 없음).

## 원인 (코드 위치)

1. `src/polaris/db/load_neo4j.py` — Chunk 노드 적재 시 일부 실패 silently. skip counter 미노출.
2. `src/polaris/db/load_qdrant.py` — Qdrant 적재 후 Neo4j 와 cross-check 단계 없음.

가능한 누락 시나리오:
- Neo4j 적재 중 transaction 실패 / retry 누락
- Chunk node 의 unique constraint 충돌
- run_id 매핑 오류

## 변경 사항

### 코드
- **`src/polaris/db/load_neo4j.py`**
  - Chunk 적재 시 try/except 안에 skip counter 누적
  - 적재 종료 시 `expected=N, loaded=M, skipped=N-M` print
  - 실패한 chunk_id 들을 `chunk_load_failures.jsonl` 로 dump
- **`src/polaris/db/load_qdrant.py`**
  - 동일 패턴 적용 (양방향)
- **신설 `src/polaris/db/verify_consistency.py`**
  - 호출 시 Qdrant.point_count vs Neo4j.Chunk(run=active).count 비교, diff 출력
  - polaris CLI 의 `verify` 명령에 통합

### 마이그레이션
- **`scripts/sync_chunk_set.py`** (신설)
  - Qdrant only 2,566개: 해당 chunk_id 의 본문이 디스크 (`2_Chuck/03_chunks/`) 에 있는지 확인 → 있으면 Neo4j 에 backfill
  - Neo4j only (현재 0): 해당 chunk 의 vector 가 임베딩 가능하면 Qdrant 에 backfill
  - `--dry-run` / `--apply`

### 문서
- 본 ADR 016
- `docs/ARCHITECTURE.md` 의 "store invariants" 섹션 추가:
  ```
  invariant: Qdrant.chunks(active_collection) == Neo4j.Chunk(run=active_run_id)
  검증: polaris verify
  ```

## 검증

```python
# polaris verify 의 출력
[verify] Qdrant points : 68,051
[verify] Neo4j  Chunk  : 68,051
[verify] diff          : 0  ✓ PASS
```

```cypher
-- Neo4j only 가 다시 생기지 않는지 모니터링
MATCH (c:Chunk) WHERE c.run_id=$active
RETURN count(*) AS neo4j_count
```

## 롤백

- backfill 은 추가 only — destructive 아님
- 시간 들여 손해 보는 것 외엔 위험 없음
