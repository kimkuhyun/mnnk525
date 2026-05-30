import { useQuery } from '@tanstack/react-query'
import { api } from './client'
import type {
  GraphData, TrendData, CompanyProfile, EvidenceItem, NewsItem, Selection,
  ActivityItem, SentimentPoint, NodeDetail,
  StockPoint, RelationTop, DailyDigestItem,
  FinancialPoint, OwnershipItem, MacroPoint,
  BriefingData, ChangesData, NodeEvidence, IrReport,
} from '../types'

// 백엔드 하나씩 연결: 아래 엔드포인트를 순서대로 구현하면 화면이 차례로 살아난다.
// 연결 전에는 query 가 실패 → 컴포넌트는 isError/빈배열로 빈 상태를 보여준다(목 데이터 금지).

const EMPTY_GRAPH: GraphData = { nodes: [], links: [] }

export function useGraph(corp: string) {
  return useQuery({
    queryKey: ['graph', corp],
    queryFn: ({ signal }) => api<GraphData>(`/graph/${corp}`, { signal }),
    placeholderData: EMPTY_GRAPH,
    retry: false,
  })
}

export function useTrend(corp: string) {
  return useQuery({
    queryKey: ['trend', corp],
    queryFn: ({ signal }) => api<TrendData>(`/dashboard/${corp}`, { signal }),
    retry: false,
  })
}

export function useProfile(corp: string | null) {
  return useQuery({
    queryKey: ['profile', corp],
    queryFn: ({ signal }) => api<CompanyProfile>(`/company/${corp}`, { signal }),
    enabled: !!corp,
    retry: false,
  })
}

// 날짜순 뉴스 피드 (그래프와 분리된 별도 뷰)
export function useNews(corp: string) {
  return useQuery({
    queryKey: ['news', corp],
    queryFn: ({ signal }) => api<NewsItem[]>(`/news/${corp}`, { signal }),
    placeholderData: [],
    retry: false,
  })
}

// 기업 행보 타임라인 (활동 추적)
export function useActivity(corp: string) {
  return useQuery({
    queryKey: ['activity', corp],
    queryFn: ({ signal }) => api<ActivityItem[]>(`/activity/${corp}`, { signal }),
    placeholderData: [],
    retry: false,
  })
}

// 감성 추이
export function useSentiment(corp: string) {
  return useQuery({
    queryKey: ['sentiment', corp],
    queryFn: ({ signal }) => api<SentimentPoint[]>(`/sentiment/${corp}`, { signal }),
    placeholderData: [],
    retry: false,
  })
}

// 엣지 선택 시 근거 기사
export function useEvidence(sel: Extract<Selection, { kind: 'edge' }> | null) {
  return useQuery({
    queryKey: ['evidence', sel?.source, sel?.target, sel?.group],
    queryFn: ({ signal }) =>
      api<EvidenceItem[]>(
        `/evidence?source=${sel!.source}&target=${sel!.target}&group=${sel!.group}`,
        { signal },
      ),
    enabled: !!sel,
    retry: false,
  })
}

// 노드 클릭 드릴다운 — "이게 뭔지·왜 잡혔는지"
// node 가 null 이면 쿼리 비활성화
export function useNodeDetail(corp: string, node: string | null) {
  return useQuery({
    queryKey: ['node', corp, node],
    queryFn: ({ signal }) => api<NodeDetail>(`/node/${corp}/${node}`, { signal }),
    enabled: !!node,
    retry: false,
  })
}

// meta 노드 펼치기 — collapse 된 멤버 노드 + center 연결 엣지 반환
// kind 가 null 이면 쿼리 비활성화
export function useMetaMembers(corp: string, kind: string | null) {
  return useQuery({
    queryKey: ['meta', corp, kind],
    queryFn: ({ signal }) => api<GraphData>(`/graph/meta/${corp}/${kind}`, { signal }),
    enabled: !!kind,
    retry: false,
  })
}

// meta 노드 펼치기 — 명령형 헬퍼 (useMetaMembers 와 동일 엔드포인트, 훅 없이 직접 fetch 할 때)
export async function fetchMetaMembers(corp: string, kind: string): Promise<GraphData> {
  return api<GraphData>(`/graph/meta/${corp}/${kind}`)
}

// 주가 시계열
export function useStock(corp: string) {
  return useQuery({
    queryKey: ['stock', corp],
    queryFn: ({ signal }) => api<StockPoint[]>(`/stock/${corp}`, { signal }),
    placeholderData: [],
    retry: false,
  })
}

// 관계 상위 5건
export function useRelationTop(corp: string) {
  return useQuery({
    queryKey: ['relation-top', corp],
    queryFn: ({ signal }) => api<RelationTop[]>(`/relation-top/${corp}`, { signal }),
    placeholderData: [],
    retry: false,
  })
}

// 일별 다이제스트
export function useDailyDigest(corp: string) {
  return useQuery({
    queryKey: ['daily-digest', corp],
    queryFn: ({ signal }) => api<DailyDigestItem[]>(`/daily-digest/${corp}`, { signal }),
    placeholderData: [],
    retry: false,
  })
}

// 재무 지표 시계열 (CFS 우선, 연도별 또는 분기별)
export function useFinancials(corp: string, period: 'annual' | 'quarter' = 'annual') {
  return useQuery({
    queryKey: ['financials', corp, period],
    queryFn: ({ signal }) => api<FinancialPoint[]>(`/financials/${corp}?period=${period}`, { signal }),
    placeholderData: [],
    retry: false,
  })
}

// IR 보고서 목록 (DART 공시 등)
export function useIrReports(corp: string) {
  return useQuery({
    queryKey: ['ir-reports', corp],
    queryFn: ({ signal }) => api<IrReport[]>(`/ir-reports/${corp}`, { signal }),
    placeholderData: [],
    retry: false,
  })
}

// 지배구조 — 자회사/출자 + 대주주
export function useOwnership(corp: string) {
  return useQuery({
    queryKey: ['ownership', corp],
    queryFn: ({ signal }) => api<OwnershipItem[]>(`/ownership/${corp}`, { signal }),
    placeholderData: [],
    retry: false,
  })
}

// 큐레이션 거시지표 최신값 (corp 무관)
export function useMacro() {
  return useQuery({
    queryKey: ['macro'],
    queryFn: ({ signal }) => api<MacroPoint[]>(`/macro`, { signal }),
    placeholderData: [],
    retry: false,
  })
}

// 최신 브리핑 — news_daily_summary + 수시공시
export function useBriefing(corp: string) {
  return useQuery({
    queryKey: ['briefing', corp],
    queryFn: ({ signal }) => api<BriefingData>(`/briefing/${corp}`, { signal }),
    retry: false,
  })
}

// 관계 변화 감지 (GET /changes/{corp}?days=60)
export function useChanges(corp: string) {
  return useQuery({
    queryKey: ['changes', corp],
    queryFn: ({ signal }) => api<ChangesData>(`/changes/${corp}?days=60`, { signal }),
    retry: false,
  })
}

// 노드 근거 드릴다운 (GET /api/node-evidence/{corp}/{node})
export function useNodeEvidence(corp: string, nodeId: string | null) {
  return useQuery({
    queryKey: ['node-evidence', corp, nodeId],
    queryFn: ({ signal }) => api<NodeEvidence>(`/node-evidence/${corp}/${nodeId}`, { signal }),
    enabled: !!corp && !!nodeId,
    retry: false,
  })
}
