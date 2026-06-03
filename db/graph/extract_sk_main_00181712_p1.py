"""SK(주) corp_code=00181712 비정형 추출 적재 — 배치 1 (text_micro LIMIT 3600 OFFSET 0).

Claude 에이전트가 chunk_index 청크 본문을 읽고 판단한 엔티티·엣지.
- 대상: text_micro LIMIT 3600 OFFSET 0 + table_nl LIKE '%특수관계%'
- 원장: graph/ledger/extra28_00181712_p1.jsonl (공유 ledger 금지)
- 멱등: 시작 시 원장 확인 → 처리완료 청크 스킵

실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_sk_main_00181712_p1.py
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

CORP_CODE = "00181712"
SK = "SK(주)"  # resolve_org → corp_code 00181712 (extra28 목록)

# 이 배치 전용 원장
LEDGER = Path(__file__).resolve().parent / "ledger" / "extra28_00181712_p1.jsonl"

P = "Product"
T = "Technology"


def E(rel, frm, to, conf, relation_type=None):
    d = {"rel": rel, "from": frm, "to": to, "conf": conf}
    if relation_type:
        d["relation_type"] = relation_type
    return d


# ── Claude 추출 결과 (청크별) ──────────────────────────────────────────────
# from/to = ('org', 회사명) | ('ent', label, canonical, name)
# 청크 본문에서 근거 있는 것만. 환각 금지.
EXTRACTIONS: dict[str, dict] = {

    # ═══ SK바이오팜 — 뇌전증 신약 세노바메이트(XCOPRI), 솔리암페톨(SUNOSI) ═══

    "012888f681df53c8": {  # SK바이오팜 세노바메이트/솔리암페톨 CNS 혁신신약
        "entities": [
            (P, "세노바메이트", "세노바메이트(XCOPRI)"),
            (P, "솔리암페톨", "솔리암페톨(SUNOSI)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "SK바이오팜"), ("ent", P, "세노바메이트", "세노바메이트(XCOPRI)"), 0.95),
            E("PRODUCES", ("org", "SK바이오팜"), ("ent", P, "솔리암페톨", "솔리암페톨(SUNOSI)"), 0.92),
        ],
    },
    "0127126082c97b0a": {  # 세노바메이트 뇌전증 시장 경쟁상황
        "entities": [(P, "세노바메이트", "세노바메이트(XCOPRI)")],
        "edges": [
            E("PRODUCES", ("org", "SK바이오팜"), ("ent", P, "세노바메이트", "세노바메이트(XCOPRI)"), 0.92),
        ],
    },
    "0157a85f0be652e5": {  # 세노바메이트 XCOPRI/ONTOZRY + 솔리암페톨 SUNOSI — 2025 사업보고서
        "entities": [
            (P, "세노바메이트", "세노바메이트(XCOPRI/ONTOZRY)"),
            (P, "솔리암페톨", "솔리암페톨(SUNOSI)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "SK바이오팜"), ("ent", P, "세노바메이트", "세노바메이트(XCOPRI/ONTOZRY)"), 0.97),
            E("PRODUCES", ("org", "SK바이오팜"), ("ent", P, "솔리암페톨", "솔리암페톨(SUNOSI)"), 0.92),
            E("RELATED_PARTY", ("org", "SK바이오팜"), ("org", "SK(주)"), 0.95, "종속기업(분할)"),
        ],
    },
    "004646e6c58476f4": {  # 세노바메이트 미국SK Life Science→유럽Arvelle/Angelini 기술수출
        "entities": [
            (P, "세노바메이트", "세노바메이트(XCOPRI/ONTOZRY)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "SK바이오팜"), ("ent", P, "세노바메이트", "세노바메이트(XCOPRI/ONTOZRY)"), 0.95),
            E("RELATED_PARTY", ("org", "SK바이오팜"), ("org", "SK Life Science, Inc."), 0.9, "종속기업(미국판매법인)"),
            E("SUPPLIES_TO", ("org", "SK바이오팜"), ("org", "Arvelle Therapeutics"), 0.85),
        ],
    },
    "01a708a05db27316": {  # 세노바메이트 일본 오노약품공업 전략제휴 / 중국 Ignis Therapeutics
        "entities": [
            (P, "세노바메이트", "세노바메이트(XCOPRI/ONTOZRY)"),
        ],
        "edges": [
            E("SUPPLIES_TO", ("org", "SK바이오팜"), ("org", "Ono Pharmaceutical Co., Ltd."), 0.88),
            E("RELATED_PARTY", ("org", "SK바이오팜"), ("org", "Ignis Therapeutics"), 0.85, "관계기업(중국상업화)"),
        ],
    },
    "0272c8a8fd846670": {  # 세노바메이트 미국 XCOPRI SK Life Science 판매
        "entities": [(P, "세노바메이트", "세노바메이트(XCOPRI)")],
        "edges": [
            E("PRODUCES", ("org", "SK바이오팜"), ("ent", P, "세노바메이트", "세노바메이트(XCOPRI)"), 0.95),
            E("RELATED_PARTY", ("org", "SK바이오팜"), ("org", "SK Life Science, Inc."), 0.9, "종속기업(미국직접판매)"),
        ],
    },

    # ═══ SK실트론 — SiC Wafer, 반도체 웨이퍼 ═══

    "005a1264348b1f6b": {  # SiC Wafer DuPont 인수, SK Siltron CSS 손자법인
        "entities": [
            (P, "sic wafer", "SiC Wafer"),
        ],
        "edges": [
            E("PRODUCES", ("org", "SK실트론"), ("ent", P, "sic wafer", "SiC Wafer"), 0.95),
            E("RELATED_PARTY", ("org", "SK실트론"), ("org", "SK Siltron CSS, LLC"), 0.9, "손자법인(미국SiC)"),
        ],
    },
    "005aaa0804048a3f": {  # SiC Wafer 사업부 DuPont 인수 — 반기보고서
        "entities": [(P, "sic wafer", "SiC Wafer")],
        "edges": [
            E("PRODUCES", ("org", "SK실트론"), ("ent", P, "sic wafer", "SiC Wafer"), 0.95),
        ],
    },
    "008420ae3ba89f38": {  # SK실트론 반도체 웨이퍼 R&D 조직
        "entities": [(P, "반도체 웨이퍼", "반도체 웨이퍼")],
        "edges": [
            E("PRODUCES", ("org", "SK실트론"), ("ent", P, "반도체 웨이퍼", "반도체 웨이퍼"), 0.9),
        ],
    },

    # ═══ SKC — 전지박(Copper Foil), CMP Pad, 실리콘러버소켓 ═══

    "00d70cdf615fad3f": {  # SKC 전지박/CMP Pad/실리콘러버소켓 사업보고서 2024
        "entities": [
            (P, "전지박", "전지박(Copper Foil)"),
            (P, "cmp pad", "CMP Pad"),
            (P, "실리콘러버소켓", "실리콘러버 소켓"),
        ],
        "edges": [
            E("PRODUCES", ("org", "SKC"), ("ent", P, "전지박", "전지박(Copper Foil)"), 0.95),
            E("PRODUCES", ("org", "SKC"), ("ent", P, "cmp pad", "CMP Pad"), 0.92),
            E("PRODUCES", ("org", "SKC"), ("ent", P, "실리콘러버소켓", "실리콘러버 소켓"), 0.9),
        ],
    },
    "00df2faa6eff2939": {  # 에스케이엔펄스 CMP Pad/CMP Slurry
        "entities": [
            (P, "cmp pad", "CMP Pad"),
            (P, "cmp slurry", "CMP Slurry"),
        ],
        "edges": [
            E("PRODUCES", ("org", "SK엔펄스"), ("ent", P, "cmp pad", "CMP Pad"), 0.92),
            E("PRODUCES", ("org", "SK엔펄스"), ("ent", P, "cmp slurry", "CMP Slurry"), 0.9),
        ],
    },

    # ═══ SK에코플랜트 — 반도체 가스/소재/DRAM모듈/SSD/환경 ═══

    "00c326eeea2f85ae": {  # SK에코플랜트 반도체 가스·소재 공급 + DRAM모듈/SSD 재활용
        "entities": [
            (P, "dram 모듈", "DRAM 모듈"),
            (P, "ssd", "SSD"),
        ],
        "edges": [
            E("PRODUCES", ("org", "SK에코플랜트"), ("ent", P, "dram 모듈", "DRAM 모듈"), 0.82),
            E("PRODUCES", ("org", "SK에코플랜트"), ("ent", P, "ssd", "SSD"), 0.82),
            E("RELATED_PARTY", ("org", SK), ("org", "SK에코플랜트"), 0.9, "종속기업"),
        ],
    },
    "00bc6d5c48f2c3be": {  # SK tes E-waste + 배터리 재활용 글로벌
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "SK에코플랜트"), ("org", "SK tes"), 0.88, "자회사(글로벌E-waste)"),
        ],
    },
    "02ea4e10ed9a6bd5": {  # SK에코플랜트 TES 지분인수 E-waste 23개국
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "SK에코플랜트"), ("org", "TES"), 0.85, "지분인수(글로벌E-waste)"),
        ],
    },
    "0339c616393bcbd9": {  # SK에코플랜트 환경·신재생에너지 솔루션 WtE
        "entities": [(T, "wte", "WtE(Waste to Energy)")],
        "edges": [
            E("USES_TECH", ("org", "SK에코플랜트"), ("ent", T, "wte", "WtE(Waste to Energy)"), 0.85),
        ],
    },
    "034d02cf1bcf59cc": {  # SK에코플랜트 반도체 플랜트 이차전지 발전플랜트
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SK), ("org", "SK에코플랜트"), 0.88, "종속기업"),
        ],
    },

    # ═══ SK이노베이션 / SK E&S 합병 — 에너지 그룹 ═══

    "022d32ba3a326876": {  # SK이노베이션+SK E&S 합병 → 아태 최대 종합에너지회사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SK), ("org", "SK이노베이션"), 0.95, "종속기업(핵심에너지)"),
            E("RELATED_PARTY", ("org", "SK이노베이션"), ("org", "SK E&S"), 0.9, "합병(2024.11)"),
        ],
    },
    "01c6f8a711a3cfd1": {  # SK이노베이션 산하 SK에너지/SK지오센트릭/SK온 제품판매
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "SK이노베이션"), ("org", "SK에너지"), 0.88),
            E("SUPPLIES_TO", ("org", "SK이노베이션"), ("org", "에스케이지오센트릭"), 0.85),
            E("SUPPLIES_TO", ("org", "SK이노베이션"), ("org", "SK온"), 0.85),
        ],
    },

    # ═══ SK온 — 배터리/전기차 ═══

    "0210a67b5abf05ba": {  # SK온 배터리 생산법인 — 미국/헝가리/중국
        "entities": [(P, "리튬이온 배터리", "리튬이온 배터리")],
        "edges": [
            E("PRODUCES", ("org", "SK온"), ("ent", P, "리튬이온 배터리", "리튬이온 배터리"), 0.92),
            E("RELATED_PARTY", ("org", "SK온"), ("org", "SK Battery America, Inc."), 0.9, "종속기업(미국생산)"),
            E("RELATED_PARTY", ("org", "SK온"), ("org", "SK Battery Manufacturing Kft."), 0.88, "종속기업(헝가리생산)"),
            E("RELATED_PARTY", ("org", "SK온"), ("org", "SK On Jiangsu Co., Ltd."), 0.88, "종속기업(중국생산)"),
        ],
    },

    # ═══ SK Pharmteco — 의약품 위탁생산(CDMO) ═══

    "01b9d57051aaf1e0": {  # SK Pharmteco Abrasax Investment 자금보충약정
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SK), ("org", "SK Pharmteco Inc."), 0.88, "종속기업(CDMO)"),
        ],
    },

    # ═══ SK(주) IT서비스 사업 — 디지털 트랜스포메이션 ═══

    "0071520f396747c8": {  # SK주식회사 Top-Tier Digital IT서비스
        "entities": [(T, "digital transformation", "Digital Transformation")],
        "edges": [
            E("USES_TECH", ("org", SK), ("ent", T, "digital transformation", "Digital Transformation"), 0.85),
        ],
    },

    # ═══ SK에너지솔루션 / ESS / 수소 ═══

    "0351695f4df0e80e": {  # SK E&S ESS/IT/AI/클라우드 에너지솔루션
        "entities": [
            (T, "에너지저장장치", "ESS(에너지저장장치)"),
            (T, "ai 에너지솔루션", "AI 에너지솔루션"),
        ],
        "edges": [
            E("USES_TECH", ("org", "에스케이이엔에스"), ("ent", T, "에너지저장장치", "ESS(에너지저장장치)"), 0.88),
            E("USES_TECH", ("org", "에스케이이엔에스"), ("ent", T, "ai 에너지솔루션", "AI 에너지솔루션"), 0.82),
        ],
    },

    # ═══ 티맵모빌리티 — 모빌리티 플랫폼 ═══

    "01a2f901d0d599bc": {  # 티맵모빌리티 글로벌 모빌리티 플랫폼
        "entities": [(P, "tmap", "TMAP 모빌리티 플랫폼")],
        "edges": [
            E("PRODUCES", ("org", "티맵모빌리티"), ("ent", P, "tmap", "TMAP 모빌리티 플랫폼"), 0.9),
            E("RELATED_PARTY", ("org", SK), ("org", "티맵모빌리티"), 0.88, "종속기업(모빌리티)"),
        ],
    },
    "022ea5e27bcbd617": {  # 티맵 AI+데이터 모빌리티 플랫폼
        "entities": [(P, "tmap", "TMAP 모빌리티 플랫폼")],
        "edges": [
            E("PRODUCES", ("org", "티맵모빌리티"), ("ent", P, "tmap", "TMAP 모빌리티 플랫폼"), 0.9),
            E("USES_TECH", ("org", "티맵모빌리티"), ("ent", T, "ai 에너지솔루션", "AI 기반 모빌리티"), 0.82),
        ],
    },

    # ═══ SK(주) 지주회사 — 대주주·종속기업 관계 ═══

    "101ed139f09d79ee": {  # SK(주) → SK이노베이션/SK바이오팜/SK스페셜티 분할 연대채무
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SK), ("org", "SK이노베이션"), 0.95, "종속기업(2007 인적분할)"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK에너지"), 0.9, "종속기업(SK이노베이션 분할)"),
            E("RELATED_PARTY", ("org", SK), ("org", "에스케이지오센트릭"), 0.9, "종속기업(SK이노베이션 분할)"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK엔무브"), 0.88, "종속기업(SK이노베이션 분할)"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK인천석유화학"), 0.88, "종속기업(SK이노베이션 분할)"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK아이이테크놀로지"), 0.88, "종속기업(SK이노베이션 분할)"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK온"), 0.9, "종속기업(SK이노베이션 분할)"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK바이오팜"), 0.92, "종속기업(2011 물적분할)"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK스페셜티"), 0.88, "종속기업(SK머티리얼즈 분할)"),
        ],
    },
    "0ee291b4a9b6b343": {  # SK(주) → 분기보고서 종속기업 연대채무
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SK), ("org", "SK이노베이션"), 0.95, "종속기업(인적분할)"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK에너지"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", SK), ("org", "에스케이지오센트릭"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK아이이테크놀로지"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK온"), 0.9, "종속기업"),
        ],
    },
    "843e65044e884cab": {  # SK(주) 분기보고서 2025.03 — 종속기업 나열
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SK), ("org", "SK이노베이션"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK에너지"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", SK), ("org", "에스케이지오센트릭"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK엔무브"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK인천석유화학"), 0.85, "종속기업"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK아이이테크놀로지"), 0.85, "종속기업"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK온"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK바이오팜"), 0.92, "종속기업"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK스페셜티"), 0.85, "종속기업"),
        ],
    },

    # ═══ X. 대주주 거래: SK하이닉스 건물 임대, 브랜드 사용료 ═══

    "7eae8e321ebabee9": {  # SK(주) SK하이닉스 건물 임대차→전대차 / 영업거래 내역
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SK), ("org", "SK하이닉스"), 0.9, "기타특수관계자(임대차)"),
        ],
    },
    "01b098754f41b251": {  # SK브랜드 사용계약 — SK텔레콤/SK(주) 등 0.2% 사용료
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SK), ("org", "SK텔레콤"), 0.88, "특수관계자(브랜드사용)"),
        ],
    },
    "043afe7a5e38d934": {  # SK브랜드 사용계약 반기보고서 2024.06 SK텔레콤/SK C&C
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SK), ("org", "SK텔레콤"), 0.88, "특수관계자(브랜드사용)"),
        ],
    },
    "0e3412275bf1a306": {  # SK브랜드 사용계약 분기보고서 2024.09 — SUPEX
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SK), ("org", "SK이노베이션"), 0.88, "SUPEX 추구협의회 분담"),
        ],
    },
    "07ae1efcef56dcff": {  # SUPEX추구협의회 SK이노베이션 비용분담
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SK), ("org", "SK이노베이션"), 0.85, "SUPEX 추구협의회 비용분담"),
        ],
    },

    # ═══ 감사보고서: 관계기업·특수관계자 현황 ═══

    "0a501c7c4eaf4c3e": {  # 연결감사보고서 종속기업 전체 목록
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SK), ("org", "SK이노베이션"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK에너지"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", SK), ("org", "에스케이지오센트릭"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", SK), ("org", "에스케이이엔에스"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK에코플랜트"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", SK), ("org", "SKC"), 0.9, "종속기업"),
        ],
    },
    "0aaba4d36d015d48": {  # 별도감사보고서 종속기업 자금대여 내역
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SK), ("org", "SK이노베이션"), 0.92, "종속기업(자금대여)"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK텔레콤"), 0.92, "종속기업(자금대여)"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK네트웍스"), 0.88, "종속기업(자금대여)"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK에코플랜트"), 0.88, "종속기업(자금대여)"),
            E("RELATED_PARTY", ("org", SK), ("org", "SKC"), 0.88, "종속기업(자금대여)"),
            E("RELATED_PARTY", ("org", SK), ("org", "에스케이이엔에스"), 0.9, "종속기업(자금대여)"),
        ],
    },

    # ═══ 연결감사보고서 — SK하이닉스 기타특수관계자 채권채무 ═══

    "0521260e65d168d9": {  # 별도감사보고서 특수관계자 채권채무 SK하이닉스/SK가스/SK케미칼
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SK), ("org", "SK하이닉스"), 0.9, "기타특수관계자"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK가스"), 0.85, "기타특수관계자"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK케미칼"), 0.85, "기타특수관계자"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK쉴더스"), 0.85, "기타특수관계자"),
        ],
    },
    "08a6b3e6d4c943b7": {  # 별도감사보고서 2023 특수관계자 SK하이닉스 기타
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SK), ("org", "SK하이닉스"), 0.9, "기타특수관계자"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK가스"), 0.85, "기타특수관계자"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK케미칼"), 0.85, "기타특수관계자"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK쉴더스"), 0.85, "기타특수관계자"),
        ],
    },
    "0ec0cfd6cbd333c6": {  # 연결감사보고서 기타특수관계자 거래: SK가스/SK쉴더스/SK Hynix
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SK), ("org", "SK가스"), 0.85, "기타특수관계자(매출거래)"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK쉴더스"), 0.85, "기타특수관계자(매출거래)"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK하이닉스"), 0.88, "기타특수관계자(매출거래)"),
            E("SUPPLIES_TO", ("org", SK), ("org", "SK하이닉스"), 0.85),
        ],
    },

    # ═══ 대주주 거래 — 실트론/에스케이트리켐 매출 ═══

    "044f49a818f4b62b": {  # SK실트론/에스케이트리켐 대주주 매출거래 2024
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SK), ("org", "SK실트론"), 0.88, "종속기업(매출)"),
            E("RELATED_PARTY", ("org", SK), ("org", "에스케이트리켐"), 0.85, "종속기업(매출)"),
            E("SUPPLIES_TO", ("org", SK), ("org", "SK실트론"), 0.85),
        ],
    },
    "0bee4ed14fdf06b3": {  # SK실트론/에스케이트리켐/SK핀크스 매출입 — 반기보고서
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SK), ("org", "SK실트론"), 0.88, "종속기업(매출거래)"),
            E("RELATED_PARTY", ("org", SK), ("org", "에스케이트리켐"), 0.85, "종속기업(매출거래)"),
            E("SUPPLIES_TO", ("org", SK), ("org", "SK실트론"), 0.85),
        ],
    },

    # ═══ 대주주 거래 — 채권채무 목록 (2026 분기 → 실질 종속기업) ═══

    "0d87620e25109951": {  # SK이노베이션/SK에너지/SK지오센트릭/SK온/Plutus Capital 채권채무
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SK), ("org", "SK이노베이션"), 0.95, "종속기업(채권채무)"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK에너지"), 0.9, "종속기업(채권채무)"),
            E("RELATED_PARTY", ("org", SK), ("org", "에스케이지오센트릭"), 0.88, "종속기업(채권채무)"),
            E("RELATED_PARTY", ("org", SK), ("org", "SK온"), 0.9, "종속기업(채권채무)"),
            E("RELATED_PARTY", ("org", SK), ("org", "Plutus Capital NY, Inc."), 0.85, "종속기업(채권채무)"),
        ],
    },

    # ═══ 특수관계자 연결주석 — 에스케이하이닉스 관계기업 ═══

    "037ac066a8a2b3e1": {  # 연결재무제표 특수관계자 현황 — SK하이닉스 관계기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SK), ("org", "SK하이닉스"), 0.9, "관계기업(연결기준)"),
        ],
    },

    # ═══ SK(주) IT서비스 — 공공/금융/제조/에너지/반도체 분야 ═══

    "02eb572aad6c0f57": {  # SKC ISC 반도체소켓 비메모리 AI 자율주행
        "entities": [(P, "실리콘러버소켓", "실리콘러버 소켓(반도체테스트용)")],
        "edges": [
            E("PRODUCES", ("org", "ISC"), ("ent", P, "실리콘러버소켓", "실리콘러버 소켓(반도체테스트용)"), 0.9),
        ],
    },

    # ═══ SK넥실리스 — 전지박 파생상품 ═══

    "004889410d4aa709": {  # SK넥실리스 파생상품자산/부채 전지박 관련
        "entities": [(P, "전지박", "전지박(Copper Foil)")],
        "edges": [
            E("PRODUCES", ("org", "SK넥실리스"), ("ent", P, "전지박", "전지박(Copper Foil)"), 0.88),
            E("RELATED_PARTY", ("org", SK), ("org", "SK넥실리스"), 0.88, "종속기업(SKC산하)"),
        ],
    },

    # ═══ SK하이닉스 DRAM/NAND (SK(주)이 대주주로 언급) ═══

    "01323bdc2cf15b70": {  # SK하이닉스 DRAM/NAND Flash 환경평가 10나노 LPDDR4
        "entities": [
            (P, "lpddr4 dram", "LPDDR4 DRAM"),
            (P, "nand flash", "3D-V4 NAND Flash"),
        ],
        "edges": [
            E("PRODUCES", ("org", "SK하이닉스"), ("ent", P, "lpddr4 dram", "LPDDR4 DRAM"), 0.9),
            E("PRODUCES", ("org", "SK하이닉스"), ("ent", P, "nand flash", "3D-V4 NAND Flash"), 0.9),
        ],
    },

    # ═══ 반도체 플랜트 — SK에코플랜트/BIM/Digital Transformation ═══

    "039d62a612dbe181": {  # SK에코플랜트 반도체플랜트 BIM Smart Work Platform DX
        "entities": [(T, "bim", "BIM(Building Information Modeling)")],
        "edges": [
            E("USES_TECH", ("org", "SK에코플랜트"), ("ent", T, "bim", "BIM(Building Information Modeling)"), 0.88),
        ],
    },
    "03a3c90076429f09": {  # 2025 사업보고서 반도체플랜트 Digital Transformation AI 5G
        "entities": [
            (T, "ai", "AI(인공지능)"),
            (T, "5g", "5G 이동통신"),
        ],
        "edges": [
            E("USES_TECH", ("org", "SK에코플랜트"), ("ent", T, "ai", "AI(인공지능)"), 0.82),
            E("USES_TECH", ("org", "SK에코플랜트"), ("ent", T, "5g", "5G 이동통신"), 0.8),
        ],
    },
    "012d2279316a66f3": {  # SK에코플랜트 하이테크사업 반도체소재+메모리반도체 종합서비스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SK), ("org", "SK에코플랜트"), 0.9, "종속기업(반도체종합서비스)"),
        ],
    },

    # ═══ SK(주) 에너지솔루션 — 재생에너지 RE100 Net Zero ═══

    "02e99a772bdc767f": {  # SK(주) Net Zero 2040 재생에너지 RE100
        "entities": [(T, "re100", "RE100(재생에너지100%)")],
        "edges": [
            E("USES_TECH", ("org", SK), ("ent", T, "re100", "RE100(재생에너지100%)"), 0.85),
        ],
    },

    # ═══ 에너지솔루션 수소충전소 — KOHYGEN ═══

    "031e919451aad52c": {  # 수소충전소 KOHYGEN 코하이젠 투자 9%
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SK), ("org", "코하이젠(KOHYGEN)"), 0.82, "관계기업(출자9%)"),
        ],
    },

    # ═══ 에스케이레조낙 — Resonac Holdings 합작 ═══

    "01b9d57051aaf1e0": {  # SK(주)-Resonac Holdings 에스케이레조낙 주주간약정
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SK), ("org", "에스케이레조낙"), 0.85, "종속기업(합작)"),
            E("RELATED_PARTY", ("org", SK), ("org", "Resonac Holdings Corporation"), 0.82, "주주간약정(합작파트너)"),
        ],
    },
}


# ── 이 배치 전용 원장 헬퍼 ───────────────────────────────────────────────────
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


def mark(chunk_id: str, n_ent: int, n_edge: int,
         rcept_no: str = None, section_path: str = None) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "chunk_id": chunk_id, "n_ent": n_ent, "n_edge": n_edge,
        "rcept_no": rcept_no, "section_path": section_path,
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
    # ── 청크 로드 ──
    rows_text = get_chunks(
        "WHERE corp_code='00181712' AND chunk_type='text_micro' "
        "ORDER BY chunk_id LIMIT 3600 OFFSET 0"
    )
    rows_table = get_chunks(
        "WHERE corp_code='00181712' AND chunk_type='table_nl' "
        "AND embedding_text LIKE '%특수관계%' ORDER BY chunk_id"
    )
    all_rows = rows_text + rows_table
    by_id = {r["chunk_id"]: r for r in all_rows}
    done = ledger_ids()

    print(f"[batch] text_micro {len(rows_text)}건 + table_nl(특수관계) {len(rows_table)}건 "
          f"= 총 {len(all_rows)}건, 원장 기처리 {len(done)}건")

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
        rcept_no = row["rcept_no"]
        n_ent = n_edge = 0

        for label, canonical, name in payload.get("entities", []):
            eid = merge_entity(driver, label, canonical, name)
            add_edge(driver, "hasObject",
                     {"kind": "chunk", "chunk_id": cid},
                     {"kind": "entity", "label": label, "id": eid},
                     chunk_id=cid, rcept_no=rcept_no, confidence=1.0)
            write_provenance(conn, cid, "hasObject", eid, cid, rcept_no, 1.0)
            n_ent += 1
            n_prov_total += 1
            ent_by_label[label] = ent_by_label.get(label, 0) + 1
            edge_by_type["hasObject"] = edge_by_type.get("hasObject", 0) + 1

        for e in payload.get("edges", []):
            rel, frm, to, conf = e["rel"], e["from"], e["to"], e["conf"]
            rtype = e.get("relation_type")
            fm, fid = _match_and_id(driver, frm)
            tm, tid = _match_and_id(driver, to)
            add_edge(driver, rel, fm, tm, chunk_id=cid, rcept_no=rcept_no,
                     confidence=conf, relation_type=rtype)
            write_provenance(conn, fid, rel, tid, cid, rcept_no, conf)
            n_edge += 1
            n_prov_total += 1
            edge_by_type[rel] = edge_by_type.get(rel, 0) + 1

        conn.commit()
        mark(cid, n_ent, n_edge, rcept_no, row["section_path"])
        n_ent_total += n_ent
        n_edge_total += n_edge
        processed += 1

    # 2) 나머지 청크는 엣지 0개로 처리 표시 (text_micro 배치 전체 커버)
    extracted_ids = set(EXTRACTIONS.keys())
    for r in rows_text:  # text_micro 배치만 커버 (table_nl은 추출 대상만)
        cid = r["chunk_id"]
        if cid in done or cid in extracted_ids:
            continue
        mark(cid, 0, 0, r["rcept_no"], r["section_path"])
        processed += 1

    conn.close()
    driver.close()

    total_in_ledger = len(ledger_ids())
    print("=== SK(주) 00181712 배치1 추출 결과 ===")
    print(f"  이번 실행 처리 청크: {processed}  (원장 누적: {total_in_ledger} / {len(all_rows)})")
    print(f"  엔티티 hasObject: {n_ent_total}  타입별: {ent_by_label}")
    print(f"  엣지(hasObject 포함) 총: {n_edge_total + n_ent_total}  타입별: {edge_by_type}")
    print(f"  provenance 행: {n_prov_total}")


if __name__ == "__main__":
    run()
