import { RELATION_GROUPS, GROUP_COLOR } from '../lib/relations';
import type { RelationGroup } from '../types';

interface GraphToolbarProps {
  groups: Set<RelationGroup>;
  onToggleGroup: (g: RelationGroup) => void;
  minWeight: number;
  onMinWeight: (n: number) => void;
}

export default function GraphToolbar({ groups, onToggleGroup, minWeight, onMinWeight }: GraphToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white/80 dark:border-slate-800 dark:bg-slate-900/80 backdrop-blur px-3 py-2 text-xs transition-colors">
      {RELATION_GROUPS.map(({ key, label }) => {
        const active = groups.has(key);
        return (
          <button
            key={key}
            onClick={() => onToggleGroup(key)}
            className={`flex items-center gap-1 rounded-full border px-2 py-0.5 transition-colors ${active ? 'border-current text-slate-700 dark:text-slate-200' : 'border-slate-200 dark:border-slate-700 text-slate-400 dark:text-slate-500 opacity-40'}`}
          >
            <span
              className="inline-block w-2 h-2 rounded-full flex-shrink-0"
              style={{ backgroundColor: GROUP_COLOR[key] }}
            />
            {label}
          </button>
        );
      })}

      <div className="w-px h-4 bg-slate-200 dark:bg-slate-700 mx-1" />

      <div className="flex items-center gap-1 text-slate-600 dark:text-slate-300">
        <span>근거수 ≥</span>
        <input
          type="range"
          min={1}
          max={30}
          value={minWeight}
          onChange={(e) => onMinWeight(Number(e.target.value))}
          className="w-20 accent-blue-600"
        />
        <span className="tabular-nums w-4 text-center">{minWeight}</span>
      </div>
    </div>
  );
}
