// 대시보드 — web/dashboard.html 와이어프레임을 참고해 위젯 구현.
// 데이터: src/api/client.ts 의 api() 로 백엔드 호출.
export default function Dashboard() {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">대시보드</h1>
      <p className="text-sm text-slate-500">
        web/dashboard.html 참고 · 위젯: 브리핑 / KPI / 멘션추이 / 감성 / 토픽 / 관계지도 / 시그널 / 근거
      </p>
      <div className="border-2 border-dashed border-slate-300 rounded-xl bg-white h-48 grid place-items-center text-slate-400 text-sm">
        위젯 영역 — api('/dashboard/…') 로 mention_daily · topic_daily · Neo4j 호출
      </div>
    </div>
  )
}
