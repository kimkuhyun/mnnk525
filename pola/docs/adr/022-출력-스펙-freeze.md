# ADR 022 — 데모 산출물 출력 스펙 Freeze

**날짜**: 2026-05-29
**상태**: Accepted
**우선순위**: P0 (UI 작업 착수 전제)

## 결정

POLARIS 데모의 사용자 향 산출물은 **3계층**으로 고정한다.

1. **Cosmos Trace** — 뉴스 핵심 쿼리 → 의미 그래프가 점진적으로 점등되는 우주 별자리(3D · 인터랙티브 · 단계 애니메이션). 응답 = `/api/galaxy/trace`.
2. **Bloomberg Dashboard** — 결과 카드 + 상황 설명. 6 섹션 + 헤드라인 인사이트 + 핵심 시그널. 응답 = `/api/analyze` 의 `report`.
3. **Source Insight** — 원본 데이터 카드. **단순 본문 미리보기 금지**. 모든 청크 카드는 `match_reason / what_it_says / why_it_matters / graph_role / quote` 다섯 필드를 가진다.

골든 케이스는 두 가지로 freeze한다.
- **Case A — iHBM (단일 신호 / 기술)**: `news_id=59401ebdf55904a9` SK하이닉스 iHBM 공개.
- **Case B — 밸류에이션 (비교 / 재무)**: `news_id=e98cbc5b5d9781c3` 미래에셋 보고서 — 삼전·하닉 목표주가 동반 상향.

이 두 케이스의 입력 + 기대 출력(키 필드만)을 `_demo/golden/cases.yml` 에 박제(pin)한다. 검증은 `python _demo/verify_golden.py`. 스키마 변경 시 두 케이스가 동시에 통과해야 한다.

## 데이터 흐름 (한눈에)

```
                       ┌─────────────────┐
   뉴스 본문 (1건) ───▶│ extract seeds   │── 본문에 등장하는 org/tech 라벨
                       └────────┬────────┘
                                ▼
                       ┌─────────────────┐
                       │ Vector RAG      │── bge-m3 → Qdrant top-k
                       └────────┬────────┘
                                ▼
                       ┌─────────────────┐
                       │ Graph augment   │── Neo4j 1-hop (actors/objects/events)
                       └────────┬────────┘
                                ▼
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
 ┌──────────────┐       ┌──────────────┐       ┌──────────────┐
 │ Layer 1      │       │ Layer 2      │       │ Layer 3      │
 │ Cosmos Trace │       │ Bloomberg    │       │ Source       │
 │ (3D 별자리)  │       │ Dashboard    │       │ Insight 카드 │
 │ 점등 시퀀스  │       │ 6 섹션+헤더  │       │ 5필드/카드   │
 └──────┬───────┘       └──────┬───────┘       └──────┬───────┘
        │                      │                      │
        └─────────────── 동일 trace_id 로 cross-link ──┘
```

## Cosmos Trace — stage 시간선

`lit_at` 은 백엔드가 결정한다. 프런트는 timeline scrub 만:

```
t=0.0   ┃ intake        뉴스 본문 수신
t=0.5   ┃ topic ────────●●  seed 별 점등 (본문에 직접 등장한 org/tech)
t=1.2   ┃ vector ───────●●●●●●  vector RAG top-k → 청크 매칭
t=2.0   ┃ graph (1hop) ─●●●●●●●●●●  1-hop 이웃 점등 (per-seed ≤ 6)
t=2.8   ┃ graph (2hop) ─●●●●  공유 이웃 (다리 노드)
t=3.3   ┃ shortest path ●●    seed pair 잇는 경로
t=3.7   ┃ ppr ──────────●●●●●●●●  Personalized PageRank score 상위
t=4.5   ┃ constellation ━━━━━━━━━━━━━━━━━━━  모든 엣지 점등
t=5.0   ┃ done ✓
```

