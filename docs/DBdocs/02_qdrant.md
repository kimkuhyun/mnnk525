# POLARIS DB 설계서 — 02. Qdrant (벡터 DB)

Qdrant = 공시 청크 임베딩 기반 의미검색 진입점. 임베딩 모델 bge-m3, 벡터 차원 1024d, 거리 Cosine.

> 벡터 DB는 관계형 ERD가 없다. 문서화의 정석은 다이어그램이 아니라 **컬렉션 스펙 표 + payload 스키마 표**다. 본 문서는 이 관례를 따른다.

---

## 1. 컬렉션 목록

| 컬렉션 | 차원 | 거리 | 임베딩 모델 | 1 point 의미 | 용도 |
|---|---|---|---|---|---|
| `polaris-chunks` | 1024 | Cosine | bge-m3 (Ollama) | 1 청크(공시 본문 청크) | 의미검색 진입점 → `chunk_id` 반환 → Neo4j/MariaDB 연결 |
| `polaris-org-er` | 1024 | Cosine | bge-m3 (Ollama) | 1 회사명 | 회사명 Entity Resolution(추출 회사명 → 기존 `corp_code` 매칭) |

---

## 2. 컬렉션 상세

### 2.1 `polaris-chunks`

공시 본문을 청크 단위로 임베딩하여 의미검색의 1단계 진입점을 제공한다. 검색 결과로 `chunk_id` 를 반환하고, 이후 Neo4j(`Chunk` 노드) · MariaDB(`chunk_index`)로 연결한다.

#### 컬렉션 스펙 표

| 항목 | 값 |
|---|---|
| 벡터 차원(size) | 1024 |
| 거리(distance) | Cosine |
| 임베딩 모델 | bge-m3 (Ollama) |
| HNSW m | 16 |
| HNSW ef_construct | 100 |
| 1 point | 1 청크(공시 본문 청크) |

#### payload 스키마 표

| 필드 | 타입 | 인덱스 | 설명 |
|---|---|---|---|
| `chunk_id` | keyword | ○ | 교차키. Qdrant point ↔ MariaDB `chunk_index` ↔ Neo4j `Chunk` 를 묶는 단일 식별자 |
| `corp_code` | keyword | ○ | 회사 코드. 회사 단위 필터 |
| `rcept_no` | keyword | ○ | 공시 접수번호. 문서 단위 식별 |
| `chunk_type` | keyword | ○ | `text_micro` \| `text_macro` \| `table_nl` |
| `section_path` | keyword | - | 공시 내 섹션 경로(목차 위치) |
| `doc_date` | datetime | ○ | 공시 일자. 시계열/변화감지 필터용 |
| `corp_name` | text | - | 회사명(표시·전문검색용) |

> 본문 전체 텍스트는 payload에 넣지 않는다. 전문은 MariaDB `chunk_index` 에 있고, Qdrant는 교차키·필터 메타만 보관한다.

#### 생성 예시 — JSON config

```json
{
  "collection_name": "polaris-chunks",
  "vectors": {
    "size": 1024,
    "distance": "Cosine"
  },
  "hnsw_config": {
    "m": 16,
    "ef_construct": 100
  }
}
```

#### 생성 예시 — Python (qdrant_client)

```python
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, HnswConfigDiff, PayloadSchemaType,
)

client = QdrantClient(host="localhost", port=6333)

client.create_collection(
    collection_name="polaris-chunks",
    vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
    hnsw_config=HnswConfigDiff(m=16, ef_construct=100),
)

# 필터에 쓰는 필드만 payload 인덱스 생성 (Qdrant는 스키마리스)
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
  "chunk_id": "00126380:20240514000001:c0042",
  "corp_code": "00126380",
  "rcept_no": "20240514000001",
  "chunk_type": "text_micro",
  "section_path": "II. 사업의 내용 > 2. 주요 제품 및 서비스",
  "doc_date": "2024-05-14T00:00:00Z",
  "corp_name": "삼성전자"
}
```

---

### 2.2 `polaris-org-er`

추출된 회사명을 임베딩하여 기존 `corp_code` 와 매칭하는 Entity Resolution 전용 컬렉션이다. 공시 본문에서 등장한 회사명을 정규 코드로 연결한다.

#### 컬렉션 스펙 표

| 항목 | 값 |
|---|---|
| 벡터 차원(size) | 1024 |
| 거리(distance) | Cosine |
| 임베딩 모델 | bge-m3 (Ollama) |
| 1 point | 1 회사명 |
| 용도 | 회사명 Entity Resolution |

#### payload 스키마 표

| 필드 | 타입 | 인덱스 | 설명 |
|---|---|---|---|
| `corp_code` | keyword | ○ | 매칭 대상 회사 코드(교차키) |
| `name` | text | - | 회사명 표면형 |
| `source` | keyword | - | 회사명 출처(DART, 본문 추출 등) |

#### 생성 예시 — JSON config

```json
{
  "collection_name": "polaris-org-er",
  "vectors": {
    "size": 1024,
    "distance": "Cosine"
  }
}
```

#### 생성 예시 — Python (qdrant_client)

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PayloadSchemaType

client = QdrantClient(host="localhost", port=6333)

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

## 3. 핵심 원칙

1. **payload 분리 원칙**: 본문 전체 텍스트는 Qdrant에 넣지 않는다. 전문은 MariaDB `chunk_index` 에 있고, payload는 교차키·필터 메타만 담는다.
2. **인덱스 최소화**: Qdrant는 스키마리스다. payload 인덱스는 실제로 필터에 쓰는 필드만 `create_payload_index` 로 생성한다.
3. **교차키 일관성**: `chunk_id` 가 Qdrant point ↔ MariaDB `chunk_index` ↔ Neo4j `Chunk` 를 하나로 묶는다.
4. **doc_date = 시계열 필터**: 변화감지/시계열 비교용. 같은 회사를 시점별 청크로 비교할 때 사용한다.

---

## 4. GraphRAG에서 Qdrant의 자리

Qdrant는 GraphRAG 검색 파이프라인의 **1단계(의미검색 진입점)** 다.

1. 질문 임베딩: 사용자 질문을 bge-m3 로 1024d 벡터화한다.
2. 유사 청크 검색: `polaris-chunks` 에서 Cosine 유사도 top_k 청크를 조회한다(필요 시 `corp_code`·`doc_date` 등 payload 필터 적용).
3. `chunk_id` 반환: 검색 결과의 `chunk_id` 를 키로 Neo4j(`Chunk` 노드·관계 그래프) 및 MariaDB(`chunk_index` 본문 전문)로 연결해 후속 그래프 탐색·근거 확보를 수행한다.

`polaris-org-er` 은 추출 파이프라인에서 회사명을 정규 `corp_code` 로 해소하는 보조 경로로 동작한다.
