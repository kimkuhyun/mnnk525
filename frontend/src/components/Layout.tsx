import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'

const NAV = [
  { to: '/dashboard', label: '📊 대시보드' },
  { to: '/workbench', label: '🕸️ 관계 워크벤치' },
  { to: '/ask', label: '💬 묻기' },
  { to: '/patents', label: '📜 특허 관계' },
  { to: '/signals', label: '🔔 시그널' },
  { to: '/evidence', label: '📑 근거 피드' },
]

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div>
      <header className="sticky top-0 z-30 h-14 bg-white border-b border-slate-200 flex items-center px-5 gap-4">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-blue-600 text-white font-black grid place-items-center">P</div>
          <span className="font-bold text-lg">POLARIS</span>
          <span className="text-[11px] text-slate-400 hidden md:inline">기업 관계 인텔리전스</span>
        </div>
        <button className="ml-6 text-sm text-slate-500 hidden lg:inline">🔍 회사 검색·전환 · 현재: <b className="text-slate-700">[선택 회사]</b></button>
      </header>
      <div className="flex">
        <aside className="w-52 shrink-0 border-r border-slate-200 bg-white min-h-[calc(100vh-3.5rem)] p-3 hidden md:block">
          <nav className="space-y-1">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                className={({ isActive }) =>
                  `block px-3 py-2.5 rounded-lg text-sm font-medium ${
                    isActive ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-blue-50 hover:text-blue-600'
                  }`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
        </aside>
        <main className="flex-1 p-5 max-w-[1500px]">{children}</main>
      </div>
    </div>
  )
}
