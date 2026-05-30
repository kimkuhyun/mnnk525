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

// ── 관계지도 그래프 ──
export interface GraphNode {
  id: string // corp_code 또는 ext_id
  name: string
  seed?: boolean // 조회한 중심 회사면 true (대형 별로 강조)
  degree?: number // 연결 수 → 노드 크기
  group?: RelationGroup // 중심과의 대표 관계그룹 → 노드 색
  logo?: string // 로고 이미지 URL (있으면 노드에 이미지, 없으면 라벨)
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

export interface CompanyProfile {
  code: string
  name: string
  summary?: string
  finance: { label: string; value: string }[]
  execs: { name: string; position?: string }[]
  subsidiaries: { name: string; stake?: number }[]
  products: string[]
  recentNews: NewsItem[]
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

// ── 연관어 ──
export interface KeywordItem {
  term: string
  freq: number
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

// 우측 패널이 무엇을 보여줄지
export type Selection =
  | { kind: 'node'; id: string; name: string }
  | { kind: 'edge'; source: string; target: string; group: RelationGroup; weight: number }
  | null
