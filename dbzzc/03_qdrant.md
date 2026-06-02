# POLARIS DB 설계 — 03. Qdrant (벡터 DB)

Qdrant의 역할 = **공시 본문 청크의 의미검색 진입점**. 질문이 들어오면 가장 먼저 여기서 "비슷한 본문 청크"를 찾고, 그 결과로 받은 `chunk_id` 를 Neo4j/MariaDB로 연결한다.

> 벡터 DB는 관계형 DB와 달리 **ERD가 없다**. 정석은 **컬렉션 스펙 + payload 스키마** 표로 문서화. 이 문서도 그 관례를 따른다.

핵심 4가지만 정리:
1. **청킹** — 본문을 어떻게 잘랐는가
2. **임베딩** — 어떤 모델로 어떻게 벡터화했는가
3. **컬렉션·인덱스** — 어디에 어떻게 저장했는가
4. **검색 사용법** — 어떻게 꺼내 쓰는가

---

## 1. 청킹 (chunking) — 본문을 어떻게 잘랐나

### 1-1. 청킹 대상 선별

**정기보고서(사업·반기·분기) 본문만** 청킹한다. 그 외 공시는 정형 API(JSON)로 적재하고 **청킹하지 않는다**.

| 보고서 챕터 | 청킹? | 이유 |
|---|---|---|
| II. 사업의 내용 | **청킹** | 정형 API에 없는 서술 |
| III/3·III/5 재무제표 주석 (특수관계자 거래 등) | **청킹** | 정형 API에 없는 서술 |
| IV. 이사의 경영진단 (MD&A) | **청킹** | 정형 API에 없는 서술 |
| V. 감사의견 본문 | **청킹** | 정형 API에 없는 서술 |
| X. 대주주 거래내용 | **청킹** | 정형 API에 없는 서술 |
| XI. 기타 투자자보호 | **청킹** | 정형 API에 없는 서술 |
| IX. 계열회사 관계 서술 | **청킹** | 정형 API에 없는 서술 |
| I. 회사개요 (자본금·자기주식) | 스킵 | 정형 API가 SSOT |
| III/1·2·4 재무제표 본체 | 스킵 | `fin_metric` SSOT |
| III/6 배당, III/7·8 자금·차입 | 스킵 | 정형 API SSOT |
| VI. 이사회 | 스킵 | 정형 API SSOT |
| VII. 주주 | 스킵 | 정형 API SSOT |
| VIII. 임원·직원·보수 | 스킵 | 정형 API SSOT |

> 스킵 대상은 청킹 없이 `fin_metric` / Neo4j 직행. 본문보다 **정형 API 응답이 훨씬 정확**하기 때문.

### 1-2. 산문 청킹 (`chunk_type = 'text_micro'`)

| 항목 | 값 |
|---|---|
| 분할 크기 | **800자** |
| 오버랩 | **80자 (10%)** |
| 분할 방식 | 재귀 분할 (문단 → 문장 → 문자) |
| 임베딩 텍스트 | **프리픽스 헤딩 + 본문** |

**프리픽스 헤딩 형식**:
```
[회사명 · 문서(YYYY.MM) · section_path]
```
예: `[삼성전자 · 사업보고서(2024.03) · II. 사업의 내용 > 2. 주요 제품]`

> 이걸 **contextual retrieval** 이라 부른다. 청크 본문만 임베딩하면 "이게 어느 회사의 어느 섹션인지" 정보가 빠져서 검색 품질이 떨어진다. 헤딩을 앞에 붙여 임베딩하면 그 맥락도 함께 벡터에 반영됨.

**중요 규칙**: 프리픽스는 `embedding_text`(임베딩 대상)에만 넣고 **Qdrant payload에는 넣지 않는다**. payload는 검색 메타용이지 표시용이 아님.

### 1-3. 표 청킹 (`chunk_type = 'table_nl'`)

표는 800자 고정 분할을 **금지**한다. 대신 행 단위로 자연어화.

| 항목 | 처리 방식 |
|---|---|
| 분할 방식 | 행 리스트로 펼침. 행마다 `헤더=값` 자연어 |
| 캡션 | `(단위: ...)` 캡션을 머리에 보존 |
| rowspan/colspan | 값을 전개해 각 셀에 채움 |
| 레이아웃용 단일셀 표 (약 60%) | **스킵** (의미 없음) |
| 셀 수 ≤ 120 (≈1,500자) | 표 1개 = 1청크 |
| 셀 수 > 120 | 행그룹 분할 + **헤더행을 매 청크에 반복 부착** |

> 표를 그대로 임베딩하면 "헤더 정보" 가 분할로 잘려나가서 의미가 깨진다. 행마다 `매출액=300조`처럼 자연어로 풀어줘야 검색이 정확해짐.

### 1-4. `text_macro` (예약값)

