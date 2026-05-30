# Claude Direct Extraction Playbook (v2)

> **다른 Claude 세션 / 다른 회사 추출 시 이 문서 하나로 self-service.**
> 참고 ADR: [`021-claude-direct-extraction.md`](adr/021-claude-direct-extraction.md)
> 통합 적재 스크립트: `scripts/load_company_claude_direct.py`

## 0. 빠른 시작 (5 단계)

```
[전제] 디스크에 chunk + embedding 있어야 함:
  data/2_Chuck/03_chunks/{corp_code}/
  data/2_Chuck/04_embeddings/{corp_code}/
  data/rawData/{corp_code}/dart/

[1] .env POLARIS_CORPS 에 corp_code 추가
[2] Chunk 적재 (Qdrant + MariaDB + Neo4j Chunk):
    python scripts/load_company_claude_direct.py --corp <code> --run-id <id> --stage chunk
[3] 정형 그래프 + P0 backfill:
    python scripts/load_company_claude_direct.py --corp <code> --run-id <id> --stage structural --name <회사명>
[4] Claude 가 직접 chunk 읽고 llm_extracts.jsonl 작성
    (디렉터리: data/4_dbGoldTest/graph_extracts/claude-direct-{corp}-YYYYMMDD/)
[5] Claude 추출 적재 + Event PROV + Org dup cleanup:
    python scripts/load_company_claude_direct.py --corp <code> --run-id <id> --stage load-claude --name <회사명>
```

---

## 1. POLARIS 그래프 schema

### Entity Type (5종)
| 타입 | 식별자 | 예시 |
|---|---|---|
| `Organization` | corp_code (8 digit 또는 X{yaml} 또는 XCLAUDE_<sha10>) | 삼성전자, Harman, Sound United |
| `Person` | person_id (yaml 또는 PCLAUDE_<sha10>) | 한종희, 김용관, 허은녕 |
| `Product` | product_id | Galaxy S25, HBM4, 디지털 콕핏, HBM TC BONDER |
| `Technology` | tech_id | AI, ADAS, SDV, ISO 14001, 2.5D 패키징 |
| `Place` | iso_code | 수원사업장, 경기도 이천시, Brazil, Vietnam |

### Predicate (9종)
| Predicate | 의미 | 방향 |
|---|---|---|
| `EXECUTIVE_OF` | 임원 ↔ 회사 | Person → Org |
| `IS_MAJOR_SHAREHOLDER_OF` | 대주주 | Org/Person → Org |
| `INVESTS_IN` | 투자 | Org → Org |
| `IS_SUBSIDIARY_OF` | 자회사 | Org → Org (모회사) |
| `AFFILIATED_WITH` | 계열·제휴·파트너십 | Org → Org/Group |
| `SUPPLIES_TO` | 공급 | Supplier → Buyer |
| `COMPETES_WITH` | 경쟁 | Org → Org |
| `PRODUCES` | 생산·제공 | Org → Product/Tech |
| `USES_TECH` | 기술 활용 | Org → Technology |

### Tier 자동 분류 (POLARIS reifier.py)
- **Tier 2 Statement**: 대부분 (subject-predicate-object + confidence + chunk evidence)
- **Tier 3 Event**: `events` 배열에 직접 작성 (acquisition, product_launch, partnership, litigation, share_transaction 등)

---

## 2. STEP 1 — Chunk 적재 (디스크 → 3DB)

### 전제 확인
```
data/2_Chuck/03_chunks/{corp_code}/
  ├── text.jsonl       (본문 chunk)
  └── table_nl.jsonl   (재무표 자연어화)

data/2_Chuck/04_embeddings/{corp_code}/
  ├── text.npy + text.ids.json
  └── table_nl.npy + table_nl.ids.json

data/rawData/{corp_code}/dart/   (정형 추출용 raw json)
```

### .env 업데이트
```
POLARIS_CORPS=00126380,00161383,00164779,...   # 적재할 회사 추가
POLARIS_CORP_NAMES=삼성전자,한미반도체,SK하이닉스,...
```

