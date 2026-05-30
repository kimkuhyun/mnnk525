import { useCompany } from '../company/CompanyContext'
import { useNews } from '../api/hooks'
import type { NewsItem } from '../types'

export default function NewsFeed() {
  const { company } = useCompany()
  const { data: news, isLoading } = useNews(company.code)

  const items: NewsItem[] = news ?? []

  return (
    <aside className="flex h-full w-80 shrink-0 flex-col border-l border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">뉴스</span>
        {items.length > 0 && (
          <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs tabular-nums text-blue-600 dark:bg-blue-900/40 dark:text-blue-400">
            {items.length}
          </span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3">
        {isLoading ? (
          <p className="text-xs text-slate-400 dark:text-slate-500">불러오는 중…</p>
        ) : items.length === 0 ? (
          <p className="text-xs text-slate-400 dark:text-slate-500">뉴스 연결 시 표시됩니다</p>
        ) : (
          <ul className="space-y-3">
            {items.map((item) => (
              <li key={item.docId} className="border-b border-slate-100 pb-3 last:border-b-0 dark:border-slate-800">
                <a
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  className="line-clamp-2 text-sm font-medium leading-snug text-slate-800 hover:text-blue-600 dark:text-slate-100 dark:hover:text-blue-400"
                >
                  {item.title}
                </a>
                <div className="mt-1 flex items-center gap-1.5 text-xs text-slate-400 dark:text-slate-500">
                  <span className="tabular-nums">{item.date}</span>
                  {item.publisher && (
                    <>
                      <span>·</span>
                      <span>{item.publisher}</span>
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  )
}
