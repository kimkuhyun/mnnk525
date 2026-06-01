"""비정형 관계 추출 적재 — SK하이닉스 2026년 1분기 분기보고서 (rcept 20260515002287, 168청크).

EXTRACTIONS = Claude(에이전트)가 대상 rcept 의 청크 본문을 하나씩 읽고 본문 근거로
판단한 엔티티·엣지. 적재는 extract_helpers 의 멱등 헬퍼로 수행.
원장은 rcept 전용 ledger/20260515002287.jsonl 에만 기록. 정형 표(재무·지분·계열사) 제외, 본문 근거 비정형만.

실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_skhynix_q_20260515002287.py
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

RCEPT = "20260515002287"
SKH = "SK하이닉스"

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

    # ── 회사 개요: 주력 제품 DRAM/NAND + Foundry 병행 ──────────
    "d3ba98ff9ea79e20": {  # 회사 개요: 메모리(DRAM/NAND) 주력, Foundry 병행
        "entities": [
            (P, "dram", "DRAM"), (P, "nand flash", "NAND Flash"),
            (T, "foundry", "Foundry"),
        ],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "dram", "DRAM"), 0.97),
            E("PRODUCES", ("org", SKH), ("ent", P, "nand flash", "NAND Flash"), 0.97),
            E("USES_TECH", ("org", SKH), ("ent", T, "foundry", "Foundry"), 0.85),
        ],
    },
    # ── 매출 품목 표: DRAM, NAND Flash ─────────────────────────
    "509f23ace3ebf912": {  # 매출 품목 표: DRAM, NAND Flash 등
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "dram", "DRAM"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "nand flash", "NAND Flash"), 0.9),
        ],
    },
    # ── 메모리 분류 본문: DRAM(휘발성)·플래시(NAND) 생산 ───────
    "14e37fc2ec1cfadd": {  # 메모리 반도체: 당사는 DRAM과 플래시메모리 생산
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "dram", "DRAM"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "nand flash", "NAND Flash"), 0.9),
        ],
    },
    # ── 시스템 반도체: CMOS 이미지센서(CIS) 생산 ───────────────
    "574d775be14d97e1": {  # 시스템반도체 CIS 생산(2025.3 AI메모리로 전환)
        "entities": [
            (P, "cmos 이미지 센서", "CMOS 이미지 센서(CIS)"),
        ],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "cmos 이미지 센서", "CMOS 이미지 센서(CIS)"), 0.88),
        ],
    },
    # ── 연구개발 실적 표: PCIe Gen5 SSD(DLC), LPDDR6, DDR5 2nd ─
    "79ce385910756dc2": {  # R&D 실적: PCIe Gen5 SSD(DLC), 1cnm LPDDR6, 1cnm 16Gb DDR5 2nd
        "entities": [
            (P, "ssd", "SSD"),
            (T, "pcie gen5", "PCIe Gen5"),
            (T, "dlc", "DLC(Direct Liquid Cooling)"),
            (P, "lpddr6", "LPDDR6"),
            (P, "ddr5", "DDR5"),
        ],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "ssd", "SSD"), 0.9),
            E("USES_TECH", ("org", SKH), ("ent", T, "pcie gen5", "PCIe Gen5"), 0.88),
            E("USES_TECH", ("org", SKH), ("ent", T, "dlc", "DLC(Direct Liquid Cooling)"), 0.85),
            E("PRODUCES", ("org", SKH), ("ent", P, "lpddr6", "LPDDR6"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "ddr5", "DDR5"), 0.9),
        ],
    },
    # ── 그래픽스: GDDR7 출시 ───────────────────────────────────
    "0068bf5aba1760e4": {  # CXL 메모리, GDDR7 출시
        "entities": [
            (P, "gddr7", "GDDR7"),
            (T, "cxl", "CXL"),
        ],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "gddr7", "GDDR7"), 0.92),
            E("USES_TECH", ("org", SKH), ("ent", T, "cxl", "CXL"), 0.85),
        ],
    },
    # ── 그래픽스 GDDR7 + 게임콘솔 협력 ─────────────────────────
    "7a91bd38e46055f4": {  # GDDR7 출시(프리미엄 메모리 리더십), 게임콘솔 협력
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "gddr7", "GDDR7"), 0.9),
        ],
    },
    # ── 모바일 메모리: LPDDR5X/T 라인업 ────────────────────────
    "6cde6304ef7a0bee": {  # 모바일 메모리: 플래그십향 LPDDR5X/T
        "entities": [
            (P, "lpddr5x", "LPDDR5X"),
            (P, "lpddr5t", "LPDDR5T"),
        ],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "lpddr5x", "LPDDR5X"), 0.85),
            E("PRODUCES", ("org", SKH), ("ent", P, "lpddr5t", "LPDDR5T"), 0.82),
        ],
    },
    # ── 자동차용 메모리: DDR4/5, LPDDR4/5, Automotive HBM ──────
    "017971f941a76fc7": {  # Automotive: 범용 DDR4/5, LPDDR4/5, Automotive Grade & HBM
        "entities": [
            (P, "hbm", "HBM"),
            (P, "lpddr5", "LPDDR5"),
        ],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "ddr5", "DDR5"), 0.85),
            E("PRODUCES", ("org", SKH), ("ent", P, "lpddr5", "LPDDR5"), 0.85),
            E("PRODUCES", ("org", SKH), ("ent", P, "hbm", "HBM"), 0.85),
        ],
    },
    # ── NAND 경쟁력: 세계최초 321단 QLC, eSSD, Solidigm ────────
    "5a2e3e9e43ae9161": {  # 세계최초 321단 QLC 개발, PCIe Gen5, eSSD, Solidigm 통합시너지
        "entities": [
            (P, "qlc", "QLC"),
            (P, "essd", "엔터프라이즈 SSD(eSSD)"),
            (T, "pcie gen5", "PCIe Gen5"),
        ],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "qlc", "QLC"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "essd", "엔터프라이즈 SSD(eSSD)"), 0.88),
            E("USES_TECH", ("org", SKH), ("ent", T, "pcie gen5", "PCIe Gen5"), 0.85),
            E("RELATED_PARTY", ("org", SKH), ("org", "Solidigm"), 0.85, "통합시너지(자회사)"),
        ],
    },
    # ── 주요 계약 표: Rambus 특허 크로스 라이선스, Intel NAND 영업양수 ─
    "588a158fc1b828fc": {  # 주요계약: Rambus 특허 크로스라이선스, Intel NAND 영업양수
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "Rambus"), 0.88, "특허크로스라이선스"),
            E("RELATED_PARTY", ("org", SKH), ("org", "Intel"), 0.88, "영업양수(NAND사업)"),
        ],
    },
    # ── X. 대주주 영업거래: 해외판매법인 (계열 거래) ───────────
    "6d9f05b6f0add07d": {  # 영업거래: SK hynix America / Wuxi Sales
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix America"), 0.85, "해외판매법인(영업거래)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix Wuxi Semiconductor Sales"), 0.85, "해외판매법인(영업거래)"),
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
            print(f"[warn] EXTRACTIONS chunk {cid} 가 rcept {RCEPT} 에 없음 — 스킵")
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
    print(f"=== SK하이닉스 2026 1분기 ({RCEPT}) 비정형 추출 결과 ===")
    print(f"  이번 실행 처리 청크: {processed}  (기처리 스킵 {skipped})")
    print(f"  원장 누적 처리 청크: {total_done} / {len(rows)}")
    print(f"  엔티티 hasObject: {n_ent_total}")
    print(f"  엣지 총: {n_edge_total}  타입별: {edge_by_type}")
    print(f"  provenance 행: {n_prov_total}")


if __name__ == "__main__":
    run()
