# ADR 012 — Organization corp_code 정규화·중복 제거

**날짜**: 2026-05-27
**상태**: Proposed
**우선순위**: P1

## 결정

추출 경로별로 분기된 corp_code 생성 규칙 4가지를 *단일* deterministic 함수로 통일. 기존 330 dup groups (674 노드) 은 `dedupe_orgs.py` 로 병합하고 모든 엣지를 대표 corp_code 로 redirect.

## 배경 (진단 수치)

| 측정 | 값 |
|---|---|
| Organization 중복 그룹 | 330 |
| 중복 노드 합계 | 674 |
| 발견된 corp_code 패턴 | `16hex`, `X+7hex`, `XDJ_*`, `unknown_*` |

대표 사례:
- 동진쎄미켐 해외법인 11곳: 모두 ×3 (예: 북경동진쎄미켐과기유한공사 → `f498e18996efbbb0`, `X360BFCB`, `XDJ_BEIJING`)
- 곽신홀딩스(주) ×3, 한미컴퍼니(주) ×3, SOULBRAIN TX LLC ×3

→ 한미반도체의 자회사 통계가 1/3 로 표시되고, KEY LINKAGES 표에서 같은 회사가 3줄 차지.

## 원인 (코드 위치)

서로 다른 추출 경로가 자기만의 corp_code 규칙을 씀:

| 경로 | 규칙 | 예 |
|---|---|---|
| `extract_shareholders.py`, `extract_invests.py` | SHA1(이름)[:16] hex | `f498e18996efbbb0` |
| vector ER fallback | `X` + 7자 hex | `X360BFCB` |
| DART API name 매칭 | `XDJ_` + 영문약자 | `XDJ_BEIJING` |
| 일반 fallback | `unknown_` + 16자 hex | `unknown_02945f55c5dda253` |
| 표준 DART | 8자리 digit | `00161383` |

## 변경 사항

### 단일 corp_code 규칙
```
canonical_corp_code(name, country=None, jurisdiction=None) =
  ① DART corps.json 매칭되면 → DART 8자리 digit corp_code
  ② 아니면 → SHA1(normalize(name) + "|" + (country or "")) [:8] 의 hex (8자, prefix 'X' 부여 → 'X' + 7자 hex)

normalize(name) = name.lower()
  .replace("㈜","").replace("(주)","").replace("주식회사","")
  .replace("co.,ltd","").replace("inc.","").replace(",","")
  .replace(/\s+/g," ").strip()
```

→ 같은 회사명은 *항상* 같은 corp_code 산출.

### 코드
- **신설 `src/polaris/graph/common.py:canonical_corp_code(name, country=None)`** — 단일 진입점
- `extract_shareholders.py`, `extract_invests.py`, vector ER fallback, linker.py 의 corp_code 생성 부분 모두 `canonical_corp_code()` 호출로 통일
- 기존 코드의 `hashlib.sha1(...).hexdigest()[:16]` 같은 ad-hoc 생성 모두 제거

### 마이그레이션
- **`scripts/dedupe_orgs.py`** (신설)
  - 단계:
    1. Neo4j 에서 같은 `name` 이지만 다른 `corp_code` 인 그룹 추출
    2. 각 그룹의 *대표 corp_code* 선택 (DART digit > X-prefix > 기타 순)
    3. 대표 외 노드의 모든 incoming/outgoing 엣지를 대표 노드로 redirect
    4. 빈 노드 삭제
    5. 옛 corp_code 들은 대표 노드의 `aliases` 속성에 보존
  - 모드: `--dry-run` (변경 카운트만) / `--apply`

### 문서
- 본 ADR 012
- `docs/ARCHITECTURE.md` 에 `canonical_corp_code` 규칙 명시

## 검증

```cypher
-- target: 0 dup groups
MATCH (o:Organization) WHERE o.name IS NOT NULL
WITH o.name AS nm, count(DISTINCT o.corp_code) AS n
WHERE n > 1
RETURN count(*) AS dup_groups
```

```cypher
-- aliases 보존 확인
MATCH (o:Organization) WHERE o.aliases IS NOT NULL AND size(o.aliases) > 0
RETURN count(o) AS nodes_with_aliases
```

## 롤백

- 마이그레이션 전 Neo4j snapshot 필수
- `aliases` 속성에 옛 corp_code 들 보존 → 필요 시 노드 재분리 가능 (실용성은 낮음, 그래도 안전망)
