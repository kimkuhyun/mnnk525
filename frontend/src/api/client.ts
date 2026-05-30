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

// 활성 회사 목록 (회사 선택기 SSOT — 백엔드 relations.SEED_CORPS)
export const getCompanies = () => api<{ code: string; name: string }[]>('/companies')
