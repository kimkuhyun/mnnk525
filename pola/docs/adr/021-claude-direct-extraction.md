# ADR 021 — Claude 가 직접 추출 (manual LLM, 데모 30 chunk)

**날짜**: 2026-05-28
**상태**: Proposed → Accepted (사용자 결정)
**우선순위**: P0 (모달 데모 정상화의 즉시 해결책)

## 결정

로컬 모델 (qwen3.5:9b, qwen2.5:7b) 이 KGGen/DSPy 와 호환·한국어 처리에서 신뢰성 부족으로 입증됨. 따라서 *데모 시나리오 (cbci-549902 한미반도체 HBM)* 에 한정해 **Claude 가 추출 LLM 역할을 한 번성 수행**. POLARIS 의 나머지 파이프라인 (linker, merger, loader_semantic, KGGen.aggregate) 은 **그대로 재사용**.

## 배경 — 로컬 모델 한계 확인

| 시도 | 결과 |
|---|---|
| `ollama/qwen3.5:9b` + KGGen.generate (한국어) | `AdapterParseError: empty response` |
| `ollama/qwen3.5:9b` + KGGen.generate (영어) | `AdapterParseError: empty response` |
| `ollama/qwen2.5:7b` + KGGen.generate (한국어) | 작동하나 relation 출력이 *중국어로 번역* (`供应产品`, `签订合同`) |
| `ollama/qwen2.5:7b` + KGGen.cluster (entity 121) | 88s 호출, entity_clusters 121 — *각자 자기 자신 1멤버*, 병합 0건 (Pydantic literal_error 다수) |
| POLARIS 본체 `graph-extract-semantic` (qwen3.5:9b) | 10,008 chunk 중 66 처리, entity quality 낮음, Chunk evidence 0.26% |

→ 로컬 옵션 (Ollama qwen 계열) 으로 *한국어 + 도메인 (반도체 IR)* 동시 처리가 production-grade 미달.

## Claude 가 책임지는 단계 (12 단계 중)

```
표준 12단계                             담당
─────────────                          ────
 1. Document parsing                    POLARIS pipeline (어제 완료)
 2. Hybrid NER                          ─┐
 3. Schema-guided LLM extraction        ─┤
 4. Multi-pass (extract/normalize)      ─┼─ Claude (한 번 호출에 통합)
 5. Reflection iteration                ─┤
 6. Multi-LLM ensemble (skip)           ─┘
 7. Entity linking                      ─┐ POLARIS linker.py
 8. Disambiguation                      ─┤   (Claude 가 canonical 미리 결정 →
 9. Knowledge fusion                    ─┘   linker 가 alias yaml 갱신)
10. PROV-O 부착                          POLARIS merger.py (CQ_*_PROV)
11. Confidence rescoring                 (Claude self_confidence + Phase B 의 multi-signal 계획)
12. Graph DB MERGE                       POLARIS loader_semantic
```

→ **Claude 는 #2~#5 만 수행, 나머지 POLARIS + KGGen 라이브러리.**

## Scope

이번 ADR 의 산출물은 **cbci-549902 데모 (한미반도체 HBM 96억) 시나리오** 만을 위한 것:
- 대상 chunk 30개 (`text_micro`, 한미반도체·SK하이닉스·삼성전자 분기보고서 사업의 개요·HBM·TC BONDER·자율공시·자사주 신탁)
- 그래프 결과는 *모달 BRIEF 모달* 검증용
- *5사 전체 코퍼스 적용 X* (그건 Phase B/C 가 정상화된 다음)

## 추출 형식 (POLARIS llm_extracts.jsonl 호환)

Claude 가 작성하는 JSON (chunk 당 1줄):
```json
{
  "chunk_id": "89e88bb30239c776",
  "run_id": "20260528_0808_01",
  "chunk_type": "text_micro",
  "entities": [
    {
      "text": "한미반도체",
      "type": "Organization",
      "canonical": "한미반도체",
      "self_confidence": 0.98,
      "evidence_span": "한미반도체는 1980년 설립후..."
    }
  ],
  "relations": [
    {
      "subject": "한미반도체",
      "predicate": "PRODUCES",
      "object": "HBM TC BONDER",
      "self_confidence": 0.95,
      "evidence_span": "주력 장비 'HBM TC 본더'는..."
    }
  ],
  "events": [
    {
      "label": "HBM 12·16단 적층 공급",
      "event_type": "supply",
      "actors": ["한미반도체"],
      "objects": ["HBM TC BONDER"],
      "evidence_span": "..."
    }
  ]
}
```

