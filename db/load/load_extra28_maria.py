"""MariaDB 적재 — 28개 연결사 dart_raw_index · document_index · chunk_index (멱등 upsert).

설계 SSOT: docs/DBdocs/01_mariadb.md. 임의 컬럼/테이블 추가 금지.
load_mariadb.py 와 동일 로직. CORP_CODE 만 extra28/corps.tsv 기준.
- dart_raw_index : raw/{회사명}/**/*.json → 1행/파일
- document_index : list/list_*.json 의 항목들 rcept_no dedup
- chunk_index    : chunk/output/{회사명}_*.jsonl 청크
재실행 안전: PK 충돌 시 UPDATE (ON DUPLICATE KEY).
임베딩(Qdrant)은 미포함 — 다음 단계에서 별도 실행.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import mariadb_conn  # noqa: E402

DB_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = DB_DIR / "raw"
CHUNK_DIR = DB_DIR / "chunk" / "output"
CORPS_TSV = DB_DIR / "extra28" / "corps.tsv"

# extra28/corps.tsv 에서 corp_code 로딩 (회사명 → corp_code)
CORP_CODE_EXTRA28: dict[str, str] = {}
with CORPS_TSV.open(encoding="utf-8") as _f:
    for _line in _f:
        _line = _line.strip()
        if not _line or _line.startswith("corp_code"):
            continue
        _parts = _line.split("\t")
        if len(_parts) >= 2:
            _code = _parts[0].strip()
            _name = _parts[1].strip()
            if _code and _name:
                CORP_CODE_EXTRA28[_name] = _code


def sha1_8(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:8]


def endpoint_base(filename: str) -> str:
    """파일명 베이스 → endpoint. '__년_코드' 접미사 제거, .json 제거."""
    stem = filename[:-5] if filename.endswith(".json") else filename
    return stem.split("__", 1)[0]


def iter_raw_files_extra28():
    """raw 폴더 내 extra28 회사 JSON 파일을 (corp_code, endpoint, hash8, path) 로 산출."""
    for corp_dir in RAW_DIR.iterdir():
        if not corp_dir.is_dir():
            continue
        corp_code = CORP_CODE_EXTRA28.get(corp_dir.name)
        if not corp_code:
            continue
        for path in corp_dir.rglob("*.json"):
            ep = endpoint_base(path.name)
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
    for corp_code, ep, h8, path in iter_raw_files_extra28():
        body = path.read_text(encoding="utf-8")
        rcept_no = None
        try:
            obj = json.loads(body)
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
    """extra28 list_*.json 항목들 rcept_no 단위 dedup upsert."""
    sql = (
        "INSERT INTO document_index "
        "(rcept_no, corp_code, corp_name, doc_type, date, title, summary_short) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s) "
        "ON DUPLICATE KEY UPDATE corp_code=VALUES(corp_code), corp_name=VALUES(corp_name), "
        "doc_type=VALUES(doc_type), date=VALUES(date), title=VALUES(title)"
    )
    seen: dict[str, tuple] = {}
    for corp_dir in RAW_DIR.iterdir():
        if not corp_dir.is_dir():
            continue
        if corp_dir.name not in CORP_CODE_EXTRA28:
            continue
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
    # extra28 회사명 집합 (JSONL 파일명 prefix 매칭)
    extra28_names = set(CORP_CODE_EXTRA28.keys())
    for path in sorted(CHUNK_DIR.glob("*.jsonl")):
        # 파일명 prefix 가 extra28 회사명인지 확인 (파일명: 회사명_rcept_no.jsonl)
        fname = path.name
        matched = False
        for name in extra28_names:
            if fname.startswith(name + "_"):
                matched = True
                break
        if not matched:
            continue
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                c = json.loads(line)
                section_path = (c.get("section_path") or "")[:256]
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
    print(f"extra28 대상 회사 {len(CORP_CODE_EXTRA28)}개: {list(CORP_CODE_EXTRA28.keys())}")
    conn = mariadb_conn()
    try:
        with conn.cursor() as cur:
            # 적재 전 행수
            for t in ("dart_raw_index", "document_index", "chunk_index"):
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                print(f"[BEFORE] {t} = {cur.fetchone()[0]}")

            print("\n[1/3] dart_raw_index 적재...")
            n_raw = load_dart_raw(cur)
            conn.commit()
            print(f"      dart_raw_index upsert rows: {n_raw}")

            print("[2/3] document_index 적재...")
            n_doc = load_document_index(cur)
            conn.commit()
            print(f"      document_index unique rcept_no: {n_doc}")

            print("[3/3] chunk_index 적재...")
            n_chk = load_chunk_index(cur)
            conn.commit()
            print(f"      chunk_index upsert rows: {n_chk}")

            # 적재 후 행수
            print()
            for t in ("dart_raw_index", "document_index", "chunk_index", "fin_metric", "extraction_provenance"):
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                print(f"[AFTER]  {t} = {cur.fetchone()[0]}")

            # 회사별 chunk_index 카운트
            print("\n[회사별 chunk_index 카운트]")
            for name, code in sorted(CORP_CODE_EXTRA28.items()):
                cur.execute("SELECT COUNT(*) FROM chunk_index WHERE corp_code=%s", (code,))
                cnt = cur.fetchone()[0]
                print(f"  {name}({code}): {cnt}")

            # 3사 무변화 확인
            print("\n[3사 기존 데이터 확인]")
            for name, code in [("삼성전자", "00126380"), ("SK하이닉스", "00164779"), ("한미반도체", "00161383")]:
                cur.execute("SELECT COUNT(*) FROM chunk_index WHERE corp_code=%s", (code,))
                cnt = cur.fetchone()[0]
                print(f"  {name}({code}) chunk_index: {cnt}")

    finally:
        conn.close()
    print("\nMariaDB extra28 적재 완료.")


if __name__ == "__main__":
    main()
