"""비정형 관계 추출 적재 — 삼성전자 2025년 1분기 분기보고서 (rcept 20250515001922, 197청크).

EXTRACTIONS = Claude(에이전트)가 대상 rcept 의 청크 본문을 하나씩 읽고 본문 근거로
판단한 엔티티·엣지. 적재는 extract_helpers 의 멱등 헬퍼로 수행.

원장은 공유 extract_ledger.jsonl 대신 rcept 전용 ledger/20250515001922.jsonl 에만 기록.
시작 시 그 원장을 확인해 처리완료 청크를 스킵하고, 대상 청크 전부를 mark_processed
(엣지 0개여도) → 누락 0. 정형 재무제표 표는 제외, 본문 근거 있는 비정형만.

실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_samsung_q_20250515001922.py
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

RCEPT = "20250515001922"
SAMSUNG = "삼성전자"  # resolve_org → corp_code 00126380

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

    # ── II. 사업의 내용 — 제품/기술 (PRODUCES / USES_TECH) ──────
    "e47c9de323473660": {  # 회사 개요: DX(TV/모니터/냉장고/세탁기/에어컨/스마트폰/네트워크시스템/PC), DS(DRAM/NAND/모바일AP), SDC(OLED패널), Harman(디지털콕핏/카오디오/포터블스피커)
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
    "add617c73ff2e561": {  # 부문별 주요제품 표: DX TV·모니터·냉장고…, DS DRAM/NAND/모바일AP, SDC OLED패널, Harman 디지털콕핏/카오디오/포터블스피커
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
    "bb550bb47fb49593": {  # SDC OLED패널, Harman 디지털콕핏/카오디오/포터블스피커 생산판매
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "oled 패널", "OLED 패널"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "디지털 콕핏", "디지털 콕핏"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "카오디오", "카오디오"), 0.86),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "포터블 스피커", "포터블 스피커"), 0.86),
        ],
    },
    "1015ac9496af5117": {  # ProVisual Engine, 태블릿/스마트워치/스마트링/무선이어폰, Galaxy Ecosystem, Samsung Wallet/Health, S Pen
        "entities": [
            (T, "프로비주얼 엔진", "프로비주얼 엔진(ProVisual Engine)"),
            (P, "태블릿", "태블릿"), (P, "스마트워치", "스마트워치"),
            (P, "스마트링", "스마트링"), (P, "무선이어폰", "무선이어폰"),
            (T, "s pen", "S Pen"),
            (P, "samsung wallet", "Samsung Wallet"),
            (P, "samsung health", "Samsung Health"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "프로비주얼 엔진", "프로비주얼 엔진(ProVisual Engine)"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "태블릿", "태블릿"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "스마트워치", "스마트워치"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "스마트링", "스마트링"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "무선이어폰", "무선이어폰"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "samsung wallet", "Samsung Wallet"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "samsung health", "Samsung Health"), 0.85),
        ],
    },
    "e59e382c49c43bf3": {  # Galaxy Z 폴드/플립, Galaxy S25 시리즈, Galaxy AI, One UI 7
        "entities": [
            (P, "galaxy z 플립", "Galaxy Z 플립"),
            (P, "galaxy z 폴드", "Galaxy Z 폴드"),
            (P, "galaxy s25", "Galaxy S25"),
            (T, "galaxy ai", "Galaxy AI"),
            (T, "one ui 7", "One UI 7"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy z 플립", "Galaxy Z 플립"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy z 폴드", "Galaxy Z 폴드"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy s25", "Galaxy S25"), 0.93),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "galaxy ai", "Galaxy AI"), 0.9),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "one ui 7", "One UI 7"), 0.88),
        ],
    },
    "7c46c77d3b6b2dcb": {  # 연구개발 표: Galaxy S25/A/북, Neo QLED 8K/4K
        "entities": [
            (P, "neo qled", "Neo QLED"),
            (P, "galaxy 북", "Galaxy 북"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy s25", "Galaxy S25"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy 북", "Galaxy 북"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "neo qled", "Neo QLED"), 0.9),
        ],
    },
    "c7f40f9f508abe7e": {  # AI TV 라인업: Neo QLED, OLED, QLED, 더 프레임
        "entities": [
            (P, "qled", "QLED"),
            (P, "더 프레임", "더 프레임(The Frame)"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "neo qled", "Neo QLED"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "oled 패널", "OLED 패널"), 0.82),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "qled", "QLED"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "더 프레임", "더 프레임(The Frame)"), 0.88),
        ],
    },
    "21628eecebaff992": {  # Q시리즈 사운드바, 컨버터블 사운드바, 더 프레임, Neo QLED/QLED, 더 프리미어 5(프로젝터)
        "entities": [
            (P, "사운드바", "사운드바"),
            (P, "프로젝터", "프로젝터"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "사운드바", "사운드바"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "프로젝터", "프로젝터"), 0.82),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "더 프레임", "더 프레임(The Frame)"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "neo qled", "Neo QLED"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "qled", "QLED"), 0.85),
        ],
    },
    "8928fad7ea83bc0b": {  # TV 기술: 마이크로 LED, Neo QLED, OLED, AI 화질 기술
        "entities": [
            (T, "마이크로 led", "마이크로 LED"),
            (T, "ai 화질 기술", "AI 화질 기술"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "마이크로 led", "마이크로 LED"), 0.82),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "ai 화질 기술", "AI 화질 기술"), 0.8),
        ],
    },
    "5c8401fd39d0af5a": {  # 반도체: 메모리(RAM/ROM), System LSI(CPU/GPU)
        "entities": [(P, "system lsi", "System LSI")],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "system lsi", "System LSI"), 0.85),
        ],
    },
    "553c9abb65a326c8": {  # System LSI/모바일AP/이미지센서, Foundry 위탁생산, 서버향 DRAM/SSD
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
    "4551a9c803de86aa": {  # System LSI, SOC(Galaxy S24/A55), 이미지센서 2억화소, DDI(OLED/LCD), Power, Foundry 4/3/2나노
        "entities": [
            (P, "ddi", "DDI(디스플레이 구동 IC)"),
            (T, "2나노 공정", "2나노 공정"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "system lsi", "System LSI"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "이미지센서", "이미지 센서"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "ddi", "DDI(디스플레이 구동 IC)"), 0.82),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "foundry", "Foundry"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "2나노 공정", "2나노 공정"), 0.82),
        ],
    },
    "c4e66e8f9fd037ba": {  # 메모리: HBM3E, 서버향 DRAM, NAND V8
        "entities": [(P, "hbm3e", "HBM3E")],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "hbm3e", "HBM3E"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "dram", "DRAM"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "nand flash", "NAND Flash"), 0.85),
        ],
    },
    "cc4db3e20d8b661d": {  # OLED, QD-OLED, TFT-LCD 디스플레이 기술
        "entities": [
            (T, "qd-oled", "QD-OLED"),
            (T, "oled", "OLED"),
            (T, "tft-lcd", "TFT-LCD"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "oled", "OLED"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "qd-oled", "QD-OLED"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "tft-lcd", "TFT-LCD"), 0.82),
        ],
    },
    "222cf71440fa88dc": {  # Harman 전장: 디지털콕핏/카오디오/텔레매틱스, SDV, AR HUD
        "entities": [
            (P, "텔레매틱스", "텔레매틱스"),
            (T, "sdv", "SDV(Software Defined Vehicle)"),
            (P, "ar hud", "AR HUD"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "디지털 콕핏", "디지털 콕핏"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "카오디오", "카오디오"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "텔레매틱스", "텔레매틱스"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "ar hud", "AR HUD"), 0.82),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "sdv", "SDV(Software Defined Vehicle)"), 0.8),
        ],
    },
    "3fe710378df41127": {  # 라이프스타일 오디오: TWS, 포터블스피커, 헤드폰
        "entities": [
            (P, "tws", "TWS(True Wireless Stereo)"),
            (P, "헤드폰", "헤드폰"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "tws", "TWS(True Wireless Stereo)"), 0.82),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "포터블 스피커", "포터블 스피커"), 0.82),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "헤드폰", "헤드폰"), 0.82),
        ],
    },

    # ── II. 원재료/공급 (SUPPLIES_TO: 공급자 → 삼성) ─────────────
    "bb550bb47fb49593_dup": {},  # placeholder (실재 chunk 아님 — run에서 skip)
    "46465ac95d49a864": {  # Harman 원재료: SOC/통신모듈 ← NVIDIA, WNC
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "NVIDIA"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "WNC"), ("org", SAMSUNG), 0.8),
        ],
    },
    "3907c31f097f2085": {  # 주요 매입처 표: 모바일AP ← Qualcomm/MediaTek, 패널 ← CSOT/AUO, Camera ← 삼성전기/SUNNY, Chemical ← 솔브레인/동우화인켐, Wafer ← SILTRONIC/SK실트론
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "Qualcomm"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "MediaTek"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "CSOT"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "AUO"), ("org", SAMSUNG), 0.82),
            E("SUPPLIES_TO", ("org", "삼성전기"), ("org", SAMSUNG), 0.9),
            E("SUPPLIES_TO", ("org", "SUNNY"), ("org", SAMSUNG), 0.82),
            E("SUPPLIES_TO", ("org", "솔브레인"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "동우화인켐"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "SILTRONIC"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "SK실트론"), ("org", SAMSUNG), 0.88),
        ],
    },

    # ── 특허 라이선스 (RELATED_PARTY) ───────────────────────────
    "381b31011f39d31a": {  # 특허 라이선스: Google, Ericsson, Qualcomm, Huawei, Nokia
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Google"), 0.85, "특허라이선스"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Ericsson"), 0.85, "특허라이선스"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Qualcomm"), 0.85, "특허라이선스"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Huawei"), 0.85, "특허라이선스"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Nokia"), 0.85, "특허라이선스"),
        ],
    },
    "1bf752ac25ae8446": {  # 경영상 주요계약 표: Google 상호특허/EMADA, GlobalFoundries 공정기술 라이선스, Ericsson 상호특허
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Google"), 0.88, "상호특허사용계약"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "GlobalFoundries"), 0.85, "공정기술라이선스"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Ericsson"), 0.85, "상호특허사용계약"),
        ],
    },

    # ── 옵션·주주간계약 / 사업결합 (RELATED_PARTY) ─────────────
    "53123833becaf9df": {  # 레인보우로보틱스 콜옵션 행사완료(지분인수), 삼성디스플레이-Corning 풋옵션, TCL/CSOT 풋옵션
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "레인보우로보틱스"), 0.88, "지분인수(콜옵션행사)"),
            E("RELATED_PARTY", ("org", "삼성디스플레이"), ("org", "Corning"), 0.8, "지분보유(풋옵션)"),
            E("RELATED_PARTY", ("org", "삼성디스플레이"), ("org", "CSOT"), 0.78, "지분보유(풋옵션)"),
        ],
    },
    "e3ef9f516cf22e5d": {  # 삼성디스플레이-TCL 풋옵션(CSOT 지분), 한영회계법인 평가
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성디스플레이"), ("org", "TCL"), 0.78, "지분매각권(풋옵션)"),
        ],
    },
    "075c93a409915ae8": {  # Harman, Roon Labs LLC 2023.4Q 인수
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "Harman"), ("org", "Roon Labs"), 0.85, "인수(2023)"),
        ],
    },

    # ── 회사 개요: 종속기업 (RELATED_PARTY 종속관계) ───────────
    "d78101657ca40037": {  # 미주 종속: SEA, SII, SSI, SAS, SEDA, Harman
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Electronics America"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Semiconductor"), 0.85, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Harman"), 0.85, "종속기업"),
        ],
    },
    "e47c9de323473660_subs": {},  # placeholder skip

    # ── X. 대주주 등과의 거래 (RELATED_PARTY / SUPPLIES_TO) ─────
    "b6cbbc0aa060538f": {  # 채무보증 SEA, 자산양수도 SCS, 영업거래 SSI
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Electronics America"), 0.85, "계열회사(채무보증)"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung China Semiconductor"), 0.85, "계열회사(자산양수도)"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Semiconductor"), 0.85, "계열회사(영업거래)"),
        ],
    },
    "51d9e042436dabae": {  # SSI 반도체 매출 등 (삼성→SSI)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "Samsung Semiconductor"), 0.85),
        ],
    },
    "7e7bad8f903286ff": {  # 자산매각/매입 표: SCS, SESS, SEVT, SEHC
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung China Semiconductor"), 0.85, "계열회사(자산양수도)"),
        ],
    },
    "7c6c92974b94ffac": {  # 채무보증 표: AdGear, Harman International Industries, Harman International Japan
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Harman"), 0.85, "계열회사(채무보증)"),
        ],
    },
    "e66a6d42cf2cda55": {  # 채무보증 표: SEA, SEM, SAMCOL
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Electronics America"), 0.85, "계열회사(채무보증)"),
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
            continue  # placeholder/존재하지 않는 청크 — skip
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
    print(f"=== 삼성전자 2025 1분기 ({RCEPT}) 비정형 추출 결과 ===")
    print(f"  이번 실행 처리 청크: {processed}  (기처리 스킵 {skipped})")
    print(f"  원장 누적 처리 청크: {total_done} / {len(rows)}")
    print(f"  엔티티 hasObject: {n_ent_total}")
    print(f"  엣지 총: {n_edge_total}  타입별: {edge_by_type}")
    print(f"  provenance 행: {n_prov_total}")


if __name__ == "__main__":
    run()
