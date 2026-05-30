import type { RelationGroup } from '../types'

// 관계 6그룹의 단일 출처(SSOT): 라벨·색(엣지 전용 의미색)·백엔드 predicate 매핑.
export interface RelationMeta {
  key: RelationGroup
  label: string
  color: string
  predicates: string[]
}

// 뮤트 팔레트 — 동일 채도·명도로 묶어 형형색색 X, 차분·고급 (Carbon/Cloudscape 데이터비주얼 가이드)
export const RELATION_GROUPS: RelationMeta[] = [
  { key: 'supply', label: '공급망', color: '#5E9BD1', predicates: ['SUPPLIES', 'CUSTOMER_OF'] },
  { key: 'compete', label: '경쟁', color: '#D9737A', predicates: ['COMPETES_WITH'] },
  { key: 'partner', label: '협력', color: '#5FB39C', predicates: ['PARTNERS_WITH', 'JV_WITH', 'LICENSES'] },
  { key: 'invest', label: '투자·인수', color: '#9B86CB', predicates: ['INVESTS_IN', 'ACQUIRES'] },
  { key: 'govern', label: '지배구조', color: '#8E99A8', predicates: ['IS_SUBSIDIARY_OF', 'IS_MAJOR_SHAREHOLDER_OF', 'AFFILIATED_WITH'] },
  { key: 'dispute', label: '분쟁', color: '#E0A45E', predicates: ['LITIGATION'] },
]

export const GROUP_COLOR = Object.fromEntries(
  RELATION_GROUPS.map((g) => [g.key, g.color]),
) as Record<RelationGroup, string>

export const GROUP_LABEL = Object.fromEntries(
  RELATION_GROUPS.map((g) => [g.key, g.label]),
) as Record<RelationGroup, string>
