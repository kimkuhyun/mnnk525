# POLARIS DB 설계서 — 04. GraphRAG 답변 레이어

질문이 답으로 바뀌는 검색·추론 규약. 로컬 LLM(qwen 9b, 순차 실행) 가정.
원칙: **숫자·관계·Cypher는 LLM이 생성하지 않는다**(CLAUDE.md 5번). LLM은 ①의도분류 ②슬롯추출 ③최종 한국어 서술만 하고, 검색은 사전작성 템플릿이 결정론적으로 실행한다("온톨로지 엔진 흉내" = 스키마 규칙을 Cypher로 박제).

---

## 1. 답변 5단계 사다리

아래로 갈수록 어렵고, LLM이 결정론 결과를 "해석"하는 비중이 커진다. 1~3은 결과를 표로 박제, 4~5만 모델이 서술.

| # | 단계 | 정의 | Retrieval | LLM 역할 |
|---|------|------|-----------|----------|
| 1 | 단답 사실 | 한 노드/한 값 직조회 | MariaDB SQL or 1-MATCH | 슬롯추출+표현 |
| 2 | 멀티홉 추론 | 관계 N홉 따라 종합 | `*1..n` 경로 Cypher | 경로 해석 |
| 3 | 지식그래프 최대 활용 | 지분+재무+공급+제품 교차 | 다중관계 조인 Cypher | 서브그래프 요약 |
| 4 | 온톨로지 엔진 흉내 | 스키마 규칙으로 암묵 사실 추론 | 규칙 Cypher + 파생엣지 | 규칙 적용·분류 |
| 5 | 인사이트 도출 | 패턴→해석, 새 관찰 | 2~4 결과 합성 | 가설·해석 |

현재 3사(+extra) 데이터 실현 가능성: 1·2 탄탄, 3 국소그래프로 가능, 4 시연 가능, 5 서사형 1~2건이 상한(통계적 일반화 금지).

---

## 2. 검색 파이프라인 (4단계 실행 흐름)

```
질문
 ├─[1] 의도분류 (qwen 9b)  → {intent, slots} JSON 만 출력
 ├─[2] 라우팅 (Python, 결정론)
 │     ├ 재무 숫자  → MariaDB fin_metric  (계정사전 + 연간·연결 필터)   ★Neo4j 아님
 │     ├ 관계/지분  → Neo4j 템플릿 Cypher (슬롯 바인딩)
 │     ├ 본문 사실  → Qdrant top-k → chunk_id → MariaDB chunk_index 원문
 │     └ 온톨로지   → 규칙 Cypher (전이지배·공통임원 파생)
 ├─[3] 근거 수화 (Python)  → rcept_no·chunk_id 출처 첨부 (PROV)
 └─[4] 답변작성 (qwen 9b)  → 위 결정론 결과를 한국어로 서술만
```

---

## 3. 재무 조회 규약 (함정 A·B·C 해결)

DART 재무는 같은 `(corp_code, account_id, bsns_year)`라도 **보고서종류·연결여부로 값이 여러 개**다(삼성 2024 매출 = 8행). 따라서:

### 3-1. 계정 사전 (C) — 질문어휘 → account_id
- `account_id`는 IFRS 원본명(`ifrs-full_Revenue`). 사용자 "매출"을 코드로 번역해야 쿼리 가능.
- 구현: `backend/app/account_dict.py` — `resolve_account("매출") → "ifrs-full_Revenue"`. 23개 핵심 계정 + 한국어 별칭. LLM 슬롯필링엔 `list_accounts()`(한국어명 목록)를 프롬프트에 제공.

### 3-2. 기본 필터 (A) — 중복 8개 중 정답 1개
- 단건 재무는 항상 **연간·연결** 기본: `reprt_code='11011' AND fs_div='CFS'`.
- `reprt_code`: 11011=사업보고서(연간)·11012=반기·11013=1분기·11014=3분기.
- `fs_div`: CFS=연결·OFS=별도. 분기/별도는 질문이 명시할 때만 변경.
- **정확한 단건 값의 SSOT = MariaDB `fin_metric`** (LLM이 SQL 생성 금지, 템플릿 고정).

```sql
-- 표준 재무 단건 템플릿 (슬롯: corp_code, account_id, year)
SELECT value, unit FROM fin_metric
WHERE corp_code = :corp_code AND account_id = :account_id
  AND bsns_year = :year AND reprt_code = '11011' AND fs_div = 'CFS';
```

