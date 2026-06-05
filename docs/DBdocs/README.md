# POLARIS — 공시 중심 GraphRAG 설계서

한국 공시(DART)를 근거로 답하는 GraphRAG 에이전트의 데이터베이스 설계 메인 문서입니다.
질문이 들어오면 의미검색과 그래프탐색을 합쳐, 항상 출처(공시 접수번호 `rcept_no`)가 붙은 답변을 만듭니다.
지분구조와 재무를 1급 시민으로 다루고, 시점별 변화를 감지하는 것이 핵심입니다.

> 목적: 사업화가 아니라 AI 엔지니어링 학습·포트폴리오 용도입니다.
> 기준일: 2026-06-05 (적재 41개사)

---

## 1. 한눈에 보는 구조

POLARIS는 3개의 데이터베이스가 각자 역할을 나눠 맡습니다.
하나는 "사실의 원본", 하나는 "의미로 찾기", 하나는 "관계로 따라가기"를 담당합니다.

### 3-DB 역할

| DB | 포트 | 한 줄 역할 | 담는 것 |
|----|------|-----------|---------|
| MariaDB | 3307 | 원본 SSOT(단일 진실) + 조인 허브 | 공시 원본, 정형 재무, 청크 텍스트, 추출 근거원장(PROV) |
| Qdrant | 6333 | 의미검색(벡터) | 청크 임베딩(bge-m3, 1024차원, Cosine) |
| Neo4j | 7687 | 관계 그래프 + 멀티홉 탐색 | 엔티티·관계, 지분·재무 1급, 근거추적(PROV) |

SSOT = Single Source of Truth. 즉, 같은 사실이 여러 군데 흩어져 있을 때 "원본은 여기"라고 못 박는 곳이 MariaDB입니다.

### 분담 그림 (ASCII)

```
                         [ 사용자 질문 ]
                               |
        +----------------------+----------------------+
        |                      |                      |
        v                      v                      v
  +-----------+         +-------------+         +-----------+
  |  Qdrant   |         |   Neo4j     |         |  MariaDB  |
  |  (6333)   |         |   (7687)    |         |  (3307)   |
  |           |         |             |         |           |
  | 의미로     |  chunk  | 관계로       |  본문/  | 사실의     |
  | 찾기       |  _id    | 따라가기     |  수치   | 원본·조인  |
  | (벡터검색) | ------> | (멀티홉)     | <-----> | (SSOT)    |
  +-----------+         +-------------+         +-----------+
        ^                                             ^
        |              임베딩 / 추출 / 정형 적재         |
        +----------------------- 적재 ------------------+
                               |
                         [ DART API ]
```

---

## 2. 교차키 3종

3개 DB를 하나로 꿰는 공통 식별자입니다. 모든 곳에서 형식을 똑같이 유지해야 합니다.

| 키 | 형식 | MariaDB 위치 | Qdrant 위치 | Neo4j 위치 |
|----|------|-------------|-------------|-----------|
| `corp_code` | 8자리 숫자 (기업 고유코드) | 기업·재무·지분·임원 테이블 PK/FK | payload 필드 | `(:Organization {corp_code})` |
| `rcept_no` | 14자리 숫자 (공시 접수번호) | `dart_raw_index` PK, 근거원장 | payload 필드 | `FinMetric`·`Chunk` 노드 속성 + 추출엣지 속성(관계 근거) |
| `chunk_id` | 16자리 hex (청크 식별자, 콘텐츠 해시이므로 단독 유일) | `chunk_index` PK | point id | `(:Chunk {chunk_id})` |

`rcept_no`가 답변의 출처가 되는 핵심 근거키입니다. 모든 추출 관계는 결국 이 번호로 역추적됩니다.

---

## 3. 데이터 흐름

DART에서 받은 원본이 어떻게 3개 DB로 퍼지는지의 경로입니다.
핵심은 `dart_raw_index`(원본 SSOT)에서 출발해 정형/본문 두 갈래로 나뉘는 것입니다.

```
DART API
   |
   v
dart_raw_index  (원본 SSOT, rcept_no 기준)
   |
   +--[정형 데이터]----> fin_metric (재무) / 지분 / 임원  ──┐
   |                                                      │ (청킹 우회, 정형 직행)
   |                                                      v
   |              Neo4j: FinMetric · IS_MAJOR_SHAREHOLDER_OF/INVESTS_IN(지분) · EXECUTIVE_OF(임원)
   |
   +--[본문 데이터]----> chunk_index (본문 청킹, chunk_id 기준)
                              |
                              +--(임베딩 bge-m3)----> Qdrant 컬렉션 (의미검색)
                              |
                              +--(추출)------------> Neo4j 관계(엣지 속성 chunk_id로 근거 역추적)
```

