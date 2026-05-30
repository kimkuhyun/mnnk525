# ADR 004 — RDB 본문 저장 (news + DART JSON) SSOT 화

**날짜**: 2026-05-25
**상태**: Accepted

## 결정

뉴스 본문과 DART JSON 원문을 **MariaDB 가 단일 진실원 (SSOT)** 으로 보관.

- `news_raw.body` (LONGTEXT) — 뉴스 원문 + meta JSON
- `dart_raw_index.body_json` (LONGTEXT) — DART JSON 원문

raw 파일 (`data/rawData/_common/news/*.json`, `data/rawData/{cc}/dart/*.json`) 은 **백업·캐시** 위치로 격하.

## 대안 (기각)

| 대안 | 기각 이유 |
|---|---|
| 파일만 (이전 정책) | 본문 검색 시 매번 파일 scan, 백업 이중 (DB + 파일), 신선도 비교 어려움 |
| 파일 + 청크 (1500자 잘림) | SSOT 불명확. 잘린 청크 → 원문 복구 못 함 |
| Object storage (S3/MinIO) | 뉴스 (수MB), DART JSON (수GB) 규모엔 과함. PDF (50~500GB) 라면 고려 |

## 결과

- `bulk_collect` 가 새 뉴스/DART 받을 때 파일 + RDB 동시 저장
- 기존 데이터는 `polaris.admin.migrate_news_to_rdb` / `migrate_dart_to_rdb` 로 일괄 import
- `verify` 09·10 체크가 RDB 본문 정합 보증

## 영향 받는 코드

- `init_mariadb.sql` — `news_raw` 테이블 + `dart_raw_index.body_json` 컬럼 추가
- `bulk_collect.py` — `_news_raw_insert` 헬퍼, news 수집 시 호출
- `load_mariadb.load_dart_raw_index` — body_json 함께 INSERT
- `stage_b4_news.py` (deprecation 후) / `chunk/news.py` — RDB 에서 본문 SELECT
