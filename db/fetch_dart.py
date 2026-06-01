"""POLARIS — DART 공시 raw 수집기.

삼성전자·SK하이닉스·한미반도체의 2024-01-01 ~ 2026-06-01 공시 전체를 받아
db/raw/{회사명}/ 아래에 저장한다. 재실행 시 이미 받은 파일은 건너뛴다(resumable).

저장 구조:
  raw/{회사명}/
    company.json                       기업개황
    list/list_{page}.json              공시검색(전체 페이지)
    ds002/{endpoint}__{year}_{reprt}.json   사업보고서 주요정보(정기보고서)
    ds003/{endpoint}__...json               재무
    ds004/{endpoint}.json                   지분 보고
    ds005/{endpoint}.json                   주요사항보고서
    documents/{rcept_no}.zip                공시서류 원본(XML/HTML 압축)

실행: uv run python fetch_dart.py            (전체)
      uv run python fetch_dart.py --no-docs  (원본 zip 제외, API만)
      uv run python fetch_dart.py --only-docs (원본 zip만)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
ENV = dotenv_values(HERE / ".env")

API_KEY = (ENV.get("DART_API_KEY") or "").strip()
BASE = "https://opendart.fss.or.kr/api"

BGN_DE = "20240101"
END_DE = "20260601"

# ── 속도 제한 (DART 차단 방지) ───────────────────────────────────
# 2026-06-01: 원본 zip 을 무딜레이로 ~1000건 연속 요청 → DART 가 키/IP 를
# 강제 차단(WinError 10054)했음. 두 단계로 막는다:
#   (1) 요청 간 최소 간격(아래 *_INTERVAL)
#   (2) 최근 60초 내 요청 수 상한(MAX_PER_MIN) — 롤링 윈도우. 분당 1000회를
#       절대 넘지 않도록 안전 마진 두고 900 으로 캡. 넘으면 가장 오래된 요청이
#       60초 창을 벗어날 때까지 강제 대기.
from collections import deque

JSON_INTERVAL = 0.25   # JSON API 요청 간 최소 간격(초)
DOC_INTERVAL = 0.6     # 원본 zip/PDF 요청 간 최소 간격(초)
BLOCK_COOLDOWN = 120   # 연결 강제종료(차단 의심) 시 대기(초)
MAX_PER_MIN = 900      # 60초당 요청 상한(분당 1000 미만 보장, 마진 100)

_last_req = 0.0
_req_times: deque[float] = deque()


def throttle(interval: float) -> None:
    """요청 직전 호출: (1) 최소 간격 + (2) 분당 상한 둘 다 보장."""
    global _last_req
    now = time.monotonic()
    wait = interval - (now - _last_req)
    if wait > 0:
        time.sleep(wait)
        now = time.monotonic()
    # 롤링 60초 윈도우 정리
    while _req_times and now - _req_times[0] > 60:
        _req_times.popleft()
    if len(_req_times) >= MAX_PER_MIN:
        sleep_for = 60 - (now - _req_times[0]) + 0.05
        if sleep_for > 0:
            log(f"    … 분당 상한({MAX_PER_MIN}/min) 도달 — {sleep_for:.1f}s 대기")
            time.sleep(sleep_for)
            now = time.monotonic()
        while _req_times and now - _req_times[0] > 60:
            _req_times.popleft()
    _req_times.append(now)
    _last_req = now
YEARS = ["2024", "2025", "2026"]
REPRT_CODES = ["11013", "11012", "11014", "11011"]  # 1분기/반기/3분기/사업보고서

CORPS: list[tuple[str, str]] = []  # (corp_code, 회사명)

# ── 엔드포인트 그룹 ───────────────────────────────────────────────
# 정기보고서 기반 (corp_code, bsns_year, reprt_code)
DS002 = [
    "irdsSttus", "alotMatter", "tesstkAcqsDspsSttus", "hyslrSttus",
    "hyslrChgSttus", "mrhlSttus", "exctvSttus", "empSttus",
    "hmvAuditAllSttus", "hmvAuditIndvdlBySttus", "indvdlByPay",
    "otrCprInvstmntSttus", "pssrpCptalUseDtls", "prvsrpCptalUseDtls",
    "entrprsBilScritsNrdmpBlce", "srtpdPsndbtNrdmpBlce",
    "cprndNrdmpBlce", "detScritsIsuAcmslt", "newCaplScritsNrdmpBlce",
    "cndlCaplScritsNrdmpBlce", "accnutAdtorNmNdAdtOpinion",
    "adtServcCnclsSttus", "accnutAdtorNonAdtServcCnclsSttus",
    "outcmpnyDrctrNdChangeSttus", "drctrAdtAllMendngSttusGmtsckConfmAmount",
    "drctrAdtAllMendngSttusMendngPymntamtTyCl", "unrstExctvMendngSttus",
]
# 재무 — 계정 (corp_code, bsns_year, reprt_code [, fs_div])
DS003_ACNT = ["fnlttSinglAcnt"]
DS003_ALL_FS = ["OFS", "CFS"]  # fnlttSinglAcntAll 의 fs_div
DS003_INDX_CODES = ["M210000", "M220000", "M230000", "M240000"]  # 수익/안정/성장/활동
# 지분 보고 (corp_code 만)
DS004 = ["majorstock", "elestock"]
# 주요사항보고서 (corp_code, bgn_de, end_de)
DS005 = [
    "tsstkAqDecsn", "tsstkDpDecsn", "tsstkAqTrctrCcDecsn",
    "tsstkAqTrctrCnsDecsn", "piicDecsn", "fricDecsn", "pifricDecsn", "crDecsn",
    "bnkMngtPcbg", "wdCocobdIsDecsn", "astInhtrfEtcPtbkOpt",
    "otcprStkInvscrInhDecsn", "otcprStkInvscrTrfDecsn", "stkExtrDecsn",
    "cmpDvDecsn", "cmpDvmgDecsn", "cmpMgDecsn", "exbdIsDecsn",
    "bdwtIsDecsn", "cvbdIsDecsn", "lwstLg", "bsnInhDecsn", "bsnTrfDecsn",
    "tgastInhDecsn", "tgastTrfDecsn", "bsnSp", "dfOcr", "ctrcvsBgrq",
    "dsRsOcr", "ovLstDecsn",
]


def log(msg: str) -> None:
    print(msg, flush=True)


def get_json(client: httpx.Client, endpoint: str, params: dict) -> dict | None:
    """DART JSON 호출. status 코드별 처리. 성공 시 dict, 데이터없음/실패 시 None."""
    p = {"crtfc_key": API_KEY, **params}
    for attempt in range(4):
        throttle(JSON_INTERVAL)
        try:
            r = client.get(f"{BASE}/{endpoint}.json", params=p, timeout=30)
            r.raise_for_status()
            data = r.json()
        except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as e:
            # 연결 강제종료 = DART 차단 의심 → 길게 대기
            log(f"    ! {endpoint} 차단 의심({type(e).__name__}) {BLOCK_COOLDOWN}s 대기")
            time.sleep(BLOCK_COOLDOWN)
            continue
        except Exception as e:  # noqa: BLE001
            log(f"    ! {endpoint} 재시도 {attempt+1}: {e}")
            time.sleep(2 * (attempt + 1))
            continue
        status = data.get("status")
        if status == "000":
            return data
        if status == "013":  # 조회 데이터 없음
            return None
        if status in {"020", "021"}:  # 사용한도 초과 / 분당 한도
            log(f"    … 한도({status}) 대기 60s")
            time.sleep(60)
            continue
        # 그 외(010 키오류 등)는 기록만
        log(f"    ! {endpoint} status={status} {data.get('message')}")
        return None
    return None


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def is_periodic(report_nm: str) -> bool:
    """정기보고서(사업·반기·분기) 판별. [기재정정] 등 접두사 무관하게 부분일치."""
    return any(k in report_nm for k in ("사업보고서", "반기보고서", "분기보고서"))


def fetch_list(client: httpx.Client, corp_code: str, out: Path) -> list[dict]:
    """공시검색 전체 페이지. 공시 item(dict) 목록 반환."""
    ldir = out / "list"
    items: list[dict] = []
    page = 1
    total_pages = 1
    while page <= total_pages:
        f = ldir / f"list_{page:03d}.json"
        if f.exists():
            data = json.loads(f.read_text(encoding="utf-8"))
        else:
            data = get_json(client, "list", {
                "corp_code": corp_code, "bgn_de": BGN_DE, "end_de": END_DE,
                "page_no": page, "page_count": 100,
            })
            if data is None:
                break
            save(f, data)
        total_pages = int(data.get("total_page", 1) or 1)
        items.extend(data.get("list", []))
        log(f"    list p{page}/{total_pages} (+{len(data.get('list', []))})")
        page += 1
    return items


def fetch_apis(client: httpx.Client, corp_code: str, out: Path) -> None:
    # company
    f = out / "company.json"
    if not f.exists():
        d = get_json(client, "company", {"corp_code": corp_code})
        if d:
            save(f, d)

    # DS002 정기보고서 주요정보
    for ep in DS002:
        for year in YEARS:
            for reprt in REPRT_CODES:
                f = out / "ds002" / f"{ep}__{year}_{reprt}.json"
                if f.exists():
                    continue
                d = get_json(client, ep, {
                    "corp_code": corp_code, "bsns_year": year, "reprt_code": reprt})
                if d:
                    save(f, d)
        log(f"    ds002 {ep} done")

    # DS003 재무
    for ep in DS003_ACNT:
        for year in YEARS:
            for reprt in REPRT_CODES:
                f = out / "ds003" / f"{ep}__{year}_{reprt}.json"
                if f.exists():
                    continue
                d = get_json(client, ep, {
                    "corp_code": corp_code, "bsns_year": year, "reprt_code": reprt})
                if d:
                    save(f, d)
    for year in YEARS:
        for reprt in REPRT_CODES:
            for fs in DS003_ALL_FS:
                f = out / "ds003" / f"fnlttSinglAcntAll__{year}_{reprt}_{fs}.json"
                if f.exists():
                    continue
                d = get_json(client, "fnlttSinglAcntAll", {
                    "corp_code": corp_code, "bsns_year": year,
                    "reprt_code": reprt, "fs_div": fs})
                if d:
                    save(f, d)
    for year in YEARS:
        for reprt in REPRT_CODES:
            for idx in DS003_INDX_CODES:
                f = out / "ds003" / f"fnlttSinglIndx__{year}_{reprt}_{idx}.json"
                if f.exists():
                    continue
                d = get_json(client, "fnlttSinglIndx", {
                    "corp_code": corp_code, "bsns_year": year,
                    "reprt_code": reprt, "idx_cl_code": idx})
                if d:
                    save(f, d)
    log("    ds003 done")

    # DS004 지분 보고
    for ep in DS004:
        f = out / "ds004" / f"{ep}.json"
        if f.exists():
            continue
        d = get_json(client, ep, {"corp_code": corp_code})
        if d:
            save(f, d)
    log("    ds004 done")

    # DS005 주요사항보고서
    for ep in DS005:
        f = out / "ds005" / f"{ep}.json"
        if f.exists():
            continue
        d = get_json(client, ep, {
            "corp_code": corp_code, "bgn_de": BGN_DE, "end_de": END_DE})
        if d:
            save(f, d)
    log("    ds005 done")


def clean_nonperiodic_zips(out: Path, keep: set[str]) -> None:
    """이전에 무차별로 받은 비-정기보고서 zip 제거. keep=정기보고서 rcept_no 집합."""
    ddir = out / "documents"
    if not ddir.exists():
        return
    removed = 0
    for f in ddir.glob("*.zip"):
        if f.stem not in keep:
            f.unlink()
            removed += 1
    if removed:
        log(f"    정리: 비정기 zip {removed}개 삭제 (정기보고서 {len(keep)}건 유지)")


DART_VIEWER = "https://dart.fss.or.kr"


def fetch_pdf(client: httpx.Client, rn: str, out_pdf: Path) -> None:
    """DART 공시뷰어에서 정기보고서 PDF 다운로드(적재용 원본 보관).

    흐름: dsaf001/main.do 에서 openPdfDownload('rcpNo','dcmNo') 로 dcm_no 추출 →
    pdf/download/pdf.do?rcp_no=&dcm_no= 로 실제 PDF 다운로드(Referer 필요).
    """
    if out_pdf.exists() and out_pdf.stat().st_size > 0:
        return
    throttle(DOC_INTERVAL)
    try:
        m = client.get(f"{DART_VIEWER}/dsaf001/main.do",
                       params={"rcpNo": rn}, timeout=60)
        m.raise_for_status()
        mt = re.search(r"openPdfDownload\(\s*'(\d+)'\s*,\s*'(\d+)'\s*\)", m.text)
        if not mt:
            log(f"      ! pdf {rn}: dcm_no 미발견")
            return
        dcm_no = mt.group(2)
        throttle(DOC_INTERVAL)
        ref = f"{DART_VIEWER}/pdf/download/main.do?rcp_no={rn}&dcm_no={dcm_no}"
        p = client.get(f"{DART_VIEWER}/pdf/download/pdf.do",
                       params={"rcp_no": rn, "dcm_no": dcm_no},
                       headers={"Referer": ref}, timeout=180)
        p.raise_for_status()
        if not p.content.startswith(b"%PDF"):
            log(f"      ! pdf {rn}: PDF 아님(ct={p.headers.get('content-type')})")
            return
        out_pdf.parent.mkdir(parents=True, exist_ok=True)
        out_pdf.write_bytes(p.content)
    except Exception as e:  # noqa: BLE001
        log(f"      ! pdf {rn} 실패: {e}")


def fetch_documents(client: httpx.Client, items: list[dict], out: Path) -> None:
    """정기보고서만 원본 zip(서술 청킹용) + PDF(적재용 보관) 다운로드."""
    periodic = [it for it in items if is_periodic(it.get("report_nm", ""))]
    keep = {it["rcept_no"] for it in periodic}
    clean_nonperiodic_zips(out, keep)
    log(f"    정기보고서 {len(periodic)}건 → zip+PDF")
    for it in sorted(periodic, key=lambda x: x["rcept_no"]):
        rn = it["rcept_no"]
        # 원본 zip (XML/HTML 본문)
        fz = out / "documents" / f"{rn}.zip"
        if not (fz.exists() and fz.stat().st_size > 0):
            for attempt in range(5):
                throttle(DOC_INTERVAL)
                try:
                    r = client.get(f"{BASE}/document.xml",
                                   params={"crtfc_key": API_KEY, "rcept_no": rn},
                                   timeout=60)
                    r.raise_for_status()
                    ct = r.headers.get("content-type", "")
                    if "xml" in ct or "json" in ct:
                        txt = r.text
                        if "020" in txt or "021" in txt:
                            log(f"      … 한도 대기 60s @ {rn}")
                            time.sleep(60)
                            continue
                        break
                    fz.parent.mkdir(parents=True, exist_ok=True)
                    fz.write_bytes(r.content)
                    break
                except (httpx.ConnectError, httpx.ReadError,
                        httpx.RemoteProtocolError) as e:
                    log(f"      ! zip {rn} 차단 의심({type(e).__name__}) {BLOCK_COOLDOWN}s 대기")
                    time.sleep(BLOCK_COOLDOWN)
                except Exception as e:  # noqa: BLE001
                    log(f"      ! zip {rn} 재시도 {attempt+1}: {e}")
                    time.sleep(2 * (attempt + 1))
        # PDF (적재용 보관)
        fetch_pdf(client, rn, out / "pdf" / f"{rn}.pdf")
        log(f"      {rn} {it.get('report_nm','').strip()} done")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-docs", action="store_true", help="원본 zip/PDF 제외")
    ap.add_argument("--only-docs", action="store_true", help="원본 zip/PDF만")
    ap.add_argument("--wait", type=int, default=0,
                    help="시작 전 대기(초) — DART 차단 쿨다운 해제용")
    args = ap.parse_args()

    if not API_KEY:
        log("DART_API_KEY 없음 (.env 확인)")
        return 1

    if args.wait > 0:
        log(f"쿨다운 대기 {args.wait}s …")
        time.sleep(args.wait)

    codes = (ENV.get("POLARIS_CORPS") or "").split(",")
    names = (ENV.get("POLARIS_CORP_NAMES") or "").split(",")
    global CORPS
    CORPS = [(c.strip(), n.strip()) for c, n in zip(codes, names) if c.strip()]
    if not CORPS:
        log("POLARIS_CORPS 없음")
        return 1

    log(f"대상: {CORPS}  기간 {BGN_DE}~{END_DE}")
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) polaris-collector/0.1"
    with httpx.Client(headers={"User-Agent": ua}, follow_redirects=True) as client:
        for corp_code, name in CORPS:
            out = RAW / name
            log(f"\n=== {name} ({corp_code}) ===")
            items = fetch_list(client, corp_code, out)
            log(f"  공시 {len(items)}건")
            if not args.only_docs:
                fetch_apis(client, corp_code, out)
            if not args.no_docs:
                fetch_documents(client, items, out)
            log(f"=== {name} 완료 ===")
    log("\n전체 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