같은 stage 안에서는 weight 내림차순으로 0.05s 간격. 엣지의 `lit_at` = max(src.lit_at, tgt.lit_at) + 0.05.

## Source Insight — 카드 anatomy

```
┌─ Source Insight Card ─────────────────────────────────────────────┐
│ ① source ─ DART URL · 회사 · rcept_no · section_path · chunk_type │
│ ② match_reason ─ vector_score + matched_keywords + filter         │
│      "벡터 유사도 0.87 · 키워드 'HBM/고대역폭/패키징' 일치 …"        │
│ ③ what_it_says ─ 1줄                                              │
│      "SK하이닉스 메모리 사업부의 HBM3E 양산 체제 사업 개요"         │
│ ④ why_it_matters ─ 1~2줄                                          │
│      "뉴스의 iHBM 기술이 이미 양산 중인 HBM3E 의 다음 세대 …"        │
│ ⑤ graph_role ─ 점등된 별                                          │
│      actors: [SK하이닉스]                                          │
│      objects: [HBM, HBM3E, 메모리 사업부]                          │
│ ⑥ quote ─ 본문 인용 + highlight span                              │
│      "당사 메모리 사업부는 [HBM3E] 의 [양산] 체제를 완비하고…"      │
└───────────────────────────────────────────────────────────────────┘
        │
        ▼ 5필드 중 ③④ 중 하나라도 비면 — 카드 제외 (스펙 강제)
```

## 출력 계층 1 — Cosmos Trace

`POST /api/galaxy/trace` 응답:

```jsonc
{
  "title": "벌써 다음 고지 향하는 하이닉스…",
  "news_id": "59401ebdf55904a9",

  // 본문에서 직접 추출된 시드 — UI 에서 "원래 별" 로 강조
  "seeds": [
    { "id": "org:00164779", "label": "SK하이닉스", "type": "Organization",
      "matched_span": "SK하이닉스", "lit_at": 0.5 }
  ],

  // 점등 순서. UI 는 lit_at 기준 timeline scrub.
  "node_sequence": [
    {
      "id": "tech:HBM",
      "label": "HBM",
      "type": "Technology",
      "x": -812.3, "y": 410.7, "z": 245.1,  // 3D 좌표 (해시 결정론, 재실행 동일)
      "weight": 18,                          // degree
      "lit_at": 1.6,                         // 시작부터 초 단위 누적 시간
      "lit_reason": "1hop",                  // seed | 1hop | 2hop_bridge | ppr | shortest_path
      "via": ["org:00164779"],               // 어떤 시드로부터 도달
      "score": 0.92                          // PPR/shortest 가중치
    }
    /* … */
  ],

  // 점등 노드 간 엣지 (lit_at 기준 순서 유지)
  "edges": [
    { "id": "org:00164779->tech:HBM:PRODUCES",
      "source": "org:00164779", "target": "tech:HBM",
      "type": "PRODUCES", "lit_at": 1.7 }
  ],

  // stage 별 narration (intake/topic/vector/graph/constellation/done)
  "steps": [
    { "stage": "intake",       "msg": "뉴스 본문 수신",           "at": 0.0 },
    { "stage": "topic",        "msg": "시드 엔티티 1건",          "at": 0.5 },
    { "stage": "vector",       "msg": "Vector RAG · top-15 매칭",  "at": 1.2, "mode": "vector_rag" },
    { "stage": "graph",        "msg": "1-hop 확장 · 22 노드",      "at": 2.0 },
    { "stage": "graph",        "msg": "PPR · 신규 +14",            "at": 3.2 },
    { "stage": "constellation","msg": "별자리 점등 · 41 노드 · 88 엣지", "at": 4.5 },
    { "stage": "done",         "msg": "지식그래프 완성",            "at": 5.0 }
  ],

  "stats": {
    "seeds": 1, "hop1": 22, "hop2": 8, "ppr": 14, "shortest_path": 2,
    "total_lit_nodes": 41, "total_lit_edges": 88
  },

  // Layer 3 가 인용할 chunk 후보
  "chunks": [ { "chunk_id": "...", "score": 0.87, "corp_code": "00164779",
                "corp_name": "SK하이닉스", "section_path": "..." } ]
}
```