### 적재 명령
```bash
python scripts/load_company_claude_direct.py \
  --corp 00161383 \
  --run-id 20260528_0808_01 \
  --stage chunk
```

→ MariaDB chunk_index INSERT + Qdrant green upsert + Neo4j Chunk MERGE.
→ 회사당 5-10분.

### 트랩
- POLARIS CLI `polaris load --db all` 명령은 **새 standby_run_id 발급** → 사용 X. 통합 스크립트로 가야 기존 run_id 유지.

---

## 3. STEP 2 — 정형 그래프 + P0 backfill

### 명령
```bash
python scripts/load_company_claude_direct.py \
  --corp 00161383 \
  --run-id 20260528_0808_01 \
  --stage structural \
  --name 한미반도체
```

### 내부 흐름 (자동)
1. `polaris load-finmetric` — DART JSON → Org-[:HAS_METRIC]->FinMetric
2. `polaris graph-extract --only persons,shareholders,invests,ftc_groups,events` — 결정론 그래프
3. **P0 backfill** (Cypher 직접):
   - FilingDocument stub 생성 (rcept_no 누락 보강)
   - FilingDocument-[:has_chunk]->Chunk
   - Organization-[:reports]->FilingDocument
   - Chunk(table_nl)-[:hasActor {role:'document_subject'}]->Organization

### 효과
- FinMetric, EXECUTIVE_OF, INVESTS_IN, AFFILIATED_WITH 모두 자동
- Chunk evidence coverage 99%+ (모든 chunk 가 graph 에 연결)
- 회사당 5-15분

### 트랩
- `POLARIS_TARGET_RUN_ID` env var 가 무시되는 일부 명령 있음 → 통합 스크립트는 내부에서 강제 set
- 다른 회사 같이 적재 시 graph-extract 가 모든 corp 처리 (POLARIS_CORPS 기준)

---

## 4. STEP 3 — Claude 가 chunk 읽고 추출

### 디렉터리 구조
```
data/4_dbGoldTest/graph_extracts/claude-direct-{corp_code}-YYYYMMDD/
  ├── claude_input.json     (자동 생성됨, 본문 chunk bundle)
  ├── llm_extracts.jsonl    ← Claude 가 작성
  ├── canonical_clusters.json  (loader 자동 생성)
  └── manifest.json         ← Claude 가 작성
```

### 4.1. claude_input.json 자동 생성 (본문 chunks bundle)

```python
# scripts/_build_claude_input.py (또는 통합 스크립트 일부로 추가)
import sys, json
from pathlib import Path
sys.path.insert(0, 'src')
from polaris.config import neo4j_driver

CORP = "00161383"   # ← 회사
RUN_ID = "20260528_0808_01"
OUT_DIR = Path(f"data/4_dbGoldTest/graph_extracts/claude-direct-{CORP}-20260528")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 본문 chunk_id list
drv = neo4j_driver()
chunks_meta = []
with drv.session() as s:
    for r in s.run("""
        MATCH (c:Chunk) WHERE c.corp_code=$code
          AND c.chunk_type IN ['text_micro','text_macro'] AND c.run_id=$rid
        RETURN c.chunk_id AS cid, c.chunk_type AS ct,
               c.corp_code AS code, c.rcept_no AS rcept
    """, code=CORP, rid=RUN_ID):
        chunks_meta.append(dict(r))
drv.close()

# chunk text 는 디스크 03_chunks 에서
text_map = {}
for fname in ['text.jsonl', 'table_nl.jsonl']:
    p = Path(f'data/2_Chuck/03_chunks/{CORP}/{fname}')
    if p.is_file():
        with p.open(encoding='utf-8') as f:
            for line in f:
                r = json.loads(line)
                text_map[r['chunk_id']] = r.get('llm_context_text') or r.get('embedding_text', '')

out_chunks = []
for c in chunks_meta:
    text = text_map.get(c['cid'], '')
    if text:
        out_chunks.append({'chunk_id': c['cid'], 'chunk_type': c['ct'],
                           'corp_code': c['code'], 'rcept_no': c['rcept'], 'text': text})

bundle = {
    '_meta': {'scope': f'{CORP} 본문', 'run_id': RUN_ID,
              'chunk_count': len(out_chunks),
              'total_chars': sum(len(c['text']) for c in out_chunks),
              'extraction_method': 'claude-direct (ADR 021)'},
    'chunks': out_chunks,
}
(OUT_DIR / 'claude_input.json').write_text(
    json.dumps(bundle, ensure_ascii=False, indent=2), encoding='utf-8')
```

