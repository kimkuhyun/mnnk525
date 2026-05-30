import { RELATION_GROUPS, GROUP_COLOR } from '../lib/relations';
import type { RelationGroup } from '../types';

interface GraphToolbarProps {
  groups: Set<RelationGroup>;
  onToggleGroup: (g: RelationGroup) => void;
}

export default function GraphToolbar({ groups, onToggleGroup }: GraphToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200/80 bg-white/80 dark:border-slate-800 dark:bg-slate-900/80 backdrop-blur px-3 py-2 text-xs transition-colors">
      {RELATION_GROUPS.map(({ key, label }) => {
        const active = groups.has(key);
        return (
          <button
            key={key}
            onClick={() => onToggleGroup(key)}
            className={`flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium transition-colors ${active ? 'border-current text-slate-700 dark:text-slate-200' : 'border-slate-200 dark:border-slate-700 text-slate-400 dark:text-slate-500 opacity-40'}`}
          >
            <span
              className="inline-block w-2 h-2 rounded-full flex-shrink-0"
              style={{ backgroundColor: GROUP_COLOR[key] }}
            />
            {label}
          </button>
        );
      })}
    </div>
  );
}