**lit_at 규칙** (deterministic): stage 누적 시간 + 같은 stage 내에서는 weight 내림차순으로 0.05s 간격. 프런트가 `lit_at` 기준 정렬·scrub 시 동일 결과.

**3D 좌표 규칙**: `_star_pos(node_id)` → md5 해시 12 byte 를 (r, θ, φ) 로 분해. r ∈ [0.4, 1.0] × radius, aspect_x=1.85 (가로 길게). z 는 sin(φ) × 0.55 × radius (구가 아닌 *얇은 디스크* 형태 — 우주 사진 톤).

## 출력 계층 2 — Bloomberg Dashboard

`POST /api/analyze` 응답의 `report` 필드:

```jsonc
{
  "primary_corp": { "corp_code": "00164779", "corp_name": "SK하이닉스", "ticker": "000660" },

  "insight_summary": [
    // 3~5 줄, 헤드라인. deterministic (1차) + LLM (선택) 으로 생성.
    "SK하이닉스가 HBM 패키지 내부에 일체형 냉각 요소(ICE)를 적용한 iHBM 신기술을 공개했다.",
    "열저항을 30% 이상 낮춰 HBM5 등 차세대 제품의 발열 한계를 푼다.",
    "WLP 공정 기반이라 양산성도 확보 — 삼성전자·마이크론과의 차세대 HBM 경쟁이 가속.",
    "재무적으로는 LTA 확대 + HBM 고객 다변화로 ROE 추정치 상향 흐름과 정합."
  ],

  "key_signals": [
    // 본문·청크에서 deterministic 으로 뽑은 시그널. UI 는 severity 색상.
    { "kind": "기술/제품",  "text": "iHBM · 열저항 -30%",          "severity": "high",
      "evidence_chunk_id": "...", "evidence_corp": "SK하이닉스" },
    { "kind": "경쟁구도",  "text": "삼성전자·마이크론 HBM4E 경쟁",  "severity": "med",
      "evidence_chunk_id": "..." },
    { "kind": "수급/계약",  "text": "LTA 확대로 공급 가시성↑",      "severity": "med",
      "evidence_chunk_id": "..." }
  ],

  "sections": {
    "exec":      [ "NEWS │ …", "PUB │ …", "FOCUS │ …", "LENS │ …", "FORM │ …" ],
    "entities":  [ { "name": "...", "type": "Organization|Person|Product", "mentions": 6, "corp_code": "..." } ],
    "governance":[ { "name": "...", "role_hint": "—", "mentions": 2 } ],
    "financials":{
      "cards":  [ { "key": "자기자본비율", "value": 53.1, "unit": "%", "year": 2024, "delta": +2.4, "delta_from_year": 2023 } ],
      "series": { "자기자본비율": [ { "year": 2020, "value": 41.0 }, … ] }
    },
    "timeline":  [ { "date": "2026-05-26", "kind": "news|event", "label": "iHBM 공개" } ],
    "scenarios": [ "현 상태 유지 …", "영향력 확대 …", "변수 발생 …" ]
  },

  // ↓ Layer 3 — source_chunks 는 별도 스펙 (아래).
  "source_chunks": [ … ]
}
```

## 출력 계층 3 — Source Insight (원본 데이터)

기존 `source_chunks[].preview[:300]` 단순 미리보기를 **폐기**하고 다음 카드로 교체.

