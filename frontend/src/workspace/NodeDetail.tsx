// 노드 상세 패널 — 우측 슬롯 (ActivityTimeline 대체)
// 노드 클릭 시: 이름·kind 배지 + DART 프로파일(있으면) + "왜 포착됐나"(relations) + 근거 기사(evidence)
// 시드 회사면 "이 회사 관계도로 보기" 버튼으로 center 전환.
// selectedId 없으면 안내문.

import { ExternalLink } from 'lucide-react'
import {
  LineChart,
  Line,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'
import { useNodeDetail } from '../api/hooks'
import { useCompany, COMPANIES } from '../company/CompanyContext'
import { GROUP_COLOR, GROUP_LABEL } from '../lib/relations'
import { useTheme } from '../theme/ThemeContext'
import type { NodeKind, RelationGroup } from '../types'

// 시드 회사 corp_code — 회사 선택 목록(CompanyContext SSOT)에서 파생
const SEED_CODES = new Set(COMPANIES.map((c) => c.code))

interface Props {
  selectedId: string | null
  onOpenEvidence?: (nodeId: string, nodeName: string) => void
}

// kind 한국어 배지 라벨
const KIND_LABEL: Record<NodeKind, string> = {
  seed: '중심',
  org: '회사',
  news_entity: '뉴스 엔티티',
  person: '인물',
  product: '제품',
  meta: '그룹',
}

// kind 배지 색 (배경 muted)
const KIND_BG: Record<NodeKind, string> = {
  seed: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  org: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  news_entity: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  person: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
  product: 'bg-teal-100 text-teal-700 dark:bg-teal-900/40 dark:text-teal-300',
  meta: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400',
}

const sectionTitle = 'text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-2.5'
const cardClass = 'rounded-xl border border-slate-200/80 bg-white dark:border-slate-800 dark:bg-slate-900 p-4'

// 주가 등락 색상
function changePctColor(v: number | undefined, isDark: boolean) {
  if (v === undefined) return isDark ? 'text-slate-400' : 'text-slate-500'
  if (v > 0) return 'text-emerald-600 dark:text-emerald-400'
  if (v < 0) return 'text-rose-600 dark:text-rose-400'
  return isDark ? 'text-slate-400' : 'text-slate-500'
}

export default function NodeDetail({ selectedId, onOpenEvidence }: Props) {
  const { company, setCompany } = useCompany()
  const { theme } = useTheme()
  const { data, isLoading, isError } = useNodeDetail(company.code, selectedId)
  const isDark = theme === 'dark'

  // 선택 없음
  if (!selectedId) {
    return (
      <aside className="h-full overflow-y-auto border-l border-slate-200/80 bg-white dark:border-slate-800 dark:bg-slate-900 flex flex-col">
        <div className="sticky top-0 z-10 flex items-center px-4 py-3 border-b border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900">
          <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">노드 상세</span>
        </div>
        <div className="flex flex-1 items-center justify-center px-4 py-10 text-xs text-slate-400 dark:text-slate-500 text-center">
          그래프에서 노드를 클릭하면 상세 정보가 표시됩니다
        </div>
      </aside>
    )
  }

  // 로딩
  if (isLoading) {
    return (
      <aside className="h-full overflow-y-auto border-l border-slate-200/80 bg-white dark:border-slate-800 dark:bg-slate-900 flex flex-col">
        <div className="sticky top-0 z-10 flex items-center px-4 py-3 border-b border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900">
          <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">노드 상세</span>
        </div>
        <div className="flex flex-1 items-center justify-center px-4 py-10 text-xs text-slate-400 dark:text-slate-500 text-center">
          불러오는 중...
        </div>
      </aside>
    )
  }

  // 오류 또는 데이터 없음
  if (isError || !data) {
    return (
      <aside className="h-full overflow-y-auto border-l border-slate-200/80 bg-white dark:border-slate-800 dark:bg-slate-900 flex flex-col">
        <div className="sticky top-0 z-10 flex items-center px-4 py-3 border-b border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900">
          <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">노드 상세</span>
        </div>
        <div className="flex flex-1 items-center justify-center px-4 py-10 text-xs text-slate-400 dark:text-slate-500 text-center">
          상세 데이터 연결 시 표시됩니다
        </div>
      </aside>
    )
  }

  const kindLabel = KIND_LABEL[data.kind] ?? data.kind
  const kindBg = KIND_BG[data.kind] ?? KIND_BG.org
  const isSeedNode = data.isSeed || SEED_CODES.has(data.id)

  // "이 회사 관계도로 보기" 클릭 — COMPANIES 목록에서 찾아 setCompany
  const handleSwitchCenter = () => {
    const found = COMPANIES.find((c) => c.code === data.id)
    if (found) setCompany(found)
  }

  const profile = data.profile

  // spark 데이터 변환 (LineChart용)
  const sparkData = profile?.stock?.spark.map((v, i) => ({ i, v })) ?? []

  return (
    <aside className="h-full overflow-y-auto border-l border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 flex flex-col">
      {/* 헤더 */}
      <div className="sticky top-0 z-10 border-b border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-3 space-y-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">
            {data.name}
          </span>
          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${kindBg}`}>
            {kindLabel}
          </span>
          <button
            onClick={() => onOpenEvidence?.(data.id, data.name)}
            className="ml-auto text-xs text-blue-600 dark:text-blue-400 hover:underline"
          >
            자세히
          </button>
        </div>
        {isSeedNode && (
          <button
            onClick={handleSwitchCenter}
            className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
          >
            이 회사 관계도로 보기
          </button>
        )}
      </div>

      <div className="flex flex-col gap-4 px-4 py-4">
        {/* 회사 프로파일 (있을 때만) — 사실 데이터 전면 배치 */}
        {profile && (
          <>
            {/* 개요 (overview KV) */}
            {profile.overview.length > 0 && (
              <div className={cardClass}>
                <p className={sectionTitle}>개요</p>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                  {profile.overview.map((kv, i) => (
                    <div key={i} className="contents">
                      <span className="text-xs text-slate-500 dark:text-slate-400">{kv.label}</span>
                      <span className="text-xs tabular-nums text-slate-700 dark:text-slate-200 text-right">
                        {kv.value}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 주가 요약 */}
            {profile.stock && (
              <div className={cardClass}>
                <p className={sectionTitle}>주가</p>
                <div className="flex items-center gap-3">
                  <div className="flex flex-col">
                    <span className="text-lg font-bold tabular-nums text-slate-800 dark:text-slate-100">
                      {profile.stock.lastClose.toLocaleString('ko-KR')}원
                    </span>
                    {profile.stock.changePct != null && (
                      <span className={`text-xs tabular-nums ${changePctColor(profile.stock.changePct, isDark)}`}>
                        {profile.stock.changePct > 0 ? '+' : ''}
                        {profile.stock.changePct.toFixed(2)}%
                      </span>
                    )}
                    <span className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
                      기준 {profile.stock.asOf}
                    </span>
                  </div>
                  {sparkData.length > 0 && (
                    <div className="flex-1 h-12">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={sparkData}>
                          <Tooltip
                            contentStyle={{
                              background: isDark ? '#1e293b' : '#fff',
                              border: isDark ? '1px solid #334155' : '1px solid #e2e8f0',
                              borderRadius: 6,
                              fontSize: 10,
                            }}
                            formatter={(v) => [`${(v as number).toLocaleString('ko-KR')}원`, '종가']}
                          />
                          <Line
                            type="monotone"
                            dataKey="v"
                            stroke="#2563eb"
                            strokeWidth={1.5}
                            dot={false}
                            activeDot={{ r: 2 }}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 재무 하이라이트 */}
            {profile.finance.length > 0 && (
              <div className={cardClass}>
                <p className={sectionTitle}>재무</p>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                  {profile.finance.map((f, i) => (
                    <div key={i} className="contents">
                      <span className="text-xs text-slate-500 dark:text-slate-400">{f.label}</span>
                      <span className="text-sm tabular-nums text-slate-700 dark:text-slate-200 text-right">
                        {f.value}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 임원 */}
            {profile.execs.length > 0 && (
              <div className={cardClass}>
                <p className={sectionTitle}>임원</p>
                <ul className="space-y-1">
                  {profile.execs.map((e, i) => (
                    <li key={i} className="flex items-center gap-2">
                      <span className="text-sm text-slate-700 dark:text-slate-200">{e.name}</span>
                      {e.position && (
                        <span className="text-xs text-slate-500 dark:text-slate-400">{e.position}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* 자회사/지분 */}
            {profile.subsidiaries.length > 0 && (
              <div className={cardClass}>
                <p className={sectionTitle}>자회사 · 지분</p>
                <ul className="space-y-1">
                  {profile.subsidiaries.map((s, i) => (
                    <li key={i} className="flex items-center justify-between">
                      <span className="text-sm text-slate-700 dark:text-slate-200 truncate">{s.name}</span>
                      {s.stake != null && (
                        <span className="text-xs tabular-nums text-slate-500 dark:text-slate-400 ml-2 shrink-0">
                          {s.stake >= 1 ? s.stake.toFixed(1) : s.stake.toFixed(2)}%
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* 대주주 */}
            {profile.shareholders.length > 0 && (
              <div className={cardClass}>
                <p className={sectionTitle}>대주주</p>
                <ul className="space-y-1">
                  {profile.shareholders.map((sh, i) => (
                    <li key={i} className="flex items-center justify-between">
                      <span className="text-sm text-slate-700 dark:text-slate-200 truncate">{sh.name}</span>
                      {sh.stake != null && (
                        <span className="text-xs tabular-nums text-slate-500 dark:text-slate-400 ml-2 shrink-0">
                          {sh.stake >= 1 ? sh.stake.toFixed(1) : sh.stake.toFixed(2)}%
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* 제품 */}
            {profile.products.length > 0 && (
              <div className={cardClass}>
                <p className={sectionTitle}>주요 제품</p>
                <div className="flex flex-wrap gap-1.5">
                  {profile.products.map((p, i) => (
                    <span
                      key={i}
                      className="rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-xs text-slate-600 dark:text-slate-300"
                    >
                      {p}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* 분쟁 */}
            {profile.disputes.length > 0 && (
              <div className={cardClass}>
                <p className={sectionTitle}>분쟁 · 소송</p>
                <ul className="space-y-1">
                  {profile.disputes.map((d, i) => (
                    <li key={i} className="flex items-center justify-between">
                      <span className="text-sm text-slate-700 dark:text-slate-200 truncate">{d.target}</span>
                      <span className="text-xs tabular-nums text-slate-500 dark:text-slate-400 ml-2 shrink-0">
                        근거 {d.evidenceCount}건
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* 최근 뉴스 */}
            {profile.recentNews && profile.recentNews.length > 0 && (
              <div className={cardClass}>
                <p className={sectionTitle}>최근 뉴스</p>
                <ul className="space-y-2">
                  {profile.recentNews.map((n) => (
                    <li key={n.docId} className="border-b border-slate-100 dark:border-slate-800 pb-2 last:border-b-0 last:pb-0">
                      <a
                        href={n.url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-start gap-1 text-xs font-medium text-slate-700 dark:text-slate-200 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                      >
                        <span className="line-clamp-2">{n.title}</span>
                        <ExternalLink size={11} className="mt-0.5 shrink-0" />
                      </a>
                      <div className="mt-0.5 flex flex-wrap gap-2 text-xs text-slate-400 dark:text-slate-500">
                        <span className="tabular-nums">{n.date}</span>
                        {n.publisher && <span>· {n.publisher}</span>}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}

        {/* 왜 포착됐나 — relations */}
        <div className={cardClass}>
          <p className={sectionTitle}>왜 포착됐나</p>
          {data.relations.length === 0 ? (
            <p className="text-xs text-slate-400 dark:text-slate-500">관계 데이터 연결 시 표시됩니다</p>
          ) : (
            <ul className="space-y-2">
              {data.relations.map((rel, idx) => {
                const chipColor = GROUP_COLOR[rel.group as RelationGroup] ?? '#94a3b8'
                const groupLabel = GROUP_LABEL[rel.group as RelationGroup] ?? rel.group
                return (
                  <li key={idx} className="flex flex-col gap-0.5">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span
                        className="rounded-full px-2 py-0.5 text-xs font-medium text-white"
                        style={{ backgroundColor: chipColor }}
                      >
                        {groupLabel}
                      </span>
                      <span className="text-sm text-slate-700 dark:text-slate-200">
                        {rel.predicate}
                        {rel.directed ? '' : ' (양방향)'}
                      </span>
                      {/* 출처 뱃지 — 공시·사실(DART) / 언급(뉴스) */}
                      {rel.source === 'dart' ? (
                        <span className="rounded-full px-2 py-0.5 text-[11px] font-medium bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400">
                          공시·사실
                        </span>
                      ) : (
                        <span className="rounded-full px-2 py-0.5 text-[11px] font-medium bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                          언급
                        </span>
                      )}
                    </div>
                    <span className="text-xs tabular-nums text-slate-400 dark:text-slate-500">
                      {rel.source === 'dart' ? '근거' : '언급'} {rel.evidenceCount}건
                    </span>
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        {/* 기사 */}
        <div className={cardClass}>
          <p className={sectionTitle}>기사</p>
          {data.evidence.length === 0 ? (
            <p className="text-xs text-slate-400 dark:text-slate-500">기사 연결 시 표시됩니다</p>
          ) : (
            <ul className="space-y-3">
              {data.evidence.map((item) => (
                <li
                  key={item.docId}
                  className="border-b border-slate-100 dark:border-slate-800 pb-3 last:border-b-0 last:pb-0"
                >
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
      </div>
    </aside>
  )
}
