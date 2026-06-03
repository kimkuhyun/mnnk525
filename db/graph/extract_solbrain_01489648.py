"""Stage 5 비정형 추출 — 솔브레인 corp_code=01489648, text_micro 전체(~768) + table_nl 특수관계.

솔브레인 = 반도체·디스플레이·2차전지 공정용 화학 소재 전문업체.
주력 제품: 반도체 식각액(Wet Etchant), CMP 슬러리, 반도체 세정액, 디스플레이 소재, 2차전지 전해액, 고순도 인산
주요 매출처: 삼성전자, SK하이닉스, 삼성디스플레이, LG디스플레이, 삼성SDI, SK이노베이션(SK온), LG에너지솔루션, LG화학
최대주주: 솔브레인홀딩스(주) (유의적 영향력 행사 기업)
종속기업: 솔브레인라사(주), Soulbrain (Xi'an) Electronic Materials Co.,Ltd., SOULBRAIN TX LLC,
          SOULBRAIN RASA TX LLC, 나우혁신소재펀드1호, 케어웰솔루션스(주)
관계기업: (주)디엔에프
기타 특수관계자: 솔브레인에스엘디(주), 솔브레인옵토스(주), 엠씨솔루션(주), Soulbrain MI Inc.,
                 Soulbrain HU Kft., 솔브레인네트워크(주), 나우아이비캐피탈(주), 머티리얼즈파크(주),
                 (주)씨엠디엘, 에스비노브스(주), (주)비즈네트웍스, 더블유에스씨에이치(주), 우양에이치씨(주)
해외 현지법인: 솔브레인(시안)전자재료유한공사(중국), SOULBRAIN TX LLC(미국)

원장 = db/graph/ledger/extra28_01489648.jsonl (이 추출 전용).
실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_solbrain_01489648.py
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

CORP = "솔브레인"
CORP_CODE = "01489648"

# 전용 원장
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_DIR.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = LEDGER_DIR / "extra28_01489648.jsonl"


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


def mark_processed(chunk_id, n_ent, n_edge, rcept_no=None, section_path=None):
    rec = {
        "chunk_id": chunk_id, "n_ent": n_ent, "n_edge": n_edge,
        "rcept_no": rcept_no, "section_path": section_path,
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


# ── Claude 추출 결과 (청크별) ──────────────────────────────────────────────
# from/to = ('org', 회사명) | ('ent', label, canonical, name)
#
# 솔브레인 핵심 사업:
#   Product: 반도체 식각액, CMP 슬러리, 반도체 세정액, 디스플레이 소재, 2차전지 전해액, 고순도 인산
#   Technology: 반도체 공정소재 기술, 2차전지 전해액 기술
#   SUPPLIES_TO: 솔브레인→삼성전자/SK하이닉스/삼성디스플레이/LG디스플레이/삼성SDI/SK온/LG에너지솔루션

EXTRACTIONS: dict[str, dict] = {

    # ═══ II. 사업의 내용: 사업 개요 (2023 사업보고서) ═══

    "6ec38acb6d3512a2": {  # 2023 사업보고서: 반도체/디스플레이/2차전지 소재 생산. 매출처=삼성전자, SK하이닉스, LG디스플레이, 삼성SDI.
        "entities": [
            (P, "반도체공정소재", "반도체 공정용 화학 소재"),
            (P, "디스플레이소재", "디스플레이 공정용 화학 소재"),
            (P, "2차전지전해액", "2차전지 전해액"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체공정소재", "반도체 공정용 화학 소재"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "디스플레이소재", "디스플레이 공정용 화학 소재"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "2차전지전해액", "2차전지 전해액"), 0.95),
        ],
    },

    "6c07537445788851": {  # 2023 사업보고서: 주요 매출처=삼성전자, SK하이닉스, LG디스플레이, 삼성SDI.
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG디스플레이"), 0.92),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성SDI"), 0.90),
        ],
    },

    "df453c5bf342d142": {  # 2023 사업보고서: 시장의 특성 - 삼성전자, 삼성디스플레이, SK하이닉스, LG디스플레이, 삼성SDI, SK이노베이션, LG화학 공급.
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG디스플레이"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성SDI"), 0.88),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK이노베이션"), 0.85),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG화학"), 0.85),
        ],
    },

    "f5394118c8ecd7f8": {  # 2023 사업보고서: 솔브레인(시안)전자재료유한공사(중국), 솔브레인라사(고순도 인산), SOULBRAIN TX LLC(미국) 설립.
        "entities": [
            (P, "고순도인산", "반도체용 고순도 인산"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "고순도인산", "반도체용 고순도 인산"), 0.88),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인라사"), 0.95, "종속기업(고순도 인산 생산·판매)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인(시안)전자재료유한공사"), 0.95, "종속기업(중국, 반도체 공정소재 생산·판매)"),
        ],
    },

    "479e247d272a6668": {  # 2023 사업보고서: 2차전지 전해액 생산·판매. 2차전지 소재 경쟁력.
        "entities": [
            (P, "2차전지전해액", "2차전지 전해액"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "2차전지전해액", "2차전지 전해액"), 0.97),
        ],
    },

    # ═══ II. 사업의 내용 (2024.03 분기보고서) ═══

    "fa59799511cbce66": {  # 2024 1Q: 반도체/디스플레이/2차전지 소재 생산. 매출 210,710백만원.
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG디스플레이"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성SDI"), 0.88),
        ],
    },

    "4fef264764874979": {  # 2024 1Q: 주요 매출처=삼성전자, SK하이닉스, LG디스플레이, 삼성SDI.
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG디스플레이"), 0.92),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성SDI"), 0.90),
        ],
    },

    "81c6b8069f58b486": {  # 2024 1Q: 시장의 특성 - 삼성전자, 삼성디스플레이, SK하이닉스, LG디스플레이, 삼성SDI, SK이노베이션, LG화학 공급.
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG디스플레이"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성SDI"), 0.88),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK이노베이션"), 0.85),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG화학"), 0.85),
        ],
    },

    # ═══ II. 사업의 내용 (2024.06 반기보고서) ═══

    "c62ed92041de4254": {  # 2024 반기: 매출 426,990백만원, 반도체 소재 319,705백만원(75%). 주요 매출처=삼성전자/SK하이닉스/LG디스플레이/삼성SDI.
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG디스플레이"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성SDI"), 0.88),
        ],
    },

    "2131dfd8a32adcb4": {  # 2024 반기: 시장의 특성 - 삼성전자, 삼성디스플레이, SK하이닉스, LG디스플레이 공급. 삼성SDI, SK이노베이션, LG화학 2차전지.
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG디스플레이"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성SDI"), 0.88),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK이노베이션"), 0.85),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG화학"), 0.85),
        ],
    },

    # ═══ II. 사업의 내용 (2024.09 분기보고서) ═══

    "fd0893e35c5a4fef": {  # 2024 3Q: 매출 646,893백만원, 반도체 소재 487,384백만원(75%).
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG디스플레이"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성SDI"), 0.88),
        ],
    },

    "e1be834a20e688fd": {  # 2024 3Q: 시장의 특성 - 삼성전자/삼성디스플레이/SK하이닉스/LG디스플레이/삼성SDI/SK이노베이션/LG화학 공급.
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG디스플레이"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성SDI"), 0.88),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK이노베이션"), 0.85),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG화학"), 0.85),
        ],
    },

    "ad0ad0544803d891": {  # 2024 3Q: 솔브레인(시안)전자재료, 솔브레인라사, SOULBRAIN TX LLC, SOULBRAIN RASA TX LLC 설립.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인라사"), 0.95, "종속기업(고순도 인산 생산·판매)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인(시안)전자재료유한공사"), 0.95, "종속기업(중국, 반도체 공정소재 생산·판매)"),
        ],
    },

    # ═══ II. 사업의 내용 (2024.12 사업보고서) ═══

    "918704d6f8ffd2f9": {  # 2024 사업보고서: 매출 863,356백만원, 반도체 656,659백만원(76%).
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG디스플레이"), 0.88),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성SDI"), 0.87),
        ],
    },

    "265afbf24604e3bb": {  # 2024 사업보고서: 삼성전자/SK하이닉스/삼성디스플레이/LG디스플레이 반도체·디스플레이 소재 공급. 삼성SDI/SK온/LG에너지솔루션 2차전지 소재 공급.
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG디스플레이"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성SDI"), 0.88),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK온"), 0.87),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG에너지솔루션"), 0.85),
        ],
    },

    "40252d55cfb2b36f": {  # 2024 사업보고서: 시장의 특성 - 삼성전자/삼성디스플레이/SK하이닉스/LG디스플레이/삼성SDI/SK이노베이션/LG화학 공급.
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG디스플레이"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성SDI"), 0.88),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK이노베이션"), 0.85),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG화학"), 0.85),
        ],
    },

    "84f2da56fce8246b": {  # 2024 사업보고서: 솔브레인라사, SOULBRAIN TX LLC, SOULBRAIN RASA TX LLC 운영.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인라사"), 0.95, "종속기업"),
        ],
    },

    # ═══ II. 사업의 내용 (2025.03 분기보고서) ═══

    "569e9cb148b77720": {  # 2025 1Q: 솔브레인라사, 솔브레인(시안)전자재료유한공사, SOULBRAIN TX LLC, SOULBRAIN RASA TX LLC.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인라사"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인(시안)전자재료유한공사"), 0.95, "종속기업(중국)"),
        ],
    },

    "36b86cae647d8938": {  # 2025 1Q: 시장의 특성 - 삼성전자/삼성디스플레이/SK하이닉스/LG디스플레이/삼성SDI/SK이노베이션/LG화학 공급.
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG디스플레이"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성SDI"), 0.88),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK이노베이션"), 0.85),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG화학"), 0.85),
        ],
    },

    # ═══ II. 사업의 내용 (2025.06 반기보고서) ═══

    "9ce35b858c3c30fe": {  # 2025 반기: 반도체 부문 매출 81%, 디스플레이 9%, 2차전지 7%. 삼성전자/SK하이닉스/삼성디스플레이/LG디스플레이/삼성SDI/SK온/LG에너지솔루션 공급.
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG디스플레이"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성SDI"), 0.87),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK온"), 0.87),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG에너지솔루션"), 0.85),
        ],
    },

    # ═══ II. 사업의 내용 (2025.09 분기보고서) ═══

    "73ca36adf6cdefa8": {  # 2025 3Q: 솔브레인라사, 솔브레인(시안)전자재료유한공사, SOULBRAIN TX LLC, SOULBRAIN RASA TX LLC 운영.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인라사"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인(시안)전자재료유한공사"), 0.95, "종속기업(중국)"),
        ],
    },

    "177bb97b54c268ba": {  # 2025 3Q: 시장의 특성 - 삼성전자/삼성디스플레이/SK하이닉스/LG디스플레이/삼성SDI/SK이노베이션/LG화학 공급.
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG디스플레이"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성SDI"), 0.88),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK이노베이션"), 0.85),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG화학"), 0.85),
        ],
    },

    "01abe65776463630": {  # 2025 3Q: 솔브레인(시안)전자재료유한공사 - 해외거점 현지 고객사 대응.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인(시안)전자재료유한공사"), 0.93, "종속기업(해외 현지법인, 중국)"),
        ],
    },

    # ═══ II. 사업의 내용 (2025.12 사업보고서) ═══

    "1b4fcdef074c6050": {  # 2025 사업보고서: 반도체/디스플레이/2차전지 소재 생산.
        "entities": [
            (P, "반도체공정소재", "반도체 공정용 화학 소재"),
            (P, "디스플레이소재", "디스플레이 공정용 화학 소재"),
            (P, "2차전지전해액", "2차전지 전해액"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체공정소재", "반도체 공정용 화학 소재"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "디스플레이소재", "디스플레이 공정용 화학 소재"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "2차전지전해액", "2차전지 전해액"), 0.95),
        ],
    },

    "0895b061a0d3ff91": {  # 2026 1Q: 시장의 특성 - 삼성전자/SK하이닉스/삼성디스플레이/LG디스플레이/삼성SDI/SK온/LG에너지솔루션 공급.
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG디스플레이"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성SDI"), 0.88),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK온"), 0.87),
            E("SUPPLIES_TO", ("org", CORP), ("org", "LG에너지솔루션"), 0.85),
        ],
    },

    "0ef0555e1a207cb3": {  # 2026 1Q: 솔브레인라사, SOULBRAIN TX LLC, SOULBRAIN RASA TX LLC 해외법인 운영.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인라사"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인(시안)전자재료유한공사"), 0.93, "종속기업(중국)"),
        ],
    },

    # ═══ IV. 이사의 경영진단 및 분석의견: 2차전지 전해액 ═══

    "22aec3ba62e13819": {  # 2023 사업보고서 IV: 2차전지 전해액 생산·판매. 2차전지 수요 성장성.
        "entities": [
            (P, "2차전지전해액", "2차전지 전해액"),
            (T, "전해액소재기술", "2차전지 전해액 소재 기술"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "2차전지전해액", "2차전지 전해액"), 0.97),
            E("USES_TECH", ("org", CORP), ("ent", T, "전해액소재기술", "2차전지 전해액 소재 기술"), 0.90),
        ],
    },

    "6b6a522b0851062c": {  # 2024 사업보고서 IV: 2차전지 전해액 생산·판매. 전해액 핵심경쟁력.
        "entities": [
            (P, "2차전지전해액", "2차전지 전해액"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "2차전지전해액", "2차전지 전해액"), 0.97),
        ],
    },

    "350390caf943ae10": {  # 2025 사업보고서 IV: 2차전지 전해액 생산·판매.
        "entities": [
            (P, "2차전지전해액", "2차전지 전해액"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "2차전지전해액", "2차전지 전해액"), 0.97),
        ],
    },

    # ═══ 감사보고서/연결감사보고서: 회사 개요 (반도체 FPD 화학재료, 이차전지 전해액) ═══

    "0ce77c2ac288ca7d": {  # 2023 감사보고서: 반도체 FPD 공정용 화학재료, 이차전지 전해액 제조·판매. 솔브레인홀딩스에서 인적분할 설립.
        "entities": [
            (P, "반도체FPD공정화학재료", "반도체 및 FPD 공정용 화학재료"),
            (P, "2차전지전해액", "2차전지 전해액"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체FPD공정화학재료", "반도체 및 FPD 공정용 화학재료"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "2차전지전해액", "2차전지 전해액"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인홀딩스"), 0.97, "유의적 영향력을 행사하는 기업(최대주주, 인적분할 모회사)"),
        ],
    },

    "27ad504423ba580f": {  # 2023 감사보고서 재무제표주석: 반도체 FPD 공정용 화학재료, 이차전지 전해액 제조·판매. KOSDAQ 등록.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인홀딩스"), 0.97, "유의적 영향력을 행사하는 기업(최대주주)"),
        ],
    },

    "64bd1408947e6568": {  # 2023 연결감사보고서: 지배기업 솔브레인, 반도체 FPD 화학재료 이차전지 전해액. 솔브레인홀딩스에서 인적분할.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인홀딩스"), 0.97, "유의적 영향력을 행사하는 기업(인적분할 모회사)"),
        ],
    },

    "4a781e6e459403a9": {  # 2023 연결재무제표주석: 반도체 FPD 공정용 화학재료, 이차전지 전해액 제조·판매. 솔브레인홀딩스에서 분할 설립.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인홀딩스"), 0.97, "유의적 영향력을 행사하는 기업"),
        ],
    },

    "8cfbe4bfdd9611d9": {  # 2024 감사보고서: 반도체 FPD 공정용 화학재료, 이차전지 전해액. 솔브레인홀딩스 인적분할.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인홀딩스"), 0.97, "유의적 영향력을 행사하는 기업(최대주주)"),
        ],
    },

    "b3c2ad97bf386e9f": {  # 2024 연결감사보고서: 반도체 FPD 화학재료 이차전지 전해액. 솔브레인홀딩스 분할.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인홀딩스"), 0.97, "유의적 영향력을 행사하는 기업"),
        ],
    },

    "226b7d6271490b1d": {  # 2025 감사보고서: 반도체 FPD 공정용 화학재료, 이차전지 전해액. 솔브레인홀딩스 인적분할 설립.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인홀딩스"), 0.97, "유의적 영향력을 행사하는 기업(최대주주)"),
        ],
    },

    # ═══ X. 대주주 등과의 거래내용 — 특수관계 목록 표 ═══

    "61f987774379fa4f": {  # 2023 연결감사보고서: 특수관계자 목록. 관계기업=(주)디엔에프, 기타=솔브레인옵토스/에스엘디/에스비노브스/비즈네트웍스/Soulbrain MI Inc./E&I Malaysia 등.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "디엔에프"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인옵토스"), 0.85, "기타 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인에스엘디"), 0.85, "기타 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에스비노브스"), 0.83, "기타 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "비즈네트웍스"), 0.83, "기타 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Soulbrain MI Inc."), 0.83, "기타 특수관계자"),
        ],
    },

    "7917e02c03ea23c7": {  # 2023 연결재무제표주석: 특수관계자 목록. 관계기업=디엔에프, 기타=솔브레인옵토스/에스엘디/에스비노브스/비즈네트웍스/Soulbrain MI Inc. 등.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "디엔에프"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인옵토스"), 0.85, "기타 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인에스엘디"), 0.85, "기타 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Soulbrain MI Inc."), 0.83, "기타 특수관계자"),
        ],
    },

    "2ceba835aec3d842": {  # 2023 연결감사보고서 특수관계 거래: 솔브레인홀딩스(유형자산), 솔브레인옵토스(매출), 에스엘디(매출), 엠씨솔루션(재고자산 매입), Soulbrain MI Inc.(매출) 거래.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인홀딩스"), 0.97, "유의적 영향력을 행사하는 기업(유형자산 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인옵토스"), 0.85, "기타 특수관계자(매출 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인에스엘디"), 0.87, "기타 특수관계자(매출 25,204백만원 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엠씨솔루션"), 0.85, "기타 특수관계자(재고자산 49,279백만원 매입)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Soulbrain MI Inc."), 0.85, "기타 특수관계자(매출 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "머티리얼즈파크"), 0.83, "기타 특수관계자(매출 거래)"),
        ],
    },

    "74558dcd8feec683": {  # 2023 연결재무제표주석 특수관계 거래: 솔브레인홀딩스(유형자산), 솔브레인옵토스(매출), 에스엘디(매출), 엠씨솔루션(재고자산), Soulbrain MI Inc.(매출) 등.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인홀딩스"), 0.97, "유의적 영향력 행사(유형자산 매입 33,943백만원)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인옵토스"), 0.85, "기타 특수관계자(매출 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인에스엘디"), 0.87, "기타 특수관계자(매출 거래)"),
        ],
    },

    "6b9a90326b3f5faf": {  # 2023 X. 대주주와의 거래: 솔브레인홀딩스(유형자산), 솔브레인라사(재고자산 74,463백만원 매입), 솔브레인(시안)(매출 43,884백만원).
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인홀딩스"), 0.97, "유의적 영향력 행사(유형자산 매입)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인라사"), 0.97, "종속기업(재고자산 74,463백만원 매입)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인(시안)전자재료유한공사"), 0.95, "종속기업(매출 43,884백만원)"),
        ],
    },

    "a61602bd576f762c": {  # 2023 X. 특수관계 거래: 나우아이비캐피탈(기타매입), 솔브레인네트워크(매출).
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "나우아이비캐피탈"), 0.83, "기타 특수관계자(기타 매입 200백만원)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인네트워크"), 0.83, "기타 특수관계자(매출 거래)"),
        ],
    },

    "91e9471aca878e66": {  # 2023 X. 특수관계 거래: 더블유에스씨에이치, 씨엠디엘(매출+유형자산+재고자산), 우양에이치씨.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "더블유에스씨에이치"), 0.80, "기타 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "씨엠디엘"), 0.83, "기타 특수관계자(매출+재고자산 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "우양에이치씨"), 0.80, "기타 특수관계자"),
        ],
    },

    "1649170ed4d4ea00": {  # 2023 감사보고서 채권채무: 솔브레인홀딩스(채권346백만/채무582백만), 솔브레인라사(채권+채무 거래).
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인홀딩스"), 0.97, "유의적 영향력 행사(채권채무 잔액)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인라사"), 0.97, "종속기업(채권채무 잔액)"),
        ],
    },

    "20db63faef6ed745": {  # 2023 연결재무제표주석 채권채무: 솔브레인홀딩스(채권346+채무586), Soulbrain HU Kft.(채권).
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인홀딩스"), 0.97, "유의적 영향력 행사(채권채무)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Soulbrain HU Kft."), 0.83, "기타 특수관계자(채권 잔액)"),
        ],
    },

    "2933b147e85310f0": {  # 2023 X. 현금출자/배당: SOULBRAIN TX LLC(현금출자), 솔브레인라사(현금출자+배당), 솔브레인(시안)(배당), 디엔에프(현금출자).
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인라사"), 0.97, "종속기업(현금출자+배당금 수익)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인(시안)전자재료유한공사"), 0.95, "종속기업(배당금 수익)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "디엔에프"), 0.90, "관계기업(현금출자 127,100백만원)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "나우혁신소재펀드1호"), 0.85, "종속기업(현금출자)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케어웰솔루션스"), 0.85, "종속기업(현금출자)"),
        ],
    },

    "31a1326f5b64fcb7": {  # 2023 X. 솔브레인홀딩스 파주2공장 자산양수도: 339억원 매입.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인홀딩스"), 0.97, "유의적 영향력 행사(자산양수도 339억원)"),
        ],
    },

    # ═══ 특수관계 관련 table_nl (III. 재무제표주석) — 2024.03 분기 ═══

    "068853d27daffbc4": {  # 2024 3Q 연결재무제표주석: 특수관계 거래표 (솔브레인홀딩스/솔브레인라사/솔브레인(시안)/엠씨솔루션 거래).
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인홀딩스"), 0.95, "유의적 영향력 행사(채권채무 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인라사"), 0.97, "종속기업(재고자산 매입 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엠씨솔루션"), 0.85, "기타 특수관계자(재고자산 매입 거래)"),
        ],
    },

    "07185a2021d942fd": {  # 2024 반기 연결재무제표주석: 특수관계 채권채무. 솔브레인홀딩스/Soulbrain HU Kft. 포함.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인홀딩스"), 0.97, "유의적 영향력 행사(채권채무)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Soulbrain HU Kft."), 0.83, "기타 특수관계자(채권 거래)"),
        ],
    },

    "01f612d4550a19a7": {  # 2024 반기 X. 대주주 거래 table_nl: Soulbrain MI Inc. 매출채권. 계열사 집합채권.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Soulbrain MI Inc."), 0.83, "기타 특수관계자(매출채권 잔액)"),
        ],
    },

    "1104796cb4172f25": {  # 2025 3Q X. 대주주 거래 table_nl: 특수관계 거래.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인홀딩스"), 0.97, "유의적 영향력 행사"),
        ],
    },

    "03d4e3e9cd5fcf35": {  # 2025 반기 X. 특수관계 table_nl: 거래 내역.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인홀딩스"), 0.97, "유의적 영향력 행사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인라사"), 0.97, "종속기업"),
        ],
    },

    # ═══ 0095fb8b2574bf12 — 2024.12 감사보고서: 특수관계 목록표 ═══

    "0095fb8b2574bf12": {  # 2024 감사보고서 특수관계자 목록: 솔브레인홀딩스(유의적 영향력)/솔브레인라사/솔브레인(시안)/SOULBRAIN TX LLC/디엔에프/솔브레인옵토스/에스엘디/Soulbrain MI Inc./HU Kft./엠씨솔루션/머티리얼즈파크 등.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인홀딩스"), 0.97, "유의적 영향력을 행사하는 기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인라사"), 0.97, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인(시안)전자재료유한공사"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "디엔에프"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인옵토스"), 0.85, "기타 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인에스엘디"), 0.87, "기타 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Soulbrain MI Inc."), 0.83, "기타 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Soulbrain HU Kft."), 0.83, "기타 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엠씨솔루션"), 0.85, "기타 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "머티리얼즈파크"), 0.83, "기타 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "나우아이비캐피탈"), 0.82, "기타 특수관계자"),
        ],
    },

    # ═══ 0325d7886d37af5d — 2025.12 연결감사보고서: 특수관계 채권채무 ═══

    "0325d7886d37af5d": {  # 2025 연결감사보고서: 특수관계 채권채무 table_nl. 솔브레인홀딩스/솔브레인라사/HU Kft. 포함.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인홀딩스"), 0.97, "유의적 영향력 행사(채권채무 잔액)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인라사"), 0.95, "종속기업(채권채무)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Soulbrain HU Kft."), 0.83, "기타 특수관계자(채권 잔액)"),
        ],
    },

    # ═══ 연결감사보고서/연결재무제표주석 2025.12 — 특수관계 거래/목록 ═══

    "1a752be1ed48b583": {  # 2024.12 연결감사보고서: 특수관계 채권채무 table_nl.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인홀딩스"), 0.97, "유의적 영향력 행사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Soulbrain HU Kft."), 0.83, "기타 특수관계자"),
        ],
    },

    "0eac4df0623c1924": {  # 2025 분기보고서 재무제표주석: 특수관계 table_nl.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인홀딩스"), 0.97, "유의적 영향력 행사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인라사"), 0.97, "종속기업"),
        ],
    },

    "024a9908cccb647a": {  # 2025 1Q 연결재무제표주석: 특수관계 table_nl.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인홀딩스"), 0.97, "유의적 영향력 행사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인라사"), 0.97, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엠씨솔루션"), 0.85, "기타 특수관계자"),
        ],
    },

    "09ea6516f0d1d05c": {  # 2026 1Q 별도재무제표주석: 특수관계 table_nl.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인홀딩스"), 0.97, "유의적 영향력 행사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "솔브레인라사"), 0.97, "종속기업"),
        ],
    },

}


# ── 메인 실행 로직 ─────────────────────────────────────────────────────────
def main():
    print(f"[솔브레인 비정형 추출] CORP={CORP}, CORP_CODE={CORP_CODE}")
    driver = neo4j_driver()
    conn = mariadb_conn()

    already = ledger_processed_ids()
    print(f"  원장 기처리: {len(already)}개")

    import pymysql.cursors
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        "SELECT chunk_id, rcept_no, section_path, chunk_type, embedding_text "
        "FROM chunk_index "
        "WHERE corp_code=%s "
        "AND (chunk_type='text_micro' OR (chunk_type='table_nl' AND embedding_text LIKE '%%특수관계%%')) "
        "ORDER BY chunk_id",
        (CORP_CODE,),
    )
    all_chunks = {r["chunk_id"]: r for r in cur.fetchall()}
    cur.close()
    print(f"  DB 청크수: {len(all_chunks)}")

    extraction_chunk_ids = set(EXTRACTIONS.keys())
    total_ent = 0
    total_edge = 0
    processed_count = 0
    edge_by_type: dict[str, int] = {}

    for chunk_id, data in EXTRACTIONS.items():
        if chunk_id in already:
            continue
        row = all_chunks.get(chunk_id)
        if row is None:
            print(f"  [warn] {chunk_id} DB에 없음 -- 원장 기록 후 스킵")
            mark_processed(chunk_id, 0, 0, None, None)
            continue
        rcept_no = row["rcept_no"]
        section_path = row["section_path"]

        n_ent = 0
        n_edge = 0

        # 엔티티 MERGE + hasObject 엣지
        eid_map: dict[tuple, str] = {}
        for label, canonical, name in data.get("entities", []):
            eid = merge_entity(driver, label, canonical, name=name)
            eid_map[(label, canonical)] = eid
            # hasObject edge: Chunk -> Entity
            add_edge(
                driver, "hasObject",
                {"kind": "chunk", "chunk_id": chunk_id},
                {"kind": "entity", "label": label, "id": eid},
                chunk_id=chunk_id, rcept_no=rcept_no, confidence=1.0,
            )
            write_provenance(conn, chunk_id, "hasObject", eid, chunk_id, rcept_no, 1.0)
            n_ent += 1

        # 엣지 MERGE
        for ed in data.get("edges", []):
            rel_type = ed["rel"]
            conf = ed["conf"]
            relation_type = ed.get("relation_type")

            def resolve_match(spec):
                kind = spec[0]
                if kind == "org":
                    org_name = spec[1]
                    org = resolve_org(org_name)
                    if org is None:
                        return None
                    merge_org_node(driver, org)
                    return {"kind": "org", "org": org}
                elif kind == "ent":
                    _, lbl, canonical, _ = spec
                    eid = eid_map.get((lbl, canonical))
                    if eid is None:
                        eid = merge_entity(driver, lbl, canonical)
                    return {"kind": "entity", "label": lbl, "id": eid}
                return None

            from_match = resolve_match(ed["from"])
            to_match = resolve_match(ed["to"])
            if from_match is None or to_match is None:
                print(f"  [warn] {chunk_id} resolve_match 실패: {ed}")
                continue

            add_edge(
                driver, rel_type, from_match, to_match,
                chunk_id, rcept_no, conf,
                relation_type=relation_type,
            )

            sub_id = from_match["org"]["id"] if from_match["kind"] == "org" else from_match["id"]
            obj_id = to_match["org"]["id"] if to_match["kind"] == "org" else to_match["id"]
            write_provenance(conn, sub_id, rel_type, obj_id, chunk_id, rcept_no, conf)
            conn.commit()
            n_edge += 1
            edge_by_type[rel_type] = edge_by_type.get(rel_type, 0) + 1

        mark_processed(chunk_id, n_ent, n_edge, rcept_no, section_path)
        total_ent += n_ent
        total_edge += n_edge
        processed_count += 1

    # 추출 대상 이외의 청크 = mark_processed(n_ent=0, n_edge=0)
    for chunk_id, row in all_chunks.items():
        if chunk_id in already or chunk_id in extraction_chunk_ids:
            continue
        mark_processed(chunk_id, 0, 0, row["rcept_no"], row["section_path"])

    driver.close()
    conn.close()

    total_marked = len(ledger_processed_ids())
    print(f"=== 솔브레인 Stage5 추출 결과 ===")
    print(f"  이번 처리 청크: {processed_count}  (원장 누적 {total_marked} / 대상 {len(all_chunks)})")
    print(f"  엔티티(Product/Tech) + hasObject: {total_ent}")
    print(f"  엣지 총: {total_edge}  타입별: {edge_by_type}")
    print(f"  원장: {LEDGER_PATH}")


if __name__ == "__main__":
    main()
