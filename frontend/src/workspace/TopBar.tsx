import { Link } from 'react-router-dom';
import { useCompany } from '../company/CompanyContext';
import ThemeToggle from '../components/ThemeToggle';

export default function TopBar() {
  const { company, setCompany, companies } = useCompany();

  return (
    <header className="sticky top-0 z-30 h-14 flex items-center gap-4 px-5 border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 transition-colors">
      <Link to="/" className="shrink-0 flex items-center gap-2">
        <span className="grid h-6 w-6 place-items-center rounded-md bg-gradient-to-br from-blue-500 to-blue-700 shadow-sm">
          <span className="h-2 w-2 rotate-45 bg-white/90" />
        </span>
        <span className="font-bold tracking-tight text-slate-900 dark:text-white">POLARIS</span>
      </Link>

      <div className="flex items-center gap-1">
        {companies.map((c) => (
          <button
            key={c.code}
            onClick={() => setCompany(c)}
            className={
              company.code === c.code
                ? 'rounded-lg px-3 py-1.5 text-sm font-medium bg-blue-600 text-white transition-colors'
                : 'rounded-lg px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors'
            }
          >
            {c.name}
          </button>
        ))}
      </div>

      <div className="ml-auto">
        <ThemeToggle />
      </div>
    </header>
  );
}
