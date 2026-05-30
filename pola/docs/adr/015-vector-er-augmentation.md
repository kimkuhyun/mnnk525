# ADR 015 — LLM·Vector ER 보강으로 unlinked 회사·인물 그래프 진입

**날짜**: 2026-05-27
**상태**: Proposed
**우선순위**: P3

## 결정

DART corps.json 미매칭 회사/인물을 LLM 추출 결과 + 벡터 ER (cosine ≥ 0.85) 로 alias 보강. 기존 unlinked.jsonl 23,845건 재매칭.

## 배경 (진단 수치)

| 라벨 | 전체 | LLM | LLM % |
|---|---:|---:|---:|
| Organization | 1,198 | 58 | 4.84% |
| Person | 646 | 1 | **0.15%** |
| Product | 35 | 35 | 100.0% |
| Technology | 10 | 10 | 100.0% |
| Place | 40 | 40 | 100.0% |
| Statement | 1,037 | ? | ? |

→ Organization/Person 은 DART 결정론에 의존, LLM 보강 거의 없음. 그래서 *DART 에 없는 해외법인·비상장 회사* 가 unlinked.jsonl 에 매장.

## 원인 (코드 위치)

1. `src/polaris/graph/linker.py` — alias 매칭은 `lexicon/aliases.yaml` 와 DART corps.json 만 lookup. LLM 추출된 회사 이름이 alias 와 정확 매칭 안 되면 unlinked.
2. 벡터 ER (embedding 유사도 매칭) 이 코드상 존재하지만 임계가 보수적 (≥0.92?) 이거나 비활성.

## 변경 사항

### 코드
- **`src/polaris/graph/linker.py`**
  - 새 함수 `vector_er_match(name, threshold=0.85, top_k=5)`:
    1. name 을 bge-m3 임베딩
    2. 기존 Organization 노드 이름 임베딩과 cosine 비교
    3. ≥0.85 매칭 시 corp_code 반환
  - 단계적 retry 의 마지막 단계로 vector ER 추가
- **`src/polaris/graph/lexicon/aliases.yaml`**
  - vector ER 매칭 결과를 자동 append (캐시 효과)
- **`src/polaris/graph/extractors/llm_entity.py`**
  - Person 추출 결과에 회사 컨텍스트 (`employer_org`) 추가 — 같은 이름 인물 disambiguation 용

### 마이그레이션
- **`scripts/relink_unlinked_with_vector_er.py`** (신설)
  - unlinked.jsonl 23,845건 순회
  - 각 entity 에 대해 vector ER 시도
  - 매칭된 항목: `relinked.jsonl` 로 분리, alias 사전 갱신, Neo4j 적재
  - `--dry-run` / `--apply`

### 문서
- 본 ADR 015
- `docs/lexicon/aliases.yaml` 의 자동 갱신 정책 명시

## 검증

```cypher
-- LLM 보강 비율 (target: Org 15%+, Person 5%+)
MATCH (o:Organization)
RETURN count(o) AS total,
       sum(CASE WHEN 'LLMExtracted' IN labels(o) THEN 1 ELSE 0 END) AS llm,
       sum(CASE WHEN 'LLMExtracted' IN labels(o) THEN 1.0 ELSE 0.0 END)/count(o)*100 AS pct
```

```
-- unlinked 감소
data/.../unlinked.jsonl: 23,845 → 5,000 이하
data/.../relinked.jsonl: 신규 생성
```

## 롤백

- alias yaml 의 vector ER 자동 추가 행은 별도 주석 (`# auto-er`) 으로 마킹 → 일괄 회수 가능
- Vector ER 매칭은 *추가만* (기존 노드 변경 X) — 안전
