"""data/rawData/{cc}/dart/*.json → dart_raw_index.body_json 마이그레이션.

각 row 의 raw_path 로 파일 읽어 body_json 컬럼에 INSERT.
"""
from __future__ import annotations
import json, time
from pathlib import Path

from polaris.config import DATA_ROOT, mariadb_conn


def main():
    conn = mariadb_conn(); cur = conn.cursor()
    cur.execute("""SELECT corp_code, endpoint, hash8, run_id, raw_path
                   FROM dart_raw_index WHERE body_json IS NULL""")
    rows = cur.fetchall()
    print(f"[migrate-dart] body_json 비어있는 row: {len(rows)}")
    if not rows:
        cur.close(); conn.close()
        return 0

    t0 = time.time()
    updated = 0
    skipped_no_file = 0
    for i, (cc, ep, h8, rid, rp) in enumerate(rows, 1):
        fpath = DATA_ROOT / rp
        if not fpath.is_file():
            skipped_no_file += 1
            continue
        try:
            body = fpath.read_text(encoding="utf-8")
        except Exception:
            skipped_no_file += 1
            continue
        cur.execute("""UPDATE dart_raw_index SET body_json=%s
                       WHERE corp_code=%s AND endpoint=%s AND hash8=%s AND run_id=%s""",
                    (body, cc, ep, h8, rid))
        updated += 1
        if i % 500 == 0:
            conn.commit()
            print(f"  {i}/{len(rows)} ({updated} OK, {skipped_no_file} skip)")
    conn.commit()
    cur.execute("SELECT COUNT(*), COUNT(body_json) FROM dart_raw_index")
    total, with_body = cur.fetchone()
    cur.close(); conn.close()
    print(f"[migrate-dart] UPDATE: {updated} / skip: {skipped_no_file}")
    print(f"[migrate-dart] dart_raw_index: total={total}, with_body_json={with_body}")
    print(f"[migrate-dart] 완료 {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
