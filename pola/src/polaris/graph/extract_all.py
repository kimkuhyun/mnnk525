"""5 추출기 통합 orchestrator — polaris graph-extract.

순서: persons → shareholders → invests → ftc_groups → events.
각 추출기는 독립적으로 실행 가능. 통합 명령은 idempotent (재실행 안전).
"""
from __future__ import annotations

import argparse
import sys

from polaris.graph import (
    extract_persons, extract_shareholders, extract_invests,
    extract_ftc_groups, extract_events,
)


EXTRACTORS = {
    "persons":      extract_persons,
    "shareholders": extract_shareholders,
    "invests":      extract_invests,
    "ftc_groups":   extract_ftc_groups,
    "events":       extract_events,
}


def main():
    parser = argparse.ArgumentParser(description="POLARIS 그래프 영역 자동 추출")
    parser.add_argument("--only", type=str, default="all",
                        help="csv 추출기 (persons,shareholders,invests,ftc_groups,events,all)")
    args = parser.parse_args()

    names = list(EXTRACTORS.keys()) if args.only == "all" \
            else [n.strip() for n in args.only.split(",")]

    print(f"=== graph-extract 시작 ({len(names)} 추출기) ===")
    rc = 0
    for n in names:
        if n not in EXTRACTORS:
            print(f"[graph-extract] 알 수 없는 추출기: {n}")
            rc = 1
            continue
        print(f"\n──── {n} ────────────────────────")
        try:
            r = EXTRACTORS[n].main()
            if r:
                print(f"[graph-extract] {n} 비정상 종료 ({r})")
                rc = rc or r
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[graph-extract] {n} 예외: {e}")
            rc = 1
    print(f"\n=== graph-extract 완료 (rc={rc}) ===")
    return rc


if __name__ == "__main__":
    sys.exit(main())
