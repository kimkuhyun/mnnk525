"""B단계 비정형 추출 적재 — 한미반도체 2025 사업보고서 전체 (rcept 20260312001230, 519청크).

이 파일의 EXTRACTIONS = Claude(에이전트)가 rcept 20260312001230 의 chunk_index 전체
(519청크)를 읽고 본문 근거로 판단한 엔티티·엣지다. 결정론 코드가 아니라 언어이해 산출물.
적재는 extract_helpers 의 멱등 헬퍼로 수행. 근거 없는 추정 금지(환각 방어).

대상 청크 전부 mark_processed(엣지 0개여도) → 누락 0.
원장은 db/graph/ledger/20260312001230.jsonl 전용(공유 ledger 금지).
대부분(감사보고서·연결감사보고서·재무제표 주석 정형표)은 추출 대상 아님 → 엣지 0개로 처리표시.

실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_hanmi2025.py
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

RCEPT = "20260312001230"
WHERE = f"WHERE rcept_no='{RCEPT}'"
HANMI = "한미반도체"  # resolve_org → corp_code 00161383
SKH = "SK하이닉스"    # resolve_org → corp_code 00164779

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

    # ── II. 사업의 내용 : 제품/기술 + 매출처 ────────────────────────

    "583d63e954ab87e3": {  # 주력장비 HBM TC 본더(12/16단), WIDE TC 본더, 하이브리드 본더 병행개발
        "entities": [
            (P, "hbm tc 본더", "HBM TC 본더"),
            (P, "wide tc 본더", "WIDE TC 본더"),
            (P, "하이브리드 본더", "하이브리드 본더"),
            (T, "thermal compression", "열압착(Thermal Compression) 본딩"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "hbm tc 본더", "HBM TC 본더"), 0.95),
            E("PRODUCES", ("org", HANMI), ("ent", P, "wide tc 본더", "WIDE TC 본더"), 0.85),
            E("PRODUCES", ("org", HANMI), ("ent", P, "하이브리드 본더", "하이브리드 본더"), 0.82),
            E("USES_TECH", ("org", HANMI), ("ent", T, "thermal compression", "열압착(Thermal Compression) 본딩"), 0.9),
        ],
    },
    "a28bb5886a11d1fd": {  # 6) 시장여건/경쟁: 수직통합제조, HBM TC 본더, WIDE TC 본더, 하이브리드 본더
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "hbm tc 본더", "HBM TC 본더"), 0.93),
            E("PRODUCES", ("org", HANMI), ("ent", P, "wide tc 본더", "WIDE TC 본더"), 0.82),
            E("PRODUCES", ("org", HANMI), ("ent", P, "하이브리드 본더", "하이브리드 본더"), 0.8),
        ],
    },
    "8034d7aa807f8bc4": {  # BOC COB 본더(세계최초), AI 시스템반도체용 TC/FC/Die 본더, MSVP, EMI Shield, 2.5D 패키징
        "entities": [
            (P, "boc cob 본더", "BOC COB 본더"),
            (P, "fc 본더", "FC 본더(Flip Chip Bonder)"),
            (P, "die 본더", "Die 본더"),
            (P, "msvp", "micro SAW & VISION PLACEMENT(MSVP)"),
            (P, "emi shield", "EMI Shield(전자기파 차폐) 장비"),
            (T, "2.5d 패키징", "AI 반도체 2.5D 패키징"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "boc cob 본더", "BOC COB 본더"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "fc 본더", "FC 본더(Flip Chip Bonder)"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "die 본더", "Die 본더"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "msvp", "micro SAW & VISION PLACEMENT(MSVP)"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield", "EMI Shield(전자기파 차폐) 장비"), 0.92),
            E("USES_TECH", ("org", HANMI), ("ent", T, "2.5d 패키징", "AI 반도체 2.5D 패키징"), 0.88),
        ],
    },
    "ace08be7a57e7b69": {  # 6-SIDE INSPECTION, 적층형 GDDR/eSSD 확장, BOC COB 본더, 2.5D 패키징
        "entities": [
            (P, "6-side inspection", "6-SIDE INSPECTION"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "6-side inspection", "6-SIDE INSPECTION"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "boc cob 본더", "BOC COB 본더"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "fc 본더", "FC 본더(Flip Chip Bonder)"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "die 본더", "Die 본더"), 0.88),
            E("USES_TECH", ("org", HANMI), ("ent", T, "2.5d 패키징", "AI 반도체 2.5D 패키징"), 0.85),
        ],
    },
    "eff01c1bf6033489": {  # 6-SIDE INSPECTION 검사, 하이브리드 본더 병행개발 (HBM 수율)
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "6-side inspection", "6-SIDE INSPECTION"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "하이브리드 본더", "하이브리드 본더"), 0.8),
        ],
    },
    "3c0dcf24ffefdcac": {  # 2.5D 패키징, MSVP(점유율1위), EMI Shield 2.0 X
        "entities": [
            (P, "emi shield 2.0 x", "EMI SHIELD 2.0 X"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "msvp", "micro SAW & VISION PLACEMENT(MSVP)"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield", "EMI Shield(전자기파 차폐) 장비"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield 2.0 x", "EMI SHIELD 2.0 X"), 0.88),
            E("USES_TECH", ("org", HANMI), ("ent", T, "2.5d 패키징", "AI 반도체 2.5D 패키징"), 0.85),
        ],
    },
    "804fda07e759b940": {  # MSVP 점유율1위, EMI Shield(2016 첫출시, 점유율1위), EMI Shield 2.0 X
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "msvp", "micro SAW & VISION PLACEMENT(MSVP)"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield", "EMI Shield(전자기파 차폐) 장비"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield 2.0 x", "EMI SHIELD 2.0 X"), 0.85),
        ],
    },
    "4327fb58813bfa77": {  # 제품 현황표: micro SAW 시리즈, EMI Shield, TC BONDER(4.5/4.0/2.5D), 6-SIDE, FLIP CHIP, META GRINDER, LASER, VISION 등
        "entities": [
            (P, "micro saw", "micro SAW (반도체 절단 장비)"),
            (P, "tc bonder", "TC BONDER"),
            (P, "meta grinder", "META GRINDER"),
            (P, "laser marking", "LASER MARKING"),
            (P, "laser cutting", "LASER CUTTING"),
            (P, "laser ablation", "LASER ABLATION"),
            (P, "3d vision inspection", "3D VISION INSPECTION"),
            (P, "vision placement", "VISION PLACEMENT"),
            (P, "pick & place", "PICK & PLACE"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "micro saw", "micro SAW (반도체 절단 장비)"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "tc bonder", "TC BONDER"), 0.93),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield", "EMI Shield(전자기파 차폐) 장비"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "6-side inspection", "6-SIDE INSPECTION"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "fc 본더", "FC 본더(Flip Chip Bonder)"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "boc cob 본더", "BOC COB 본더"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "meta grinder", "META GRINDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "laser marking", "LASER MARKING"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "laser cutting", "LASER CUTTING"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "laser ablation", "LASER ABLATION"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "3d vision inspection", "3D VISION INSPECTION"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "vision placement", "VISION PLACEMENT"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "pick & place", "PICK & PLACE"), 0.9),
        ],
    },
    "b0ff3c5a3c5da059": {  # 매출액표: 반도체 제조용 장비/Conversion Kit, 상표 HANMI
        "entities": [
            (P, "반도체 제조용 장비", "반도체 제조용 장비"),
            (P, "conversion kit", "Conversion Kit"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "반도체 제조용 장비", "반도체 제조용 장비"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "conversion kit", "Conversion Kit"), 0.85),
        ],
    },
    "3e8e7c8fdba4c682": {  # (4) 주요매출처: SK하이닉스, Micron, ASE, AmKor, JCET, Huatian, TFME, Infineon, ST Micro, PTI, Skyworks, Luxshare / 국내 JCET스태츠칩팩코리아, ASE코리아, Amkor코리아, 삼성전기, LG이노텍, 코리아써키트, SFA반도체, 시그네틱스
        "entities": [],
        "edges": [
            # 한미(공급자) → 매출처(수요자) : 반도체 장비 매출
            E("SUPPLIES_TO", ("org", HANMI), ("org", SKH), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Micron Technology"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "ASE Technology"), 0.82),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Amkor Technology"), 0.82),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "JCET"), 0.82),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Huatian Technology"), 0.82),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "TFME"), 0.8),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Infineon Technologies"), 0.8),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "STMicroelectronics"), 0.8),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Powertech Technology"), 0.8),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Skyworks Solutions"), 0.8),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Luxshare"), 0.8),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "삼성전기"), 0.82),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "LG이노텍"), 0.82),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "코리아써키트"), 0.8),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "SFA반도체"), 0.8),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "시그네틱스"), 0.8),
        ],
    },
    "7d103ed48d159486": {  # IV. TC본더 글로벌 71.2% 1위, HBM4/5/6, WIDE TC 본더, 하이브리드 본더, BOC COB 본더, EMI 장비
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "tc bonder", "TC BONDER"), 0.93),
            E("PRODUCES", ("org", HANMI), ("ent", P, "wide tc 본더", "WIDE TC 본더"), 0.85),
            E("PRODUCES", ("org", HANMI), ("ent", P, "하이브리드 본더", "하이브리드 본더"), 0.82),
            E("PRODUCES", ("org", HANMI), ("ent", P, "boc cob 본더", "BOC COB 본더"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield", "EMI Shield(전자기파 차폐) 장비"), 0.85),
        ],
    },
    "acfa1f8f9748ba55": {  # IV. TC 본더 글로벌 No.1, 테크인사이츠 71.2% 점유율
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "tc bonder", "TC BONDER"), 0.9),
        ],
    },

    # ── III. 연결재무제표 주석 : 종속기업/관계기업/특수관계자 (RELATED_PARTY) ──

    "bc5043b0c3a50e3e": {  # 종속기업투자 내역표: Hanmi Taiwan/Vietnam/Singapore 100%
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "Hanmi Taiwan Co., Ltd."), 0.92, "종속기업(100%)"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "Hanmi Vietnam Co., Ltd."), 0.92, "종속기업(100%)"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "Hanmi Singapore Pte. Ltd."), 0.92, "종속기업(100%)"),
        ],
    },
    "09f0244c384b1b62": {  # 연결대상 변동: Hanmi Singapore 당기 설립
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "Hanmi Singapore Pte. Ltd."), 0.88, "종속기업(당기설립)"),
        ],
    },
    "8c6e64936592e5c3": {  # 특수관계자: 관계기업 곽신홀딩스, 기타특수관계자 한미인터내셔널, 도야인터내셔날
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "곽신홀딩스(주)"), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "한미인터내셔널(주)"), 0.85, "기타특수관계자"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "(주)도야인터내셔날"), 0.85, "기타특수관계자"),
        ],
    },
    "17df486a70783b88": {  # 관계기업투자: 곽신홀딩스 40%
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "곽신홀딩스(주)"), 0.9, "관계기업(40%)"),
        ],
    },
    "5f50d1ea0e41349d": {  # 관계기업투자 내역: 곽신홀딩스 40%(전기49%) 도소매업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "곽신홀딩스(주)"), 0.9, "관계기업(40%)"),
        ],
    },
    "1d852109b07b95cc": {  # 전체 특수관계자: 곽신홀딩스(관계기업), 도야인터내셔날(그밖)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "곽신홀딩스(주)"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "(주)도야인터내셔날"), 0.82, "기타특수관계자"),
        ],
    },
    "a54197b23ed9167b": {  # 별도 전체 특수관계자: 곽신홀딩스, 도야인터내셔날
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "곽신홀딩스(주)"), 0.85, "관계기업"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "(주)도야인터내셔날"), 0.8, "기타특수관계자"),
        ],
    },
    "228ff512c9dc4df0": {  # 별도 종속기업/관계기업투자: Hanmi Taiwan/Vietnam/Singapore 100%, 곽신홀딩스 40%
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "Hanmi Taiwan Co., Ltd."), 0.9, "종속기업(100%)"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "Hanmi Vietnam Co., Ltd."), 0.9, "종속기업(100%)"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "Hanmi Singapore Pte. Ltd."), 0.9, "종속기업(100%)"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "곽신홀딩스(주)"), 0.88, "관계기업(40%)"),
        ],
    },

    # ── X. 대주주 등과의 거래내용 (RELATED_PARTY) ────────────────────
    "0c74b123d935bd6b": {  # 대주주 자산양수도: 곽동신(최대주주) 곽신홀딩스 지분증권 자산양도
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "곽신홀딩스(주)"), 0.8, "대주주거래(지분양도)"),
        ],
    },

    # ── XI. 소송 (RELATED_PARTY, 특허소송) ───────────────────────────
    "aafefa5229e4910b": {  # 소송: 한미↔한화세미텍 특허침해 양방향 소송
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "한화세미텍"), 0.9, "특허침해소송(원고/피고)"),
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

    print("=== 한미반도체 2025 추출 결과 ===")
    print(f"  대상 청크: {len(rows)}  신규 처리: {processed}  스킵(원장): {skipped}")
    print(f"  엔티티 hasObject: {n_ent_total}  타입별: {ent_by_label}")
    print(f"  엣지 총: {n_edge_total}  타입별: {edge_by_type}")
    print(f"  provenance 행: {n_prov_total}")
    print(f"  원장: {H.LEDGER_PATH}")


if __name__ == "__main__":
    run()
