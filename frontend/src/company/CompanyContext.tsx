import { createContext, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { getCompanies } from '../api/client'

export interface Company { code: string; name: string }

// 초기값/오프라인 폴백. 라이브 목록은 백엔드 GET /api/companies (relations.SEED_CORPS) 가 SSOT.
export const COMPANIES: Company[] = [
  { code: '00126380', name: '삼성전자' },
  { code: '00164779', name: 'SK하이닉스' },
  { code: '00161383', name: '한미반도체' },
]

interface CompanyCtx { company: Company; setCompany: (c: Company) => void; companies: Company[] }
const Ctx = createContext<CompanyCtx>({ company: COMPANIES[0], setCompany: () => {}, companies: COMPANIES })

export function CompanyProvider({ children }: { children: ReactNode }) {
  const [companies, setCompanies] = useState<Company[]>(COMPANIES)
  const [company, setCompany] = useState<Company>(COMPANIES[0])
  useEffect(() => {
    getCompanies()
      .then((list) => { if (Array.isArray(list) && list.length) setCompanies(list) })
      .catch(() => { /* 백엔드 미가동 시 폴백(COMPANIES) 유지 */ })
  }, [])
  return <Ctx.Provider value={{ company, setCompany, companies }}>{children}</Ctx.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export const useCompany = () => useContext(Ctx)