섹션 통째를 부모 청크로 두는 방식. **현재 단계 미생성**, 추후 컨텍스트 보강이 필요할 때 도입 예정.

### 1-5. 노이즈 정규화 규칙

| 제거 | 보존 |
|---|---|
| 전각공백(`　`) → 공백 | `△` (재무 음수 기호) |
| 연속공백 → 1칸 | `㈜` (회사명 약자) |
| 빈 줄 3연속+ 축약 | `(단위: ...)` |
| 각주 마커 (`주N)`) | 한자 (한글 병기 의미) |
| 불릿/주의 기호 (`※ □ ○`) | `「」` (법령 인용) |
| 표 참조 (`<표N>`, `[표N]`) | |

> DART XML은 미이스케이프 `&` 가 섞여 있어 엄격 XML 파서(ElementTree/lxml strict) **금지**. 정규식 또는 `lxml(recover=True)` 로 추출.

---

## 2. 임베딩 (embedding)

### 2-1. 모델

| 항목 | 값 |
|---|---|
| 모델 | **bge-m3** (BAAI) |
| 차원 (size) | **1024d** |
| 거리 (distance) | **Cosine** (코사인 유사도) |
| 실행 환경 | Ollama (`OLLAMA_BASE` 환경변수로 엔드포인트 지정) |

> bge-m3 = 다국어(한국어 포함) 지원 + 1024차원 + 균형 잡힌 성능으로 한국어 RAG에 자주 쓰이는 오픈 임베딩 모델.
> Cosine = 두 벡터의 **방향**이 얼마나 비슷한지 측정. 의미검색의 표준 거리.

### 2-2. 임베딩 대상 = `embedding_text`

청크의 임베딩 대상은 MariaDB `chunk_index.embedding_text` 컬럼. 형식:

```
[회사명 · 문서(YYYY.MM) · section_path]\n
<청크 본문>
```

> 프리픽스가 들어가 있는 이 텍스트를 그대로 bge-m3 에 넣어 1024d 벡터를 얻는다.

### 2-3. 임베딩 파이프라인 흐름

```
chunk_index.embedding_text (MariaDB)
    │
    │  (Ollama bge-m3 호출, 1024d 벡터 생성)
    ▼
Qdrant point
    ├─ vector: 1024d float[]
    └─ payload: { chunk_id, corp_code, rcept_no, chunk_type, section_path, doc_date, corp_name }
```

> `doc_date` 는 `chunk_index` 에 없으므로 `document_index.date` 를 조인해 채운다.

---

## 3. 컬렉션 + 인덱스

### 3-1. 컬렉션 목록 (2개)

| 컬렉션 | 차원 | 거리 | 1 point 의미 | 용도 |
|---|---|---|---|---|
| `polaris-chunks` | 1024 | Cosine | 1 청크(공시 본문 청크) | **의미검색 진입점** → `chunk_id` 반환 |
| `polaris-org-er` | 1024 | Cosine | 1 회사명 | **회사명 Entity Resolution** (추출 회사명 → 정규 `corp_code` 매칭) |

> ER = Entity Resolution. "삼성전자" / "삼성전자(주)" / "Samsung Electronics" 처럼 다양한 표면형을 같은 `corp_code` 로 묶는 작업.

---

### 3-2. `polaris-chunks` 컬렉션

#### 컬렉션 스펙

| 항목 | 값 |
|---|---|
| 벡터 차원 (size) | 1024 |
| 거리 (distance) | Cosine |
| HNSW `m` | 16 |
| HNSW `ef_construct` | 100 |
| 1 point | 1 청크 |

> HNSW = Hierarchical Navigable Small World. Qdrant의 **근사 최근접 이웃(ANN) 인덱스** 알고리즘. `m`(연결 차수)과 `ef_construct`(빌드 시 탐색 폭)는 그래프 품질·메모리 트레이드오프 파라미터.

#### Payload 스키마 (메타 필드)

> Payload = 벡터와 함께 저장되는 메타데이터. 본문 텍스트는 넣지 않고 **교차키·필터 메타**만 보관.

| 필드 (영문) | 한글 의미 | 타입 | 인덱스 | 설명 |
|---|---|---|---|---|
| `chunk_id` | 청크ID | keyword | ○ | 교차키. Qdrant point ↔ MariaDB ↔ Neo4j 묶는 단일 식별자 |
| `corp_code` | 기업코드 | keyword | ○ | 회사 단위 필터용 |
| `rcept_no` | 접수번호 | keyword | ○ | 공시 단위 식별 |
| `chunk_type` | 청크 종류 | keyword | ○ | `text_micro` / `text_macro` / `table_nl` |
| `section_path` | 섹션 경로 | keyword | — | 공시 내 위치 |
| `doc_date` | 공시일 | datetime | ○ | 시계열·변화감지 필터용 |
| `corp_name` | 기업명 | text | — | 표시·전문검색용 |