포인트:
- 정형 재무·지분·임원은 청킹을 거치지 않고 곧장 Neo4j로 들어갑니다(정형 직행).
- 본문은 `chunk_index`를 거쳐 임베딩(Qdrant)과 관계추출(Neo4j) 양쪽으로 갑니다.
- 관계추출은 Claude 직접 우선(로컬LLM은 빡센 QC 통과 시 조건부 허용), 추출 관계는 엣지 속성 `chunk_id`(→`Chunk`)·`rcept_no`로 근거 역추적됩니다(별도 FilingDocument/DERIVED_FROM 노드 없음).

### 3.1 청킹 정책 (본문 → `chunk_index`)

본문 청킹은 **정기보고서(사업·반기·분기) 원본**에만 적용한다. 그 외 공시는 정형 API(JSON)로 적재하며 청킹하지 않는다.

대상 구분 (사업보고서 기준 — 3사 챕터 구조 동일):
- 청킹 대상(정형 API에 없음): II.사업의 내용, III/3·III/5 재무제표 주석(특수관계자 거래 등), IV.이사의 경영진단(MD&A), V.감사의견 본문, X.대주주 거래내용, XI.기타 투자자보호, IX.계열회사 관계 서술.
- 청킹 스킵(정형 API가 SSOT): I.회사개요(자본금·자기주식), III/1·2·4(재무제표 본체)·6(배당)·7·8(자금·차입), VI.이사회, VII.주주, VIII.임원·직원·보수. → `fin_metric`/Neo4j 직행.

산문 (`chunk_type='text_micro'`):
- 분할 800자 / 80자(10%) 오버랩, 재귀 분할(문단→문장→문자).
- `embedding_text` = 프리픽스 헤딩 + 본문. 프리픽스 형식 `[회사명 · 문서(YYYY.MM) · section_path]` (contextual retrieval). 프리픽스는 `embedding_text`에만 넣고 Qdrant payload에는 넣지 않는다.
- `text_macro`(섹션 통째 부모 청크)는 예약값 — 현재 단계 미생성, 추후 답변 컨텍스트 보강이 필요할 때 도입.

표 (`chunk_type='table_nl'`):
- 고정 800 분할 금지. 표를 행 리스트로 펼쳐 자연어화(행마다 `헤더=값`), `(단위:…)` 캡션을 머리에 보존.
- rowspan/colspan 은 값 전개. 레이아웃용 단일셀 표(약 60%)는 스킵.
- 셀수 약 120 이하(≈1,500자): 표 1개 = 1청크. 120 초과: 행그룹 분할(헤더행을 매 청크에 반복 부착).

노이즈 정규화:
- 제거: 전각공백(`　`)→공백, 연속공백→1칸, 빈 줄 3연속+ 축약, 각주마커(`주N)`), 불릿/주의기호(`※ □ ○`), 표참조 마커(`<표N>`·`[표N]`).
- 보존: `△`(재무 음수), `㈜`(회사명), `(단위:…)`, 한자(한글 병기 의미), `「」`(법령 인용).
- DART XML 은 미이스케이프 `&` 가 섞여 있어 엄격 XML 파서(ElementTree/lxml strict) 금지 — 정규식 또는 `lxml(recover=True)` 로 추출한다.

`doc_date`: `chunk_index`에는 날짜 컬럼이 없다. 시계열·변화감지 필터용 `doc_date`(Qdrant payload)는 `document_index.date`에서 조인해 채운다.

### 3.2 컨텍스트 확장 (참고 — 추후 옵션)

기본 검색은 `text_micro`(800/80 + 프리픽스 헤딩)만으로 동작한다. 답변 컨텍스트나 근거 제시가 부족할 때 아래를 단계적으로 도입한다(현재 미구현, 설계 참고용).

- 원본 PDF = 사람용 근거 뷰어: 답변에 붙은 `rcept_no` → 저장된 정기보고서 PDF(`db/raw/{회사}/pdf/{rcept_no}.pdf`) 또는 DART 뷰어(`dart.fss.or.kr/dsaf001/main.do?rcpNo=`)를 열어 사용자가 원문을 직접 검증. LLM 컨텍스트가 아니라 사람 검증용이다(PDF 통째는 LLM에 넣지 않음).
- 이웃 청크 확장: micro 가 검색에 걸리면 같은 `section_path` 의 앞뒤 micro 를 `chunk_index` 에서 가져와 LLM 컨텍스트로 함께 제공(sentence-window). 별도 임베딩·parent 링크 불필요 — `text_macro` 의 가벼운 대체.
- `text_macro`(부모-자식, small-to-big): 위로도 부족할 때만. 매크로(부모 섹션)는 임베딩하지 않고 저장만 하며, micro 가 걸리면 부모 텍스트를 컨텍스트로 제공. 도입 시 `chunk_index` 에 부모 참조(`parent_id`) 컬럼 추가가 필요하다(섹션 통째를 그대로 임베딩하면 벡터가 뭉개지므로 임베딩 금지).

