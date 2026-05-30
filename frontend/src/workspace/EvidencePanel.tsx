import { ExternalLink } from 'lucide-react';
import { useEvidence } from '../api/hooks';
import { GROUP_LABEL, GROUP_COLOR } from '../lib/relations';
import type { RelationGroup } from '../types';

interface Props {
  sel: { kind: 'edge'; source: string; target: string; group: RelationGroup; weight: number };
}

export default function EvidencePanel({ sel }: Props) {
  const { data, isLoading, isError } = useEvidence(sel);

  return (
    <div className="rounded-xl border border-slate-200/80 bg-white dark:border-slate-800 dark:bg-slate-900 p-4 transition-colors">
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">
          {sel.source} → {sel.target}
        </span>
        <span
          className="rounded-full px-2 py-0.5 text-[11px] font-medium text-white"
          style={{ backgroundColor: GROUP_COLOR[sel.group] }}
        >
          {GROUP_LABEL[sel.group]}
        </span>
        <span className="ml-auto text-xs text-slate-400 dark:text-slate-500 tabular-nums">
          언급 {sel.weight}건
        </span>
      </div>

      {isLoading ? (
        <p className="text-xs text-slate-400 dark:text-slate-500">불러오는 중…</p>
      ) : isError || !data || data.length === 0 ? (
        <p className="text-xs text-slate-400 dark:text-slate-500">언급 기사 연결 시 표시됩니다</p>
      ) : (
        <ul className="space-y-3">
          {data.map((item) => (
            <li key={item.docId} className="border-b border-slate-100 dark:border-slate-800 pb-3 last:border-b-0 last:pb-0">
              <a
                href={item.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-start gap-1 text-sm font-medium text-slate-700 dark:text-slate-200 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
              >
                <span>{item.title}</span>
                <ExternalLink size={13} className="mt-0.5 shrink-0" />
              </a>
              <div className="mt-1 flex flex-wrap gap-2 text-xs text-slate-400 dark:text-slate-500">
                <span className="tabular-nums">{item.date}</span>
                {item.publisher && <span>· {item.publisher}</span>}
              </div>
              {item.snippet && (
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 line-clamp-2 leading-relaxed">
                  {item.snippet}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
