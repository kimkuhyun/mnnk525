"""비정형 관계 추출 적재 — 한미반도체 2024년 반기보고서 (rcept 20240814003244, 264청크).

원장은 rcept 전용 ledger/20240814003244.jsonl 에만. 시작 시 기처리 청크 스킵,
대상 청크 전부 mark_processed(엣지 0개여도) → 누락 0. 정형 재무표 제외, 본문 근거 비정형만.

실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_hanmi_q_20240814003244.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_helpers import (  # noqa: E402
    add_edge,
    get_chunks,
    mariadb_conn,
    merge_entity,
    merge_org_node,
    neo4j_driver,
    resolve_org,
    write_provenance,
)

RCEPT = "20240814003244"
HANMI = "한미반도체"

LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_PATH = LEDGER_DIR / f"{RCEPT}.jsonl"

P = "Product"
T = "Technology"


def E(rel, frm, to, conf, relation_type=None):
    d = {"rel": rel, "from": frm, "to": to, "conf": conf}
    if relation_type:
        d["relation_type"] = relation_type
    return d


def mark_processed(chunk_id, n_ent, n_edge, rcept_no=None, section_path=None):
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    rec = {
        "chunk_id": chunk_id, "n_ent": n_ent, "n_edge": n_edge,
        "rcept_no": rcept_no, "section_path": section_path,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def ledger_processed_ids():
    if not LEDGER_PATH.exists():
        return set()
    ids = set()
    for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ids.add(json.loads(line)["chunk_id"])
        except Exception:
            continue
    return ids


# ── Claude 추출 결과 (청크별, 본문 근거 있는 것만) ──────────────
EXTRACTIONS: dict[str, dict] = {

    # 제조용 장비 라인업 나열 + DUAL TC Bonder(2017 SK하이닉스 공동개발)
    "0a56ebebdd21e151": {
        "entities": [
            (P, "dual tc bonder", "DUAL TC BONDER"),
            (P, "hbm 6-side inspection", "HBM 6-SIDE INSPECTION"),
            (P, "micro saw", "micro SAW"),
            (P, "vision placement", "VISION PLACEMENT"),
            (P, "flip chip bonder", "FLIP CHIP BONDER"),
            (P, "emi shield 장비", "EMI Shield 장비"),
            (P, "meta grinder", "META GRINDER"),
            (P, "tape saw", "TAPE SAW"),
            (P, "wafer saw", "Wafer SAW"),
            (P, "laser equipment", "LASER EQUIPMENT"),
            (T, "열압착 본딩", "열압착(Thermal Compression) 본딩"),
            (T, "hbm", "HBM(광대역폭메모리)"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "dual tc bonder", "DUAL TC BONDER"), 0.95),
            E("PRODUCES", ("org", HANMI), ("ent", P, "hbm 6-side inspection", "HBM 6-SIDE INSPECTION"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "micro saw", "micro SAW"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "vision placement", "VISION PLACEMENT"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "flip chip bonder", "FLIP CHIP BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield 장비", "EMI Shield 장비"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "meta grinder", "META GRINDER"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "tape saw", "TAPE SAW"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "wafer saw", "Wafer SAW"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "laser equipment", "LASER EQUIPMENT"), 0.85),
            E("USES_TECH", ("org", HANMI), ("ent", T, "열압착 본딩", "열압착(Thermal Compression) 본딩"), 0.9),
            E("USES_TECH", ("org", HANMI), ("ent", T, "hbm", "HBM(광대역폭메모리)"), 0.85),
            E("RELATED_PARTY", ("org", HANMI), ("org", "SK하이닉스"), 0.9, "DUAL TC Bonder 공동개발(2017)"),
        ],
    },
    # 시장여건·경쟁상황: DUAL TC BONDER 2017 SK하이닉스 공동개발
    "dc008e367cdb47ab": {
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "dual tc bonder", "DUAL TC BONDER"), 0.92),
            E("USES_TECH", ("org", HANMI), ("ent", T, "열압착 본딩", "열압착(Thermal Compression) 본딩"), 0.88),
            E("USES_TECH", ("org", HANMI), ("ent", T, "hbm", "HBM(광대역폭메모리)"), 0.82),
            E("RELATED_PARTY", ("org", HANMI), ("org", "SK하이닉스"), 0.9, "DUAL TC Bonder 공동개발(2017)"),
        ],
    },
    # TC BONDER HBM 핵심, 6-SIDE INSPECTION, FLIP CHIP/MULTI DIE/BIG DIE BONDER
    "02bb51798276a839": {
        "entities": [
            (P, "multi die bonder", "MULTI DIE BONDER"),
            (P, "big die bonder", "BIG DIE BONDER"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "hbm 6-side inspection", "HBM 6-SIDE INSPECTION"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "flip chip bonder", "FLIP CHIP BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "multi die bonder", "MULTI DIE BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "big die bonder", "BIG DIE BONDER"), 0.9),
            E("USES_TECH", ("org", HANMI), ("ent", T, "hbm", "HBM(광대역폭메모리)"), 0.82),
        ],
    },
    # 6-SIDE INSPECTION, Flip Chip Bonder, micro SAW/VISION PLACEMENT 세계1위
    "a09983e4167db16d": {
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "hbm 6-side inspection", "HBM 6-SIDE INSPECTION"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "flip chip bonder", "FLIP CHIP BONDER"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "multi die bonder", "MULTI DIE BONDER"), 0.85),
            E("PRODUCES", ("org", HANMI), ("ent", P, "micro saw", "micro SAW"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "vision placement", "VISION PLACEMENT"), 0.9),
        ],
    },
    # BIG DIE BONDER, micro SAW/VISION PLACEMENT, EMI Shield
    "66a5f0e275f5aae2": {
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "big die bonder", "BIG DIE BONDER"), 0.85),
            E("PRODUCES", ("org", HANMI), ("ent", P, "micro saw", "micro SAW"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "vision placement", "VISION PLACEMENT"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield 장비", "EMI Shield 장비"), 0.9),
        ],
    },
    # 연구개발 실적 표: micro SAW 시리즈, EMI Shield, TC BONDER, FLIP CHIP, META GRINDER, LASER 등
    "0a09c579e6c41f6c": {
        "entities": [
            (P, "laser marking", "LASER MARKING"),
            (P, "laser cutting", "LASER CUTTING"),
            (P, "pick & place", "PICK & PLACE"),
            (T, "flip chip 패키징", "Flip-Chip 패키징"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "vision placement", "VISION PLACEMENT"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "micro saw", "micro SAW"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield 장비", "EMI Shield 장비"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "dual tc bonder", "DUAL TC BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "flip chip bonder", "FLIP CHIP BONDER"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "meta grinder", "META GRINDER"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "laser marking", "LASER MARKING"), 0.85),
            E("PRODUCES", ("org", HANMI), ("ent", P, "laser cutting", "LASER CUTTING"), 0.85),
            E("PRODUCES", ("org", HANMI), ("ent", P, "pick & place", "PICK & PLACE"), 0.85),
            E("USES_TECH", ("org", HANMI), ("ent", T, "flip chip 패키징", "Flip-Chip 패키징"), 0.82),
        ],
    },
    # 주요매출처: ASE, Amkor, Micron, Infineon, ST Micro, SK하이닉스, 삼성전기, 삼성전자, LG이노텍 등
    "347feaea95e111e1": {
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", HANMI), ("org", "SK하이닉스"), 0.88),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "삼성전자"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "삼성전기"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Micron Technology"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "ASE"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Amkor"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Infineon"), 0.82),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "STMicroelectronics"), 0.82),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "LG이노텍"), 0.82),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "JCET"), 0.8),
        ],
    },
}


def _match_and_id(driver, ref):
    if ref[0] == "org":
        org = resolve_org(ref[1])
        merge_org_node(driver, org)
        return {"kind": "org", "org": org}, org["id"]
    _, label, canonical, name = ref
    eid = merge_entity(driver, label, canonical, name)
    return {"kind": "entity", "label": label, "id": eid}, eid


def run():
    rows = get_chunks(f"WHERE rcept_no='{RCEPT}'")
    by_id = {r["chunk_id"]: r for r in rows}
    print(f"[batch] 대상 청크 {len(rows)}건 (rcept {RCEPT})")

    done = ledger_processed_ids()
    print(f"[ledger] 기처리 {len(done)}건 (스킵 대상)")

    driver = neo4j_driver()
    conn = mariadb_conn()

    n_ent_total = n_edge_total = n_prov_total = 0
    edge_by_type: dict[str, int] = {}
    processed = skipped = 0

    for cid, payload in EXTRACTIONS.items():
        if cid not in by_id:
            continue
        if cid in done:
            skipped += 1
            continue
        row = by_id[cid]
        n_ent = n_edge = 0

        for label, canonical, name in payload.get("entities", []):
            eid = merge_entity(driver, label, canonical, name)
            add_edge(driver, "hasObject",
                     {"kind": "chunk", "chunk_id": cid},
                     {"kind": "entity", "label": label, "id": eid},
                     chunk_id=cid, rcept_no=RCEPT, confidence=1.0)
            write_provenance(conn, cid, "hasObject", eid, cid, RCEPT, 1.0)
            n_ent += 1
            n_prov_total += 1

        for e in payload.get("edges", []):
            rel, frm, to, conf = e["rel"], e["from"], e["to"], e["conf"]
            rtype = e.get("relation_type")
            fm, fid = _match_and_id(driver, frm)
            tm, tid = _match_and_id(driver, to)
            add_edge(driver, rel, fm, tm, chunk_id=cid, rcept_no=RCEPT,
                     confidence=conf, relation_type=rtype)
            write_provenance(conn, fid, rel, tid, cid, RCEPT, conf)
            n_edge += 1
            n_prov_total += 1
            edge_by_type[rel] = edge_by_type.get(rel, 0) + 1

        conn.commit()
        mark_processed(cid, n_ent, n_edge, RCEPT, row["section_path"])
        n_ent_total += n_ent
        n_edge_total += n_edge
        processed += 1

    extracted_ids = set(EXTRACTIONS.keys())
    for r in rows:
        cid = r["chunk_id"]
        if cid in extracted_ids or cid in done:
            continue
        mark_processed(cid, 0, 0, RCEPT, r["section_path"])
        processed += 1

    conn.close()
    driver.close()

    total_done = len(ledger_processed_ids())
    print(f"=== 한미반도체 2024 반기 ({RCEPT}) 비정형 추출 결과 ===")
    print(f"  이번 실행 처리 청크: {processed}  (기처리 스킵 {skipped})")
    print(f"  원장 누적 처리 청크: {total_done} / {len(rows)}")
    print(f"  엔티티 hasObject: {n_ent_total}")
    print(f"  엣지 총: {n_edge_total}  타입별: {edge_by_type}")
    print(f"  provenance 행: {n_prov_total}")


if __name__ == "__main__":
    run()
