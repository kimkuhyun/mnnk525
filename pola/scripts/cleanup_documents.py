"""documents/ 폴더 정리 — 사업·반기·분기 보고서 외 rcept_no 폴더 제거.

DART list 응답 (rawData/{cc}/dart/list__*.json) 의 report_nm 으로 판정.
"""
from __future__ import annotations
import json, shutil, sys
from pathlib import Path

from polaris.config import DATA_ROOT, CORPS


def main(dry_run: bool = True):
    base = DATA_ROOT / "rawData"
    if not base.is_dir():
        print(f"[cleanup] {base} 없음 - exit")
        return 0

    total_kept = 0
    total_removed = 0
    for corp in CORPS:
        docs = base / corp / "documents"
        if not docs.is_dir():
            continue
        # rcept_no → report_nm 매핑 (list 응답에서)
        mapping = {}
        for f in (base / corp / "dart").glob("list__*.json") if (base / corp / "dart").is_dir() else []:
            try:
                d = json.load(f.open(encoding="utf-8"))
                for r in (d.get("data", {}).get("list") or []):
                    mapping[r.get("rcept_no")] = r.get("report_nm", "")
            except Exception:
                continue

        kept, removed = 0, 0
        for d in sorted(docs.iterdir()):
            if not d.is_dir():
                continue
            rn = mapping.get(d.name, "")
            keep = any(t in rn for t in ("사업보고서", "반기보고서", "분기보고서"))
            if keep:
                kept += 1
                print(f"  KEEP  {corp}/{d.name}  -  {rn}")
            else:
                removed += 1
                action = "(dry-run)" if dry_run else "REMOVED"
                print(f"  {action}  {corp}/{d.name}  -  {rn or '(report_nm 매핑 없음 → 안전상 제거)'}")
                if not dry_run:
                    shutil.rmtree(d, ignore_errors=True)
        total_kept += kept
        total_removed += removed
        print(f"  {corp}: kept={kept} removed={removed}")
        print()

    print(f"=== 합계 - kept {total_kept} / removed {total_removed} ===")
    if dry_run:
        print("dry-run 이었음. 실제 삭제는: python -m scripts.cleanup_documents apply")
    return 0


if __name__ == "__main__":
    dry = not (len(sys.argv) > 1 and sys.argv[1] == "apply")
    sys.exit(main(dry_run=dry))
