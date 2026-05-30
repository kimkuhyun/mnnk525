import { useTheme } from '../theme/ThemeContext';
import { useCompany } from '../company/CompanyContext';
import { useRelationTop } from '../api/hooks';
import { GROUP_COLOR, GROUP_LABEL } from '../lib/relations';

interface Props {
  onFocusNode: (id: string) => void;
}

export default function RelationTopCard({ onFocusNode }: Props) {
  const { theme } = useTheme();
  const { company } = useCompany();
  const { data } = useRelationTop(company.code);

  const isDark = theme === 'dark';
  const items = data ?? [];

  const textMuted = isDark ? 'text-slate-400' : 'text-slate-500';
  const textSub = isDark ? 'text-slate-300' : 'text-slate-700';
  const rowHover = isDark
    ? 'hover:bg-slate-800/50 active:bg-slate-700'
    : 'hover:bg-slate-50 active:bg-slate-100';

  return (
    <div className="h-full rounded-xl border border-slate-200/80 bg-white dark:border-slate-800 dark:bg-slate-900 flex flex-col p-4 overflow-hidden shadow-sm">
      <div className="flex items-center gap-2 mb-2.5 shrink-0">
        <span className="h-4 w-[3px] rounded-full bg-blue-500" />
        <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">핵심 관계 Top5</p>
      </div>

      {items.length === 0 ? (
        <div className={`flex items-center justify-center flex-1 text-xs ${textMuted} text-center`}>
          관계 데이터 연결 시 표시
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto min-h-0 space-y-0.5">
          {items.map((item) => (
            <button
              key={item.nodeId}
              onClick={() => onFocusNode(item.nodeId)}
              className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs transition-colors ${rowHover} text-left`}
            >
              {/* 그룹 색 점 */}
              <span
                className="shrink-0 w-2 h-2 rounded-full"
                style={{ backgroundColor: GROUP_COLOR[item.group] }}
              />
              {/* 라벨 + target */}
              <span className={`shrink-0 ${textMuted}`}>{GROUP_LABEL[item.group]}</span>
              <span className={`flex-1 truncate font-medium ${textSub}`}>{item.target}</span>
              {/* 근거 건수 */}
              <span className={`shrink-0 tabular-nums ${textMuted}`}>
                언급{' '}
                <span className="font-semibold" style={{ color: GROUP_COLOR[item.group] }}>
                  {item.evidenceCount}
                </span>
                건
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