```jsonc
{
  "chunk_id": "00164779_text_2024_3_31_001",
  "source": {
    "corp_code": "00164779", "corp_name": "SK하이닉스",
    "rcept_no": "20240514001234",
    "section_path": "Ⅱ. 사업의 내용 > 1. 사업의 개요 > 메모리 사업부",
    "chunk_type": "text_macro",
    "dart_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20240514001234"
  },

  // (1) 왜 이 청크가 뽑혔는가 — 검색·매칭 근거. 결정형.
  "match_reason": {
    "vector_score": 0.871,
    "matched_keywords": ["HBM", "고대역폭", "패키징"],
    "filter_matches":  { "corp_code": "00164779" },
    "narrative": "벡터 유사도 0.87 · 키워드 'HBM/고대역폭/패키징' 3건 일치 · corp_code 필터 적중"
  },

  // (2) 이 청크는 무엇을 말하는가 — 1줄. 결정형(섹션헤더+1번째 명제문) 또는 LLM.
  "what_it_says": "SK하이닉스 메모리 사업부가 HBM3E 양산 체제를 갖추고 고대역폭 솔루션 라인업을 확대하고 있다는 사업 개요.",

  // (3) 이 뉴스 맥락에서 시사하는 점 — 1~2줄. 결정형(엔티티/이벤트 결합) + LLM 옵션.
  "why_it_matters": "뉴스의 iHBM 신기술이 이미 양산 중인 HBM3E 라인의 다음 세대 (HBM5) 에 적용된다는 점에서, 이 청크의 기존 양산 인프라가 새 기술의 빠른 적용 근거가 된다.",

  // (4) 점등 그래프에서 이 청크가 가져온 별들
  "graph_role": {
    "actors":   [ { "id": "org:00164779",   "label": "SK하이닉스" } ],
    "objects":  [ { "id": "tech:HBM",       "label": "HBM" },
                  { "id": "tech:HBM3E",     "label": "HBM3E" },
                  { "id": "product:메모리",  "label": "메모리 사업부" } ],
    "events":   []
  },

  // (5) 본문 인용 — UI 가 highlight 처리 가능하도록 span 단위 (start/end 는 청크 본문 기준).
  "quote": {
    "text": "당사 메모리 사업부는 HBM3E 의 양산 체제를 완비하고…",
    "highlight": [ { "start": 8, "end": 14 }, { "start": 19, "end": 22 } ]  // "HBM3E", "양산"
  }
}
```

### 생성 전략 — Deterministic 우선, LLM 토글

| 필드 | 결정형 1차 | LLM 보강 (선택) |
|---|---|---|
| `match_reason` | Qdrant score + 본문 token 교집합 + payload filter | — |
| `what_it_says` | `{section_path} 의 {chunk_type}: {본문 첫 명제문(. 또는 다음 두 줄 중 짧은 것)}` | qwen3.5:9b, 1줄, max 60자 |
| `why_it_matters` | 뉴스 seed 엔티티와 청크 엔티티 교집합 + 청크 이벤트 라벨 | qwen3.5:9b, 1~2줄, max 140자 |
| `graph_role` | augment_with_graph 결과 그대로 | — |
| `quote` | 첫 명제문 (`.` 단위) — 매칭 키워드 위치 span | — |

LLM 옵션은 `?llm=true` 쿼리 파라미터 또는 환경 변수 `POLARIS_INSIGHT_LLM=1` 로 토글. **기본은 결정형** (캐시 가능, 재현 가능, 비용 0).

## 골든 케이스 2건

### Case A — iHBM (단일 신호 · 기술)

| 항목 | 값 |
|---|---|
| `news_id` | `59401ebdf55904a9` |
| 제목 | "벌써 다음 고지 향하는 하이닉스…발열 확 낮춘 iHBM 신기술 공개" |
| seeds (기대) | `org:00164779` (SK하이닉스) |
| stats 최소치 | seeds ≥ 1, hop1 ≥ 8, ppr ≥ 5, total_lit ≥ 20 |
| insight_summary | 첫 줄에 "iHBM" + "SK하이닉스" 포함 |
| key_signals 최소 | "iHBM" 한 건 + 경쟁사("삼성전자" 또는 "마이크론") 한 건 |
| source_chunks 최소 | 5건, 모두 `match_reason.narrative` 비어있지 않음 |

