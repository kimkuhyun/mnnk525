"""회사 단위 Haiku 배치 추출 러너 (병렬 웨이브 + 청크단위 원장 = 누락0).

흐름:
  1) prep  <corp> <wave> <bsize> : 원장에 없는 사전필터 통과 청크를 배치파일로 씀.
        _auto/batch_<corp>_<i>.json = {"subject":회사명, "chunks":[{chunk_id,rcept_no,text}...]}
  2) (오케스트레이터가) Haiku 서브에이전트 N개 병렬 — 각자 batch 파일 Read, result 파일 Write.
        _auto/result_<corp>_<i>.json = [{"chunk_id":..,"entities":[..],"edges":[..]}]
  3) load  <corp> : result 파일들 → 앵커검증·캐논화 → Neo4j/MariaDB 적재 → 원장 mark → 파일 정리.

원장 = ledger/auto.jsonl (전역, chunk_id 단위). 재실행 안전(원장에 있으면 스킵, MERGE 멱등).
"""
from __future__ import annotations
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from db import mariadb_conn, neo4j_driver  # noqa: E402  (graph/db.py)
from extract_prompt import SKIP_WHERE, verify_and_canonicalize  # noqa: E402
from extract_helpers import (  # noqa: E402
    merge_entity, resolve_org, merge_org_node, add_edge, write_provenance, entity_id,
)

AUTO = HERE / "_auto"
LEDGER = HERE / "ledger" / "auto.jsonl"
CONF = 0.7  # Haiku 추출 기본 신뢰도

POSITIVE_WHERE = (
    "("
    " (section_path LIKE 'II.%' AND embedding_text REGEXP "
    "'주요 매출처|주요 고객|고객사|거래처|매출처|판매처|납품|공급|주요 매입처|매입처|원재료|원부재료|협력사|제품|기술|장비|소재|반도체|HBM|DRAM|NAND|OLED|LCD|PCB|FPCA|패키징|웨이퍼')"
    " OR ((section_path LIKE 'III.%' OR section_path LIKE 'IX.%' OR section_path LIKE 'X.%') "
    "AND embedding_text REGEXP "
    "'특수관계|관계기업|종속기업|계열회사|거래내역|매출|매입|지분|투자')"
    ")"
)


def corp_name(cur, corp_code: str) -> str:
    cur.execute("SELECT DISTINCT corp_name FROM document_index WHERE corp_code=%s LIMIT 1", (corp_code,))
    r = cur.fetchone()
    return r[0] if r else corp_code


def ledger_ids() -> set[str]:
    if not LEDGER.exists():
        return set()
    out = set()
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.add(json.loads(line)["chunk_id"])
            except Exception:
                pass
    return out


def mark(chunk_id: str, n_ent: int, n_edge: int, rcept_no: str):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"chunk_id": chunk_id, "n_ent": n_ent, "n_edge": n_edge,
                            "rcept_no": rcept_no}, ensure_ascii=False) + "\n")


