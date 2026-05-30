import { useQuery } from '@tanstack/react-query'
import { api } from './client'
import type {
  GraphData, TrendData, CompanyProfile, EvidenceItem, NewsItem, Selection,
  ActivityItem, KeywordItem, SentimentPoint,
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

// 연관어 Top10
export function useKeywords(corp: string) {
  return useQuery({
    queryKey: ['keywords', corp],
    queryFn: ({ signal }) => api<KeywordItem[]>(`/keywords/${corp}`, { signal }),
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
