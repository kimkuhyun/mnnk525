"""POLARIS — DART 공시 raw 수집기 (28개 연결사용).

fetch_dart.py 와 완전히 동일한 수집 로직.
CORPS 만 db/extra28/corps.tsv 에서 읽는다.

저장 구조:
  db/raw/{회사명}/
    company.json
    list/list_{page}.json
    ds002/{endpoint}__{year}_{reprt}.json
    ds003/{endpoint}__...json
    ds004/{endpoint}.json
    ds005/{endpoint}.json
    documents/{rcept_no}.zip
    pdf/{rcept_no}.pdf

실행:
  uv run python extra28/fetch_extra28.py
  uv run python extra28/fetch_extra28.py --no-docs
  uv run python extra28/fetch_extra28.py --only-docs
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

HERE = Path(__file__).resolve().parent        # db/extra28/
DB   = HERE.parent                            # db/
RAW  = DB / "raw"
ENV  = dotenv_values(DB / ".env")

API_KEY = (ENV.get("DART_API_KEY") or "").strip()
BASE = "https://opendart.fss.or.kr/api"

BGN_DE = "20240101"
END_DE = "20260601"

# ── 속도 제한 (fetch_dart.py 와 동일) ──────────────────────────────
from collections import deque

JSON_INTERVAL  = 0.25   # JSON API 요청 간 최소 간격(초)
DOC_INTERVAL   = 0.6    # 원본 zip/PDF 요청 간 최소 간격(초)
BLOCK_COOLDOWN = 120    # 연결 강제종료(차단 의심) 시 대기(초)
MAX_PER_MIN    = 900    # 60초당 요청 상한

_last_req: float = 0.0
_req_times: deque[float] = deque()


def throttle(interval: float) -> None:
    global _last_req
    now = time.monotonic()
    wait = interval - (now - _last_req)
    if wait > 0:
        time.sleep(wait)
        now = time.monotonic()
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
REPRT_CODES = ["11013", "11012", "11014", "11011"]  # 1분기/반기/3분기/사업

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
DS003_ACNT = ["fnlttSinglAcnt"]
DS003_ALL_FS = ["OFS", "CFS"]
DS003_INDX_CODES = ["M210000", "M220000", "M230000", "M240000"]
DS004 = ["majorstock", "elestock"]
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
    p = {"crtfc_key": API_KEY, **params}
    for attempt in range(4):
        throttle(JSON_INTERVAL)
        try:
            r = client.get(f"{BASE}/{endpoint}.json", params=p, timeout=30)
            r.raise_for_status()
            data = r.json()
        except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as e:
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
        if status == "013":
            return None
        if status in {"020", "021"}:
            log(f"    … 한도({status}) 대기 60s")
            time.sleep(60)
            continue
        log(f"    ! {endpoint} status={status} {data.get('message')}")
        return None
    return None


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def is_periodic(report_nm: str) -> bool:
    return any(k in report_nm for k in ("사업보고서", "반기보고서", "분기보고서"))


def fetch_list(client: httpx.Client, corp_code: str, out: Path) -> list[dict]:
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

    # DS002
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

    # DS003
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

    # DS004
    for ep in DS004:
        f = out / "ds004" / f"{ep}.json"
        if f.exists():
            continue
        d = get_json(client, ep, {"corp_code": corp_code})
        if d:
            save(f, d)
    log("    ds004 done")

    # DS005
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
    periodic = [it for it in items if is_periodic(it.get("report_nm", ""))]
    keep = {it["rcept_no"] for it in periodic}
    clean_nonperiodic_zips(out, keep)
    log(f"    정기보고서 {len(periodic)}건 → zip+PDF")
    for it in sorted(periodic, key=lambda x: x["rcept_no"]):
        rn = it["rcept_no"]
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
        fetch_pdf(client, rn, out / "pdf" / f"{rn}.pdf")
        log(f"      {rn} {it.get('report_nm','').strip()} done")


def load_corps_tsv() -> list[tuple[str, str]]:
    """corps.tsv 에서 (corp_code, name) 목록 로드."""
    tsv = HERE / "corps.tsv"
    corps: list[tuple[str, str]] = []
    with tsv.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            code = row["corp_code"].strip()
            name = row["name"].strip()
            if code:
                corps.append((code, name))
    return corps


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-docs", action="store_true", help="원본 zip/PDF 제외")
    ap.add_argument("--only-docs", action="store_true", help="원본 zip/PDF만")
    ap.add_argument("--wait", type=int, default=0,
                    help="시작 전 대기(초) — DART 차단 쿨다운 해제용")
    ap.add_argument("--start-from", default="",
                    help="이 회사명부터 재개 (앞 회사들 건너뜀)")
    ap.add_argument("--corp-code", action="append", default=[],
                    help="지정한 corp_code만 처리. 여러 번 지정 가능")
    args = ap.parse_args()

    if not API_KEY:
        log("DART_API_KEY 없음 (db/.env 확인)")
        return 1

    if args.wait > 0:
        log(f"쿨다운 대기 {args.wait}s …")
        time.sleep(args.wait)

    corps = load_corps_tsv()
    if not corps:
        log("corps.tsv 비어 있음")
        return 1

    if args.corp_code:
        wanted = {c.strip() for c in args.corp_code if c.strip()}
        original_len = len(corps)
        corps = [(code, name) for code, name in corps if code in wanted]
        missing = sorted(wanted - {code for code, _ in corps})
        if missing:
            log(f"--corp-code: corps.tsv 미발견 {', '.join(missing)}")
        log(f"--corp-code: {len(corps)}개 선택 ({original_len - len(corps)}개 제외)")
        if not corps:
            return 1

    # --start-from 재개 처리
    if args.start_from and not args.corp_code:
        skip_until = args.start_from.strip()
        original_len = len(corps)
        found = False
        for i, (_, name) in enumerate(corps):
            if name == skip_until:
                corps = corps[i:]
                found = True
                break
        if found:
            log(f"--start-from: {skip_until} 부터 재개 ({original_len - len(corps)}개 건너뜀)")
        else:
            log(f"--start-from: '{skip_until}' 미발견 — 전체 처리")
    elif args.start_from and args.corp_code:
        log("--corp-code 지정으로 --start-from은 fetch 단계에서 무시")

    log(f"대상 {len(corps)}개사  기간 {BGN_DE}~{END_DE}")
    log(f"저장 경로: {RAW}")

    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) polaris-collector/0.1"
    with httpx.Client(headers={"User-Agent": ua}, follow_redirects=True) as client:
        for idx, (corp_code, name) in enumerate(corps, 1):
            out = RAW / name
            log(f"\n=== [{idx}/{len(corps)}] {name} ({corp_code}) ===")
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
