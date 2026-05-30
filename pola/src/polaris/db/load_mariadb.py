"""MariaDB 적재 — chunk_index / document_index / chunk_summary / news_matched / dart_raw_index.

run_id 주입은 standby_run_id (active_run_manifest) 기준. 적재 완료 시 promote_run.py 가 active 로 전환.

idempotent — UPSERT (INSERT ... ON DUPLICATE KEY UPDATE).
"""
from __future__ import annotations
import argparse, json, sys, time
from datetime import datetime
from pathlib import Path

from polaris.config import (mariadb_conn, QDRANT_COLLECTION_STANDBY,
                            DATA_ROOT, CHUNKS_DIR, META_DIR, CORPS)

CHUNKS = CHUNKS_DIR
META = META_DIR
RAW = DATA_ROOT / "rawData"

BATCH = 500


def acquire_standby_run_id(conn) -> str:
    """active_run_manifest standby 슬롯 발급. 이미 ingesting 상태면 그 run_id 반환."""
    cur = conn.cursor()
    cur.execute("SELECT standby_run_id, standby_status FROM active_run_manifest WHERE id=1 FOR UPDATE")
    row = cur.fetchone()
    if row and row[1] == "ingesting" and row[0]:
        run_id = row[0]
        print(f"[run_id] 기존 standby 인입 재개: {run_id}")
    else:
        run_id = datetime.now().strftime("%Y%m%d_%H%M") + "_01"
        cur.execute(
            "UPDATE active_run_manifest SET "
            "  standby_run_id=%s, "
            "  standby_qdrant_collection=%s, "
            "  standby_mariadb_schema='polaris', "
            "  standby_neo4j_run_id=%s, "
            "  standby_started_at=NOW(), "
            "  standby_status='ingesting' "
            "WHERE id=1",
            (run_id, QDRANT_COLLECTION_STANDBY, run_id),
        )
        print(f"[run_id] 새 standby 발급: {run_id}")
    conn.commit()
    cur.close()
    return run_id


def load_chunk_index(conn, run_id: str) -> int:
    cur = conn.cursor()
    sql = """
    INSERT INTO chunk_index
      (chunk_id, run_id, corp_code, rcept_no, chunk_type, endpoint, variant,
       bsns_year, reprt_code, fs_div, section_path, token_count,
       embedding_text, llm_context_text, pipeline_version, ingest_status)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending')
    ON DUPLICATE KEY UPDATE
      chunk_type=VALUES(chunk_type), endpoint=VALUES(endpoint),
      embedding_text=VALUES(embedding_text), llm_context_text=VALUES(llm_context_text),
      ingest_status='pending'
    """
    n = 0
    for corp in CORPS:
        for fname in ("table_nl.jsonl", "text.jsonl"):
            p = CHUNKS / corp / fname
            if not p.is_file():
                continue
            batch: list[tuple] = []
            for line in p.open(encoding="utf-8"):
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                pl = r.get("payload", {})
                sp = "/".join(pl.get("section_path", [])) if pl.get("section_path") else ""
                batch.append((
                    r["chunk_id"], run_id, pl.get("corp_code"), pl.get("rcept_no"),
                    r.get("chunk_type") or pl.get("chunk_type"),
                    pl.get("endpoint"), pl.get("variant"),
                    pl.get("bsns_year"), pl.get("reprt_code"), pl.get("fs_div"),
                    sp, pl.get("token_count"),
                    r.get("embedding_text",""), r.get("llm_context_text",""),
                    pl.get("pipeline_version"),
                ))
                if len(batch) >= BATCH:
                    cur.executemany(sql, batch); conn.commit()
                    n += len(batch); batch.clear()
            if batch:
                cur.executemany(sql, batch); conn.commit()
                n += len(batch)
            print(f"  chunk_index ← {corp}/{fname}: 누적 {n}")
    cur.close()
    return n


def load_document_index(conn, run_id: str) -> int:
    cur = conn.cursor()
    sql = """
    INSERT INTO document_index
      (rcept_no, run_id, corp_code, corp_name, doc_type, date, title, filer,
       summary_short, summary_method, summary_verified, key_facts,
       snapshot_path, hash16, page_index, body_chars, pipeline_version)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON DUPLICATE KEY UPDATE
      summary_short=VALUES(summary_short), summary_method=VALUES(summary_method),
      summary_verified=VALUES(summary_verified), key_facts=VALUES(key_facts),
      snapshot_path=VALUES(snapshot_path), page_index=VALUES(page_index)
    """
    p = META / "document_index.jsonl"
    n = 0
    if not p.is_file():
        print("  document_index.jsonl 없음 — skip")
        return 0
    rows = []
    for line in p.open(encoding="utf-8"):
        r = json.loads(line)
        d = r.get("date") or None
        if d == "": d = None
        rows.append((
            r["rcept_no"], run_id, r["corp_code"], r.get("corp_name"),
            r.get("doc_type"), d, r.get("title"), r.get("filer"),
            r.get("summary_short"), r.get("summary_method"),
            1 if r.get("summary_verified") else 0,
            json.dumps(r.get("key_facts", []), ensure_ascii=False),
            r.get("snapshot_path"), r.get("hash16"),
            json.dumps(r.get("page_index", {}), ensure_ascii=False),
            r.get("body_chars"), "2026.05.24.v1",
        ))
    cur.executemany(sql, rows); conn.commit()
    n = len(rows)
    cur.close()
    print(f"  document_index: {n}")
    return n


