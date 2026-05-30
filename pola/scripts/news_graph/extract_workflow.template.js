// 뉴스 그래프 추출 Workflow (Claude Code 의 Workflow 툴로 실행 — 어시스턴트가 이 대화에서 구동).
//
// 사용법:
//   1) export_batches.py 가 출력한 DIR, N 을 아래 두 상수에 채운다.
//   2) 전체 추출은 model:'sonnet' (비용), 품질 의심 시 30건만 'opus' 로 먼저 샘플.
//   3) Workflow 완료 → .output 파일을 assemble.py 로 정제 → graph_load.
//
// 산출(.output) 구조: { result: { docs:[{doc_id,entities,relations}], ok_batches, ... } }
// 정합 키: doc_id (document_unified / Qdrant / Neo4j Document 와 동일)

export const meta = {
  name: 'news-graph-extract',
  description: '뉴스 본문 → 엔티티+관계 추출 (배치별 Claude)',
  phases: [{ title: 'extract', detail: '배치별 추출' }],
}

// ── 회사마다 교체 (export_batches.py 출력값) ─────────────────────────
const DIR = "C:\\Users\\kimkuhyn\\Desktop\\mnnk525\\pola\\scripts\\news_graph\\00164779"
const N = 0   // ← export_batches.py 의 N
const MODEL = 'sonnet'   // 전체. 샘플 품질검증은 'opus'
// ────────────────────────────────────────────────────────────────────

const PREDICATES = ["SUPPLIES","CUSTOMER_OF","PARTNERS_WITH","COMPETES_WITH","INVESTS_IN","ACQUIRES","JV_WITH","DEVELOPS","EXECUTIVE_OF","LICENSES","LITIGATION"]

const SCHEMA = {
  type: "object",
  properties: {
    results: {
      type: "array",
      items: {
        type: "object",
        properties: {
          doc_id: { type: "string" },
          entities: {
            type: "array",
            items: {
              type: "object",
              properties: {
                text: { type: "string" },
                type: { type: "string", enum: ["Organization","Person","Product","Technology"] },
              },
              required: ["text","type"],
            },
          },
          relations: {
            type: "array",
            items: {
              type: "object",
              properties: {
                subject: { type: "string" },
                predicate: { type: "string", enum: PREDICATES },
                object: { type: "string" },
                evidence: { type: "string" },
                confidence: { type: "number" },
              },
              required: ["subject","predicate","object","confidence"],
            },
          },
        },
        required: ["doc_id","entities","relations"],
      },
    },
  },
  required: ["results"],
}

const prompt = (p) => `당신은 반도체 기업 관계 인텔리전스 분석가다. 뉴스 기사에서 그래프 DB에 넣을 (1) 핵심 엔티티와 (2) 엔티티 사이의 관계를 추출한다.

먼저 Read 도구로 이 파일을 읽어라: ${p}
파일은 JSON 배열이고 각 원소는 {doc_id, date, title, body} 형식이다. 배열의 모든 기사를 처리한다.

[엔티티] type 은 Organization / Person / Product / Technology 중 하나.
- 기업·기관=Organization, 인물=Person, 제품·브랜드=Product, 기술·공정=Technology
- 본문 표기 그대로 추출 (정규화·약어풀이 금지. 예 "HSB"→"HSB").
- 반도체·전자·IT 비즈니스와 무관한 정치 엔티티(정당, 정치인, 국회 등)는 제외.
- 단, 기업 임원·경영진은 Person 으로 포함.
- 발행사 자기홍보(전자신문·한국경제 자체 서비스/상품)는 제외.

[관계] subject, predicate, object. subject/object 는 반드시 위 entities 의 text 와 정확히 동일하게.
predicate 는 다음에서만: SUPPLIES, CUSTOMER_OF, PARTNERS_WITH, COMPETES_WITH, INVESTS_IN,
  ACQUIRES, JV_WITH, DEVELOPS, EXECUTIVE_OF(반드시 인물→기업), LICENSES, LITIGATION

[규칙]
- 관계는 본문에 명시적 근거가 있을 때만. 추측·일반상식 금지.
- evidence 에 근거 본문 구절 25자 이내. confidence 0.0~1.0 (명확 0.9+, 암시 0.5~0.7).
- 크롤 노이즈(본문 중간 끼어든 의미없는 숫자)는 무시.
- 관계 없는 기사는 relations 빈 배열, entities 는 항상 추출.

각 기사마다 {doc_id, entities, relations} 를 만들어 results 배열로 반환하라.`

const paths = Array.from({ length: N }, (_, i) => `${DIR}\\b${String(i).padStart(4, '0')}.json`)
log(`뉴스 추출: ${N} 배치 (${MODEL})`)
phase('extract')
const out = await parallel(paths.map((p) => () =>
  agent(prompt(p), { label: `extract:${p.split(/[\\/]/).pop()}`, phase: 'extract', model: MODEL, schema: SCHEMA })
))
const batches = out.filter(Boolean)
const flat = batches.flatMap((b) => b.results || [])
log(`완료: ${batches.length}/${N} 배치 / ${flat.length} 문서`)
return {
  docs: flat, ok_batches: batches.length, total_batches: N,
  doc_count: flat.length,
  entity_count: flat.reduce((s, r) => s + (r.entities?.length || 0), 0),
  relation_count: flat.reduce((s, r) => s + (r.relations?.length || 0), 0),
}
