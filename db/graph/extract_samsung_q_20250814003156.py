"""비정형 관계 추출 적재 — 삼성전자 2025년 반기보고서 (rcept 20250814003156, 274청크).

EXTRACTIONS = Claude(에이전트)가 대상 rcept 의 청크 본문을 하나씩 읽고 본문 근거로
판단한 엔티티·엣지. 적재는 extract_helpers 의 멱등 헬퍼로 수행.
원장은 rcept 전용 ledger/20250814003156.jsonl 에만 기록. 정형 표 제외, 본문 근거 비정형만.

실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_samsung_q_20250814003156.py
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

RCEPT = "20250814003156"
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

    # ── II. 회사/제품 개요 (PRODUCES) ──────────────────────────
    "7219a0a6ed5718cf": {  # 회사 개요: DX(TV/모니터/냉장고/세탁기/에어컨/스마트폰/네트워크시스템/PC), DS(DRAM/NAND/모바일AP), SDC(OLED패널), Harman(디지털콕핏/카오디오/포터블스피커)
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
    "2fe156a644589ae9": {  # 부문별 주요제품 표
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "tv", "TV"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "dram", "DRAM"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "nand flash", "NAND Flash"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "모바일ap", "모바일AP"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "oled 패널", "OLED 패널"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "디지털 콕핏", "디지털 콕핏"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "카오디오", "카오디오"), 0.86),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "포터블 스피커", "포터블 스피커"), 0.86),
        ],
    },
    "3a5d6568a705b44b": {  # 주요제품 매출: 완제품 + DRAM/NAND/모바일AP + OLED패널 + Harman 디지털콕핏/카오디오/포터블사운드바
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "디지털 콕핏", "디지털 콕핏"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "카오디오", "카오디오"), 0.86),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "포터블 스피커", "포터블 스피커"), 0.86),
        ],
    },
    "08978d7cbbdb5e04": {  # Galaxy Z 폴드/플립, Galaxy S25, Galaxy AI, One UI 7, ProVisual Engine
        "entities": [
            (P, "galaxy z 플립", "Galaxy Z 플립"),
            (P, "galaxy z 폴드", "Galaxy Z 폴드"),
            (P, "galaxy s25", "Galaxy S25"),
            (T, "galaxy ai", "Galaxy AI"),
            (T, "one ui 7", "One UI 7"),
            (T, "프로비주얼 엔진", "프로비주얼 엔진(ProVisual Engine)"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy z 플립", "Galaxy Z 플립"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy z 폴드", "Galaxy Z 폴드"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy s25", "Galaxy S25"), 0.93),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "galaxy ai", "Galaxy AI"), 0.9),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "one ui 7", "One UI 7"), 0.88),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "프로비주얼 엔진", "프로비주얼 엔진(ProVisual Engine)"), 0.85),
        ],
    },
    "859e1a118d79db2c": {  # Samsung Health, Galaxy S25 재활용소재
        "entities": [(P, "samsung health", "Samsung Health")],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "samsung health", "Samsung Health"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy s25", "Galaxy S25"), 0.85),
        ],
    },
    "3304192c25d37097": {  # 연구개발 표: Galaxy S25/A/북, Neo QLED 8K/4K, OLED TV
        "entities": [
            (P, "neo qled", "Neo QLED"),
            (P, "galaxy 북", "Galaxy 북"),
            (P, "oled tv", "OLED TV"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy s25", "Galaxy S25"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy 북", "Galaxy 북"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "neo qled", "Neo QLED"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "oled tv", "OLED TV"), 0.88),
        ],
    },
    "c68a1c6c6810b0c7": {  # AI TV: Neo QLED, OLED, QLED, 더 프레임, 더 프리미어 5
        "entities": [
            (P, "qled", "QLED"),
            (P, "더 프레임", "더 프레임(The Frame)"),
            (P, "프로젝터", "프로젝터"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "neo qled", "Neo QLED"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "oled 패널", "OLED 패널"), 0.82),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "qled", "QLED"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "더 프레임", "더 프레임(The Frame)"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "프로젝터", "프로젝터"), 0.82),
        ],
    },
    "efe202490fa90671": {  # Q시리즈 사운드바, 컨버터블 사운드바, 더 프레임
        "entities": [(P, "사운드바", "사운드바")],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "사운드바", "사운드바"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "더 프레임", "더 프레임(The Frame)"), 0.85),
        ],
    },
    "28c50a6993065669": {  # TV 기술: 마이크로 LED, AI 화질 기술
        "entities": [
            (T, "마이크로 led", "마이크로 LED"),
            (T, "ai 화질 기술", "AI 화질 기술"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "마이크로 led", "마이크로 LED"), 0.82),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "ai 화질 기술", "AI 화질 기술"), 0.8),
        ],
    },
    "cb69570ec04e0bdc": {  # TV: 마이크로 LED, Neo QLED, OLED 기술
        "entities": [],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "마이크로 led", "마이크로 LED"), 0.8),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "neo qled", "Neo QLED"), 0.82),
        ],
    },
    "4f3640a920c7f6bc": {  # System LSI 모바일AP/이미지센서, Foundry 위탁생산
        "entities": [
            (P, "이미지센서", "이미지 센서"),
            (T, "foundry", "Foundry"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "모바일ap", "모바일AP"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "이미지센서", "이미지 센서"), 0.9),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "foundry", "Foundry"), 0.85),
        ],
    },
    "6284048e1a2ddcf1": {  # 메모리: HBM3E, 고용량 DDR5, 서버향 LPDDR5x, NAND V8
        "entities": [
            (P, "hbm3e", "HBM3E"),
            (P, "ddr5", "DDR5"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "hbm3e", "HBM3E"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "ddr5", "DDR5"), 0.82),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "dram", "DRAM"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "nand flash", "NAND Flash"), 0.85),
        ],
    },
    "c8ce2b2242439dc1": {  # Power/Security, Foundry 2나노 GAA, 17나노 CIS/DDI, OLED/QD-OLED/TFT-LCD
        "entities": [
            (T, "2나노 공정", "2나노 공정"),
            (P, "ddi", "DDI(디스플레이 구동 IC)"),
            (T, "qd-oled", "QD-OLED"),
            (T, "oled", "OLED"),
            (T, "tft-lcd", "TFT-LCD"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "2나노 공정", "2나노 공정"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "이미지센서", "이미지 센서"), 0.82),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "ddi", "DDI(디스플레이 구동 IC)"), 0.82),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "oled", "OLED"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "qd-oled", "QD-OLED"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "tft-lcd", "TFT-LCD"), 0.82),
        ],
    },

    # ── II. 원재료/공급 (SUPPLIES_TO) ──────────────────────────
    "48b1fad89207c2c4": {  # 원재료: 모바일AP/Camera ← Qualcomm/삼성전기, 패널 ← AUO, Chemical/Wafer ← 솔브레인/SILTRONIC, FPCA/Cover Glass ← 비에이치/Apple, SOC/통신모듈 ← NVIDIA/WNC
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "Qualcomm"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "삼성전기"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "AUO"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "솔브레인"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "SILTRONIC"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "비에이치"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "Apple"), ("org", SAMSUNG), 0.82),
            E("SUPPLIES_TO", ("org", "NVIDIA"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "WNC"), ("org", SAMSUNG), 0.8),
        ],
    },
    "f9d5f48adbf56d23": {  # 주요 매입처 표: Qualcomm/MediaTek, AUO/CSOT, 삼성전기/SUNNY OPTICAL, 솔브레인/동우화인켐, SILTRONIC/SK실트론, 비에이치/유니온, Apple/LENS
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "Qualcomm"), ("org", SAMSUNG), 0.9),
            E("SUPPLIES_TO", ("org", "MediaTek"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "AUO"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "CSOT"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "삼성전기"), ("org", SAMSUNG), 0.9),
            E("SUPPLIES_TO", ("org", "SUNNY OPTICAL"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "솔브레인"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "동우화인켐"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "SILTRONIC"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "SK실트론"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "비에이치"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "Apple"), ("org", SAMSUNG), 0.82),
            E("SUPPLIES_TO", ("org", "LENS"), ("org", SAMSUNG), 0.82),
        ],
    },

    # ── 특허 라이선스 (RELATED_PARTY) ──────────────────────────
    "21706a11f3048f46": {  # 특허 라이선스: Google, Nokia, Qualcomm, Huawei
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Google"), 0.85, "특허라이선스"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Nokia"), 0.85, "특허라이선스"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Qualcomm"), 0.85, "특허라이선스"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Huawei"), 0.85, "특허라이선스"),
        ],
    },
    "c4609bcceedcbf89": {  # 경영상 주요계약 표: Google 상호특허/EMADA, Ericsson, Qualcomm, Huawei, Nokia
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Google"), 0.88, "상호특허사용계약"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Ericsson"), 0.85, "상호특허사용계약"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Qualcomm"), 0.85, "상호특허사용계약"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Huawei"), 0.85, "상호특허사용계약"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Nokia"), 0.85, "상호특허사용계약"),
        ],
    },

    # ── Foundry 수주 (SUPPLIES_TO: 삼성→Tesla) ─────────────────
    # (반기보고서에는 Tesla 수주 미기재 → 생략)

    # ── 옵션·인수 (RELATED_PARTY) ──────────────────────────────
    "344efb99271f9bcb": {  # 레인보우로보틱스 콜옵션 행사완료, 삼성디스플레이-Corning/TCL/CSOT 풋옵션
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "레인보우로보틱스"), 0.88, "지분인수(콜옵션행사)"),
            E("RELATED_PARTY", ("org", "삼성디스플레이"), ("org", "Corning"), 0.8, "지분보유(풋옵션)"),
            E("RELATED_PARTY", ("org", "삼성디스플레이"), ("org", "TCL"), 0.78, "지분매각권(풋옵션)"),
            E("RELATED_PARTY", ("org", "삼성디스플레이"), ("org", "CSOT"), 0.78, "지분보유(풋옵션)"),
        ],
    },
    "16973f8b2960b810": {  # Harman, Roon Labs LLC 2023.4Q 인수
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "Harman"), ("org", "Roon Labs"), 0.85, "인수(2023)"),
        ],
    },

    # ── 회사 개요 종속기업 (RELATED_PARTY 종속관계) ────────────
    "7219a0a6ed5718cf_dup": {},  # placeholder
    "b138729b1ac822d1": {  # 해외 종속: SEA, Harman, SEUK/SEG 등
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Electronics America"), 0.85, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Harman"), 0.85, "종속기업"),
        ],
    },

    # ── IX. 계열회사: 삼성그룹 계열관계 (RELATED_PARTY) ─────────
    "136175f839472679": {  # 출자현황 표: 삼성물산/삼성바이오로직스/삼성생명/삼성SDI/삼성에스디에스/삼성전기/삼성전자 → 삼성글로벌리서치 등 출자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성물산"), 0.85, "계열회사"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성바이오로직스"), 0.85, "계열회사"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성SDI"), 0.85, "계열회사"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성에스디에스"), 0.85, "계열회사"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성전기"), 0.85, "계열회사"),
        ],
    },

    # ── X. 대주주 등과의 거래 (RELATED_PARTY) ──────────────────
    "f67c3047e7685f83": {  # 채무보증 SEA, 자산양수도 SCS, 영업거래 SSI, Cash Pooling 모법인 SEA/SEEH/SAPL/SCIC
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Electronics America"), 0.85, "계열회사(채무보증)"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung China Semiconductor"), 0.85, "계열회사(자산양수도)"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Semiconductor"), 0.85, "계열회사(영업거래)"),
        ],
    },
    "e9c82d21b79a11dc": {  # SSI 영업거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Semiconductor"), 0.85, "계열회사(영업거래)"),
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
    print(f"=== 삼성전자 2025 반기 ({RCEPT}) 비정형 추출 결과 ===")
    print(f"  이번 실행 처리 청크: {processed}  (기처리 스킵 {skipped})")
    print(f"  원장 누적 처리 청크: {total_done} / {len(rows)}")
    print(f"  엔티티 hasObject: {n_ent_total}")
    print(f"  엣지 총: {n_edge_total}  타입별: {edge_by_type}")
    print(f"  provenance 행: {n_prov_total}")


if __name__ == "__main__":
    run()
