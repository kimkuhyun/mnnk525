// Briefing — 최상단 hero 카드
// 좌: 최신 브리핑 날짜 + 요약 + 헤드라인 2개
// 우/하: 수시공시 목록 (날짜·docType 배지·title·summary 1줄, DART 링크)

import { ExternalLink } from 'lucide-react'
import { useTheme } from '../theme/ThemeContext'
import { useCompany } from '../company/CompanyContext'
import { useBriefing } from '../api/hooks'
import type { DisclosureItem, NewsItem } from '../types'

export default function Briefing() {
  const { theme } = useTheme()
  const { company } = useCompany()
  const { data, isError } = useBriefing(company.code)

  const isDark = theme === 'dark'
  const textMain = isDark ? 'text-slate-100' : 'text-slate-900'
  const textSub = isDark ? 'text-slate-300' : 'text-slate-700'
  const textMuted = isDark ? 'text-slate-400' : 'text-slate-500'

  if (isError || !data) {
    return (
      <div className="rounded-xl border border-slate-200/80 bg-white dark:border-slate-800 dark:bg-slate-900 shadow-sm p-5 flex items-center justify-center min-h-[120px]">
        <span className="text-xs text-slate-400 dark:text-slate-500">브리핑 데이터 연결 시 표시됩니다.</span>
      </div>
    )
  }

  const headlines: NewsItem[] = data.headlines ?? []
  const disclosures: DisclosureItem[] = data.disclosures ?? []

  return (
    <div className="rounded-xl border border-slate-200/80 bg-white dark:border-slate-800 dark:bg-slate-900 shadow-sm overflow-hidden">
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] divide-y lg:divide-y-0 lg:divide-x divide-slate-200/80 dark:divide-slate-800">

        {/* ── 좌: 최신 브리핑 ── */}
        <div className="p-5 flex flex-col gap-4 bg-gradient-to-br from-blue-50/70 via-transparent to-transparent dark:from-blue-950/20 dark:via-transparent dark:to-transparent">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-blue-600 dark:text-blue-400">최신 브리핑</span>
            {data.date && (
              <span className="text-xs tabular-nums text-slate-400 dark:text-slate-500">{data.date}</span>
            )}
            {data.articleCount > 0 && (
              <span className="ml-auto rounded-full px-2 py-0.5 text-[11px] font-medium tabular-nums bg-blue-50 text-blue-600 dark:bg-blue-950/40 dark:text-blue-300">
                기사 {data.articleCount}건
              </span>
            )}
          </div>

          {data.summary ? (
            <p className={`border-l-2 border-blue-500 pl-3 text-base leading-relaxed ${textSub}`}>{data.summary}</p>
          ) : (
            <p className={`text-sm ${textMuted}`}>요약 정보가 없습니다.</p>
          )}

          {headlines.length > 0 && (
            <div className="border-t border-slate-200/80 dark:border-slate-800 pt-4 flex flex-col gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">대표 헤드라인</span>
              {headlines.map((h) => (
                <a
                  key={h.docId}
                  href={h.url}
                  target="_blank"
                  rel="noreferrer"
                  className={`inline-flex items-start gap-1.5 text-sm hover:text-blue-500 transition-colors ${textSub}`}
                >
                  <ExternalLink size={13} className="shrink-0 mt-0.5 opacity-60" />
                  <span className="line-clamp-2">{h.title}</span>
                </a>
              ))}
            </div>
          )}

          {headlines.length === 0 && (
            <p className={`text-sm ${textMuted}`}>연결된 헤드라인이 없습니다.</p>
          )}
        </div>

        {/* ── 우: 수시공시 ── */}
        <div className="p-5 flex flex-col gap-2.5">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">수시공시</span>

          {disclosures.length === 0 ? (
            <p className="text-xs text-slate-400 dark:text-slate-500">공시 데이터 연결 시 표시됩니다.</p>
          ) : (
            <div className="flex flex-col divide-y divide-slate-100 dark:divide-slate-800 overflow-y-auto" style={{ maxHeight: 300 }}>
              {disclosures.map((d, idx) => (
                <div key={idx} className="flex flex-col gap-1 py-2 first:pt-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs tabular-nums text-slate-400 dark:text-slate-500">{d.date}</span>
                    <span
                      className="rounded-full px-2 py-0.5 text-[11px] font-medium"
                      style={{ background: '#5E9BD120', color: '#5E9BD1' }}
                    >
                      {d.docType}
                    </span>
                  </div>

                  {d.rcept ? (
                    <a
                      href={`https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${d.rcept}`}
                      target="_blank"
                      rel="noreferrer"
                      className={`inline-flex items-start gap-1 text-sm font-medium hover:text-blue-500 transition-colors ${textMain}`}
                    >
                      <span className="truncate">{d.title}</span>
                      <ExternalLink size={12} className="shrink-0 mt-0.5 opacity-60" />
                    </a>
                  ) : (
                    <span className={`text-sm font-medium truncate ${textMain}`}>{d.title}</span>
                  )}

                  {d.summary && (
                    <p className="text-xs leading-relaxed line-clamp-1 text-slate-400 dark:text-slate-500">{d.summary}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