### 4.2. Claude 가 chunk 읽고 추출하는 규칙

#### Boilerplate skip (entity 없음 — 빈 chunk 로 둠)
```
- 중요한 회계추정 및 가정 > 수익인식 / 환불부채 / 영업권 손상 / 순확정급여부채 / 법인세
- 기업공시서식 작성기준에 따라 분ㆍ반기보고서에 기재하지 않습니다  (= 미기재)
- 의결권의 위임 / 위임장 / 전자위임장
- 금융상품의 공정가치
- 재무제표 > 4-1. 재무상태표 ...
```

#### Implicit entity 보강 (의미 있는 chunk 만)
```
- 환경규제 chunk → 회사 + ISO 14001 + ISO 45001 (Technology)
- 자기주식 보유/처분 → 회사 + Event
- 자산 손상 / 자금 조달 → 회사 + 금액 evidence_span
- R&D 비용 → 회사 + 정형 reference
```

#### ⚠️ ANTI-PATTERN: fill_remaining (default_only) 금지

```python
# ❌ 나쁜 패턴 (SK 사례에서 발견)
def fill_remaining(all_chunk_ids):
    """추출 안 한 chunk 들에 자동으로 Org entity 부착."""
    for cid in remaining:
        chunk_extracts[cid] = {"entities": [org("SK하이닉스")],
                               "relations": [], "events": []}
```

**문제**: coverage 가 inflated (97.7%) 되지만 실제 명시 추출은 11.6%. Loader 가 이런 패턴을 **자동 skip** 함 (해당 chunk 는 적재 안 됨).

**올바른 패턴**: chunk text 자세히 읽고 entity 명시. 정말 boilerplate 면 `entities=[]` 로 둠.

#### canonical 지정 원칙
```
"삼성전자", "삼성전자㈜" → canonical: "삼성전자"
"SDC", "삼성디스플레이" → canonical: "삼성디스플레이"
"Galaxy S25 시리즈", "Galaxy S25" → canonical: "Galaxy S25"
"NAND Flash" → canonical: "NAND"
```

기존 yaml lexicon (`src/polaris/graph/lexicon/`) 의 canonical 사용. 매칭 시 linker 가 자동 dedup.

#### self_confidence 가이드라인
| 상황 | conf |
|---|---|
| 회사명 정확 명시 | 0.95-0.98 |
| 명시 + 관계 명확 | 0.92-0.95 |
| 명시 + 관계 약간 추론 | 0.85-0.92 |
| Implicit (boilerplate 회사명) | 0.85-0.90 |

#### evidence_span
- 50-200자
- 본문 발췌 그대로 (요약 X)
- 추론 정보는 evidence_span 비움

### 4.3. llm_extracts.jsonl 형식 (1 chunk = 1 line)

```json
{
  "chunk_id": "07c5f8b780e61b05",
  "run_id": "20260528_0808_01",
  "chunk_type": "text_micro",
  "entities": [
    {"text":"삼성전자","type":"Organization","canonical":"삼성전자",
     "self_confidence":0.95,"evidence_span":"당사는 Harman의 선두 위상을 강화하기 위해"},
    {"text":"Galaxy S25 시리즈","type":"Product","canonical":"Galaxy S25",
     "self_confidence":0.97,"evidence_span":"Galaxy S25 시리즈, Galaxy Z 폴드7와 ..."}
  ],
  "relations": [
    {"subject":"Harman","predicate":"AFFILIATED_WITH","object":"Sound United",
     "self_confidence":0.95,"evidence_span":"Sound United를 2025년 3분기에 인수"}
  ],
  "events": [
    {"label":"Harman의 Sound United 인수 (2025 3Q)","event_type":"acquisition",
     "actors":["Harman"],"objects":["Sound United"],
     "evidence_span":"Sound United를 2025년 3분기에 인수"}
  ]
}
```