### Case B — 밸류에이션 (비교 · 재무)

| 항목 | 값 |
|---|---|
| `news_id` | `e98cbc5b5d9781c3` |
| 제목 | "“삼성전자 55만원·하이닉스 380만원”…이익에 비하면 아직 싸다" |
| seeds (기대) | `org:00126380` (삼성전자) + `org:00164779` (SK하이닉스) **둘 다** |
| stats 최소치 | seeds = 2, shortest_path ≥ 1 (두 seed 잇는 다리), total_lit ≥ 30 |
| financials.cards | primary_corp 의 자기자본비율/부채비율 중 최소 1건 |
| insight_summary | "목표주가" 또는 "밸류에이션" 포함 |
| key_signals 최소 | "재무/실적" 카테고리 시그널 1건 + "수급/계약" (LTA) 시그널 1건 |

두 케이스 모두 `_demo/golden/cases.yml` 에 freeze. PR 시 `python _demo/verify_golden.py` 로 두 케이스 모두 회귀 없는지 확인.

## 샘플 응답 — Case A (iHBM)

**`POST /api/galaxy/trace` (발췌)**:

```jsonc
{
  "title": "벌써 다음 고지 향하는 하이닉스…발열 확 낮춘 iHBM 신기술 공개",
  "news_id": "59401ebdf55904a9",
  "seeds": [
    { "id": "org:00164779", "label": "SK하이닉스", "type": "Organization",
      "x": -812.3, "y": 410.7, "z": 245.1, "weight": 32,
      "matched_span": "SK하이닉스", "lit_at": 0.5 }
  ],
  "node_sequence": [
    { "id": "tech:HBM",      "label": "HBM",      "type": "Technology",
      "x":  912.1, "y": -322.5, "z":  78.4, "weight": 18,
      "lit_reason": "1hop", "via": ["org:00164779"], "lit_at": 2.00 },
    { "id": "tech:HBM3E",    "label": "HBM3E",    "type": "Technology",
      "x":  144.7, "y":  701.1, "z": -198.2, "weight": 12,
      "lit_reason": "1hop", "via": ["org:00164779"], "lit_at": 2.05 },
    { "id": "org:00126380",  "label": "삼성전자",  "type": "Organization",
      "x": -1611.8, "y": -55.9, "z":  90.3, "weight": 27,
      "lit_reason": "2hop_bridge", "via": ["org:00164779"], "lit_at": 2.80 },
    { "id": "event:HBM3E-양산", "label": "HBM3E 양산", "type": "Event",
      "x":  201.5, "y":  -440.0, "z": 312.0, "weight": 6,
      "lit_reason": "ppr", "via": ["org:00164779"], "score": 0.0431, "lit_at": 3.70 }
  ],
  "edges": [
    { "id": "org:00164779->tech:HBM:PRODUCES",
      "source": "org:00164779", "target": "tech:HBM",
      "type": "PRODUCES", "lit_at": 2.05 }
  ],
  "steps": [
    { "stage": "intake",       "msg": "뉴스 본문 수신",                  "at": 0.0 },
    { "stage": "topic",        "msg": "본문에서 추출한 후보 엔티티 1건",  "at": 0.5 },
    { "stage": "vector",       "msg": "Vector RAG · top-15 chunk 매칭",    "at": 1.2,
      "mode": "vector_rag" },
    { "stage": "graph",        "msg": "1-hop 확장 · 인접 노드 22건",       "at": 1.9 },
    { "stage": "graph",        "msg": "PPR · 신규 노드 +14 · 엣지 +18",   "at": 2.45 },
    { "stage": "constellation","msg": "별자리 점등 · 41 노드 · 88 엣지",   "at": 4.5 },
    { "stage": "done",         "msg": "지식그래프 완성",                  "at": 5.0 }
  ],
  "stats": {
    "seeds": 1, "vector": 4, "hop1": 22, "hop2_bridge": 8,
    "ppr": 14, "shortest_path": 0,
    "total_lit_nodes": 49, "total_lit_edges": 88
  }
}
```