> `○` 가 붙은 5개 필드만 **payload 인덱스**를 만든다. 나머지는 인덱스 없이 표시용/저장용.

#### 생성 코드 — Python (qdrant_client)

```python
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, HnswConfigDiff, PayloadSchemaType,
)

client = QdrantClient(host="localhost", port=6333)

# 1) 컬렉션 생성
client.create_collection(
    collection_name="polaris-chunks",
    vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
    hnsw_config=HnswConfigDiff(m=16, ef_construct=100),
)

# 2) 필터에 쓰는 필드만 payload 인덱스 생성 (Qdrant는 스키마리스)
for field in ("chunk_id", "corp_code", "rcept_no", "chunk_type"):
    client.create_payload_index(
        collection_name="polaris-chunks",
        field_name=field,
        field_schema=PayloadSchemaType.KEYWORD,
    )

client.create_payload_index(
    collection_name="polaris-chunks",
    field_name="doc_date",
    field_schema=PayloadSchemaType.DATETIME,
)
```

#### payload JSON 예시 1건

```json
{
  "chunk_id": "a1b2c3d4e5f60718",
  "corp_code": "00126380",
  "rcept_no": "20240514000001",
  "chunk_type": "text_micro",
  "section_path": "II. 사업의 내용 > 2. 주요 제품 및 서비스",
  "doc_date": "2024-05-14T00:00:00Z",
  "corp_name": "삼성전자"
}
```

---

### 3-3. `polaris-org-er` 컬렉션 (회사명 매칭용)

#### 컬렉션 스펙

| 항목 | 값 |
|---|---|
| 벡터 차원 (size) | 1024 |
| 거리 (distance) | Cosine |
| 1 point | 1 회사명 |

#### Payload 스키마

| 필드 (영문) | 한글 의미 | 타입 | 인덱스 | 설명 |
|---|---|---|---|---|
| `corp_code` | 기업코드 | keyword | ○ | 매칭 대상 회사 코드 (교차키) |
| `name` | 회사명 | text | — | 회사명 표면형 |
| `source` | 출처 | keyword | — | 회사명 출처 (DART / 뉴스 추출 등) |

#### 생성 코드 — Python

```python
client.create_collection(
    collection_name="polaris-org-er",
    vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
)

client.create_payload_index(
    collection_name="polaris-org-er",
    field_name="corp_code",
    field_schema=PayloadSchemaType.KEYWORD,
)
```

#### payload JSON 예시 1건

```json
{
  "corp_code": "00126380",
  "name": "삼성전자주식회사",
  "source": "DART"
}
```

---

## 4. 검색 사용법 (GraphRAG 1단계)

Qdrant는 GraphRAG 4단계 중 **1단계: 의미검색 진입점**.

```
사용자 질문
   ↓ ① bge-m3 임베딩 (1024d)
   ↓ ② polaris-chunks 에서 Cosine top_k 청크 검색
         (필요시 corp_code · doc_date 등 payload 필터)
   ↓ ③ chunk_id[] 반환
        → Neo4j (Chunk 노드 기점 그래프 탐색)
        → MariaDB (chunk_index 본문 전문 조회)
```

**예시 검색 코드**:
```python
from qdrant_client.models import Filter, FieldCondition, MatchValue

results = client.search(
    collection_name="polaris-chunks",
    query_vector=embed_query("삼성전자의 주요 공급망 협력사는?"),  # bge-m3 임베딩
    query_filter=Filter(
        must=[
            FieldCondition(key="corp_code", match=MatchValue(value="00126380")),
        ]
    ),
    limit=10,
)
chunk_ids = [r.payload["chunk_id"] for r in results]
# → Neo4j / MariaDB 후속 조회
```

`polaris-org-er` 은 추출 파이프라인에서 **회사명 → 정규 `corp_code`** 해소에만 쓴다(검색 결과 표면화용이 아님).

---

## 5. 핵심 원칙 (요약)

1. **payload 분리 원칙** — 본문 전체 텍스트는 Qdrant 에 넣지 않는다. 전문은 MariaDB `chunk_index` 에 있고, payload 는 교차키·필터 메타만.
2. **인덱스 최소화** — Qdrant 는 스키마리스. 실제로 필터에 쓰는 필드만 `create_payload_index`.
3. **교차키 일관성** — `chunk_id` 가 Qdrant point ↔ MariaDB `chunk_index` ↔ Neo4j `Chunk` 를 하나로 묶는다.
4. **doc_date = 시계열 필터** — 변화감지·시점별 비교용. 같은 회사를 분기별로 비교할 때 사용.
5. **contextual retrieval** — `embedding_text` 에 `[회사명 · 문서(YYYY.MM) · section_path]` 헤딩을 프리픽스로 붙여 임베딩 품질을 끌어올린다.
