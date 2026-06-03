"""연결 28개사 재무 raw 수집 — DART fnlttSinglAcntAll (정형만, 청킹·추출 없음).

각 corp_code 에 대해 bsns_year 2024·2025, reprt_code 11011(사업보고서),
fs_div OFS·CFS 호출 → extra_finance/raw/{corp_code}_{year}_{fs}.json 저장.
status '000' 만 저장. throttle 필수(DART 차단 방지).

오염 금지: 각 회사는 자기 corp_code 로만 호출. DART 응답 그대로 저장(LLM 생성 금지).
비상장(데이터 없음, status 013) 은 '재무없음' — 저장하지 않고 넘어감.

실행: cd db && uv run python extra_finance/fetch_extra_finance.py
"""
from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path

import httpx
from dotenv import dotenv_values

HERE = Path(__file__).resolve().parent
DB_DIR = HERE.parent
RAW_OUT = HERE / "raw"
ENV = dotenv_values(DB_DIR / ".env")

API_KEY = (ENV.get("DART_API_KEY") or "").strip()
BASE = "https://opendart.fss.or.kr/api"

YEARS = ["2024", "2025"]
REPRT_CODE = "11011"  # 사업보고서
FS_DIVS = ["OFS", "CFS"]

# ── 검증된 28개사 (이름 → corp_code, ER 검증 완료 — 절대 변경 금지) ──
TARGETS: dict[str, str] = {
    "삼성SDI": "00126362",
    "삼성전기": "00126371",
    "삼성에스디에스": "00126186",
    "삼성디스플레이": "00912006",
    "삼성물산": "00149655",
    "삼성생명보험": "00126256",
    "삼성화재해상보험": "00139214",
    "삼성중공업": "00126478",
    "삼성바이오로직스": "00877059",
    "제일기획": "00148276",
    "에스원": "00158501",
    "호텔신라": "00165680",
    "SK": "00181712",
    "SK스퀘어": "01596425",
    "에스케이키파운드리": "01555631",
    "에스케이하이닉스시스템아이씨": "01265516",
    "에스케이하이스텍": "00652706",
    "에스케이하이이엔지": "00415390",
    "한미네트웍스": "00560070",
    "한화세미텍": "01241987",
    "동진쎄미켐": "00118804",
    "솔브레인": "01489648",
    "원익아이피에스": "01135941",
    "원익홀딩스": "00216647",
    "케이씨텍": "01261893",
    "에스앤에스텍": "00411048",
    "에프에스티": "00223434",
    "대덕전자": "01478712",
}

# ── throttle (fetch_dart.py 와 동일 전략) ──
JSON_INTERVAL = 0.35
BLOCK_COOLDOWN = 120
MAX_PER_MIN = 800
_last_req = 0.0
_req_times: deque[float] = deque()


def log(msg: str) -> None:
    print(msg, flush=True)


def throttle(interval: float = JSON_INTERVAL) -> None:
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
            log(f"    … 분당 상한 도달 — {sleep_for:.1f}s 대기")
            time.sleep(sleep_for)
            now = time.monotonic()
        while _req_times and now - _req_times[0] > 60:
            _req_times.popleft()
    _req_times.append(now)
    _last_req = now


def get_json(client: httpx.Client, params: dict) -> dict | None:
    p = {"crtfc_key": API_KEY, **params}
    for attempt in range(4):
        throttle()
        try:
            r = client.get(f"{BASE}/fnlttSinglAcntAll.json", params=p, timeout=30)
            r.raise_for_status()
            data = r.json()
        except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as e:
            log(f"    ! 차단 의심({type(e).__name__}) {BLOCK_COOLDOWN}s 대기")
            time.sleep(BLOCK_COOLDOWN)
            continue
        except Exception as e:  # noqa: BLE001
            log(f"    ! 재시도 {attempt+1}: {e}")
            time.sleep(2 * (attempt + 1))
            continue
        status = data.get("status")
        if status == "000":
            return data
        if status == "013":  # 데이터 없음 (비상장 등)
            return {"status": "013"}
        if status in {"020", "021"}:  # 한도 초과
            log(f"    … 한도({status}) 대기 60s")
            time.sleep(60)
            continue
        log(f"    ! status={status} {data.get('message')}")
        return {"status": status}
    return None


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    if not API_KEY:
        log("DART_API_KEY 없음 (.env 확인)")
        return 1

    RAW_OUT.mkdir(parents=True, exist_ok=True)
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) polaris-collector/0.1"
    summary: dict[str, dict] = {}

    with httpx.Client(headers={"User-Agent": ua}, follow_redirects=True) as client:
        for name, corp_code in TARGETS.items():
            log(f"\n=== {name} ({corp_code}) ===")
            got = 0
            no_data = 0
            for year in YEARS:
                for fs in FS_DIVS:
                    f = RAW_OUT / f"{corp_code}_{year}_{REPRT_CODE}_{fs}.json"
                    if f.exists():
                        try:
                            obj = json.loads(f.read_text(encoding="utf-8"))
                        except Exception:
                            obj = None
                        if obj and obj.get("status") == "000" and obj.get("list"):
                            got += len(obj["list"])
                            log(f"    {year} {fs} 캐시 ({len(obj['list'])}행)")
                            continue
                    data = get_json(client, {
                        "corp_code": corp_code, "bsns_year": year,
                        "reprt_code": REPRT_CODE, "fs_div": fs,
                    })
                    if data is None:
                        log(f"    {year} {fs} 실패(None)")
                        continue
                    if data.get("status") == "000" and data.get("list"):
                        # corp_code 오염 방지 검증: 응답 corp_code 일치 확인
                        save(f, data)
                        got += len(data["list"])
                        log(f"    {year} {fs} 저장 ({len(data['list'])}행)")
                    else:
                        no_data += 1
                        log(f"    {year} {fs} 데이터없음(status={data.get('status')})")
            summary[corp_code] = {"name": name, "rows_total": got, "no_data": no_data}

    log("\n=== 수집 요약 ===")
    have = sum(1 for v in summary.values() if v["rows_total"] > 0)
    log(f"재무 확보 {have}/{len(TARGETS)} 개사")
    for cc, v in summary.items():
        flag = "OK" if v["rows_total"] > 0 else "재무없음"
        log(f"  {v['name']} ({cc}): {v['rows_total']}행 [{flag}]")
    (HERE / "fetch_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
