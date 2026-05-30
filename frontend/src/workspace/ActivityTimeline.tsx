import { useMemo } from 'react';
import { useCompany } from '../company/CompanyContext';
import { useActivity } from '../api/hooks';
import { GROUP_COLOR, GROUP_LABEL } from '../lib/relations';
import type { ActivityItem, RelationGroup } from '../types';

function groupByDate(items: ActivityItem[]): Map<string, ActivityItem[]> {
  const map = new Map<string, ActivityItem[]>();
  for (const item of items) {
    const key = item.date;
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(item);
  }
  return map;
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return dateStr;
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${mm}-${dd}`;
}

export default function ActivityTimeline() {
  const { company } = useCompany();
  const { data: items = [] } = useActivity(company?.code ?? '');

  const sortedGroups = useMemo(() => {
    const sorted = [...items].sort(
      (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()
    );
    return groupByDate(sorted);
  }, [items]);

  const totalCount = items.length;

  return (
    <aside className="h-full overflow-y-auto border-l border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 flex flex-col">
      <div className="sticky top-0 z-10 flex items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
        <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">기업 행보</span>
        {totalCount > 0 && (
          <span className="text-xs tabular-nums text-slate-500 dark:text-slate-400">
            {totalCount.toLocaleString()}건
          </span>
        )}
      </div>

      {totalCount === 0 ? (
        <div className="flex flex-1 items-center justify-center px-4 py-10 text-xs text-slate-400 dark:text-slate-500 text-center">
          행보 데이터 연결 시 표시됩니다
        </div>
      ) : (
        <ul className="flex flex-col px-4 py-3 space-y-0">
          {Array.from(sortedGroups.entries()).map(([date, dayItems]) => (
            <li key={date}>
              <div className="pt-1 pb-0.5">
                <span className="text-[10px] font-medium tabular-nums text-slate-400 dark:text-slate-500 tracking-wide">
                  {formatDate(date)}
                </span>
              </div>
              <ul className="space-y-3 pb-3 border-b border-slate-100 dark:border-slate-800">
                {dayItems.map((item, idx) => {
                  const dotColor = GROUP_COLOR[item.group as RelationGroup] ?? '#94a3b8';
                  return (
                    <li key={item.docId ? `${item.docId}-${idx}` : `${date}-${idx}`} className="flex items-start gap-2">
                      <span
                        className="mt-1.5 shrink-0 w-2 h-2 rounded-full"
                        style={{ backgroundColor: dotColor }}
                      />
                      <div className="flex flex-col min-w-0">
                        <span className="text-[13px] leading-snug text-slate-700 dark:text-slate-200 break-words">
                          {item.target}
                          {item.predicate ? ` · ${item.predicate}` : ''}
                          {item.group ? ` · ${GROUP_LABEL[item.group as RelationGroup] ?? item.group}` : ''}
                        </span>
                        {item.evidenceCount > 0 && (
                          <span className="text-[11px] tabular-nums text-slate-400 dark:text-slate-500 mt-0.5">
                            근거 {item.evidenceCount}건
                          </span>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