**`POST /api/analyze` (report 발췌)**:

```jsonc
{
  "primary_corp": { "corp_code": "00164779", "corp_name": "SK하이닉스" },
  "insight_summary": [
    "SK하이닉스: iHBM · 열저항 -30% · HBM5 차세대 적용 예고",
    "삼성전자·마이크론과 차세대 HBM 개발 경쟁 가속",
    "LTA 확대로 공급 가시성↑ — 데이터센터 수주잔고 증가"
  ],
  "key_signals": [
    { "kind": "기술/제품",  "text": "iHBM 신기술 공개 — 열저항 30% 이상 저감",
      "keyword": "iHBM", "severity": "high",
      "evidence_chunk_id": "00164779_text_2024_…", "evidence_corp": "SK하이닉스" },
    { "kind": "경쟁구도",   "text": "삼성전자·마이크론 HBM4E 경쟁 가속",
      "keyword": "마이크론", "severity": "med",
      "evidence_chunk_id": null, "evidence_corp": null }
  ],
  "source_chunks": [
    {
      "chunk_id": "00164779_text_…_001",
      "source": {
        "corp_code": "00164779", "corp_name": "SK하이닉스",
        "section_path": "Ⅱ. 사업의 내용 > 1. 사업의 개요 > 메모리 사업부",
        "chunk_type": "text_macro",
        "dart_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20240514…"
      },
      "match_reason": {
        "vector_score": 0.871,
        "matched_keywords": ["HBM", "고대역폭", "패키징"],
        "filter_matches": { "corp_code": "00164779" },
        "narrative": "벡터 유사도 0.87 · 키워드 'HBM', '고대역폭', '패키징' 일치 · SK하이닉스 필터 적중"
      },
      "what_it_says": "SK하이닉스 · 메모리 사업부 · 본문 발췌: 당사 메모리 사업부는 HBM3E 양산 체제를 갖추고…",
      "why_it_matters": "뉴스 핵심어 HBM, 고대역폭 가 청크의 HBM 관련 사업 맥락과 직접 맞물린다. (SK하이닉스 1차 시드)",
      "graph_role": {
        "actors":  [ { "id": "org:00164779", "label": "SK하이닉스" } ],
        "objects": [ { "id": "tech:HBM", "label": "HBM" },
                     { "id": "tech:HBM3E", "label": "HBM3E" } ],
        "events":  []
      },
      "quote": {
        "text": "당사 메모리 사업부는 HBM3E 의 양산 체제를 완비하고…",
        "highlight": [ { "start": 11, "end": 16, "text": "HBM3E" },
                       { "start": 20, "end": 22, "text": "양산" } ]
      }
    }
  ]
}
```

## 샘플 응답 — Case B (밸류에이션)

**`POST /api/galaxy/trace` (발췌)**:

```jsonc
{
  "title": "“삼성전자 55만원·하이닉스 380만원”…이익에 비하면 아직 싸다",
  "news_id": "e98cbc5b5d9781c3",
  "seeds": [
    { "id": "org:00126380", "label": "삼성전자",   "type": "Organization",
      "x": -1611.8, "y": -55.9, "z":  90.3, "weight": 41, "lit_at": 0.50 },
    { "id": "org:00164779", "label": "SK하이닉스", "type": "Organization",
      "x": -812.3,  "y": 410.7, "z": 245.1, "weight": 32, "lit_at": 0.55 }
  ],
  "node_sequence": [
    { "id": "org:미래에셋증권",  "label": "미래에셋증권", "type": "Organization",
      "lit_reason": "shortest_path", "via": ["org:00126380", "org:00164779"], "lit_at": 3.30 },
    { "id": "tech:HBM4",         "label": "HBM4",         "type": "Technology",
      "lit_reason": "1hop", "via": ["org:00164779"], "lit_at": 2.00 },
    { "id": "tech:DRAM",         "label": "DRAM",         "type": "Technology",
      "lit_reason": "1hop", "via": ["org:00126380"], "lit_at": 2.05 }
  ],
  "stats": {
    "seeds": 2, "vector": 5, "hop1": 18, "hop2_bridge": 12,
    "ppr": 12, "shortest_path": 3,
    "total_lit_nodes": 52, "total_lit_edges": 114
  }
}
```

