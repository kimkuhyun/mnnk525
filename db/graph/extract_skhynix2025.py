"""B단계 비정형 추출 적재 — SK하이닉스 2025 사업보고서 전체 (rcept 20260317000635).

이 파일의 EXTRACTIONS = Claude(에이전트)가 rcept 20260317000635 의 chunk_index 전체
(약 780청크)를 읽고 본문 근거로 판단한 엔티티·엣지다. 결정론 코드가 아니라 언어이해 산출물.
적재는 extract_helpers 의 멱등 헬퍼로 수행. 근거 없는 추정 금지(환각 방어).

대상 청크 전부 mark_processed(엣지 0개여도) → 누락 0.
원장은 db/graph/ledger/20260317000635.jsonl 전용(공유 ledger 금지).

실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_skhynix2025.py
멱등: 재실행해도 MERGE/ON DUP 로 중복 적재 없음(원장만 append 누적).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extract_helpers as H  # noqa: E402
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

RCEPT = "20260317000635"
WHERE = f"WHERE rcept_no='{RCEPT}'"
SKH = "SK하이닉스"  # resolve_org → corp_code 00164779

# 전용 원장 (공유 extract_ledger.jsonl 금지)
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_DIR.mkdir(parents=True, exist_ok=True)
H.LEDGER_PATH = LEDGER_DIR / f"{RCEPT}.jsonl"

P = "Product"
T = "Technology"


def E(rel, frm, to, conf, relation_type=None):
    d = {"rel": rel, "from": frm, "to": to, "conf": conf}
    if relation_type:
        d["relation_type"] = relation_type
    return d


# ── Claude 추출 결과 (청크별) ──────────────────────────────
EXTRACTIONS: dict[str, dict] = {

    # ── II. 사업의 내용 : 제품 / 기술 (PRODUCES / USES_TECH) ─────────
    "a6535b5c57f898a8": {  # 주력제품: DRAM, NAND, Foundry 병행
        "entities": [
            (P, "dram", "DRAM"), (P, "nand flash", "NAND Flash"),
            (T, "foundry", "Foundry"),
        ],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "dram", "DRAM"), 0.97),
            E("PRODUCES", ("org", SKH), ("ent", P, "nand flash", "NAND Flash"), 0.97),
            E("PRODUCES", ("org", SKH), ("ent", T, "foundry", "Foundry"), 0.85),
        ],
    },
    "b0da2e3b082a7642": {  # 매출 품목표: DRAM, NAND Flash 등 (상표 SK하이닉스)
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "dram", "DRAM"), 0.95),
            E("PRODUCES", ("org", SKH), ("ent", P, "nand flash", "NAND Flash"), 0.95),
        ],
    },
    "826c0d5d4fa9e698": {  # 시스템반도체: CMOS 이미지센서(CIS) 생산 (2025.3 AI메모리로 전환)
        "entities": [
            (P, "cmos 이미지센서", "CMOS 이미지센서(CIS)"),
        ],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "cmos 이미지센서", "CMOS 이미지센서(CIS)"), 0.88),
        ],
    },
    "48df245374dfae00": {  # 연구개발실적(제76기): LPDDR5T, LPDDR5X, 12단 HBM3, HBM3E, 서버용 DDR5, 238단 4D NAND, Mobile UFS, eSSD, cSSD, GDDR7
        "entities": [
            (P, "lpddr5t", "LPDDR5T"), (P, "lpddr5x", "LPDDR5X"),
            (P, "hbm3", "HBM3"), (P, "hbm3e", "HBM3E"),
            (P, "ddr5", "DDR5"), (P, "238단 4d nand", "238단 4D NAND"),
            (P, "gddr7", "GDDR7"), (P, "essd", "eSSD"), (P, "cssd", "cSSD"),
            (P, "mobile ufs", "Mobile UFS"),
            (T, "tsv", "TSV(Through Silicon Via)"),
            (T, "mr-muf", "MR-MUF"), (T, "hkmg", "HKMG(High-K Metal Gate)"),
        ],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "lpddr5t", "LPDDR5T"), 0.92),
            E("PRODUCES", ("org", SKH), ("ent", P, "lpddr5x", "LPDDR5X"), 0.95),
            E("PRODUCES", ("org", SKH), ("ent", P, "hbm3", "HBM3"), 0.95),
            E("PRODUCES", ("org", SKH), ("ent", P, "hbm3e", "HBM3E"), 0.95),
            E("PRODUCES", ("org", SKH), ("ent", P, "ddr5", "DDR5"), 0.95),
            E("PRODUCES", ("org", SKH), ("ent", P, "238단 4d nand", "238단 4D NAND"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "gddr7", "GDDR7"), 0.92),
            E("PRODUCES", ("org", SKH), ("ent", P, "essd", "eSSD"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "cssd", "cSSD"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "mobile ufs", "Mobile UFS"), 0.9),
            E("USES_TECH", ("org", SKH), ("ent", T, "tsv", "TSV(Through Silicon Via)"), 0.9),
            E("USES_TECH", ("org", SKH), ("ent", T, "mr-muf", "MR-MUF"), 0.9),
            E("USES_TECH", ("org", SKH), ("ent", T, "hkmg", "HKMG(High-K Metal Gate)"), 0.9),
        ],
    },
    "cde5422aa82f662b": {  # 연구개발실적(제77기): 1cnm DDR5, GDDR7, 1bnm LPDDR5X, ZUFS 4.0, HBM3E, PCIe Gen5 SSD, 321단 4D NAND, CMM-DDR(CXL), eSSD
        "entities": [
            (P, "1cnm ddr5", "1cnm DDR5"), (P, "zufs", "ZUFS"),
            (P, "321단 4d nand", "321단 4D NAND"),
            (P, "cmm-ddr", "CMM-DDR"),
            (P, "pcie gen5 ssd", "PCIe Gen5 SSD"),
            (T, "cxl", "CXL"), (T, "qlc", "QLC"), (T, "pcie", "PCIe"),
            (T, "euv", "EUV"),
        ],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "1cnm ddr5", "1cnm DDR5"), 0.92),
            E("PRODUCES", ("org", SKH), ("ent", P, "gddr7", "GDDR7"), 0.92),
            E("PRODUCES", ("org", SKH), ("ent", P, "lpddr5x", "LPDDR5X"), 0.92),
            E("PRODUCES", ("org", SKH), ("ent", P, "zufs", "ZUFS"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "hbm3e", "HBM3E"), 0.93),
            E("PRODUCES", ("org", SKH), ("ent", P, "321단 4d nand", "321단 4D NAND"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "cmm-ddr", "CMM-DDR"), 0.88),
            E("PRODUCES", ("org", SKH), ("ent", P, "pcie gen5 ssd", "PCIe Gen5 SSD"), 0.9),
            E("USES_TECH", ("org", SKH), ("ent", T, "cxl", "CXL"), 0.85),
            E("USES_TECH", ("org", SKH), ("ent", T, "qlc", "QLC"), 0.85),
            E("USES_TECH", ("org", SKH), ("ent", T, "euv", "EUV"), 0.85),
            E("USES_TECH", ("org", SKH), ("ent", T, "mr-muf", "MR-MUF"), 0.88),
        ],
    },
    "f68bde4db9f46aa8": {  # 연구개발실적(제78기): Mobile UFS 4.1, ZUFS 4.1, PCIe Gen4/Gen5 SSD(PEB210), CMM-DDR5, 1cnm LPDDR5X, 1bnm DDR5 3DS, 1cnm GDDR7, HBM4
        "entities": [
            (P, "hbm4", "HBM4"), (P, "ddr5 3ds", "DDR5 3DS"),
            (P, "cmm-ddr5", "CMM-DDR5"),
            (P, "pcie gen4 ssd", "PCIe Gen4 SSD"),
        ],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "mobile ufs", "Mobile UFS"), 0.92),
            E("PRODUCES", ("org", SKH), ("ent", P, "zufs", "ZUFS"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "pcie gen4 ssd", "PCIe Gen4 SSD"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "pcie gen5 ssd", "PCIe Gen5 SSD"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "cmm-ddr5", "CMM-DDR5"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "lpddr5x", "LPDDR5X"), 0.92),
            E("PRODUCES", ("org", SKH), ("ent", P, "ddr5 3ds", "DDR5 3DS"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "gddr7", "GDDR7"), 0.92),
            E("PRODUCES", ("org", SKH), ("ent", P, "hbm4", "HBM4"), 0.95),
            E("USES_TECH", ("org", SKH), ("ent", T, "cxl", "CXL"), 0.85),
            E("USES_TECH", ("org", SKH), ("ent", T, "mr-muf", "MR-MUF"), 0.88),
        ],
    },
    "b94ad9b2ad6bc259": {  # 영업개황: HBM4 업계최초 양산, HBM3E 12단, 256GB DDR5, 321단 QLC
        "entities": [
            (P, "256gb ddr5", "256GB DDR5"),
        ],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "hbm4", "HBM4"), 0.95),
            E("PRODUCES", ("org", SKH), ("ent", P, "hbm3e", "HBM3E"), 0.95),
            E("PRODUCES", ("org", SKH), ("ent", P, "256gb ddr5", "256GB DDR5"), 0.9),
        ],
    },
    "e1a0a5fe3125780b": {  # HBM3E 주력, HBM4 9월 세계최초 양산
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "hbm3e", "HBM3E"), 0.95),
            E("PRODUCES", ("org", SKH), ("ent", P, "hbm4", "HBM4"), 0.95),
        ],
    },
    "822292f83ca21cf0": {  # AIN(AI-NAND) Family: AIN P/D/B(HBF)
        "entities": [
            (P, "ain family", "AIN(AI-NAND) Family"),
            (P, "hbf", "HBF(High Bandwidth Flash)"),
        ],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "ain family", "AIN(AI-NAND) Family"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "hbf", "HBF(High Bandwidth Flash)"), 0.85),
        ],
    },
    "5704093251cab824": {  # AIN Family, QLC eSSD, Solidigm 통합 시너지
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "ain family", "AIN(AI-NAND) Family"), 0.88),
            E("RELATED_PARTY", ("org", SKH), ("org", "Solidigm"), 0.82, "종속기업(NAND/eSSD 통합)"),
        ],
    },
    "51569b2bd309ae6b": {  # CXL 메모리 준비
        "entities": [
            (P, "cxl 메모리", "CXL 메모리"),
        ],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "cxl 메모리", "CXL 메모리"), 0.85),
            E("USES_TECH", ("org", SKH), ("ent", T, "cxl", "CXL"), 0.85),
        ],
    },
    "f1e64d2afaf08274": {  # 24GB/48GB DDR5 게이밍 대응
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "ddr5", "DDR5"), 0.9),
        ],
    },
    "8ea0f5d8c9fdc8e5": {  # Automotive: DDR4/5, LPDDR4/5, Automotive Grade & HBM
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "lpddr5x", "LPDDR5X"), 0.8),
        ],
    },

    # ── II. 주요계약 (RELATED_PARTY) ───────────────────────────
    "35ea437cde401dc9": {  # 주요계약표: Rambus(특허 크로스라이선스), Intel(NAND 영업양수)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "Rambus Inc."), 0.85, "특허 크로스 라이선스"),
            E("RELATED_PARTY", ("org", SKH), ("org", "Intel Corporation"), 0.85, "NAND 영업양수"),
        ],
    },

    # ── III. 연결재무제표 주석 : 관계기업/공동기업/특수관계자 ────────
    "14cfbd88877db8a9": {  # 관계기업및공동기업투자 내역
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK China Company Limited"), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK South East Asia Investment Pte. Ltd."), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SiFive, Inc."), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "우시시신파직접회로산업원유한공사"), 0.85, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "HITECH Semiconductor (Wuxi) Co., Ltd."), 0.9, "공동기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix system ic (Wuxi) Co., Ltd."), 0.9, "공동기업"),
        ],
    },
    "1055899f1af2e820": {  # 종속기업 추가/제외: 에스케이파워텍 추가
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "에스케이파워텍"), 0.88, "종속기업(지분취득)"),
        ],
    },
    "136daf1aea8e096e": {  # 공동기업/기타특수관계자: HITECH, Hystars, SK에어플러스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "Hystars Semiconductor (Wuxi) Co., Ltd."), 0.88, "공동기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "에스케이에어플러스"), 0.82, "기타특수관계자"),
        ],
    },
    "1a44a4c187dfaf08": {  # 전체 특수관계자: 미래에셋위반도체 사모투자, Hystars, HITECH, 반도체성장 사모투자신탁, SK스퀘어
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK스퀘어"), 0.9, "기타특수관계자(최대주주)"),
        ],
    },

    # ── III. 별도재무제표 주석 : 특수관계자 ────────────────────────
    "46947cdeb37836e6": {  # 별도 전체 특수관계자: 종속/공동/관계/기타 (HITECH, 반도체성장신탁, 미래에셋위반도체, SK스퀘어)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK스퀘어"), 0.88, "기타특수관계자(최대주주)"),
        ],
    },

    # ── X. 대주주 등과의 거래내용 (SUPPLIES_TO / RELATED_PARTY) ─────
    "cbb6b917593177a3": {  # 영업거래: SK하이닉스→해외판매법인(반도체 매출), 해외생산법인(China)→SK(반도체 매입)
        "entities": [],
        "edges": [
            # SK하이닉스(공급자) → 해외 판매법인(수요자) : 반도체 매출
            E("SUPPLIES_TO", ("org", SKH), ("org", "SK hynix America Inc."), 0.85),
            E("SUPPLIES_TO", ("org", SKH), ("org", "SK hynix(Wuxi) Semiconductor Sales Ltd."), 0.85),
            E("SUPPLIES_TO", ("org", SKH), ("org", "SK hynix Semiconductor Taiwan Inc."), 0.85),
            E("SUPPLIES_TO", ("org", SKH), ("org", "SK hynix Semiconductor HongKong"), 0.85),
            # 해외 생산법인(공급자) → SK하이닉스(수요자) : 반도체 매입
            E("SUPPLIES_TO", ("org", "SK hynix Semiconductor(China) Ltd."), ("org", SKH), 0.85),
        ],
    },
    "3eec8354eba3c7fb": {  # 대여금: Dalian, NAND Product Solutions (해외법인 특수관계)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix Semiconductor(Dalian) Co., Ltd."), 0.85, "해외법인(대여)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix NAND Product Solutions"), 0.85, "해외법인(대여)"),
        ],
    },
    "469d9722da78f10c": {  # 자산양수도: China, HITECH Wuxi, Chongqing (기계장치 매각/매입)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix Semiconductor(China) Ltd."), 0.85, "해외법인(자산거래)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "HITECH Semiconductor(Wuxi) Co., Ltd"), 0.85, "공동기업(자산거래)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix Semiconductor(Chongqing) Ltd."), 0.85, "해외법인(자산거래)"),
        ],
    },
    "d1108db04c9ed70d": {  # 출자: China, Dalian 추가증자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix Semiconductor(China) Ltd."), 0.85, "해외법인(출자증자)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix Semiconductor(Dalian) Co., Ltd."), 0.85, "해외법인(출자증자)"),
        ],
    },

    # ── IX. 계열회사 등에 관한 사항 (SK스퀘어 → SK하이닉스 20.1%, 임원겸직) ──
    "674d011c5d68cad4": {  # 계열사 출자: SK스퀘어 SK하이닉스 20.1%; SK하이닉스 100% 자회사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "SK스퀘어"), ("org", SKH), 0.9, "지분보유(20.1%, 최대주주)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK하이스텍"), 0.88, "종속기업(100%)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK하이이엔지"), 0.88, "종속기업(100%)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK하이닉스시스템IC"), 0.88, "종속기업(100%)"),
        ],
    },
    "5a5f7e2d3fde9f5e": {  # SK하이닉스 → 행복나래 100%, SK키파운드리 100%
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "행복나래"), 0.85, "종속기업(100%)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK키파운드리"), 0.88, "종속기업(100%)"),
        ],
    },
    "b7df32d843e5f828": {  # 임원겸직: 곽노정→SK hynix NAND Product Solutions/SK Americas; 장용호→SK(주) 등
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix NAND Product Solutions Corp."), 0.8, "임원겸직"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK Americas, Inc."), 0.78, "임원겸직"),
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
    rows = get_chunks(WHERE)
    by_id = {r["chunk_id"]: r for r in rows}
    print(f"[batch] 청크 {len(rows)}건 (rcept {RCEPT})")

    # 멱등: 이미 원장에 처리된 청크는 스킵
    done = H.ledger_processed_ids()

    driver = neo4j_driver()
    conn = mariadb_conn()

    n_ent_total = 0
    n_edge_total = 0
    n_prov_total = 0
    ent_by_label: dict[str, int] = {}
    edge_by_type: dict[str, int] = {}
    processed = 0
    skipped = 0

    extracted_ids = set(EXTRACTIONS.keys())

    # 1) 추출 결과가 있는 청크 처리
    for cid, payload in EXTRACTIONS.items():
        if cid not in by_id:
            print(f"  [warn] {cid} 대상 rcept 에 없음 — 스킵")
            continue
        if cid in done:
            skipped += 1
            continue
        row = by_id[cid]
        n_ent = 0
        n_edge = 0

        for label, canonical, name in payload.get("entities", []):
            eid = merge_entity(driver, label, canonical, name)
            add_edge(driver, "hasObject",
                     {"kind": "chunk", "chunk_id": cid},
                     {"kind": "entity", "label": label, "id": eid},
                     chunk_id=cid, rcept_no=RCEPT, confidence=1.0)
            write_provenance(conn, cid, "hasObject", eid, cid, RCEPT, 1.0)
            n_ent += 1
            n_prov_total += 1
            ent_by_label[label] = ent_by_label.get(label, 0) + 1

        for e in payload.get("edges", []):
            rel = e["rel"]
            conf = e["conf"]
            rtype = e.get("relation_type")
            fm, fid = _match_and_id(driver, e["from"])
            tm, tid = _match_and_id(driver, e["to"])
            add_edge(driver, rel, fm, tm, chunk_id=cid, rcept_no=RCEPT,
                     confidence=conf, relation_type=rtype)
            write_provenance(conn, fid, rel, tid, cid, RCEPT, conf)
            n_edge += 1
            n_prov_total += 1
            edge_by_type[rel] = edge_by_type.get(rel, 0) + 1

        conn.commit()
        H.mark_processed(cid, n_ent, n_edge, RCEPT, row["section_path"])
        n_ent_total += n_ent
        n_edge_total += n_edge
        processed += 1

    # 2) 나머지 대상 청크는 엣지 0개로 처리 표시(누락 0 보장)
    for r in rows:
        cid = r["chunk_id"]
        if cid in extracted_ids or cid in done:
            continue
        H.mark_processed(cid, 0, 0, RCEPT, r["section_path"])
        processed += 1

    conn.close()
    driver.close()

    print("=== SK하이닉스 2025 추출 결과 ===")
    print(f"  대상 청크: {len(rows)}  신규 처리: {processed}  스킵(원장): {skipped}")
    print(f"  엔티티 hasObject: {n_ent_total}  타입별: {ent_by_label}")
    print(f"  엣지 총: {n_edge_total}  타입별: {edge_by_type}")
    print(f"  provenance 행: {n_prov_total}")
    print(f"  원장: {H.LEDGER_PATH}")


if __name__ == "__main__":
    run()
