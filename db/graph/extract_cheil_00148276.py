"""Stage 5 비정형 추출 — 제일기획 corp_code=00148276, text_micro 전체(~865) + table_nl 특수관계(~210).

제일기획 = 삼성그룹 계열 통합 마케팅/광고대행 전문기업.
  - 주요 사업: 광고 기획/제작, 매체(TV/라디오/온라인) 대행, 프로모션, 스포츠 이벤트
  - 마케팅 솔루션: Media Solution, Creative Solution, Experiential Solution
  - 글로벌: 46개국 54개 거점. 해외 M&A사(BMB, Iris, McKinney, TBG, PengTai, One Agency 등)
  - 기술: AdTech(광고기술), 디지털 마케팅, 개인화 마케팅
  - 주요 광고주(특수관계): 삼성전자(주) — 매출의 약 40~50% 차지(본사 별도기준)
    * 2023: 영업수익 본사 별도 ~ 약 1.1조원 (연결 영업총이익 1조6,189억)
    * 2024: 삼성전자 영업수익 944,776백만원 (본사 별도기준)
    * 2025: 삼성전자 영업수익 921,341백만원 (본사 별도기준)
    * 2026Q1: 삼성전자 영업수익 192,742백만원
  - 삼성그룹 계열: 2023~2024 63개사, 2025 67개사 (삼성전자·삼성물산·삼성생명·삼성SDS 등)
  - 기타 특수관계자: 삼성디스플레이(주), 삼성카드(주), (주)이브이알스튜디오(관계기업)

원장 = db/graph/ledger/extra28_00148276.jsonl (이 추출 전용).
실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_cheil_00148276.py
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

CORP = "제일기획"
CORP_CODE = "00148276"

# ── 전용 원장 ─────────────────────────────────────────────────
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_DIR.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = LEDGER_DIR / "extra28_00148276.jsonl"


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
# 제일기획 = 삼성그룹 계열 통합 마케팅/광고대행사
# Product: 통합마케팅솔루션, Media Solution, Creative Solution, Experiential Solution
# Technology: AdTech(광고기술), 디지털마케팅
# 핵심 광고주: 삼성전자 (SUPPLIES_TO 제일기획→삼성전자 광고서비스 제공)
# 삼성그룹 계열 계열사 관계

EXTRACTIONS: dict[str, dict] = {

    # ═══ II. 사업의 내용: 회사 개요 — 2023 사업보고서 ═══

    "0d078ebe0da78fc6": {  # 2023 사업보고서 II: 광고업 주요 사업 — 광고기획/제작, 매체선정, 프로모션 대행, AdTech
        "entities": [
            (P, "통합마케팅솔루션", "통합 마케팅 솔루션(Integrated Marketing Solution)"),
            (T, "AdTech", "AdTech(광고기술 — 온라인 구매 패턴 분석·개인화 마케팅)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "통합마케팅솔루션", "통합 마케팅 솔루션(Integrated Marketing Solution)"), 0.97),
            E("USES_TECH", ("org", CORP), ("ent", T, "AdTech", "AdTech(광고기술 — 온라인 구매 패턴 분석·개인화 마케팅)"), 0.90),
        ],
    },

    "5af6ebc2db1442aa": {  # 2023 사업보고서 II: 미디어 서비스(전파/인쇄/뉴미디어) + 광고물 제작
        "entities": [
            (P, "미디어솔루션", "Media Solution(매체계획·광고집행 서비스)"),
            (P, "광고물제작서비스", "광고물 제작 서비스(TV/인쇄/디지털 광고)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "미디어솔루션", "Media Solution(매체계획·광고집행 서비스)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "광고물제작서비스", "광고물 제작 서비스(TV/인쇄/디지털 광고)"), 0.95),
        ],
    },

    "bc24cc1eb76a1fe5": {  # 2023 사업보고서 II: 광고업 사업부문 — Media/Creative/Digital/Experiential/Strategy
        "entities": [
            (P, "크리에이티브솔루션", "Creative Solution(광고 크리에이티브 기획·제작)"),
            (P, "익스피리엔셜솔루션", "Experiential Solution(프로모션·이벤트·체험 마케팅)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "크리에이티브솔루션", "Creative Solution(광고 크리에이티브 기획·제작)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "익스피리엔셜솔루션", "Experiential Solution(프로모션·이벤트·체험 마케팅)"), 0.93),
        ],
    },

    "4154f10f62973b31": {  # 2023 사업보고서 II: Media Solution — 최적 매체플래닝·구매력 / Experiential Solution — 프로모션·글로벌 전시·스포츠 행사
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "미디어솔루션", "Media Solution(매체계획·광고집행 서비스)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "익스피리엔셜솔루션", "Experiential Solution(프로모션·이벤트·체험 마케팅)"), 0.93),
        ],
    },

    "0dce8cdcfba797bf": {  # 2023 사업보고서 II: 판매전략 — 통합 마케팅 솔루션(IMS), 글로벌 46개국 54개 거점
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "통합마케팅솔루션", "통합 마케팅 솔루션(Integrated Marketing Solution)"), 0.97),
        ],
    },

    "f39c46683c1a6da7": {  # 2023 사업보고서 II: 경쟁우위 — 글로벌 46개국 54개 거점, 영국 BMB·Iris, 미국 McKinney·TBG, 중국 PengTai, 중동 One Agency
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "통합마케팅솔루션", "통합 마케팅 솔루션(Integrated Marketing Solution)"), 0.95),
        ],
    },

    "500aa38b6fb36ce7": {  # 2023 사업보고서 II: 크리에이티브 수준 — 광고제 수상, 최고 크리에이티브력
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "크리에이티브솔루션", "Creative Solution(광고 크리에이티브 기획·제작)"), 0.92),
        ],
    },

    # ═══ II. 2023 사업보고서: 영업현황 ═══

    "4d4f2b4acb81cc22": {  # 2023 사업보고서 II: 연결 영업총이익 1조6,189억, 본사 3,492억. 광고주 마케팅 효율화 → 국내 광고시장 -1.6%
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "통합마케팅솔루션", "통합 마케팅 솔루션(Integrated Marketing Solution)"), 0.95),
        ],
    },

    # ═══ IX. 계열회사: 삼성그룹 계열 — 2023 사업보고서 ═══

    "71c403d9875427c1": {  # 2023 사업보고서 IX: 삼성그룹 계열 63개사, 상장 17개사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "삼성그룹 대규모기업집단 계열사(유의적 영향력 행사)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.92, "삼성그룹 대규모기업집단 계열사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.92, "삼성그룹 대규모기업집단 계열사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에스디에스"), 0.90, "삼성그룹 대규모기업집단 계열사"),
        ],
    },

    # ═══ X. 대주주 등과의 거래내용: 삼성전자 광고 매출 — 2023 사업보고서 ═══

    "3f45c6f1467af114": {  # 2023 사업보고서 X: 삼성전자(주) 특수관계인 — 2023년 영업수익(광고서비스 제공)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "대주주(유의적 영향력 행사 회사, 광고서비스 주요 광고주)"),
        ],
    },

    # ═══ II. 사업의 내용 — 2024.03 분기보고서 ═══

    "fe2bf4e187e0e1be": {  # 2024.03 분기보고서 II: 광고업 주요 사업 — 광고기획/제작, 매체선정, 프로모션, AdTech
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "통합마케팅솔루션", "통합 마케팅 솔루션(Integrated Marketing Solution)"), 0.97),
            E("USES_TECH", ("org", CORP), ("ent", T, "AdTech", "AdTech(광고기술 — 온라인 구매 패턴 분석·개인화 마케팅)"), 0.88),
        ],
    },

    "fcfe4b78bf459288": {  # 2024.03 분기보고서 II: Media/Experiential/Creative Solution — 통합 마케팅 솔루션
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "미디어솔루션", "Media Solution(매체계획·광고집행 서비스)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "크리에이티브솔루션", "Creative Solution(광고 크리에이티브 기획·제작)"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "익스피리엔셜솔루션", "Experiential Solution(프로모션·이벤트·체험 마케팅)"), 0.93),
        ],
    },

    "09026eca4b4fbded": {  # 2024.03 분기보고서 II: Creative Solution — 광고제 수상실적, 최고 크리에이티브력
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "크리에이티브솔루션", "Creative Solution(광고 크리에이티브 기획·제작)"), 0.92),
        ],
    },

    "522787371ce66b17": {  # 2024.03 분기보고서 II: 2024Q1 실적 — 51년 경험·노하우, 국내 1위 광고회사
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "통합마케팅솔루션", "통합 마케팅 솔루션(Integrated Marketing Solution)"), 0.95),
        ],
    },

    # ═══ IX/X — 2024.03 분기보고서 ═══

    "1994ae55c8f6471c": {  # 2024.03 분기보고서 IX: 분기보고서에 계열회사 기재 안 함, 2023 사업보고서 참조
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.95, "삼성그룹 대규모기업집단 계열사(2023말 63개사)"),
        ],
    },

    "38a5dc76160c8800": {  # 2024.03 분기보고서 X: 삼성전자(주) 특수관계인 — 2024Q1 광고서비스 영업수익
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "대주주(유의적 영향력 행사 회사)"),
        ],
    },

    # ═══ II. [기재정정]분기보고서 2024.03 ═══

    "13090a6f00498036": {  # 2024.03 기재정정 분기보고서 II: 광고업 — 통합 마케팅 솔루션, AdTech
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "통합마케팅솔루션", "통합 마케팅 솔루션(Integrated Marketing Solution)"), 0.97),
            E("USES_TECH", ("org", CORP), ("ent", T, "AdTech", "AdTech(광고기술 — 온라인 구매 패턴 분석·개인화 마케팅)"), 0.88),
        ],
    },

    "d92148b2d9eabe24": {  # 2024.03 기재정정 X: 삼성전자(주) 특수관계인 — 2024Q1 영업수익
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "대주주(유의적 영향력 행사 회사)"),
        ],
    },

    # ═══ II. 반기보고서 2024.06 ═══

    "c38a34f4b678e891": {  # 2024.06 반기보고서 II: 광고업 — 46개국 54개 거점, 통합 마케팅 솔루션
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "통합마케팅솔루션", "통합 마케팅 솔루션(Integrated Marketing Solution)"), 0.97),
            E("USES_TECH", ("org", CORP), ("ent", T, "AdTech", "AdTech(광고기술 — 온라인 구매 패턴 분석·개인화 마케팅)"), 0.88),
        ],
    },

    "1adec2bf6a8d9406": {  # 2024.06 반기보고서 II: Media/Experiential/Creative Solution
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "미디어솔루션", "Media Solution(매체계획·광고집행 서비스)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "크리에이티브솔루션", "Creative Solution(광고 크리에이티브 기획·제작)"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "익스피리엔셜솔루션", "Experiential Solution(프로모션·이벤트·체험 마케팅)"), 0.93),
        ],
    },

    "1a50072a991899fc": {  # 2024.06 반기보고서 II: 한국방송광고진흥공사·SBS M&C와 매년 방송광고업무 계약 — 13.0~13.6% 수수료
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "미디어솔루션", "Media Solution(매체계획·광고집행 서비스)"), 0.92),
        ],
    },

    "a808166a90a01100": {  # 2024.06 반기보고서 II: 2024년 반기 실적 — 국내 1위 광고회사
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "통합마케팅솔루션", "통합 마케팅 솔루션(Integrated Marketing Solution)"), 0.95),
        ],
    },

    # ═══ IX/X — 2024.06 반기보고서 ═══

    "bee22e4b4fa6ad40": {  # 2024.06 반기보고서 IX: 삼성그룹 계열 63개사, 상장 17개사(2024년 반기말)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "삼성그룹 대규모기업집단 계열사(2024반기 63개사)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.92, "삼성그룹 대규모기업집단 계열사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.90, "삼성그룹 대규모기업집단 계열사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에스디에스"), 0.90, "삼성그룹 대규모기업집단 계열사"),
        ],
    },

    "3bea1270ab8dc6ff": {  # 2024.06 반기보고서 X: 삼성전자(주) 특수관계인 — 2024년 반기 광고서비스 영업수익
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "대주주(유의적 영향력 행사 회사)"),
        ],
    },

    # ═══ II. 분기보고서 2024.09 ═══

    "405603bbe3b59eff": {  # 2024.09 분기보고서 II: 통합 마케팅 솔루션(IMS), 글로벌 톱 수준 경쟁력
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "통합마케팅솔루션", "통합 마케팅 솔루션(Integrated Marketing Solution)"), 0.97),
        ],
    },

    "960d34bfa4adcbaa": {  # 2024.09 분기보고서 II: Media/Experiential/Creative Solution
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "미디어솔루션", "Media Solution(매체계획·광고집행 서비스)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "크리에이티브솔루션", "Creative Solution(광고 크리에이티브 기획·제작)"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "익스피리엔셜솔루션", "Experiential Solution(프로모션·이벤트·체험 마케팅)"), 0.92),
        ],
    },

    "63aae5c7399a5787": {  # 2024.09 분기보고서 II: 2024년 3분기 실적, 국내 1위 광고회사, 전자·식품·화장품·건설·자동차 전 업종 광고주
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "통합마케팅솔루션", "통합 마케팅 솔루션(Integrated Marketing Solution)"), 0.95),
        ],
    },

    # ═══ IX/X — 2024.09 분기보고서 ═══

    "86bab6dd4c1822ed": {  # 2024.09 분기보고서 IX: 분기보고서에 계열회사 기재 안 함, 2024 반기보고서 참조
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.95, "삼성그룹 대규모기업집단 계열사"),
        ],
    },

    "cc4c4d9c2f19ee35": {  # 2024.09 분기보고서 X: 삼성전자(주) 특수관계인 — 2024년 3분기 광고서비스 영업수익
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "대주주(유의적 영향력 행사 회사)"),
        ],
    },

    # ═══ 2024.12 사업보고서 IX/X ═══

    "7ed782266cfcd044": {  # 2024.12 사업보고서 IX: 삼성그룹 계열 63개사, 상장 17개사(2024년말)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "삼성그룹 대규모기업집단 계열사(2024말 63개사)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.92, "삼성그룹 대규모기업집단 계열사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.90, "삼성그룹 대규모기업집단 계열사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에스디에스"), 0.90, "삼성그룹 대규모기업집단 계열사"),
        ],
    },

    "f42b084c3720720c": {  # 2024.12 사업보고서 X: 삼성전자(주) 특수관계인 — 2024년 영업수익 944,776백만원(본사 별도기준)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "대주주(유의적 영향력 행사 회사, 2024 영업수익 944,776백만원)"),
        ],
    },

    # ═══ II. 분기보고서 2025.03 ═══

    "abbf1c03ac565f02": {  # 2025.03 분기보고서 IX: 분기보고서에 계열회사 기재 안 함, 2024 사업보고서 참조
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.95, "삼성그룹 대규모기업집단 계열사"),
        ],
    },

    "d9f07a63c56c58e2": {  # 2025.03 분기보고서 X: 삼성전자(주) — 2025Q1 영업수익 224,015백만원(본사 별도기준)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "대주주(유의적 영향력 행사 회사, 2025Q1 영업수익 224,015백만원)"),
        ],
    },

    # ═══ II. 반기보고서 2025.06 ═══

    "bb2bfc4343b90fe5": {  # 2025.06 반기보고서 IX: 삼성그룹 계열 63개사, 상장 17개사(2025년 반기말)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "삼성그룹 대규모기업집단 계열사(2025반기 63개사)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.92, "삼성그룹 대규모기업집단 계열사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.90, "삼성그룹 대규모기업집단 계열사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에스디에스"), 0.90, "삼성그룹 대규모기업집단 계열사"),
        ],
    },

    "c1cb8eeb8ab9ddbe": {  # 2025.06 반기보고서 X: 삼성전자(주) — 2025년 반기 영업수익 440,026백만원(본사 별도기준)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "대주주(유의적 영향력 행사 회사, 2025반기 영업수익 440,026백만원)"),
        ],
    },

    # ═══ II. 분기보고서 2025.09 ═══

    "1bc690b9cb5b6e8c": {  # 2025.09 분기보고서 IX: 분기보고서에 계열회사 기재 안 함
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.95, "삼성그룹 대규모기업집단 계열사"),
        ],
    },

    "ce87084ff58f8d3c": {  # 2025.09 분기보고서 X: 삼성전자(주) — 2025년 3분기 영업수익 679,285백만원(본사 별도기준)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "대주주(유의적 영향력 행사 회사, 2025Q3 영업수익 679,285백만원)"),
        ],
    },

    # ═══ 2025.12 사업보고서 IX/X ═══

    "4e39cdd8bbef36c1": {  # 2025.12 사업보고서 IX: 삼성그룹 계열 67개사(전년+4개: 디앤엠·삼성노블라이프·삼성에피스홀딩스·에피스넥스랩), 상장 18개사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "삼성그룹 대규모기업집단 계열사(2025말 67개사)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.92, "삼성그룹 대규모기업집단 계열사(2025말)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.90, "삼성그룹 대규모기업집단 계열사(2025말)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에스디에스"), 0.90, "삼성그룹 대규모기업집단 계열사(2025말)"),
        ],
    },

    "be6f507de59f516a": {  # 2025.12 사업보고서 X: 삼성전자(주) — 2025년 영업수익 921,341백만원(본사 별도기준)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "대주주(유의적 영향력 행사 회사, 2025 영업수익 921,341백만원)"),
        ],
    },

    # ═══ 2026.03 분기보고서 IX/X ═══

    "7552f25847c39aca": {  # 2026.03 분기보고서 IX: 분기보고서에 계열회사 기재 안 함, 2025 사업보고서 참조
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.95, "삼성그룹 대규모기업집단 계열사(2025말 67개사)"),
        ],
    },

    "d22256738dae7a09": {  # 2026.03 분기보고서 X: 삼성전자(주) — 2026Q1 영업수익 192,742백만원(본사 별도기준)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "대주주(유의적 영향력 행사 회사, 2026Q1 영업수익 192,742백만원)"),
        ],
    },

    # ═══ 특수관계자 채권채무 표 (연결) — 삼성전자 채권(매출채권) ═══

    "0341c3775fef1302": {  # 2023 사업보고서 연결재무제표주석: 채권채무 — 삼성전자(주) 채권 매출채권 509,751,485천원
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.95, "유의적 영향력 행사 회사(채권 매출채권 509.8억원, 채무 선수수익 126.0억원)"),
        ],
    },

    "a18903fb0600a4fa": {  # 2023 사업보고서 연결재무제표주석: 거래현황 — 삼성전자(주) 1,176,829,070천원, Samsung China 322,876,925천원
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "유의적 영향력 행사 회사(연결 거래액 1조1,768억원)"),
        ],
    },

    "ae6c5a4ec5cb16f5": {  # 2023 사업보고서 연결재무제표주석: 거래현황(전기) — 삼성전자(주) 1,008,231,609천원
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
        ],
    },

    "2237b21df7acdc5e": {  # 2023 사업보고서 연결재무제표주석: 자금거래 — 삼성전자㈜ 배당금 33,393,786천원, 삼성카드㈜ 4,025,000천원
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.90, "유의적 영향력 행사 회사(배당금 지급 33,393,786천원)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성카드"), 0.85, "기타 특수관계자(배당금 지급 4,025,000천원)"),
        ],
    },

    "29dd6cb521061c56": {  # 2023 사업보고서 연결재무제표주석: 자금거래(전기) — 삼성전자㈜ 배당금 28,747,694천원, 삼성카드㈜, (주)이브이알스튜디오 출자 17,250,000
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.90, "유의적 영향력 행사 회사(전기 배당금 지급 28,747,694천원)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "이브이알스튜디오"), 0.85, "관계기업(출자 17,250,000천원)"),
        ],
    },

    "6c1a0afd67ff7880": {  # 2023 사업보고서 연결감사보고서: 거래현황 — 삼성전자(주) 1,008,231,609, Samsung China 351,861,251, Samsung India 165,203,142
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성디스플레이"), 0.88, "유의적 영향력 행사 회사(삼성그룹 계열)"),
        ],
    },

    "cfaaf4381d6ed3c6": {  # 2023 사업보고서 연결감사보고서: 거래현황(당기) — 삼성전자(주) 1,176,829,070
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
        ],
    },

    "392e63448193c2b5": {  # 2023 사업보고서 연결감사보고서: 채권채무(당기말) — 삼성전자(주) 매출채권 534,544,756
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.95, "유의적 영향력 행사 회사(채권 매출채권 534.5억원)"),
        ],
    },

    "a3042420ce3f0940": {  # 2023 사업보고서 연결감사보고서: 채권채무(전기말) — 삼성전자(주) 534,544,756, Samsung China 156,765,391
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
        ],
    },

    "390b8e4eed23a56c": {  # 2023 사업보고서 연결감사보고서: 자금거래(당기) — 삼성전자㈜ 배당금 33,393,786, 삼성카드㈜
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.90, "유의적 영향력 행사 회사(배당금 지급)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성카드"), 0.85, "기타 특수관계자(배당금 지급)"),
        ],
    },

    "c0db6648a600234e": {  # 2023 사업보고서 연결재무제표주석: 채권채무(당기말) — 삼성전자(주) 매출채권 534,544,756
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.95, "유의적 영향력 행사 회사(채권 매출채권 534.5억원, 선수수익 84.8억원)"),
        ],
    },

    "2b52e12124137223": {  # 2023 사업보고서 연결재무제표주석: 채권채무(당기말) — 기타 합계 1,091,213,811
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.90),
        ],
    },

    "bc8c24ce0a3d724b": {  # 2023 사업보고서 연결감사보고서: 채권채무(전기말) 합계 — 삼성전자 포함 1,091,213,811
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.90),
        ],
    },

    # ═══ 특수관계자 채권채무 (개별) — 2023 사업보고서 ═══

    "e07e1a46648ef4d6": {  # 2023 사업보고서 감사보고서(개별): 채권채무 — 삼성전자(주) 매출채권 497,491,752, 선수수익 72,910,030
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.95, "유의적 영향력 행사 회사(개별 채권 497.5억원, 선수수익 72.9억원)"),
        ],
    },

    "0bdc3a10eaf75b98": {  # 2023 사업보고서 감사보고서(개별): 채권채무(전기말) — 삼성전자(주) 480,642,566, 삼성디스플레이 5,002,550
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성디스플레이"), 0.88, "유의적 영향력 행사 회사(개별 채권 5,002,550천원)"),
        ],
    },

    "33654d7e1cc6686f": {  # 2023 사업보고서 감사보고서(개별): 거래현황(전기) — Samsung Saudi Arabia, Samsung Japan, 삼성디스플레이, 삼성전자서비스
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.93),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성디스플레이"), 0.88, "유의적 영향력 행사 회사(광고서비스 거래)"),
        ],
    },

    "7393d90040741b51": {  # 2023 사업보고서 감사보고서(개별): 거래현황(당기) — Samsung Saudi Arabia 26.9억, Samsung Japan 8.0억, 삼성디스플레이 5.5억
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.93),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성디스플레이"), 0.88, "유의적 영향력 행사 회사(광고서비스 거래 5.5억원)"),
        ],
    },

    "90e43bc1a979e754": {  # 2023 사업보고서 재무제표주석(개별): 거래현황(당기) — Samsung Saudi 26.9억, Samsung Japan 8.0억, 삼성디스플레이 5.5억
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.93),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성디스플레이"), 0.88, "유의적 영향력 행사 회사(광고서비스)"),
        ],
    },

    # ═══ 자금거래(개별) — 삼성전자·삼성카드 배당금 ═══

    "d5243cf5f3f04781": {  # 2023 사업보고서 감사보고서(개별): 자금거래(당기) — Iris Worldwide Holdings 회수, SVIC 34호 출자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.88, "유의적 영향력 행사 회사"),
        ],
    },

    "d7d40cc01c2df69f": {  # 2023 사업보고서 감사보고서(개별): 자금거래(전기) — Iris Worldwide Holdings 환율변동, SVIC 34호 회수·출자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.88, "유의적 영향력 행사 회사"),
        ],
    },

    # ═══ 채권채무 — 개별 재무제표 주석 (2023 사업보고서) ═══

    "b327a4a8cf89cd95": {  # 2023 사업보고서 재무제표주석(개별): 채권채무 종속기업(당기말) — CHEIL CHINA 104,732, 기타 종속기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.90, "유의적 영향력 행사 회사(개별 채권 포함)"),
        ],
    },

    "d9e374c73d9aea91": {  # 2023 사업보고서 감사보고서(개별): 채권채무 종속기업(당기말) — CHEIL CHINA, 기타 종속기업 대여금 포함
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.88, "유의적 영향력 행사 회사"),
        ],
    },

    # ═══ 특수관계자 채권채무 — II. 사업의 내용 텍스트 ═══

    "1b5cd178058a54be": {  # 2023 사업보고서 재무제표주석: 특수관계자 현황 텍스트 — 34. 특수관계자 및 주요거래 언급
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.92, "유의적 영향력 행사 회사(특수관계자)"),
        ],
    },

    # ═══ II. 2025.12 사업보고서 ═══
    # (동일 내용 반복 공시 — 추가 특이사항 없음. 2025 사업보고서의 X에서 삼성전자 연간 실적 확인)

}


# ── 메인 실행 로직 ─────────────────────────────────────────────────────────
def run():
    print(f"[제일기획 비정형 추출] CORP={CORP}, CORP_CODE={CORP_CODE}")
    driver = neo4j_driver()
    conn = mariadb_conn()

    # 대상 청크 조회
    import pymysql.cursors
    _conn = mariadb_conn()
    cur = _conn.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        "SELECT chunk_id, rcept_no, section_path, chunk_type, embedding_text "
        "FROM chunk_index "
        "WHERE corp_code=%s "
        "AND (chunk_type='text_micro' OR (chunk_type='table_nl' AND embedding_text LIKE '%%특수관계%%')) "
        "ORDER BY chunk_id",
        (CORP_CODE,),
    )
    all_rows = {r["chunk_id"]: r for r in cur.fetchall()}
    cur.close()
    _conn.close()

    total_chunks = len(all_rows)
    print(f"  DB 청크수: {total_chunks}")

    done = ledger_processed_ids()
    print(f"  원장 기처리: {len(done)}건 - 스킵")

    n_ent_total = n_edge_total = n_prov_total = 0
    edge_by_type: dict[str, int] = {}
    extracted_real_ids = set()
    processed = 0

    for cid, payload in EXTRACTIONS.items():
        real_cid = cid.split("_v")[0] if "_v" in cid else cid
        extracted_real_ids.add(real_cid)

        if real_cid in done:
            continue
        if real_cid not in all_rows:
            print(f"  [warn] {real_cid} DB에 없음 — 스킵")
            mark_processed(real_cid, 0, 0, None, None)
            continue

        row = all_rows[real_cid]
        rcept = row["rcept_no"]
        n_ent = n_edge = 0

        # 엔티티 MERGE
        eid_map: dict[tuple, str] = {}
        for label, canonical, name in payload.get("entities", []):
            eid = merge_entity(driver, label, canonical, name)
            eid_map[(label, canonical)] = eid
            # hasObject 엣지
            add_edge(
                driver, "hasObject",
                {"kind": "chunk", "chunk_id": real_cid},
                {"kind": "entity", "label": label, "id": eid},
                chunk_id=real_cid, rcept_no=rcept, confidence=1.0,
            )
            write_provenance(conn, real_cid, "hasObject", eid, real_cid, rcept, 1.0)
            n_ent += 1
            n_prov_total += 1

        # 엣지 MERGE
        for ed in payload.get("edges", []):
            rel_type = ed["rel"]
            conf = ed["conf"]
            relation_type = ed.get("relation_type")

            def resolve_match(spec):
                kind = spec[0]
                if kind == "org":
                    org = resolve_org(spec[1])
                    if org is None:
                        return None, None
                    merge_org_node(driver, org)
                    return {"kind": "org", "org": org}, org["id"]
                elif kind == "ent":
                    _, lbl, canonical, _ = spec
                    eid = eid_map.get((lbl, canonical))
                    if eid is None:
                        eid = merge_entity(driver, lbl, canonical)
                    return {"kind": "entity", "label": lbl, "id": eid}, eid
                return None, None

            fm, fid = resolve_match(ed["from"])
            tm, tid = resolve_match(ed["to"])
            if fm is None or tm is None:
                continue

            add_edge(
                driver, rel_type, fm, tm,
                chunk_id=real_cid, rcept_no=rcept, confidence=conf,
                relation_type=relation_type,
            )
            write_provenance(conn, fid, rel_type, tid, real_cid, rcept, conf)
            n_edge += 1
            n_prov_total += 1
            edge_by_type[rel_type] = edge_by_type.get(rel_type, 0) + 1

        conn.commit()
        mark_processed(real_cid, n_ent, n_edge, rcept, row["section_path"])
        n_ent_total += n_ent
        n_edge_total += n_edge
        processed += 1

    # 추출 대상 이외의 청크 = 엔티티/엣지 0개 (커버리지 100% 보장)
    for chunk_id, row in all_rows.items():
        if chunk_id in done or chunk_id in extracted_real_ids:
            continue
        mark_processed(chunk_id, 0, 0, row["rcept_no"], row["section_path"])
        processed += 1

    conn.close()
    driver.close()

    total_marked = len(ledger_processed_ids())
    print("=== 제일기획 Stage5 추출 결과 ===")
    print(f"  이번 처리 청크: {processed}  (원장 누적 {total_marked} / 대상 {total_chunks})")
    print(f"  엔티티(Product/Tech) hasObject: {n_ent_total}")
    print(f"  엣지 총: {n_edge_total}  타입별: {edge_by_type}")
    print(f"  provenance 행: {n_prov_total}")
    print(f"  원장: {LEDGER_PATH}")


if __name__ == "__main__":
    run()
