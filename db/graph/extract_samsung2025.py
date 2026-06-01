"""비정형 관계 추출 적재 — 삼성전자 2025 사업보고서 (rcept 20260310002820, 799청크 전체).

이 파일의 EXTRACTIONS = Claude(에이전트)가 대상 rcept 의 청크 본문을 하나씩 읽고
본문 근거로 판단한 엔티티·엣지다. 결정론 코드가 아니라 언어이해 산출물의 기록.
적재 자체는 extract_helpers 의 멱등 헬퍼로 수행한다.

원장은 공유 extract_ledger.jsonl 대신 rcept 전용 ledger/20260310002820.jsonl 에만 기록
(동시실행 충돌 방지). 시작 시 그 원장을 확인해 처리완료 청크를 스킵하고, 대상 청크
전부를 mark_processed(엣지 0개여도) → 누락 0.

실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_samsung2025.py
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

RCEPT = "20260310002820"
SAMSUNG = "삼성전자"  # resolve_org → corp_code 00126380

# rcept 전용 원장 (공유 원장 금지)
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_PATH = LEDGER_DIR / f"{RCEPT}.jsonl"

P = "Product"
T = "Technology"


def E(rel, frm, to, conf, relation_type=None):
    d = {"rel": rel, "from": frm, "to": to, "conf": conf}
    if relation_type:
        d["relation_type"] = relation_type
    return d


# ── 전용 원장 헬퍼 (extract_helpers 의 공유 원장 대신 rcept 전용) ──
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
    "0de568ebc8ae9e00": {  # 부문별 주요 제품: TV/모니터/냉장고/세탁기/에어컨/스마트폰/네트워크시스템/PC, DRAM/NAND/모바일AP, OLED패널, 디지털콕핏/카오디오/포터블스피커
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
    "09790ee496fdddd5": {  # 부문 매출표: TV·모니터 / 스마트폰 / 메모리 / 디스플레이 패널
        "entities": [(P, "메모리", "메모리")],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "tv", "TV"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "스마트폰", "스마트폰"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "메모리", "메모리"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "oled 패널", "OLED 패널"), 0.88),
        ],
    },
    "6e93a1afbbf7f01b": {  # 주요제품: TV/냉장고/세탁기/에어컨/스마트폰 완제품, DRAM/NAND/모바일AP 반도체, OLED패널, Harman 디지털콕핏/카오디오/포터블스피커
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "스마트폰", "스마트폰"), 0.95),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "dram", "DRAM"), 0.95),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "nand flash", "NAND Flash"), 0.95),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "모바일ap", "모바일AP"), 0.92),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "디지털 콕핏", "디지털 콕핏"), 0.9),
        ],
    },
    "754379bc8298f56f": {  # Galaxy Z 플립7, Galaxy S25, Galaxy AI, One UI 7, ProVisual Engine, 태블릿/스마트워치/스마트링/무선이어폰, S Pen
        "entities": [
            (P, "galaxy z 플립7", "Galaxy Z 플립7"),
            (P, "galaxy s25", "Galaxy S25"),
            (T, "galaxy ai", "Galaxy AI"),
            (T, "one ui 7", "One UI 7"),
            (T, "프로비주얼 엔진", "프로비주얼 엔진(ProVisual Engine)"),
            (P, "태블릿", "태블릿"),
            (P, "스마트워치", "스마트워치"),
            (P, "스마트링", "스마트링"),
            (P, "무선이어폰", "무선이어폰"),
            (T, "s pen", "S Pen"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy z 플립7", "Galaxy Z 플립7"), 0.93),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "galaxy s25", "Galaxy S25"), 0.93),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "galaxy ai", "Galaxy AI"), 0.9),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "one ui 7", "One UI 7"), 0.88),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "프로비주얼 엔진", "프로비주얼 엔진(ProVisual Engine)"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "태블릿", "태블릿"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "스마트워치", "스마트워치"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "스마트링", "스마트링"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "무선이어폰", "무선이어폰"), 0.88),
        ],
    },
    "84f3d75fe7ad327d": {  # Galaxy Ecosystem, Samsung Wallet(舊 Samsung Pay), Samsung Health, Galaxy S25 재활용소재/배터리순환
        "entities": [
            (P, "samsung wallet", "Samsung Wallet"),
            (P, "samsung health", "Samsung Health"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "samsung wallet", "Samsung Wallet"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "samsung health", "Samsung Health"), 0.85),
        ],
    },
    "53ff89b525eeae17": {  # AI TV 라인업: Neo QLED, OLED, QLED, 더 프레임, Q시리즈 사운드바
        "entities": [
            (P, "neo qled", "Neo QLED"),
            (P, "qled", "QLED"),
            (P, "더 프레임", "더 프레임(The Frame)"),
            (P, "사운드바", "사운드바"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "neo qled", "Neo QLED"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "oled 패널", "OLED 패널"), 0.82),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "qled", "QLED"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "더 프레임", "더 프레임(The Frame)"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "사운드바", "사운드바"), 0.85),
        ],
    },
    "3578fe3217c9e68f": {  # TV 발전: 평면TV(LCD), 스마트TV, OLED, QLED, Micro LED, RGB; AI 화질 기술
        "entities": [
            (T, "마이크로 led", "마이크로 LED"),
            (T, "ai 화질 기술", "AI 화질 기술"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "마이크로 led", "마이크로 LED"), 0.82),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "ai 화질 기술", "AI 화질 기술"), 0.8),
        ],
    },
    "2514fc2c3aa53e09": {  # 반도체: 메모리(RAM/ROM), System LSI(CPU), 모바일 AP, 이미지센서, Foundry
        "entities": [
            (P, "이미지센서", "이미지 센서"),
            (T, "foundry", "Foundry"),
            (P, "system lsi", "System LSI"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "이미지센서", "이미지 센서"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "모바일ap", "모바일AP"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "system lsi", "System LSI"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "foundry", "Foundry"), 0.85),
        ],
    },
    "32e0203cf6f453b6": {  # V9 NAND, PCIe Gen6, 모바일 2나노 SOC→Galaxy S26, 2억화소 이미지센서, 모바일 DDI/OLED, Power
        "entities": [
            (P, "v9 nand", "V9 NAND"),
            (T, "2나노 공정", "2나노 공정"),
            (P, "galaxy s26", "Galaxy S26"),
            (P, "ddi", "DDI(디스플레이 구동 IC)"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "v9 nand", "V9 NAND"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "2나노 공정", "2나노 공정"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "이미지센서", "이미지 센서"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "ddi", "DDI(디스플레이 구동 IC)"), 0.82),
        ],
    },
    "9398ea793a86eec0": {  # 메모리시장: HBM4, 서버향 DRAM, NAND, KV SSD/PCIe Gen6 SSD, TLC
        "entities": [
            (P, "hbm4", "HBM4"),
            (P, "pcie gen6 ssd", "PCIe Gen6 SSD"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "hbm4", "HBM4"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "dram", "DRAM"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "nand flash", "NAND Flash"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "pcie gen6 ssd", "PCIe Gen6 SSD"), 0.82),
        ],
    },
    "5918ab61b9b0b62c": {  # Foundry 2나노/4나노 HBM4 Base-Die, SDC OLED/QD-OLED/TFT-LCD
        "entities": [
            (T, "qd-oled", "QD-OLED"),
            (T, "oled", "OLED"),
            (T, "tft-lcd", "TFT-LCD"),
            (P, "hbm4 base-die", "HBM4 Base-Die"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "2나노 공정", "2나노 공정"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "hbm4 base-die", "HBM4 Base-Die"), 0.82),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "qd-oled", "QD-OLED"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "oled", "OLED"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "tft-lcd", "TFT-LCD"), 0.82),
        ],
    },
    "4c4f2ceee88a9945": {  # Harman 디지털콕핏/카오디오, ADAS, SDV, 멀티브랜드 오디오
        "entities": [
            (T, "adas", "ADAS(첨단 운전자 보조 시스템)"),
            (T, "sdv", "SDV(Software Defined Vehicle)"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "디지털 콕핏", "디지털 콕핏"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "카오디오", "카오디오"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "adas", "ADAS(첨단 운전자 보조 시스템)"), 0.82),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "sdv", "SDV(Software Defined Vehicle)"), 0.8),
        ],
    },
    "707dab91969a59f4": {  # Harman 전장: 디지털콕핏/카오디오/텔레매틱스, AR HUD, 컨슈머오디오(TWS/포터블스피커/헤드폰)
        "entities": [
            (P, "텔레매틱스", "텔레매틱스"),
            (P, "ar hud", "AR HUD"),
            (P, "헤드폰", "헤드폰"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "텔레매틱스", "텔레매틱스"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "ar hud", "AR HUD"), 0.82),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "헤드폰", "헤드폰"), 0.82),
        ],
    },

    # ── II. 원재료/공급 (SUPPLIES_TO: 공급자 → 삼성) ─────────────
    "10e0996e92fb9b32": {  # 주요 원재료: 모바일AP/Camera Module ← Qualcomm·삼성전기 / 패널 ← CSOT / Chemical·Wafer ← 솔브레인·SILTRONIC / FPCA·Cover Glass ← 비에이치·Apple / SOC·통신모듈 ← NVIDIA·WNC
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "Qualcomm"), ("org", SAMSUNG), 0.88),
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
    "7638a2c690f51c67": {},  # 생산실적 표(제품 수량) — 추가 신규관계 없음(상위 표와 중복) → 0엣지
    "8437ed61cd3fb5fb": {  # 주요 매입처 표: CSOT/SDP, 삼성전기/엠씨넥스(Camera Module), 솔브레인/동우화인켐(Chemical), SILTRONIC/SK실트론(Wafer), 비에이치/SI FLEX(FPCA), Apple/LENS(Cover Glass)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "CSOT"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "SDP"), ("org", SAMSUNG), 0.82),
            E("SUPPLIES_TO", ("org", "삼성전기"), ("org", SAMSUNG), 0.9),
            E("SUPPLIES_TO", ("org", "엠씨넥스"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "솔브레인"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "동우화인켐"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "SILTRONIC"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "SK실트론"), ("org", SAMSUNG), 0.88),
            E("SUPPLIES_TO", ("org", "비에이치"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "SI FLEX"), ("org", SAMSUNG), 0.85),
            E("SUPPLIES_TO", ("org", "Apple"), ("org", SAMSUNG), 0.82),
            E("SUPPLIES_TO", ("org", "LENS"), ("org", SAMSUNG), 0.82),
        ],
    },

    # 주요 매출처 (SUPPLIES_TO: 삼성 → 수요자)
    # (CID 6e93a1afbbf7f01b 본문에도 매출처 언급되나, 제품 엣지 청크라 매출처는 별도 anchor.)
    "8c9ef6b204449caa": {},  # (없는 청크면 run에서 자동 skip)

    # ── 수주: Foundry 위탁생산 (SUPPLIES_TO: 삼성 → Tesla) ──────
    "25bb829f753ee21c": {  # DS Foundry — Tesla 반도체 위탁생산 수주(16,544백만달러)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "Tesla"), 0.9),
        ],
    },

    # ── 특허 라이선스 / 인수 (RELATED_PARTY) ───────────────────
    "8b5cbbc3c1fc826b": {  # 특허 라이선스: Google, Nokia, Qualcomm, Huawei
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Google"), 0.82, "특허라이선스"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Nokia"), 0.82, "특허라이선스"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Qualcomm"), 0.82, "특허라이선스"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Huawei"), 0.82, "특허라이선스"),
        ],
    },
    "752c25213f3b5ecc": {  # Harman, Sound United(B&W/Denon/Marantz) 2025 3분기 인수
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "Harman"), ("org", "Sound United"), 0.85, "인수(2025)"),
        ],
    },

    # ── II/주석: 옵션·주주간계약 (RELATED_PARTY) ───────────────
    "20d34660002d6c47": {  # 레인보우로보틱스 콜옵션, 삼성디스플레이-Corning 풋옵션, TCL/CSOT 풋옵션, 삼성디스플레이 주식선도
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "레인보우로보틱스"), 0.85, "지분인수(콜옵션)"),
            E("RELATED_PARTY", ("org", "삼성디스플레이"), ("org", "Corning"), 0.8, "지분보유(풋옵션)"),
            E("RELATED_PARTY", ("org", "삼성디스플레이"), ("org", "CSOT"), 0.78, "지분보유(풋옵션)"),
        ],
    },
    "2621b346a61a84e7": {  # 삼성디스플레이 주식선도계약(당사 보통주 기초)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성디스플레이"), 0.85, "종속기업"),
        ],
    },

    # ── 사업결합/소송 (RELATED_PARTY) ──────────────────────────
    "3de185b2d93150e2": {  # 레인보우로보틱스 콜옵션 행사 완료 → 관계기업→종속기업, AI/SW+로봇기술 접목
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "레인보우로보틱스"), 0.9, "종속기업(사업결합)"),
        ],
    },
    "c0a6ea9ca43188c4": {  # (별도) 레인보우로보틱스 콜옵션 행사 완료 → 관계기업→종속기업 재분류
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "레인보우로보틱스"), 0.88, "종속기업(재분류)"),
        ],
    },
    "4776d264b6a098ec": {  # 삼성바이오로직스(관계기업), Biogen 합작 삼성바이오에피스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성바이오로직스"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", "삼성바이오로직스"), ("org", "삼성바이오에피스"), 0.85, "합작투자"),
            E("RELATED_PARTY", ("org", "삼성바이오에피스"), ("org", "Biogen"), 0.8, "합작투자"),
        ],
    },
    "738365bb47144438": {  # (연결) 삼성바이오로직스 관계기업, Biogen 합작 삼성바이오에피스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성바이오로직스"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", "삼성바이오에피스"), ("org", "Biogen"), 0.8, "합작투자"),
        ],
    },
    "062c67d55ef4b200": {  # (연결) 삼성바이오로직스 관계기업, 삼성바이오에피스 지분 회계처리
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성바이오로직스"), 0.85, "관계기업"),
        ],
    },
    "61a78fe5a597fff3": {  # (III연결주석) 삼성바이오로직스 관계기업, 삼성바이오에피스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성바이오로직스"), 0.85, "관계기업"),
        ],
    },

    # ── 연결회사 개요: 지배회사·종속·관계기업 (RELATED_PARTY) ──
    "55a4e54884a48cf9": {  # (III연결) 삼성디스플레이·SEA 308 종속기업, 삼성전기 등 33 관계기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성디스플레이"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Electronics America"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성전기"), 0.85, "관계기업및공동기업"),
        ],
    },
    "b0c93d20dcf66259": {  # (연결감사) 삼성디스플레이·SEA 308 종속기업, 삼성전기 등 33 관계기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성디스플레이"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Electronics America"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성전기"), 0.85, "관계기업및공동기업"),
        ],
    },

    # ── 특수관계자 분류 표 (RELATED_PARTY, relation_type 명시) ──
    # 동일한 분류 머리표가 여러 청크에 반복 — 각 청크에 동일 근거로 적재(멱등).
    "162c4d18a1b0cb02": {"entities": [], "edges": [
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성에스디에스"), 0.9, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성전기"), 0.9, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성SDI"), 0.9, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "제일기획"), 0.9, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성물산"), 0.9, "그밖의특수관계자"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성이앤에이"), 0.88, "대규모기업집단"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "에스원"), 0.88, "대규모기업집단"),
    ]},
    "25a3cb79dcb3d5db": {"entities": [], "edges": [
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성에스디에스"), 0.9, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성전기"), 0.9, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성SDI"), 0.9, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "제일기획"), 0.9, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성물산"), 0.9, "그밖의특수관계자"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성이앤에이"), 0.88, "대규모기업집단"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "에스원"), 0.88, "대규모기업집단"),
    ]},
    "5d31538dafa56757": {"entities": [], "edges": [
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성에스디에스"), 0.9, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성전기"), 0.9, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성SDI"), 0.9, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "제일기획"), 0.9, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성물산"), 0.9, "그밖의특수관계자"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성이앤에이"), 0.88, "대규모기업집단"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "에스원"), 0.88, "대규모기업집단"),
    ]},
    "294536ed31bc373e": {"entities": [], "edges": [  # 종속기업 표: 삼성디스플레이·SEA·SAPL·SAS·SSI·Harman·SCS·SCIC
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성디스플레이"), 0.9, "종속기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Electronics America"), 0.88, "종속기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Semiconductor"), 0.85, "종속기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Harman"), 0.85, "종속기업"),
    ]},
    "4ae0c4c3d8012785": {"entities": [], "edges": [  # 종속기업 표(별도주석)
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성디스플레이"), 0.9, "종속기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Electronics America"), 0.88, "종속기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Semiconductor"), 0.85, "종속기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Harman"), 0.85, "종속기업"),
    ]},
    "8e5d914127570728": {"entities": [], "edges": [  # 종속기업 표(별도주석)
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성디스플레이"), 0.9, "종속기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Electronics America"), 0.88, "종속기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Semiconductor"), 0.85, "종속기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Harman"), 0.85, "종속기업"),
    ]},

    # ── 특수관계자 매출·매입 / 채권·채무 표 (RELATED_PARTY + SUPPLIES_TO 방향) ──
    # 매출>매입 단정 불가(쌍방거래)이므로 SUPPLIES_TO는 명확한 일방이 아닌 경우 생략, RELATED_PARTY로.
    "011e0403c8b36735": {"entities": [], "edges": [  # 매출/매입 표(별도): 삼성에스디에스/삼성전기/삼성SDI/제일기획/삼성물산/삼성이앤에이
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성에스디에스"), 0.88, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성전기"), 0.88, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성SDI"), 0.88, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "제일기획"), 0.88, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성물산"), 0.88, "그밖의특수관계자"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성이앤에이"), 0.85, "대규모기업집단"),
    ]},
    "755de34cf61e40b3": {"entities": [], "edges": [  # 매출/매입 표(별도 전기)
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성에스디에스"), 0.86, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성전기"), 0.86, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성SDI"), 0.86, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "제일기획"), 0.86, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성물산"), 0.86, "그밖의특수관계자"),
    ]},
    "9063906a736fc414": {"entities": [], "edges": [  # 매출/매입 표(연결): 삼성에스디에스/삼성전기/삼성SDI/제일기획/삼성물산/삼성이앤에이
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성에스디에스"), 0.88, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성전기"), 0.88, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성SDI"), 0.88, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "제일기획"), 0.88, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성물산"), 0.88, "그밖의특수관계자"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성이앤에이"), 0.85, "대규모기업집단"),
    ]},
    "09989d029aaf3aa9": {"entities": [], "edges": [  # 채권/채무 표(별도): + 에스원
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성에스디에스"), 0.86, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성전기"), 0.86, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성SDI"), 0.86, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "제일기획"), 0.86, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성물산"), 0.86, "그밖의특수관계자"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성이앤에이"), 0.85, "대규모기업집단"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "에스원"), 0.85, "대규모기업집단"),
    ]},
    "756fd92aa368a405": {"entities": [], "edges": [  # 채권/채무 표(별도 전기)
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성에스디에스"), 0.85, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성전기"), 0.85, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성SDI"), 0.85, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "제일기획"), 0.85, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성물산"), 0.85, "그밖의특수관계자"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성이앤에이"), 0.82, "대규모기업집단"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "에스원"), 0.82, "대규모기업집단"),
    ]},
    "680b31316fbccb7e": {"entities": [], "edges": [  # 채권/채무 표(연결): + 에스원
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성에스디에스"), 0.86, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성전기"), 0.86, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성SDI"), 0.86, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "제일기획"), 0.86, "관계기업및공동기업"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성물산"), 0.86, "그밖의특수관계자"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성이앤에이"), 0.85, "대규모기업집단"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "에스원"), 0.85, "대규모기업집단"),
    ]},

    # ── X. 대주주 거래: 영업거래 매출/매입 방향 (SUPPLIES_TO) ───
    "e0b07b772df4c716": {"entities": [], "edges": [  # SSI/SSS 반도체 매출(삼성→), SCS 반도체 매입(→삼성); SEA/SEVT/SEV 스마트폰 매출입(혼합→RELATED_PARTY)
        E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "Samsung Semiconductor"), 0.85),
        E("SUPPLIES_TO", ("org", "Samsung China Semiconductor"), ("org", SAMSUNG), 0.82),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Electronics America"), 0.85, "계열회사(영업거래)"),
    ]},
    "4471585ac2712320": {"entities": [], "edges": [  # SEA 채무보증, SCS 자산매각, SSI 영업거래
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Electronics America"), 0.85, "계열회사(채무보증)"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung China Semiconductor"), 0.85, "계열회사(자산양수도)"),
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Semiconductor"), 0.85, "계열회사(영업거래)"),
    ]},
    "0b8a4bf0d00978ee": {"entities": [], "edges": [  # 채무보증 표: Harman International Industries 계열회사
        E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Harman"), 0.85, "계열회사(채무보증)"),
    ]},
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

    # 1) 추출 결과가 있는 청크
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

    # 2) 나머지 대상 청크는 엣지 0개로 처리 표시 (누락 0 보장)
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
    print("=== 삼성전자 2025 비정형 추출 결과 ===")
    print(f"  이번 실행 처리 청크: {processed}  (기처리 스킵 {skipped})")
    print(f"  원장 누적 처리 청크: {total_done} / {len(rows)}")
    print(f"  엔티티(Product/Tech) hasObject: {n_ent_total}")
    print(f"  엣지 총: {n_edge_total}  타입별: {edge_by_type}")
    print(f"  provenance 행: {n_prov_total}")


if __name__ == "__main__":
    run()