**필수 필드**: chunk_id, run_id, chunk_type, entities, relations, events
**빈 chunk** (boilerplate): entities/relations/events = `[]`

---

## 5. STEP 4 — Claude 추출 → Neo4j MERGE (loader)

### 명령
```bash
python scripts/load_company_claude_direct.py \
  --corp 00161383 \
  --run-id 20260528_0808_01 \
  --stage load-claude \
  --name 한미반도체
```

### 내부 흐름 (자동)
1. `llm_extracts.jsonl` 읽어서 chunk 단위로 처리
2. **default_only skip**: entities=[Org만] + relations/events=[] 인 chunk 는 자동 skip (inflated 방지)
3. EntityLinker (enable_vector=True + canonical fallback + synthetic ID) 로 모든 entity 매칭
4. POLARIS merger 호출 — Statement/Event MERGE + PROV-O 부착
5. **Post-load Org dup cleanup** (APOC mergeNodes)
6. **Post-load Event PROV backfill** (rcept_no 기반)
7. `canonical_clusters.json` 자동 생성

### 효과
- Statement PROV 100%, Event PROV 100% 보장
- Org dup 0 보장
- 회사당 1-5분

---

## 6. STEP 5 — 검증 쿼리

통합 스크립트가 자동 출력. 수동 검증:

```cypher
-- (1) 본문 chunk 정직한 coverage
MATCH (c:Chunk) WHERE c.corp_code=$code
  AND c.chunk_type IN ['text_micro','text_macro']
  AND EXISTS {(c)-[h:hasActor|hasObject]-()
    WHERE h.run_id=$run_id AND coalesce(h.role,'') <> 'document_subject'}
WITH count(c) AS with_entity
MATCH (c2:Chunk) WHERE c2.corp_code=$code AND c2.chunk_type IN ['text_micro','text_macro']
RETURN with_entity, count(c2) AS total, 100.0*with_entity/count(c2) AS pct;
-- 목표: 50%+ (한미 73%, 삼성 65%, 동진 50%, SK 50% — v2 재추출 후)

-- (2) Statement PROV 100%
MATCH (s:Statement {run_id:$run_id})
OPTIONAL MATCH (s)-[:wasDerivedFrom]->(c:Chunk)
WITH s.subject_id AS subj, s.object_id AS obj, count(s) AS total, count(c) AS linked
WHERE subj=$code OR obj=$code
RETURN total, linked;

-- (3) Event PROV 100%
MATCH (e:Event {corp_code:$code})
OPTIONAL MATCH (e)-[:wasDerivedFrom]->(target)
RETURN count(e) AS total, count(target) AS linked;

-- (4) Org dup 0
MATCH (o:Organization) WHERE o.name IS NOT NULL AND o.name <> ''
WITH o.name AS nm, collect(DISTINCT o.corp_code) AS codes
WHERE size(codes) > 1 RETURN nm, codes;
-- 결과 없어야 함

-- (5) 4-hop: Org → Filing → Chunk → Entity (graph traversal)
MATCH (o:Organization {corp_code:$code})-[:reports]->(:FilingDocument)
      -[:has_chunk]->(c:Chunk)-[:hasActor|hasObject]->(target)
WHERE target <> o
RETURN labels(target)[0] AS kind, target.name AS name, count(*) AS n
ORDER BY n DESC LIMIT 10;
```

---

## 7. Anti-pattern + Trap 모음

### ANTI-PATTERN 1: POLARIS `load` 명령 사용
```bash
# ❌ 새 standby_run_id 발급 → 기존 run_id 와 불일치
polaris load --db all

# ✅ 통합 스크립트 사용 (run_id 강제)
python scripts/load_company_claude_direct.py ...
```

