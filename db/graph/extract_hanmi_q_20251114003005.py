"""비정형 관계 추출 적재 — 한미반도체 2025년 3분기 분기보고서 (rcept 20251114003005, 141청크).

EXTRACTIONS = Claude(에이전트)가 대상 rcept 청크 본문을 읽고 본문 근거로 판단한 엔티티·엣지.
적재는 extract_helpers 의 멱등 헬퍼로 수행. 원장은 rcept 전용 ledger/20251114003005.jsonl 에만.
정형 재무수치 표 제외, 본문 근거 비정형만. 환각 금지(본문에 있는 것만).

실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_hanmi_q_20251114003005.py
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

RCEPT = "20251114003005"
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


EXTRACTIONS: dict[str, dict] = {

    # ── II. 사업의 내용 — 회사개요/주력장비 ──
    "1047d34545ba8526": {  # 주력장비 나열: HBM TC BONDER, 6-SIDE INSPECTION, MSVP, FLIP CHIP BONDER, EMI Shield, CAMERA MODULE, LASER, META GRINDER, TAPE/WAFER SAW + 하이브리드 본더
        "entities": [
            (P, "hbm tc bonder", "HBM TC BONDER"),
            (T, "thermal compression bonding", "열압착(Thermal Compression) 본딩"),
            (P, "6-side inspection", "6-SIDE INSPECTION"),
            (P, "micro saw vision placement", "micro SAW & VISION PLACEMENT"),
            (P, "flip chip bonder", "FLIP CHIP BONDER"),
            (P, "emi shield", "EMI Shield 장비"),
            (P, "camera module 장비", "CAMERA MODULE용 장비"),
            (P, "laser equipment", "LASER EQUIPMENT"),
            (P, "meta grinder", "META GRINDER"),
            (P, "tape saw", "TAPE SAW"),
            (P, "wafer saw", "WAFER SAW"),
            (P, "하이브리드 본더", "하이브리드 본더"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "hbm tc bonder", "HBM TC BONDER"), 0.95),
            E("USES_TECH", ("org", HANMI), ("ent", T, "thermal compression bonding", "열압착(Thermal Compression) 본딩"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "6-side inspection", "6-SIDE INSPECTION"), 0.93),
            E("PRODUCES", ("org", HANMI), ("ent", P, "micro saw vision placement", "micro SAW & VISION PLACEMENT"), 0.93),
            E("PRODUCES", ("org", HANMI), ("ent", P, "flip chip bonder", "FLIP CHIP BONDER"), 0.93),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield", "EMI Shield 장비"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "camera module 장비", "CAMERA MODULE용 장비"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "laser equipment", "LASER EQUIPMENT"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "meta grinder", "META GRINDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "tape saw", "TAPE SAW"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "wafer saw", "WAFER SAW"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "하이브리드 본더", "하이브리드 본더"), 0.82),
        ],
    },
    "6275d9703368c852": {  # HBM TC BONDER 2017 SK하이닉스 공동개발·공급, 6-SIDE INSPECTION, 하이브리드 본더
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "hbm tc bonder", "HBM TC BONDER"), 0.93),
            E("PRODUCES", ("org", HANMI), ("ent", P, "6-side inspection", "6-SIDE INSPECTION"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "하이브리드 본더", "하이브리드 본더"), 0.82),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "SK하이닉스"), 0.9),  # 2017 공동개발하여 공급
        ],
    },
    "7b4ddaa9fa1e21dc": {  # 6-SIDE INSPECTION, FLIP CHIP/MULTI DIE/BIG DIE BONDER, MSVP, micro SAW
        "entities": [
            (P, "multi die bonder", "MULTI DIE BONDER"),
            (P, "big die bonder", "BIG DIE BONDER"),
            (P, "micro saw", "micro SAW"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "6-side inspection", "6-SIDE INSPECTION"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "flip chip bonder", "FLIP CHIP BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "multi die bonder", "MULTI DIE BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "big die bonder", "BIG DIE BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "micro saw vision placement", "micro SAW & VISION PLACEMENT"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "micro saw", "micro SAW"), 0.9),
        ],
    },
    "be8a25397f957dd7": {  # 하이브리드 본더, 6-SIDE INSPECTION, FLIP CHIP/MULTI DIE/BIG DIE BONDER, MSVP
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "하이브리드 본더", "하이브리드 본더"), 0.82),
            E("PRODUCES", ("org", HANMI), ("ent", P, "6-side inspection", "6-SIDE INSPECTION"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "flip chip bonder", "FLIP CHIP BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "multi die bonder", "MULTI DIE BONDER"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "big die bonder", "BIG DIE BONDER"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "micro saw vision placement", "micro SAW & VISION PLACEMENT"), 0.88),
        ],
    },
    "d0e6597e7fbc0a50": {  # micro SAW (국산화), EMI Shield
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "micro saw", "micro SAW"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield", "EMI Shield 장비"), 0.9),
        ],
    },
    "fbf4dd17e8a5a8d0": {  # EMI Shield (자동차 전장화/LEO/UAM/6G)
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield", "EMI Shield 장비"), 0.88),
        ],
    },
    "80779f4fc59f6b48": {  # 연구개발 실적 표: 전 장비군 + TC BONDER 4 (TIGER/GRIFFIN), FC BONDER 5.0/MULTI DIE 2.0/BIG DIE 2.0
        "entities": [
            (P, "laser marking", "LASER MARKING"),
            (P, "laser cutting", "LASER CUTTING"),
            (P, "laser ablation", "LASER ABLATION"),
            (P, "3d vision inspection", "3D VISION INSPECTION"),
            (P, "vision inspection", "VISION INSPECTION"),
            (P, "pick & place", "PICK & PLACE"),
            (T, "secs/gem", "SECS/GEM 통신모듈"),
            (P, "tc bonder 4 tiger", "TC BONDER 4 TIGER"),
            (P, "tc bonder 4 griffin", "TC BONDER 4 GRIFFIN"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "micro saw vision placement", "micro SAW & VISION PLACEMENT"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield", "EMI Shield 장비"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "hbm tc bonder", "HBM TC BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "tc bonder 4 tiger", "TC BONDER 4 TIGER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "tc bonder 4 griffin", "TC BONDER 4 GRIFFIN"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "6-side inspection", "6-SIDE INSPECTION"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "flip chip bonder", "FLIP CHIP BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "multi die bonder", "MULTI DIE BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "big die bonder", "BIG DIE BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "meta grinder", "META GRINDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "laser marking", "LASER MARKING"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "laser cutting", "LASER CUTTING"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "laser ablation", "LASER ABLATION"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "3d vision inspection", "3D VISION INSPECTION"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "vision inspection", "VISION INSPECTION"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "pick & place", "PICK & PLACE"), 0.9),
            E("USES_TECH", ("org", HANMI), ("ent", T, "secs/gem", "SECS/GEM 통신모듈"), 0.85),
        ],
    },

    # ── II. 시설투자: 7공장 하이브리드 본더 전용 (PRODUCES 하이브리드 본더) ──
    "b3900600ff487dfa": {  # 7공장 — 하이브리드 본더 전용 공장, 차세대 프리미엄 HBM
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "하이브리드 본더", "하이브리드 본더"), 0.82),
        ],
    },
    "daf753cf8bc0ef9d": {  # 7공장 투자 표: 차세대 프리미엄 HBM 하이브리드 본더 전용 공장
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "하이브리드 본더", "하이브리드 본더"), 0.8),
        ],
    },

    # ── II. 주요매출처 (SUPPLIES_TO: 한미 → 고객) ──
    "d2a07ea1b8c601f4": {  # 매출처: SK하이닉스/Micron/ASE/Amkor/JCET/Huatian/TFME/Infineon/STMicro/PTI/Skyworks/Luxshare/삼성전기/삼성전자/LG이노텍/코리아써키트/SFA반도체/시그네틱스
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", HANMI), ("org", "SK하이닉스"), 0.9),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Micron Technology"), 0.88),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "ASE"), 0.88),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Amkor"), 0.88),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "JCET"), 0.88),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Huatian Technology"), 0.86),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "TFME"), 0.86),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Infineon"), 0.86),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "ST Micro"), 0.86),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "PTI"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Skyworks"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Luxshare"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "삼성전기"), 0.88),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "삼성전자"), 0.88),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "LG이노텍"), 0.86),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "코리아써키트"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "SFA반도체"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "시그네틱스"), 0.85),
        ],
    },

    # ── XI. 투자자 보호 — 소송 (RELATED_PARTY) ──
    "80cf3eeac040e59c": {  # 소송 2건: 한미(원고)↔한화세미텍, 한화세미텍(원고)↔한미 (상호 특허침해)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "한화세미텍"), 0.9, "특허침해소송(원고)"),
            E("RELATED_PARTY", ("org", "한화세미텍"), ("org", HANMI), 0.9, "특허침해소송(원고)"),
        ],
    },

    # ── III. 연결재무제표 주석 — 특수관계자 (RELATED_PARTY) ──
    "f7cffce58bb5cda8": {  # 연결실체 특수관계자: 곽신홀딩스(관계기업), 한미인터내셔널·도야인터내셔날(기타특수관계자)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "곽신홀딩스"), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "한미인터내셔널"), 0.88, "기타특수관계자"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "도야인터내셔날"), 0.88, "기타특수관계자"),
        ],
    },
    "5e08ae82db881ee8": {  # 별도 특수관계자: 종속기업 Hanmi Taiwan/Vietnam + 곽신홀딩스 등
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "Hanmi Taiwan"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "Hanmi Vietnam"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "곽신홀딩스"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "한미인터내셔널"), 0.86, "기타특수관계자"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "도야인터내셔날"), 0.86, "기타특수관계자"),
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
    print(f"=== 한미반도체 2025 3분기 ({RCEPT}) 비정형 추출 결과 ===")
    print(f"  이번 실행 처리 청크: {processed}  (기처리 스킵 {skipped})")
    print(f"  원장 누적 처리 청크: {total_done} / {len(rows)}")
    print(f"  엔티티 hasObject: {n_ent_total}")
    print(f"  엣지 총: {n_edge_total}  타입별: {edge_by_type}")
    print(f"  provenance 행: {n_prov_total}")


if __name__ == "__main__":
    run()