**`POST /api/analyze` (report 발췌)**:

```jsonc
{
  "primary_corp": { "corp_code": "00126380", "corp_name": "삼성전자" },
  "insight_summary": [
    "삼성전자·SK하이닉스 목표주가 동반 상향 — 미래에셋증권",
    "글로벌 메모리 밸류에이션 상향 반영 — PBR 5.3→6.2, EV/EBITDA 6.0→7.0",
    "LTA 확대 + 데이터센터 수주잔고 ≫ 설비투자 증가 속도"
  ],
  "key_signals": [
    { "kind": "재무/실적", "text": "SK하이닉스 목표주가 320만→380만 (+18.8%), 삼성 48만→55만 (+14.6%)",
      "keyword": "목표주가", "severity": "high",
      "evidence_chunk_id": null, "evidence_corp": null },
    { "kind": "수급/계약",  "text": "데이터센터 수주잔고 증가 속도 ≫ 설비투자 — LTA 확대",
      "keyword": "LTA", "severity": "med",
      "evidence_chunk_id": "00164779_table_…", "evidence_corp": "SK하이닉스" },
    { "kind": "경쟁구도",   "text": "글로벌 메모리 2개사 (마이크론·키옥시아) 배수 평균 반영",
      "keyword": "마이크론", "severity": "med" }
  ],
  "sections": {
    "financials": {
      "cards": [
        { "key": "자기자본비율", "value": 53.1, "unit": "%",
          "year": 2024, "delta": 2.4, "delta_from_year": 2023 },
        { "key": "부채비율",     "value": 31.4, "unit": "%",
          "year": 2024, "delta": -1.9, "delta_from_year": 2023 }
      ]
    }
  }
}
```

## 의사 결정 근거

- **왜 결정형 우선?** — 데모 재현성·캐시·비용 0. LLM 은 향상용 toggle. ADR 021 의 Claude 직접 추출과 같은 결을 따르되, 인사이트 1줄은 룰로 충분히 quality 확보 가능.
- **왜 원본 데이터 카드를 5필드로?** — "참고용 의미없는 데이터 나열 금지" 가 핵심 요구. 5필드 중 하나라도 비면 *해당 청크는 응답에서 제외* (룰 강제). 빈약한 청크가 통과하는 것보다 빠지는 게 낫다.
- **왜 3D 가 디스크 형태?** — 구는 회전 시 노드 가림이 심하고 좌표 학습 부담. 우주 사진은 사실 *얇은 디스크* (은하수) — z 폭 좁게(0.55) 잡으면 가로 우주 + 살짝 깊이감.
- **왜 `lit_at` 을 백엔드에서?** — 프런트별 타이밍 분기 방지. 백엔드가 결정하면 같은 trace 가 모든 클라이언트에서 동일 애니메이션.

## 미적용 (스코프 아웃)

- 무의미 뉴스(스팸/리스팅) 필터링 — 현 단계 고려 안 함 (사용자 명시).
- 멀티턴 추론 / 뉴스간 cross-reference — Layer 2 가 다음 단계.
- 한미반도체·동진쎄미켐 등 기타 6사 골든 케이스 — Case A/B 가 안정화된 후 확장.
