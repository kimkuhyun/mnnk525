"""SK하이닉스 2024 사업보고서(rcept 20250319000665) 전체 비정형 추출 적재.

이 파일의 EXTRACTIONS = Claude(에이전트)가 chunk_index의 791개 청크를 하나씩 읽고
본문 근거로 판단한 엔티티·엣지다. 결정론 코드가 아니라 언어이해 산출물을 기록한 것.
적재 자체는 extract_helpers 의 멱등 헬퍼로 수행한다.

원장은 공유 extract_ledger.jsonl 이 아니라 graph/ledger/20250319000665.jsonl 에만 쌓는다
(작업 지시: 공유 ledger 금지). 시작 시 원장 확인해 처리완료 청크 스킵 → 멱등·누락 0.

실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_skhynix2024.py
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

RCEPT = "20250319000665"
WHERE = f"WHERE rcept_no='{RCEPT}'"
SKH = "SK하이닉스"  # resolve_org → corp_code 00164779

# 이 rcept 전용 원장 (공유 ledger 금지)
LEDGER = Path(__file__).resolve().parent / "ledger" / f"{RCEPT}.jsonl"

P = "Product"
T = "Technology"


def E(rel, frm, to, conf, relation_type=None):
    d = {"rel": rel, "from": frm, "to": to, "conf": conf}
    if relation_type:
        d["relation_type"] = relation_type
    return d


# ── Claude 추출 결과 (청크별) ──────────────────────────────
# from/to = ('org', 회사명) | ('ent', label, canonical, name)
# 회사는 resolve_org (3사 corp_code 또는 needs_er). 제품/기술은 canonical 소문자 키.
EXTRACTIONS: dict[str, dict] = {

    # ── II. 사업의 내용: 제품/기술 (PRODUCES / USES_TECH) ──────────
    "1027c50a3025f680": {  # 주력제품 DRAM, NAND, Foundry
        "entities": [(P, "dram", "DRAM"), (P, "nand flash", "NAND Flash"),
                     (P, "foundry", "Foundry")],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "dram", "DRAM"), 0.97),
            E("PRODUCES", ("org", SKH), ("ent", P, "nand flash", "NAND Flash"), 0.97),
            E("PRODUCES", ("org", SKH), ("ent", P, "foundry", "Foundry"), 0.85),
        ],
    },
    "246bf1c3e7a8de2e": {  # 연구개발실적 제75기: Client SSD, 238단 4D NAND, GDDR6-AiM(PIM), P5530, MCR DIMM
        "entities": [(P, "client ssd", "Client SSD"), (P, "238단 4d nand", "238단 4D NAND"),
                     (T, "pim", "PIM(Processing-In-Memory)"), (P, "gddr6-aim", "GDDR6-AiM"),
                     (P, "p5530", "P5530"), (P, "mcr dimm", "DDR5 MCR DIMM")],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "client ssd", "Client SSD"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "238단 4d nand", "238단 4D NAND"), 0.92),
            E("USES_TECH", ("org", SKH), ("ent", T, "pim", "PIM(Processing-In-Memory)"), 0.85),
            E("PRODUCES", ("org", SKH), ("ent", P, "gddr6-aim", "GDDR6-AiM"), 0.88),
            E("PRODUCES", ("org", SKH), ("ent", P, "p5530", "P5530"), 0.85),
            E("PRODUCES", ("org", SKH), ("ent", P, "mcr dimm", "DDR5 MCR DIMM"), 0.88),
        ],
    },
    "307cad1a7c2e809b": {  # 연구개발 제76기: LPDDR5T, LPDDR5X, 12단 HBM3, HBM3E, 서버 DDR5, cSSD, UFS, eSSD, GDDR7
        "entities": [(P, "lpddr5t", "LPDDR5T"), (P, "lpddr5x", "LPDDR5X"),
                     (P, "hbm3", "HBM3"), (P, "hbm3e", "HBM3E"), (P, "ddr5", "DDR5"),
                     (T, "hkmg", "HKMG(High-K Metal Gate)"), (T, "mr-muf", "MR-MUF"),
                     (T, "tsv", "TSV(Through Silicon Via)"), (P, "ufs", "UFS"),
                     (P, "essd", "eSSD"), (P, "gddr7", "GDDR7"), (P, "csdd", "cSSD")],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "lpddr5t", "LPDDR5T"), 0.92),
            E("PRODUCES", ("org", SKH), ("ent", P, "lpddr5x", "LPDDR5X"), 0.92),
            E("PRODUCES", ("org", SKH), ("ent", P, "hbm3", "HBM3"), 0.95),
            E("PRODUCES", ("org", SKH), ("ent", P, "hbm3e", "HBM3E"), 0.95),
            E("PRODUCES", ("org", SKH), ("ent", P, "ddr5", "DDR5"), 0.92),
            E("USES_TECH", ("org", SKH), ("ent", T, "hkmg", "HKMG(High-K Metal Gate)"), 0.9),
            E("USES_TECH", ("org", SKH), ("ent", T, "mr-muf", "MR-MUF"), 0.9),
            E("USES_TECH", ("org", SKH), ("ent", T, "tsv", "TSV(Through Silicon Via)"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "ufs", "UFS"), 0.88),
            E("PRODUCES", ("org", SKH), ("ent", P, "essd", "eSSD"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "gddr7", "GDDR7"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "csdd", "cSSD"), 0.88),
        ],
    },
    "ed66f799a52c15a5": {  # 연구개발 제77기: 1cnm DDR5, GDDR7, 1bnm LPDDR5X, ZUFS4.0, HBM3E, PCB01 SSD, 321단 4D NAND, CMM-DDR, PS1012 eSSD
        "entities": [(P, "ddr5", "DDR5"), (P, "gddr7", "GDDR7"), (P, "lpddr5x", "LPDDR5X"),
                     (P, "zufs 4.0", "ZUFS 4.0"), (P, "hbm3e", "HBM3E"), (P, "pcb01", "PCB01 SSD"),
                     (P, "321단 4d nand", "321단 4D NAND"), (P, "cmm-ddr", "CMM-DDR"),
                     (P, "ps1012", "PS1012 eSSD"), (T, "euv", "EUV 공정")],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "ddr5", "DDR5"), 0.92),
            E("PRODUCES", ("org", SKH), ("ent", P, "gddr7", "GDDR7"), 0.92),
            E("PRODUCES", ("org", SKH), ("ent", P, "lpddr5x", "LPDDR5X"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "zufs 4.0", "ZUFS 4.0"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "hbm3e", "HBM3E"), 0.95),
            E("PRODUCES", ("org", SKH), ("ent", P, "pcb01", "PCB01 SSD"), 0.88),
            E("PRODUCES", ("org", SKH), ("ent", P, "321단 4d nand", "321단 4D NAND"), 0.92),
            E("PRODUCES", ("org", SKH), ("ent", P, "cmm-ddr", "CMM-DDR"), 0.88),
            E("PRODUCES", ("org", SKH), ("ent", P, "ps1012", "PS1012 eSSD"), 0.88),
            E("USES_TECH", ("org", SKH), ("ent", T, "euv", "EUV 공정"), 0.85),
        ],
    },
    "5a680368043f7f64": {  # HBM3E 8단/12단 업계 최초 공급, eSSD
        "entities": [(P, "hbm3e", "HBM3E"), (P, "essd", "eSSD")],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "hbm3e", "HBM3E"), 0.95),
            E("PRODUCES", ("org", SKH), ("ent", P, "essd", "eSSD"), 0.9),
        ],
    },
    "57249cc55c017d16": {  # HBM 수요, eMMC/UFS/SSD
        "entities": [(P, "hbm", "HBM"), (P, "emmc", "eMMC"), (P, "ufs", "UFS"), (P, "ssd", "SSD")],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "hbm", "HBM"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "emmc", "eMMC"), 0.82),
            E("PRODUCES", ("org", SKH), ("ent", P, "ufs", "UFS"), 0.85),
            E("PRODUCES", ("org", SKH), ("ent", P, "ssd", "SSD"), 0.88),
        ],
    },
    "b91072e314914991": {  # (placeholder env) — 엔티티 없음
        "entities": [], "edges": [],
    },
    "f97bbb83253c51e1": {  # HBM AI/HPC 가속, NVIDIA GPU 시장영향
        "entities": [(P, "hbm", "HBM")],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "hbm", "HBM"), 0.92),
        ],
    },
    "2826a791f365d8e9": {  # GDDR6/GDDR7 그래픽 메모리, CXL SoC 협력
        "entities": [(P, "gddr6", "GDDR6"), (P, "gddr7", "GDDR7"), (P, "cxl 메모리", "CXL 메모리")],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "gddr6", "GDDR6"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "gddr7", "GDDR7"), 0.9),
            E("PRODUCES", ("org", SKH), ("ent", P, "cxl 메모리", "CXL 메모리"), 0.82),
        ],
    },
    "ed2fa1dd0569deef": {  # CXL 메모리 SoC 협력사 협업
        "entities": [(P, "cxl 메모리", "CXL 메모리")],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "cxl 메모리", "CXL 메모리"), 0.82),
        ],
    },
    "cce29cd057291697": {  # 범용 DDR4/5, LPDDR4/5, Automotive Grade & HBM
        "entities": [(P, "ddr4", "DDR4"), (P, "lpddr4", "LPDDR4"), (P, "lpddr5", "LPDDR5"),
                     (P, "hbm", "HBM")],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "ddr4", "DDR4"), 0.85),
            E("PRODUCES", ("org", SKH), ("ent", P, "lpddr4", "LPDDR4"), 0.85),
            E("PRODUCES", ("org", SKH), ("ent", P, "lpddr5", "LPDDR5"), 0.85),
            E("PRODUCES", ("org", SKH), ("ent", P, "hbm", "HBM"), 0.88),
        ],
    },
    "a69dd7c0d0b8ad29": {  # 24GB/48GB DDR5 게이밍
        "entities": [(P, "ddr5", "DDR5")],
        "edges": [E("PRODUCES", ("org", SKH), ("ent", P, "ddr5", "DDR5"), 0.85)],
    },
    "d6c2bd1ada065da5": {  # 모바일 메모리 LPDDR5X/T
        "entities": [(P, "lpddr5x", "LPDDR5X"), (P, "lpddr5t", "LPDDR5T")],
        "edges": [
            E("PRODUCES", ("org", SKH), ("ent", P, "lpddr5x", "LPDDR5X"), 0.88),
            E("PRODUCES", ("org", SKH), ("ent", P, "lpddr5t", "LPDDR5T"), 0.88),
        ],
    },
    "81b51da954f6d30e": {  # QLC, PCIe Gen5, 61TB Gen5 eSSD, Solidigm 시너지
        "entities": [(T, "qlc", "QLC"), (P, "essd", "eSSD")],
        "edges": [
            E("USES_TECH", ("org", SKH), ("ent", T, "qlc", "QLC"), 0.85),
            E("PRODUCES", ("org", SKH), ("ent", P, "essd", "eSSD"), 0.88),
        ],
    },
    "b5b353f2c35715b6": {  # CMOS 이미지센서(CIS) 생산
        "entities": [(P, "cis", "CMOS 이미지 센서(CIS)")],
        "edges": [E("PRODUCES", ("org", SKH), ("ent", P, "cis", "CMOS 이미지 센서(CIS)"), 0.88)],
    },

    # ── II. 주요 계약 (RELATED_PARTY / 라이선스·영업양수) ──────────
    "26e4bbb8482f4c96": {  # Rambus 특허 크로스 라이선스, Intel NAND 영업양수
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "Rambus Inc."), 0.9, "특허 크로스 라이선스"),
            E("RELATED_PARTY", ("org", SKH), ("org", "Intel Corporation"), 0.9, "영업양수(NAND사업)"),
        ],
    },

    # ── II. 원재료 매입처 (SUPPLIES_TO: 공급자→SK) ────────────────
    # 본문은 공급사를 익명(9개사/6개사)으로 기술 → 특정 회사 엔티티 없음. 엣지 0.

    # ── X. 대주주 등과의 거래: 해외 종속/관계 법인 ────────────────
    "ad793baad16e5c52": {  # 매출/매입: 미주/우시/중국/홍콩/대만/싱가포르 법인
        "entities": [],
        "edges": [
            # 판매법인 = SK가 반도체 매출(공급) → SK→법인
            E("SUPPLIES_TO", ("org", SKH), ("org", "SK hynix America Inc."), 0.9),
            E("SUPPLIES_TO", ("org", SKH), ("org", "SK hynix (Wuxi) Semiconductor Sales Ltd."), 0.9),
            E("SUPPLIES_TO", ("org", SKH), ("org", "SK hynix Semiconductor HongKong"), 0.88),
            E("SUPPLIES_TO", ("org", SKH), ("org", "SK hynix Semiconductor Taiwan Inc."), 0.88),
            E("SUPPLIES_TO", ("org", SKH), ("org", "SK hynix Asia Pte. Ltd."), 0.88),
            # 중국 생산법인 = SK가 반도체 매입(공급받음) → 법인→SK
            E("SUPPLIES_TO", ("org", "SK hynix Semiconductor (China) Ltd."), ("org", SKH), 0.88),
            # 모두 특수관계자(해외 종속법인)
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix America Inc."), 0.9, "해외판매법인(종속기업)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix Semiconductor (China) Ltd."), 0.9, "해외생산법인(종속기업)"),
        ],
    },
    "2c3dd87d68ffa203": {  # China 법인에서 기계장치 매입
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "SK hynix Semiconductor (China) Ltd."), ("org", SKH), 0.85),
        ],
    },
    "00a9c45751854232": {  # NAND Product Solutions 장기대여
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix NAND Product Solutions Corp."), 0.88, "해외법인(자금대여)"),
        ],
    },
    "9197f6ef69708a84": {  # China/Dalian/NAND Product Solutions 장기대여
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix Semiconductor (Dalian) Co., Ltd."), 0.88, "해외법인(자금대여)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix NAND Product Solutions Corp."), 0.85, "해외법인(자금대여)"),
        ],
    },
    "ee6b35574149f6c4": {  # 출자: SK Americas, SK Telecom Japan
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK Americas, Inc."), 0.85, "관계기업(출자)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK Telecom Japan"), 0.82, "관계기업(출자)"),
        ],
    },

    # ── III. 주석 / 감사보고서: 관계기업·공동기업·종속기업·특수관계자 ──
    "cfed045d3c28c8f5": {  # 관계기업/공동기업 상세 (연결주석)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK China Company Limited"), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK South East Asia Investment Pte. Ltd."), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SiFive, Inc."), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "우시시신파직접회로산업원유한공사"), 0.85, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "HITECH Semiconductor (Wuxi) Co., Ltd."), 0.9, "공동기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix system ic (Wuxi) Co., Ltd."), 0.9, "공동기업"),
        ],
    },
    "a5ffcef58c27a626": {  # 별도주석 관계기업/공동기업: Stratio, SK China, SEA, 푸르메, SiFive, SK telecom Japan, SK Americas
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "Stratio, Inc."), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK China Company Limited"), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK South East Asia Investment Pte. Ltd."), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SiFive, Inc."), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK telecom Japan Inc."), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK Americas, Inc."), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "HITECH Semiconductor (Wuxi) Co., Ltd."), 0.9, "공동기업"),
        ],
    },
    "6f8a0118f62f1bed": {  # 연결감사보고서 관계기업/공동기업 (cfed 중복 재제시)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK China Company Limited"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK South East Asia Investment Pte. Ltd."), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SiFive, Inc."), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "HITECH Semiconductor (Wuxi) Co., Ltd."), 0.88, "공동기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix system ic (Wuxi) Co., Ltd."), 0.88, "공동기업"),
        ],
    },
    "c3a178cf5156b86b": {  # 특수관계자 전체 목록 (연결감사보고서)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "Stratio, Inc."), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "Gemini Partners Pte. Ltd."), 0.82, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SAPEON Inc."), 0.82, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK telecom Japan Inc."), 0.85, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK Americas, Inc."), 0.85, "관계기업"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK스퀘어"), 0.9, "기타특수관계자(지배주주)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK(주)"), 0.85, "기타특수관계자(최상위지배기업)"),
        ],
    },
    "8d632ca2ca2e0d24": {  # 종속기업 추가/제외 (신설·청산)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix Semiconductor West Lafayette LLC"), 0.85, "종속기업(신설)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK hynix memory solutions Poland sp. z o.o."), 0.85, "종속기업(신설)"),
        ],
    },
    "8b272c38e0edeae4": {  # KIOXIA 투자, 인텔 NAND 사업 인수
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "KIOXIA Holdings Corporation"), 0.85, "장기투자(지분보유)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "Intel Corporation"), 0.85, "영업양수(NAND사업)"),
        ],
    },
    "c1aeda5576c9d364": {  # 별도 인텔 NAND 인수 / 중국 경쟁당국 조건
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "Intel Corporation"), 0.82, "영업양수(NAND사업)"),
        ],
    },

    # ── IX. 계열회사: SK스퀘어 대주주, SK하이닉스 종속기업, 겸직 ──────
    "2a552388b3a39072": {  # 출자현황: SK스퀘어→SK하이닉스 20.1%, SK하이닉스→하이스텍/하이이엔지/행복모아/시스템IC/행복나래/키파운드리 100%
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK스퀘어"), 0.9, "최대주주(20.1%)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK하이스텍"), 0.88, "종속기업(100%)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK하이이엔지"), 0.88, "종속기업(100%)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "행복모아"), 0.88, "종속기업(100%)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK하이닉스시스템IC"), 0.88, "종속기업(100%)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "행복나래"), 0.88, "종속기업(100%)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK키파운드리"), 0.88, "종속기업(100%)"),
        ],
    },
    "8546ed9db12474f5": {  # 동일 출자 매트릭스 (계열사 계 행) — 중복 재제시
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK스퀘어"), 0.85, "최대주주(20.1%)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK하이스텍"), 0.85, "종속기업(100%)"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK키파운드리"), 0.85, "종속기업(100%)"),
        ],
    },
    "5558c3ad121fd773": {  # 특별약정 계열사: 하이이엔지/하이스텍/시스템아이씨/키파운드리/행복모아/행복나래; 기업집단 에스케이
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SKH), ("org", "SK하이이엔지"), 0.82, "특별약정계열사"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK하이스텍"), 0.82, "특별약정계열사"),
            E("RELATED_PARTY", ("org", SKH), ("org", "SK키파운드리"), 0.82, "특별약정계열사"),
            E("RELATED_PARTY", ("org", SKH), ("org", "행복모아"), 0.8, "특별약정계열사"),
            E("RELATED_PARTY", ("org", SKH), ("org", "행복나래"), 0.8, "특별약정계열사"),
        ],
    },
}


# ── 이 rcept 전용 원장 헬퍼 ────────────────────────────────
def ledger_ids() -> set[str]:
    if not LEDGER.exists():
        return set()
    ids = set()
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ids.add(json.loads(line)["chunk_id"])
        except Exception:
            continue
    return ids


def mark(chunk_id: str, n_ent: int, n_edge: int, section_path: str = None) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "chunk_id": chunk_id, "n_ent": n_ent, "n_edge": n_edge,
        "rcept_no": RCEPT, "section_path": section_path,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


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
    done = ledger_ids()
    print(f"[batch] 청크 {len(rows)}건 (rcept {RCEPT}), 원장 기처리 {len(done)}건")

    driver = neo4j_driver()
    conn = mariadb_conn()

    n_ent_total = n_edge_total = n_prov_total = 0
    ent_by_label: dict[str, int] = {}
    edge_by_type: dict[str, int] = {}
    processed = 0

    # 1) 추출 결과 있는 청크
    for cid, payload in EXTRACTIONS.items():
        if cid in done:
            continue
        if cid not in by_id:
            print(f"  [warn] {cid} chunk_index에 없음 — 스킵")
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
            edge_by_type["hasObject"] = edge_by_type.get("hasObject", 0) + 1

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
        mark(cid, n_ent, n_edge, row["section_path"])
        n_ent_total += n_ent
        n_edge_total += n_edge
        processed += 1

    # 2) 나머지 청크는 엣지 0개로 처리 표시 (누락 0 보장)
    extracted_ids = set(EXTRACTIONS.keys())
    for r in rows:
        cid = r["chunk_id"]
        if cid in done or cid in extracted_ids:
            continue
        mark(cid, 0, 0, r["section_path"])
        processed += 1

    conn.close()
    driver.close()

    print("=== SK하이닉스 2024 추출 결과 ===")
    print(f"  이번 실행 처리 청크: {processed}  (원장 누적: {len(ledger_ids())} / {len(rows)})")
    print(f"  엔티티 hasObject: {n_ent_total}  타입별: {ent_by_label}")
    print(f"  엣지(hasObject 포함) 총: {n_edge_total + n_ent_total}  타입별: {edge_by_type}")
    print(f"  provenance 행: {n_prov_total}")


if __name__ == "__main__":
    run()
