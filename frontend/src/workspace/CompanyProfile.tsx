import { useProfile } from '../api/hooks';

interface Props { code: string; name: string; }

export default function CompanyProfile({ code }: Props) {
  const { data, isLoading } = useProfile(code);

  const sectionTitle = 'text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase mb-2';
  const empty = <p className="text-sm text-slate-500 dark:text-slate-400">데이터 연결 시 표시됩니다</p>;

  return (
    <div className="space-y-4">
      {isLoading && (
        <p className="text-sm text-slate-500 dark:text-slate-400">불러오는 중…</p>
      )}

      {/* 요약 */}
      <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-4">
        <p className={sectionTitle}>요약</p>
        {data?.summary
          ? <p className="text-sm text-slate-700 dark:text-slate-200 leading-relaxed">{data.summary}</p>
          : empty}
      </div>

      {/* 재무 */}
      <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-4">
        <p className={sectionTitle}>재무</p>
        {data?.finance?.length
          ? (
            <div className="grid grid-cols-2 gap-x-4 gap-y-1">
              {data.finance.map((f, i) => (
                <div key={i} className="contents">
                  <span className="text-xs text-slate-500 dark:text-slate-400">{f.label}</span>
                  <span className="text-sm tabular-nums text-slate-700 dark:text-slate-200 text-right">{f.value}</span>
                </div>
              ))}
            </div>
          )
          : empty}
      </div>

      {/* 임원 */}
      <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-4">
        <p className={sectionTitle}>임원</p>
        {data?.execs?.length
          ? (
            <ul className="space-y-1">
              {data.execs.map((e, i) => (
                <li key={i} className="flex items-center gap-2">
                  <span className="text-sm text-slate-700 dark:text-slate-200">{e.name}</span>
                  {e.position && <span className="text-xs text-slate-500 dark:text-slate-400">{e.position}</span>}
                </li>
              ))}
            </ul>
          )
          : empty}
      </div>

      {/* 자회사·지분 */}
      <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-4">
        <p className={sectionTitle}>자회사·지분</p>
        {data?.subsidiaries?.length
          ? (
            <ul className="space-y-1">
              {data.subsidiaries.map((s, i) => (
                <li key={i} className="flex items-center gap-2">
                  <span className="text-sm text-slate-700 dark:text-slate-200">{s.name}</span>
                  {s.stake != null && (
                    <span className="text-xs tabular-nums text-slate-500 dark:text-slate-400">{s.stake}%</span>
                  )}
                </li>
              ))}
            </ul>
          )
          : empty}
      </div>

      {/* 주력 제품 */}
      <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-4">
        <p className={sectionTitle}>주력 제품</p>
        {data?.products?.length
          ? (
            <div className="flex flex-wrap gap-2">
              {data.products.map((p, i) => (
                <span key={i} className="rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 text-xs text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 transition-colors">
                  {p}
                </span>
              ))}
            </div>
          )
          : empty}
      </div>

      {/* 최근 뉴스 */}
      <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-4">
        <p className={sectionTitle}>최근 뉴스</p>
        {data?.recentNews?.length
          ? (
            <ul className="space-y-2">
              {data.recentNews.map((n) => (
                <li key={n.docId} className="flex flex-col gap-0.5">
                  <a
                    href={n.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-blue-600 dark:text-blue-400 hover:underline leading-snug"
                  >
                    {n.title}
                  </a>
                  <span className="text-xs text-slate-500 dark:text-slate-400">
                    {n.date}{n.publisher ? ` · ${n.publisher}` : ''}
                  </span>
                </li>
              ))}
            </ul>
          )
          : empty}
      </div>
    </div>
  );
}