def load_chunk_summary(conn, run_id: str) -> int:
    cur = conn.cursor()
    sql = """
    INSERT INTO chunk_summary
      (chunk_id, run_id, corp_code, summary, summary_method, summary_version, pipeline_version)
    VALUES (%s,%s,%s,%s,%s,%s,%s)
    ON DUPLICATE KEY UPDATE
      summary=VALUES(summary), summary_method=VALUES(summary_method),
      summary_version=VALUES(summary_version)
    """
    p = META / "chunk_summary.jsonl"
    if not p.is_file():
        print("  chunk_summary.jsonl 없음 — skip")
        return 0
    rows = []
    for line in p.open(encoding="utf-8"):
        r = json.loads(line)
        rows.append((
            r["chunk_id"], run_id, r.get("corp_code"),
            r.get("summary"), r.get("summary_method"),
            r.get("summary_version"), r.get("pipeline_version", "2026.05.24.v1"),
        ))
    cur.executemany(sql, rows); conn.commit()
    cur.close()
    print(f"  chunk_summary: {len(rows)}")
    return len(rows)


def load_news_matched(conn, run_id: str) -> int:
    cur = conn.cursor()
    sql = """
    INSERT INTO news_matched
      (news_id, run_id, url, title, published, publisher,
       matched_corps, rule_hits, llm_hits, method, pipeline_version)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON DUPLICATE KEY UPDATE
      matched_corps=VALUES(matched_corps), method=VALUES(method)
    """
    p = META / "news_matched.jsonl"
    if not p.is_file():
        print("  news_matched.jsonl 없음 — skip")
        return 0
    rows = []
    for line in p.open(encoding="utf-8"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        pub = r.get("published")
        if pub and len(str(pub)) >= 19:
            try:
                pub = datetime.fromisoformat(str(pub).replace("Z","+00:00")).replace(tzinfo=None)
            except Exception:
                pub = None
        else:
            pub = None
        rows.append((
            r.get("news_id") or r.get("id") or "", run_id,
            r.get("url"), r.get("title"), pub, r.get("publisher"),
            json.dumps(r.get("matched_corps", []), ensure_ascii=False),
            json.dumps(r.get("rule_hits", {}), ensure_ascii=False),
            json.dumps(r.get("llm_hits", {}), ensure_ascii=False),
            r.get("method"), "2026.05.24.v1",
        ))
    if rows:
        cur.executemany(sql, rows); conn.commit()
    cur.close()
    print(f"  news_matched: {len(rows)}")
    return len(rows)


def load_dart_raw_index(conn, run_id: str) -> int:
    """rawData/{corp}/dart/*.json → RDB. body_json 컬럼에 본문 포함 (SSOT).
    파일은 백업·캐시용으로 유지."""
    from polaris.config import DATA_ROOT
    cur = conn.cursor()
    sql = """
    INSERT INTO dart_raw_index
      (corp_code, rcept_no, endpoint, hash8, raw_path, body_json, status, collected_at, run_id)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON DUPLICATE KEY UPDATE
      raw_path=VALUES(raw_path), body_json=VALUES(body_json), status=VALUES(status)
    """
    n = 0
    for corp in CORPS:
        dart_dir = RAW / corp / "dart"
        if not dart_dir.is_dir():
            continue
        rows = []
        for jf in dart_dir.glob("*.json"):
            stem = jf.stem
            if "__" not in stem:
                continue
            endpoint, hash8 = stem.split("__", 1)
            try:
                body_text = jf.read_text(encoding="utf-8")
                payload = json.loads(body_text)
            except Exception:
                continue
            status = payload.get("status", "")
            params = payload.get("params") or {}
            rcept = params.get("rcept_no") or payload.get("rcept_no") or ""
            rel_path = jf.relative_to(DATA_ROOT).as_posix()
            rows.append((corp, rcept, endpoint, hash8, rel_path, body_text, status, None, run_id))
        for i in range(0, len(rows), BATCH):
            cur.executemany(sql, rows[i:i+BATCH]); conn.commit()
        n += len(rows)
        print(f"  dart_raw_index ← {corp}: 누적 {n} (body_json 포함)")
    cur.close()
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tables", default="all",
                    help="all 또는 콤마 (chunk,doc,summary,news,raw)")
    args = ap.parse_args()
    targets = ["chunk", "doc", "summary", "news", "raw"] if args.tables == "all" \
        else args.tables.split(",")

    t0 = time.time()
    conn = mariadb_conn()
    run_id = acquire_standby_run_id(conn)
    stats = {}
    if "chunk"   in targets: stats["chunk_index"]     = load_chunk_index(conn, run_id)
    if "doc"     in targets: stats["document_index"]  = load_document_index(conn, run_id)
    if "summary" in targets: stats["chunk_summary"]   = load_chunk_summary(conn, run_id)
    if "news"    in targets: stats["news_matched"]    = load_news_matched(conn, run_id)
    if "raw"     in targets: stats["dart_raw_index"]  = load_dart_raw_index(conn, run_id)
    conn.close()
    elapsed = time.time() - t0
    print(f"\n=== MariaDB 적재 완료 ({elapsed:.1f}s) ===")
    print(f"  run_id: {run_id}")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
