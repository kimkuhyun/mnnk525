import { useNavigate } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import StarField from '../components/StarField'
import ThemeToggle from '../components/ThemeToggle'

// 진입화면 — 나브/검색/알림 제거. 배경(별)+문구+테마토글(아이콘)+시작하기 버튼+소년 일러스트.
export default function Landing() {
  const navigate = useNavigate()

  return (
    <div className="relative min-h-screen overflow-hidden bg-white dark:bg-[#0B0820] text-slate-900 dark:text-white transition-colors duration-500">
      {/* 별 배경 (다크에서 또렷) */}
      <StarField />
      {/* POLARIS 별 + halo — 원본 cliff.svg radialGradient 재현 (좌상단 36%·30%) */}
      <div className="pointer-events-none absolute left-[36%] top-[30%] -translate-x-1/2 -translate-y-1/2 transition-opacity duration-700">
        <div
          className="h-[420px] w-[420px] rounded-full"
          style={{
            background:
              'radial-gradient(circle, rgba(232,240,255,0.45) 0%, rgba(122,176,255,0.16) 40%, rgba(122,176,255,0) 72%)',
          }}
        />
        {/* 별 코어 (라이트=파랑, 다크=흰 + 발광) */}
        <div
          className="absolute left-1/2 top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-sky-400 dark:bg-white transition-colors duration-500"
          style={{ boxShadow: '0 0 22px 9px rgba(122,176,255,0.45)' }}
        />
      </div>

      {/* 우상단: 로고 워드마크 + 테마 토글(아이콘) */}
      <div className="absolute top-5 left-6 z-20 font-bold tracking-tight">POLARIS</div>
      <div className="absolute top-4 right-5 z-20">
        <ThemeToggle />
      </div>

      {/* 중앙 콘텐츠 */}
      <div className="relative z-10 flex min-h-screen flex-col items-center justify-center px-6 text-center">
        <p className="mb-5 text-xs tracking-[0.4em] text-slate-400 dark:text-slate-500">POLARIS · 89°15&#39;</p>
        <h1 className="mb-12 text-4xl font-bold sm:text-5xl">언제나 같은 자리.</h1>
        <button
          onClick={() => navigate('/app')}
          className="inline-flex items-center gap-2 rounded-full bg-blue-600 px-9 py-3.5 text-base font-semibold text-white shadow-lg shadow-blue-600/30 transition hover:-translate-y-0.5 hover:bg-blue-700"
        >
          시작하기 <ArrowRight size={18} />
        </button>
      </div>

      {/* 소년 일러스트 (public/cliff.png 넣으면 표시. 없으면 자동 숨김) */}
      <img
        src="/cliff.png"
        alt=""
        onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
        className="pointer-events-none absolute bottom-0 right-0 z-0 w-[38%] max-w-xl select-none opacity-95 transition duration-500 dark:invert"
      />
    </div>
  )
}
