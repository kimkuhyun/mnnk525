"""비정형 관계 추출 적재 — 삼성전자 2024 3분기보고서 (rcept 20241114002642, 220청크 전체).

EXTRACTIONS = Claude(에이전트)가 대상 rcept 청크 본문을 읽고 본문 근거로 판단한
엔티티·엣지. 적재는 extract_helpers 멱등 헬퍼로 수행. 원장은 rcept 전용
ledger/20241114002642.jsonl 에만(공유 원장 금지). 대상 청크 전부
mark_processed(엣지 0개여도) → 누락 0.

실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_samsung2024q3.py
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

RCEPT = "20241114002642"
SAMSUNG = "삼성전자"

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

    # ── 부문 매출표: 주요 제품 (PRODUCES) ──────────────────────
    "8d64ce1a5ace7349": {  # DX: TV/모니터/냉장고/세탁기/에어컨/스마트폰/네트워크시스템/PC, DS: DRAM/NAND/모바일AP, SDC: OLED패널, Harman: 디지털콕핏/카오디오/포터블스피커
        "entities": [
            (P, "tv", "TV"), (P, "모니터", "모니터"), (P, "냉장고", "냉장고"),
            (P, "세탁기", "세탁기"), (P, "에어컨", "에어컨"), (P, "스마트폰", "스마트폰"),
            (P, "네트워크시스템", "네트워크시스템"), (P, "pc", "PC"),
            (P, "dram", "DRAM"), (P, "nand flash", "NAND Flash"), (P, "모바일ap", "모바일AP"),
            (P, "oled 패널", "OLED 패널"), (P, "디지털 콕핏", "디지털 콕핏"),
            (P, "카오디오", "카오디오"), (P, "포터블 스피커", "포터블 스피커"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "tv", "TV"), 0.95),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "모니터", "모니터"), 0.92),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "냉장고", "냉장고"), 0.95),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "세탁기", "세탁기"), 0.95),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "에어컨", "에어컨"), 0.95),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "스마트폰", "스마트폰"), 0.97),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "네트워크시스템", "네트워크시스템"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "pc", "PC"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "dram", "DRAM"), 0.97),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "nand flash", "NAND Flash"), 0.97),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "모바일ap", "모바일AP"), 0.95),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "oled 패널", "OLED 패널"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "디지털 콕핏", "디지털 콕핏"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "카오디오", "카오디오"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "포터블 스피커", "포터블 스피커"), 0.88),
        ],
    },
    "80e3617e1eeb25aa": {  # 주요 제품 매출 narrative: 완제품 + 반도체 + OLED패널 + Harman
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "tv", "TV"), 0.92),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "냉장고", "냉장고"), 0.92),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "스마트폰", "스마트폰"), 0.92),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "dram", "DRAM"), 0.92),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "nand flash", "NAND Flash"), 0.92),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "oled 패널", "OLED 패널"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "디지털 콕핏", "디지털 콕핏"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "카오디오", "카오디오"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "포터블 스피커", "포터블 스피커"), 0.85),
        ],
    },

    # ── 모바일: Galaxy 제품/기술 ───────────────────────────────
    "d78f74f49f34a9a0": {  # Galaxy Z 폴드6/플립6, Galaxy S24, Galaxy AI, 태블릿/스마트워치/스마트링/무선이어폰, S Pen
        "entities": [
            (P, "galaxy z 폴드6", "Galaxy Z 폴드6"),
            (P, "galaxy z 플립6", "Galaxy Z 플립6"),
            (P, "galaxy s24", "Galaxy S24"),
            (T, "galaxy ai", "Galaxy AI"),
            (P, "태블릿", "태블릿"),
            (P, "스마트워치", "스마트워치"),
            (P, "스마트링", "스마트링"),
            (P, "무선이어폰", "무선이어폰"),
            (T, "s pen", "S Pen"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy z 폴드6", "Galaxy Z 폴드6"), 0.93),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy z 플립6", "Galaxy Z 플립6"), 0.93),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy s24", "Galaxy S24"), 0.93),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "galaxy ai", "Galaxy AI"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "태블릿", "태블릿"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "스마트워치", "스마트워치"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "스마트링", "스마트링"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "무선이어폰", "무선이어폰"), 0.88),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "s pen", "S Pen"), 0.82),
        ],
    },

    # ── DS 반도체: 제품/기술 ───────────────────────────────────
    "51ea9a0f0ba0a382": {  # 메모리(RAM/ROM), System LSI(SOC), 모바일 AP, 이미지센서, Foundry
        "entities": [
            (P, "system lsi", "System LSI"),
            (P, "이미지센서", "이미지 센서"),
            (T, "foundry", "Foundry"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "system lsi", "System LSI"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "모바일ap", "모바일AP"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "이미지센서", "이미지 센서"), 0.88),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "foundry", "Foundry"), 0.85),
        ],
    },

    # ── SDC 디스플레이 기술 ────────────────────────────────────
    "52bb015ef40ea3e4": {  # OLED, QD-OLED, Flexible/Rigid OLED
        "entities": [
            (T, "oled", "OLED"),
            (T, "qd-oled", "QD-OLED"),
            (T, "flexible oled", "Flexible OLED"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "oled", "OLED"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "qd-oled", "QD-OLED"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "flexible oled", "Flexible OLED"), 0.82),
        ],
    },

    # ── Harman: 멀티브랜드 오디오 ──────────────────────────────
    "d5dcc838a63debf7": {  # Harman SDV 대응, 멀티브랜드 오디오 전략
        "entities": [
            (T, "sdv", "SDV(Software Defined Vehicle)"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "디지털 콕핏", "디지털 콕핏"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "카오디오", "카오디오"), 0.82),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "sdv", "SDV(Software Defined Vehicle)"), 0.8),
        ],
    },

    # ── 원재료/매입처 (SUPPLIES_TO: 공급자 → 삼성) ─────────────
    "22c61cab74399281": {  # 주요 원재료 narrative: Qualcomm/삼성전기(모바일AP·Camera), CSOT(패널), 솔브레인/SK실트론, 비에이치/Apple, NVIDIA/WNC
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "Qualcomm"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "삼성전기"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "CSOT"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "솔브레인"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "SK실트론"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "비에이치"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "Apple"), ("org", SAMSUNG), 0.82),
            E("SUPPLIES_TO", ("org", "NVIDIA"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "WNC"), ("org", SAMSUNG), 0.8),
        ],
    },
    "b9decb0c79905725": {  # 주요 매입처 표: Qualcomm/MediaTek, CSOT/SDP, 삼성전기/파트론, 솔브레인/동우화인켐, SK실트론/SILTRONIC, 비에이치/씨유테크, Apple/LENS, NVIDIA/Intel, WNC
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "Qualcomm"), ("org", SAMSUNG), 0.9),
            E("SUPPLIES_TO", ("org", "MediaTek"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "CSOT"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "SDP"), ("org", SAMSUNG), 0.82),
            E("SUPPLIES_TO", ("org", "삼성전기"), ("org", SAMSUNG), 0.9),
            E("SUPPLIES_TO", ("org", "파트론"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "솔브레인"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "동우화인켐"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "SK실트론"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "SILTRONIC"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "비에이치"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "씨유테크"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "Apple"), ("org", SAMSUNG), 0.82),
            E("SUPPLIES_TO", ("org", "LENS"), ("org", SAMSUNG), 0.82),
            E("SUPPLIES_TO", ("org", "NVIDIA"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "Intel"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "WNC"), ("org", SAMSUNG), 0.8),
        ],
    },

    # ── 특허 라이선스 (RELATED_PARTY) ──────────────────────────
    "b83a244797877509": {  # Google, GlobalFoundries, Ericsson, Qualcomm, Huawei, Nokia 특허/공정 라이선스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Google"), 0.85, "특허라이선스"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "GlobalFoundries"), 0.82, "공정기술라이선스"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Ericsson"), 0.82, "특허라이선스"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Qualcomm"), 0.82, "특허라이선스"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Huawei"), 0.82, "특허라이선스"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Nokia"), 0.82, "특허라이선스"),
        ],
    },

    # ── 옵션/주주간계약 (RELATED_PARTY) ────────────────────────
    "8f15a05a4fb7956d": {  # 레인보우로보틱스 콜옵션, 삼성디스플레이-Corning 풋옵션, 삼성디스플레이-TCL/CSOT 풋옵션
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "레인보우로보틱스"), 0.85, "지분보유(콜옵션)"),
            E("RELATED_PARTY", ("org", "삼성디스플레이"), ("org", "Corning"), 0.82, "지분보유(풋옵션)"),
            E("RELATED_PARTY", ("org", "삼성디스플레이"), ("org", "TCL"), 0.8, "주주간계약(풋옵션)"),
            E("RELATED_PARTY", ("org", "삼성디스플레이"), ("org", "CSOT"), 0.8, "지분보유(풋옵션)"),
        ],
    },
    "9a1c346cf15a7b86": {  # (이어지는 청크) 풋옵션 한영회계법인 평가 — 삼성디스플레이-CSOT 풋옵션
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성디스플레이"), ("org", "CSOT"), 0.78, "지분보유(풋옵션)"),
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
            print(f"  [warn] {cid} 대상 rcept 에 없음 — 스킵")
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
    print("=== 삼성전자 2024 3분기 비정형 추출 결과 ===")
    print(f"  이번 실행 처리 청크: {processed}  (기처리 스킵 {skipped})")
    print(f"  원장 누적 처리 청크: {total_done} / {len(rows)}")
    print(f"  엔티티(Product/Tech) hasObject: {n_ent_total}")
    print(f"  엣지 총: {n_edge_total}  타입별: {edge_by_type}")
    print(f"  provenance 행: {n_prov_total}")


if __name__ == "__main__":
    run()