### 3-3. Neo4j 재무 미러 (B) — 멀티홉용
- Neo4j `FinMetric`은 그래프 탐색(지분 따라가며 각 회사 재무)용 미러. 정확값은 MariaDB.
- 구분키 `reprt_code`·`fs_div`를 노드 속성으로 보유(2026-06-04 백필 완료). 멀티홉 재무는 `{reprt_code:'11011', fs_div:'CFS'}` 필터 필수(없으면 회사당 8개 중복).

---

## 4. 의도 카탈로그 (intent → 템플릿)

단답식 v0은 아래 핵심만. 더 늘리면 9b 분류 정확도 저하 — 10~12개 상한.

| intent | 질문 예 | 검색 | 단계 |
|--------|---------|------|------|
| `fin_value` | "삼성 2024 매출?" | MariaDB 표준 재무 템플릿(3-2) | 1 |
| `fin_trend` | "SK 매출 3년 추이" | fin_metric 연도 GROUP | 1 |
| `ownership_in` | "한미 최대주주?" | `IS_MAJOR_SHAREHOLDER_OF` 역방향 | 1 |
| `ownership_out` | "삼성이 투자한 회사" | `INVESTS_IN`\|`IS_MAJOR_SHAREHOLDER_OF` | 1 |
| `executives` | "SK 대표이사?" | `EXECUTIVE_OF` | 1 |
| `subsidiaries` | "삼성 종속회사" | `IS_SUBSIDIARY_OF` 역방향 | 1 |
| `affiliates_fin` | "삼성 자회사들 매출" | 지분 `*1..2` + 재무(3-3) | 2·3 |
| `supply_chain` | "한미 고객사" | `SUPPLIES_TO` | 2 |
| `products` | "삼성 제품" | `PRODUCES` | 1 |
| `related_party` | "A·B 특수관계?" | `RELATED_PARTY` 양방향 | 1·4 |
| `disclosure` | "주요 리스크" | Qdrant → chunk 원문 | 1 |
| `provenance` | "그 출처?" | chunk_id → rcept_no 역추적 | — |

---

## 5. 온톨로지 엔진 흉내 (4단계 규칙 Cypher)

OWL 리즈너 대신, 온톨로지 추론 규칙을 Cypher로 박제. 파생엣지는 출처 `derived_by='rule'`로 표시(claude/NULL과 구분 — 향후 03_neo4j.md 출처 3종 체계화).

```cypher
-- (a) 규칙 분류: 지분율 → K-IFRS 회계 등급
MATCH (a:Organization)-[r:IS_MAJOR_SHAREHOLDER_OF]->(b:Organization)
RETURN a.name, b.name, r.qota_rt,
  CASE WHEN r.qota_rt >= 50 THEN '지배(종속회사)'
       WHEN r.qota_rt >= 20 THEN '유의적영향(관계기업)'
       ELSE '단순투자' END AS 회계분류;

-- (b) 전이 추론: A→B→C 간접지배 (파생엣지 생성)
MATCH path = (a:Organization)-[:IS_MAJOR_SHAREHOLDER_OF*2..]->(c:Organization)
WHERE all(r IN relationships(path) WHERE r.qota_rt >= 50)
MERGE (a)-[:CONTROLS_INDIRECTLY {via_hops: length(path), derived_by:'rule'}]->(c);

-- (c) 공통임원 추론: 같은 사람이 두 회사 임원 → 인적 연결
-- 주의: person_id = sha1(corp_code|name|birth) 라 같은 사람도 회사별 다른 노드 →
--       반드시 p1.name=p2.name (이름매칭). person_id/동일노드로 짜면 영원히 0건.
MATCH (p1:Person)-[:EXECUTIVE_OF]->(a:Organization),
      (p2:Person)-[:EXECUTIVE_OF]->(b:Organization)
WHERE p1.name = p2.name AND elementId(a) < elementId(b)
  AND a.corp_code IS NOT NULL AND b.corp_code IS NOT NULL
MERGE (a)-[:INTERLOCKING_DIRECTORATE {via: p1.name, derived_by:'rule'}]->(b);
// ⚠ 동명이인 위험: 흔한 이름(김·이·박)은 다른 사람일 수 있음 → 신뢰도 낮음, 검증 필요.
```

---

## 6. 평가(eval)

골든셋(단계별 10문항, 정답 손박제) → 정확도·환각률·지연 측정. 1~3단은 DB값 완전일치, 4~5단은 근거 청크·rcept_no 첨부 여부로 채점. 데이터로 답이 나오는지 먼저 검증(1·2단 = 정형 직조회로 확정).
