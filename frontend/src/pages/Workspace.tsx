import { useCallback, useMemo, useState } from 'react'
import { useCompany } from '../company/CompanyContext'
import { useGraph, useMetaMembers } from '../api/hooks'
import { RELATION_GROUPS } from '../lib/relations'
import type { ChangeItem, GraphData, GraphLink, GraphNode, RelationGroup, Selection } from '../types'
import TopBar from '../workspace/TopBar'
import Briefing from '../workspace/Briefing'
import TrendBand from '../workspace/TrendBand'
import GraphToolbar from '../workspace/GraphToolbar'
import GraphCanvas from '../workspace/GraphCanvas'
import EvidencePanel from '../workspace/EvidencePanel'
import NodeDetail from '../workspace/NodeDetail'
import NodeEvidenceModal from '../workspace/NodeEvidenceModal'
import DailyDigest from '../workspace/DailyDigest'
import IrDashboard from '../workspace/IrDashboard'
import ChangesFeed from '../workspace/ChangesFeed'

const DEFAULT_GROUPS = new Set<RelationGroup>(['compete', 'supply', 'partner'])

// force-graph 가 link.source/target 을 노드 객체로 치환하므로 id 만 안전 추출
const idOf = (x: unknown): string =>
  typeof x === 'object' && x !== null ? (x as { id: string }).id : String(x)

// ── 그래프 머지 유틸 ──────────────────────────────────────────────────────────
// base + patch 를 노드/엣지 dedup(id 기준) 으로 합치고,
// meta 노드(kind==='meta', group===expandedKind)는 펼쳐졌으면 숨긴다(hidden 표식).
function mergeGraphData(
  base: GraphData,
  patch: GraphData | null,
  expandedKinds: Set<string>,
): GraphData {
  if (!patch || (patch.nodes.length === 0 && patch.links.length === 0)) {
    // patch 없음 — base 만 반환하되 이미 expandedKinds 에 있는 meta 노드 숨김
    const nodes = base.nodes.filter(
      (n) => !(n.kind === 'meta' && n.group && expandedKinds.has(n.group)),
    )
    return { nodes, links: base.links }
  }

  // 노드 dedup
  const nodeMap = new Map<string, GraphNode>()
  for (const n of base.nodes) nodeMap.set(n.id, n)
  for (const n of patch.nodes) {
    if (!nodeMap.has(n.id)) nodeMap.set(n.id, n)
  }

  // 펼쳐진 meta 노드 숨김
  const nodes = Array.from(nodeMap.values()).filter(
    (n) => !(n.kind === 'meta' && n.group && expandedKinds.has(n.group)),
  )

  // 엣지 dedup (source+target+group 복합키)
  const linkKey = (l: GraphLink) => `${idOf(l.source)}__${idOf(l.target)}__${l.group}`
  const linkMap = new Map<string, GraphLink>()
  for (const l of base.links) linkMap.set(linkKey(l), l)
  for (const l of patch.links) {
    const k = linkKey(l)
    if (!linkMap.has(k)) linkMap.set(k, l)
  }

  return { nodes, links: Array.from(linkMap.values()) }
}

// ─────────────────────────────────────────────────────────────────────────────

