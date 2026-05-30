// DailyDigest — 가로 시계열
// 상단: 날짜별 미니맵(막대=기사수, 색=감성) + 클릭 시 해당 카드로 스크롤
// 하단: 가로 스크롤 카드 레일 (왼=과거 → 오른=현재, 마운트 시 최신=우측)
// 휠/드래그 가로 스크롤

import {
  useRef,
  useEffect,
  useCallback,
  useState,
} from 'react'
import { ExternalLink } from 'lucide-react'
import { useTheme } from '../theme/ThemeContext'
import { useCompany } from '../company/CompanyContext'
import { useDailyDigest } from '../api/hooks'
import type { DailyDigestItem } from '../types'

// 감성 점수 (0~1) → 색
function sentimentColor(score: number | undefined) {
  if (score === undefined) return '#94a3b8'
  if (score >= 0.6) return '#5FB39C'
  if (score <= 0.35) return '#D9737A'
  return '#8E99A8'
}

// 감성 라벨
function sentimentLabel(score: number | undefined) {
  if (score === undefined) return ''
  if (score >= 0.6) return '긍정'
  if (score <= 0.35) return '부정'
  return '중립'
}

export default function DailyDigest() {
  const { theme } = useTheme()
  const { company } = useCompany()
  const { data } = useDailyDigest(company.code)

  const isDark = theme === 'dark'
  const items: DailyDigestItem[] = data ?? []

  const railRef = useRef<HTMLDivElement>(null)
  const cardRefs = useRef<(HTMLDivElement | null)[]>([])

  const textMuted = isDark ? 'text-slate-400' : 'text-slate-500'
  const textSub = isDark ? 'text-slate-300' : 'text-slate-700'
  const cardBg = isDark ? 'bg-slate-800/60 border-slate-700/80' : 'bg-white border-slate-200/80'
  const cardHover = isDark ? 'hover:bg-slate-800' : 'hover:bg-slate-50'

  // 마운트 시 최신(오른쪽)으로 스크롤
  useEffect(() => {
    if (railRef.current && items.length > 0) {
      railRef.current.scrollLeft = railRef.current.scrollWidth
    }
  }, [items.length])

  // 휠 → 가로 스크롤
  const handleWheel = useCallback((e: React.WheelEvent<HTMLDivElement>) => {
    if (!railRef.current) return
    e.preventDefault()
    railRef.current.scrollLeft += e.deltaY + e.deltaX
  }, [])

  // 드래그 가로 스크롤
  const dragState = useRef({ dragging: false, startX: 0, scrollStart: 0 })
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    dragState.current = {
      dragging: true,
      startX: e.clientX,
      scrollStart: railRef.current?.scrollLeft ?? 0,
    }
  }, [])
  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragState.current.dragging || !railRef.current) return
    const dx = e.clientX - dragState.current.startX
    railRef.current.scrollLeft = dragState.current.scrollStart - dx
  }, [])
  const handleMouseUp = useCallback(() => {
    dragState.current.dragging = false
  }, [])

  // 미니맵 클릭 → 해당 카드로 스크롤
  const scrollToCard = useCallback((idx: number) => {
    const el = cardRefs.current[idx]
    if (el && railRef.current) {
      railRef.current.scrollTo({
        left: el.offsetLeft - 16,
        behavior: 'smooth',
      })
    }
  }, [])

  // 최대 기사 수 (미니맵 막대 스케일)
  const maxArticles = Math.max(1, ...items.map((i) => i.articleCount))

  if (items.length === 0) {
    return (
      <div className="rounded-xl border border-slate-200/80 bg-white dark:border-slate-800 dark:bg-slate-900 p-4 flex items-center justify-center min-h-[160px]">
        <span className="text-xs text-slate-400 dark:text-slate-500">다이제스트 연결 시 표시</span>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-slate-200/80 bg-white dark:border-slate-800 dark:bg-slate-900 flex flex-col overflow-hidden shadow-sm">
      {/* 헤더 */}
      <div className="px-4 pt-4 pb-1 shrink-0">
        <div className="flex items-center gap-2">
          <span className="h-4 w-[3px] rounded-full bg-blue-500" />
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">일별 다이제스트</p>
        </div>
      </div>

      {/* 미니맵 — 날짜별 막대 */}
      <div className="px-4 pb-2 shrink-0">
        <div
          className="flex items-end gap-0.5 h-10 overflow-x-auto"
          style={{ scrollbarWidth: 'none' }}
        >
          {items.map((item, idx) => {
            const heightPct = (item.articleCount / maxArticles) * 100
            // sentimentScore 필드 없으면 undefined — articleCount 기반 fallback
            const sc = (item as any).sentimentScore as number | undefined
            const barColor = sentimentColor(sc)
            return (
              <button
                key={item.date}
                title={`${item.date} (${item.articleCount}건)`}
                onClick={() => scrollToCard(idx)}
                className="shrink-0 flex flex-col items-center gap-0.5 group"
                style={{ minWidth: 8 }}
              >
                <div
                  className="w-1.5 rounded-sm transition-opacity group-hover:opacity-80"
                  style={{
                    height: `${Math.max(heightPct, 8)}%`,
                    backgroundColor: barColor,
                    maxHeight: '100%',
                  }}
                />
              </button>
            )
          })}
        </div>
        <p className={`text-xs mt-1 tabular-nums ${textMuted}`}>
          {items[0]?.date} — {items[items.length - 1]?.date}
        </p>
      </div>

      {/* 카드 레일 */}
      <div
        ref={railRef}
        className="flex gap-3 px-4 pb-4 overflow-x-auto select-none"
        style={{ scrollbarWidth: 'thin', cursor: 'grab' }}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        {items.map((item, idx) => {
          const sc = (item as any).sentimentScore as number | undefined
          const color = sentimentColor(sc)
          const label = sentimentLabel(sc)
          return (
            <div
              key={item.date}
              ref={(el) => { cardRefs.current[idx] = el }}
              className={`shrink-0 rounded-xl border ${cardBg} ${cardHover} transition-colors p-3 flex flex-col gap-1.5`}
              style={{ width: 200, minHeight: 120 }}
            >
              {/* 날짜 + 감성 */}
              <div className="flex items-center justify-between gap-2">
                <span className={`text-xs font-semibold tabular-nums ${textSub}`}>{item.date}</span>
                <div className="flex items-center gap-1.5">
                  {label && (
                    <span
                      className="rounded-full px-2 py-0.5 text-[11px] font-medium text-white"
                      style={{ backgroundColor: color }}
                    >
                      {label}
                    </span>
                  )}
                  <span className={`text-xs tabular-nums ${textMuted}`}>{item.articleCount}건</span>
                </div>
              </div>

              {/* 요약 */}
              {item.summary && (
                <p className={`text-xs leading-relaxed line-clamp-3 ${textMuted}`}>
                  {item.summary}
                </p>
              )}

              {/* 대표 헤드라인 1개 */}
              {item.headlines && item.headlines.length > 0 && (
                <a
                  href={item.headlines[0].url}
                  target="_blank"
                  rel="noreferrer"
                  className={`inline-flex items-start gap-1 text-xs mt-auto hover:text-blue-500 transition-colors ${textMuted}`}
                  onClick={(e) => e.stopPropagation()}
                >
                  <span className="line-clamp-2">{item.headlines[0].title}</span>
                  <ExternalLink size={10} className="shrink-0 mt-0.5" />
                </a>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
