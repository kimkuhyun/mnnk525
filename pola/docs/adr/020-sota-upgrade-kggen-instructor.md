# ADR 020 — SOTA 업그레이드: Instructor + KGGen + Reflection 통합

**날짜**: 2026-05-28
**상태**: Proposed
**우선순위**: P0 (이전 ADR 010~017 의 상위 framework)

## 결정

POLARIS 의 LLM 추출 + 그래프 적재 파이프라인을 단계적으로 SOTA 표준에 맞춰 업그레이드한다. **현재 코드 (linker, merger, schema) 는 유지** 하고, 누락된 단계 (schema-strict validation, reflection iteration, knowledge fusion) 를 검증된 오픈소스로 보강한다.

## 배경 — 12단계 SOTA 와 POLARIS 의 현재 위치

학계·산업 표준 (NeurIPS 2025 KGGen, FinReflectKG, Microsoft GraphRAG, LECITE) 의 12단계 와 POLARIS 의 갭:

| # | 표준 단계 | POLARIS | 책임 라이브러리 |
|---|---|---:|---|
| 1 | Schema-guided 추출 | 60% | **Instructor + Pydantic** |
| 2 | Document parsing | 50% | (현재 충분, 향후 Docling) |
| 3 | Hybrid NER | 0% | (Phase C) spaCy / KoBERT-NER |
| 4 | Multi-pass (추출/정규화 분리) | 0% | Instructor 후속 호출 |
| 5 | **Reflection iteration** | **0%** | **KGGen.cluster() / 자체 loop** |
| 6 | Multi-LLM ensemble | 0% | (보류 — 비용 5×) |
| 7 | Disambiguation | 30% | 자체 (linker Stage 3 활성화) |
| 8 | **Knowledge fusion** | **30%** | **KGGen.aggregate() / cluster()** |
| 9 | PROV-O | 50% | 자체 (스키마 OK, 적재 fix ADR 011) |
| 10 | Multi-signal confidence | 0% | 자체 (ADR 014 계획) |
| 11 | Golden set + auto-eval | 30% | **Ragas / DeepEval** |
| 12 | Active learning | 0% | (장기 — Argilla) |

→ POLARIS 평균 **28%**. SOTA = 85%+.

## 단계적 통합 계획 — Phase A → D

### Phase A. KGGen plugin (1주)
**목표**: reflection iteration + knowledge fusion 만 도입. 현재 코드 100% 유지.

**의존성**
```bash
pip install kg-gen
```

**변경 파일**
- 신설 `src/polaris/graph/kggen_adapter.py` — POLARIS llm_extracts.jsonl ↔ KGGen Graph 변환
- 신설 `scripts/run_kggen_fusion.py` — 추출 후 cluster() 호출 + 결과 jsonl

**코드 패턴**
```python
from kg_gen import KGGen
kg = KGGen(model="ollama/qwen3.5:9b", api_base="http://localhost:11434")
# 1) POLARIS llm_extracts.jsonl → KGGen Graph
g = kg.aggregate(polaris_graphs)  # 청크별 결과 통합
# 2) iterative clustering (canonical name 정규화)
g_clustered = kg.cluster(g, context="한국 반도체 5사 — 회사·임원·제품·기술")
# 3) clustered graph → Neo4j MERGE (POLARIS merger 재사용)
```

**기대 효과**
- Org 중복 ×3 자동 병합 (corp_code 4갈래 → canonical)
- Entity 변형(㈜/주식회사/(주)) 자동 정규화
- ADR 012 (corp_code canonicalization) 의 *상당 부분 자동 해결*

**검증**
```cypher
MATCH (o:Organization)
WITH o.name AS nm, count(DISTINCT o.corp_code) AS n
WHERE n > 1 RETURN count(*) AS dup_groups
-- 목표: 현재 330 → 0
```

---

### Phase B. Instructor + Reflection loop (1~2주)
**목표**: LLM 호출 안정성 (94%+ JSON valid) + reflection 3-round 적용.

**의존성**
```bash
pip install instructor
```

**변경 파일**
- `src/polaris/graph/extractors/llm_entity.py` — `instructor.from_ollama()` 로 wrap
- `src/polaris/graph/pipeline.py` — chunk 별 multi-round loop (1차 추출 → 누락 prompt → 재추출 × 최대 3)
- ExtractionActivity 노드 schema 에 `rounds` 필드 추가

