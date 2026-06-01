"""B단계 비정형 추출 적재 — SK하이닉스 2023 사업보고서 (rcept 20240319000684).

이 파일의 EXTRACTIONS = Claude(에이전트)가 768개 청크를 읽고 본문 근거로 판단한
엔티티·엣지다. 결정론 코드가 아니라 언어이해 산출물의 기록. 적재는 extract_helpers
의 멱등 헬퍼로 수행한다.

실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_skhynix2023.py
멱등 — 원장(db/graph/ledger/20240319000684.jsonl)에 기록된 청크는 스킵.
대상 청크 전부 mark_processed(엣지 0개여도) → 누락 0.

원장은 공유 extract_ledger.jsonl 이 아닌 per-rcept 파일에만 기록(동시실행 충돌 방지).
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
    prov_id,
    resolve_org,
    write_provenance,
)

RCEPT = "20240319000684"
WHERE = f"WHERE rcept_no='{RCEPT}'"
SKH = "SK하이닉스"  # resolve_org → corp_code 00164779

# per-rcept 원장 (공유 ledger 금지)
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_PATH = LEDGER_DIR / f"{RCEPT}.jsonl"

P = "Product"
T = "Technology"


def E(rel, frm, to, conf, relation_type=None):
    d = {"rel": rel, "from": frm, "to": to, "conf": conf}
    if relation_type:
        d["relation_type"] = relation_type
    return d


# ── per-rcept 원장 ─────────────────────────────────────────
def _ledger_ids() -> set:
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


def _mark(chunk_id, n_ent, n_edge, section_path):
    rec = {
        "chunk_id": chunk_id, "n_ent": n_ent, "n_edge": n_edge,
        "rcept_no": RCEPT, "section_path": section_path,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ── Claude 추출 결과 (청크별) ──────────────────────────────
EXTRACTIONS: dict[str, dict] = {

    # ── II. 사업의 내용 : 제품/기술 ────────────────────────
    "1315dab54b362ff6": {  # 주력제품 DRAM/NAND 메모리, 시스템반도체 CIS·파운드리. Fab 설명, 인텔 NAND사업 인수→Dalian Fab
        "entities": [
            (P, "dram", "DRAM"), (P, "nand flash", "NAND Flash"),
            (P, "cis", "CIS(CMOS Image Sensor)"), (P, "foundry", "파운드리"),
        ],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "dram", "DRAM"), 0.97),
            E("PRODUCES", ("org", SKH), ("ent", P, "nand flash", "NAND Flash"), 0.97),
            E("PRODUCES", ("org", SKH), ("ent", P, "cis", "CIS(CMOS Image Sensor)"), 0.92),
            E("PRODUCES", ("org", SKH), ("ent", P, "foundry", "파운드리"), 0.85),
        ],
    },
    "6d8c825009624c8b": {  # 매출표 주요제품 DRAM, NAND Flash, CIS 등 (주요상표 SK하이닉스)
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "dram", "DRAM"), 0.95),
            E("PRODUCES", ("org", SKH), ("ent", P, "nand flash", "NAND Flash"), 0.95),
            E("PRODUCES", ("org", SKH), ("ent", P, "cis", "CIS(CMOS Image Sensor)"), 0.9),
        ],
    },
    "b8463da70bfec847": {  # 사업부문 매출표 주요제품 DRAM, NAND Flash, CIS 등
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "dram", "DRAM"), 0.95),
            E("PRODUCES", ("org", SKH), ("ent", P, "nand flash", "NAND Flash"), 0.95),
            E("PRODUCES", ("org", SKH), ("ent", P, "cis", "CIS(CMOS Image Sensor)"), 0.9),
        ],
    },
    "1d0dbbd3398d91d6": {  # 당사는 CMOS 이미지 센서(CIS)를 생산
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "cis", "CIS(CMOS Image Sensor)"), 0.9),
        ],
    },
    "1eeb9a1c91124a0a": {  # 당사가 생산하는 낸드플래시 / 당사는 CMOS 이미지 센서 생산
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "nand flash", "NAND Flash"), 0.92),
            E("PRODUCES", ("org", SKH), ("ent", P, "cis", "CIS(CMOS Image Sensor)"), 0.88),
        ],
    },
    "4b104c748703b2df": {  # 당사는 DRAM과 비휘발성 플래시메모리를 생산
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "dram", "DRAM"), 0.93),
            E("PRODUCES", ("org", SKH), ("ent", P, "nand flash", "NAND Flash"), 0.9),
        ],
    },
    "c0edb62ee2b9653c": {  # DDR5, HBM3 프리미엄 제품 포트폴리오, AI향 HBM 선도
        "entities": [
            (P, "ddr5", "DDR5"), (P, "hbm3", "HBM3"), (P, "hbm", "HBM"),
        ],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "ddr5", "DDR5"), 0.92),
            E("PRODUCES", ("org", SKH), ("ent", P, "hbm3", "HBM3"), 0.92),
            E("PRODUCES", ("org", SKH), ("ent", P, "hbm", "HBM"), 0.9),
        ],
    },
    "8cb4334e64dbc23c": {  # HBM/고용량 DDR5 AI서버향 제품 수요 성장
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "hbm", "HBM"), 0.88),
            E("PRODUCES", ("org", SKH), ("ent", P, "ddr5", "DDR5"), 0.88),
        ],
    },
    "42631daf211c5396": {  # HBM(High Bandwidth Memory) 자사 신기술 Lead, GDDR6 그래픽스
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "hbm", "HBM"), 0.9),
        ],
    },
    "a389979df07d0538": {  # GDDR6 메인 채용, GDDR7 출시 예정 (그래픽스 메모리)
        "entities": [
            (P, "gddr6", "GDDR6"), (P, "gddr7", "GDDR7"),
        ],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "gddr6", "GDDR6"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "gddr7", "GDDR7"), 0.8),
        ],
    },
    "ab787f8c4fdfb8da": {  # DDR3/4, LPDDR4/5, Specialty(HBM) 등 포트폴리오; 모바일 메모리
        "entities": [
            (P, "lpddr5", "LPDDR5"),
        ],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "lpddr5", "LPDDR5"), 0.85),
            E("PRODUCES", ("org", SKH), ("ent", P, "hbm", "HBM"), 0.85),
        ],
    },
    "48ebc0be3f36e7b2": {  # 연구개발실적 제76기: LPDDR5T, LPDDR5X 24GB, HBM DRAM, HKMG 공정
        "entities": [
            (P, "lpddr5t", "LPDDR5T"), (P, "lpddr5x", "LPDDR5X"),
            (T, "hkmg", "HKMG(High-K Metal Gate)"),
        ],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "lpddr5t", "LPDDR5T"), 0.92),
            E("PRODUCES", ("org", SKH), ("ent", P, "lpddr5x", "LPDDR5X"), 0.92),
            E("USES_TECH", ("org", SKH), ("ent", T, "hkmg", "HKMG(High-K Metal Gate)"), 0.9),
        ],
    },
    "7da1473264be661c": {  # 연구개발실적 제75기: Client SSD(176단 DRAMless), 238단 4D NAND, PIM GDDR6-AiM
        "entities": [
            (P, "client ssd", "Client SSD"),
            (P, "238단 4d nand", "238단 4D NAND Flash"),
            (T, "pim", "PIM(Processing-In-Memory)"),
            (P, "gddr6-aim", "GDDR6-AiM"),
            (T, "4d nand", "4D NAND"),
        ],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "client ssd", "Client SSD"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "238단 4d nand", "238단 4D NAND Flash"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "gddr6-aim", "GDDR6-AiM"), 0.9),
            E("USES_TECH", ("org", SKH), ("ent", T, "pim", "PIM(Processing-In-Memory)"), 0.88),
            E("USES_TECH", ("org", SKH), ("ent", T, "4d nand", "4D NAND"), 0.85),
        ],
    },
    "d9d24c307cb857e6": {  # 연구개발실적 제74기: LPDDR4/5, GDDR6, E1.S eSSD, EUV 1anm, 0.8um CIS
        "entities": [
            (P, "lpddr4", "LPDDR4"),
            (P, "essd", "eSSD(Enterprise SSD)"),
            (T, "euv", "EUV"),
        ],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "lpddr4", "LPDDR4"), 0.88),
            E("PRODUCES", ("org", SKH), ("ent", P, "lpddr5", "LPDDR5"), 0.88),
            E("PRODUCES", ("org", SKH), ("ent", P, "gddr6", "GDDR6"), 0.88),
            E("PRODUCES", ("org", SKH), ("ent", P, "essd", "eSSD(Enterprise SSD)"), 0.85),
            E("USES_TECH", ("org", SKH), ("ent", T, "euv", "EUV"), 0.85),
        ],
    },
    "098d400ab8f244d9": {  # CXL 기술/CXL 메모리, Heterogeneous Computing, 서버 DRAM
        "entities": [
            (T, "cxl", "CXL(Compute Express Link)"),
        ],
        "edges": [
            E("USES_TECH", ("org", SKH), ("ent", T, "cxl", "CXL(Compute Express Link)"), 0.8),
        ],
    },
    "ff4ce50dfbb6cab2": {  # TSV(Through Silicon Via) 기술 경쟁력 확보, 응용복합제품 개발
        "entities": [
            (T, "tsv", "TSV(Through Silicon Via)"),
        ],
        "edges": [
            E("USES_TECH", ("org", SKH), ("ent", T, "tsv", "TSV(Through Silicon Via)"), 0.82),
        ],
    },
    "f15115f39ea33d7f": {  # 주요계약: Rambus 라이선스(특허 사용권), BCPE Pangea(도시바 반도체 SPC 투자/LP)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "Rambus Inc."), 0.85, "특허라이선스계약"),
            E("RELATED_PARTY", ("org", SKH),
              ("org", "BCPE Pangea Intermediate Holdings Cayman, LP"), 0.82, "SPC출자(도시바 반도체)"),
        ],
    },

    # ── IX. 계열회사 : 기업집단/특별약정 계열사 ────────────
    "6fbd5b8da95672a8": {  # 기업집단명=에스케이, 특별약정 계열사(SK하이이엔지/하이스텍/하이닉스시스템IC/키파운드리/행복모아/행복나래), 해외판매법인
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK하이이엔지"), 0.9, "계열회사(특별약정)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK하이스텍"), 0.9, "계열회사(특별약정)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK하이닉스시스템아이씨"), 0.9, "계열회사(특별약정)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK키파운드리"), 0.9, "계열회사(특별약정)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "행복모아"), 0.88, "계열회사(특별약정)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "행복나래"), 0.88, "계열회사(특별약정)"),
        ],
    },

    # ── X. 대주주 등과의 거래 : 특수관계자 거래 ────────────
    "b67b7687bb2933bf": {  # 대주주 영업거래: 해외판매·생산법인과 반도체 매출/매입, 대여금
        "entities": [],
        "edges": [
            # SK하이닉스가 해외판매법인에 반도체 공급(매출) → SUPPLIES_TO 공급자(SKH)→수요자(판매법인)
            E("SUPPLIES_TO", ("org", SKH), ("org", "SK hynix America Inc."), 0.85),
            E("SUPPLIES_TO", ("org", SKH), ("org", "SK hynix (Wuxi) Semiconductor Sales Ltd."), 0.85),
            E("SUPPLIES_TO", ("org", SKH), ("org", "SK hynix Semi. Taiwan Inc."), 0.85),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix America Inc."), 0.9, "해외판매법인(종속기업)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix (Wuxi) Semiconductor Sales Ltd."), 0.9, "해외판매법인(종속기업)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix Semiconductor (China) Ltd."), 0.9, "해외생산법인(종속기업)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix NAND Product Solutions Corp."), 0.9, "해외판매법인(종속기업)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix Semi. Taiwan Inc."), 0.9, "해외판매법인(종속기업)"),
        ],
    },
    "1ef0bae788f66979": {  # 자산양수도: HITECH Semiconductor(Wuxi), SK hynix Semiconductor(Chongqing/China) 기계장치 매각
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "HITECH Semiconductor (Wuxi) Co., Ltd."), 0.88, "해외법인(공동기업)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix Semiconductor (Chongqing) Ltd."), 0.9, "해외법인(종속기업)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix Semiconductor (China) Ltd."), 0.9, "해외법인(종속기업)"),
        ],
    },
    "375dc52337f4e159": {  # 대여금: SK hynix NAND Product Solutions Corp.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix NAND Product Solutions Corp."), 0.9, "해외법인(자금대여)"),
        ],
    },
    "9455ae8f1e711237": {  # 대여금: SK hynix Semiconductor(China/Dalian), NAND Product Solutions
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix Semiconductor (China) Ltd."), 0.9, "해외법인(자금대여)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix Semiconductor (Dalian) Co., Ltd."), 0.9, "해외법인(자금대여)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix NAND Product Solutions Corp."), 0.88, "해외법인(자금대여)"),
        ],
    },
    "69ef2743359c1c4d": {  # 자산매입: SK hynix Semiconductor(China)로부터 기계장치 매입
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix Semiconductor (China) Ltd."), 0.88, "해외법인(자산매입)"),
        ],
    },
    "77f1b171fa34b351": {  # 출자/지분처분: SK Telecom Japan(관계기업, SK Telecom으로부터 34% 취득), SK hynix Ventures America LLC(SK hynix America와 합병)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK Telecom Japan"), 0.85, "관계기업(지분취득)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK Telecom"), 0.8, "특수관계자(지분취득 상대)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix Ventures America LLC"), 0.82, "해외법인(합병)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix America Inc."), 0.85, "해외법인(종속기업)"),
        ],
    },
    "d6ee914d37161525": {  # 부동산 매각: 클린인더스트리얼위탁관리부동산투자회사(계열회사)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "클린인더스트리얼위탁관리부동산투자회사"), 0.88, "계열회사(부동산매각)"),
        ],
    },

    # ── 주석 : 특수관계자 명단 ─────────────────────────────
    "51c3307d5059966a": {  # 연결주석 관계기업/공동기업: SK China, SK SEA Investment, 매그너스PEF, SiFive, 우시시신파, Hitech/Hystars(Wuxi), 반도체성장펀드, 시스템반도체상생펀드
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK China Company Limited"), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK South East Asia Investment Pte. Ltd."), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "매그너스사모투자합자회사"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SiFive, Inc."), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "우시시신파직접회로산업원유한공사"), 0.85, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "Hitech Semiconductor (Wuxi) Co., Ltd."), 0.9, "공동기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "Hystars Semiconductor (Wuxi) Co., Ltd."), 0.9, "공동기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "반도체성장 전문투자형 사모 투자신탁"), 0.85, "공동기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "시스템반도체상생펀드"), 0.82, "공동기업"),
        ],
    },
    "e2e5d88ecb176625": {  # 동일 관계기업/공동기업 명단(연결주석) — 멱등 보강
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK China Company Limited"), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK South East Asia Investment Pte. Ltd."), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SiFive, Inc."), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "Hitech Semiconductor (Wuxi) Co., Ltd."), 0.9, "공동기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "Hystars Semiconductor (Wuxi) Co., Ltd."), 0.9, "공동기업"),
        ],
    },
    "b63c75892ef23c2b": {  # 별도주석 관계기업·공동기업: Stratio, SK China, SK SEA, 푸르메소셜팜, 매그너스, 엘앤에스10호, SiFive, 미래에셋위반도체, SK telecom Japan, Hitech, 반도체성장/시스템반도체상생/생태계펀드
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "Stratio, Inc."), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK China Company Limited"), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK South East Asia Investment Pte. Ltd."), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "농업회사법인 푸르메소셜팜"), 0.82, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "매그너스사모투자합자회사"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "엘앤에스 10호 Early Stage III 투자조합"), 0.8, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SiFive, Inc."), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "미래에셋위반도체 제1호창업벤처전문사모투자합자회사"), 0.8, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK telecom Japan"), 0.85, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "반도체 생태계 일반 사모 투자신탁"), 0.8, "공동기업"),
        ],
    },
    "e86f2ab8d1c94ea4": {  # 별도주석 동일 명단 — 멱등 보강
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "Stratio, Inc."), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK telecom Japan"), 0.85, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "미래에셋위반도체 제1호창업벤처전문사모투자합자회사"), 0.8, "관계기업"),
        ],
    },
    "348c88e643c04286": {  # 별도주석 특수관계자: 종속기업/공동기업(HITECH)/관계기업(매그너스)/기타특수관계자(SK스퀘어)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "HITECH Semiconductor (Wuxi) Co., Ltd."), 0.88, "공동기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "매그너스사모투자합자회사"), 0.85, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK스퀘어"), 0.88, "기타특수관계자(대주주)"),
        ],
    },
    "7ca7298c354a689e": {  # 동일 특수관계자 분류(별도주석) — 멱등 보강
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "HITECH Semiconductor (Wuxi) Co., Ltd."), 0.88, "공동기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "매그너스사모투자합자회사"), 0.85, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK스퀘어"), 0.88, "기타특수관계자(대주주)"),
        ],
    },
    "3d913f87a536d821": {  # 연결주석 특수관계자: HITECH/반도체성장펀드/Hystars(공동기업), 매그너스(관계기업), SK스퀘어(기타특수관계자)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "Hitech Semiconductor (Wuxi) Co., Ltd."), 0.88, "공동기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "반도체성장 전문투자형 사모 투자신탁"), 0.85, "공동기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "Hystars Semiconductor (Wuxi) Co., Ltd."), 0.88, "공동기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "매그너스사모투자합자회사"), 0.85, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK스퀘어"), 0.88, "기타특수관계자(대주주)"),
        ],
    },
    "abf259df3e693eff": {  # 동일 특수관계자(연결주석) — 멱등 보강
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "Hitech Semiconductor (Wuxi) Co., Ltd."), 0.88, "공동기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "Hystars Semiconductor (Wuxi) Co., Ltd."), 0.88, "공동기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK스퀘어"), 0.88, "기타특수관계자(대주주)"),
        ],
    },
    "6ca472f5ba7c9581": {  # 별도주석 종속기업 명단: SK하이이엔지/하이스텍/행복모아/하이닉스시스템IC/행복나래/키파운드리, SK hynix America/Deutschland/Asia/HongKong/U.K.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK하이이엔지"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK하이스텍"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "행복모아"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK하이닉스시스템아이씨"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "행복나래"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK키파운드리"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix America Inc."), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix Deutschland GmbH"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix Asia Pte. Ltd."), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix Semiconductor HongKong Ltd."), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix U.K. Ltd."), 0.85, "종속기업"),
        ],
    },
    "8b596cd107893ca6": {  # 동일 종속기업 명단(별도주석) — 멱등 보강
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix America Inc."), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix Deutschland GmbH"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix Asia Pte. Ltd."), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix Semiconductor HongKong Ltd."), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix U.K. Ltd."), 0.85, "종속기업"),
        ],
    },
    "dba33963e98ca4ee": {  # 공동기업 HITECH / 기타특수관계자 클린인더스트리얼리츠, SK머티리얼즈에어플러스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "HITECH Semiconductor (Wuxi) Co., Ltd."), 0.88, "공동기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "클린인더스트리얼위탁관리부동산투자회사"), 0.85, "기타특수관계자"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK머티리얼즈에어플러스"), 0.82, "기타특수관계자"),
        ],
    },
    "fb9914a6c2cb4c5f": {  # 동일(연결주석) — 멱등 보강
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "HITECH Semiconductor (Wuxi) Co., Ltd."), 0.88, "공동기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "클린인더스트리얼위탁관리부동산투자회사"), 0.85, "기타특수관계자"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK머티리얼즈에어플러스"), 0.82, "기타특수관계자"),
        ],
    },
    "e434235c36f5ac26": {  # RSU: SK hynix NAND Product Solutions Corp. 및 종속기업 종업원 부여분
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix NAND Product Solutions Corp."), 0.85, "종속기업"),
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

    done = _ledger_ids()
    if done:
        print(f"[ledger] 기처리 {len(done)}건 스킵")

    driver = neo4j_driver()
    conn = mariadb_conn()

    n_ent_total = n_edge_total = n_prov_total = 0
    edge_by_type: dict[str, int] = {}
    processed = 0

    # 1) 추출 결과 청크
    for cid, payload in EXTRACTIONS.items():
        if cid not in by_id:
            print(f"  [warn] {cid} 대상에 없음 — 스킵")
            continue
        if cid in done:
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
        _mark(cid, n_ent, n_edge, row["section_path"])
        n_ent_total += n_ent
        n_edge_total += n_edge
        processed += 1

    # 2) 나머지 청크 엣지 0개로 처리 표시(누락 0)
    extracted_ids = set(EXTRACTIONS.keys())
    for r in rows:
        cid = r["chunk_id"]
        if cid in extracted_ids or cid in done:
            continue
        _mark(cid, 0, 0, r["section_path"])
        processed += 1

    conn.close()
    driver.close()

    print("=== SK하이닉스 2023 추출 결과 ===")
    print(f"  처리 청크: {processed} / {len(rows)}  (기존원장 {len(done)})")
    print(f"  엔티티(Product/Tech) hasObject: {n_ent_total}")
    print(f"  엣지 총: {n_edge_total}  타입별: {edge_by_type}")
    print(f"  provenance 행: {n_prov_total}")


if __name__ == "__main__":
    run()
