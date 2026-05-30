import { useState } from 'react'
import { useCompany } from '../company/CompanyContext'
import { useGraph } from '../api/hooks'
import { RELATION_GROUPS } from '../lib/relations'
import type { RelationGroup, Selection } from '../types'
import TopBar from '../workspace/TopBar'
import TrendBand from '../workspace/TrendBand'
import GraphToolbar from '../workspace/GraphToolbar'
import GraphCanvas from '../workspace/GraphCanvas'
import ContextPanel from '../workspace/ContextPanel'
import ActivityTimeline from '../workspace/ActivityTimeline'

const DEFAULT_GROUPS = new Set<RelationGroup>(['supply','compete','partner','invest','govern','dispute'])
// 런타임에 force-graph 가 link.source/target 을 노드 객체로 치환 → id 만 안전 추출
const idOf = (x: unknown): string =>
  typeof x === 'object' && x !== null ? (x as { id: string }).id : String(x)

// 인텔리전스 워크스페이스 — 트렌드 띠(질문) + 관계지도(답) 한 화면.
export default function Workspace() {
  const { company } = useCompany()
  const { data: graph } = useGraph(company.code)
  const [groups, setGroups] = useState<Set<RelationGroup>>(DEFAULT_GROUPS)
  const [minWeight, setMinWeight] = useState(1)
  const [selection, setSelection] = useState<Selection>(null)

  const toggleGroup = (g: RelationGroup) =>
    setGroups((prev) => {
      const next = new Set(prev)
      if (next.has(g)) next.delete(g)
      else next.add(g)
      return next
    })

  return (
    <div className="flex h-screen flex-col bg-slate-50 transition-colors dark:bg-slate-950">
      <TopBar />
      <TrendBand />
      <main className="relative flex flex-1 overflow-hidden">
        <div className="relative flex-1 min-w-0 overflow-hidden">
          <div className="absolute left-4 top-4 z-10">
            <GraphToolbar
              groups={groups}
              onToggleGroup={toggleGroup}
              minWeight={minWeight}
              onMinWeight={setMinWeight}
            />
          </div>
          <GraphCanvas
            data={graph ?? { nodes: [], links: [] }}
            activeGroups={groups}
            minWeight={minWeight}
            onSelectNode={(n) => setSelection({ kind: 'node', id: n.id, name: n.name })}
            onSelectEdge={(l) =>
              setSelection({
                kind: 'edge',
                source: idOf(l.source),
                target: idOf(l.target),
                group: l.group,
                weight: l.weight,
              })
            }
          />
          <ContextPanel selection={selection} onClose={() => setSelection(null)} />
        </div>
        <div className="w-96 flex-shrink-0 overflow-y-auto border-l border-slate-200 dark:border-slate-800">
          <ActivityTimeline />
        </div>
      </main>
    </div>
  )
}
