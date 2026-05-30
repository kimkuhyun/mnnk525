// 관계 변화 — 컴팩트 가로 칩 (최근 신규 위주). 브리핑 바로 아래 슬림 카드.
// GET /changes/{corp} -> ChangesData (백엔드 기본 최근 14일·근거2건↑·상위 정렬)

import { useChanges } from '../api/hooks'
import { useCompany } from '../company/CompanyContext'
import { GROUP_COLOR, GROUP_LABEL } from '../lib/relations'
import type { ChangeItem, RelationGroup } from '../types'

interface ChangesFeedProps {
  onSelectChange?: (item: ChangeItem) => void
}

export default function ChangesFeed({ onSelectChange }: ChangesFeedProps) {
  const { company } = useCompany()
  const { data, isLoading, isError } = useChanges(company.code)

  const newItems = (data?.newItems ?? []).slice(0, 8) // 최근 신규만 컴팩트하게
  const dropped = (data?.dropped ?? []).slice(0, 4)
  const latest = newItems[0]?.date

  return (
    <div className="rounded-xl border border-slate-200/80 bg-white dark:border-slate-800 dark:bg-slate-900 px-4 py-3 shadow-sm">
      <div className="flex items-center gap-2 mb-2.5">
        <span className="h-4 w-[3px] rounded-full bg-blue-500" />
        <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">관계 변화</span>
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
          신규
        </span>
        {latest && (
          <span className="ml-auto text-xs tabular-nums text-slate-400 dark:text-slate-500">최근 {latest}</span>
        )}
      </div>

      {isLoading ? (
        <p className="text-xs text-slate-400 dark:text-slate-500">불러오는 중...</p>
      ) : isError || (newItems.length === 0 && dropped.length === 0) ? (
        <p className="text-xs text-slate-400 dark:text-slate-500">최근 신규 관계 없음</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {newItems.map((item, idx) => {
            const color = GROUP_COLOR[item.group as RelationGroup] ?? '#94a3b8'
            const label = GROUP_LABEL[item.group as RelationGroup] ?? item.group
            const clickable = !!onSelectChange
            return (
              <span
                key={`n${idx}`}
                className={
                  'inline-flex items-center gap-1.5 rounded-full border border-slate-200/80 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/60 pl-1.5 pr-2.5 py-1 transition-colors' +
                  (clickable
                    ? ' cursor-pointer hover:border-slate-300 hover:bg-slate-100 dark:hover:border-slate-600 dark:hover:bg-slate-800'
                    : '')
                }
                title={`${label} · ${item.predicate} · 언급 ${item.evidenceCount}건${clickable ? ' (클릭하면 근거 열람)' : ''}`}
                onClick={clickable ? () => onSelectChange(item) : undefined}
              >
                <span className="h-2 w-2 flex-shrink-0 rounded-full" style={{ backgroundColor: color }} />
                <span className="max-w-[160px] truncate text-xs font-medium text-slate-700 dark:text-slate-200">
                  {item.target}
                </span>
                <span className="text-[11px] text-slate-400 dark:text-slate-500">{label}</span>
                <span className="text-[11px] tabular-nums text-slate-400 dark:text-slate-500">
                  {item.date.slice(5)}
                </span>
              </span>
            )
          })}
          {dropped.map((item, idx) => (
            <span
              key={`d${idx}`}
              className="inline-flex items-center gap-1.5 rounded-full border border-slate-200/80 px-2.5 py-1 opacity-70 dark:border-slate-700"
            >
              <span className="h-2 w-2 flex-shrink-0 rounded-full border border-slate-400 dark:border-slate-500" />
              <span className="max-w-[140px] truncate text-xs text-slate-500 line-through dark:text-slate-400">
                {item.target}
              </span>
              <span className="text-[11px] text-slate-400 dark:text-slate-500">소멸</span>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
