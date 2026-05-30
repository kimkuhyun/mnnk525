# TODO — 재현성 강화 (Phase 3 검증 후 적용)

**작성**: 2026-05-26 — Phase 3 LLM 추출 진행 중에 점검 결과 정리
**적용 시점**: P-3.7 평가 게이트 PASS / verify 11/11 회귀 OK 확인 후

**[2026-05-26 적용 완료]** 4건 + linked 비율 출력 한 PR 로 적용. sanity (`graph-extract-semantic --limit 3`) 통과. manifest.json + jsonl meta(model/temp/prompt_hash) 확인. embed/llm digest 는 Ollama 0.24 `modelfile` FROM 라인 파싱으로 보강.

현재 LLM 추출 배치 (273 청크, qwen3.5:9b, temp 0.0) 는 이미 모델·온도·프롬프트가 코드에 hardcoded 라 git commit 으로 추적 가능 → 진행 중 배치는 그대로 두고, 다음 사이클부터 4개 항목 강화.

## 1. jsonl record meta 에 model + temp + prompt_hash 명시

**현재 (`graph/extractors/llm_entity.py` / `llm_relation.py` 응답 meta):**
```json
{"raw_count": 2, "validated_count": 2, "elapsed_ms": 9681}
```

**개선 — 호출 시점 메타 동봉:**
```json
{"raw_count": 2, "validated_count": 2, "elapsed_ms": 9681,
 "model": "qwen3.5:9b", "temperature": 0.0,
 "prompt_hash": "<sha1(system+user_template+schema)>",
 "pipeline_version": "polaris-0.3.0+p3.4"}
```

수정 위치:
- `src/polaris/graph/extractors/llm_entity.py::call_ollama` return meta
- `src/polaris/graph/extractors/llm_relation.py::call_ollama` return meta

## 2. prompt_hash 를 실제 prompt 텍스트의 SHA1 으로 계산

**현재 (`graph/loader_semantic.py:30`):**
```python
def _hash_prompt(prompt_marker: str) -> str:
    return hashlib.md5(prompt_marker.encode()).hexdigest()[:16]
# 호출: _hash_prompt("entity_v1+relation_v1")
```

→ marker string 이 같으면 prompt 텍스트가 바뀌어도 동일 hash. **변경 추적 X.**

**개선:**
```python
from polaris.graph.extractors.llm_entity import SYSTEM_PROMPT as ENT_SYS, ENTITY_SCHEMA, USER_TEMPLATE as ENT_USR
from polaris.graph.extractors.llm_relation import SYSTEM_PROMPT as REL_SYS, RELATION_SCHEMA, USER_TEMPLATE as REL_USR

def compute_prompt_hash() -> str:
    payload = "|".join([
        ENT_SYS, ENT_USR, json.dumps(ENTITY_SCHEMA, sort_keys=True),
        REL_SYS, REL_USR, json.dumps(RELATION_SCHEMA, sort_keys=True),
    ])
    return hashlib.sha1(payload.encode()).hexdigest()[:16]
```

수정 위치: `src/polaris/graph/loader_semantic.py`

## 3. lexicon yaml SHA1 기록 (graph_extracts manifest)

**문제:** alias yaml 변경 시 같은 LLM 결과라도 linking 결과 달라짐. 재현성 위해 추출 시점 yaml 스냅샷 필요.

**개선:** `data/4_dbGoldTest/graph_extracts/{run_id}/manifest.json` 신규 — 한 번 작성, 추출 시작 시 기록.
```json
{
  "started_at": "2026-05-26T10:00:00Z",
  "git_commit": "<HEAD short hash>",
  "model": "qwen3.5:9b",
  "pipeline_version": "polaris-0.3.0+p3.4",
  "lexicon_sha1": {
    "organizations": "abc123...",
    "persons": "def456...",
    "products": "789...",
    "technologies": "...",
    "places": "..."
  },
  "embedding_model": "bge-m3:latest",
  "ollama_base": "http://localhost:11434"
}
```

수정 위치: `src/polaris/graph/pipeline.py::run_pipeline` 시작 부분에 manifest 저장.

## 4. bge-m3 임베딩 모델 ID 추적

**현재:** `OLLAMA_EMBED_MODEL=bge-m3:latest` — Ollama `latest` 태그는 시간 지나면 갱신 가능. 동일 텍스트 → 다른 vector 위험.

**개선:**
- `.env.example` 에 `OLLAMA_EMBED_MODEL=bge-m3:567f` 같이 **digest** 고정 권장 가이드 추가
- `src/polaris/embed/bge_m3.py` 가 모델 digest 를 Ollama `/api/show` 로 조회해 manifest 에 기록

수정 위치:
- `src/polaris/embed/bge_m3.py` — digest 조회 함수
- `pipeline.py` manifest 에 `embedding_model_digest` 추가

---

## 적용 순서 (검증 완료 후)

1. Phase 3 P-3.7 평가 게이트 PASS 확인
2. verify 11/11 회귀 확인
3. (옵션) commit 으로 현 상태 보존
4. 본 TODO 4건 단일 PR 로 적용:
   - 1, 2 동시 (jsonl meta + prompt_hash)
   - 3 별도 (manifest 신설)
   - 4 별도 (embed digest)
5. 적용 후 sanity — 3 청크 재실행 → manifest/prompt_hash 확인 → 본격 다음 사이클