**코드 패턴**
```python
import instructor
from pydantic import BaseModel
from typing import Literal

class Entity(BaseModel):
    text: str
    type: Literal["Organization", "Person", "Product", "Technology", "Place", "Event"]
    category: str | None
    self_confidence: float
    evidence_span: str

class Triple(BaseModel):
    subject: str
    predicate: str
    object: str
    self_confidence: float

class ChunkExtraction(BaseModel):
    entities: list[Entity]
    relations: list[Triple]

client = instructor.from_ollama(
    client=ollama.Client(host="http://localhost:11434"),
    mode=instructor.Mode.JSON,
)

# Pass 1
result = client.chat.completions.create(
    model="qwen3.5:9b",
    response_model=ChunkExtraction,
    max_retries=3,
    messages=[...],
)

# Reflection: 누락 검토
critique = client.chat.completions.create(
    response_model=MissingItems,
    messages=[..., "위 추출에서 빠진 entity/relation 이 있나?"],
)
if critique.missing:
    result_v2 = client.chat.completions.create(
        response_model=ChunkExtraction,
        messages=[..., f"빠진 것 보충: {critique.missing}"],
    )
```

**기대 효과**
- mojibake 문제 해결 (Pydantic UTF-8 검증)
- 첫 추출 recall +20~30%
- ADR 013 (entity precision guard) 의 일반명사 차단을 Pydantic enum 으로 일원화

---

### Phase C. Hybrid NER (1~2주, 선택)
**목표**: 결정론 NER (한국어 회사·인명) 1차 + LLM 보강.

**의존성**
```bash
pip install spacy
python -m spacy download ko_core_news_lg
# OR
pip install transformers  # KoBERT-NER 또는 KLUE-NER
```

**변경 파일**
- 신설 `src/polaris/graph/extractors/ner_hybrid.py`
- pipeline.py 의 LLM 호출 직전 ner_hybrid.scan(text) 결과 entity union

**기대 효과**
- Person LLM 비율 0.15% → 5%+ (ADR 015 의 vector ER augmentation 보완)
- Org / Person recall ↑

---

### Phase D. 자동 평가 (1주)
**목표**: Golden set 200 정답 + Ragas/DeepEval CI 통합.

**의존성**
```bash
pip install ragas deepeval
```

**변경 파일**
- 신설 `tests/golden_set.jsonl` — 200 정답 triple (수동 작성)
- 신설 `tests/eval_graph_quality.py` — precision/recall/F1 자동 측정
- `polaris graph-eval` 명령에 통합

---

## 기존 ADR 들과의 관계

| 기존 ADR | Phase A 후 | Phase B 후 |
|---|---|---|
| ADR 010 (Chunk 엣지) | linker fix 유지, Phase B 의 reflection 으로 recall ↑ | ✓ |
| ADR 011 (Event PROV) | merger fix 유지 | ✓ |
| ADR 012 (corp_code) | **KGGen.cluster() 가 자동 해결** | ✓ |
| ADR 013 (Entity FP) | Pydantic Literal enum 으로 자동 차단 | ✓ |
| ADR 014 (Confidence) | Phase D 와 통합 (Ragas signal) | ✓ |
| ADR 015 (Vector ER aug) | Phase C 의 hybrid NER 로 대체 가능 | ✓ |
| ADR 016 (Chunk store) | 별도 진행 | (영향 없음) |
| ADR 017 (Cleanup) | 별도 진행 | (영향 없음) |

→ **Phase A + B 만 끝나면 ADR 012 / 013 / 015 는 사실상 해결**.

## 롤백

각 Phase 는 *추가만* (기존 코드 보존). 문제 시 import 만 빼면 원복.

- Phase A: `kg-gen` import 제거 → POLARIS 그대로 동작
- Phase B: `instructor` 없으면 기존 `llm_entity.py` 그대로
- Phase C: hybrid NER skip
- Phase D: eval CI 끔

## 참고 (조사 출처)

- KGGen (NeurIPS 2025): https://arxiv.org/html/2502.09956v1
- Instructor: https://python.useinstructor.com/integrations/ollama/
- FinReflectKG (재무 도메인 SOTA): https://arxiv.org/abs/2508.17906
- DSPy Refine: https://dspy.ai/cheatsheet/
- Microsoft GraphRAG: https://www.microsoft.com/en-us/research/project/graphrag/
- LLM-empowered KG survey: https://arxiv.org/html/2510.20345v1
