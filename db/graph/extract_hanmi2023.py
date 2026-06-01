"""배치 추출 적재 — 한미반도체 2023 사업보고서 (rcept 20240314001257, 772청크).

이 파일의 EXTRACTIONS = Claude(에이전트)가 청크 본문을 하나씩 읽고 본문 근거로
판단한 엔티티·엣지다. 결정론 코드가 아니라 언어이해 산출물 기록.
적재는 extract_helpers 멱등 헬퍼로 수행. 환각 금지 — 본문 명시·표 근거만.

한미반도체 = 반도체 후공정 장비 제조사(micro SAW, DUAL TC BONDER 등).
매출처=한미→상대(SUPPLIES_TO). 특수관계자(종속/관계기업)=RELATED_PARTY.
정형(지분·재무·임원겸직 수치표)은 제외 — 본문/분류 근거 비정형만.

원장 = db/graph/ledger/20240314001257.jsonl (이 rcept 전용, 공유 ledger 금지).
시작 시 원장 확인해 처리완료 청크 스킵. 대상 청크 전부 mark(0개여도) → 누락 0.

실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_hanmi2023.py
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

RCEPT = "20240314001257"
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
EXTRACTIONS: dict[str, dict] = {

    # ── II. 사업의 내용: 제품/기술 본문 ─────────────────────
    "d617fa870b571a95": {  # 1980설립, 주력장비 라인업 + micro SAW 국산화·세계1위
        "entities": [
            (P, "vision placement", "VISION PLACEMENT"),
            (P, "dual tc bonder", "DUAL TC BONDER"),
            (P, "flip chip bonder", "FLIP CHIP BONDER"),
            (P, "emi shield vision", "EMI Shield VISION ATTACH/DETACH"),
            (P, "camera module 장비", "CAMERA MODULE 조립/테스트 장비"),
            (P, "laser equipment", "LASER EQUIPMENT"),
            (P, "meta grinder", "META GRINDER"),
            (P, "tape saw", "TAPE SAW"),
            (P, "wafer saw", "Wafer SAW"),
            (P, "micro saw&vision placement", "micro SAW&VISION PLACEMENT"),
            (P, "micro saw", "micro SAW"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "vision placement", "VISION PLACEMENT"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "dual tc bonder", "DUAL TC BONDER"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "flip chip bonder", "FLIP CHIP BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield vision", "EMI Shield VISION ATTACH/DETACH"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "camera module 장비", "CAMERA MODULE 조립/테스트 장비"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "laser equipment", "LASER EQUIPMENT"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "meta grinder", "META GRINDER"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "tape saw", "TAPE SAW"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "wafer saw", "Wafer SAW"), 0.88),
            E("PRODUCES", ("org", HANMI), ("ent", P, "micro saw&vision placement", "micro SAW&VISION PLACEMENT"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "micro saw", "micro SAW"), 0.92),
        ],
    },
    "28b779b734e17ef7": {  # DUAL TC BONDER 2017 SK하이닉스 공동개발/공급, FLIP/MULTI/BIG DIE BONDER, EMI Shield, HBM
        "entities": [
            (P, "dual tc bonder", "DUAL TC BONDER"),
            (P, "flip chip bonder", "FLIP CHIP BONDER"),
            (P, "multi die bonder", "MULTI DIE BONDER"),
            (P, "big die bonder", "BIG DIE BONDER"),
            (P, "emi shield 장비", "EMI Shield 장비"),
            (T, "hbm", "HBM(광대역폭메모리)"),
            (T, "thermal compression bonding", "열압착(Thermal Compression) 본딩"),
            (T, "emi shield", "EMI Shield(전자기파 차폐)"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "dual tc bonder", "DUAL TC BONDER"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "flip chip bonder", "FLIP CHIP BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "multi die bonder", "MULTI DIE BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "big die bonder", "BIG DIE BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield 장비", "EMI Shield 장비"), 0.9),
            E("USES_TECH", ("org", HANMI), ("ent", T, "thermal compression bonding", "열압착(Thermal Compression) 본딩"), 0.9),
            E("USES_TECH", ("org", HANMI), ("ent", T, "hbm", "HBM(광대역폭메모리)"), 0.85),
            E("USES_TECH", ("org", HANMI), ("ent", T, "emi shield", "EMI Shield(전자기파 차폐)"), 0.85),
            # "2017년 SK하이닉스 사와 공동 개발하여 공급" 명시
            E("SUPPLIES_TO", ("org", HANMI), ("org", "SK하이닉스"), 0.9),
            E("RELATED_PARTY", ("org", HANMI), ("org", "SK하이닉스"), 0.85, "DUAL TC BONDER 공동개발(2017)"),
        ],
    },
    "963626fde264128c": {  # 28b779.. 와 동일 본문(중복 청크): DUAL TC BONDER SK하이닉스 공동개발
        "entities": [
            (P, "dual tc bonder", "DUAL TC BONDER"),
            (P, "flip chip bonder", "FLIP CHIP BONDER"),
            (P, "multi die bonder", "MULTI DIE BONDER"),
            (P, "big die bonder", "BIG DIE BONDER"),
            (P, "emi shield 장비", "EMI Shield 장비"),
            (T, "hbm", "HBM(광대역폭메모리)"),
            (T, "thermal compression bonding", "열압착(Thermal Compression) 본딩"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "dual tc bonder", "DUAL TC BONDER"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "flip chip bonder", "FLIP CHIP BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "multi die bonder", "MULTI DIE BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "big die bonder", "BIG DIE BONDER"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield 장비", "EMI Shield 장비"), 0.9),
            E("USES_TECH", ("org", HANMI), ("ent", T, "thermal compression bonding", "열압착(Thermal Compression) 본딩"), 0.9),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "SK하이닉스"), 0.9),
            E("RELATED_PARTY", ("org", HANMI), ("org", "SK하이닉스"), 0.85, "DUAL TC BONDER 공동개발(2017)"),
        ],
    },
    "fc7a40f7eac6b5ca": {  # 시장여건/경쟁: micro SAW&VISION PLACEMENT 세계1위, micro SAW 국산화, DUAL TC BONDER SK하이닉스 공동개발
        "entities": [
            (P, "micro saw&vision placement", "micro SAW&VISION PLACEMENT"),
            (P, "micro saw", "micro SAW"),
            (P, "dual tc bonder", "DUAL TC BONDER"),
            (T, "hbm", "HBM(광대역폭메모리)"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "micro saw&vision placement", "micro SAW&VISION PLACEMENT"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "micro saw", "micro SAW"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "dual tc bonder", "DUAL TC BONDER"), 0.92),
            E("USES_TECH", ("org", HANMI), ("ent", T, "hbm", "HBM(광대역폭메모리)"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "SK하이닉스"), 0.9),
            E("RELATED_PARTY", ("org", HANMI), ("org", "SK하이닉스"), 0.82, "DUAL TC BONDER 공동개발(2017)"),
        ],
    },
    "c9d4fe851ee9d105": {  # 연구개발 실적표: micro SAW 6종, EMI Shield 관련장비, TC BONDER(SK하이닉스 공동개발) DRAGON/GRIFFIN/CS/CW, FLIP CHIP BONDER
        "entities": [
            (P, "micro saw", "micro SAW"),
            (P, "emi shield 장비", "EMI Shield 관련장비"),
            (P, "dual tc bonder dragon", "Dual TC Bonder 1.0 DRAGON"),
            (P, "dual tc bonder griffin", "Dual TC Bonder 1.0 GRIFFIN"),
            (P, "tc bonder cs", "TC Bonder 1.0 CS"),
            (P, "tc bonder cw", "TC Bonder 1.0 CW"),
            (P, "flip chip bonder", "FLIP CHIP BONDER"),
            (T, "dual bonding", "DUAL Bonding 방식"),
            (T, "thermal compression bonding", "열압착(Thermal Compression) 본딩"),
            (T, "emi shield", "EMI Shield(전자기파 차폐)"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "micro saw", "micro SAW"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "emi shield 장비", "EMI Shield 관련장비"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "dual tc bonder dragon", "Dual TC Bonder 1.0 DRAGON"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "dual tc bonder griffin", "Dual TC Bonder 1.0 GRIFFIN"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "tc bonder cs", "TC Bonder 1.0 CS"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "tc bonder cw", "TC Bonder 1.0 CW"), 0.9),
            E("PRODUCES", ("org", HANMI), ("ent", P, "flip chip bonder", "FLIP CHIP BONDER"), 0.9),
            E("USES_TECH", ("org", HANMI), ("ent", T, "dual bonding", "DUAL Bonding 방식"), 0.88),
            E("USES_TECH", ("org", HANMI), ("ent", T, "thermal compression bonding", "열압착(Thermal Compression) 본딩"), 0.88),
            E("USES_TECH", ("org", HANMI), ("ent", T, "emi shield", "EMI Shield(전자기파 차폐)"), 0.85),
            # 표에 "SK하이닉스와 공동개발" 명시
            E("RELATED_PARTY", ("org", HANMI), ("org", "SK하이닉스"), 0.88, "Dual TC Bonder 공동개발"),
        ],
    },
    "bd25f3109f9d132c": {  # 매출표: 반도체 제조용 장비 外(HANMI), Conversion Kit 등
        "entities": [
            (P, "반도체 제조용 장비", "반도체 제조용 장비"),
            (P, "conversion kit", "Conversion Kit"),
        ],
        "edges": [
            E("PRODUCES", ("org", HANMI), ("ent", P, "반도체 제조용 장비", "반도체 제조용 장비"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "conversion kit", "Conversion Kit"), 0.88),
        ],
    },

    # ── II. 사업의 내용: 주요매출처(고객사) → SUPPLIES_TO (한미→고객) ──
    "fcb28910e3b3ceb6": {  # (4)주요매출처: ASE, AmKor, Infineon, ST Micro, SPIL, PTI, Skyworks / 중국 JCET, Huatian, TFME, SK하이닉스(충칭), Luxshare / 국내 JCET스태츠칩팩코리아, ASE코리아, Amkor코리아, SK하이닉스, 삼성전기, 삼성전자, LG이노텍, 코리아써키트, SFA반도체, 시그네틱스, 네패스
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", HANMI), ("org", "ASE"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Amkor"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Infineon"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "ST Micro"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "SPIL"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "PTI"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Skyworks"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "JCET"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "Huatian Technology"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "TFME"), 0.85),
            E("SUPPLIES_TO", ("org", HANMI), ("org", "SK하이닉스"), 0.9),
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
            E("SUPPLIES_TO", ("org", HANMI), ("org", "네패스"), 0.82),
        ],
    },

    # ── XI. 단일판매·공급계약: HBM TC Bonder 수주 (한미→SK하이닉스) ──
    "97d41c7854b2b49c": {  # 공급계약표: SK하이닉스 DUAL TC Bonder 1.0 DRAGON / GRIFFIN(2건) 수주
        "entities": [
            (P, "dual tc bonder dragon", "Dual TC Bonder 1.0 DRAGON"),
            (P, "dual tc bonder griffin", "Dual TC Bonder 1.0 GRIFFIN"),
            (P, "반도체 제조용 장비", "반도체 제조용 장비"),
        ],
        "edges": [
            E("SUPPLIES_TO", ("org", HANMI), ("org", "SK하이닉스"), 0.95),
            E("PRODUCES", ("org", HANMI), ("ent", P, "dual tc bonder dragon", "Dual TC Bonder 1.0 DRAGON"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "dual tc bonder griffin", "Dual TC Bonder 1.0 GRIFFIN"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "반도체 제조용 장비", "반도체 제조용 장비"), 0.9),
        ],
    },

    # ── IV. 경영진단: SK하이닉스 HBM 1위, DUAL TC BONDER 누적수주 ──
    "2d48fe3107bac285": {  # "전세계 HBM 1위 제조사인 SK하이닉스로부터 ... 누적 1,872억원 DUAL TC BONDER 수주"
        "entities": [
            (P, "dual tc bonder", "DUAL TC BONDER"),
            (T, "hbm", "HBM(광대역폭메모리)"),
        ],
        "edges": [
            E("SUPPLIES_TO", ("org", HANMI), ("org", "SK하이닉스"), 0.92),
            E("PRODUCES", ("org", HANMI), ("ent", P, "dual tc bonder", "DUAL TC BONDER"), 0.9),
            E("USES_TECH", ("org", HANMI), ("ent", T, "hbm", "HBM(광대역폭메모리)"), 0.85),
        ],
    },
    "203ae4715e862acd": {  # 재무상태: 당기 중 HPSP 평가이익 반영, 기타투자자산 급증 (HPSP 투자관계)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "HPSP"), 0.8, "투자기업(HPSP 평가이익)"),
        ],
    },

    # ── 특수관계자 목록: 종속·관계기업·기타특수관계자 (RELATED_PARTY) ──
    "29fc57aaf3a94068": {  # 특수관계자 목록표: 종속(Hanmi Taiwan/Vietnam), 관계(곽신홀딩스/한미네트웍스), 기타(한미인터내셔널)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "Hanmi Taiwan Co., Ltd"), 0.92, "종속기업"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "Hanmi Vietnam Co., Ltd"), 0.92, "종속기업"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "곽신홀딩스"), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "한미네트웍스"), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "한미인터내셔널"), 0.88, "기타특수관계자"),
        ],
    },
    "d34c68421b27afbf": {  # 연결주석 특수관계자 목록: 관계(곽신홀딩스/한미네트웍스), 기타(한미인터내셔널)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "곽신홀딩스"), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "한미네트웍스"), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "한미인터내셔널"), 0.88, "기타특수관계자"),
        ],
    },
    "7e41194a991a6702": {  # 종속기업 현황표: Hanmi Taiwan(대만, 반도체 제조장비 판매, 100%), Hanmi Vietnam(베트남, 100%)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "Hanmi Taiwan Co., Ltd"), 0.92, "종속기업(100%, 반도체 제조장비 판매)"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "Hanmi Vietnam Co., Ltd"), 0.92, "종속기업(100%, 반도체 제조장비 판매)"),
        ],
    },
    "b2fef6690baa9b00": {  # 종속회사 변동: Hanmi Vietnam 당기 신규 설립(동남아 영업력 강화)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "Hanmi Vietnam Co., Ltd"), 0.9, "종속기업(당기 신규설립)"),
        ],
    },
    "7636d5247a387161": {  # 특수관계자 거래(채권채무) 목록: 곽신홀딩스/한미네트웍스(관계), 한미인터내셔널(기타)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "곽신홀딩스"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "한미네트웍스"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "한미인터내셔널"), 0.85, "기타특수관계자"),
        ],
    },
    "262bb4cdc52c06b3": {  # 특수관계자 거래: 곽신홀딩스(관계), 한미인터내셔널(기타)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", HANMI), ("org", "곽신홀딩스"), 0.85, "관계기업"),
            E("RELATED_PARTY", ("org", HANMI), ("org", "한미인터내셔널"), 0.82, "기타특수관계자"),
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
    print("=== 한미반도체 2023 추출 결과 ===")
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
