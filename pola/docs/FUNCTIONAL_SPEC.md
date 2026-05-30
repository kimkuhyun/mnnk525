# POLARIS 기능 정의서 (Functional Spec)

> 버전: v1.0 · 작성: 2026-05-29 · 상태: 확정(ERD v2.1 freeze 기반)
> 짝 문서: `docs/ERD.md` (데이터 모델 v2.1) · 데모: `_demo/service_main.html`, `_demo/workbench_v1.html`

---

## 1. 서비스 개요

| 항목 | 내용 |
|---|---|
| 한 줄 정의 | 흩어진 정보(공시·뉴스·정책·통계·특허)를 엮어 한 회사의 **관계 지도**를 그리고, 모든 내용에 **출처**를 다는 서비스 |
| 정체성 | **관계·구조 데이터** 제공 (값=토스, 양=썸트렌드, 관계·맥락=POLARIS) |
| 화면 철학 | "차트는 질문, 그래프는 답" — 모든 차트는 그래프 탐색의 진입점 |
| 1차 타겟 | 반도체 산업 전략·IR 담당자, 애널리스트 (B2B) |
| 1차 시드 | 삼성전자 단일 (`corp_code 00126380`), 일(day) 단위 |
| 목표 | 창업/사업화 — 단일 시드로 "좁게 깊게" 검증 후 확장 |

---

## 2. 핵심 개념 (설계 원칙)

1. **Neo4j = 관계의 source of truth.** 관계를 타고 다니는 모든 기능의 본체.
2. **MariaDB = 집계 캐시.** 숫자(추이·감성·카운트)는 precompute. 언제든 그래프에서 재생성 가능.
3. **Qdrant = 의미 진입점.** 자연어/키워드 → 관련 문서·노드 찾기.
4. **GraphRAG** = 벡터 진입 → 그래프 1~2hop 확장 → LLM 답변 + citation.
5. **Drill-down 원칙.** 모든 집계 숫자는 `evidence_doc_ids`로 그래프 부분집합까지 역추적 가능.
6. **ID 일관성.** 세 저장소가 `chunk_id·doc_id·corp_code·rcept_no`를 공유해야 citation·drill-down 성립.
7. **탐색 깊이.** 펼치기는 1~2hop(노이즈 방지), 경로 탐색은 양 끝 지정 시 3~4hop 허용.

---

## 3. 데이터 소스 (4개 층)

| 층 | 채우는 것 | 소스 | 순위 |
|---|---|---|---|
| ① 골격 | 지분·임원·계열 (구조) | 공시 DART, 공정위 FTC | 1 |
| ② 근육 | 사건·발표 (움직임) | 기업 공식 IR / 뉴스 / 한경컨센서스·네이버 | 1·2 |
| ③ 신경 | 조기 신호 | 채용공고, 커뮤니티·SNS (신호용·원문 비저장) | 2·3 |
| ④ 배경 | 산업·경제·기술 | 통계청 KOSIS, 한국은행, 특허 Google Patents(메인)/USPTO | 1 |

제외: KIPRIS Plus(유료), 증권사 원본 리포트(유료).

---

## 4. 기능 정의

각 기능: 설명 / 입력 / 처리(사용 DB) / 출력 / ERD 매핑 / 우선순위.

### F-01. 관계 지도 (Relation Graph) ★핵심
- **설명**: 회사를 중심으로 1~2hop 관계망을 시각화. 노드 크기=멘션 빈도, 선 색=감성, 굵기=공동출현.
- **입력**: corp_code, 기간, hop(1/2), 타입 필터, 감성 필터
- **처리**: 🕸️Neo4j — `(s)<-[:ABOUT]-(Document)-[:MENTIONS]->(n)` 순회, 가중치 컷으로 노이즈 제거
- **출력**: 노드·엣지 집합 (인터랙티브 그래프)
- **ERD**: `Document`, `Organization/Product/Technology/Keyword`, `MENTIONS`, `ABOUT`
- **우선순위**: P0

### F-02. 오늘의 브리핑 (AI Briefing)
- **설명**: 오늘 핵심 동향을 3문장 요약, 문장마다 근거 문서 링크.
- **처리**: 📊선정(오늘 신규/이상) → 🕸️관계 수집 → LLM 요약+citation
- **출력**: 요약 텍스트 + 근거 doc_id 목록 (밑줄 클릭 시 원문)
- **ERD**: `document_unified`, `Document`, `MENTIONS`, `HAS_SENTIMENT`
- **우선순위**: P1

