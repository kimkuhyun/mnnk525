"""파일럿 배치 추출 적재 — 삼성전자 2024 사업보고서 II장 + 주석 (rcept 20250311001085).

이 파일의 EXTRACTIONS 리스트 = Claude(에이전트)가 242개 청크를 하나씩 읽고
본문 근거로 판단한 엔티티·엣지다. 결정론 코드가 아니라 언어이해 산출물을 기록한 것.
적재 자체는 extract_helpers 의 멱등 헬퍼로 수행한다.

실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_pilot_samsung2024.py
모든 배치 청크는 엣지 0개여도 mark_processed(누락 0 보장).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_helpers import (  # noqa: E402
    add_edge,
    entity_id,
    get_chunks,
    mariadb_conn,
    merge_entity,
    merge_org_node,
    neo4j_driver,
    resolve_org,
    write_provenance,
)
from extract_helpers import mark_processed  # noqa: E402

RCEPT = "20250311001085"
WHERE = (
    f"WHERE rcept_no='{RCEPT}' "
    "AND (section_path LIKE 'II.%' OR section_path LIKE '%주석%')"
)
SAMSUNG = "삼성전자"  # resolve_org → corp_code 00126380

# ── Claude 추출 결과 (청크별) ──────────────────────────────
# 각 항목: chunk_id → {entities:[(label,canonical,name)], edges:[edge dict]}
# edge dict: rel(PRODUCES|USES_TECH|SUPPLIES_TO|RELATED_PARTY|hasObject),
#   from/to = ('org', 회사명) | ('ent', label, canonical, name),
#   conf, (relation_type for RELATED_PARTY)
#
# 회사는 resolve_org 로 매칭(3사 corp_code 또는 needs_er er_name).
# 제품/기술은 canonical(소문자 정규화 키)로 MERGE.

P = "Product"
T = "Technology"


def E(rel, frm, to, conf, relation_type=None):
    d = {"rel": rel, "from": frm, "to": to, "conf": conf}
    if relation_type:
        d["relation_type"] = relation_type
    return d


# 제품/기술 canonical 사전(중복 제거용)
EXTRACTIONS: dict[str, dict] = {

    # ── II. 제품 라인업 / 사업부문 ──────────────────────────
    "2a022fd44e7ec054": {  # 사업부문별 생산제품 개요
        "entities": [
            (P, "tv", "TV"), (P, "냉장고", "냉장고"), (P, "세탁기", "세탁기"),
            (P, "에어컨", "에어컨"), (P, "스마트폰", "스마트폰"),
            (P, "네트워크시스템", "네트워크시스템"),
            (P, "dram", "DRAM"), (P, "nand flash", "NAND Flash"),
            (P, "모바일ap", "모바일AP"),
            (P, "oled 패널", "OLED 패널"), (P, "디지털 콕핏", "디지털 콕핏"),
            (P, "카오디오", "카오디오"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "tv", "TV"), 0.95),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "냉장고", "냉장고"), 0.95),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "세탁기", "세탁기"), 0.95),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "에어컨", "에어컨"), 0.95),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "스마트폰", "스마트폰"), 0.97),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "네트워크시스템", "네트워크시스템"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "dram", "DRAM"), 0.97),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "nand flash", "NAND Flash"), 0.97),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "모바일ap", "모바일AP"), 0.95),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "oled 패널", "OLED 패널"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "디지털 콕핏", "디지털 콕핏"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "카오디오", "카오디오"), 0.88),
        ],
    },
    "0e1d85fa87c1f189": {  # 부문별 주요제품 매출표 (TV/모니터/냉장고.. DRAM/NAND/모바일AP, OLED패널, 디지털콕핏)
        "entities": [
            (P, "모니터", "모니터"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "모니터", "모니터"), 0.92),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "dram", "DRAM"), 0.95),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "nand flash", "NAND Flash"), 0.95),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "oled 패널", "OLED 패널"), 0.9),
        ],
    },
    "05b2b0730657d7e9": {  # 연구개발실적: Galaxy Z Fold6/Flip6, S24, Neo QLED 8K/4K, BESPOKE AI ..
        "entities": [
            (P, "galaxy z fold6", "Galaxy Z Fold6"),
            (P, "galaxy z flip6", "Galaxy Z Flip6"),
            (P, "galaxy s24", "Galaxy S24"),
            (P, "neo qled 8k", "Neo QLED 8K"),
            (P, "neo qled 4k", "Neo QLED 4K"),
            (P, "galaxy book4", "Galaxy Book4"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy z fold6", "Galaxy Z Fold6"), 0.95),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy z flip6", "Galaxy Z Flip6"), 0.95),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy s24", "Galaxy S24"), 0.95),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "neo qled 8k", "Neo QLED 8K"), 0.93),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "neo qled 4k", "Neo QLED 4K"), 0.93),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy book4", "Galaxy Book4"), 0.9),
        ],
    },
    "0501d7d966649770": {  # 마이크로 LED, Neo QLED 8K/4K, OLED, 릴루미노 모드, 태블릿/웨어러블
        "entities": [
            (T, "마이크로 led", "마이크로 LED"),
            (P, "태블릿", "태블릿"),
            (T, "릴루미노 모드", "릴루미노 모드(Relumino Mode)"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", T, "마이크로 led", "마이크로 LED"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "태블릿", "태블릿"), 0.9),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "릴루미노 모드", "릴루미노 모드(Relumino Mode)"), 0.8),
        ],
    },
    "8c9ef6b204449caa": {  # 8K AI 업스케일링 프로, 녹스(Knox) 보안 솔루션, Neo QLED/OLED/QLED, 사운드바
        "entities": [
            (T, "8k ai 업스케일링 프로", "8K AI 업스케일링 프로"),
            (T, "녹스", "녹스(Knox)"),
            (P, "사운드바", "사운드바"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "8k ai 업스케일링 프로", "8K AI 업스케일링 프로"), 0.88),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "녹스", "녹스(Knox)"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "사운드바", "사운드바"), 0.85),
        ],
    },
    "9d221f3dd8f7d3d6": {  # Galaxy AI, Galaxy Z Fold6/Flip6, 스마트워치, 스마트링, 무선이어폰
        "entities": [
            (T, "galaxy ai", "Galaxy AI"),
            (P, "스마트워치", "스마트워치"),
            (P, "스마트링", "스마트링"),
            (P, "무선이어폰", "무선이어폰"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "galaxy ai", "Galaxy AI"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "스마트워치", "스마트워치"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "스마트링", "스마트링"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "무선이어폰", "무선이어폰"), 0.88),
        ],
    },
    "dd10fd4f5329fb94": {  # Samsung Wallet, Samsung Health 서비스
        "entities": [
            (P, "samsung wallet", "Samsung Wallet"),
            (P, "samsung health", "Samsung Health"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "samsung wallet", "Samsung Wallet"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "samsung health", "Samsung Health"), 0.85),
        ],
    },
    "e9083d83b9bc7c5c": {  # Galaxy Z 폴드/플립, Dynamic AMOLED 2X, UWB
        "entities": [
            (T, "dynamic amoled 2x", "Dynamic AMOLED 2X"),
            (T, "uwb", "UWB(Ultra Wideband)"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "dynamic amoled 2x", "Dynamic AMOLED 2X"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "uwb", "UWB(Ultra Wideband)"), 0.82),
        ],
    },
    "0a3ae88af4062e71": {  # 반도체 설명: AP, 이미지센서 공급, Foundry
        "entities": [
            (P, "이미지센서", "이미지 센서"),
            (T, "foundry", "Foundry"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "이미지센서", "이미지 센서"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "모바일ap", "모바일AP"), 0.92),
        ],
    },
    "95f9ae8fc5e23291": {  # Foundry 4나노/3나노 GAA, 2나노 Exynos
        "entities": [
            (T, "gaa", "GAA(Gate-All-Around)"),
            (P, "exynos", "Exynos"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "gaa", "GAA(Gate-All-Around)"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "exynos", "Exynos"), 0.88),
        ],
    },
    "539cc40ee2fa79dc": {  # 서버향 DDR5, QLC SSD, On-Device AI, 2나노 Exynos, 이미지센서
        "entities": [
            (P, "ddr5", "DDR5"),
            (P, "qlc ssd", "QLC SSD"),
            (T, "on-device ai", "On-Device AI"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "ddr5", "DDR5"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "qlc ssd", "QLC SSD"), 0.88),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "on-device ai", "On-Device AI"), 0.82),
        ],
    },
    "9fdbdf7413323531": {  # HBM, DDR5, LPDDR5x, QLC SSD
        "entities": [
            (P, "hbm", "HBM"),
            (P, "lpddr5x", "LPDDR5x"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "hbm", "HBM"), 0.92),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "lpddr5x", "LPDDR5x"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "ddr5", "DDR5"), 0.9),
        ],
    },
    "2658034a19185cf4": {  # SDC: OLED, QD-OLED 디스플레이 기술
        "entities": [
            (T, "qd-oled", "QD-OLED"),
            (T, "oled", "OLED"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "qd-oled", "QD-OLED"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "oled", "OLED"), 0.85),
        ],
    },

    # ── II. 공급/매입처 (SUPPLIES_TO) ──────────────────────
    "fa2c44f6fafa4ad8": {  # 주요 매입처 표: Qualcomm/MediaTek(모바일AP), CSOT/AUO(패널), 삼성전기/파트론(카메라), 솔브레인/동우화인켐(Chemical), SUMCO/SILTRONIC(Wafer), 비에이치/씨유테크(FPCA), Apple/LENS(Cover Glass)
        "entities": [],
        "edges": [
            # 공급자 → 삼성전자(수요자). SUPPLIES_TO 방향 = 공급자→수요자.
            E("SUPPLIES_TO", ("org", "Qualcomm"), ("org", SAMSUNG), 0.92),
            E("SUPPLIES_TO", ("org", "MediaTek"), ("org", SAMSUNG), 0.92),
            E("SUPPLIES_TO", ("org", "CSOT"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "AUO"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "삼성전기"), ("org", SAMSUNG), 0.9),
            E("SUPPLIES_TO", ("org", "파트론"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "솔브레인"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "동우화인켐"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "SUMCO"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "SILTRONIC"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "비에이치"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "씨유테크"), ("org", SAMSUNG), 0.85),
        ],
    },
    "7ab07c6e43fae144": {  # 주요 매출처: Apple, Deutsche Telekom, Hong Kong Techtronics, Supreme Electronics, Verizon
        "entities": [],
        "edges": [
            # 삼성전자(공급자) → 주요 매출처(수요자)
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "Apple"), 0.88),
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "Deutsche Telekom"), 0.85),
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "Hong Kong Techtronics"), 0.82),
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "Supreme Electronics"), 0.82),
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "Verizon"), 0.85),
        ],
    },
    "6d36aadc1d0c0f42": {  # SOC/통신모듈을 NVIDIA, WNC 등에서 공급받음
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "NVIDIA"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "WNC"), ("org", SAMSUNG), 0.8),
        ],
    },
    "d29f147065dcbc0b": {  # 통신사업자 판매경로: SK텔레콤, KT, LG유플러스
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "SK텔레콤"), 0.8),
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "케이티"), 0.8),
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "LG유플러스"), 0.8),
        ],
    },
    "a7d5d02fd3713424": {  # Harman이 Roon Labs LLC 인수 → Roon 기술
        "entities": [
            (T, "roon", "Roon 음원재생기술"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Roon Labs LLC"), 0.78, "인수(Harman)"),
        ],
    },

    # ── 주석: 특수관계자 (RELATED_PARTY) ───────────────────
    "089e6cea24ed0e1d": {  # 특수관계자 표: 관계기업/공동기업·그밖의특수관계자·대규모기업집단
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성에스디에스"), 0.9, "관계기업및공동기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성전기"), 0.9, "관계기업및공동기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성SDI"), 0.9, "관계기업및공동기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "제일기획"), 0.9, "관계기업및공동기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성물산"), 0.9, "그밖의특수관계자"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성이앤에이"), 0.88, "대규모기업집단"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "에스원"), 0.88, "대규모기업집단"),
        ],
    },
    "7483b7079c7af934": {  # 연결회사 개요: 삼성디스플레이, SEA 종속기업 / 삼성전기 등 관계기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성디스플레이"), 0.92, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Electronics America"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성전기"), 0.88, "관계기업및공동기업"),
        ],
    },
    "d2de8e3324ad184a": {  # 삼성바이오로직스(관계기업), 삼성바이오에피스, Biogen
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성바이오로직스"), 0.9, "관계기업"),
        ],
    },
    "ecb7a1eaf69fcf50": {  # 레인보우로보틱스(관계기업) 콜옵션 / 삼성바이오로직스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "레인보우로보틱스"), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성바이오로직스"), 0.88, "관계기업"),
        ],
    },
    "3b8d31f3385806aa": {  # 별도재무 주석: 레인보우로보틱스 관계기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "레인보우로보틱스"), 0.88, "관계기업"),
        ],
    },
    "1357194040ad8fe5": {  # 레인보우로보틱스 콜옵션, 삼성디스플레이-Corning 풋옵션, TCL/CSOT
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "레인보우로보틱스"), 0.85, "관계기업"),
            E("RELATED_PARTY", ("org", "삼성디스플레이"), ("org", "Corning"), 0.78, "지분보유(풋옵션)"),
        ],
    },
}


def run():
    rows = get_chunks(WHERE)
    by_id = {r["chunk_id"]: r for r in rows}
    print(f"[batch] 청크 {len(rows)}건 (rcept {RCEPT})")

    driver = neo4j_driver()
    conn = mariadb_conn()

    n_ent_total = 0
    n_edge_total = 0
    n_prov_total = 0
    edge_by_type: dict[str, int] = {}
    processed = 0

    # 1) 추출 결과가 있는 청크 처리
    for cid, payload in EXTRACTIONS.items():
        if cid not in by_id:
            print(f"  [warn] {cid} 배치에 없음 — 스킵")
            continue
        row = by_id[cid]
        n_ent = 0
        n_edge = 0

        # 엔티티 MERGE (hasObject 로 출처청크에 anchor)
        for label, canonical, name in payload.get("entities", []):
            eid = merge_entity(driver, label, canonical, name)
            add_edge(driver, "hasObject",
                     {"kind": "chunk", "chunk_id": cid},
                     {"kind": "entity", "label": label, "id": eid},
                     chunk_id=cid, rcept_no=RCEPT, confidence=1.0)
            write_provenance(conn, cid, "hasObject", eid, cid, RCEPT, 1.0)
            n_ent += 1
            n_prov_total += 1

        # 엣지
        for e in payload.get("edges", []):
            rel = e["rel"]
            frm, to = e["from"], e["to"]
            conf = e["conf"]
            rtype = e.get("relation_type")

            # from / to match dict + subject/object id (provenance용)
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

    # 2) 나머지 배치 청크는 엣지 0개로 처리 표시(누락 0 보장)
    extracted_ids = set(EXTRACTIONS.keys())
    for r in rows:
        if r["chunk_id"] in extracted_ids:
            continue
        mark_processed(r["chunk_id"], 0, 0, RCEPT, r["section_path"])
        processed += 1

    conn.close()
    driver.close()

    print("=== 파일럿 추출 결과 ===")
    print(f"  처리 청크: {processed} / {len(rows)}")
    print(f"  엔티티(Product/Tech) hasObject: {n_ent_total}")
    print(f"  엣지 총: {n_edge_total}  타입별: {edge_by_type}")
    print(f"  provenance 행: {n_prov_total}")


def _match_and_id(driver, ref):
    """edge from/to 참조 → (add_edge match dict, provenance subject/object id)."""
    if ref[0] == "org":
        org = resolve_org(ref[1])
        merge_org_node(driver, org)
        return {"kind": "org", "org": org}, org["id"]
    # ('ent', label, canonical, name)
    _, label, canonical, name = ref
    eid = merge_entity(driver, label, canonical, name)
    return {"kind": "entity", "label": label, "id": eid}, eid


if __name__ == "__main__":
    run()
