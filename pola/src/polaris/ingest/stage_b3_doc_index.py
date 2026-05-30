"""Stage B-3: document_index.jsonl 통합.

135 문서 × (rcept_no, corp_code, doc_type, date, title, summary_short,
snapshot_path, hash16, page_index) 1행씩.
"""
from __future__ import annotations
import json, sys, time, glob, hashlib, re
from pathlib import Path

from polaris.config import (
    DATA_ROOT, FILTERED_DIR, META_DIR,
    CORPS as _ENV_CORPS, CORP_NAMES as _ENV_CORP_NAMES, get_corp_meta,
)
RAW = DATA_ROOT / "rawData"
CLEAN = FILTERED_DIR
META = META_DIR
SNAP = META / "snapshots"
PER_DOC = META / "per_doc"
OUT = META / "document_index.jsonl"

# config.CORPS 동적 — 신규 회사 추가 시 자동 반영
CORPS = list(_ENV_CORPS)
CORP_NAMES = {cc: (_ENV_CORP_NAMES.get(cc) or get_corp_meta(cc).get("corp_name", cc))
              for cc in CORPS}


def load_report_nm_map(corp: str) -> dict:
    """list_*.json에서 rcept_no → report_nm·rcept_dt."""
    out = {}
    for lf in glob.glob(str(RAW / corp / "dart" / "list__*.json")):
        try:
            d = json.load(open(lf, encoding="utf-8"))
            for it in d.get("data", {}).get("list", []):
                rn = it.get("rcept_no")
                if rn:
                    out[rn] = {
                        "report_nm": (it.get("report_nm") or "").strip(),
                        "rcept_dt": it.get("rcept_dt", ""),
                        "flr_nm": it.get("flr_nm", ""),
                    }
        except Exception:
            pass
    return out


def hash16_body(body_path: Path) -> str:
    if not body_path.is_file():
        return ""
    return hashlib.sha1(body_path.read_bytes()).hexdigest()[:16]


def extract_page_index(body_text: str) -> dict:
    """HTML 본문에서 섹션 패턴(I., II., III. 등) 추출 → page_index 대용.
    PDF 페이지 번호는 없으므로 line offset 기반."""
    pi = {}
    if not body_text:
        return pi
    lines = body_text.split("\n")
    section_re = re.compile(r"^([IVXLCDM]+)\.\s*(.+)")
    for i, line in enumerate(lines):
        m = section_re.match(line.strip())
        if m:
            roman = m.group(1)
            title = m.group(2).strip()[:50]
            pi.setdefault(str(i+1), []).append(f"{roman}. {title}")
    return pi


def main():
    t0 = time.time()
    rows = []
    summary = {"total": 0, "by_corp": {}, "doc_type_count": {}}

    for corp in CORPS:
        name = CORP_NAMES[corp]
        report_map = load_report_nm_map(corp)
        body_dir = CLEAN / corp / "body_clean"
        sum_dir = PER_DOC / corp
        snap_dir = SNAP / corp

        corp_count = 0
        for sum_path in sorted(sum_dir.glob("*.summary.json")) if sum_dir.is_dir() else []:
            rno = sum_path.stem.replace(".summary", "")
            s = json.load(open(sum_path, encoding="utf-8"))

            rep_info = report_map.get(rno, {})
            report_nm = rep_info.get("report_nm", "")
            # 정정 prefix 제거
            if report_nm.startswith("["):
                close = report_nm.find("]")
                if close > 0:
                    report_nm = report_nm[close+1:].strip()

            body_path = body_dir / f"{rno}.txt"
            body_text = body_path.read_text(encoding="utf-8") if body_path.is_file() else ""
            snap_path = snap_dir / f"{rno}.png"
            snap_rel = snap_path.relative_to(DATA_ROOT).as_posix() if snap_path.is_file() else ""

            rcept_dt = rep_info.get("rcept_dt", "")
            date_iso = f"{rcept_dt[:4]}-{rcept_dt[4:6]}-{rcept_dt[6:8]}" if len(rcept_dt) == 8 else ""

            row = {
                "rcept_no": rno,
                "corp_code": corp,
                "corp_name": name,
                "doc_type": report_nm or s.get("doc_type", ""),
                "report_nm_raw": rep_info.get("report_nm", ""),
                "date": date_iso,
                "title": report_nm,
                "filer": rep_info.get("flr_nm", ""),
                "summary_short": s.get("summary_short", ""),
                "summary_method": s.get("summary_method", ""),
                "summary_verified": s.get("verification", {}).get("passed", False),
                "key_facts": s.get("key_facts", []),
                "snapshot_path": snap_rel,
                "hash16": hash16_body(body_path),
                "page_index": extract_page_index(body_text),
                "body_chars": len(body_text),
            }
            rows.append(row)
            corp_count += 1
            summary["doc_type_count"][report_nm] = summary["doc_type_count"].get(report_nm, 0) + 1
        summary["by_corp"][corp] = corp_count
        summary["total"] += corp_count
        print(f"  {name}: {corp_count}")

    # 저장
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    elapsed = time.time() - t0
    print(f"\n=== Stage B-3 완료 ({elapsed:.1f}s) ===")
    print(f"  총 {summary['total']}행 → {OUT}")
    print(f"  doc_type 종류 {len(summary['doc_type_count'])}개")

    # manifest
    manifest = DATA_ROOT / "2_Chuck" / "_manifest.json"
    m = {}
    if manifest.exists():
        try: m = json.loads(manifest.read_text(encoding="utf-8"))
        except: m = {}
    m["stage_b3"] = {
        "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_sec": elapsed,
        "summary": summary,
    }
    manifest.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
