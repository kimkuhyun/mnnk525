# ADR 007 — FTC 파일명 멀티패턴 dispatch + 요약 필드명 교정

**날짜**: 2026-05-26
**상태**: Accepted

## 결정

`chunk/ftc.py` 의 단일 정규식 (`_RE_FNAME`) 을 6 종 파일명 패턴 dispatch 테이블 (`_FNAME_PATTERNS` + `_parse_fname`) 로 교체.
`_summarize_rows` 의 가짜 필드명을 실측 XML 응답 필드명으로 전면 교정.

## 배경

기존 `_RE_FNAME = re.compile(r"^([a-zA-Z]+)__(\d+)_([A-Z0-9]+)_p(\d+)\.xml$")` 는 1 종 패턴 (`name__YYYY_GROUP_pN.xml`) 만 매칭. FTC 14 endpoint 중 6+ endpoint 가 매치 실패 → 청크 누락. 또한 `_summarize_rows` 가 실제 응답에 없는 필드명 (`grupNm/hppyNm/cmpnCo/asetTotamt`, `compNm/exctvCo/asetTotamt/saleAmt` 등) 을 사용해 청크 텍스트가 빈값으로 들어가 검색 품질 즉시 타격.

## 6 종 파일명 패턴

| mode | 형태 | 해당 endpoint |
|---|---|---|
| year_group | `name__YYYY_GROUP_pN.xml` | affiliationCompSttusList, executiveCompSttusList, financeCompSttusList, stockholderCompSttusList, appnGroupAffiList, typeOfBusinessCompSttusList |
| year_only | `name__YYYY_pN.xml` | appnGroupSttusList |
| ym_jurirno | `name__YYYYMM_{jurirno13}_pN.xml` | holdingProgCompStusList |
| ym_only | `name__YYYYMM_pN.xml` | sllInnerQotaList, grupRotatInvstmntList, holdingGenFinCompSttusList, innerQotaEqltrmCmprAssetsList |
| group_only | `name__GROUP_pN.xml` | innerQotaEqltrmCmprUnityList |
| period_group | `name__YYYY_GROUP_pN.xml` | tyAssetsRentDelngDtlsList (year_group 과 동일 형태) |

dispatch 함수 `_parse_fname(name) → (endpoint, year|None, gid|None)` 로 통합. year/gid 가 None 가능하므로 `build_chunks` 에서 `int(year)` 가드 + `rcept_key` 폴백 (`(gid or f"{year or ''}_{endpoint}")[:14]`) 추가.

## 실측 응답 필드명 (전면 교정)

| endpoint | 잘못된 필드 (기존) | 실제 필드 (실측) |
|---|---|---|
| appnGroupSttusList | grupNm, hppyNm, cmpnCo, asetTotamt | unityGrupNm, unityGrupCode, smerNm, repreCmpny, sumCmpnyCo, entrprsCl |
| affiliationCompSttusList | entrprsNm, rprsntvNm, indutyNm (OK) | + indutyCode, ordtmEmplyCo, fondDe |
| appnGroupAffiList | compNm, indtyNm | entrprsNm, jurirno, rprsntvNm, grinil |
| executiveCompSttusList | compNm, exctvCo | entrprsNm, exctvNm, ofcpsNm (회사별 임원 집계 방식) |
| financeCompSttusList | compNm, asetTotamt, saleAmt | entrprsNm, assetsTotamt, caplTotamt, debtTotamt, selngAmount, thstrmNtpfAmount, stacntDudt |
| stockholderCompSttusList | (전용 없음) | entrprsNm, shrholdrNm, shrholdrSe, allQotaRate, posesnStockCo |
| innerQotaEqltrmCmprUnityList | (전용 없음) | presentnYear, caplAmount, smerCaplAmount, entrprsCaplAmount, tesstkCaplAmount |
| tyAssetsRentDelngDtlsList | (전용 없음) | entrprsNm, psitnCmpnyChangeSeCode, incrprDe, exclDe, postpneBeginDe |

금액 필드는 `_fmt_amt` 헬퍼로 억/만 단위 변환 (자산 12300000000 → "123억").

## 근거

- 청크 텍스트가 빈값이면 임베딩 noise → Recall 즉시 하락
- 카탈로그 (`docs/APIdocs/API_메타카탈로그.xlsx`) + 실측 raw XML (`data/rawData/_common/ftc/`) 양방향 검증
- dispatch 테이블 방식 → 신규 endpoint 추가 시 패턴만 1 줄 추가 (확장성)

## 영향 받는 코드

- `src/polaris/chunk/ftc.py` — `_FNAME_PATTERNS`, `_parse_fname`, `_fmt_amt`, `_summarize_rows` 전면 재작성, `build_chunks` 매칭 부분 + main() INSERT/payload `rcept_key` 사용
- `src/polaris/ingest/bulk_collect.py` — KRX `Change=NaN` 가드 (`_safe_float`/`_safe_int`)

## 검증 시나리오

1. **회귀 방지**: `polaris verify` 기존 10/10 PASS 유지
2. **청크 카운트 회복** (MariaDB):
   ```sql
   SELECT chunk_type, COUNT(*) FROM chunk_index WHERE chunk_type='ftc_meta';
   ```
   수정 전 ~소수 → 수정 후 수십~수백 증가 기대 (year_only/ym_only/group_only 패턴 신규 인식)
3. **샘플 텍스트 점검**:
   ```sql
   SELECT chunk_id, LEFT(embedding_text, 300)
   FROM chunk_index WHERE chunk_type='ftc_meta' LIMIT 5;
   ```
   - 빈 필드 `( / 대표  / )` 같은 패턴이 사라져야 함
   - 실제 회사명·대표·업종이 채워져야 함
4. **재임베딩**: 청크 텍스트 변경 → `chunk_id` 동일하지만 의미 변경 → `ingest_status='pending'` 강제 후 재임베딩 필요. 별도 admin 명령으로 처리

## 트레이드오프

- ❌ 잃는 것: `cid = _hash16("ftc", endpoint, year, gid)` → `_hash16("ftc", endpoint, year or "", gid or "")` 로 변경. 기존 청크 ID 일부 (year_only/ym_only) 가 변경 가능성 — Blue/Green 새 슬롯에서 재적재 필요
- ✅ 얻는 것: 14 endpoint 100% 인식, 청크 텍스트 의미 회복, 신규 endpoint 확장성
