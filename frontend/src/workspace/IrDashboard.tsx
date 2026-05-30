// IR 대시보드 — 그래프 아래 전폭 (중심회사 company.code 기준)
// 재무연도추이 · 지분구조 · 임원/제품요약 · 거시배경 + "전체 재무제표 보기" 토글

import { useState } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { ChevronDown, ChevronUp, ExternalLink } from 'lucide-react'
import { useTheme } from '../theme/ThemeContext'
import { useCompany } from '../company/CompanyContext'
import { useFinancials, useOwnership, useProfile, useMacro, useIrReports } from '../api/hooks'
import type { FinancialPoint } from '../types'
import SectionLabel from '../components/SectionLabel'

// ── 재무 지표 표시 이름 매핑 ──────────────────────────────────────────────────
const INDICATOR_LABEL: Record<string, string> = {
  revenue: '매출',
  operating_income: '영업이익',
  net_income: '당기순이익',
  total_assets: '총자산',
  total_equity: '자본총계',
  // DART 기준 원문 키 대응
  '매출액': '매출',
  '영업이익': '영업이익',
  '당기순이익': '당기순이익',
}

// 헤드라인 3개 지표 (bar 색)
const HEADLINE_INDICATORS = ['revenue', '매출액', 'operating_income', '영업이익', 'net_income', '당기순이익']
const HEADLINE_COLORS = ['#5E9BD1', '#5FB39C', '#9B86CB']

// 표시할 3종 (정규화 키)
const BAR_DEFS: { key: string; label: string; color: string }[] = [
  { key: 'revenue', label: '매출', color: '#5E9BD1' },
  { key: 'operating_income', label: '영업이익', color: '#5FB39C' },
  { key: 'net_income', label: '당기순이익', color: '#9B86CB' },
]

// 원문 지표명 → 정규화 키
const NORM_KEY: Record<string, string> = {
  revenue: 'revenue',
  '매출액': 'revenue',
  operating_income: 'operating_income',
  '영업이익': 'operating_income',
  net_income: 'net_income',
  '당기순이익': 'net_income',
}

// 억원 단위 포맷
function fmtBillion(v: number) {
  const abs = Math.abs(v)
  if (abs >= 1_000_000_000_000) return `${(v / 1_000_000_000_000).toFixed(1)}조`
  if (abs >= 100_000_000) return `${(v / 100_000_000).toFixed(0)}억`
  return v.toLocaleString('ko-KR')
}

// FinancialPoint[] → { xKey, revenue, operating_income, net_income }[]
// annual: xKey = year(숫자)  /  quarter: xKey = '2024 1Q' 형태 문자열
function pivotFinancials(points: FinancialPoint[], mode: 'annual' | 'quarter' = 'annual') {
  if (mode === 'annual') {
    const map: Record<number, Record<string, number>> = {}
    for (const p of points) {
      const normKey = NORM_KEY[p.indicator]
      if (!normKey) continue
      if (!map[p.year]) map[p.year] = { year: p.year }
      map[p.year][normKey] = p.value
    }
    return Object.values(map).sort((a, b) => (a.year as number) - (b.year as number))
  } else {
    // 분기: xKey = '{year} {period}'
    const map: Record<string, Record<string, unknown>> = {}
    for (const p of points) {
      const normKey = NORM_KEY[p.indicator]
      if (!normKey) continue
      const periodLabel = p.period && p.period !== 'FY' ? p.period : 'FY'
      const xKey = `${p.year} ${periodLabel}`
      if (!map[xKey]) map[xKey] = { xKey, _year: p.year, _period: periodLabel }
      map[xKey][normKey] = p.value
    }
    // 정렬: 연도 오름차순, 같은 연도 내 1Q→2Q→3Q→4Q→FY
    const PERIOD_ORDER: Record<string, number> = { '1Q': 1, '2Q': 2, '3Q': 3, '4Q': 4, FY: 5 }
    return Object.values(map).sort((a, b) => {
      const ay = a._year as number, by = b._year as number
      if (ay !== by) return ay - by
      return (PERIOD_ORDER[a._period as string] ?? 9) - (PERIOD_ORDER[b._period as string] ?? 9)
    })
  }
}

