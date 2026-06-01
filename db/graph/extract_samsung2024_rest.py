"""B단계 비정형 추출 — 삼성전자 2024 사업보고서(rcept 20250311001085) '나머지' 청크.

파일럿(extract_pilot_samsung2024.py, II장+주석 242개) 이후 남은 청크 전부를
Claude(에이전트)가 직접 읽고 본문 근거로 판단한 엔티티·엣지를 멱등 적재한다.
대상 섹션: IV(MD&A), IX(계열회사), X(대주주 등 거래), XI(투자자 보호), V(감사인),
          (연결)감사보고서. 적재는 extract_helpers 멱등 헬퍼로 수행.

설계 근거 = docs/DBdocs/03_neo4j.md 비정형 섹션. 환각 금지(본문 근거 있을 때만).
- 지분율 교차표(IX 출자/피출자, 감사보고서 재무수치)는 정형 SSOT 영역 →
  Claude 비정형 추출 대상 아님(숫자·지분은 결정론 로더가 적재). no-edge 처리.
- 추출 대상: 산문으로 명시된 제품/기술/서비스(PRODUCES/USES_TECH),
  공급/매출 관계(SUPPLIES_TO), 명시적 특수관계자(RELATED_PARTY).

동시실행 충돌 방지: 공유 extract_ledger.jsonl 대신 문서별 원장
  db/graph/ledger/20250311001085.jsonl 에만 기록(아래 mark_processed 래핑).

실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_samsung2024_rest.py
모든 대상 청크는 엣지 0개여도 mark_processed(누락 0 보장).
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
    ledger_processed_ids,
    mariadb_conn,
    merge_entity,
    merge_org_node,
    neo4j_driver,
    resolve_org,
    write_provenance,
)

RCEPT = "20250311001085"
SAMSUNG = "삼성전자"  # resolve_org → corp_code 00126380

# ── 문서별 원장 (공유 원장 대신 이 파일에만 기록) ─────────────
DOC_LEDGER = Path(__file__).resolve().parent / "ledger" / f"{RCEPT}.jsonl"


def doc_mark_processed(chunk_id, n_ent, n_edge, rcept_no=None, section_path=None):
    """문서별 원장 append. extract_helpers.mark_processed 와 동일 스키마, 경로만 다름."""
    DOC_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "chunk_id": chunk_id, "n_ent": n_ent, "n_edge": n_edge,
        "rcept_no": rcept_no, "section_path": section_path,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with DOC_LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def doc_ledger_ids() -> set[str]:
    if not DOC_LEDGER.exists():
        return set()
    ids = set()
    for line in DOC_LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ids.add(json.loads(line)["chunk_id"])
        except Exception:
            continue
    return ids


P = "Product"
T = "Technology"


def E(rel, frm, to, conf, relation_type=None):
    d = {"rel": rel, "from": frm, "to": to, "conf": conf}
    if relation_type:
        d["relation_type"] = relation_type
    return d


# ── Claude 추출 결과 (청크별) ──────────────────────────────
# 본문에 명시적 근거가 있는 경우만. 숫자/지분 교차표는 제외(정형 SSOT).
EXTRACTIONS: dict[str, dict] = {

    # ── IV. 이사의 경영진단 및 분석의견 (MD&A) ──────────────
    "0ced6979fad988bd": {  # MX: Galaxy AI, Galaxy S24, Galaxy Z폴드6/플립6, 태블릿/워치/스마트링/무선이어폰, Samsung Wallet/Health, HVAC
        "entities": [
            (T, "galaxy ai", "Galaxy AI"),
            (P, "galaxy s24", "Galaxy S24"),
            (P, "galaxy z 폴드6", "Galaxy Z 폴드6"),
            (P, "galaxy z 플립6", "Galaxy Z 플립6"),
            (P, "스마트링", "스마트링"),
            (P, "hvac", "HVAC 시스템에어컨"),
            (P, "samsung wallet", "Samsung Wallet"),
            (P, "samsung health", "Samsung Health"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "galaxy ai", "Galaxy AI"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy s24", "Galaxy S24"), 0.92),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy z 폴드6", "Galaxy Z 폴드6"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy z 플립6", "Galaxy Z 플립6"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "스마트링", "스마트링"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "hvac", "HVAC 시스템에어컨"), 0.85),
        ],
    },
    "f0a3e79521e6d415": {  # Samsung Wallet, Samsung Health, Bixby, Galaxy S25, One UI 7.0
        "entities": [
            (P, "bixby", "Bixby"),
            (P, "galaxy s25", "Galaxy S25"),
            (T, "one ui 7.0", "One UI 7.0"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "bixby", "Bixby"), 0.82),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy s25", "Galaxy S25"), 0.88),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "one ui 7.0", "One UI 7.0"), 0.85),
        ],
    },
    "768896e91b615e59": {  # DS: HBM3E, HBM4, 서버향 DDR5, LPDDR5x, QLC SSD, V8/V9 NAND
        "entities": [
            (P, "hbm3e", "HBM3E"),
            (P, "hbm4", "HBM4"),
            (P, "ddr5", "DDR5"),
            (P, "lpddr5x", "LPDDR5x"),
            (P, "qlc ssd", "QLC SSD"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "hbm3e", "HBM3E"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "hbm4", "HBM4"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "ddr5", "DDR5"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "lpddr5x", "LPDDR5x"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "qlc ssd", "QLC SSD"), 0.85),
        ],
    },
    "6acbb3481e0852d5": {  # NAND V8/V9 공정전환, Foundry Advanced/Mature 노드, System LSI
        "entities": [
            (T, "foundry", "Foundry"),
            (P, "system lsi", "System LSI"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "foundry", "Foundry"), 0.82),
        ],
    },
    "1664d7414c6ff682": {  # 비전 AI, Galaxy S24, Galaxy Z폴드6/플립6, HBM, DDR5
        "entities": [
            (T, "비전 ai", "비전 AI"),
            (P, "hbm", "HBM"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "비전 ai", "비전 AI"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "hbm", "HBM"), 0.9),
        ],
    },
    "8e137b67ce9d82c5": {  # DX: Neo QLED, 마이크로 LED, AI 가전
        "entities": [
            (P, "neo qled", "Neo QLED"),
            (T, "마이크로 led", "마이크로 LED"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "neo qled", "Neo QLED"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", T, "마이크로 led", "마이크로 LED"), 0.85),
        ],
    },
    "f710aa3ebf81dc58": {  # Neo QLED, 마이크로 LED, OLED TV, 비전 AI, 클릭 투 서치/실시간 번역/생성형 배경화면
        "entities": [
            (P, "oled tv", "OLED TV"),
            (T, "비전 ai", "비전 AI"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "neo qled", "Neo QLED"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "oled tv", "OLED TV"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "비전 ai", "비전 AI"), 0.82),
        ],
    },
    "be6c4ac14d2d1858": {  # 생활가전 Bixby, SmartThings, HVAC
        "entities": [
            (T, "smartthings", "SmartThings"),
            (P, "bixby", "Bixby"),
            (P, "hvac", "HVAC 시스템에어컨"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "smartthings", "SmartThings"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "hvac", "HVAC 시스템에어컨"), 0.82),
        ],
    },
    "ab46b5235178de74": {  # SDC: QD-OLED TV, 스마트폰 패널, 모니터
        "entities": [
            (T, "qd-oled", "QD-OLED"),
            (P, "스마트폰 패널", "스마트폰 패널"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "qd-oled", "QD-OLED"), 0.82),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "스마트폰 패널", "스마트폰 패널"), 0.85),
        ],
    },
    "28252c9fb3a819a5": {  # Harman: 전장부품, 디지털콕핏, TCU, 카오디오, IVI, HUD → 완성차업체 공급
        "entities": [
            (P, "디지털 콕핏", "디지털 콕핏"),
            (P, "tcu", "TCU(Telematics Control Unit)"),
            (P, "카오디오", "카오디오"),
            (P, "차량용 디스플레이", "차량용 디스플레이"),
            (P, "hud", "HUD(Head Up Display)"),
        ],
        "edges": [
            # Harman = 삼성 종속(연결). 전장부품을 완성차 업체에 공급.
            E("PRODUCES", ("org", "Harman International Industries, Inc."), ("ent", P, "디지털 콕핏", "디지털 콕핏"), 0.85),
            E("PRODUCES", ("org", "Harman International Industries, Inc."), ("ent", P, "tcu", "TCU(Telematics Control Unit)"), 0.82),
            E("PRODUCES", ("org", "Harman International Industries, Inc."), ("ent", P, "카오디오", "카오디오"), 0.85),
            E("PRODUCES", ("org", "Harman International Industries, Inc."), ("ent", P, "차량용 디스플레이", "차량용 디스플레이"), 0.8),
            E("PRODUCES", ("org", "Harman International Industries, Inc."), ("ent", P, "hud", "HUD(Head Up Display)"), 0.8),
        ],
    },
    "e402f91d295eeac7": {  # Harman 소비자오디오 JBL 브랜드, Roon 기술 활용
        "entities": [
            (P, "jbl", "JBL"),
            (T, "roon", "Roon 음원재생기술"),
        ],
        "edges": [
            E("PRODUCES", ("org", "Harman International Industries, Inc."), ("ent", P, "jbl", "JBL"), 0.85),
            E("USES_TECH", ("org", "Harman International Industries, Inc."), ("ent", T, "roon", "Roon 음원재생기술"), 0.8),
        ],
    },
    "dd2825aabfc2be64": {  # 사업조직: DS부문 메모리/System LSI/Foundry, SDC 디스플레이 패널
        "entities": [
            (P, "system lsi", "System LSI"),
            (T, "foundry", "Foundry"),
        ],
        "edges": [],  # 조직개편 표 — 산문 제품화 근거 약함, 엔티티 anchor만
    },

    # ── X. 대주주 등과의 거래내용 (특수관계자/계열회사 명시) ──
    "69755e954f4957da": {  # 영업거래: SSI 반도체매출, SEA 스마트폰/가전, SSS 반도체, SEVT/SEV 스마트폰, SCS 반도체매입, SIEL
        "entities": [],
        "edges": [
            # SSI/SEA/SSS 등은 삼성 해외 계열·종속법인. 명시 '계열회사'.
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Semiconductor, Inc."), 0.85, "계열회사"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Electronics America, Inc."), 0.85, "계열회사"),
        ],
    },
    "69f39dcf9bab7f18": {  # SEA 통합채무보증, Cash Pooling 모법인(SEA,SEEH,SAPL,SCIC), SESS 자산매각, SSI 영업거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Electronics America, Inc."), 0.85, "계열회사"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Electronics Suzhou Semiconductor Co., Ltd."), 0.82, "계열회사"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Semiconductor, Inc."), 0.82, "계열회사"),
        ],
    },
    "016b5888739e4da7": {  # 협력업체 대여금: ㈜이랜텍, 대덕전자㈜
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "이랜텍"), 0.8, "협력업체"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "대덕전자"), 0.8, "협력업체"),
        ],
    },
    "b9d97d8ed53c84bc": {  # 채무보증: Harman 계열사들(Harman International Industries, AdGear Technologies)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Harman International Industries, Inc."), 0.85, "계열회사"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "AdGear Technologies Inc."), 0.8, "계열회사"),
        ],
    },

    # ── XI. 그 밖에 투자자 보호 (명시적 특수관계자/자회사) ──
    "5a21ffbfec134c41": {  # 삼성웰스토리 단체급식 거래, 삼성디스플레이 연대, 삼성카드
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성웰스토리"), 0.82, "특수관계자"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성디스플레이"), 0.85, "종속기업"),
        ],
    },
    "0b9b23f2c77ca3ad": {  # 자회사 (주)미래로시스템
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "미래로시스템"), 0.85, "자회사"),
        ],
    },
    "9c4afe6280835b24": {  # 삼성메디슨㈜ 수출 행정처분
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성메디슨"), 0.82, "종속기업"),
        ],
    },
    "80dbfac01574ffb7": {  # SDN 채무보증인=삼성디스플레이, SAS 채무보증인=SEA / 종속기업 삼성디스플레이
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성디스플레이"), 0.85, "종속기업"),
        ],
    },
    "fbcae817693231b3": {  # 사회공헌: 삼성복지재단/삼성생명공익재단/호암재단 등 출연(특수관계 재단)
        "entities": [],
        "edges": [],  # 기부금 출연 — 사업관계 아님(특수관계자 엣지 부적합), no-edge
    },

    # ── (연결)감사보고서: 명시적 특수관계자 거래표(산문 라벨) ──
    "0823ebdc13b787fb": {  # 별도 특수관계자 거래: 삼성에스디에스/삼성전기/삼성SDI/제일기획(관계기업), 삼성물산(그밖)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성에스디에스"), 0.88, "관계기업및공동기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성전기"), 0.88, "관계기업및공동기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성SDI"), 0.88, "관계기업및공동기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "제일기획"), 0.88, "관계기업및공동기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성물산"), 0.88, "그밖의특수관계자"),
        ],
    },
    "23c7f7f53a215430": {  # 별도 특수관계자 거래(전기): 동일 4사 + 삼성물산
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성에스디에스"), 0.85, "관계기업및공동기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성전기"), 0.85, "관계기업및공동기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성SDI"), 0.85, "관계기업및공동기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "제일기획"), 0.85, "관계기업및공동기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성물산"), 0.85, "그밖의특수관계자"),
        ],
    },
    "4cd1c019d652c2b7": {  # 연결 특수관계자 거래: 동일 4사 + 삼성물산
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성에스디에스"), 0.88, "관계기업및공동기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성전기"), 0.88, "관계기업및공동기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성SDI"), 0.88, "관계기업및공동기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "제일기획"), 0.88, "관계기업및공동기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성물산"), 0.88, "그밖의특수관계자"),
        ],
    },
    "5d6d71399c14aef8": {  # 연결 특수관계자 거래(전기): 동일 4사 + 삼성물산
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성에스디에스"), 0.85, "관계기업및공동기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성전기"), 0.85, "관계기업및공동기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성SDI"), 0.85, "관계기업및공동기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "제일기획"), 0.85, "관계기업및공동기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성물산"), 0.85, "그밖의특수관계자"),
        ],
    },
    "4e73c1212e30159e": {  # 삼성바이오로직스(관계기업)가 Biogen과 합작 → 삼성바이오에피스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성바이오로직스"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", "삼성바이오로직스"), ("org", "삼성바이오에피스"), 0.8, "종속기업"),
            E("RELATED_PARTY", ("org", "삼성바이오에피스"), ("org", "Biogen Therapeutics Inc."), 0.78, "합작투자"),
        ],
    },
    "8ae5e921288105bd": {  # 연결 관계기업 투자 장부가: 삼성전기/삼성에스디에스/삼성바이오로직스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성전기"), 0.85, "관계기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성에스디에스"), 0.85, "관계기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성바이오로직스"), 0.85, "관계기업"),
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
    # 대상 = 이 rcept 전체 - (공유원장 처리분 ∪ 문서원장 처리분)
    rows = get_chunks(f"WHERE rcept_no='{RCEPT}'")
    by_id = {r["chunk_id"]: r for r in rows}
    shared = ledger_processed_ids()
    docled = doc_ledger_ids()
    skip = shared | docled
    todo = [r for r in rows if r["chunk_id"] not in skip]
    print(f"[rest] rcept {RCEPT}: 전체 {len(rows)}, 공유원장 {len(shared & set(by_id))}, "
          f"문서원장 {len(docled)}, TODO {len(todo)}")

    driver = neo4j_driver()
    conn = mariadb_conn()

    n_ent_total = n_edge_total = n_prov_total = 0
    ent_by_label: dict[str, int] = {}
    edge_by_type: dict[str, int] = {}
    processed = 0

    todo_ids = {r["chunk_id"] for r in todo}

    # 1) 추출 결과가 있는 청크
    for cid, payload in EXTRACTIONS.items():
        if cid not in todo_ids:
            # 이미 처리됐거나(원장) 대상 아님 — 건너뜀(중복 방지)
            if cid not in by_id:
                print(f"  [warn] {cid} 이 rcept 청크 아님 — 스킵")
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
            ent_by_label[label] = ent_by_label.get(label, 0) + 1

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
        doc_mark_processed(cid, n_ent, n_edge, RCEPT, row["section_path"])
        n_ent_total += n_ent
        n_edge_total += n_edge
        processed += 1

    # 2) 나머지 TODO 청크는 엣지 0개로 처리 표시(누락 0)
    extracted = set(EXTRACTIONS.keys())
    skipped_zero = 0
    for r in todo:
        if r["chunk_id"] in extracted:
            continue
        doc_mark_processed(r["chunk_id"], 0, 0, RCEPT, r["section_path"])
        processed += 1
        skipped_zero += 1

    conn.close()
    driver.close()

    print("=== B단계 나머지 추출 결과 ===")
    print(f"  처리 청크: {processed} (엣지有 {processed - skipped_zero} / no-edge {skipped_zero})")
    print(f"  엔티티 hasObject: {n_ent_total}  라벨별: {ent_by_label}")
    print(f"  엣지 총: {n_edge_total}  타입별: {edge_by_type}")
    print(f"  provenance 행: {n_prov_total}")


if __name__ == "__main__":
    run()
