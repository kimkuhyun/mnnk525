"""Stage 5 비정형 추출 -- 케이씨텍 corp_code=01261893, text_micro 전체(~479) + table_nl 특수관계(~165).

케이씨텍 = 반도체 장비(CMP, Wet Cleaning System) + 디스플레이 장비(Wet Station, Coater 등) + 소재(Ceria Slurry, Silica Slurry, Zirconia, Hollow Silica) 제조사.
2017년 11월 1일 (주)케이씨로부터 인적분할 신설.
주요 매출처: 삼성전자, SK하이닉스 (10% 초과 단일 외부고객 (가)(나)).
최대주주: (주)케이씨 (2023년 29.80%, 2025년 34.35%).
특수관계자: (주)케이씨이앤씨, (주)케이씨인더스트리얼, (주)케이씨이노베이션,
  KC Precision Equipment Maintenance (Wuxi) Co., Ltd., 스타트업 코리아 케이씨 초격차펀드,
  KCTech America Inc.(종속기업), (주)케이씨솔루션, (주)케이씨투자파트너스, (주)케이씨파츠텍.
2025년부터 연결 종속기업: KCTech America Inc. 추가.
2025년 연결 매출액 3,828억원. 반도체부문 3,457억원, 디스플레이부문 370억원.

원장 = db/graph/ledger/extra28_01261893.jsonl (이 추출 전용).
실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_kctech_extra28.py
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

CORP = "케이씨텍"
CORP_CODE = "01261893"

# -- 전용 원장 -----------------------------------------------------------------
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_DIR.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = LEDGER_DIR / "extra28_01261893.jsonl"


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


# -- Claude 추출 결과 (청크별) ---------------------------------------------------
# from/to = ('org', 회사명) | ('ent', label, canonical, name)
#
# 케이씨텍 핵심사업:
#   반도체 장비: CMP(화학기계적 평탄화), Wet Cleaning System
#   디스플레이 장비: Wet Station, APP, CO2 Cleaner, Coater
#   소재: Ceria Slurry, Silica Slurry, Zirconia, Hollow Silica
# 주요 매출처: 삼성전자, SK하이닉스 (매출 10% 초과)
# 최대주주(유의적 영향력): (주)케이씨
# 기타의 특수관계자: (주)케이씨이앤씨, (주)케이씨인더스트리얼, (주)케이씨이노베이션,
#   KC Precision Equipment Maintenance (Wuxi) Co.,Ltd., 스타트업 코리아 케이씨 초격차펀드,
#   (주)케이씨솔루션, (주)케이씨투자파트너스, (주)케이씨파츠텍, KCINNOVATION CHINA CO.,LTD
# 종속기업: KCTech America Inc.(2025년~)
EXTRACTIONS: dict[str, dict] = {

    # -- II. 사업의 내용: 제품 (사업보고서 2023.12) --------------------------------

    "2c5737579e131704": {  # 2023 사업보고서: CMP, Wet Cleaning System, Wet Station, APP, CO2 Cleaner, Coater, Ceria Slurry, Silica Slurry, Zirconia, Hollow Silica
        "entities": [
            (P, "cmp장비", "CMP 장비"),
            (P, "wet cleaning system", "Wet Cleaning System"),
            (P, "wet station", "Wet Station"),
            (P, "coater", "Coater"),
            (P, "ceria slurry", "Ceria Slurry"),
            (P, "silica slurry", "Silica Slurry"),
            (P, "zirconia", "Zirconia"),
            (P, "hollow silica", "Hollow Silica"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmp장비", "CMP 장비"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "wet cleaning system", "Wet Cleaning System"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "wet station", "Wet Station"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "coater", "Coater"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "ceria slurry", "Ceria Slurry"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "silica slurry", "Silica Slurry"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "zirconia", "Zirconia"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "hollow silica", "Hollow Silica"), 0.95),
        ],
    },

    "6dad750ee26f20ed": {  # 2023 사업보고서: 디스플레이 장비 상세 (Wet Station, APP, CO2 Cleaner, Coater)
        "entities": [
            (P, "app모듈", "APP 모듈"),
            (P, "co2 cleaner", "CO2 Cleaner"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "wet station", "Wet Station"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "app모듈", "APP 모듈"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "co2 cleaner", "CO2 Cleaner"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "coater", "Coater"), 0.93),
        ],
    },

    "2f6afb6773ccd74e": {  # 2023 사업보고서: Hollow Silica 소재 - 저굴절·저유전·단열 특성, Anti Glare 등 응용
        "entities": [
            (T, "hollow silica기술", "Hollow Silica 저굴절·저유전·단열 기술"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "hollow silica", "Hollow Silica"), 0.95),
            E("USES_TECH", ("org", CORP), ("ent", T, "hollow silica기술", "Hollow Silica 저굴절·저유전·단열 기술"), 0.88),
        ],
    },

    # -- II. 사업의 내용: CMP 기술 상세 ------------------------------------------

    "036a7f909b5d1990": {  # 2023 사업보고서: CMP 연구개발, 지적재산권 (특허권)
        "entities": [
            (T, "cmp기술", "CMP(화학기계적 평탄화) 기술"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "cmp기술", "CMP(화학기계적 평탄화) 기술"), 0.90),
        ],
    },

    "1fd2d8d91057f8f3": {  # 2025 사업보고서: 반도체 전공정(포토/에칭/세정/건조/열처리/박막형성) 장비 특성
        "entities": [
            (T, "반도체전공정장비기술", "반도체 전공정 장비 기술"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "반도체전공정장비기술", "반도체 전공정 장비 기술"), 0.88),
        ],
    },

    # -- II. 사업의 내용: 주요 매출처 (삼성전자·SK하이닉스 10% 초과) ----------------

    "3016ac8d565bbc07": {  # 2024 사업보고서 주석: 단일외부고객 (가)183,226백만, (나)128,040백만 10% 초과 매출처
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.88),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.88),
        ],
    },

    "668da30ebe928a8c": {  # 2024 감사보고서 주석: 동일 단일외부고객 (가)(나) 10% 초과
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.88),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.88),
        ],
    },

    "7c33740560490f64": {  # 2025 감사보고서 주석: (가)181,086백만, (나)152,578백만 10% 초과 단일 외부고객
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.88),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.88),
        ],
    },

    "7fa817015bd2d127": {  # 2025 연결감사보고서: (가)(나) 10% 초과 단일 외부고객
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.88),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.88),
        ],
    },

    "645b3be2423dc3d2": {  # 2024Q1 주석: (가)44,163, (나)29,251 단일외부고객 10% 초과
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.86),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.86),
        ],
    },

    "f5641030f9592ec4": {  # 2024H1 주석: 단일외부고객 (가)(나) 10% 초과
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.86),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.86),
        ],
    },

    "328aba0066c3ed6a": {  # 2024Q3 주석: 단일외부고객 (가)(나) 10% 초과
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.86),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.86),
        ],
    },

    "05713f3ef01c6d98": {  # 2023 주석: 보고부문 반도체부문(장비·소재) + 디스플레이부문
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.85),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.85),
        ],
    },

    # -- II. 사업의 내용: 제품/소재 (반복 확인 청크들) ----------------------------

    "0d58dfee43c6ae0b": {  # 2025Q3: CMP, Wet Cleaning, Wet Station, Coater, Ceria/Silica Slurry, Zirconia, Hollow Silica
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmp장비", "CMP 장비"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "wet cleaning system", "Wet Cleaning System"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "wet station", "Wet Station"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "coater", "Coater"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "ceria slurry", "Ceria Slurry"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "silica slurry", "Silica Slurry"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "zirconia", "Zirconia"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "hollow silica", "Hollow Silica"), 0.95),
        ],
    },

    "113779360f34f29d": {  # 2025Q1: CMP, Wet Cleaning, Wet Station, APP, CO2 Cleaner, Coater, Ceria Slurry, Silica Slurry, Zirconia, Hollow Silica
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmp장비", "CMP 장비"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "wet cleaning system", "Wet Cleaning System"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "ceria slurry", "Ceria Slurry"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "silica slurry", "Silica Slurry"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "zirconia", "Zirconia"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "hollow silica", "Hollow Silica"), 0.95),
        ],
    },

    "3513c51599b19e91": {  # 2025H1: CMP, Wet Cleaning, Wet Station, APP, CO2 Cleaner, Coater, 소재 4종
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmp장비", "CMP 장비"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "wet cleaning system", "Wet Cleaning System"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "ceria slurry", "Ceria Slurry"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "silica slurry", "Silica Slurry"), 0.97),
        ],
    },

    "1ceb2aa46f6c3f83": {  # 2026Q1: CMP, Wet Cleaning, Wet Station, APP, CO2 Cleaner, Coater, 소재 4종
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmp장비", "CMP 장비"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "wet cleaning system", "Wet Cleaning System"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "ceria slurry", "Ceria Slurry"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "silica slurry", "Silica Slurry"), 0.97),
        ],
    },

    "35d073c06c59d5aa": {  # 2025 사업보고서: CMP, Wet Cleaning, Wet Station, APP, CO2 Cleaner, Coater, 소재 4종
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmp장비", "CMP 장비"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "ceria slurry", "Ceria Slurry"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "silica slurry", "Silica Slurry"), 0.97),
        ],
    },

    "eb310422897d8470": {  # 2024 사업보고서: CMP, Wet Cleaning, Wet Station, APP, CO2 Cleaner, Coater, 소재 4종
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmp장비", "CMP 장비"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "ceria slurry", "Ceria Slurry"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "silica slurry", "Silica Slurry"), 0.97),
        ],
    },

    "ce6e4695b3008a1e": {  # 2024Q1: CMP, Wet Cleaning, Wet Station, APP, CO2 Cleaner, Coater, 소재 4종
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmp장비", "CMP 장비"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "ceria slurry", "Ceria Slurry"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "silica slurry", "Silica Slurry"), 0.97),
        ],
    },

    "795066cb82ec960f": {  # 2024H1: CMP, Wet Cleaning, Wet Station, APP, CO2 Cleaner, Coater, 소재 4종
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmp장비", "CMP 장비"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "ceria slurry", "Ceria Slurry"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "silica slurry", "Silica Slurry"), 0.97),
        ],
    },

    "d293fef1ace71bf7": {  # 2024Q3: CMP, Wet Cleaning, Wet Station, APP, CO2 Cleaner, Coater, 소재 4종
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmp장비", "CMP 장비"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "ceria slurry", "Ceria Slurry"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "silica slurry", "Silica Slurry"), 0.97),
        ],
    },

    # -- II. 사업의 내용: Hollow Silica 소재 단독 언급 ---------------------------

    "15dfde8136859430": {  # 2024 사업보고서: Hollow Silica Anti Glare, Low Reflection 등 응용
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "hollow silica", "Hollow Silica"), 0.95),
            E("USES_TECH", ("org", CORP), ("ent", T, "hollow silica기술", "Hollow Silica 저굴절·저유전·단열 기술"), 0.87),
        ],
    },

    "2d6400c2995458c5": {  # 2024Q3: Hollow Silica Anti Glare 응용
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "hollow silica", "Hollow Silica"), 0.95),
        ],
    },

    "0855b606a8cc46ac": {  # 2025 사업보고서: Hollow Silica Anti Glare 등 응용
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "hollow silica", "Hollow Silica"), 0.95),
            E("USES_TECH", ("org", CORP), ("ent", T, "hollow silica기술", "Hollow Silica 저굴절·저유전·단열 기술"), 0.87),
        ],
    },

    "29c309f1a93a8a6b": {  # 2026Q1: Hollow Silica Anti Glare 등 응용
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "hollow silica", "Hollow Silica"), 0.95),
        ],
    },

    # -- II. 사업의 내용: CMP 기술 상세 (반복) -----------------------------------

    "65a2bca8c1528b31": {  # 2025 사업보고서: CMP Wafer 화학기계적 평탄화, Wet Cleaning System 불순물 제거
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmp장비", "CMP 장비"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "wet cleaning system", "Wet Cleaning System"), 0.97),
            E("USES_TECH", ("org", CORP), ("ent", T, "cmp기술", "CMP(화학기계적 평탄화) 기술"), 0.90),
        ],
    },

    "818576e25b032a08": {  # 2026Q1: CMP, Wet Cleaning, Wet Station, CO2 Cleaner, Coater 상세
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmp장비", "CMP 장비"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "wet cleaning system", "Wet Cleaning System"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "co2 cleaner", "CO2 Cleaner"), 0.92),
        ],
    },

    "a590c8637bf032c8": {  # 2025Q3: CMP, Wet Cleaning, Wet Station, Coater, Zirconia 상세
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmp장비", "CMP 장비"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "wet cleaning system", "Wet Cleaning System"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "zirconia", "Zirconia"), 0.95),
        ],
    },

    # -- 특수관계자 목록 (2023 감사보고서) ----------------------------------------

    "01446f831e4c9cd9": {  # 2024 감사보고서: 지분법투자=(주)케이씨, 기타의특수관계자=(주)케이씨이앤씨, KC Precision Wuxi, (주)케이씨인더스트리얼, (주)케이씨이노베이션
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업(최대주주)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이앤씨"), 0.90, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨인더스트리얼"), 0.90, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이노베이션"), 0.88, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "KC Precision Equipment Maintenance Wuxi"), 0.87, "기타의 특수관계자"),
        ],
    },

    "336de25915b789a9": {  # 2024H1: 유의적 영향력=(주)케이씨, 기타 특수관계자 목록
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업(최대주주)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이앤씨"), 0.90, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨인더스트리얼"), 0.90, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이노베이션"), 0.88, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "KC Precision Equipment Maintenance Wuxi"), 0.87, "기타의 특수관계자"),
        ],
    },

    "1566ed2f5328bf8d": {  # 2025 연결감사보고서: 유의적 영향력=(주)케이씨, 기타의특수관계자 목록(케이씨이앤씨 등), (주)케이씨솔루션, (주)케이씨투자파트너스, (주)케이씨파츠텍, 스타트업 코리아 케이씨 초격차펀드, KCINNOVATION CHINA 추가
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업(최대주주)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이앤씨"), 0.90, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨인더스트리얼"), 0.90, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이노베이션"), 0.88, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "KC Precision Equipment Maintenance Wuxi"), 0.87, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨솔루션"), 0.85, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨투자파트너스"), 0.85, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨파츠텍"), 0.85, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "스타트업코리아케이씨초격차펀드"), 0.82, "기타의 특수관계자(펀드)"),
        ],
    },

    # -- 특수관계자 목록 (재무제표 주석): (주)케이씨 지분법 투자회사 ----------------

    "1d6a8ca0facb6ee7": {  # 2023 재무제표주석: 특수관계자 거래 (주)케이씨 매출·기타수익·유형자산매각, (주)케이씨인더스트리얼 재고자산매입
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업(매출·유형자산매각·기타비용 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이앤씨"), 0.88, "기타의 특수관계자(기타비용 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨인더스트리얼"), 0.90, "기타의 특수관계자(재고자산매입 10,193,933천원)"),
        ],
    },

    "38d0b7f0f8a86bc1": {  # 2023 재무제표주석: 특수관계자 채권채무 - (주)케이씨 미지급금/미지급비용, (주)케이씨인더스트리얼 매입채무/선급금
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업(미지급금·미지급비용 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이앤씨"), 0.88, "기타의 특수관계자(미지급금 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨인더스트리얼"), 0.90, "기타의 특수관계자(매입채무·선급금 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "KC Precision Equipment Maintenance Wuxi"), 0.85, "기타의 특수관계자(미수금 거래)"),
        ],
    },

    # -- 특수관계자 거래 (X. 대주주 등과의 거래내용) --------------------------------

    "1921d91fded0584e": {  # 2023 사업보고서: 대주주 (주)케이씨 특수관계자 거래(배당금 1,554,368천원 포함)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업(대주주, 배당금 거래)"),
        ],
    },

    "4d5b9ff26ecd1514": {  # 2024Q3 대주주 거래: (주)케이씨 특수관계자 거래, 배당금 1,119,145천원
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업(배당금 1,119,145천원)"),
        ],
    },

    "1e6bf7b96da53aa0": {  # 2024Q3: RSU 주식기준보상 도입 (대표이사), 특수관계자 채권채무 잔액
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.95, "유의적인 영향력을 행사하는 기업(채권채무 거래)"),
        ],
    },

    "118b222f4e865b59": {  # 2025H1: 대주주 거래 없음, 특수관계자 거래 기타비용(배당금 1,678,717천원)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업(배당금 1,678,717천원)"),
        ],
    },

    "068a20df429e2dec": {  # 2025Q3: 대주주 거래 없음, 특수관계자 거래 배당금 1,678,717천원
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업(배당금 1,678,717천원)"),
        ],
    },

    "01c056374d6b58c9": {  # 2026Q1: 특수관계자 기타비용 배당금 3,198,336천원
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업(배당금 3,198,336천원)"),
        ],
    },

    "26f271851e2220cd": {  # 2026Q1: 특수관계자 채권채무 잔액 (RSU 언급 포함)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업(채권채무 잔액)"),
        ],
    },

    # -- 특수관계자 거래 상세: (주)케이씨인더스트리얼 재고자산매입 ------------------

    "0d5e0e8108527dee": {  # 2024Q1 대주주거래표: (주)케이씨이앤씨·케이씨인더스트리얼·케이씨이노베이션·KC Precision Wuxi 재고자산매입
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.95, "유의적인 영향력을 행사하는 기업(기타수익 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이앤씨"), 0.88, "기타의 특수관계자(재고자산매입)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨인더스트리얼"), 0.90, "기타의 특수관계자(재고자산매입 3,231,922천원)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이노베이션"), 0.88, "기타의 특수관계자(재고자산매입 829,200천원)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "KC Precision Equipment Maintenance Wuxi"), 0.85, "기타의 특수관계자(기타수익 거래)"),
        ],
    },

    "0492ee1867a16724": {  # 2024Q1 채권채무표: (주)케이씨 미지급금/배당금, (주)케이씨인더스트리얼 선급금/매입채무
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업(미지급금·배당금 1,119,145천원)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이앤씨"), 0.88, "기타의 특수관계자(미지급금 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨인더스트리얼"), 0.90, "기타의 특수관계자(선급금·매입채무 거래)"),
        ],
    },

    "298ce4624f2c7828": {  # 2025 연결감사보고서: (주)케이씨 매출/기타수익, (주)케이씨인더스트리얼 재고자산매입 10,574,768천원
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업(매출·기타비용 6,636,215천원)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이앤씨"), 0.88, "기타의 특수관계자(기타비용 155,000천원)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨인더스트리얼"), 0.90, "기타의 특수관계자(재고자산매입 10,574,768천원)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이노베이션"), 0.88, "기타의 특수관계자(재고자산매입 138,200천원)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "KC Precision Equipment Maintenance Wuxi"), 0.85, "기타의 특수관계자(기타수익 83,510천원)"),
        ],
    },

    "1da8cfa2343a57f7": {  # 2025 연결감사보고서: 특수관계자 채권채무 - (주)케이씨 미지급비용/리스부채, (주)케이씨인더스트리얼 매입채무 970,116천원
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업(미지급금·미지급비용·리스부채)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이앤씨"), 0.88, "기타의 특수관계자(미지급금 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨인더스트리얼"), 0.90, "기타의 특수관계자(매입채무 970,116천원)"),
        ],
    },

    # -- 특수관계자 거래 (2024 사업보고서 / 감사보고서) ---------------------------

    "17e60dd4f4e27501": {  # 2024 재무제표주석: (주)케이씨 채권/미지급금, (주)케이씨인더스트리얼 매입채무 1,216,007천원
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업(매출채권·미지급금·미지급비용·리스부채)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이앤씨"), 0.88, "기타의 특수관계자(미지급금 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨인더스트리얼"), 0.90, "기타의 특수관계자(매입채무 1,216,007천원)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "KC Precision Equipment Maintenance Wuxi"), 0.85, "기타의 특수관계자(미수금 거래)"),
        ],
    },

    "23f68a258b6f7e69": {  # 2024 대주주 채권채무표: (주)케이씨이앤씨·케이씨인더스트리얼·KC Precision Wuxi
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업(매출채권·미지급금·리스부채)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이앤씨"), 0.88, "기타의 특수관계자(미지급금 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨인더스트리얼"), 0.90, "기타의 특수관계자(매입채무 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "KC Precision Equipment Maintenance Wuxi"), 0.85, "기타의 특수관계자(미수금 거래)"),
        ],
    },

    # -- 특수관계자 거래 (분기보고서 2024Q3 주석) ----------------------------------

    "1d2bba7675093e77": {  # 2024Q1 주석: (주)케이씨인더스트리얼 재고자산매입 3,231,922, (주)케이씨이노베이션 829,200
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨인더스트리얼"), 0.90, "기타의 특수관계자(재고자산매입 3,231,922천원)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이노베이션"), 0.88, "기타의 특수관계자(재고자산매입 829,200천원)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "KC Precision Equipment Maintenance Wuxi"), 0.85, "기타의 특수관계자(기타수익 거래)"),
        ],
    },

    # -- 특수관계자 목록 (2025Q1~2026Q1) ------------------------------------------

    "16b7b34160252ceb": {  # 2025Q1 주석: (주)케이씨 + (주)케이씨이앤씨, (주)케이씨인더스트리얼, KC Precision Wuxi, 임원
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이앤씨"), 0.90, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨인더스트리얼"), 0.90, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "KC Precision Equipment Maintenance Wuxi"), 0.87, "기타의 특수관계자"),
        ],
    },

    "1a38249edff1f11f": {  # 2025H1 연결주석: (주)케이씨 + 기타 특수관계자 목록
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이앤씨"), 0.90, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨인더스트리얼"), 0.90, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "KC Precision Equipment Maintenance Wuxi"), 0.87, "기타의 특수관계자"),
        ],
    },

    "21a640540754d5eb": {  # 2025Q3 주석: (주)케이씨 + 기타 특수관계자, 임원
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이앤씨"), 0.90, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨인더스트리얼"), 0.90, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "KC Precision Equipment Maintenance Wuxi"), 0.87, "기타의 특수관계자"),
        ],
    },

    # -- 특수관계자 목록 (2025 사업보고서 주석) ------------------------------------

    "07f2cc4696501494": {  # 2025 사업보고서 주석: 종속기업=KCTech America Inc, 그 밖의특수관계자=스타트업 코리아 케이씨 초격차펀드, 임원
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "KCTech America Inc"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "스타트업코리아케이씨초격차펀드"), 0.82, "그 밖의 특수관계자(펀드)"),
        ],
    },

    "0d1812bf06085fe1": {  # 2025 사업보고서 주석: 종속기업=KCTech America Inc, 그 밖의 특수관계자 + 임원
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "KCTech America Inc"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이앤씨"), 0.90, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨인더스트리얼"), 0.90, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "KC Precision Equipment Maintenance Wuxi"), 0.87, "기타의 특수관계자"),
        ],
    },

    "3c4af060c6bcb8c8": {  # 2025 사업보고서 주석: 종속기업=KCTech America Inc, 유의적 영향력=(주)케이씨, 기타특수관계자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "KCTech America Inc"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이앤씨"), 0.90, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨인더스트리얼"), 0.90, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "KC Precision Equipment Maintenance Wuxi"), 0.87, "기타의 특수관계자"),
        ],
    },

    "201ebc7b68f8f296": {  # 2025 연결감사보고서 주석: 유의적 영향력=(주)케이씨, 기타특수관계자(케이씨이앤씨~KC Precision)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이앤씨"), 0.90, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨인더스트리얼"), 0.90, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "KC Precision Equipment Maintenance Wuxi"), 0.87, "기타의 특수관계자"),
        ],
    },

    # -- 특수관계자 채권채무 (2025Q1 대주주 거래표) --------------------------------

    "01ba71c51c996200": {  # 2025Q1 대주주거래표: (주)케이씨 미지급배당금 1,678,717, (주)케이씨인더스트리얼 매입채무 1,118,983
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업(배당금 1,678,717천원)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이앤씨"), 0.88, "기타의 특수관계자(미지급금 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨인더스트리얼"), 0.90, "기타의 특수관계자(매입채무 1,118,983천원)"),
        ],
    },

    # -- 2026Q1 특수관계자 목록 (연결재무제표 주석) --------------------------------

    "1bf617594740962b": {  # 2026Q1 연결주석: 종속기업, 유의적 영향력 기업, 그 밖의 특수관계자 6~7개
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "KCTech America Inc"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이앤씨"), 0.90, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨인더스트리얼"), 0.90, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "KC Precision Equipment Maintenance Wuxi"), 0.87, "기타의 특수관계자"),
        ],
    },

    "379c73baacc29716": {  # 2026Q1 연결주석: 특수관계자 전체목록(종속기업+유의적 영향력+그 밖의)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨"), 0.97, "유의적인 영향력을 행사하는 기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨이앤씨"), 0.90, "기타의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "케이씨인더스트리얼"), 0.90, "기타의 특수관계자"),
        ],
    },

    # -- 영업부문 정보 (반도체·디스플레이 부문 분리) --------------------------------

    "45739a2bfc82bc36": {  # 2023 사업보고서: 반도체부문 1,967억원, 디스플레이부문 902억원, 총 매출액 2,869억원
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.85),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.85),
        ],
    },

    "fffe56c4523fa296": {  # 2024 사업보고서: 매출액 3,854억원, 영업이익 498억원
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.85),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.85),
        ],
    },

    "4f7c3fb3cea027c1": {  # 2025 사업보고서: 연결 매출 3,828억원, 반도체부문 3,457억원, 디스플레이 370억원
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.87),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.87),
        ],
    },

    "54f6dff032676ede": {  # 2025 사업보고서: 반도체부문 3,457억원(90%), 디스플레이부문 370억원
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.87),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.87),
        ],
    },

    # -- 2025 연결재무제표 주석: 종속기업 현황 ------------------------------------

    "0d72c4f631b67904": {  # 2025 연결재무제표주석: 종속기업 현황 (KCTech America Inc 신규 출자)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "KCTech America Inc"), 0.90, "종속기업(신규 출자)"),
        ],
    },

    "1f9cc0d63648a021": {  # 2026Q1 연결재무제표주석: 종속기업 현황 (KCTech America Inc 포함)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "KCTech America Inc"), 0.90, "종속기업"),
        ],
    },
}


def run():
    # text_micro 전체 + table_nl 특수관계 청크
    rows_text = get_chunks(
        f"WHERE corp_code='{CORP_CODE}' AND chunk_type='text_micro' ORDER BY chunk_id"
    )
    rows_table = get_chunks(
        f"WHERE corp_code='{CORP_CODE}' AND chunk_type='table_nl' AND embedding_text LIKE '%특수관계%' ORDER BY chunk_id"
    )
    all_rows = rows_text + rows_table
    by_id = {r["chunk_id"]: r for r in all_rows}
    print(f"[batch] 대상 text_micro {len(rows_text)}건 + table_nl(특수관계) {len(rows_table)}건 = {len(all_rows)}건")

    done = ledger_processed_ids()
    print(f"[batch] 원장 기처리 {len(done)}건 -- 스킵")

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
            print(f"  [warn] {cid} 대상에 없음 -- 스킵")
            continue
        row = by_id[cid]
        rcept = row["rcept_no"]
        n_ent = n_edge = 0

        for label, canonical, name in payload.get("entities", []):
            eid = merge_entity(driver, label, canonical, name)
            add_edge(driver, "hasObject",
                     {"kind": "chunk", "chunk_id": cid},
                     {"kind": "entity", "label": label, "id": eid},
                     chunk_id=cid, rcept_no=rcept, confidence=1.0)
            write_provenance(conn, cid, "hasObject", eid, cid, rcept, 1.0)
            n_ent += 1
            n_prov_total += 1

        for e in payload.get("edges", []):
            rel, frm, to, conf = e["rel"], e["from"], e["to"], e["conf"]
            rtype = e.get("relation_type")
            fm, fid = _match_and_id(driver, frm)
            tm, tid = _match_and_id(driver, to)
            add_edge(driver, rel, fm, tm, chunk_id=cid, rcept_no=rcept,
                     confidence=conf, relation_type=rtype)
            write_provenance(conn, fid, rel, tid, cid, rcept, conf)
            n_edge += 1
            n_prov_total += 1
            edge_by_type[rel] = edge_by_type.get(rel, 0) + 1

        conn.commit()
        mark_processed(cid, n_ent, n_edge, rcept, row["section_path"])
        n_ent_total += n_ent
        n_edge_total += n_edge
        processed += 1

    # 2) 나머지 청크 = 엣지 0개 (누락 0 보장)
    extracted_ids = set(EXTRACTIONS.keys())
    for r in all_rows:
        cid = r["chunk_id"]
        if cid in done or cid in extracted_ids:
            continue
        mark_processed(cid, 0, 0, r["rcept_no"], r["section_path"])
        processed += 1

    conn.close()
    driver.close()

    total_marked = len(ledger_processed_ids())
    print("=== 케이씨텍 Stage5 추출 결과 ===")
    print(f"  이번 처리 청크: {processed}  (원장 누적 {total_marked} / 대상 {len(all_rows)})")
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
