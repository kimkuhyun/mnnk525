# ADR 006 — PDF 다운로드를 사업·반기·분기 보고서 3종으로 제한

**날짜**: 2026-05-25
**상태**: Accepted

## 결정

`bulk_collect.collect_documents` 가 다운로드하는 PDF/HTML 을 **사업보고서 · 반기보고서 · 분기보고서 3종만** 으로 제한.

나머지 공시 (자기주식·임원변동·정정공시·대규모기업집단·주주총회 등) 는 **DART JSON 으로만** 수집.

## 대안 (기각)

| 대안 | 기각 이유 |
|---|---|
| catalog/8 KEEP 37종 (이전 정책) | 자기주식·정정 등 PDF 50~500GB 부담. 검색·평가에 실제 안 쓰임 |
| 모든 공시 PDF 다운로드 | 회사당 100건+ 공시 → 한 회사 1시간+ 소요. 디스크 폭증 |
| HTML 만 (PDF 제외) | HTML 도 같이 받으니 구분 의미 없음. 사용자 원본 보기 시 PDF 가 더 유용 |

## 근거

- **RAG 검색·평가에 사용되는 건 DART JSON 정형 + HTML 본문 텍스트뿐**. PDF 는 사용자 "원본 보기" 용
- 사업·반기·분기 보고서가 회사 정보의 95% (재무·사업현황·리스크·임원·연구개발)
- 그 외 공시는 DART JSON 에 핵심 데이터 있어 PDF 불필요 (예: 임원 명단은 `exctvSttus` JSON)

## 영향 받는 코드

- `bulk_collect._is_key_report` 단순화: `any(t in report_nm for t in ("사업보고서", "반기보고서", "분기보고서"))`
- `KEY_REPORT_KEYWORDS`, `CATALOG_KEEP_SET` 무시 (코드 유지, fallback 으로만)
- `scripts/cleanup_documents.py` 신규 — 기존 PDF 정리 (7사 합쳐 148개 제거)

## 결과

- DB하이텍 documents: 42개 → 5개 (사업 1 + 반기 1 + 분기 3)
- 7사 합계: 178개 → 30개

## 트레이드오프

- ❌ 잃는 것: 자기주식·정정공시 원문 PDF 빠른 접근. 단 DART API 로 언제든 다시 다운로드 가능
- ✅ 얻는 것: 디스크 절약 (~수십GB), 회사 추가 시간 5배 단축
