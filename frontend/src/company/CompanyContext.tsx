import { createContext, useContext, useState } from 'react'
import type { ReactNode } from 'react'

export interface Company { code: string; name: string }

// 1차 시드 3사. corp_code 는 pola corps.json 확정값.
export const COMPANIES: Company[] = [
  { code: '00126380', name: '삼성전자' },
  { code: '00164779', name: 'SK하이닉스' },
  { code: '00161383', name: '한미반도체' }, // 00164742 는 현대차였음 — 정정
]

interface CompanyCtx { company: Company; setCompany: (c: Company) => void }
const Ctx = createContext<CompanyCtx>({ company: COMPANIES[0], setCompany: () => {} })

export function CompanyProvider({ children }: { children: ReactNode }) {
  const [company, setCompany] = useState<Company>(COMPANIES[0])
  return <Ctx.Provider value={{ company, setCompany }}>{children}</Ctx.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export const useCompany = () => useContext(Ctx)
