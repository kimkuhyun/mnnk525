import type { ReactNode } from 'react'

// 카드 섹션 헤더 — 좌측 액센트 바 + eyebrow 텍스트. 위계/리듬 통일용.
export default function SectionLabel({
  children,
  color = '#3b82f6',
  className = '',
}: {
  children: ReactNode
  color?: string
  className?: string
}) {
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <span className="h-3.5 w-[3px] shrink-0 rounded-full" style={{ backgroundColor: color }} />
      <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
        {children}
      </span>
    </div>
  )
}
