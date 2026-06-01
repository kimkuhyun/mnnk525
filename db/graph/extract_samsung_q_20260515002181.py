"""비정형 관계 추출 적재 — 삼성전자 2026년 1분기 분기보고서 (rcept 20260515002181, 220청크).

EXTRACTIONS = Claude(에이전트)가 대상 rcept 의 청크 본문을 하나씩 읽고 본문 근거로
판단한 엔티티·엣지. 적재는 extract_helpers 의 멱등 헬퍼로 수행.
원장은 rcept 전용 ledger/20260515002181.jsonl 에만 기록. 정형 표 제외, 본문 근거 비정형만.

실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_samsung_q_20260515002181.py
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

RCEPT = "20260515002181"
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
    "be8e9ecae6a5c5de": {  # 회사 개요: DX/DS/SDC/Harman 제품군
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
    "dc59a8240a8ca3ff": {  # 부문별 주요제품 표
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
    "40b93919fa82e013": {  # 주요제품 매출: 완제품 + 반도체 + OLED패널 + Harman 디지털콕핏/카오디오/포터블스피커
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "디지털 콕핏", "디지털 콕핏"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "카오디오", "카오디오"), 0.86),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "포터블 스피커", "포터블 스피커"), 0.86),
        ],
    },
    "6af98dbfbc9626c4": {  # Galaxy S26 시리즈, S26 Ultra, Galaxy AI, 프라이버시 디스플레이, 태블릿/스마트워치/스마트링/무선이어폰, Samsung Wallet/Health
        "entities": [
            (P, "galaxy s26", "Galaxy S26"),
            (P, "galaxy s26 ultra", "Galaxy S26 Ultra"),
            (T, "galaxy ai", "Galaxy AI"),
            (T, "프라이버시 디스플레이", "프라이버시 디스플레이(Privacy Display)"),
            (P, "태블릿", "태블릿"), (P, "스마트워치", "스마트워치"),
            (P, "스마트링", "스마트링"), (P, "무선이어폰", "무선이어폰"),
            (T, "s pen", "S Pen"),
            (P, "samsung wallet", "Samsung Wallet"),
            (P, "samsung health", "Samsung Health"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy s26", "Galaxy S26"), 0.93),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy s26 ultra", "Galaxy S26 Ultra"), 0.92),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "galaxy ai", "Galaxy AI"), 0.9),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "프라이버시 디스플레이", "프라이버시 디스플레이(Privacy Display)"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "태블릿", "태블릿"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "스마트워치", "스마트워치"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "스마트링", "스마트링"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "무선이어폰", "무선이어폰"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "samsung wallet", "Samsung Wallet"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "samsung health", "Samsung Health"), 0.85),
        ],
    },
    "2aa77c7b07f78526": {  # 연구개발 표: Galaxy S26, Galaxy Book6, Micro RGB LED TV, Neo Mini LED TV, OLED TV
        "entities": [
            (P, "galaxy s26", "Galaxy S26"),
            (P, "galaxy 북", "Galaxy 북"),
            (P, "micro rgb led tv", "Micro RGB LED TV"),
            (P, "mini led tv", "Mini LED TV"),
            (P, "oled tv", "OLED TV"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy s26", "Galaxy S26"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy 북", "Galaxy 북"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "micro rgb led tv", "Micro RGB LED TV"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "mini led tv", "Mini LED TV"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "oled tv", "OLED TV"), 0.88),
        ],
    },
    "934c61302734ed20": {  # AI TV: QLED, Micro RGB, Mini LED, OLED, Vision AI Companion
        "entities": [
            (P, "qled", "QLED"),
            (T, "vision ai companion", "Vision AI Companion"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "qled", "QLED"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "micro rgb led tv", "Micro RGB LED TV"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "mini led tv", "Mini LED TV"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "oled tv", "OLED TV"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "vision ai companion", "Vision AI Companion"), 0.85),
        ],
    },
    "07649b5af33e6159": {  # Micro RGB/OLED/Mini LED, 더 프레임, 태블릿/웨어러블
        "entities": [
            (P, "더 프레임", "더 프레임(The Frame)"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "더 프레임", "더 프레임(The Frame)"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "micro rgb led tv", "Micro RGB LED TV"), 0.82),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "oled tv", "OLED TV"), 0.82),
        ],
    },
    "19858895a9231864": {  # 사운드바 QS90H, WiFi 스피커 뮤직스튜디오, 더 프레임 프로, 프리스타일 플러스
        "entities": [
            (P, "사운드바", "사운드바"),
            (P, "wifi 스피커", "WiFi 스피커"),
            (P, "프로젝터", "프로젝터"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "사운드바", "사운드바"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "wifi 스피커", "WiFi 스피커"), 0.82),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "프로젝터", "프로젝터"), 0.82),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "더 프레임", "더 프레임(The Frame)"), 0.85),
        ],
    },
    "59349dcf313cc49f": {  # PCIe Gen6 서버 SSD, System LSI, 모바일 2나노 SOC→Galaxy S26, 2억화소 이미지센서, DDI, Power
        "entities": [
            (P, "pcie gen6 ssd", "PCIe Gen6 SSD"),
            (P, "이미지센서", "이미지 센서"),
            (P, "ddi", "DDI(디스플레이 구동 IC)"),
            (T, "2나노 공정", "2나노 공정"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "pcie gen6 ssd", "PCIe Gen6 SSD"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "이미지센서", "이미지 센서"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "ddi", "DDI(디스플레이 구동 IC)"), 0.82),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "2나노 공정", "2나노 공정"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy s26", "Galaxy S26"), 0.82),
        ],
    },
    "b18739978e3ec8d4": {  # 반도체: 메모리 RAM/ROM, System LSI(CPU), 모바일AP/이미지센서, Foundry
        "entities": [
            (P, "system lsi", "System LSI"),
            (T, "foundry", "Foundry"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "system lsi", "System LSI"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "모바일ap", "모바일AP"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "이미지센서", "이미지 센서"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "foundry", "Foundry"), 0.85),
        ],
    },
    "215fb99b8c0bb19c": {  # Power 서버향, Foundry 4나노 HBM Base-die, 2나노 2세대, OLED/QD-OLED/TFT-LCD
        "entities": [
            (P, "hbm base-die", "HBM Base-Die"),
            (T, "qd-oled", "QD-OLED"),
            (T, "oled", "OLED"),
            (T, "tft-lcd", "TFT-LCD"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "hbm base-die", "HBM Base-Die"), 0.82),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "2나노 공정", "2나노 공정"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "oled", "OLED"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "qd-oled", "QD-OLED"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "tft-lcd", "TFT-LCD"), 0.82),
        ],
    },

    # ── II. 원재료/공급 (SUPPLIES_TO) ──────────────────────────
    "270048ee1f784f45": {  # 원재료: 모바일AP/모바일메모리/Camera ← Qualcomm/Micron/삼성전기, 패널 ← CSOT, Chemical/Wafer ← 솔브레인/SILTRONIC, FPCA/Cover Glass ← 비에이치/Apple, SOC/통신모듈 ← NVIDIA/WNC
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "Qualcomm"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "Micron"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "삼성전기"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "CSOT"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "솔브레인"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "SILTRONIC"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "비에이치"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "Apple"), ("org", SAMSUNG), 0.82),
            E("SUPPLIES_TO", ("org", "NVIDIA"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "WNC"), ("org", SAMSUNG), 0.8),
        ],
    },
    "3597e264e6c131e5": {  # 주요 매입처 표: Qualcomm/MediaTek, CSOT/AUO, Micron(모바일메모리), 삼성전기/파트론, 솔브레인/동우화인켐, SILTRONIC/SK실트론
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "Qualcomm"), ("org", SAMSUNG), 0.9),
            E("SUPPLIES_TO", ("org", "MediaTek"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "CSOT"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "AUO"), ("org", SAMSUNG), 0.82),
            E("SUPPLIES_TO", ("org", "Micron"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "삼성전기"), ("org", SAMSUNG), 0.9),
            E("SUPPLIES_TO", ("org", "파트론"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "솔브레인"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "동우화인켐"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "SILTRONIC"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "SK실트론"), ("org", SAMSUNG), 0.88),
        ],
    },

    # ── Foundry 수주 (SUPPLIES_TO: 삼성 → Tesla) ───────────────
    "bb9a5ec23036e545": {  # DS Foundry — Tesla 반도체 위탁생산 수주(16,544백만달러)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "Tesla"), 0.9),
        ],
    },
    "de487fda027c3fa7": {  # XI 수주: Tesla 반도체 위탁생산 공급계약
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "Tesla"), 0.9),
        ],
    },

    # ── 특허 라이선스 (RELATED_PARTY) ──────────────────────────
    "2a2286d83555464a": {  # 특허 라이선스: Google, Nokia, Qualcomm, Huawei
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Google"), 0.85, "특허라이선스"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Nokia"), 0.85, "특허라이선스"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Qualcomm"), 0.85, "특허라이선스"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Huawei"), 0.85, "특허라이선스"),
        ],
    },
    "4e71cd0fb8de391d": {  # 경영상 주요계약 표: Google/Ericsson/Qualcomm/Huawei 상호특허
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Google"), 0.88, "상호특허사용계약"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Ericsson"), 0.85, "상호특허사용계약"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Qualcomm"), 0.85, "상호특허사용계약"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Huawei"), 0.85, "상호특허사용계약"),
        ],
    },

    # ── Harman 인수 / 옵션 (RELATED_PARTY) ─────────────────────
    "30816a21f7894725": {  # Harman, Sound United(B&W/Denon/Marantz) 2025 3분기 인수
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "Harman"), ("org", "Sound United"), 0.88, "인수(2025)"),
        ],
    },
    "d38698f4f5e574ea": {  # 레인보우로보틱스 콜옵션 행사완료, 삼성디스플레이-Corning/TCL/CSOT 풋옵션
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "레인보우로보틱스"), 0.88, "지분인수(콜옵션행사)"),
            E("RELATED_PARTY", ("org", "삼성디스플레이"), ("org", "Corning"), 0.8, "지분보유(풋옵션)"),
            E("RELATED_PARTY", ("org", "삼성디스플레이"), ("org", "TCL"), 0.78, "지분매각권(풋옵션)"),
            E("RELATED_PARTY", ("org", "삼성디스플레이"), ("org", "CSOT"), 0.78, "지분보유(풋옵션)"),
        ],
    },

    # ── 회사 개요 종속기업 (RELATED_PARTY 종속관계) ────────────
    "002761c76f9c2530": {  # 해외 종속: SEA, SII, SSI, SAS, SEDA, Harman
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Electronics America"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Semiconductor"), 0.85, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Harman"), 0.85, "종속기업"),
        ],
    },

    # ── X. 대주주 등과의 거래 (RELATED_PARTY) ──────────────────
    "ea57fc2e9e272759": {  # 채무보증 SEA, 자산양수도 SCS, 영업거래 SSI
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Electronics America"), 0.85, "계열회사(채무보증)"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung China Semiconductor"), 0.85, "계열회사(자산양수도)"),
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
    print(f"=== 삼성전자 2026 1분기 ({RCEPT}) 비정형 추출 결과 ===")
    print(f"  이번 실행 처리 청크: {processed}  (기처리 스킵 {skipped})")
    print(f"  원장 누적 처리 청크: {total_done} / {len(rows)}")
    print(f"  엔티티 hasObject: {n_ent_total}")
    print(f"  엣지 총: {n_edge_total}  타입별: {edge_by_type}")
    print(f"  provenance 행: {n_prov_total}")


if __name__ == "__main__":
    run()
