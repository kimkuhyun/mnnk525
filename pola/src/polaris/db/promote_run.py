"""active_run_manifest 의 standby → active 슬롯 atomic switch.

사용:
  python scripts/db/promote_run.py --dry-run   # 영향만 표시
  python scripts/db/promote_run.py             # 진짜 promote

룰 (설계 05 §1.2):
- standby_status='ready_to_promote' 만 promote 허용
- standby↔active 1트랜잭션으로 swap
- 옛 active 정보는 standby 슬롯에 잠시 보관 (cleanup 대기)
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

from polaris.config import mariadb_conn


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-from-ingesting", action="store_true",
                    help="standby_status='ingesting' 도 promote 허용 (시연 첫 실행 — verify 단계 생략)")
    args = ap.parse_args()

    conn = mariadb_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT active_run_id, active_qdrant_collection, active_neo4j_run_id,
               standby_run_id, standby_qdrant_collection, standby_neo4j_run_id,
               standby_status
        FROM active_run_manifest WHERE id=1
    """)
    row = cur.fetchone()
    if not row:
        print("[promote_run] manifest 행 없음 — init_mariadb.py 먼저")
        return 1
    a_run, a_col, a_neo, s_run, s_col, s_neo, s_status = row

    print(f"[promote_run] 현재 상태:")
    print(f"  active : run_id={a_run!r}  qdrant={a_col!r}  neo4j={a_neo!r}")
    print(f"  standby: run_id={s_run!r}  qdrant={s_col!r}  neo4j={s_neo!r}  status={s_status!r}")

    if not s_run:
        print("\n[promote_run] standby 비어 있음 — 적재 필요")
        return 1

    allowed = {"ready_to_promote"} | ({"ingesting"} if args.force_from_ingesting else set())
    if s_status not in allowed:
        print(f"\n[promote_run] standby_status={s_status!r} → promote 불가")
        print(f"  허용 상태: {allowed}")
        return 2

    if args.dry_run:
        print(f"\n[promote_run] DRY-RUN — 실제 변경 없음")
        print(f"  promote 시: active <- ({s_run}, {s_col}, {s_neo})")
        print(f"             standby slot 비움 (cleanup_pending)")
        return 0

    # Atomic swap: standby → active. 옛 active 는 standby 슬롯에 cleanup_pending 으로 잠시 보관.
    cur.execute("""
        UPDATE active_run_manifest SET
          active_run_id            = standby_run_id,
          active_qdrant_collection = standby_qdrant_collection,
          active_neo4j_run_id      = standby_neo4j_run_id,
          standby_run_id            = %s,
          standby_qdrant_collection = %s,
          standby_neo4j_run_id      = %s,
          standby_status            = 'cleanup_pending',
          switched_at               = NOW()
        WHERE id = 1
    """, (a_run, a_col, a_neo))
    conn.commit()

    cur.execute("SELECT active_run_id, switched_at FROM active_run_manifest WHERE id=1")
    new_active, switched = cur.fetchone()
    cur.close(); conn.close()
    print(f"\n[promote_run] ✓ atomic switch 완료")
    print(f"  new active_run_id = {new_active}")
    print(f"  switched_at       = {switched}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