// 전체 재무 테이블용: 지표 × 연도(또는 연+분기) 행렬
const PERIOD_ORDER_TABLE: Record<string, number> = { '1Q': 1, '2Q': 2, '3Q': 3, '4Q': 4, FY: 5 }

function buildFullTable(points: FinancialPoint[], mode: 'annual' | 'quarter' = 'annual') {
  const indicators = Array.from(new Set(points.map((p) => p.indicator)))

  if (mode === 'annual') {
    const colSet = Array.from(new Set(points.map((p) => p.year))).sort() as number[]
    const lookup: Record<string, Record<string, number>> = {}
    for (const p of points) {
      if (!lookup[p.indicator]) lookup[p.indicator] = {}
      lookup[p.indicator][String(p.year)] = p.value
    }
    return { cols: colSet.map(String), colLabels: colSet.map(String), indicators, lookup }
  } else {
    // 분기: 컬럼 키 = '{year} {period}'
    const colSet = Array.from(
      new Set(
        points.map((p) => {
          const periodLabel = p.period && p.period !== 'FY' ? p.period : 'FY'
          return `${p.year} ${periodLabel}`
        })
      )
    ).sort((a, b) => {
      const [ay, ap] = a.split(' ')
      const [by, bp] = b.split(' ')
      if (ay !== by) return Number(ay) - Number(by)
      return (PERIOD_ORDER_TABLE[ap] ?? 9) - (PERIOD_ORDER_TABLE[bp] ?? 9)
    })
    const lookup: Record<string, Record<string, number>> = {}
    for (const p of points) {
      const periodLabel = p.period && p.period !== 'FY' ? p.period : 'FY'
      const col = `${p.year} ${periodLabel}`
      if (!lookup[p.indicator]) lookup[p.indicator] = {}
      lookup[p.indicator][col] = p.value
    }
    return { cols: colSet, colLabels: colSet, indicators, lookup }
  }
}

const cardClass = 'rounded-xl border border-slate-200/80 bg-white dark:border-slate-800 dark:bg-slate-900 p-4 shadow-sm'

