"""MariaDB DDL 적용 (idempotent).

사용:  python scripts/db/init_mariadb.py
재실행: 안전 (IF NOT EXISTS / INSERT IGNORE 사용).
"""
from __future__ import annotations
import sys, time
from pathlib import Path

from polaris.config import mariadb_conn, MARIADB_DATABASE

SQL_PATH = Path(__file__).parent / "init_mariadb.sql"


def split_statements(text: str) -> list[str]:
    """DDL 파일을 ; 단위로 분할. 주석·빈 줄 제외."""
    parts = []
    cur = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        cur.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(cur).strip().rstrip(";").strip()
            if stmt:
                parts.append(stmt)
            cur = []
    if cur:
        stmt = "\n".join(cur).strip().rstrip(";").strip()
        if stmt:
            parts.append(stmt)
    return parts


def main() -> int:
    t0 = time.time()
    sql_text = SQL_PATH.read_text(encoding="utf-8")
    stmts = split_statements(sql_text)
    print(f"[init_mariadb] {len(stmts)} statements 적용 → DB={MARIADB_DATABASE}")

    conn = mariadb_conn()
    cur = conn.cursor()
    applied = 0
    for i, stmt in enumerate(stmts, 1):
        head = stmt[:60].replace("\n", " ")
        try:
            cur.execute(stmt)
            conn.commit()
            applied += 1
            print(f"  [{i:02d}/{len(stmts)}] OK  {head}...")
        except Exception as e:
            print(f"  [{i:02d}/{len(stmts)}] FAIL {head}... → {e}")
            conn.rollback()
            return 1
    cur.close()
    conn.close()
    print(f"\n=== MariaDB init 완료 ({time.time()-t0:.1f}s, {applied}/{len(stmts)} OK) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
