"""비정형 관계 추출 적재 — 한미반도체 2026년 1분기 분기보고서 (rcept 20260515001572, 130청크).

EXTRACTIONS = Claude(에이전트)가 대상 rcept 청크 본문을 읽고 본문 근거로 판단한 엔티티·엣지.
적재는 extract_helpers 의 멱등 헬퍼로 수행. 원장은 rcept 전용 ledger/20260515001572.jsonl 에만.
정형 재무수치 표 제외, 본문 근거 비정형만. 환각 금지(본문에 있는 것만).

실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_hanmi_q_20260515001572.py
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

RCEPT = "20260515001572"
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

    # ── II. 사업의 내용 — 회사개요/주력장비 (신제품: BOC COB, WIDE TC, 2.5D TC, EMI 2.0X, MSVP 8.0) ──
    "a9d849389d160ba4": {  # HBM TC 본더(12/16단), WIDE TC 본더(출시예정), 하이브리드 본더, 수직통합제조
        "entities": [
            (P, "hbm tc bonder", "HBM TC BONDER"),
            (T, "thermal compression bonding", "열압착(Thermal Compression) 본딩"),
            (P, "wide tc 본더", "WIDE TC 본더"),
            (P, "하이브리드 본더", "하이브리드 본더"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "hbm tc bonder", "HBM TC BONDER"), 0.95),
            E("USES_TECH", ("org", HANMI), ("ent", T, "thermal compression bonding", "열압착(Thermal Compression) 본딩"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "wide tc 본더", "WIDE TC 본더"), 0.82),
            E("PRODUCES", ("org", HANMI), ("ent", P, "하이브리드 본더", "하이브리드 본더"), 0.82),
        ],
    },
    "a4c0e546f0cddfd9": {  # 시장여건: HBM TC 본더, WIDE TC 본더, 하이브리드 본더 (반복 본문)
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "hbm tc bonder", "HBM TC BONDER"), 0.93),
            E("PRODUCES", ("org", HANMI), ("ent", P, "wide tc 본더", "WIDE TC 본더"), 0.8),
            E("PRODUCES", ("org", HANMI), ("ent", P, "하이브리드 본더", "하이브리드 본더"), 0.8),
        ],
    },
    "7143322f002c31ac": {  # BOC COB 본더(세계최초 투인원), AI 2.5D 패키징(TC/FC/Die 본더), 적층형 GDDR, eSSD
        "entities": [
            (P, "boc cob 본더", "BOC COB 본더"),
            (T, "2.5d 패키징", "2.5D 패키징"),
            (P, "fc 본더", "FC 본더"),
            (P, "die 본더", "Die 본더"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "boc cob 본더", "BOC COB 본더"), 0.9),
            E("USES_TECH", ("org", HANMI), ("ent", T, "2.5d 패키징", "2.5D 패키징"), 0.85),
            E("PRODUCES", ("org", HANMI), ("ent", P, "fc 본더", "FC 본더"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "die 본더", "Die 본더"), 0.88),
        ],
    },
    "d12671e45306bdf3": {  # 6-SIDE INSPECTION, BOC COB 본더, AI 2.5D 패키징(TC/FC/Die 본더), GDDR/eSSD (반복)
        "entities": [
            (P, "6-side inspection", "6-SIDE INSPECTION"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "6-side inspection", "6-SIDE INSPECTION"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "boc cob 본더", "BOC COB 본더"), 0.88),
            E("USES_TECH", ("org", HANMI), ("ent", T, "2.5d 패키징", "2.5D 패키징"), 0.82),
            E("PRODUCES", ("org", HANMI), ("ent", P, "fc 본더", "FC 본더"), 0.86),
            E("PRODUCES", ("org", HANMI), ("ent", P, "die 본더", "Die 본더"), 0.86),
        ],
    },
    "c6da2343868b3324": {  # 하이브리드 본더, 6-SIDE INSPECTION (반복)
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "하이브리드 본더", "하이브리드 본더"), 0.8),
            E("PRODUCES", ("org", HANMI), ("ent", P, "6-side inspection", "6-SIDE INSPECTION"), 0.9),
        ],
    },
    "425bcf35be78a91b": {  # AI 2.5D 패키징, MSVP 8.0 시리즈, EMI SHIELD 2.0 X
        "entities": [
            (P, "micro saw vision placement", "micro SAW & VISION PLACEMENT"),
            (P, "msvp 8.0", "micro SAW & VISION PLACEMENT(MSVP) 8.0"),
            (P, "emi shield", "EMI Shield 장비"),
            (P, "emi shield 2.0 x", "EMI SHIELD 2.0 X"),
        ],
        "edges": [
            E("USES_TECH", ("org", HANMI), ("ent", T, "2.5d 패키징", "2.5D 패키징"), 0.82),
            E("PRODUCES", ("org", HANMI), ("ent", P, "micro saw vision placement", "micro SAW & VISION PLACEMENT"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "msvp 8.0", "micro SAW & VISION PLACEMENT(MSVP) 8.0"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield", "EMI Shield 장비"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield 2.0 x", "EMI SHIELD 2.0 X"), 0.9),
        ],
    },
    "eed2a923f86fd23b": {  # MSVP 8.0(PLP/Chiplet), EMI SHIELD 2.0 X (반복)
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "micro saw vision placement", "micro SAW & VISION PLACEMENT"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "msvp 8.0", "micro SAW & VISION PLACEMENT(MSVP) 8.0"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield", "EMI Shield 장비"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield 2.0 x", "EMI SHIELD 2.0 X"), 0.88),
        ],
    },
    "0d67f05a4258a0d2": {  # EMI Shield (방산용 드론/스마트 디바이스 전자파 차폐)
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield", "EMI Shield 장비"), 0.85),
        ],
    },
    "530ee9fa10d3f3ad": {  # 연구개발 실적 표: 전 장비군 + TC BONDER 4.5 GRIFFIN/4.0 TIGER/2.5D TC 120·40·BOC COB + FC BONDER 3.5/3.0/5.0/MULTI DIE 2.0/FC 75
        "entities": [
            (P, "flip chip bonder", "FLIP CHIP BONDER"),
            (P, "multi die bonder", "MULTI DIE BONDER"),
            (P, "meta grinder", "META GRINDER"),
            (P, "laser marking", "LASER MARKING"),
            (P, "laser cutting", "LASER CUTTING"),
            (P, "laser ablation", "LASER ABLATION"),
            (P, "3d vision inspection", "3D VISION INSPECTION"),
            (P, "vision inspection", "VISION INSPECTION"),
            (P, "pick & place", "PICK & PLACE"),
            (T, "secs/gem", "SECS/GEM 통신모듈"),
            (P, "micro saw", "micro SAW"),
            (P, "2.5d tc bonder", "2.5D TC BONDER"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "micro saw vision placement", "micro SAW & VISION PLACEMENT"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "micro saw", "micro SAW"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield", "EMI Shield 장비"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "hbm tc bonder", "HBM TC BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "2.5d tc bonder", "2.5D TC BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "boc cob 본더", "BOC COB 본더"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "6-side inspection", "6-SIDE INSPECTION"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "flip chip bonder", "FLIP CHIP BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "multi die bonder", "MULTI DIE BONDER"), 0.9),
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
    "5c8a80df5819aad7": {  # 7공장 — 하이브리드 본더 전용 공장(차세대 프리미엄 HBM)
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "하이브리드 본더", "하이브리드 본더"), 0.8),
        ],
    },

    # ── II. 주요매출처 (SUPPLIES_TO: 한미 → 고객) — 본문상 삼성전자 누락, 삼성전기 포함 ──
    "0e7aa840094235eb": {  # 매출처: SK하이닉스/Micron/ASE/Amkor/JCET/Huatian/TFME/Infineon/STMicro/PTI/Skyworks/Luxshare/삼성전기/LG이노텍/코리아써키트/SFA반도체/시그네틱스
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
            E("SUPPLIES_TO", ("org", HANMI), ("org", "LG이노텍"), 0.86),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "코리아써키트"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "SFA반도체"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "시그네틱스"), 0.85),
        ],
    },

    # ── XI. 투자자 보호 — 소송 (RELATED_PARTY) ──
    "3a34571363311c8d": {  # 소송 2건: 한미↔한화세미텍 상호 특허침해
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "한화세미텍"), 0.9, "특허침해소송(원고)"),
            E("RELATED_PARTY", ("org", "한화세미텍"), ("org", HANMI), 0.9, "특허침해소송(원고)"),
        ],
    },

    # ── III. 연결재무제표 주석 — 특수관계자 (RELATED_PARTY) ──
    "e4917b8e457e71cc": {  # 연결실체 특수관계자: 곽신홀딩스(관계기업), 한미인터내셔널·도야인터내셔날(기타특수관계자)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "곽신홀딩스"), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "한미인터내셔널"), 0.88, "기타특수관계자"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "도야인터내셔날"), 0.88, "기타특수관계자"),
        ],
    },
    "d4f68c27b96b89cd": {  # 별도 특수관계자: 종속기업 Hanmi Taiwan/Vietnam/Singapore + 곽신홀딩스 등
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "Hanmi Taiwan"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "Hanmi Vietnam"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "Hanmi Singapore"), 0.9, "종속기업"),
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
    print(f"=== 한미반도체 2026 1분기 ({RCEPT}) 비정형 추출 결과 ===")
    print(f"  이번 실행 처리 청크: {processed}  (기처리 스킵 {skipped})")
    print(f"  원장 누적 처리 청크: {total_done} / {len(rows)}")
    print(f"  엔티티 hasObject: {n_ent_total}")
    print(f"  엣지 총: {n_edge_total}  타입별: {edge_by_type}")
    print(f"  provenance 행: {n_prov_total}")


if __name__ == "__main__":
    run()
