# ADR 014 — Statement confidence 재계산 (self_confidence 단독 폐기)

**날짜**: 2026-05-27
**상태**: Proposed
**우선순위**: P2

## 결정

Statement 의 `confidence` 를 LLM self_confidence 단독에서 *4-factor weighted score* 로 교체.

## 배경 (진단 수치)

| 버킷 | 카운트 | 비율 |
|---|---:|---:|
| ≥0.95 | ~900 | 86.8% |
| 0.9~0.95 | 83 | 8.0% |
| 0.8~0.9 | 32 | 3.1% |
| 0.7~0.8 | 0 | 0.0% |
| <0.7 | 22 | 2.1% |
| null | 0 | 0.0% |
| **avg** | | **0.9654** |

→ 94.8% 가 ≥0.9. confidence 로 reranking·필터링하면 사실상 *모두 통과* — 신호 무력.

## 원인 (코드 위치)

LLM (`extractors/llm_*.py`) 이 `self_confidence` 를 자기 판단으로 0.9-1.0 사이에 박는 경향. 모델 자체의 calibration 문제.

```python
# 현재 (의사코드)
statement.confidence = llm_output["self_confidence"]
```

self-report 만으로는 *어느 statement 가 진짜 신뢰 가능한지* 판별 못함.

## 변경 사항

### 새 confidence 정의
```
final_confidence =
    w_self * self_confidence      # LLM 자기 평가 (지금)
  + w_ev   * normalize_log(evidence_count)  # 같은 statement 가 몇 개 chunk 에서 추출됐나
  + w_src  * multi_source_factor # 다른 출처 (회사 IR + 뉴스 등) 결합 시 가산
  + w_canon * canonical_match    # subject·object 가 canonical entity 와 매칭됐는지

가중치 권고 (실험 후 튜닝): w_self=0.30, w_ev=0.30, w_src=0.20, w_canon=0.20
```

### 코드
- **신설 `src/polaris/graph/extractors/scoring.py`**
  - `compute_final_confidence(statement, evidence, sources, canonical_ok) -> float`
  - 입력 4축, 출력 [0, 1]
- **`src/polaris/graph/merger.py`**
  - Statement MERGE 직전 `compute_final_confidence` 호출 후 결과를 `confidence` 에 저장
  - 원본 `self_confidence` 는 별도 속성 `self_confidence` 로 보존 (디버깅용)

### 마이그레이션
- **`scripts/rescore_statements.py`** (신설)
  - 기존 Statement 1,037 순회
  - 각 statement 의 evidence/sources/canonical 정보를 Neo4j 에서 join 으로 수집
  - 새 confidence 계산 후 update
  - `--dry-run` 모드로 변화 분포 미리보기 (예: 94.8% → 30%)

### 문서
- 본 ADR 014
- `docs/ARCHITECTURE.md` 의 "confidence semantics" 섹션 신설

## 검증

```cypher
-- 분포 검증 — 변경 후 더 넓게 퍼져야
MATCH (st:Statement)
RETURN
  sum(CASE WHEN st.confidence >= 0.9 THEN 1 ELSE 0 END) AS high,
  sum(CASE WHEN st.confidence >= 0.7 AND st.confidence < 0.9 THEN 1 ELSE 0 END) AS mid,
  sum(CASE WHEN st.confidence < 0.7 THEN 1 ELSE 0 END) AS low,
  avg(st.confidence) AS avg,
  count(st) AS total
-- target: high < 40%, avg 0.65~0.75
```

```cypher
-- self vs final 차이가 큰 statement sample (이상치 검증)
MATCH (st:Statement)
WHERE abs(st.self_confidence - st.confidence) > 0.3
RETURN st.subject_name, st.predicate, st.object_name,
       st.self_confidence, st.confidence
LIMIT 30
```

## 롤백

- `self_confidence` 원본은 별도 속성에 보존 → rescore_statements.py `--restore` 모드로 즉시 원복
