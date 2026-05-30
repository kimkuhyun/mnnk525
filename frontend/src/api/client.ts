// 백엔드 호출 공통 래퍼. 사용 예: const data = await api<{status:string}>('/health')
const BASE = import.meta.env.VITE_API_BASE_URL || '/api'

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`)
  return res.json() as Promise<T>
}

// 화면별 호출은 여기에 모으면 됨:
// export const getDbStatus = () => api<Record<string,string>>('/db/status')
// export const getMentionDaily = (corp: string) => api(`/dashboard/mentions?corp=${corp}`)
