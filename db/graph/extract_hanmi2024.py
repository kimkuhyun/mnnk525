"""배치 추출 적재 — 한미반도체 2024 사업보고서 (rcept 20250313001171, 587청크).

이 파일의 EXTRACTIONS = Claude(에이전트)가 청크 본문을 하나씩 읽고 본문 근거로
판단한 엔티티·엣지다. 결정론 코드가 아니라 언어이해 산출물 기록.
적재는 extract_helpers 멱등 헬퍼로 수행. 환각 금지 — 본문 명시·표 근거만.

원장 = db/graph/ledger/20250313001171.jsonl (이 rcept 전용, 공유 ledger 금지).
시작 시 원장 확인해 처리완료 청크 스킵. 대상 청크 전부 mark(0개여도) → 누락 0.

실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_hanmi2024.py
멱등: 재실행해도 MERGE/ON DUP/원장 갱신이라 중복 없음.
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

RCEPT = "20250313001171"
WHERE = f"WHERE rcept_no='{RCEPT}'"
HANMI = "한미반도체"  # resolve_org → corp_code 00161383

# ── 전용 원장 (이 rcept 만) ────────────────────────────────
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_DIR.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = LEDGER_DIR / f"{RCEPT}.jsonl"


def ledger_processed_ids() -> set[str]:
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


def mark_processed(chunk_id, n_ent, n_edge, section_path=None):
    rec = {
        "chunk_id": chunk_id, "n_ent": n_ent, "n_edge": n_edge,
        "rcept_no": RCEPT, "section_path": section_path,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


P = "Product"
T = "Technology"


def E(rel, frm, to, conf, relation_type=None):
    d = {"rel": rel, "from": frm, "to": to, "conf": conf}
    if relation_type:
        d["relation_type"] = relation_type
    return d


# ── Claude 추출 결과 (청크별) ──────────────────────────────
# from/to = ('org', 회사명) | ('ent', label, canonical, name)
# 한미는 후공정 장비 제조사. 매출처=한미→상대(SUPPLIES_TO), 매입처=상대→한미.
EXTRACTIONS: dict[str, dict] = {

    # ── II. 사업의 내용: 제품/기술 ─────────────────────────
    "d378fc1626c2664e": {  # 주력장비 라인업 + DUAL TC BONDER(HBM 열압착)
        "entities": [
            (P, "dual tc bonder", "DUAL TC BONDER"),
            (P, "6-side inspection", "HBM 6-SIDE INSPECTION"),
            (P, "micro saw&vision placement", "micro SAW&VISION PLACEMENT"),
            (P, "flip chip bonder", "FLIP CHIP BONDER"),
            (P, "emi shield vision", "EMI Shield VISION ATTACH/DETACH"),
            (P, "camera module 장비", "CAMERA MODULE 용 장비"),
            (P, "laser equipment", "LASER EQUIPMENT"),
            (P, "meta grinder", "META GRINDER"),
            (P, "tape saw", "TAPE SAW"),
            (P, "wafer saw", "WAFER SAW"),
            (T, "hbm", "HBM(광대역폭메모리)"),
            (T, "thermal compression bonding", "열압착(Thermal Compression) 본딩"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "dual tc bonder", "DUAL TC BONDER"), 0.95),
            E("PRODUCES", ("org", HANMI), ("ent", P, "6-side inspection", "HBM 6-SIDE INSPECTION"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "micro saw&vision placement", "micro SAW&VISION PLACEMENT"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "flip chip bonder", "FLIP CHIP BONDER"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield vision", "EMI Shield VISION ATTACH/DETACH"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "camera module 장비", "CAMERA MODULE 용 장비"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "laser equipment", "LASER EQUIPMENT"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "meta grinder", "META GRINDER"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "tape saw", "TAPE SAW"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "wafer saw", "WAFER SAW"), 0.88),
            E("USES_TECH", ("org", HANMI), ("ent", T, "thermal compression bonding", "열압착(Thermal Compression) 본딩"), 0.9),
            E("USES_TECH", ("org", HANMI), ("ent", T, "hbm", "HBM(광대역폭메모리)"), 0.85),
        ],
    },
    "aa083d0e9214b746": {  # DUAL TC BONDER 2017 SK하이닉스 공동개발/공급
        "entities": [
            (P, "dual tc bonder", "DUAL TC BONDER"),
            (T, "hbm", "HBM(광대역폭메모리)"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "dual tc bonder", "DUAL TC BONDER"), 0.95),
            E("USES_TECH", ("org", HANMI), ("ent", T, "hbm", "HBM(광대역폭메모리)"), 0.88),
            # 2017 SK하이닉스 공동개발 → 공급 (한미→SK하이닉스)
            E("SUPPLIES_TO", ("org", HANMI), ("org", "SK하이닉스"), 0.9),
            E("RELATED_PARTY", ("org", HANMI), ("org", "SK하이닉스"), 0.85, "DUAL TC BONDER 공동개발(2017)"),
        ],
    },
    "356f1547f3af0503": {  # DUAL TC BONDER AI/HBM 핵심, 6-SIDE INSPECTION, FLIP CHIP BONDER, MULTI DIE BONDER, BIG DIE BONDER
        "entities": [
            (P, "multi die bonder", "MULTI DIE BONDER"),
            (P, "big die bonder", "BIG DIE BONDER"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "multi die bonder", "MULTI DIE BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "big die bonder", "BIG DIE BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "flip chip bonder", "FLIP CHIP BONDER"), 0.9),
        ],
    },
    "0976ca03c0d431ee": {  # FLIP CHIP/MULTI DIE/BIG DIE BONDER, micro SAW&VISION PLACEMENT, EMI Shield
        "entities": [
            (P, "emi shield 장비", "EMI Shield 장비"),
            (T, "emi shield", "EMI Shield(전자기파 차폐)"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "multi die bonder", "MULTI DIE BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "big die bonder", "BIG DIE BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "micro saw&vision placement", "micro SAW&VISION PLACEMENT"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield 장비", "EMI Shield 장비"), 0.9),
            E("USES_TECH", ("org", HANMI), ("ent", T, "emi shield", "EMI Shield(전자기파 차폐)"), 0.85),
        ],
    },
    "2019eb331e6eb78d": {  # micro SAW 국산화·세계1위, EMI Shield
        "entities": [
            (P, "micro saw", "micro SAW"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "micro saw", "micro SAW"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield 장비", "EMI Shield 장비"), 0.88),
        ],
    },
    "4bc2e6d95b6e0be4": {  # EMI Shield 6G 상용화 공정
        "entities": [
            (P, "emi shield 장비", "EMI Shield 장비"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield 장비", "EMI Shield 장비"), 0.88),
        ],
    },
    "291e4697567b2dda": {  # 연구개발실적 표: micro SAW 6종, EMI Shield, TC BONDER(SK하이닉스 공동개발) Dragon/Griffin/Tiger
        "entities": [
            (P, "micro saw", "micro SAW"),
            (P, "dual tc bonder dragon", "Dual TC Bonder DRAGON"),
            (P, "dual tc bonder griffin", "Dual TC Bonder GRIFFIN"),
            (P, "dual tc bonder tiger", "Dual TC Bonder TIGER"),
            (T, "dual bonding", "DUAL Bonding 방식"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "micro saw", "micro SAW"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "dual tc bonder dragon", "Dual TC Bonder DRAGON"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "dual tc bonder griffin", "Dual TC Bonder GRIFFIN"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "dual tc bonder tiger", "Dual TC Bonder TIGER"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield 장비", "EMI Shield 장비"), 0.9),
            E("USES_TECH", ("org", HANMI), ("ent", T, "dual bonding", "DUAL Bonding 방식"), 0.88),
            # 표에 "SK하이닉스와 공동개발" 명시
            E("RELATED_PARTY", ("org", HANMI), ("org", "SK하이닉스"), 0.88, "Dual TC Bonder 공동개발"),
        ],
    },
    "202fc71797f002b6": {  # 매출표: 반도체 제조용 장비 外(HANMI), Conversion Kit 등
        "entities": [
            (P, "반도체 제조용 장비", "반도체 제조용 장비"),
            (P, "conversion kit", "Conversion Kit"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "반도체 제조용 장비", "반도체 제조용 장비"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "conversion kit", "Conversion Kit"), 0.88),
        ],
    },

    # ── II. 주요 매출처(고객사) → SUPPLIES_TO (한미→고객) ──
    "46d0be7bdd0cf8c5": {  # 주요매출처: SK하이닉스, Micron, ASE, AmKor, JCET, Huatian, TFME, Infineon, ST Micro, PTI, Skyworks, Luxshare / 국내 JCET스태츠칩팩코리아, ASE코리아, Amkor코리아, 삼성전기, 삼성전자, LG이노텍, 코리아써키트, SFA반도체, 시그네틱스
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", HANMI), ("org", "SK하이닉스"), 0.9),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Micron Technology"), 0.88),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "ASE"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Amkor"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "JCET"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Huatian Technology"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "TFME"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Infineon"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "ST Micro"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "PTI"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Skyworks"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Luxshare"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "JCET스태츠칩팩코리아"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "ASE코리아"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Amkor코리아"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "삼성전기"), 0.88),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "삼성전자"), 0.88),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "LG이노텍"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "코리아써키트"), 0.82),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "SFA반도체"), 0.82),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "시그네틱스"), 0.82),
        ],
    },
    "ce68bb6d91cafdf8": {  # 매출처 후반부(코리아, ASE코리아, Amkor코리아, 삼성전기, 삼성전자, LG이노텍, 코리아써키트, SFA반도체, 시그네틱스) — 동일 매출처
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", HANMI), ("org", "ASE코리아"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Amkor코리아"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "삼성전기"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "삼성전자"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "LG이노텍"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "코리아써키트"), 0.82),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "SFA반도체"), 0.82),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "시그네틱스"), 0.82),
        ],
    },

    # ── XI. 단일판매·공급계약: HBM TC Bonder 수주 (한미→상대) ──
    "bccf402de937a11e": {  # 공급계약표: SK하이닉스(DUAL TC Bonder Griffin), Micron(DUAL TC BONDER TIGER)
        "entities": [
            (P, "dual tc bonder griffin", "Dual TC Bonder GRIFFIN"),
            (P, "dual tc bonder tiger", "Dual TC Bonder TIGER"),
        ],
        "edges": [
            E("SUPPLIES_TO", ("org", HANMI), ("org", "SK하이닉스"), 0.92),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Micron Technology"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "dual tc bonder griffin", "Dual TC Bonder GRIFFIN"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "dual tc bonder tiger", "Dual TC Bonder TIGER"), 0.92),
        ],
    },

    # ── XI. 특허침해 소송: 한미반도체 vs 한화세미텍 ─────────
    "319896a345517778": {  # 소송표: 원고 한미반도체, 피고 한화세미텍 (특허침해)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "한화세미텍"), 0.9, "특허침해 소송(원고)"),
        ],
    },

    # ── X. 대주주 등과의 거래: 관계기업·특수관계인 ──────────
    "7c2faa78014c3b99": {  # 거래표: 곽신홀딩스(관계기업) 유형자산 매입
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "곽신홀딩스"), 0.9, "관계기업(유형자산 매입거래)"),
        ],
    },

    # ── 연결/별도재무 주석: 종속·관계·기타특수관계자 ──────
    "9498af0407a1db67": {  # 종속기업표: Hanmi Vietnam(베트남, 반도체 제조장비 판매, 100%)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "Hanmi Vietnam Co., Ltd"), 0.92, "종속기업(100%)"),
        ],
    },
    "a895487d4751204e": {  # 종속기업투자 내역(Hanmi Taiwan/Vietnam 포함 연결대상)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "Hanmi Taiwan Co., Ltd"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "Hanmi Vietnam Co., Ltd"), 0.9, "종속기업"),
        ],
    },
    "ede3f2762c2e3d8d": {  # 별도재무: 종속(Hanmi Vietnam 100%)+관계기업(곽신홀딩스) 투자내역
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "Hanmi Vietnam Co., Ltd"), 0.9, "종속기업(100%)"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "곽신홀딩스"), 0.88, "관계기업"),
        ],
    },
    "551e4f1d58e2d835": {  # 관계기업투자 내역: 곽신홀딩스 49.00%
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "곽신홀딩스"), 0.92, "관계기업(49%)"),
        ],
    },
    "3d401e2847df46b0": {  # 특수관계자 목록: 관계기업 곽신홀딩스 / 기타특수관계자 한미인터내셔널, 도야인터내셔날
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "곽신홀딩스"), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "한미인터내셔널"), 0.9, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "도야인터내셔날"), 0.9, "그 밖의 특수관계자"),
        ],
    },
    "9ba32430149c308c": {  # 별도재무 특수관계자: 종속(Hanmi Taiwan/Vietnam), 관계(곽신홀딩스), 기타(한미인터내셔널, 도야인터내셔날)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "Hanmi Taiwan Co., Ltd"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "Hanmi Vietnam Co., Ltd"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "곽신홀딩스"), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "한미인터내셔널"), 0.88, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "도야인터내셔날"), 0.88, "그 밖의 특수관계자"),
        ],
    },
    "4c9fd689b727bb76": {  # 곽신홀딩스(구 한미컴퍼니) 관계기업 연혁 (한미네트웍스 흡수합병)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "곽신홀딩스"), 0.85, "관계기업"),
        ],
    },
}


def run():
    rows = get_chunks(WHERE)
    by_id = {r["chunk_id"]: r for r in rows}
    print(f"[batch] 청크 {len(rows)}건 (rcept {RCEPT})")

    done = ledger_processed_ids()
    print(f"[batch] 원장 기처리 {len(done)}건 — 스킵")

    driver = neo4j_driver()
    conn = mariadb_conn()

    n_ent_total = n_edge_total = n_prov_total = 0
    edge_by_type: dict[str, int] = {}
    processed = 0

    # 1) 추출 결과가 있는 청크
    for cid, payload in EXTRACTIONS.items():
        if cid in done:
            continue
        if cid not in by_id:
            print(f"  [warn] {cid} 대상에 없음 — 스킵")
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
        mark_processed(cid, n_ent, n_edge, row["section_path"])
        n_ent_total += n_ent
        n_edge_total += n_edge
        processed += 1

    # 2) 나머지 청크 = 엣지 0개 처리(누락 0)
    extracted_ids = set(EXTRACTIONS.keys())
    for r in rows:
        cid = r["chunk_id"]
        if cid in done or cid in extracted_ids:
            continue
        mark_processed(cid, 0, 0, r["section_path"])
        processed += 1

    conn.close()
    driver.close()

    total_marked = len(ledger_processed_ids())
    print("=== 한미반도체 2024 추출 결과 ===")
    print(f"  이번 처리 청크: {processed}  (원장 누적 {total_marked} / 대상 {len(rows)})")
    print(f"  엔티티(Product/Tech) hasObject: {n_ent_total}")
    print(f"  엣지 총: {n_edge_total}  타입별: {edge_by_type}")
    print(f"  provenance 행: {n_prov_total}")


def _match_and_id(driver, ref):
    if ref[0] == "org":
        org = resolve_org(ref[1])
        merge_org_node(driver, org)
        return {"kind": "org", "org": org}, org["id"]
    _, label, canonical, name = ref
    eid = merge_entity(driver, label, canonical, name)
    return {"kind": "entity", "label": label, "id": eid}, eid


if __name__ == "__main__":
    run()
