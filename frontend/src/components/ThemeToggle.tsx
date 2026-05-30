import { Sun, Moon } from 'lucide-react'
import { useTheme } from '../theme/ThemeContext'

// 라이트/나이트 토글 — 공식 아이콘(lucide)
export default function ThemeToggle() {
  const { theme, toggle } = useTheme()
  return (
    <button
      onClick={toggle}
      title={theme === 'dark' ? '라이트 모드' : '나이트 모드'}
      aria-label="테마 전환"
      className="grid h-9 w-9 place-items-center rounded-full border border-slate-300/50 dark:border-slate-600/50 text-slate-600 dark:text-slate-300 hover:bg-slate-500/10 transition"
    >
      {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  )
}
