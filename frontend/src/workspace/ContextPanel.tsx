import { X } from 'lucide-react';
import { Selection } from '../types';
import CompanyProfile from './CompanyProfile';
import EvidencePanel from './EvidencePanel';

interface Props {
  selection: Selection;
  onClose: () => void;
}

export default function ContextPanel({ selection, onClose }: Props) {
  if (!selection) return null;

  const title = selection.kind === 'node' ? selection.name : '관계';

  return (
    <div className="fixed right-0 top-14 bottom-0 w-96 z-20 border-l bg-white dark:bg-slate-900 dark:border-slate-800 shadow-xl overflow-y-auto transition-transform">
      <div className="sticky top-0 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 flex justify-between items-center p-4">
        <span className="font-semibold text-slate-700 dark:text-slate-200 truncate">{title}</span>
        <button
          onClick={onClose}
          className="ml-2 p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400 transition-colors"
          aria-label="닫기"
        >
          <X size={18} />
        </button>
      </div>
      <div className="p-4">
        {selection.kind === 'node' ? (
          <CompanyProfile code={selection.id} name={selection.name} />
        ) : (
          <EvidencePanel sel={selection} />
        )}
      </div>
    </div>
  );
}