별도 파일 `canonical_clusters.json`:
```json
{
  "삼성전자": ["삼성전자", "삼성전자(주)", "삼성전자㈜", "Samsung Electronics"],
  "한미반도체": ["한미반도체", "Hanmi Semiconductor", "한미반도체㈜"],
  "SK하이닉스": ["SK하이닉스", "SK Hynix", "에스케이하이닉스"]
}
```

## 저장 위치

```
data/4_dbGoldTest/graph_extracts/claude-direct-20260528/
  ├─ llm_extracts.jsonl           — Claude 추출 결과 (30 chunk)
  ├─ canonical_clusters.json      — entity 정규화 그룹
  ├─ input_chunks.json            — 입력 chunk 본문 (재현용)
  └─ manifest.json                — 추출 시간, chunk 수, scope
```

## Neo4j 대상 — partial wipe

기존 LLM 추출 결과만 삭제, 정형 그래프 (DART 결정론) 는 유지:

| 노드/엣지 | 처리 |
|---|---|
| Chunk (10,008) | 유지 |
| FilingDocument | 유지 |
| Organization (847, 정형) | 유지 |
| Person (281, 정형 임원) | 유지 |
| FinMetric (3,957) | 유지 |
| BusinessGroup / StatTable / MacroIndicator | 유지 |
| Statement (190) | **삭제** (qwen 추출 잡음) |
| Event (123) | **삭제** |
| `:Chunk-[:hasActor]->()` (70 + 466) | **삭제** |
| `:Chunk-[:hasObject]->()` (282) | **삭제** |
| ExtractionActivity (1) | **삭제** |

`:LLMExtracted` 라벨 가진 entity 노드 중 *추출 전용* 인 것도 삭제 검토 (단, 추출 후 다시 적재됨).

## 검증

```cypher
-- target: 30 chunk 모두 evidence 보유 (현재 26 → 30 또는 그 이상)
MATCH (c:Chunk)-[:hasActor|hasObject]-()
WHERE c.chunk_id IN $sample_30_ids
RETURN count(DISTINCT c)

-- target: Statement 새로 적재 (현재 190 → 100+ new, 모두 PROV 있음)
MATCH (s:Statement)-[:wasDerivedFrom]->(:Chunk)
RETURN count(s)

-- target: Org dedup — 같은 canonical 의 surface 들이 같은 corp_code 로
MATCH (o:Organization {corp_code: '00161383'})  -- 한미반도체
RETURN o.name, o.aliases
```

## Trade-off

| Pro | Con |
|---|---|
| 한국어·도메인 정확 (mojibake 없음) | 30 chunk 한정 — 전체 코퍼스 X |
| 의미 있는 entity·relation (Brazil/Connecticut 같은 노이즈 X) | 재현 불가 (Claude 호출 1회성 산출물) |
| canonical cluster 정확 (사람 판단) | 다른 시나리오 (예: 동진쎄미켐 뉴스) 는 별도 추출 필요 |
| 모달 BRIEF 가 진짜 분석 보고서로 | Phase B (Instructor + reflection) 정상화 전까지의 *임시 처방* |

## 다음 단계 (이 ADR 이후)

1. Phase B 가 정상화되면 (B1~B4) → 같은 chunk 들에 *재추출* 후 Claude 결과와 비교 → Phase B 의 quality 측정
2. 이번 추출 결과 = **Golden set 의 seed** — D1 (Golden set 작성) 의 출발점

## 롤백

- `claude-direct-20260528` 폴더 통째로 삭제하면 원복
- Neo4j 의 새 Statement/Event/엣지는 `from_claude_direct=true` 마킹 → 일괄 회수 가능
- 추출 전 partial wipe 직전 노드 카운트 snapshot 저장

## 참고

- ADR 020 (Phase A/B/C/D 통합 계획) — 본 ADR 은 그 *Phase A 의 임시 우회*
- ADR 010 (linker fix), 011 (PROV) — 그대로 활용
- 본 ADR 의 추출 형식은 POLARIS pipeline.py 의 llm_extracts.jsonl 호환
