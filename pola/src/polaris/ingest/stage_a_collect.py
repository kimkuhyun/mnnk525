"""Stage A: 정제·필터.

입력: ___test/1_rawData/{corp}/documents/{rcept_no}/body.html + dart/*.json
출력: ___test/2_Chuck/01_filtered/{corp}/body_clean/{rcept_no}.txt + dart/{stem}__{hash}.json
       + _filter_log.jsonl (제외 행·이유)

처리:
1. HTML normalize (한자 병기·페이지번호·다중공백 제거)
2. DART JSON null 가드 + 단위·날짜 표준화
3. 분기 dedupe: 동일 (corp, year, endpoint, value_hash) 행 1개만 (사업보고서 11011 우선)
"""
from __future__ import annotations
import json
import sys
import time
import hashlib
from pathlib import Path
from collections import defaultdict

# 모듈 import
from polaris.chunk.lib.normalize import extract_body_text, to_int, normalize_date, is_empty_value

# =========================================================================
# 경로
# =========================================================================
from polaris.config import DATA_ROOT, FILTERED_DIR
RAW = DATA_ROOT / "rawData"
OUT = FILTERED_DIR
LOG_PATH = FILTERED_DIR / "_filter_log.jsonl"

from polaris.config import CORPS as _ENV_CORPS, CORP_NAMES as _ENV_CORP_NAMES, get_corp_meta
CORPS = list(_ENV_CORPS)
CORP_NAMES = {cc: (_ENV_CORP_NAMES.get(cc) or get_corp_meta(cc).get("corp_name", cc))
              for cc in CORPS}

# 사업보고서 11011 우선순위 (dedupe 선택 기준)
REPRT_PRIORITY = {"11011": 4, "11014": 3, "11012": 2, "11013": 1}

# =========================================================================
# HTML 정제
# =========================================================================

def filter_html_one(html_path: Path, out_path: Path) -> dict:
    """body.html → body_clean.txt. 처리 결과 메타 반환."""
    try:
        html = html_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return {"status": "read_fail", "error": str(e), "in_bytes": 0, "out_bytes": 0}
    in_bytes = len(html)
    text = extract_body_text(html)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return {
        "status": "ok",
        "in_bytes": in_bytes,
        "out_bytes": len(text),
        "lines": text.count("\n") + 1,
    }


# =========================================================================
# DART JSON 정제 + dedupe
# =========================================================================

def normalize_row(row: dict) -> dict:
    """한 응답 row를 정제. 빈값 통일·날짜 표준화·숫자 콤마 정리."""
    out = {}
    for k, v in row.items():
        if is_empty_value(v):
            out[k] = ""  # 빈값 통일
        elif isinstance(v, str):
            # 날짜처럼 보이면 표준화
            if k.endswith("_dt") or k.endswith("_de") or "date" in k.lower():
                out[k] = normalize_date(v)
            else:
                out[k] = v.strip()
        else:
            out[k] = v
    return out


def row_value_hash(row: dict, key_fields: list[str]) -> str:
    """dedupe 키 = 핵심 필드값 SHA1 hash16."""
    parts = [str(row.get(f, "")) for f in key_fields]
    s = "|".join(parts)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


# 카테고리별 dedupe 핵심 필드 (corp+year+이 필드들이 같으면 같은 사실)
DEDUPE_KEYS = {
    # 재무지표·재무제표: account_id + sj_div + fs_div
    "fnlttSinglAcnt": ["account_id", "sj_div", "fs_div"],
    "fnlttSinglAcntAll": ["account_id", "sj_div", "fs_div"],
    "fnlttSinglIndx": ["idx_cd", "idx_nm"],
    # 임원·직원·주주: nm
    "exctvSttus": ["nm", "ofcps", "birth_ym"],
    "empSttus": ["fo_bbm", "sexdstn"],
    "hyslrSttus": ["nm", "stock_knd"],
    "hyslrChgSttus": ["change_on", "mxmm_shrholdr_nm"],
    # 배당
    "alotMatter": ["se", "stock_knd"],
    # 자기주식
    "tesstkAcqsDspsSttus": ["stock_knd", "acqs_mth1", "acqs_mth2"],
    # 타법인 출자
    "otrCprInvstmntSttus": ["inv_prm"],
    # 보수
    "hmvAuditAllSttus": ["nmpr"],
    "hmvAuditIndvdlBySttus": ["nm"],
    "indvdlByPay": ["nm"],
    # 채권
    "entrprsBilScritsNrdmpBlce": ["isu_cmpny_nm"],
    "srtpdPsndbtNrdmpBlce": ["isu_cmpny_nm"],
    "cprndNrdmpBlce": ["isu_cmpny_nm"],
}