### F-03. 핵심 지표 (KPI / 차트)
- **설명**: 총 멘션·감성 점수·시그널 수·신규 엔티티, 일별 추이·감성 도넛·Top 키워드.
- **처리**: 📊MariaDB 집계 (신규 엔티티만 🕸️ delta)
- **출력**: 숫자 + 차트
- **ERD**: `mention_daily`, `keyword_daily`, `topic_daily`
- **우선순위**: P0

### F-04. 시그널 / 알림 (Signals)
- **설명**: 스파이크·감성 반전·신규성·공시빈도 이상 자동 감지.
- **처리**: 📊일배치 계산 (신규 엔티티는 🕸️)
- **출력**: 알림 카드 (트리거 타입·점수·근거)
- **ERD**: `alert_event`, `mention_daily.novelty_score`
- **우선순위**: P2

### F-05. 근거 피드 (Evidence Feed)
- **설명**: 최근 문서 목록, 소스 배지(합법무료=파랑), 감성 점수. 모든 분석의 출처.
- **입력**: source_type 필터(전체/공시/뉴스/IR/특허/커뮤니티)
- **처리**: 📊`document_unified` 조회 (의미검색 시 🔍)
- **출력**: 문서 리스트 (제목·출처·시각·엔티티·감성)
- **ERD**: `document_unified`, `polaris-doc-1024`
- **우선순위**: P0

### F-06. POLARIS에게 묻기 (GraphRAG)
- **설명**: 자연어 질문 → 그래프 근거 기반 답변 + citation.
- **처리**: 🔍벡터 top-k → 🕸️1~2hop 관계 확장 → LLM
- **출력**: 답변 + 근거(chunk_id/doc_id) + 관계 하이라이트
- **ERD**: `Chunk`, `HAS_CHUNK`, `MENTIONS`, PROV-O
- **우선순위**: P1

### F-07. 워크벤치 렌즈 (Lens)
- **설명**: 시간 슬라이더·감성 토글·타입 필터·초점 키워드로 그래프를 실시간 재조회.
- **처리**: 🕸️ Cypher `WHERE` 조건 동적 교체
- **출력**: 필터 적용된 관계 그래프 (예: "부정만" → 악재 전파 경로)
- **ERD**: `MENTIONS`(weight,ts,sentiment), `CO_OCCURS_WITH`(pmi)
- **우선순위**: P1

### F-08. 경로 탐색 (Path Finding)
- **설명**: 두 노드의 숨은 연결 경로 찾기 (아는 두 대상 한정, 3~4hop).
- **처리**: 🕸️`shortestPath`
- **출력**: 경로 (예: 삼성 ─공유공급사→ 동진쎄미켐 ←─ SK하이닉스)
- **ERD**: 정형 backbone(`INVESTS_IN` 등) + `MENTIONS`
- **우선순위**: P2

### F-09. 신규 엔티티 발견 (Discovery)
- **설명**: 회사 주변에 처음 등장한 대상을 이상도·중심성으로 부각 ("새 얼굴").
- **처리**: 🕸️1-hop delta + `first_seen_ts` + (선택)중심성
- **출력**: 신규 노드 카드 (멘션·감성·첫 등장일)
- **ERD**: `Keyword.first_seen_ts`, `MENTIONS`
- **우선순위**: P1

### F-10. 차트 Drill-down
- **설명**: 차트의 한 점 클릭 → 그 시점의 관계 스냅샷으로.
- **처리**: 📊`evidence_doc_ids` → 🕸️`MATCH (d:Document) WHERE d.doc_id IN $ids`
- **출력**: 해당 시점 부분 그래프
- **ERD**: `*_daily.evidence_doc_ids` → `Document`
- **우선순위**: P1

### F-11. 특허 관계 (Patent)
- **설명**: 회사↔기술↔회사 관계, 인용망. "어떤 회사가 어떤 기술을 미는가".
- **처리**: 🕸️`(Org)-[:HOLDS_PATENT]->(Patent)-[:ABOUT]->(Tech)`, `CITES`
- **출력**: 기술 중심 관계망
- **ERD**: `Patent`, `HOLDS_PATENT`, `ABOUT`, `CITES`, `patent_raw`
- **우선순위**: P1

