"""B단계 비정형 추출 — 삼성전자 2023 사업보고서(rcept 20240312000736) 전체 655청크.

Claude(에이전트)가 청크 본문을 직접 읽고 본문 근거로 판단한 엔티티·엣지를 멱등 적재한다.
대상 = chunk_index WHERE rcept_no='20240312000736' 전체(655). 엣지有 청크는 아래 EXTRACTIONS,
나머지(IX 지분 교차표·감사보고서 재무수치 등 정형 SSOT 영역)는 no-edge 처리(누락 0 보장).

설계 근거 = docs/DBdocs/03_neo4j.md 비정형. 환각 금지(본문 명시 근거 있을 때만).
- 지분율 교차표(IX), 감사보고서 재무수치, 임원 겸직은 정형 SSOT → 비정형 추출 제외(no-edge).
- 추출 대상: 산문/표로 명시된 제품·기술(PRODUCES/USES_TECH), 매입처·매출처(SUPPLIES_TO,
  공급자→수요자 방향), 명시적 특수관계자·계열회사(RELATED_PARTY), Chunk→엔티티(hasObject).

동시실행 충돌 방지: 공유 extract_ledger.jsonl 대신 문서별 원장
  db/graph/ledger/20240312000736.jsonl 에만 기록. 시작 시 (공유∪문서) 원장 확인해 처리완료 스킵.

실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_samsung2023.py
멱등 — 재실행해도 중복 적재 없음(MERGE + 결정론 prov_id + 원장 스킵).
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

RCEPT = "20240312000736"
SAMSUNG = "삼성전자"  # resolve_org → corp_code 00126380
HARMAN = "Harman International Industries, Inc."  # 삼성 종속(연결)
SDC = "삼성디스플레이"  # 종속기업
P = "Product"
T = "Technology"

DOC_LEDGER = Path(__file__).resolve().parent / "ledger" / f"{RCEPT}.jsonl"


def doc_mark_processed(chunk_id, n_ent, n_edge, rcept_no=None, section_path=None):
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


def E(rel, frm, to, conf, relation_type=None):
    d = {"rel": rel, "from": frm, "to": to, "conf": conf}
    if relation_type:
        d["relation_type"] = relation_type
    return d


# ── Claude 추출 결과 (청크별) ──────────────────────────────
# 본문 명시 근거 기반. 숫자/지분 교차표는 제외(정형 SSOT).
EXTRACTIONS: dict[str, dict] = {

    # ── II. 사업의 내용 — 제품/기술 (산문·표 명시) ──────────────
    "072bd3981d99081c": {  # 디스플레이: OLED, TFT-LCD, QD-OLED
        "entities": [(T, "oled", "OLED"), (T, "tft-lcd", "TFT-LCD"), (T, "qd-oled", "QD-OLED")],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "oled", "OLED"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "qd-oled", "QD-OLED"), 0.85),
        ],
    },
    "0848c931388bd3de": {  # 생산실적 표: TV·모니터, 스마트폰, 메모리, 디스플레이 패널, 디지털 콕핏
        "entities": [
            (P, "tv", "TV"), (P, "스마트폰", "스마트폰"), (P, "메모리", "메모리"),
            (P, "디스플레이 패널", "디스플레이 패널"), (P, "디지털 콕핏", "디지털 콕핏"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "tv", "TV"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "스마트폰", "스마트폰"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "메모리", "메모리"), 0.88),
            E("PRODUCES", ("org", SDC), ("ent", P, "디스플레이 패널", "디스플레이 패널"), 0.85),
            E("PRODUCES", ("org", HARMAN), ("ent", P, "디지털 콕핏", "디지털 콕핏"), 0.88),
        ],
    },
    "080431ab51c22149": {  # IV MD&A 영상디스플레이: Neo QLED TV, Lifestyle TV, BESPOKE, 마이크로 LED, The Wall
        "entities": [
            (P, "neo qled", "Neo QLED TV"), (P, "lifestyle tv", "Lifestyle TV"),
            (P, "bespoke", "BESPOKE 가전"), (T, "마이크로 led", "마이크로 LED"),
            (P, "the wall", "The Wall"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "neo qled", "Neo QLED TV"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "lifestyle tv", "Lifestyle TV"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "bespoke", "BESPOKE 가전"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "마이크로 led", "마이크로 LED"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "the wall", "The Wall"), 0.82),
        ],
    },
    "196cddc85ef6850d": {  # MX: 갤럭시 S23/S23 Ultra, 갤럭시 Z 폴드5/플립5, 태블릿/워치/무선이어폰, Galaxy Ecosystem
        "entities": [
            (P, "갤럭시 s23", "갤럭시 S23"), (P, "갤럭시 s23 ultra", "갤럭시 S23 Ultra"),
            (P, "갤럭시 z 폴드5", "갤럭시 Z 폴드5"), (P, "갤럭시 z 플립5", "갤럭시 Z 플립5"),
            (T, "galaxy ecosystem", "Galaxy Ecosystem"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "갤럭시 s23", "갤럭시 S23"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "갤럭시 s23 ultra", "갤럭시 S23 Ultra"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "갤럭시 z 폴드5", "갤럭시 Z 폴드5"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "갤럭시 z 플립5", "갤럭시 Z 플립5"), 0.9),
        ],
    },
    "303e8d92cd8f233d": {  # 원재료 매입처 표: 공급자→삼성 (SUPPLIES_TO). Harman SOC=NVIDIA/Intel.
        "entities": [],
        "edges": [
            # DX 모바일AP 솔루션: Qualcomm, MediaTek → 삼성
            E("SUPPLIES_TO", ("org", "Qualcomm"), ("org", SAMSUNG), 0.85, "모바일AP 솔루션"),
            E("SUPPLIES_TO", ("org", "MediaTek"), ("org", SAMSUNG), 0.85, "모바일AP 솔루션"),
            # DX 디스플레이 패널: CSOT, AUO → 삼성
            E("SUPPLIES_TO", ("org", "CSOT"), ("org", SAMSUNG), 0.82, "디스플레이 패널"),
            E("SUPPLIES_TO", ("org", "AUO"), ("org", SAMSUNG), 0.82, "디스플레이 패널"),
            # DX Camera Module: 삼성전기, 파워로직스 → 삼성
            E("SUPPLIES_TO", ("org", "삼성전기"), ("org", SAMSUNG), 0.85, "Camera Module"),
            E("SUPPLIES_TO", ("org", "파워로직스"), ("org", SAMSUNG), 0.82, "Camera Module"),
            # DS Chemical: 솔브레인, 동우화인켐 → 삼성
            E("SUPPLIES_TO", ("org", "솔브레인"), ("org", SAMSUNG), 0.85, "Chemical 원판가공"),
            E("SUPPLIES_TO", ("org", "동우화인켐"), ("org", SAMSUNG), 0.85, "Chemical 원판가공"),
            # DS Wafer: SK실트론, SUMCO → 삼성
            E("SUPPLIES_TO", ("org", "SK실트론"), ("org", SAMSUNG), 0.85, "Wafer 반도체원판"),
            E("SUPPLIES_TO", ("org", "SUMCO"), ("org", SAMSUNG), 0.85, "Wafer 반도체원판"),
            # SDC FPCA: 비에이치, 영풍전자 → 삼성디스플레이
            E("SUPPLIES_TO", ("org", "비에이치"), ("org", SDC), 0.82, "FPCA 구동회로"),
            E("SUPPLIES_TO", ("org", "영풍전자"), ("org", SDC), 0.82, "FPCA 구동회로"),
            # SDC Cover Glass: Apple, Biel → 삼성디스플레이
            E("SUPPLIES_TO", ("org", "Apple"), ("org", SDC), 0.8, "Cover Glass 강화유리"),
            E("SUPPLIES_TO", ("org", "Biel"), ("org", SDC), 0.8, "Cover Glass 강화유리"),
            # Harman SOC: NVIDIA, Intel → Harman
            E("SUPPLIES_TO", ("org", "NVIDIA"), ("org", HARMAN), 0.82, "SOC CPU"),
            E("SUPPLIES_TO", ("org", "Intel"), ("org", HARMAN), 0.82, "SOC CPU"),
            # Harman 통신 모듈: WNC → Harman
            E("SUPPLIES_TO", ("org", "WNC"), ("org", HARMAN), 0.8, "차량 통신 모듈"),
        ],
    },
    "510efaabc942400e": {  # 경영상 주요 계약: Google/Ericsson/Qualcomm/Huawei/Nokia 상호특허, GlobalFoundries 공정라이선스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Google"), 0.85, "상호 특허 사용 계약"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Ericsson"), 0.85, "상호 특허 사용 계약"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Qualcomm"), 0.85, "상호 특허 사용 계약"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Huawei"), 0.85, "상호 특허 사용 계약"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Nokia"), 0.85, "상호 특허 사용 계약"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "GlobalFoundries"), 0.82, "공정 기술 라이선스 계약"),
        ],
    },
    "3d3f7d9131b54c8a": {  # 연구개발실적 표: Galaxy Z Fold5/Flip5, S23, Tab S9, Book3, Watch6, Neo QLED 8K/4K, LPCAMM, HBM3E 샤인볼트, 엑시노스, 이미지센서, OLED
        "entities": [
            (P, "갤럭시 탭 s9", "Galaxy Tab S9"), (P, "갤럭시 북3", "Galaxy Book3"),
            (P, "갤럭시 워치6", "Galaxy Watch6"), (P, "hbm3e", "HBM3E (샤인볼트)"),
            (P, "엑시노스", "엑시노스"), (P, "이미지센서", "이미지센서"),
            (T, "lpcamm", "LPCAMM"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "갤럭시 탭 s9", "Galaxy Tab S9"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "갤럭시 북3", "Galaxy Book3"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "갤럭시 워치6", "Galaxy Watch6"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "hbm3e", "HBM3E (샤인볼트)"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "엑시노스", "엑시노스"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "이미지센서", "이미지센서"), 0.85),
        ],
    },
    "58b3a21cc0fe6f7c": {  # 매출처 + 주요제품: Apple/Best Buy/Deutsche Telekom/Qualcomm/Verizon 매출처. DRAM/NAND/모바일AP, OLED 패널, 디지털콕핏/카오디오/포터블스피커
        "entities": [
            (P, "dram", "DRAM"), (P, "nand flash", "NAND Flash"), (P, "모바일ap", "모바일AP"),
            (P, "카오디오", "카오디오"), (P, "포터블 스피커", "포터블 스피커"),
        ],
        "edges": [
            # 매출처: 삼성 → 수요자 (방향: 삼성이 공급)
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "Apple"), 0.85, "주요 매출처"),
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "Best Buy"), 0.82, "주요 매출처"),
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "Deutsche Telekom"), 0.82, "주요 매출처"),
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "Qualcomm"), 0.82, "주요 매출처"),
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "Verizon"), 0.82, "주요 매출처"),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "dram", "DRAM"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "nand flash", "NAND Flash"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "모바일ap", "모바일AP"), 0.88),
            E("PRODUCES", ("org", HARMAN), ("ent", P, "카오디오", "카오디오"), 0.88),
            E("PRODUCES", ("org", HARMAN), ("ent", P, "포터블 스피커", "포터블 스피커"), 0.85),
        ],
    },
    "6913acb75baf6c96": {  # DS: 모바일AP, 이미지센서 공급; Foundry 수탁생산; HBM, DDR5, LPDDR5x, UFS4.0
        "entities": [
            (T, "foundry", "Foundry"), (P, "hbm", "HBM"), (P, "ddr5", "DDR5"),
            (P, "lpddr5x", "LPDDR5x"), (P, "ufs4.0", "UFS4.0"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "foundry", "Foundry"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "hbm", "HBM"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "ddr5", "DDR5"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "lpddr5x", "LPDDR5x"), 0.9),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "ufs4.0", "UFS4.0"), 0.88),
        ],
    },
    "7187cf0ed9e0eddc": {  # 갤럭시 S24, 모바일 AI 경험
        "entities": [(P, "갤럭시 s24", "갤럭시 S24"), (T, "모바일 ai", "모바일 AI")],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "갤럭시 s24", "갤럭시 S24"), 0.88),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "모바일 ai", "모바일 AI"), 0.82),
        ],
    },
    "76d85eebd5a955ad": {  # 매출유형 표: DX(TV/모니터/냉장고/세탁기/에어컨/스마트폰), DS(DRAM/NAND/모바일AP), SDC(OLED패널), Harman(디지털콕핏/카오디오/포터블스피커)
        "entities": [
            (P, "냉장고", "냉장고"), (P, "세탁기", "세탁기"), (P, "에어컨", "에어컨"),
            (P, "스마트폰용 oled 패널", "스마트폰용 OLED 패널"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "냉장고", "냉장고"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "세탁기", "세탁기"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "에어컨", "에어컨"), 0.85),
            E("PRODUCES", ("org", SDC), ("ent", P, "스마트폰용 oled 패널", "스마트폰용 OLED 패널"), 0.88),
        ],
    },
    "78610ecf77bd4aa0": {  # TV 기술: 마이크로 LED, Neo QLED, OLED, AI 화질, System on Chip
        "entities": [(T, "ai 화질 기술", "AI 화질 기술")],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "neo qled", "Neo QLED TV"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "마이크로 led", "마이크로 LED"), 0.82),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "ai 화질 기술", "AI 화질 기술"), 0.8),
        ],
    },
    "84e3af849e5dc7c4": {  # 사업개황: DX(TV/모니터/냉장고/세탁기/에어컨/스마트폰/네트워크시스템/컴퓨터), DS(DRAM/NAND/모바일AP), SDC(OLED패널), Harman(디지털콕핏/카오디오/소비자오디오)
        "entities": [(P, "네트워크시스템", "네트워크시스템"), (P, "모니터", "모니터")],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "네트워크시스템", "네트워크시스템"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "모니터", "모니터"), 0.85),
            E("PRODUCES", ("org", HARMAN), ("ent", P, "디지털 콕핏", "디지털 콕핏"), 0.88),
            E("PRODUCES", ("org", HARMAN), ("ent", P, "카오디오", "카오디오"), 0.88),
        ],
    },
    "8ada226d352f967e": {  # System LSI → MX사 갤럭시향 부품 공급; SOC On-Device AI, 3나노, 자동차향 SOC; 이미지센서
        "entities": [(P, "soc", "SOC (모바일 SOC)"), (T, "on-device ai", "On-Device AI"), (T, "3나노", "3나노 공정")],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "soc", "SOC (모바일 SOC)"), 0.85),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "on-device ai", "On-Device AI"), 0.82),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "3나노", "3나노 공정"), 0.82),
        ],
    },
    "18a3dec508df94c4": {  # Harman 전장: 디지털 콕핏, 카오디오; SDV 대응
        "entities": [(T, "sdv", "SDV (Software Defined Vehicle)")],
        "edges": [
            E("PRODUCES", ("org", HARMAN), ("ent", P, "디지털 콕핏", "디지털 콕핏"), 0.85),
            E("PRODUCES", ("org", HARMAN), ("ent", P, "카오디오", "카오디오"), 0.85),
            E("USES_TECH", ("org", HARMAN), ("ent", T, "sdv", "SDV (Software Defined Vehicle)"), 0.8),
        ],
    },
    "34b051fe09385f26": {  # 라이프스타일 오디오: True Wireless Stereo, Portable Speaker, Headphone
        "entities": [
            (P, "true wireless stereo", "True Wireless Stereo"),
            (P, "headphone", "Headphone"),
        ],
        "edges": [
            E("PRODUCES", ("org", HARMAN), ("ent", P, "true wireless stereo", "True Wireless Stereo"), 0.82),
            E("PRODUCES", ("org", HARMAN), ("ent", P, "headphone", "Headphone"), 0.82),
        ],
    },
    "83ba951e660b4d20": {  # Harman 소비자오디오 JBL 브랜드
        "entities": [(P, "jbl", "JBL")],
        "edges": [
            E("PRODUCES", ("org", HARMAN), ("ent", P, "jbl", "JBL"), 0.85),
        ],
    },
    "89421f720b2345a2": {  # SDC: 8.6G IT OLED 라인; Harman 전장(디지털콕핏/카오디오/텔레매틱스)
        "entities": [(P, "텔레매틱스", "텔레매틱스")],
        "edges": [
            E("PRODUCES", ("org", HARMAN), ("ent", P, "디지털 콕핏", "디지털 콕핏"), 0.85),
            E("PRODUCES", ("org", HARMAN), ("ent", P, "텔레매틱스", "텔레매틱스"), 0.82),
        ],
    },
    "80cb1485cd8f3bea": {  # SDC 디스플레이: OLED, QD-OLED, TFT-LCD
        "entities": [],
        "edges": [
            E("USES_TECH", ("org", SDC), ("ent", T, "oled", "OLED"), 0.85),
            E("USES_TECH", ("org", SDC), ("ent", T, "qd-oled", "QD-OLED"), 0.85),
        ],
    },
    "84513e3dbee33c4e": {  # 영상디스플레이: Neo QLED, OLED, Lifestyle TV(The Terrace/Premiere/Sero), 마이크로 LED, AI 업스케일링
        "entities": [(T, "ai 업스케일링", "AI 업스케일링")],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "neo qled", "Neo QLED TV"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "lifestyle tv", "Lifestyle TV"), 0.82),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "ai 업스케일링", "AI 업스케일링"), 0.8),
        ],
    },
    "6066a04f3e6b41e7": {  # SOC On-Device AI, 자동차향 SOC, 3나노, 차세대IP; 이미지센서 2억화소; Foundry Advanced/Mature 노드
        "entities": [],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "on-device ai", "On-Device AI"), 0.82),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "foundry", "Foundry"), 0.82),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "이미지센서", "이미지센서"), 0.85),
        ],
    },
    "76a8bba4f9692048": {  # DRAM Multi-step EUV; On-Device AI
        "entities": [(T, "euv", "EUV (극자외선) 공정")],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "dram", "DRAM"), 0.88),
            E("USES_TECH", ("org", SAMSUNG), ("ent", T, "euv", "EUV (극자외선) 공정"), 0.85),
        ],
    },
    "6088724094d3d295": {  # 사업측면: 갤럭시S23, Z폴드5/플립5, Neo QLED TV, BESPOKE, HBM, DDR5, LPDDR5x
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "갤럭시 s23", "갤럭시 S23"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "hbm", "HBM"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "ddr5", "DDR5"), 0.88),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "lpddr5x", "LPDDR5x"), 0.88),
        ],
    },
    "6ba050627229d5b0": {  # TV: 8K TV(세계최초), QLED 4K/8K, Lifestyle TV(The Terrace/Premiere/Sero)
        "entities": [(P, "8k tv", "8K TV"), (P, "qled", "QLED TV")],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "8k tv", "8K TV"), 0.85),
            E("PRODUCES", ("org", SAMSUNG), ("ent", P, "qled", "QLED TV"), 0.85),
        ],
    },

    # ── II. 판매경로: 통신사업자(SKT/KT/LGU+) — 삼성 → 통신사 공급 ──
    "64f429bdf388ee98": {  # 판매경로 표: 통신사업자 SK텔레콤/KT/LG유플러스
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "SK텔레콤"), 0.8, "통신사업자 판매경로"),
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "케이티"), 0.8, "통신사업자 판매경로"),
            E("SUPPLIES_TO", ("org", SAMSUNG), ("org", "LG유플러스"), 0.8, "통신사업자 판매경로"),
        ],
    },

    # ── II. 경영상 주요계약: 레인보우로보틱스, Corning, TCL/CSOT ──
    "749dcf725efc0024": {  # 레인보우로보틱스 주주간계약; 삼성디스플레이-Corning 풋옵션; 삼성디스플레이-TCL/CSOT 주주간계약
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "레인보우로보틱스"), 0.82, "주주간 계약"),
            E("RELATED_PARTY", ("org", SDC), ("org", "Corning Incorporated"), 0.82, "주식매매계약 풋옵션"),
            E("RELATED_PARTY", ("org", SDC), ("org", "TCL Technology Group Corporation"), 0.8, "주주간 계약"),
        ],
    },

    # ── X. 대주주 등과의 거래내용 (영업거래·자산거래 = 계열회사) ──
    "1b74f4195d159df4": {  # 영업거래: SEA 스마트폰/가전, SEVT/SEV 스마트폰, SSI/SSS 반도체매출 (삼성→계열)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Electronics America, Inc."), 0.85, "계열회사"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "Samsung Semiconductor, Inc."), 0.82, "계열회사"),
        ],
    },
    "7234885c0a19bcd0": {  # 자산매각/매입: SCS, SDC, SESS, SAS, SEHC, TSLED, SEV, SEVT, SIEL, SESK (계열회사)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", SDC), 0.85, "계열회사 자산거래"),
        ],
    },
    "758c4d2e8bc64a4f": {  # 협력업체 대여금: ㈜이랜텍, 대덕전자㈜
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "이랜텍"), 0.8, "협력업체"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "대덕전자"), 0.8, "협력업체"),
        ],
    },
    "0311b37b0ea332bd": {  # 채무보증: Harman 계열사들(Harman Intl, AdGear Technologies 등 계열회사)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", HARMAN), 0.85, "계열회사"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "AdGear Technologies Inc."), 0.8, "계열회사"),
        ],
    },

    # ── XI. 그 밖에 투자자 보호: 명시적 종속/특수관계 ──
    "15836fd1ead86ab7": {  # SDN 채무보증인=삼성디스플레이(종속기업); 도우인시스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", SDC), 0.85, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "도우인시스"), 0.78, "종속기업"),
        ],
    },
    "7f22ba9bb205505c": {  # 채무보증: SAS(계열), DOWOOINSYS VINA(계열회사)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "도우인시스"), 0.78, "계열회사"),
        ],
    },
    "64cae4ae4ff697e1": {  # 공정위 제재: 삼성웰스토리 단체급식 거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성웰스토리"), 0.8, "특수관계자 단체급식거래"),
        ],
    },
    "301f8be426beb071": {  # 삼성메디슨(종속) 수출 행정처분
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성메디슨"), 0.8, "종속기업"),
        ],
    },
    "2845427f5f6de7e3": {  # 제재현황 표: 자회사 삼성디스플레이, 삼성전자서비스씨에스 명시
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", SDC), 0.82, "자회사"),
            E("RELATED_PARTY", ("org", SAMSUNG), ("org", "삼성전자서비스씨에스"), 0.8, "자회사"),
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
    shared = ledger_processed_ids()
    docled = doc_ledger_ids()
    skip = (shared & set(by_id)) | docled
    todo = [r for r in rows if r["chunk_id"] not in skip]
    print(f"[s2023] rcept {RCEPT}: 전체 {len(rows)}, 공유원장 {len(shared & set(by_id))}, "
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

    # 2) 나머지 TODO 청크 = no-edge 처리(누락 0)
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

    print("=== B단계 삼성2023 추출 결과 ===")
    print(f"  처리 청크: {processed} (엣지有 {processed - skipped_zero} / no-edge {skipped_zero})")
    print(f"  엔티티 hasObject: {n_ent_total}  라벨별: {ent_by_label}")
    print(f"  엣지 총: {n_edge_total}  타입별: {edge_by_type}")
    print(f"  provenance 행: {n_prov_total}")


if __name__ == "__main__":
    run()
