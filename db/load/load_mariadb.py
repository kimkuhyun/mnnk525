"""MariaDB 적재 — dart_raw_index · document_index · chunk_index (멱등 upsert).

설계 SSOT: docs/DBdocs/01_mariadb.md. 임의 컬럼/테이블 추가 금지.
- dart_raw_index : raw/*/{company.json, list/*, ds00x/*} 931 JSON → 1행/파일
- document_index : list_*.json 의 항목들 rcept_no dedup
- chunk_index    : chunk/output/*.jsonl 10,774 청크
재실행 안전: PK 충돌 시 UPDATE.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import CORP_CODE, mariadb_conn  # noqa: E402

DB_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = DB_DIR / "raw"
CHUNK_DIR = DB_DIR / "chunk" / "output"


def sha1_8(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:8]


def endpoint_base(filename: str) -> str:
    """파일명 베이스 → endpoint. '__년_코드' 접미사 제거, .json 제거."""
    stem = filename[:-5] if filename.endswith(".json") else filename
    return stem.split("__", 1)[0]


def load_schema(cur) -> None:
    sql = (Path(__file__).resolve().parent / "schema.sql").read_text(encoding="utf-8")
    for stmt in sql.split(";"):
        if stmt.strip():
            cur.execute(stmt)


def iter_raw_files():
    """raw 폴더 내 모든 JSON 파일을 (corp_code, endpoint, hash8, path) 로 산출."""
    for corp_dir in RAW_DIR.iterdir():
        if not corp_dir.is_dir():
            continue
        corp_code = CORP_CODE.get(corp_dir.name)
        if not corp_code:
            continue
        for path in corp_dir.rglob("*.json"):
            # pdf 등 비-JSON 폴더는 rglob('*.json') 으로 자연 제외
            ep = endpoint_base(path.name)
            # hash8 = 파일명(요청 식별)의 sha1 앞 8hex — 결정론적·중복호출 식별
            h8 = sha1_8(path.name)
            yield corp_code, ep, h8, path


def load_dart_raw(cur) -> int:
    sql = (
        "INSERT INTO dart_raw_index "
        "(corp_code, endpoint, hash8, rcept_no, body_json, status, collected_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s) "
        "ON DUPLICATE KEY UPDATE rcept_no=VALUES(rcept_no), body_json=VALUES(body_json), "
        "status=VALUES(status), collected_at=VALUES(collected_at)"
    )
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n = 0
    for corp_code, ep, h8, path in iter_raw_files():
        body = path.read_text(encoding="utf-8")
        # rcept_no: 단일 문서 응답에만 추출. company/list/ds00x 는 집계 응답 → NULL.
        rcept_no = None
        try:
            obj = json.loads(body)
            # 최상위에 단일 rcept_no 가 있는 경우만(집계 list 안의 건별 rcept_no 는 제외)
            if isinstance(obj, dict) and isinstance(obj.get("rcept_no"), str):
                rv = obj["rcept_no"]
                if len(rv) == 14 and rv.isdigit():
                    rcept_no = rv
        except json.JSONDecodeError:
            pass
        cur.execute(sql, (corp_code, ep, h8, rcept_no, body, "ok", now))
        n += 1
    return n


def load_document_index(cur) -> int:
    """list_*.json 항목들 rcept_no 단위 dedup upsert."""
    sql = (
        "INSERT INTO document_index "
        "(rcept_no, corp_code, corp_name, doc_type, date, title, summary_short) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s) "
        "ON DUPLICATE KEY UPDATE corp_code=VALUES(corp_code), corp_name=VALUES(corp_name), "
        "doc_type=VALUES(doc_type), date=VALUES(date), title=VALUES(title)"
    )
    seen: dict[str, tuple] = {}
    for corp_dir in RAW_DIR.iterdir():
        list_dir = corp_dir / "list"
        if not list_dir.is_dir():
            continue
        for path in sorted(list_dir.glob("list_*.json")):
            obj = json.loads(path.read_text(encoding="utf-8"))
            for it in obj.get("list", []) or []:
                rno = it.get("rcept_no")
                if not rno:
                    continue
                report_nm = (it.get("report_nm") or "").strip()
                rdt = it.get("rcept_dt") or ""
                date = None
                if len(rdt) == 8 and rdt.isdigit():
                    date = f"{rdt[:4]}-{rdt[4:6]}-{rdt[6:8]}"
                seen[rno] = (
                    rno,
                    it.get("corp_code"),
                    (it.get("corp_name") or "")[:64],
                    report_nm[:128],
                    date,
                    report_nm[:256],
                    None,
                )
    for row in seen.values():
        cur.execute(sql, row)
    return len(seen)


def load_chunk_index(cur) -> int:
    sql = (
        "INSERT INTO chunk_index "
        "(chunk_id, corp_code, rcept_no, chunk_type, section_path, embedding_text, token_count, ingest_status) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,'pending') "
        "ON DUPLICATE KEY UPDATE corp_code=VALUES(corp_code), rcept_no=VALUES(rcept_no), "
        "chunk_type=VALUES(chunk_type), section_path=VALUES(section_path), "
        "embedding_text=VALUES(embedding_text), token_count=VALUES(token_count)"
    )
    n = 0
    for path in sorted(CHUNK_DIR.glob("*.jsonl")):
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                c = json.loads(line)
                section_path = (c.get("section_path") or "")[:256]  # VARCHAR(256) 안전 절단
                cur.execute(
                    sql,
                    (
                        c["chunk_id"],
                        c.get("corp_code"),
                        c.get("rcept_no"),
                        c.get("chunk_type"),
                        section_path,
                        c.get("embedding_text"),
                        c.get("token_count"),
                    ),
                )
                n += 1
    return n


def main() -> None:
    conn = mariadb_conn()
    try:
        with conn.cursor() as cur:
            print("[1/4] 스키마 생성(IF NOT EXISTS)...")
            load_schema(cur)
            conn.commit()

            print("[2/4] dart_raw_index 적재...")
            n_raw = load_dart_raw(cur)
            conn.commit()
            print(f"      dart_raw_index upsert rows: {n_raw}")

            print("[3/4] document_index 적재...")
            n_doc = load_document_index(cur)
            conn.commit()
            print(f"      document_index unique rcept_no: {n_doc}")

            print("[4/4] chunk_index 적재...")
            n_chk = load_chunk_index(cur)
            conn.commit()
            print(f"      chunk_index upsert rows: {n_chk}")

            # 검증
            for t in ("dart_raw_index", "document_index", "chunk_index", "fin_metric", "extraction_provenance"):
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                print(f"  COUNT {t} = {cur.fetchone()[0]}")
    finally:
        conn.close()
    print("MariaDB 적재 완료.")


if __name__ == "__main__":
    main()