### F-12. 검색 / 회사 전환 / 기간 토글
- **검색**: 🔍벡터 → 🕸️노드 펼침. **회사 전환**: 시드 corp_code 교체. **기간**: 전역 `WHERE ts` 파라미터.
- **우선순위**: P0

---

## 5. 화면 구성

| 화면 | 파일 | 핵심 기능 |
|---|---|---|
| 서비스 메인 (홈) | `_demo/service_main.html` | 사이드바 + 브리핑(F-02) + KPI(F-03) + 관계지도(F-01) + 시그널(F-04) + 근거피드(F-05) |
| 관계 워크벤치 | `_demo/workbench_v1.html` | 렌즈(F-07) + 그래프 무대(F-01) + 인과체인 + 근거 + 묻기(F-06) + 스크럽바(F-10) |
| 소개 | `_demo/onepager.html` | 서비스 설명 (비기능) |

레이아웃 원칙: 좌=네비/렌즈, 중앙=관계 그래프(무대), 우=컨텍스트(인과·근거·묻기), 하단=시계열 스크럽바.

---

## 6. ERD 요약 (상세: `docs/ERD.md` v2.1)

```
🕸️ Neo4j (관계 truth)
  노드: Document(멀티라벨) · Organization · Person · Product · Technology
        · Keyword · Topic · Sentiment · Patent · Event · Statement · FinMetric
        · FilingDocument · Chunk · ExtractionActivity · BusinessGroup · MacroIndicator
  엣지: ABOUT · MENTIONS · OF_TOPIC · HAS_SENTIMENT · CO_OCCURS_WITH · HAS_CHUNK
        · HOLDS_PATENT · CITES · 정형 backbone(지분·공급·임원) · PROV-O

🔍 Qdrant (1024d, bge-m3, cosine)
  polaris-doc-1024(통합) · polaris-keyword-1024 · polaris-topic-1024
  · polaris-1024-cos-{blue|green} · polaris-news-body-1024 · polaris-org-er

📊 MariaDB (집계 캐시)
  document_unified · mention_daily · keyword_daily · topic_daily
  · keyword_assoc_window · macro_series · macro_indicator_catalog
  · alert_event · patent_raw · (기존: chunk_index 등)

교차키: chunk_id · doc_id · corp_code · rcept_no · keyword_id · topic_id · patent_id
```

기능 ↔ DB 분담:
- 🕸️ 그래프 주인공: F-01·F-08·F-09·F-11 + F-07 렌즈 + F-06/F-10 확장
- 📊 집계: F-03·F-04·F-05
- 🔍 벡터: F-12 검색 · F-06 진입

---

## 7. 비기능 요구 (Non-functional)

| 항목 | 요구 |
|---|---|
| 성능 | 차트/KPI < 50ms (precompute), 관계지도 1-hop < 300ms, GraphRAG < 5s |
| Citation 무결성 | 모든 분석 출력은 doc_id/chunk_id로 원문 추적 가능해야 함 (필수) |
| 데이터 라이선스 | 1순위(공시·정부·특허·기업IR) 합법무료. 뉴스/커뮤니티는 신호용, **원문 재배포 금지** |
| 확장성 | 다회사 확장은 `corp_code` 데이터 추가만 (스키마 불변), 소스 추가는 `source_type` 확장 |
| 신뢰도 표기 | 문서마다 `credibility(high/mid/low)` 태그 노출 |

---

## 8. 구현 우선순위

| 단계 | 기능 | 데이터 |
|---|---|---|
| **P0** | F-01 관계지도 · F-03 KPI · F-05 근거피드 · F-12 검색 | document_unified · mention_daily · Neo4j Document/ABOUT/MENTIONS |
| **P1** | F-02 브리핑 · F-06 묻기 · F-07 렌즈 · F-09 발견 · F-10 drill-down · F-11 특허 | Keyword/Topic 추출 · polaris-doc-1024 · Patent(Google Patents) |
| **P2** | F-04 시그널 · F-08 경로탐색 · 커뮤니티 | alert_event · macro_series · 커뮤니티(법적검토) |

---

## 참고
- 데이터 모델 상세: `docs/ERD.md` (v2.1 freeze)
- 데모 화면: `_demo/service_main.html`, `_demo/workbench_v1.html`, `_demo/onepager.html`
- 추출 방식: Claude-direct (ADR 021)