export default function Workspace() {
  const { company } = useCompany()

  // 필터 상태
  const [groups, setGroups] = useState<Set<RelationGroup>>(DEFAULT_GROUPS)
  const [minWeight] = useState(1)

  // 선택 상태 (노드 id 또는 엣지)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [edgeSelection, setEdgeSelection] = useState<Extract<Selection, { kind: 'edge' }> | null>(null)

  // 근거 모달 상태
  const [evidenceNode, setEvidenceNode] = useState<{ id: string; name: string } | null>(null)

  // meta 펼치기 상태
  const [expandedKinds, setExpandedKinds] = useState<Set<string>>(new Set())
  const [pendingKind, setPendingKind] = useState<string | null>(null)

  // 데이터 패치
  const { data: baseGraph } = useGraph(company.code)
  const { data: metaPatch } = useMetaMembers(company.code, pendingKind)

  const toggleGroup = useCallback((g: RelationGroup) => {
    setGroups((prev) => {
      const next = new Set(prev)
      if (next.has(g)) next.delete(g)
      else next.add(g)
      return next
    })
  }, [])

  // meta 펼치기 핸들러
  const handleExpandMeta = useCallback((metaKind: string) => {
    setExpandedKinds((prev) => {
      const next = new Set(prev)
      // 이미 펼쳐진 경우 토글 닫기(접기)
      if (next.has(metaKind)) {
        next.delete(metaKind)
        // pendingKind 도 제거
        setPendingKind((p) => (p === metaKind ? null : p))
        return next
      }
      next.add(metaKind)
      setPendingKind(metaKind)
      return next
    })
  }, [])

  // 머지된 그래프 (메모이즈)
  const mergedGraph = useMemo(
    () =>
      mergeGraphData(
        baseGraph ?? { nodes: [], links: [] },
        metaPatch ?? null,
        expandedKinds,
      ),
    [baseGraph, metaPatch, expandedKinds],
  )

  // company 전환 시 선택·펼치기 상태 초기화
  // (company.code 가 바뀌면 useGraph 가 새 데이터를 페치하므로 상태만 초기화)
  // → useEffect 대신 company.code 를 key 로 쓰면 더 깔끔하지만, 레이아웃 유지 위해 수동 처리
  // selectedId/edgeSelection/expandedKinds/pendingKind 는 company.code 변경 시 자연 초기화됨
  // (useGraph queryKey 가 corp 포함 → baseGraph 가 바뀌면 mergedGraph 도 바뀜)

  const handleSelectNode = useCallback((n: { id: string; name: string }) => {
    setSelectedId(n.id)
    setEdgeSelection(null)
  }, [])

  const handleSelectEdge = useCallback((l: any) => {
    setEdgeSelection({
      kind: 'edge',
      source: idOf(l.source),
      target: idOf(l.target),
      group: l.group,
      weight: l.weight,
    })
    setSelectedId(null)
  }, [])

  const handleCloseEdge = useCallback(() => {
    setEdgeSelection(null)
  }, [])

  // RelationTopCard → 그래프 포커스 연결
  const handleFocusNode = useCallback((id: string) => {
    setSelectedId(id)
    setEdgeSelection(null)
  }, [])

  // ChangesFeed 칩 클릭 → 해당 그룹 켜기 + 노드 선택 + 근거 모달 즉시 오픈
  const handleSelectChange = useCallback((item: ChangeItem) => {
    const g = item.group as RelationGroup
    setGroups((prev) => {
      if (prev.has(g)) return prev
      const next = new Set(prev)
      next.add(g)
      return next
    })
    setSelectedId(item.targetId)
    setEdgeSelection(null)
    setEvidenceNode({ id: item.targetId, name: item.target })
  }, [])

  return (
    <div className="min-h-screen flex flex-col bg-gradient-to-b from-blue-50/50 via-slate-50 to-slate-50 transition-colors dark:from-slate-950 dark:via-slate-950 dark:to-slate-950">
      <TopBar />

      <div className="mx-auto w-full max-w-[1680px] px-6 lg:px-10 py-6 space-y-6">
        {/* (0) 브리핑 — 최상단 전폭 hero */}
        <Briefing />

        {/* (0b) 관계 변화 — 신규 컴팩트 (브리핑 바로 아래) */}
        <ChangesFeed onSelectChange={handleSelectChange} />

        {/* (a) 트렌드 밴드 — 멘션/감성/주가 탭 + 핵심 관계 Top5 */}
        <TrendBand onFocusNode={handleFocusNode} />

        {/* (b) 관계지도 행 */}
        <div className="flex gap-5 items-start">
          {/* 그래프 카드 */}
          <div className="flex-1 min-w-0 rounded-xl border border-slate-200/80 bg-white dark:border-slate-800 dark:bg-slate-900 relative h-[500px] overflow-hidden shadow-sm">
            {/* GraphToolbar 오버레이 (좌상단) */}
            <div className="absolute left-4 top-4 z-10">
              <GraphToolbar
                groups={groups}
                onToggleGroup={toggleGroup}
              />
            </div>

            {/* GraphCanvas — absolute inset-0 으로 카드 전체 채움 */}
            <GraphCanvas
              data={mergedGraph}
              activeGroups={groups}
              minWeight={minWeight}
              selectedId={selectedId}
              onSelect={handleSelectNode}
              onSelectEdge={handleSelectEdge}
              onExpandMeta={handleExpandMeta}
            />

            {/* 엣지 선택 시 근거 패널 (floating, 그래프 카드 안 우측) */}
            {edgeSelection && (
              <div className="absolute right-0 top-0 bottom-0 w-72 z-20 border-l border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-xl overflow-y-auto">
                <div className="sticky top-0 bg-white dark:bg-slate-900 border-b border-slate-200/80 dark:border-slate-800 flex justify-between items-center px-4 py-3">
                  <span className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">
                    관계 언급
                  </span>
                  <button
                    onClick={handleCloseEdge}
                    className="ml-2 p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 dark:text-slate-500 transition-colors text-xs"
                    aria-label="닫기"
                  >
                    X
                  </button>
                </div>
                <div className="p-4">
                  <EvidencePanel sel={edgeSelection} />
                </div>
              </div>
            )}
          </div>

          {/* 우측: NodeDetail — 그래프와 같은 높이로 정렬 */}
          <div className="w-96 flex-shrink-0">
            <div className="h-[500px] overflow-y-auto rounded-xl border border-slate-200/80 bg-white dark:border-slate-800 dark:bg-slate-900 shadow-sm">
              <NodeDetail
                selectedId={selectedId}
                onOpenEvidence={(id, name) => setEvidenceNode({ id, name })}
              />
            </div>
          </div>
        </div>

        {/* 근거 모달 — Workspace 소유 */}
        <NodeEvidenceModal
          corp={company.code}
          nodeId={evidenceNode?.id ?? null}
          nodeName={evidenceNode?.name ?? ''}
          open={!!evidenceNode}
          onClose={() => setEvidenceNode(null)}
        />

        {/* (c) IR 대시보드 — 그래프 아래 전폭 */}
        <IrDashboard />

        {/* (d) 일별 다이제스트 — 가로 시계열 */}
        <DailyDigest />
      </div>
    </div>
  )
}