# ── prep ───────────────────────────────────────────────────
def prep(corp_code: str, wave: int, bsize: int, *, positive: bool = False):
    done = ledger_ids()
    conn = mariadb_conn(); cur = conn.cursor()
    subject = corp_name(cur, corp_code)
    where = POSITIVE_WHERE if positive else SKIP_WHERE
    cur.execute(
        f"SELECT chunk_id, rcept_no, embedding_text FROM chunk_index "
        f"WHERE corp_code=%s AND {where.replace('%', '%%')} ORDER BY chunk_id",
        (corp_code,))
    rows = [r for r in cur.fetchall() if r[0] not in done]
    conn.close()
    AUTO.mkdir(exist_ok=True)
    # 기존 배치/결과 잔재 정리
    for f in AUTO.glob(f"batch_{corp_code}_*.json"): f.unlink()
    for f in AUTO.glob(f"result_{corp_code}_*.json"): f.unlink()
    for f in AUTO.glob(f"review_{corp_code}_*.jsonl"): f.unlink()
    take = rows[: wave * bsize]
    nb = 0
    for i in range(0, len(take), bsize):
        chunk = take[i:i + bsize]
        nb += 1
        payload = {"subject": subject, "chunks": [
            {"chunk_id": c, "rcept_no": r, "text": t} for c, r, t in chunk]}
        (AUTO / f"batch_{corp_code}_{nb-1}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    mode = "positive" if positive else "default"
    print(f"corp={corp_code}({subject}) mode={mode} 남은 pending={len(rows)} | 이번 배치 {nb}개(각 ≤{bsize}청크)")
    print(f"배치파일: _auto/batch_{corp_code}_0..{nb-1}.json")
    return nb


# ── load ───────────────────────────────────────────────────
def _load_edge(driver, conn, subject, pred, obj, ent_label, chunk_id, rcept_no,
               extracted_by: str = "claude"):
    """추출 엣지 1건 → Neo4j add_edge + MariaDB provenance."""
    def org_match(name):
        o = resolve_org(name)
        if not o:
            return None
        merge_org_node(driver, o)
        return {"kind": "org", "org": o}, o["id"]

    if pred == "hasObject":
        lbl = ent_label.get(obj, "Product")
        eid = merge_entity(driver, lbl, obj.lower(), name=obj)
        frm = {"kind": "chunk", "chunk_id": chunk_id}
        to = {"kind": "entity", "label": lbl, "id": eid}
        add_edge(driver, "hasObject", frm, to, chunk_id, rcept_no, CONF,
                 extracted_by=extracted_by)
        write_provenance(conn, chunk_id, "hasObject", eid, chunk_id, rcept_no, CONF,
                         extracted_by=extracted_by)
    elif pred in ("PRODUCES", "USES_TECH"):
        sm = org_match(subject)
        if not sm: return
        lbl = ent_label.get(obj, "Technology" if pred == "USES_TECH" else "Product")
        eid = merge_entity(driver, lbl, obj.lower(), name=obj)
        to = {"kind": "entity", "label": lbl, "id": eid}
        add_edge(driver, pred, sm[0], to, chunk_id, rcept_no, CONF,
                 extracted_by=extracted_by)
        write_provenance(conn, sm[1], pred, eid, chunk_id, rcept_no, CONF,
                         extracted_by=extracted_by)
    elif pred in ("SUPPLIES_TO", "RELATED_PARTY"):
        # SUPPLIES_TO는 추출 결과의 명시 방향(subject -> object)을 존중한다.
        a_name, b_name = (subject, obj)
        am, bm = org_match(a_name), org_match(b_name)
        if not am or not bm: return
        add_edge(driver, pred, am[0], bm[0], chunk_id, rcept_no, CONF,
                 extracted_by=extracted_by)
        write_provenance(conn, am[1], pred, bm[1], chunk_id, rcept_no, CONF,
                         extracted_by=extracted_by)


def load(corp_code: str, extracted_by: str = "claude", *, keep_files: bool = False):
    # batch (텍스트) 와 result (추출) 매칭
    batches = {}
    for bf in AUTO.glob(f"batch_{corp_code}_*.json"):
        data = json.loads(bf.read_text(encoding="utf-8"))
        for c in data["chunks"]:
            batches[c["chunk_id"]] = c
    driver = neo4j_driver(); conn = mariadb_conn()
    n_chunk = n_ent = n_edge = 0
    processed_ids = set()
    for rf in sorted(AUTO.glob(f"result_{corp_code}_*.json")):
        try:
            results = json.loads(rf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [skip] {rf.name} 파싱실패: {e}"); continue
        for item in results:
            cid = item.get("chunk_id")
            if cid not in batches:
                continue
            text = batches[cid]["text"]; rno = batches[cid]["rcept_no"]
            clean = verify_and_canonicalize(item, text)
            ent_label = {c: t for c, t in clean["entities"]}
            for c, t in clean["entities"]:
                merge_entity(driver, t, c.lower(), name=c)
            for subj, pred, obj in clean["edges"]:
                try:
                    _load_edge(driver, conn, subj, pred, obj, ent_label, cid, rno,
                               extracted_by=extracted_by)
                    n_edge += 1
                except Exception as e:
                    print(f"    [edge fail] {pred} {obj}: {e}")
            conn.commit()
            n_ent += len(clean["entities"])
            mark(cid, len(clean["entities"]), len(clean["edges"]), rno)
            processed_ids.add(cid)
            n_chunk += 1
    # batch에 있었으나 result에 없는 청크 = 추출 0으로 mark(누락방지)
    for cid, c in batches.items():
        if cid not in processed_ids:
            mark(cid, 0, 0, c["rcept_no"])
            n_chunk += 1
    driver.close(); conn.close()
    # 정리
    if not keep_files:
        for f in AUTO.glob(f"batch_{corp_code}_*.json"): f.unlink()
        for f in AUTO.glob(f"result_{corp_code}_*.json"): f.unlink()
    suffix = "파일유지" if keep_files else "파일정리 완료"
    print(f"load 완료: 청크 {n_chunk}, 엔티티 {n_ent}, 엣지 {n_edge}, extracted_by={extracted_by} (원장 기록·{suffix})")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "prep":
        prep(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
    elif cmd == "prep-positive":
        prep(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), positive=True)
    elif cmd == "load":
        keep_files = "--keep-files" in sys.argv[3:]
        args = [a for a in sys.argv[3:] if a != "--keep-files"]
        load(sys.argv[2], args[0] if args else "claude", keep_files=keep_files)
