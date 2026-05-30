# ADR 013 — Entity 추출 precision 가드 (일반명사 FP 차단)

**날짜**: 2026-05-27
**상태**: Proposed
**우선순위**: P2

## 결정

`llm_entity.py:69` SYSTEM_PROMPT 의 "일반명사 제외" 규칙을 Product/Technology 에서 Organization/Person/Place 까지 확장. 추출 후처리에 블랙리스트 검증 단계 추가. 기존 FP 노드는 점진적 제거.

## 배경 (진단 수치)

| 측정 | 값 |
|---|---|
| Organization 라벨에 `반도체` | 40 |
| Organization 에 `파운드리` | 7 |
| Product 에 `HBM/DRAM/NAND/파운드리` | 각 1 |
| Place 라벨 100% LLM (FP 가능성 ↑) | 40개 |
| Technology 라벨 100% LLM | 10개 |

추가 의심 (사용자 보고): IDM(176), Foundry(165), Fabless(143), 패널업체(33) 등 — 다른 run/누적 데이터에서 더 큼.

→ KEY LINKAGES 표에서 "반도체 → 직접 투자 → SK하이닉스" 같은 의미 없는 행 발생 가능.

## 원인 (코드 위치)

1. `src/polaris/graph/extractors/llm_entity.py:69` SYSTEM_PROMPT —
   ```
   Product / Technology 에는 "일반명사 제외" 규칙 명시 ✅
   Organization / Person / Place 에는 동일 가드 없음 ❌
   ```
2. `src/polaris/graph/extractors/filter.py` — 추출 후 일반명사 블랙리스트 검증 없음

## 변경 사항

### 코드
- **`src/polaris/graph/extractors/llm_entity.py:69`**
  - Organization 가드 추가:
    ```
    - 산업·업종 명 ("반도체", "전기전자업", "패널업체") 는 ORGANIZATION 이 아님.
      특정 법인명 (예: "삼성전자", "DB하이텍") 만 OK.
    - 일반 약자 (IDM, Foundry, Fabless, OEM, ODM) 는 ORGANIZATION 아님 — 사업 모델/카테고리임.
    ```
  - Person 가드 추가:
    ```
    - 사업부 약칭 (CE, DM, DS, DX, MX) 은 PERSON 이 아님. 한국 인명은 2-4자 한글 + 직위 패턴 권장.
    ```
  - Place 가드 추가:
    ```
    - 산업명 + 산업 ("자동차산업", "기계부품산업") 은 PLACE 가 아님. 행정구역 / 시설 이름 / 국가만 OK.
    ```

- **신설 `src/polaris/graph/extractors/blocklist.py`**
  - 일반명사 블랙리스트 (yaml 외부화 가능):
    ```python
    ORG_BLOCK = {"반도체", "메모리", "파운드리", "IDM", "Foundry", "Fabless",
                 "OEM", "ODM", "전기전자업", "패널업체", "디스플레이"}
    PERSON_BLOCK = {"CE", "DM", "DS", "DX", "MX", "임원", "이사회", "회장단"}
    PLACE_BLOCK = {"자동차산업", "기계부품산업", "반도체 FAB", "UAM"}
    PRODUCT_BLOCK = {"반도체", "메모리", "디스플레이", "자동차"}
    ```
- **`src/polaris/graph/extractors/filter.py`**
  - extract 후 entities 순회: 라벨별 blocklist 체크 → 일치 시 entity 폐기 + 카운터

### 마이그레이션
- **`scripts/prune_fp_entities.py`** (신설)
  - 기존 노드 중 blocklist 단어와 정확히 일치하는 Organization/Person/Place/Product 노드 찾기
  - 모드 1: `--isolate` — 엣지 다 제거하고 `:Suppressed` 라벨 추가 (안전)
  - 모드 2: `--delete` — DETACH DELETE (관계 함께 삭제, 사용자 확인 후)

### 문서
- 본 ADR 013
- `docs/blocklist.yaml` — 블랙리스트 외부화 (코드 변경 없이 추가 가능)

## 검증

```cypher
-- target: 0 (또는 :Suppressed 라벨로 격리)
MATCH (o:Organization) WHERE o.name IN ["반도체","메모리","파운드리","IDM","Foundry","Fabless","OEM"]
RETURN o.name AS name, count(*) AS c
```

```
-- 추출 카운터 (filter.py print)
extracted: 1234  blocked: 56  (blocked = blocklist 매칭 폐기)
```

## 롤백

- 블랙리스트 외부화 → yaml 만 비우면 즉시 원복
- `--isolate` 모드 사용 시 `:Suppressed` 라벨만 제거하면 원복
