// 백엔드 응답 계약(contract). 백엔드는 이 형태에만 맞추면 화면이 그대로 살아난다.

export interface Company {
  code: string // corp_code
  name: string
}

// 관계 6그룹 키
export type RelationGroup =
  | 'supply' // 공급망
  | 'compete' // 경쟁
  | 'partner' // 협력
  | 'invest' // 투자·인수
  | 'govern' // 지배구조
  | 'dispute' // 분쟁

// 노드 종류
export type NodeKind = 'seed' | 'org' | 'news_entity' | 'person' | 'product' | 'meta'

// ── 관계지도 그래프 ──
export interface GraphNode {
  id: string // corp_code 또는 ext_id
  name: string
  seed?: boolean // 조회한 중심 회사면 true (대형 별로 강조)
  degree?: number // 연결 수 → 노드 크기
  group?: RelationGroup // 중심과의 대표 관계그룹 → 노드 색
  logo?: string // 로고 이미지 URL (있으면 노드에 이미지, 없으면 라벨)
  kind?: NodeKind // 노드 종류
  count?: number // meta 노드일 때 접힌 멤버 수, 아니면 undefined
}

export interface GraphLink {
  source: string
  target: string
  group: RelationGroup
  weight: number // 근거 기사 수 → 엣지 두께
  directed: boolean
}

export interface GraphData {
  nodes: GraphNode[]
  links: GraphLink[]
}

// ── 트렌드(대시보드 상단 띠) ──
export interface MentionPoint {
  date: string
  count: number
}

export interface RelationTopItem {
  group: RelationGroup
  target: string
  weight: number
}

export interface TrendData {
  mentions: MentionPoint[]
  relationTop: RelationTopItem[]
  sentiment: null // 향후 — 지금은 자리만
  keywords: null // 향후 — 지금은 자리만
}

// ── 회사 프로파일(노드 클릭 드릴다운) ──
export interface NewsItem {
  docId: string
  title: string
  date: string
  url: string
  publisher?: string
}

export interface Shareholder {
  name: string
  stake?: number
}

export interface StockSummary {
  lastClose: number
  changePct?: number
  asOf: string
  spark: number[]
}

export interface DisputeItem {
  target: string
  evidenceCount: number
}

export interface CompanyProfile {
  code: string
  name: string
  summary?: string
  finance: { label: string; value: string }[]
  execs: { name: string; position?: string }[]
  subsidiaries: { name: string; stake?: number }[]
  products: string[]
  recentNews: NewsItem[]
  shareholders: Shareholder[]
  stock?: StockSummary
  overview: { label: string; value: string }[]
  disputes: DisputeItem[]
}

// ── 행보 타임라인(기업 활동 추적 — 뉴스리스트 대체) ──
export interface ActivityItem {
  date: string
  group: RelationGroup
  predicate: string // 관계 타입(원본)
  target: string // 상대 (회사/제품/인물)
  evidenceCount: number
  docId?: string // 대표 근거 기사
}

// ── 감성 추이 ──
export interface SentimentPoint {
  date: string
  pos: number
  neg: number
  neu: number
}

// ── 근거(엣지 클릭) ──
export interface EvidenceItem {
  docId: string
  title: string
  date: string
  url: string
  publisher?: string
  snippet?: string
}

// ── 노드 상세 (클릭 드릴다운 — /node/{corp}/{node}) ──
export interface NodeRelation {
  group: RelationGroup
  predicate: string // 관계 타입 원문
  target: string // 상대 노드 id 또는 이름
  evidenceCount: number
  directed: boolean
  source?: 'news' | 'dart' // 기본 'news'
}

export interface NodeDetail {
  id: string
  name: string
  kind: NodeKind
  isSeed: boolean
  relations: NodeRelation[]
  evidence: EvidenceItem[]
  profile: CompanyProfile | null
}

// 우측 패널이 무엇을 보여줄지
export type Selection =
  | { kind: 'node'; id: string; name: string }
  | { kind: 'edge'; source: string; target: string; group: RelationGroup; weight: number }
  | null

// ── 신규 카드 API ──
export interface StockPoint {
  date: string
  close: number
  changePct?: number
  volume?: number
}

export interface RelationTop {
  nodeId: string
  target: string
  group: RelationGroup
  predicate: string
  evidenceCount: number
}

export interface DailyDigestItem {
  date: string
  summary: string
  articleCount: number
  headlines: NewsItem[]
}

export interface FinancialPoint {
  indicator: string
  year: number
  value: number
  fsDiv: string
  period?: string // 'FY'|'1Q'|'2Q'|'3Q'|'4Q', 기본 'FY'
}

export interface OwnershipItem {
  name: string
  stake?: number
  kind: 'subsidiary' | 'shareholder'
}

export interface MacroPoint {
  name: string
  value: string
  unit?: string
  asOf?: string
  source?: string
}

// ── 브리핑 ──
export interface DisclosureItem {
  date: string
  docType: string
  title: string
  summary?: string
  rcept?: string
}

export interface BriefingData {
  date?: string
  summary?: string
  articleCount: number
  headlines: NewsItem[]
  disclosures: DisclosureItem[]
}

// ── 관계 변화 감지 (GET /changes/{corp}?days=60) ──
export interface ChangeItem {
  group: string
  predicate: string
  target: string
  status: 'new' | 'dropped'
  date: string
  evidenceCount: number
  targetId: string // 상대 노드 id
}

export interface ChangesData {
  newItems: ChangeItem[]
  dropped: ChangeItem[]
}

// ── 노드 근거 드릴다운 (GET /api/node-evidence/{corp}/{node}) ──
export interface EvidenceDoc {
  docId: string
  docType: 'news' | 'disclosure'
  title: string
  date: string
  url: string
  publisher?: string
  snippet: string
}

export interface EdgeEvidence {
  group: string
  predicate: string
  directed: boolean
  evidenceCount: number
  firstDate: string
  lastDate: string
  docs: EvidenceDoc[]
  source?: 'news' | 'dart' // 기본 'news'
  stake?: number
  purpose?: string
  amount?: string
  firstAcq?: string
}

export interface NodeEvidence {
  id: string
  name: string
  kind: string
  edges: EdgeEvidence[]
}

// ── IR 보고서 (GET /ir-reports/{corp}) ──
export interface IrReport {
  rceptNo: string
  corpCode: string
  docType: string
  date: string
  title: string
  summary: string
  source: string // 'dart'|'news' 등
}