### ANTI-PATTERN 2: fill_remaining (default_only)
```python
# ❌ 모든 chunk 에 회사명만 부착 → coverage inflated
def fill_remaining(all_chunk_ids):
    for cid in remaining:
        chunk_extracts[cid] = {"entities": [org("회사명")], ...}

# ✅ chunk text 읽고 명시. boilerplate 면 entities=[] 그대로
```

### ANTI-PATTERN 3: qwen3.5:9b LLM 호출
```bash
# ❌ LLM 부정확 (mojibake, 중국어 출력, empty response)
polaris graph-extract-semantic

# ✅ Claude 가 직접 chunk 읽고 추출 (ADR 021)
```

### TRAP 1: Korean encoding
```bash
# Windows / PowerShell
PYTHONIOENCODING=utf-8 python -X utf8 script.py
$env:PYTHONIOENCODING="utf-8"
```

### TRAP 2: APOC 의존
- `apoc.refactor.mergeNodes` 가 Org dup cleanup 에 필수
- Neo4j 에 APOC 플러그인 활성 필요 (현재 환경 OK)

### TRAP 3: stale run_id
- standby_run_id 가 의도와 다르면 모든 적재가 잘못된 그룹으로 감
- 통합 스크립트는 명시 `--run-id` 사용 — 매뉴얼 확인 필수

### TRAP 4: chunk_id 충돌
- 다른 회사 chunk_id 가 우연히 겹치면 잘못된 chunk 에 부착
- POLARIS schema 는 (chunk_id, run_id) 복합키라 안전
- 단, run_id 가 같으면 정말 같은 chunk 로 해석

### TRAP 5: RAG 에서 news 가 본문 누름
- Qdrant 에 news (`corp_code=00000000`, `chunk_type=news_text`) 가 별도 인덱스로 존재 — Neo4j 에는 없음.
- "회사명 + 일반 키워드" 질의는 뉴스 본문 키워드 매칭이 보고서 본문보다 우세 → top 5 에 본문 안 들어옴.
- 영향 받는 회사: 본문 chunk 가 적은 SK (text_micro 119 / text_macro 10) 가 가장 두드러짐. 한미는 chunk 가 적어도 제품 특화 키워드 (HBM TC BONDER 등) 가 강해 영향 적음.
- 해결: 회사 단위 질의는 `query_filter = corp_code=<code>` 강제, 또는 chunk_type 가중치, 또는 reranker 추가.

### TRAP 6: table_nl 이 본문보다 vector 점수 높음
- 표 자연어화 chunk 가 일반 키워드 매칭에 강해 본문 (text_micro/macro) 를 top 결과에서 밀어냄.
- 하지만 table_nl 은 1-hop entity 가 `document_subject` (해당 회사 자체) 뿐 → 그래프 신호 빈약.
- 회사 단위 사실 질의에서는 본문 chunk 가 답인데 retrieval 단계에서 잃음.
- 해결: text_micro/macro 가산점 또는 chunk_type 별 별도 검색 후 결합.

---

## 8. 회사별 진행 상태 (2026-05-28 기준)

| 회사 | corp_code | chunk | 본문 coverage | Statement | Event | PROV |
|---|---|---|---|---|---|---|
| 삼성전자 | 00126380 | 10,008 | 107/165 (64.8%) | 402 | 35 | 100% |
| 한미반도체 | 00161383 | 8,660 | 43/59 (72.9%) | 74 | 10 | 100% |
| SK하이닉스 | 00164779 | 9,351 | 64/129 (49.6%) | 59 | 45 | 100% |
| 동진쎄미켐 | 00118804 | 10,360 | 88/176 (50.0%) | 381 | 38 | 100% |

> **SK 이력**: v1 추출은 fill_remaining anti-pattern 으로 inflated 97.7% → loader 자동 skip 후 정직 11.6% 였음. v2 재추출 (2026-05-28) 로 49.6% 회복.
> 자세한 이력: `data/4_dbGoldTest/graph_extracts/claude-direct-00164779-20260528/manifest.json`

