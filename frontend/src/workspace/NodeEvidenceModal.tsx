import { useState } from 'react'
import { ExternalLink } from 'lucide-react'
import Modal from '../components/Modal'
import { useNodeEvidence } from '../api/hooks'
import { GROUP_COLOR, GROUP_LABEL } from '../lib/relations'
import type { RelationGroup } from '../types'

function formatAmount(raw: string): string {
  const n = Number(raw.replace(/[^0-9.]/g, ''))
  if (Number.isNaN(n) || n === 0) return raw
  if (n >= 1e12) return (n / 1e12).toLocaleString('ko-KR', { maximumFractionDigits: 1 }) + '조'
  if (n >= 1e8) return (n / 1e8).toLocaleString('ko-KR', { maximumFractionDigits: 1 }) + '억'
  return n.toLocaleString('ko-KR')
}

interface Props {
  corp: string
  nodeId: string | null
  nodeName: string
  open: boolean
  onClose: () => void
}

export default function NodeEvidenceModal({ corp, nodeId, nodeName, open, onClose }: Props) {
  const { data, isLoading, isError } = useNodeEvidence(corp, open ? nodeId : null)
  const [selectedGroup, setSelectedGroup] = useState<string>('all')

  // 등장하는 group 목록 추출
  const groups = data
    ? Array.from(new Set(data.edges.map((e) => e.group)))
    : []

  // group별 docs 합계
  const groupDocCount = (group: string) =>
    data ? data.edges.filter((e) => e.group === group).reduce((s, e) => s + e.docs.length, 0) : 0

  // 표시할 edges
  const visibleEdges = data
    ? selectedGroup === 'all'
      ? data.edges
      : data.edges.filter((e) => e.group === selectedGroup)
    : []

  // group 변경 시 칩 선택
  const handleChipClick = (g: string) => {
    setSelectedGroup(g)
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`${nodeName} — 관계`}
    >
      {isLoading ? (
        <p className="text-xs text-slate-400 dark:text-slate-500">불러오는 중...</p>
      ) : isError ? (
        <p className="text-xs text-slate-400 dark:text-slate-500">데이터를 불러오지 못했습니다</p>
      ) : !data || data.edges.length === 0 ? (
        <p className="text-xs text-slate-400 dark:text-slate-500">근거 데이터가 없습니다</p>
      ) : (
        <div className="flex flex-col gap-5">
          {/* 그룹 필터 칩바 */}
          <div className="flex flex-wrap gap-2">
            {/* 전체 칩 */}
            <button
              onClick={() => handleChipClick('all')}
              className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium border transition-colors ${
                selectedGroup === 'all'
                  ? 'border-slate-400 bg-slate-100 dark:border-slate-500 dark:bg-slate-800 text-slate-700 dark:text-slate-200'
                  : 'border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-600'
              }`}
            >
              전체
              <span className="tabular-nums text-slate-400 dark:text-slate-500">
                {data.edges.reduce((s, e) => s + e.docs.length, 0)}
              </span>
            </button>
            {groups.map((g) => {
              const color = GROUP_COLOR[g as RelationGroup] ?? '#94a3b8'
              const label = GROUP_LABEL[g as RelationGroup] ?? g
              const count = groupDocCount(g)
              const active = selectedGroup === g
              return (
                <button
                  key={g}
                  onClick={() => handleChipClick(g)}
                  className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium border transition-colors ${
                    active
                      ? 'border-slate-400 bg-slate-100 dark:border-slate-500 dark:bg-slate-800 text-slate-700 dark:text-slate-200'
                      : 'border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-600'
                  }`}
                >
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ backgroundColor: color }}
                  />
                  {label}
                  <span className="tabular-nums text-slate-400 dark:text-slate-500">{count}</span>
                </button>
              )
            })}
          </div>

          {/* 섹션 목록 */}
          <div className="flex flex-col gap-6">
            {visibleEdges.map((edge, idx) => {
              const color = GROUP_COLOR[edge.group as RelationGroup] ?? '#94a3b8'
              const groupLabel = GROUP_LABEL[edge.group as RelationGroup] ?? edge.group
              return (
                <div key={idx}>
                  {/* 섹션 헤더 */}
                  <div className="flex items-center gap-2 mb-3 flex-wrap">
                    <div
                      className="h-4 w-[3px] rounded-full shrink-0"
                      style={{ backgroundColor: color }}
                    />
                    <span className="text-xs font-semibold text-slate-700 dark:text-slate-200">
                      {groupLabel}
                    </span>
                    <span className="text-xs text-slate-500 dark:text-slate-400">
                      {edge.predicate}
                      {!edge.directed ? ' (양방향)' : ''}
                    </span>
                    {/* 출처 뱃지 */}
                    {edge.source === 'dart' ? (
                      <span className="rounded-full px-2 py-0.5 text-[11px] font-medium bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400">
                        공시·사실
                      </span>
                    ) : (
                      <span className="rounded-full px-2 py-0.5 text-[11px] font-medium bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                        언급
                      </span>
                    )}
                    {/* dart 엣지는 지분·목적·금액·취득일 표기, news 엣지는 '언급 N건' */}
                    {edge.source === 'dart' ? (
                      <span className="ml-auto flex items-center gap-0 flex-wrap tabular-nums text-xs text-slate-600 dark:text-slate-300">
                        {[
                          edge.stake != null
                            ? `지분 ${edge.stake >= 1 ? edge.stake.toFixed(1) : edge.stake.toFixed(2)}%`
                            : null,
                          edge.purpose ? `목적 ${edge.purpose}` : null,
                          edge.amount ? `금액 ${formatAmount(edge.amount)}` : null,
                          edge.firstAcq ? `취득 ${edge.firstAcq}` : null,
                        ]
                          .filter(Boolean)
                          .map((part, i, arr) => (
                            <span key={i}>
                              {part}
                              {i < arr.length - 1 && (
                                <span className="mx-1 text-slate-300 dark:text-slate-600">·</span>
                              )}
                            </span>
                          ))}
                      </span>
                    ) : (
                      <span className="ml-auto text-xs tabular-nums text-slate-400 dark:text-slate-500 shrink-0">
                        언급 {edge.evidenceCount}건
                      </span>
                    )}
                    {edge.firstDate && edge.lastDate && (
                      <span className="text-xs tabular-nums text-slate-400 dark:text-slate-500 shrink-0">
                        {edge.firstDate} ~ {edge.lastDate}
                      </span>
                    )}
                  </div>

                  {/* docs 리스트 */}
                  {edge.docs.length === 0 ? (
                    <p className="text-xs text-slate-400 dark:text-slate-500">문서 없음</p>
                  ) : (
                    <ul className="space-y-3">
                      {edge.docs.map((doc) => (
                        <li
                          key={doc.docId}
                          className="border-b border-slate-100 dark:border-slate-800 pb-3 last:border-b-0 last:pb-0"
                        >
                          <div className="flex items-center gap-2 mb-1 flex-wrap">
                            {/* docType 배지 */}
                            <span
                              className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                                doc.docType === 'disclosure'
                                  ? 'bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400'
                                  : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
                              }`}
                            >
                              {doc.docType === 'disclosure' ? '공시' : '기사'}
                            </span>
                            <span className="text-xs tabular-nums text-slate-400 dark:text-slate-500">
                              {doc.date}
                            </span>
                          </div>
                          <a
                            href={doc.url}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-start gap-1 text-sm font-medium text-slate-700 dark:text-slate-200 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                          >
                            <span>{doc.title}</span>
                            <ExternalLink size={13} className="mt-0.5 shrink-0" />
                          </a>
                          {doc.publisher && (
                            <div className="mt-0.5 text-xs text-slate-400 dark:text-slate-500">
                              {doc.publisher}
                            </div>
                          )}
                          {doc.snippet && (
                            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 line-clamp-2 leading-relaxed">
                              {doc.snippet}
                            </p>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </Modal>
  )
}