def filter_dart_json_one(json_path: Path, out_dir: Path) -> dict:
    """DART JSON 한 파일 정제 + 저장."""
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"status": "read_fail", "error": str(e)}

    endpoint = data.get("endpoint", "")
    status = data.get("status", "")
    if status != "ok":
        return {"status": "skip_non_ok", "raw_status": status}

    # 리스트 응답: data.list[]
    items = (data.get("data") or {}).get("list") or []
    if not isinstance(items, list):
        items = []

    in_rows = len(items)
    if in_rows == 0:
        return {"status": "ok", "in_rows": 0, "out_rows": 0, "dedup_removed": 0}

    # 1) 각 row 정제
    normalized = [normalize_row(r) for r in items]

    # 2) dedupe (옵션 — 명시된 endpoint만)
    dedup_removed = 0
    if endpoint in DEDUPE_KEYS:
        keys = DEDUPE_KEYS[endpoint]
        seen = {}  # hash → (row, priority)
        for r in normalized:
            h = row_value_hash(r, keys)
            rc = r.get("reprt_code", "")
            prio = REPRT_PRIORITY.get(rc, 0)
            if h in seen:
                if prio > seen[h][1]:
                    seen[h] = (r, prio)
                dedup_removed += 1
            else:
                seen[h] = (r, prio)
        # dedup 후 살아남은 행
        dedup_removed = in_rows - len(seen)
        normalized = [v[0] for v in seen.values()]

    # 3) 저장 (원본 파일명 그대로)
    data["data"]["list"] = normalized
    out_path = out_dir / json_path.name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "status": "ok",
        "endpoint": endpoint,
        "in_rows": in_rows,
        "out_rows": len(normalized),
        "dedup_removed": dedup_removed,
    }


# =========================================================================
# 메인
# =========================================================================

def main():
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    log_lines = []

    summary = {
        "html_processed": 0, "html_total_bytes_in": 0, "html_total_bytes_out": 0,
        "json_processed": 0, "json_in_rows": 0, "json_out_rows": 0, "json_dedup_removed": 0,
        "per_corp": {},
    }

    for corp in CORPS:
        corp_name = CORP_NAMES[corp]
        print(f"\n=== {corp_name} ({corp}) ===")
        corp_stat = {"html": 0, "json": 0, "dedup": 0}

        # 1) HTML 정제 — documents/{rcept_no}/body.html
        docs_dir = RAW / corp / "documents"
        if docs_dir.is_dir():
            html_out_dir = OUT / corp / "body_clean"
            for rno_dir in sorted(docs_dir.iterdir()):
                if not rno_dir.is_dir():
                    continue
                rno = rno_dir.name
                body_html = rno_dir / "body.html"
                if not body_html.is_file():
                    log_lines.append({"corp": corp, "stage": "html", "rcept_no": rno,
                                      "status": "no_body_html"})
                    continue
                out_path = html_out_dir / f"{rno}.txt"
                r = filter_html_one(body_html, out_path)
                r.update({"corp": corp, "stage": "html", "rcept_no": rno})
                log_lines.append(r)
                if r["status"] == "ok":
                    summary["html_processed"] += 1
                    summary["html_total_bytes_in"] += r["in_bytes"]
                    summary["html_total_bytes_out"] += r["out_bytes"]
                    corp_stat["html"] += 1
            print(f"  HTML: {corp_stat['html']}건")

        # 2) DART JSON 정제 + dedupe
        dart_dir = RAW / corp / "dart"
        if dart_dir.is_dir():
            json_out_dir = OUT / corp / "dart"
            for f in sorted(dart_dir.iterdir()):
                if f.suffix != ".json":
                    continue
                r = filter_dart_json_one(f, json_out_dir)
                r.update({"corp": corp, "stage": "json", "file": f.name})
                log_lines.append(r)
                if r["status"] == "ok":
                    summary["json_processed"] += 1
                    summary["json_in_rows"] += r["in_rows"]
                    summary["json_out_rows"] += r["out_rows"]
                    summary["json_dedup_removed"] += r["dedup_removed"]
                    corp_stat["json"] += 1
                    corp_stat["dedup"] += r["dedup_removed"]
            print(f"  JSON: {corp_stat['json']}건 (dedup -{corp_stat['dedup']})")

        summary["per_corp"][corp] = corp_stat

    # 3) 로그 저장
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("w", encoding="utf-8") as f:
        for line in log_lines:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    # 4) 요약
    elapsed = time.time() - t0
    print(f"\n=== Stage A 완료 ({elapsed:.1f}s) ===")
    print(f"  HTML: {summary['html_processed']}건 / {summary['html_total_bytes_in']/1024:.0f}KB → "
          f"{summary['html_total_bytes_out']/1024:.0f}KB "
          f"({summary['html_total_bytes_out']/summary['html_total_bytes_in']*100:.1f}%)")
    print(f"  JSON: {summary['json_processed']}건 / "
          f"{summary['json_in_rows']} → {summary['json_out_rows']} rows "
          f"(dedup -{summary['json_dedup_removed']}, {summary['json_dedup_removed']/max(1,summary['json_in_rows'])*100:.1f}%)")
    print(f"  로그: {LOG_PATH}")

    # 5) manifest
    manifest = DATA_ROOT / "2_Chuck" / "_manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    m = {}
    if manifest.exists():
        try:
            m = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            m = {}
    m["stage_a"] = {
        "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_sec": elapsed,
        "summary": summary,
    }
    manifest.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  manifest: {manifest}")


if __name__ == "__main__":
    main()