export default function IrDashboard() {
  const { theme } = useTheme()
  const { company } = useCompany()
  const isDark = theme === 'dark'

  const [showFullTable, setShowFullTable] = useState(false)
  const [period, setPeriod] = useState<'annual' | 'quarter'>('annual')
  const [expandedReports, setExpandedReports] = useState<Record<string, boolean>>({})

  const { data: financials = [] } = useFinancials(company.code, period)
  const { data: ownership = [] } = useOwnership(company.code)
  const { data: profile } = useProfile(company.code)
  const { data: macro = [] } = useMacro()
  const { data: irReports = [] } = useIrReports(company.code)

  const textMuted = isDark ? 'text-slate-400' : 'text-slate-500'
  const textMain = isDark ? 'text-slate-100' : 'text-slate-900'

  const barData = pivotFinancials(financials, period)
  const xKey = period === 'annual' ? 'year' : 'xKey'
  // 분기 차트는 최근 8개만(가독성). KPI/전체표는 barData 전체 사용.
  const chartData = period === 'quarter' ? barData.slice(-8) : barData

  // YAxis domain: 음수 값 존재 시 실제 [min,max] 타이트하게(8% 패딩), 양수 전용이면 0 기준
  const barAllValues = barData.flatMap((row) =>
    BAR_DEFS.map((b) => row[b.key] as number | undefined).filter((v): v is number => v != null)
  )
  const barDataMin = barAllValues.length > 0 ? Math.min(...barAllValues) : 0
  const hasNegative = barDataMin < 0
  // Recharts domain 함수 시그니처: (dataMin: number) => number
  const yDomainMin = hasNegative ? (v: number) => Math.floor(v * 1.08) : 0
  const yDomainMax = (v: number) => Math.ceil(v * 1.08)
  const subsidiaries = ownership.filter((o) => o.kind === 'subsidiary')
  const shareholders = ownership.filter((o) => o.kind === 'shareholder')
  const { cols, colLabels, indicators, lookup } = buildFullTable(financials, period)

  const tooltipStyle = {
    background: isDark ? '#1e293b' : '#fff',
    border: isDark ? '1px solid #334155' : '1px solid #e2e8f0',
    borderRadius: 8,
    fontSize: 11,
  }

  return (
    <div className="space-y-5">
      {/* 상단 그리드: 재무추이(2/4) + 지분구조(1/4) + 거시배경(1/4) */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-5">
        {/* 재무 연도 추이 — col-span-2 */}
        <div className={`${cardClass} lg:col-span-2`}>
          <div className="flex items-center justify-between mb-2.5">
            <SectionLabel>재무 연도 추이</SectionLabel>
            <div className="flex items-center gap-2">
              {/* 연간/분기 세그먼트 토글 */}
              <div className="flex rounded-md border border-slate-200 dark:border-slate-700 overflow-hidden text-[11px]">
                {(['annual', 'quarter'] as const).map((p) => (
                  <button
                    key={p}
                    className={`px-2 py-0.5 transition-colors ${
                      period === p
                        ? 'bg-slate-700 text-white dark:bg-slate-200 dark:text-slate-900'
                        : `${textMuted} hover:bg-slate-50 dark:hover:bg-slate-800`
                    }`}
                    onClick={() => setPeriod(p)}
                  >
                    {p === 'annual' ? '연간' : '분기'}
                  </button>
                ))}
              </div>
              <button
                className={`flex items-center gap-1 text-xs ${textMuted} hover:${textMain} transition-colors`}
                onClick={() => setShowFullTable((v) => !v)}
              >
                {showFullTable ? (
                  <>
                    <ChevronUp size={13} />
                    접기
                  </>
                ) : (
                  <>
                    <ChevronDown size={13} />
                    전체 재무제표 보기
                  </>
                )}
              </button>
            </div>
          </div>

          {/* 최신 기간 핵심 지표 — 큰 숫자 + 증감 */}
          {barData.length > 0 && (() => {
            const latest = barData[barData.length - 1]
            // 분기: 전년동기(4분기 전) 비교, 없으면 전분기. 연간: 전년.
            let prev: typeof latest | null = null
            let deltaLabel = '전년'
            if (period === 'quarter') {
              if (barData.length >= 5) { prev = barData[barData.length - 5]; deltaLabel = '전년동기' }
              else if (barData.length > 1) { prev = barData[barData.length - 2]; deltaLabel = '전분기' }
            } else {
              prev = barData.length > 1 ? barData[barData.length - 2] : null
            }
            return (
              <div className="grid grid-cols-3 gap-3 mb-4">
                {BAR_DEFS.map((b) => {
                  const cur = latest[b.key] as number | undefined
                  const pv = prev ? (prev[b.key] as number | undefined) : undefined
                  const yoy =
                    cur != null && pv != null && pv !== 0 ? ((cur - pv) / Math.abs(pv)) * 100 : null
                  return (
                    <div key={b.key}>
                      <div className="flex items-center gap-1.5">
                        <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: b.color }} />
                        <span className={`text-[11px] ${textMuted}`}>{b.label}</span>
                      </div>
                      <div className={`mt-0.5 text-xl font-bold tabular-nums ${textMain}`}>
                        {cur != null ? fmtBillion(cur) : '—'}
                      </div>
                      {yoy != null && (
                        <div
                          className="text-[11px] font-medium tabular-nums"
                          style={{ color: yoy >= 0 ? '#5FB39C' : '#D9737A' }}
                        >
                          {yoy >= 0 ? '+' : '-'}
                          {Math.abs(yoy).toFixed(1)}% <span className={textMuted}>{deltaLabel}</span>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )
          })()}

          {barData.length === 0 ? (
            <div className={`flex items-center justify-center h-40 text-xs ${textMuted}`}>
              재무 데이터 연결 시 표시
            </div>
          ) : (
            <div className="h-44">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
                  <XAxis
                    dataKey={xKey}
                    tick={{ fontSize: 10, fill: isDark ? '#94a3b8' : '#64748b' }}
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis
                    tick={{ fontSize: 10, fill: isDark ? '#94a3b8' : '#64748b' }}
                    tickLine={false}
                    axisLine={false}
                    width={48}
                    tickFormatter={fmtBillion}
                    domain={[yDomainMin, yDomainMax]}
                  />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    labelStyle={{ color: isDark ? '#cbd5e1' : '#475569' }}
                    formatter={(value) => [fmtBillion(value as number), '']}
                  />
                  <Legend
                    wrapperStyle={{ fontSize: 10, color: isDark ? '#94a3b8' : '#64748b' }}
                  />
                  {BAR_DEFS.map((b) => (
                    <Bar
                      key={b.key}
                      dataKey={b.key}
                      name={b.label}
                      fill={b.color}
                      radius={[2, 2, 0, 0]}
                      maxBarSize={20}
                    />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* 전체 재무제표 테이블 토글 */}
          {showFullTable && financials.length > 0 && (
            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full text-xs border-collapse">
                <thead>
                  <tr>
                    <th className={`sticky left-0 bg-white dark:bg-slate-900 text-left py-1 pr-3 whitespace-nowrap ${textMuted} font-medium`}>지표</th>
                    {cols.map((col, i) => (
                      <th key={col} className={`text-right py-1 px-2 whitespace-nowrap ${textMuted} font-medium tabular-nums`}>
                        {colLabels[i]}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {indicators.map((ind) => (
                    <tr
                      key={ind}
                      className="border-t border-slate-100 dark:border-slate-800"
                    >
                      <td className={`sticky left-0 bg-white dark:bg-slate-900 py-1 pr-3 whitespace-nowrap ${textMuted}`}>
                        {INDICATOR_LABEL[ind] ?? ind}
                      </td>
                      {cols.map((col) => {
                        const v = lookup[ind]?.[col]
                        return (
                          <td key={col} className={`py-1 px-2 text-right whitespace-nowrap tabular-nums ${textMain}`}>
                            {v !== undefined ? fmtBillion(v) : '—'}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* 지분구조 — col-span-1 */}
        <div className={`${cardClass} lg:col-span-1`}>
          <SectionLabel className="mb-2.5">지분구조</SectionLabel>
          {ownership.length === 0 ? (
            <div className={`flex items-center justify-center h-28 text-xs ${textMuted} text-center`}>
              지분 데이터 연결 시 표시
            </div>
          ) : (
            <div className="space-y-3">
              {shareholders.length > 0 && (
                <div>
                  <p className={`text-xs font-medium mb-1 ${textMuted}`}>대주주</p>
                  <ul className="space-y-1">
                    {shareholders.map((s, i) => (
                      <li key={i} className="flex items-center justify-between">
                        <span className={`text-xs truncate ${textMain}`}>{s.name}</span>
                        {s.stake != null && (
                          <span className={`text-xs tabular-nums ml-2 shrink-0 ${textMuted}`}>
                            {s.stake >= 1 ? s.stake.toFixed(1) : s.stake.toFixed(2)}%
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {subsidiaries.length > 0 && (
                <div>
                  <p className={`text-xs font-medium mb-1 ${textMuted}`}>자회사</p>
                  <ul className="space-y-1">
                    {subsidiaries.map((s, i) => (
                      <li key={i} className="flex items-center justify-between">
                        <span className={`text-xs truncate ${textMain}`}>{s.name}</span>
                        {s.stake != null && (
                          <span className={`text-xs tabular-nums ml-2 shrink-0 ${textMuted}`}>
                            {s.stake >= 1 ? s.stake.toFixed(1) : s.stake.toFixed(2)}%
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>

        {/* 거시 배경 — col-span-1 */}
        <div className={`${cardClass} lg:col-span-1`}>
          <SectionLabel className="mb-2.5">거시 배경</SectionLabel>
          {macro.length === 0 ? (
            <div className={`flex items-center justify-center h-28 text-xs ${textMuted} text-center`}>
              거시 데이터 연결 시 표시
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-2">
              {macro.map((m, i) => (
                <div
                  key={i}
                  className="rounded-lg bg-slate-50 dark:bg-slate-800/60 px-3 py-2"
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className={`text-xs ${textMuted} truncate`}>{m.name}</span>
                    <span className="text-base font-semibold tabular-nums shrink-0 text-blue-600 dark:text-blue-400">
                      {m.value}
                      {m.unit && (
                        <span className={`text-xs font-normal ml-0.5 ${textMuted}`}>{m.unit}</span>
                      )}
                    </span>
                  </div>
                  {m.asOf && (
                    <p className={`text-xs ${textMuted} mt-0.5`}>{m.asOf}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* IR 보고서 요약 카드 */}
      <div className={cardClass}>
        <SectionLabel className="mb-3">최근 보고서</SectionLabel>
        {irReports.length === 0 ? (
          <div className={`flex items-center justify-center h-16 text-xs ${textMuted}`}>
            보고서 적재 시 표시
          </div>
        ) : (
          <div className="space-y-2">
            {irReports.map((r) => {
              const isExpanded = !!expandedReports[r.rceptNo]
              const toggleExpand = () =>
                setExpandedReports((prev) => ({ ...prev, [r.rceptNo]: !prev[r.rceptNo] }))

              // 요약 불릿 여부: 줄 중 하나라도 '- '로 시작하면 리스트 렌더
              const summaryLines = r.summary
                ? r.summary.split('\n').map((l) => l.trim()).filter(Boolean)
                : []
              const isBullet = summaryLines.some((l) => l.startsWith('- '))

              return (
                <div
                  key={r.rceptNo}
                  className="rounded-lg border border-slate-100 dark:border-slate-800 px-3 py-2"
                >
                  {/* 헤더 행: 배지 + 날짜 + 제목(DART 링크) + 더보기 토글 */}
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[11px] text-slate-600 dark:text-slate-300 shrink-0">
                      {r.docType}
                    </span>
                    <span className={`text-[11px] tabular-nums shrink-0 ${textMuted}`}>{r.date}</span>
                    <a
                      href={`https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${r.rceptNo}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={`text-xs font-medium truncate min-w-0 flex-1 hover:text-blue-500 transition-colors ${textMain}`}
                      title="DART 원문 보기"
                    >
                      <span className="inline-flex items-center gap-1">
                        {r.title}
                        <ExternalLink size={11} className="shrink-0 opacity-50" />
                      </span>
                    </a>
                    {r.summary && (
                      <button
                        onClick={toggleExpand}
                        className={`flex items-center gap-0.5 text-[11px] shrink-0 ${textMuted} hover:${textMain} transition-colors`}
                      >
                        {isExpanded ? (
                          <><ChevronUp size={12} />접기</>
                        ) : (
                          <><ChevronDown size={12} />더보기</>
                        )}
                      </button>
                    )}
                  </div>

                  {/* 요약 — 접힘: line-clamp-2 티저 / 펼침: 전체 */}
                  {r.summary && (
                    <div className="mt-1.5">
                      {isExpanded ? (
                        isBullet ? (
                          <ul className={`space-y-0.5 text-xs ${textMuted} leading-relaxed list-none`}>
                            {summaryLines
                              .filter((l) => l.startsWith('- '))
                              .map((l, i) => (
                                <li key={i} className="flex gap-1">
                                  <span className="shrink-0 select-none">-</span>
                                  <span>{l.slice(2)}</span>
                                </li>
                              ))}
                          </ul>
                        ) : (
                          <p className={`text-xs ${textMuted} leading-relaxed whitespace-pre-line`}>
                            {r.summary}
                          </p>
                        )
                      ) : (
                        <p className={`text-xs ${textMuted} line-clamp-2 leading-relaxed`}>
                          {r.summary}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* 하단: 임원 요약 + 제품 요약 */}
      {profile && (profile.execs.length > 0 || profile.products.length > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* 임원 */}
          {profile.execs.length > 0 && (
            <div className={cardClass}>
              <SectionLabel className="mb-2.5">주요 임원</SectionLabel>
              <ul className="grid grid-cols-2 gap-x-4 gap-y-1">
                {profile.execs.map((e, i) => (
                  <li key={i} className="flex items-center gap-1.5 min-w-0">
                    <span className={`text-sm truncate ${textMain}`}>{e.name}</span>
                    {e.position && (
                      <span className={`text-xs shrink-0 ${textMuted}`}>{e.position}</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {/* 제품 */}
          {profile.products.length > 0 && (
            <div className={cardClass}>
              <SectionLabel className="mb-2.5">주요 제품</SectionLabel>
              <div className="flex flex-wrap gap-1.5">
                {profile.products.map((p, i) => (
                  <span
                    key={i}
                    className="rounded-full bg-slate-100 dark:bg-slate-800 px-2.5 py-0.5 text-xs text-slate-600 dark:text-slate-300"
                  >
                    {p}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