---

## 4. GraphRAG 검색 흐름

질문 한 건이 답변으로 바뀌는 4단계입니다.

1. 의미검색 — Qdrant `polaris-chunks` 에서 질문 임베딩과 가까운 청크를 찾아 `chunk_id[]`를 얻습니다.
2. 그래프 탐색 — Neo4j에서 그 `Chunk`들을 기점으로 관계·지분·재무를 멀티홉으로 따라갑니다.
3. 본문·수치 조회 — MariaDB에서 청크 원문과 정형 수치를 끌어와 사실을 확정합니다.
4. 답변 생성 — 근거(`rcept_no`)를 붙여 답변을 반환합니다.

```
질문
  └─① Qdrant 의미검색(polaris-chunks) → chunk_id[]
       └─② Neo4j: Chunk → 관계 + 지분/재무 멀티홉
            └─③ MariaDB: 본문 텍스트 + 정형 수치
                 └─④ 답변 + 근거(rcept_no)
```

이 구조 덕분에 "왜 그렇게 답했는지"를 항상 특정 공시까지 되짚을 수 있습니다.

---

## 5. 문서 구성

상세 설계는 DB별로 3개 파일에 나눠 정리합니다.

| 문서 | 내용 |
|------|------|
| [01_mariadb.md](01_mariadb.md) | MariaDB ERD — 원본 테이블, 정형 재무, 청크, 근거원장(PROV) |
| [02_qdrant.md](02_qdrant.md) | Qdrant 컬렉션 스펙 — bge-m3 1024차원 Cosine, payload |
| [03_neo4j.md](03_neo4j.md) | Neo4j 노드·관계·다이어그램 — 지분/재무 1급, 멀티홉, PROV 근거추적 |
| [04_graphrag.md](04_graphrag.md) | GraphRAG 답변 레이어 — 5단계 사다리, 재무 조회 규약(계정사전·연간연결 필터), 의도 카탈로그, 온톨로지 규칙 Cypher |

---

## 6. 변경 규칙 (위반 금지)

1. 스키마 우선 갱신 — 새 테이블·노드·엣지를 추가/변경하면 반드시 이 설계 문서를 먼저 갱신한 뒤 구현합니다.
2. 교차키 일관 — `corp_code`·`rcept_no`·`chunk_id`의 형식을 모든 DB에서 동일하게 유지합니다.
3. 관계 출처 구분 — 관계 엣지는 출처를 구분해 보존합니다.
   - `extracted_by = 'claude'`(또는 로컬LLM `'q3.5:9b'` 등) : 본문에서 추출(언급·해석)한 관계
   - `extracted_by IS NULL` : DART 공시에 명시된 사실 그대로
4. 근거추적 필수 — 모든 추출 관계는 **엣지 속성 `chunk_id`**(→ `(:Chunk {chunk_id})`)와 `rcept_no`로 원본 공시까지 역추적 가능해야 합니다 + MariaDB `extraction_provenance` 원장 1행(PROV-O 준용). **별도 reification/FilingDocument/DERIVED_FROM 노드는 만들지 않습니다**(v3 — 03_neo4j.md §1·§6).

---

## 7. 기존 설계(썸트렌드 융합)와 달라진 점

이전 설계는 SNS·트렌드 분석 성격이 섞여 있었습니다. 이번 v3는 공시 GraphRAG로 방향을 좁혔습니다.

| 구분 | 항목 | 기존 → v3 |
|------|------|----------|
| 제거 | 감성(sentiment) | 삭제 — 공시는 사실 기반이라 감성 분석 불필요 |
| 제거 | 키워드(keyword) | 삭제 — 키워드 집계 레이어 폐기 |
| 제거 | 뉴스 일별집계 | 삭제 — 뉴스 소스 자체 폐기(신규 추가 금지) |
| 제거 | 커뮤니티/SNS | 삭제 — 소스 자체 폐기 |
| 제거 | `document_unified` 통합레이어 | 삭제 — `dart_raw_index → chunk_index` 직행으로 단순화 |
| 승격 | 지분 + 재무 그래프 | 1급 시민으로 승격 — Neo4j `IS_MAJOR_SHAREHOLDER_OF`/`INVESTS_IN`/`IS_SUBSIDIARY_OF`(지분)·`FinMetric` |
| 승격 | 변화감지 | 시점별 변화 추적을 핵심 기능으로 채택 |

참고한 레퍼런스: Neo4j sec-edgar(Company/Person/Form/Chunk + OWNS{지분,시점}), Microsoft GraphRAG(Local/Global 검색), PROV-O(근거추적 표준).
