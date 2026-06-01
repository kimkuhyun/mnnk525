"""비정형 관계 추출 적재 — 삼성전자 2024 1분기보고서 (rcept 20240516001421, 200청크 전체).

EXTRACTIONS = Claude(에이전트)가 대상 rcept 청크 본문을 읽고 본문 근거로 판단한
엔티티·엣지. 적재는 extract_helpers 멱등 헬퍼로 수행. 원장은 rcept 전용
ledger/20240516001421.jsonl 에만(공유 원장 금지). 시작 시 원장 확인해 스킵하고
대상 청크 전부 mark_processed(엣지 0개여도) → 누락 0.

실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_samsung2024q1.py
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

RCEPT = "20240516001421"
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


# ── Claude 추출 결과 (청크별, 본문 근거 있는 것만) ──────────────
EXTRACTIONS: dict[str, dict] = {

    # ── 부문 매출표: 주요 제품 (PRODUCES) ──────────────────────
    "2edf1bd0cc8b47e0": {  # DX: TV/모니터/냉장고/세탁기/에어컨/스마트폰/네트워크시스템/컴퓨터, DS: DRAM/NAND/모바일AP, SDC: OLED패널, Harman: 디지털콕핏/카오디오/포터블스피커
        "entities": [
            (P, "tv", "TV"), (P, "모니터", "모니터"), (P, "냉장고", "냉장고"),
            (P, "세탁기", "세탁기"), (P, "에어컨", "에어컨"), (P, "스마트폰", "스마트폰"),
            (P, "네트워크시스템", "네트워크시스템"), (P, "컴퓨터", "컴퓨터"),
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
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "컴퓨터", "컴퓨터"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "dram", "DRAM"), 0.97),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "nand flash", "NAND Flash"), 0.97),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "모바일ap", "모바일AP"), 0.95),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "oled 패널", "OLED 패널"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "디지털 콕핏", "디지털 콕핏"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "카오디오", "카오디오"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "포터블 스피커", "포터블 스피커"), 0.88),
        ],
    },
    "3bc3b15656c215cd": {  # 매출유형별 매출 표 (동일 제품군 재확인)
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "tv", "TV"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "스마트폰", "스마트폰"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "dram", "DRAM"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "nand flash", "NAND Flash"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "oled 패널", "OLED 패널"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "디지털 콕핏", "디지털 콕핏"), 0.88),
        ],
    },
    "5c0ed05f3aacdedf": {  # 주요 제품 매출 narrative: 완제품 + 반도체 + OLED패널 + Harman, 매출처 Apple/Deutsche Telekom/Verizon
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

    # ── 모바일: Galaxy 제품/기술 (PRODUCES / USES_TECH) ─────────
    "53200cbe22d9534e": {  # 갤럭시 Z 폴드/Z 플립, Galaxy S24, Galaxy AI, 태블릿/스마트워치/무선이어폰(Galaxy Ecosystem), S Pen
        "entities": [
            (P, "갤럭시 z 플립", "갤럭시 Z 플립"),
            (P, "갤럭시 z 폴드", "갤럭시 Z 폴드"),
            (P, "galaxy s24", "Galaxy S24"),
            (T, "galaxy ai", "Galaxy AI"),
            (P, "태블릿", "태블릿"),
            (P, "스마트워치", "스마트워치"),
            (P, "무선이어폰", "무선이어폰"),
            (T, "s pen", "S Pen"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "갤럭시 z 플립", "갤럭시 Z 플립"), 0.92),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "갤럭시 z 폴드", "갤럭시 Z 폴드"), 0.92),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy s24", "Galaxy S24"), 0.93),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "galaxy ai", "Galaxy AI"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "태블릿", "태블릿"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "스마트워치", "스마트워치"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "무선이어폰", "무선이어폰"), 0.88),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "s pen", "S Pen"), 0.82),
        ],
    },
    "1de0c6076cad8131": {  # Samsung Wallet, Samsung Health, Bixby, SmartThings 서비스
        "entities": [
            (P, "samsung wallet", "Samsung Wallet"),
            (P, "samsung health", "Samsung Health"),
            (T, "smartthings", "SmartThings"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "samsung wallet", "Samsung Wallet"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "samsung health", "Samsung Health"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "smartthings", "SmartThings"), 0.8),
        ],
    },

    # ── TV/SDC 기술 (USES_TECH) ───────────────────────────────
    "42668c6b5a1d0dcf": {  # TV: 마이크로 LED, Neo QLED, OLED, AI 화질 기술, AI 업스케일링
        "entities": [
            (P, "neo qled", "Neo QLED"),
            (T, "마이크로 led", "마이크로 LED"),
            (T, "ai 화질 기술", "AI 화질 기술"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "마이크로 led", "마이크로 LED"), 0.82),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "ai 화질 기술", "AI 화질 기술"), 0.8),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "neo qled", "Neo QLED"), 0.85),
        ],
    },
    "05b7975d0bf5444e": {  # Neo QLED, OLED, 사운드바, 마이크로 LED 프리미엄 라인업
        "entities": [
            (P, "사운드바", "사운드바"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "neo qled", "Neo QLED"), 0.88),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "마이크로 led", "마이크로 LED"), 0.8),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "사운드바", "사운드바"), 0.85),
        ],
    },
    "a25ae22ec81e8907": {  # SDC: OLED, QD-OLED, TFT-LCD
        "entities": [
            (T, "oled", "OLED"),
            (T, "qd-oled", "QD-OLED"),
            (T, "tft-lcd", "TFT-LCD"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "oled", "OLED"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "qd-oled", "QD-OLED"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "tft-lcd", "TFT-LCD"), 0.82),
        ],
    },

    # ── DS 반도체: 제품/기술 (PRODUCES / USES_TECH) ────────────
    "cc2e6064697b1fa5": {  # System LSI, 모바일 AP(SOC), 이미지센서, 메모리(RAM/ROM)
        "entities": [
            (P, "system lsi", "System LSI"),
            (P, "이미지센서", "이미지 센서"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "system lsi", "System LSI"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "모바일ap", "모바일AP"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "이미지센서", "이미지 센서"), 0.88),
        ],
    },
    "065f3c4fa206f80d": {  # 모바일용 AP, 이미지센서, Foundry(위탁생산)
        "entities": [
            (T, "foundry", "Foundry"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "모바일ap", "모바일AP"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "이미지센서", "이미지 센서"), 0.88),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "foundry", "Foundry"), 0.85),
        ],
    },
    "c968d06ba386ea98": {  # 이미지센서(1억화소), mDDI/pDDI, Power, Foundry 3나노/2나노/1.4나노
        "entities": [
            (P, "ddi", "DDI(디스플레이 구동 IC)"),
            (T, "2나노 공정", "2나노 공정"),
            (T, "3나노 공정", "3나노 공정"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "이미지센서", "이미지 센서"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "ddi", "DDI(디스플레이 구동 IC)"), 0.82),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "3나노 공정", "3나노 공정"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "2나노 공정", "2나노 공정"), 0.82),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "foundry", "Foundry"), 0.82),
        ],
    },

    # ── Harman: 전장/오디오 + Roon Labs 인수 (PRODUCES/USES_TECH/RELATED_PARTY) ──
    "36e06205c8aac8b8": {  # 디지털콕핏/카오디오/텔레매틱스, SDV, Roon Labs LLC 인수, TWS/포터블스피커/헤드폰
        "entities": [
            (P, "텔레매틱스", "텔레매틱스"),
            (T, "sdv", "SDV(Software Defined Vehicle)"),
            (P, "헤드폰", "헤드폰"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "디지털 콕핏", "디지털 콕핏"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "카오디오", "카오디오"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "텔레매틱스", "텔레매틱스"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "헤드폰", "헤드폰"), 0.82),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "sdv", "SDV(Software Defined Vehicle)"), 0.8),
            E("RELATED_PARTY", ("org", "Harman"), ("org", "Roon Labs"), 0.82, "인수(2023.4Q)"),
        ],
    },

    # ── 원재료/매입처 (SUPPLIES_TO: 공급자 → 삼성) ─────────────
    "6f6b0f04d1debb1f": {  # 주요 원재료 narrative: Qualcomm/삼성전기(모바일AP·Camera), CSOT(패널), 솔브레인/SK실트론(Chemical/Wafer), 비에이치/Apple(FPCA/Cover Glass), NVIDIA/WNC(SOC/통신모듈)
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
    "5a32287fb9730d13": {  # 주요 매입처 표: Qualcomm/MediaTek, CSOT/SDP, 삼성전기/파트론, 솔브레인/동우화인켐, SK실트론/SUMCO, 비에이치/영풍전자, Apple/Biel, NVIDIA/Intel, WNC
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
            E("SUPPLIES_TO", ("org", "SUMCO"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "비에이치"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "영풍전자"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "Apple"), ("org", SAMSUNG), 0.82),
            E("SUPPLIES_TO", ("org", "Biel"), ("org", SAMSUNG), 0.82),
            E("SUPPLIES_TO", ("org", "NVIDIA"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "Intel"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "WNC"), ("org", SAMSUNG), 0.8),
        ],
    },

    # ── 주요 매출처 (SUPPLIES_TO: 삼성 → 수요자) ───────────────
    "37a18d547d06213c": {  # 주요 매출처: Apple, Deutsche Telekom, Hong Kong Techtronics, Supreme Electronics, Verizon
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "Apple"), 0.85),
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "Deutsche Telekom"), 0.85),
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "Hong Kong Techtronics"), 0.82),
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "Supreme Electronics"), 0.82),
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "Verizon"), 0.85),
        ],
    },

    # ── 특허 라이선스 (RELATED_PARTY) ──────────────────────────
    "902abef146125416": {  # Google, GlobalFoundries, Ericsson, Qualcomm, Huawei, Nokia 특허/공정 라이선스
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
    "8bf9efba3801b792": {  # 레인보우로보틱스 콜옵션·주주간계약, 안진회계법인 평가
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "레인보우로보틱스"), 0.85, "지분보유(콜옵션)"),
        ],
    },

    # ── 대주주 거래: 자산양수도 / 채무보증 (RELATED_PARTY) ─────
    "ae48189971870991": {  # 자산매각/매입: SESS/SCS/SEVT/SII/SEV/삼성바이오로직스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성바이오로직스"), 0.85, "계열회사(자산양수도)"),
        ],
    },
    "d36edd4a29f690c7": {  # SEA 채무보증, SESS 자산매각
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Electronics America"), 0.85, "계열회사(채무보증)"),
        ],
    },
    "69f8f385d64424c4": {  # 채무보증 표: Harman International Industries 등 계열회사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Harman"), 0.82, "계열회사(채무보증)"),
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
    print("=== 삼성전자 2024 1분기 비정형 추출 결과 ===")
    print(f"  이번 실행 처리 청크: {processed}  (기처리 스킵 {skipped})")
    print(f"  원장 누적 처리 청크: {total_done} / {len(rows)}")
    print(f"  엔티티(Product/Tech) hasObject: {n_ent_total}")
    print(f"  엣지 총: {n_edge_total}  타입별: {edge_by_type}")
    print(f"  provenance 행: {n_prov_total}")


if __name__ == "__main__":
    run()
