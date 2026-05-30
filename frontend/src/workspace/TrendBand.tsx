import { useState } from 'react';
import { TrendingUp, Heart, BarChart2 } from 'lucide-react';
import {
  AreaChart,
  Area,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { useTheme } from '../theme/ThemeContext';
import { useCompany } from '../company/CompanyContext';
import { useTrend, useSentiment, useStock } from '../api/hooks';
import RelationTopCard from './RelationTopCard';

type Tab = 'mention' | 'sentiment' | 'stock';

interface Props {
  onFocusNode: (id: string) => void;
}

export default function TrendBand({ onFocusNode }: Props) {
  const { theme } = useTheme();
  const { company } = useCompany();
  const [activeTab, setActiveTab] = useState<Tab>('mention');

  const { data: trendData } = useTrend(company.code);
  const { data: sentimentData } = useSentiment(company.code);
  const { data: stockData } = useStock(company.code);

  const isDark = theme === 'dark';

  const cardClass =
    'rounded-xl border border-slate-200/80 bg-white dark:border-slate-800 dark:bg-slate-900 shadow-sm';
  const textMuted = isDark ? 'text-slate-400' : 'text-slate-500';
  const textMain = isDark ? 'text-slate-100' : 'text-slate-900';
  const tabBase =
    'flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-lg transition-colors';
  const tabActive = isDark
    ? 'bg-slate-700 text-slate-100'
    : 'bg-slate-100 text-slate-900';
  const tabInactive = isDark
    ? 'text-slate-400 hover:text-slate-200'
    : 'text-slate-500 hover:text-slate-700';

  const mentions = trendData?.mentions ?? [];
  const sentiments = sentimentData ?? [];
  const stockPoints = (stockData ?? []).map((p) => ({ ...p, close: Number(p.close) }));

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 h-56">
      {/* 탭 카드 col-span-2 */}
      <div className={`${cardClass} col-span-1 lg:col-span-2 flex flex-col p-3 overflow-hidden`}>
        {/* 탭 헤더 */}
        <div className="flex items-center gap-1 mb-2 shrink-0">
          <button
            className={`${tabBase} ${activeTab === 'mention' ? tabActive : tabInactive}`}
            onClick={() => setActiveTab('mention')}
          >
            <TrendingUp size={12} />
            멘션추이
          </button>
          <button
            className={`${tabBase} ${activeTab === 'sentiment' ? tabActive : tabInactive}`}
            onClick={() => setActiveTab('sentiment')}
          >
            <Heart size={12} />
            감성
          </button>
          <button
            className={`${tabBase} ${activeTab === 'stock' ? tabActive : tabInactive}`}
            onClick={() => setActiveTab('stock')}
          >
            <BarChart2 size={12} />
            주가
          </button>
        </div>

        {/* 탭 콘텐츠 */}
        <div className="flex-1 min-h-0">
          {activeTab === 'mention' && (
            mentions.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={mentions} margin={{ top: 2, right: 8, left: -24, bottom: 0 }}>
                  <defs>
                    <linearGradient id="mentionGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#2563eb" stopOpacity={0.34} />
                      <stop offset="95%" stopColor="#2563eb" stopOpacity={0.04} />
                    </linearGradient>
                  </defs>
                  <XAxis
                    dataKey="date"
                    tick={false}
                    tickLine={false}
                    axisLine={false}
                    height={4}
                  />
                  <YAxis
                    tick={{ fontSize: 10, fill: isDark ? '#94a3b8' : '#64748b' }}
                    tickLine={false}
                    axisLine={false}
                    width={32}
                  />
                  <Tooltip
                    contentStyle={{
                      background: isDark ? '#1e293b' : '#fff',
                      border: isDark ? '1px solid #334155' : '1px solid #e2e8f0',
                      borderRadius: 8,
                      fontSize: 11,
                    }}
                    labelStyle={{ color: isDark ? '#cbd5e1' : '#475569' }}
                    itemStyle={{ color: '#2563eb' }}
                  />
                  <Area
                    type="monotone"
                    dataKey="count"
                    stroke="#2563eb"
                    strokeWidth={2}
                    fill="url(#mentionGrad)"
                    dot={false}
                    activeDot={{ r: 3 }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className={`flex items-center justify-center h-full text-xs ${textMuted}`}>
                멘션 데이터 연결 시 표시
              </div>
            )
          )}

          {activeTab === 'sentiment' && (
            sentiments.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={sentiments} margin={{ top: 2, right: 8, left: -24, bottom: 0 }}>
                  <defs>
                    <linearGradient id="posGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#5FB39C" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#5FB39C" stopOpacity={0.05} />
                    </linearGradient>
                    <linearGradient id="negGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#D9737A" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#D9737A" stopOpacity={0.05} />
                    </linearGradient>
                    <linearGradient id="neuGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#94a3b8" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#94a3b8" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <XAxis
                    dataKey="date"
                    tick={false}
                    tickLine={false}
                    axisLine={false}
                    height={4}
                  />
                  <YAxis
                    tick={{ fontSize: 10, fill: isDark ? '#94a3b8' : '#64748b' }}
                    tickLine={false}
                    axisLine={false}
                    width={32}
                  />
                  <Tooltip
                    contentStyle={{
                      background: isDark ? '#1e293b' : '#fff',
                      border: isDark ? '1px solid #334155' : '1px solid #e2e8f0',
                      borderRadius: 8,
                      fontSize: 11,
                    }}
                    labelStyle={{ color: isDark ? '#cbd5e1' : '#475569' }}
                  />
                  <Area
                    type="monotone"
                    dataKey="neu"
                    stackId="1"
                    stroke="#94a3b8"
                    strokeWidth={1.5}
                    fill="url(#neuGrad)"
                    dot={false}
                    name="중립"
                  />
                  <Area
                    type="monotone"
                    dataKey="neg"
                    stackId="1"
                    stroke="#D9737A"
                    strokeWidth={1.5}
                    fill="url(#negGrad)"
                    dot={false}
                    name="부정"
                  />
                  <Area
                    type="monotone"
                    dataKey="pos"
                    stackId="1"
                    stroke="#5FB39C"
                    strokeWidth={1.5}
                    fill="url(#posGrad)"
                    dot={false}
                    name="긍정"
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className={`flex items-center justify-center h-full text-xs ${textMuted} text-center px-4`}>
                감성 데이터 연결 시 표시
              </div>
            )
          )}

          {activeTab === 'stock' && (
            stockPoints.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={stockPoints} margin={{ top: 2, right: 8, left: 4, bottom: 0 }}>
                  <XAxis
                    dataKey="date"
                    tick={false}
                    tickLine={false}
                    axisLine={false}
                    height={4}
                  />
                  <YAxis
                    tick={{ fontSize: 10, fill: isDark ? '#94a3b8' : '#64748b' }}
                    tickLine={false}
                    axisLine={false}
                    width={48}
                    domain={['dataMin', 'dataMax']}
                    tickFormatter={(v: number) =>
                      `${(v / 10000).toLocaleString('ko-KR', { maximumFractionDigits: 0 })}만`
                    }
                  />
                  <Tooltip
                    contentStyle={{
                      background: isDark ? '#1e293b' : '#fff',
                      border: isDark ? '1px solid #334155' : '1px solid #e2e8f0',
                      borderRadius: 8,
                      fontSize: 11,
                    }}
                    labelStyle={{ color: isDark ? '#cbd5e1' : '#475569' }}
                    itemStyle={{ color: '#2563eb' }}
                    formatter={(value) => [
                      (value as number).toLocaleString('ko-KR') + '원',
                      '종가',
                    ]}
                  />
                  <Line
                    type="monotone"
                    dataKey="close"
                    stroke="#2563eb"
                    strokeWidth={1.5}
                    dot={false}
                    activeDot={{ r: 3 }}
                    name="주가"
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className={`flex items-center justify-center h-full text-xs ${textMuted}`}>
                주가 데이터 연결 시 표시
              </div>
            )
          )}
        </div>
      </div>

      {/* 우측 슬롯: 핵심 관계 Top5 */}
      <div className="col-span-1 h-full">
        <RelationTopCard onFocusNode={onFocusNode} />
      </div>
    </div>
  );
}
