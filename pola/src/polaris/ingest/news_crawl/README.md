# 뉴스 크롤러 (`news_crawl`)

RSS는 최근분만 노출 → 과거(2026-01-01~) 수집 불가. 그래서 언론사 섹션 목록을 직접
페이지네이션하며 기사 URL을 모으고, **Readability**로 본문을 통일 추출해 `news_raw`에 적재한다.
**증분**: 이미 받은 기사는 건너뛰므로 매일 돌려도 신규만 쌓인다.

## 구조
```
browser.py   Playwright 세션 (CDP attach 우선 / headless launch 폴백)
sources.py   언론사 × 섹션 정의 (목록 URL · 링크 셀렉터)   ← 새 언론사는 여기만 추가
collect.py   섹션 목록 페이지네이션 → 기사 URL 수집 (증분 조기종료)
extract.py   페이지 → Readability 본문 + og/JSON-LD 메타
store.py     news_raw upsert (news_id = sha1(url)[:16])
run.py       CLI 오케스트레이션
```

## 1) 크롬을 디버그 모드로 띄우기  (팀 공용 — 각자 자기 크롬)
크롤러는 아래 크롬 세션에 **attach**한다. 평소처럼 로그인·탐색해도 된다.

**Windows (PowerShell)**
```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 --user-data-dir="$env:TEMP\polaris_chrome"
```
> 크롬을 안 띄워두면 크롤러가 자동으로 headless 브라우저를 띄운다(혼자 빠르게 돌릴 때).

## 2) 실행
```powershell
uv run python -m polaris.ingest.news_crawl.run --since 2026-01-01 --sources 전자신문 --sections "산업/IT"
```
| 옵션 | 설명 |
|---|---|
| `--since` | 이 날짜부터 (기본 `2026-01-01`) |
| `--sources` | 언론사 필터 (생략 시 전체) |
| `--sections` | 분야 필터 (생략 시 전체) |
| `--full` | 증분 끄고 전체 재수집 |
| `--cdp` | CDP 주소 (기본 `http://localhost:9222`) |

## 3) 새 언론사/섹션 추가
`sources.py` 의 `SOURCES` 에 `Section(...)` 한 줄 추가. `list_url`(페이지네이션 템플릿)과
`link_selector`(기사 링크 CSS)만 채우면 나머지(collect/extract/store)는 그대로 동작.

## ⚠️ 현재 상태 (골격)
- 공통부(browser/collect/extract/store/run)는 동작.
- `sources.py` 의 전자신문 `list_url`·`link_selector` 는 **실제 사이트 확인 후 검증 필요**.
  첫 슬라이스(전자신문 산업/IT) 동작 확인 → 나머지 3사·섹션을 같은 패턴으로 복제.