### 사용 가능 (미적재)
디스크에 chunk + embedding 살아있음:
- 00160843, 00246417, 00369657, 01135941, 01489648

위 회사들 모두 같은 Playbook 패턴으로 1-2시간 안에 적재 가능.

---

## 9. Rollback 절차

특정 회사 추출을 통째로 되돌리려면:

```cypher
// 1. Claude-direct 적재 노드/엣지 (run_id 기반)
MATCH (s:Statement {run_id:$run_id})
WHERE s.subject_id=$corp OR s.object_id=$corp DETACH DELETE s;
MATCH (e:Event {run_id:$run_id, corp_code:$corp}) DETACH DELETE e;

// 2. Chunk-entity 엣지
MATCH (c:Chunk {corp_code:$corp})-[h:hasActor|hasObject]-()
WHERE h.run_id=$run_id DELETE h;

// 3. synthetic Claude 노드 (해당 회사 추출 시 만들어진 것만)
MATCH (o:Organization) WHERE o.corp_code STARTS WITH 'XCLAUDE_'
  AND o.first_seen_run_id=$run_id DETACH DELETE o;
// (PCLAUDE_, PRCLAUDE_, TCLAUDE_, PLCLAUDE_ 도 동일)
```

**비가역**:
- Org dup mergeNodes (APOC) — 원복 불가
- FilingDocument backfill — stub 삭제는 가능, 정형 데이터 복원은 별도 빌드

---

## 10. 다음 회사 추출 시 — Prompt 예시

```
ADR 021 양식으로 다음 회사 추출 진행.

회사: <회사명> (corp_code <8자리>)
근거: docs/CLAUDE_DIRECT_PLAYBOOK.md

순서:
1. .env POLARIS_CORPS 에 <corp_code> 추가
2. python scripts/load_company_claude_direct.py --corp <corp_code> --run-id <run_id> --stage chunk
3. python scripts/load_company_claude_direct.py --corp <corp_code> --run-id <run_id> --stage structural --name <회사명>
4. claude_input.json 생성 (Playbook STEP 4.1 Python 코드)
5. Claude 가 chunk 읽고 llm_extracts.jsonl 작성 (STEP 4.2 규칙)
   - ⚠️ fill_remaining 절대 X (entities=[Org만] 패턴 금지)
   - boilerplate 는 entities=[] 그대로
6. python scripts/load_company_claude_direct.py --corp <corp_code> --run-id <run_id> --stage load-claude --name <회사명>
7. manifest.json 작성 (한미/SK/동진 manifest 참고)

검증: STEP 6 쿼리로 확인. 본문 coverage 50%+ 목표 (한미 73%, 삼성 65%, 동진/SK 50% 수준).

⚠️ 사용자 입력 corp_code 가 디스크에 없으면 즉시 중단하고 확인할 것.
   (예: 동진쎄미켐 = 00118804 인데 00128605 같은 다른 코드 받으면 오타.)
```

---

## 11. 참고

| 자료 | 위치 |
|---|---|
| ADR 021 | `docs/adr/021-claude-direct-extraction.md` |
| 통합 적재 스크립트 | `scripts/load_company_claude_direct.py` |
| RAG 통합 테스트 | `scripts/rag_test.py` |
| POLARIS schema | `src/polaris/graph/merger.py` (CQ_* 템플릿) |
| EntityLinker | `src/polaris/graph/linker.py` |
| reifier | `src/polaris/graph/reifier.py` |
| 알리아스 yaml | `src/polaris/graph/lexicon/` |
| 첫 사례 (Samsung) | `data/4_dbGoldTest/graph_extracts/claude-direct-20260528/` |
| 한미 사례 | `data/4_dbGoldTest/graph_extracts/claude-direct-00161383-20260528/` |
| SK 사례 (v2 재추출) | `data/4_dbGoldTest/graph_extracts/claude-direct-00164779-20260528/` |
| 동진쎄미켐 사례 | `data/4_dbGoldTest/graph_extracts/claude-direct-00118804-20260528/` |
