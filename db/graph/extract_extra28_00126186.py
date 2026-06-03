"""Stage 5 비정형 추출 — 삼성에스디에스 corp_code=00126186, text_micro 전체(~1,237) + table_nl 특수관계(~26).

삼성에스디에스 = IT서비스(클라우드·SI·ITO) + 물류(Cello Square).
제품(Product) = Samsung Cloud Platform(SCP), Cello Square, FabriX, Brightics, Brity Works, Nexprime SCM, Brity Copilot, Caidentia, SI/ITO 서비스.
기술(Technology) = 클라우드 CSP/MSP/SaaS, AI, 블록체인, 디지털포워딩, IT Shared Service.
특수관계자 = 삼성전자(최대 고객·대주주 계열), 엠로(종속기업, 23년 인수), SVIC조합(종속), 해외법인 등.

원장 = db/graph/ledger/extra28_00126186.jsonl (이 추출 전용).
실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_extra28_00126186.py
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

CORP = "삼성에스디에스"
CORP_CODE = "00126186"

# ── 전용 원장 ─────────────────────────────────────────────────
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_DIR.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = LEDGER_DIR / "extra28_00126186.jsonl"


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


# ── Claude 추출 결과 (청크별) ──────────────────────────────────
# from/to = ('org', 회사명) | ('ent', label, canonical, name)
# 삼성에스디에스 핵심 제품군:
#   IT서비스: CSP(SCP), MSP, SaaS(Brity Works, Brightics, Nexprime SCM, Caidentia(SRM), Brity Copilot)
#             FabriX(AI 플랫폼), GPUaaS, SI, ITO
#   물류: Cello Square(디지털포워딩), 글로벌통합물류
# 특수관계: 삼성전자(최대 IT/물류 고객·그 밖의 특수관계자), 엠로(종속기업, SRM 1위 인수)
#           SVIC 39/50/65호 신기술사업투자조합(종속), SDS-MP Logistics(베트남 합작)
#           한국정보인증(24년 전량 매각)
EXTRACTIONS: dict[str, dict] = {

    # ── II. 사업의 내용: 물류 — Cello Square (반기보고서 2024.06) ──
    "0015e12f87ea55c1": {  # Cello Square 디지털 물류 플랫폼, 국제·내륙·물류센터·이커머스·프로젝트 물류
        "entities": [
            (P, "cello square", "Cello Square"),
            (P, "글로벌통합물류서비스", "글로벌 통합물류 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cello square", "Cello Square"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "글로벌통합물류서비스", "글로벌 통합물류 서비스"), 0.92),
        ],
    },

    # ── II. 사업의 내용: 경쟁사 언급 (사업보고서 2023.12) ──────────
    "009eef0570034e20": {  # IT서비스 사업자: IBM, Accenture, NTT Data; 물류: DHL, UPS, DB Schenker
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "IBM"), ("org", CORP), 0.78, ),
            E("SUPPLIES_TO", ("org", "Accenture"), ("org", CORP), 0.78),
        ],
    },

    # ── II. 사업의 내용: 설비 현황 — 상암센터, 삼성 관계사 IT서비스 (사업보고서 2025.12) ──
    "01558f172aa09ce0": {  # 상암센터: 삼성생명·삼성화재 IT 인프라 서비스 제공 거점
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성생명보험"), 0.88, ),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성화재해상보험"), 0.88),
        ],
    },

    # ── II. 사업의 내용: IT서비스 3개 분야 — CSP/MSP/SaaS (분기보고서 2024.09) ──
    "089db3a448096b58": {  # SCP(CSP), MSP End-to-End, SaaS(Brity Works 협업솔루션)
        "entities": [
            (P, "samsung cloud platform", "Samsung Cloud Platform (SCP)"),
            (P, "brity works", "Brity Works"),
            (T, "클라우드 csp", "클라우드 CSP 서비스"),
            (T, "클라우드 msp", "클라우드 MSP 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "samsung cloud platform", "Samsung Cloud Platform (SCP)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "brity works", "Brity Works"), 0.92),
            E("USES_TECH", ("org", CORP), ("ent", T, "클라우드 csp", "클라우드 CSP 서비스"), 0.90),
            E("USES_TECH", ("org", CORP), ("ent", T, "클라우드 msp", "클라우드 MSP 서비스"), 0.90),
        ],
    },

    # ── II. 사업의 내용: SaaS — Brity Works, Nexprime, Brightics, 엠로 인수 (분기보고서 2024.03) ──
    "0adde6fd30cb43e7": {  # Brity Works(메일·메신저·미팅), Nexprime SCM/HCM, Brightics, 엠로 지분인수(SRM1위)
        "entities": [
            (P, "brity works", "Brity Works"),
            (P, "nexprime scm", "Nexprime SCM"),
            (P, "brightics", "Brightics"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "brity works", "Brity Works"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "nexprime scm", "Nexprime SCM"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "brightics", "Brightics"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "엠로"), 0.92, "종속기업(SRM 1위 기업, 23년 지분 인수)"),
        ],
    },

    # ── II. 사업의 내용: 물류 + 삼성전자 관계사 IT/물류 (분기보고서 2025.09) ──
    "0ae0534dedb0aeb1": {  # 삼성전자 포함 삼성 관계사들에게 IT서비스 제공, 단일 화주 물동량
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.93),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.92, "그 밖의 특수관계자(최대 IT/물류 고객, 삼성그룹 계열)"),
        ],
    },

    # ── II. 사업의 내용: CSP(SCP), MSP, FabriX, Brity Copilot (분기보고서 2025.03) ──
    "0a1fbfc524dfc9dc": {  # SCP CSP서비스, MSP 전환/구축/운영
        "entities": [
            (P, "samsung cloud platform", "Samsung Cloud Platform (SCP)"),
            (T, "클라우드 csp", "클라우드 CSP 서비스"),
            (T, "클라우드 msp", "클라우드 MSP 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "samsung cloud platform", "Samsung Cloud Platform (SCP)"), 0.95),
            E("USES_TECH", ("org", CORP), ("ent", T, "클라우드 csp", "클라우드 CSP 서비스"), 0.90),
            E("USES_TECH", ("org", CORP), ("ent", T, "클라우드 msp", "클라우드 MSP 서비스"), 0.88),
        ],
    },

    # ── II. 사업의 내용: Cello Square 디지털포워딩 (사업보고서 2024.12) ──
    "0a60a2a379904b94": {  # Cello Square 글로벌 36개국 종합물류, 디지털포워딩
        "entities": [
            (P, "cello square", "Cello Square"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cello square", "Cello Square"), 0.95),
        ],
    },

    # ── II. 사업의 내용: FabriX + Brity Copilot (반기보고서 2024.06) ──
    "38c06f28420086dd": {  # FabriX(패브릭스, 생성형AI 플랫폼), Brity Copilot, SCP CSP/MSP
        "entities": [
            (P, "fabrix", "FabriX"),
            (P, "brity copilot", "Brity Copilot"),
            (P, "samsung cloud platform", "Samsung Cloud Platform (SCP)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "fabrix", "FabriX"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "brity copilot", "Brity Copilot"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "samsung cloud platform", "Samsung Cloud Platform (SCP)"), 0.93),
        ],
    },

    # ── II. 사업의 내용: SCP CSP/MSP/FabriX/Brity Copilot (분기보고서 2024.03) ──
    "5b8d0f8fafb7e0bc": {  # FabriX, Brity Copilot, SCP 언급
        "entities": [
            (P, "fabrix", "FabriX"),
            (P, "brity copilot", "Brity Copilot"),
            (P, "samsung cloud platform", "Samsung Cloud Platform (SCP)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "fabrix", "FabriX"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "brity copilot", "Brity Copilot"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "samsung cloud platform", "Samsung Cloud Platform (SCP)"), 0.92),
        ],
    },

    # ── II. 사업의 내용: IT서비스 3개분야 개요 (분기보고서 2024.03) ──
    "5847cccd04fc47a2": {  # 클라우드·SI·ITO 3개 분야, SCP 하이브리드 멀티클라우드
        "entities": [
            (P, "samsung cloud platform", "Samsung Cloud Platform (SCP)"),
            (T, "하이브리드 멀티클라우드", "하이브리드 멀티클라우드"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "samsung cloud platform", "Samsung Cloud Platform (SCP)"), 0.95),
            E("USES_TECH", ("org", CORP), ("ent", T, "하이브리드 멀티클라우드", "하이브리드 멀티클라우드"), 0.88),
        ],
    },

    # ── II. 사업의 내용: Cello Square 디지털포워딩 (사업보고서 2025.12) ──
    "06bd0901a8faa46e": {  # Cello Square 50개국 글로벌, AI 데이터 분석 하이테크 물류
        "entities": [
            (P, "cello square", "Cello Square"),
            (T, "ai 데이터분석", "AI 기반 데이터 분석"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cello square", "Cello Square"), 0.95),
            E("USES_TECH", ("org", CORP), ("ent", T, "ai 데이터분석", "AI 기반 데이터 분석"), 0.88),
        ],
    },

    # ── II. 사업의 내용: SCP/SaaS/FabriX/Brity Works (분기보고서 2025.09) ──
    "0dd48310c5ac75d6": {  # SCP CSP/MSP/SaaS, Brity Works, FabriX(AI 플랫폼)
        "entities": [
            (P, "samsung cloud platform", "Samsung Cloud Platform (SCP)"),
            (P, "brity works", "Brity Works"),
            (P, "fabrix", "FabriX"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "samsung cloud platform", "Samsung Cloud Platform (SCP)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "brity works", "Brity Works"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "fabrix", "FabriX"), 0.93),
        ],
    },

    # ── II. 사업의 내용: SCP/SaaS — Brity Works/FabriX/Caidentia (분기보고서 2026.03) ──
    "114b1a87e7ff0062": {  # Brity Works, Caidentia(SRM), FabriX(AI 플랫폼), Brity Copilot(AI 솔루션), GPUaaS, AX센터
        "entities": [
            (P, "brity works", "Brity Works"),
            (P, "caidentia", "Caidentia"),
            (P, "fabrix", "FabriX"),
            (P, "brity copilot", "Brity Copilot"),
            (T, "gpuaas", "GPUaaS"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "brity works", "Brity Works"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "caidentia", "Caidentia"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "fabrix", "FabriX"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "brity copilot", "Brity Copilot"), 0.93),
            E("USES_TECH", ("org", CORP), ("ent", T, "gpuaas", "GPUaaS"), 0.88),
        ],
    },

    # ── II. 사업의 내용: SCP/SaaS — Brity Works/FabriX (사업보고서 2024.12) ──
    "14069da8d42ca7d8": {  # SCP CSP/MSP/SaaS(Brity Works), FabriX AI 플랫폼 언급
        "entities": [
            (P, "samsung cloud platform", "Samsung Cloud Platform (SCP)"),
            (P, "brity works", "Brity Works"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "samsung cloud platform", "Samsung Cloud Platform (SCP)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "brity works", "Brity Works"), 0.92),
        ],
    },

    # ── II. 사업의 내용: Cello Square (반기보고서 2025.06) ──────────
    "1334f8ed38e5b6be": {  # Cello Square 디지털포워딩, 바이오·배터리·프로젝트 특화 물류
        "entities": [
            (P, "cello square", "Cello Square"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cello square", "Cello Square"), 0.95),
        ],
    },

    # ── II. 사업의 내용: 블록체인·AI 등 Digital 기술 (사업보고서 2024.12) ──
    "06d0c1406b36ac6e": {  # 클라우드·AI·빅데이터·블록체인 등 DX 기술
        "entities": [
            (T, "블록체인", "블록체인"),
            (T, "ai 데이터분석", "AI 기반 데이터 분석"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "블록체인", "블록체인"), 0.82),
            E("USES_TECH", ("org", CORP), ("ent", T, "ai 데이터분석", "AI 기반 데이터 분석"), 0.85),
        ],
    },

    # ── II. 사업의 내용: AI·블록체인·IoT 전문인력 확보 (사업보고서 2023.12) ──
    "11d79fc9ac94ae12": {  # 클라우드·AI·빅데이터·블록체인·엔터프라이즈모빌리티·IoT 전문인력
        "entities": [
            (T, "블록체인", "블록체인"),
            (T, "iot", "IoT"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "블록체인", "블록체인"), 0.80),
            E("USES_TECH", ("org", CORP), ("ent", T, "iot", "IoT"), 0.80),
        ],
    },

    # ── II. 사업의 내용: IT Shared Service + ITO (분기보고서 2026.03) ──
    "04e79f7f69d0eb5e": {  # IT Shared Service(그룹 관계사 통합운영), ITO, 데이터센터 인프라
        "entities": [
            (P, "it shared service", "IT Shared Service"),
            (T, "데이터센터 인프라", "데이터센터 인프라 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "it shared service", "IT Shared Service"), 0.90),
            E("USES_TECH", ("org", CORP), ("ent", T, "데이터센터 인프라", "데이터센터 인프라 서비스"), 0.85),
        ],
    },

    # ── II. 사업의 내용: 가격변동추이 — IT서비스 + 물류 맞춤서비스 (사업보고서 2023.12) ──
    "03572e4f5bc7e871": {  # IT서비스(SI, ITO, 클라우드) + 물류; Cello Square 데이터 분석·예측
        "entities": [
            (P, "cello square", "Cello Square"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cello square", "Cello Square"), 0.92),
        ],
    },

    # ── II. 사업의 내용: AI·블록체인 DX (기재정정 사업보고서 2023.12) ──
    "085cf589ea00f700": {  # AI·빅데이터·블록체인 Digital 기술 시장 변화
        "entities": [
            (T, "블록체인", "블록체인"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "블록체인", "블록체인"), 0.80),
        ],
    },

    # ── II. 사업의 내용: 클라우드·AI·IoT 경쟁력 (반기보고서 2025.06) ──
    "07f9ccb3138eabf4": {  # 클라우드·AI·빅데이터·블록체인·IoT 전문인력 확보
        "entities": [
            (T, "iot", "IoT"),
            (T, "ai 데이터분석", "AI 기반 데이터 분석"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "iot", "IoT"), 0.80),
            E("USES_TECH", ("org", CORP), ("ent", T, "ai 데이터분석", "AI 기반 데이터 분석"), 0.83),
        ],
    },

    # ── II. 사업의 내용: 특수관계 매입처 없음 공시 (분기보고서 2024.09) ──
    "07eed13aba3b3af8": {  # 주요 매입처 중 특수관계 없음; IT서비스 특성 상 맞춤 서비스
        "entities": [],
        "edges": [],
    },

    # ── II. 사업의 내용: 해외 수주·레퍼런스 (사업보고서 2023.12) ──
    "07f71c1cb7103b5f": {  # 해외사업 수주: 레퍼런스·주변 국가 공급 방식
        "entities": [],
        "edges": [],
    },

    # ── IX. 계열회사: 삼성그룹 63개사 (사업보고서 2023.12) ──────────
    "47c9c023d0afa864": {  # 삼성그룹 63개 계열회사, 삼성에스디에스 포함 17개 상장사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.88, "그 밖의 특수관계자(삼성그룹 계열)"),
        ],
    },

    # ── IX. 계열회사: 삼성그룹 63개사 (기재정정 사업보고서 2023.12) ──
    "55da559553c3c53e": {  # 동일
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.88, "그 밖의 특수관계자(삼성그룹 계열)"),
        ],
    },

    # ── IX. 계열회사: 2024 반기 (반기보고서 2024.06) ────────────────
    "87d1c89f56aeccbb": {  # 삼성그룹 63개사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.88, "그 밖의 특수관계자(삼성그룹 계열)"),
        ],
    },

    # ── IX. 계열회사: 2025 반기 (반기보고서 2025.06) ────────────────
    "2254358a88a3d472": {  # 삼성그룹 63개사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.87, "그 밖의 특수관계자(삼성그룹 계열)"),
        ],
    },

    # ── X. 대주주 거래: 영업거래 (사업보고서 2023.12) ────────────────
    "3488f06a3980f352": {  # 대주주(삼성전자 등) 영업거래, IT서비스 공급
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.92, "그 밖의 특수관계자(최대 고객, IT서비스 공급)"),
        ],
    },

    # ── X. 대주주 거래: 영업거래 (분기보고서 2024.09) ────────────────
    "3d90e5452e357aa5": {  # 대주주 영업거래
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.90, "그 밖의 특수관계자(IT서비스·물류 공급)"),
        ],
    },

    # ── X. 대주주 거래: 영업거래 (사업보고서 2025.12) ────────────────
    "4b5a13345b7acadd": {  # 대주주 영업거래
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.90, "그 밖의 특수관계자(IT서비스 공급)"),
        ],
    },

    # ── X. 대주주 거래: 영업거래 (반기보고서 2025.06) ───────────────
    "54f9b8d04cea55bd": {  # 대주주 영업거래
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.91),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.90, "그 밖의 특수관계자(IT서비스 공급)"),
        ],
    },

    # ── 감사보고서 특수관계자 주석 — SVIC조합·엠로 (사업보고서 2023.12) ──
    "aea4ba6f47f7e870": {  # SVIC 39호 청산, 엠로 신규 취득, 엠로 종속기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "엠로"), 0.95, "종속기업(23년 지분 인수, SRM 1위)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 39호 신기술사업투자조합"), 0.90, "종속기업(23년 청산)"),
        ],
    },

    # ── 재무제표주석 특수관계자: SVIC·엠로·Samsung SDS Global SCL Greece (사업보고서 2023.12) ──
    "89ea6107a0a48cb5": {  # SVIC 39/50호, 엠로, Samsung SDS Global SCL Greece 종속기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "엠로"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 39호 신기술사업투자조합"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 50호 신기술사업투자조합"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Samsung SDS Global SCL Greece"), 0.88, "종속기업(물류 해외법인)"),
        ],
    },

    # ── 재무제표주석 특수관계자 (기재정정 사업보고서 2023.12) ───────
    "b3de39b7f756b553": {  # SVIC 39/50호, 엠로, Samsung SDS Global SCL Greece
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "엠로"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 39호 신기술사업투자조합"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 50호 신기술사업투자조합"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Samsung SDS Global SCL Greece"), 0.88, "종속기업"),
        ],
    },

    # ── 재무제표주석 특수관계자 (기재정정 2023.12 별도) ───────────────
    "e7fbcd554c70dd7f": {  # SVIC 39/50호, 엠로, Samsung SDS Global SCL Greece
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "엠로"), 0.94, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 50호 신기술사업투자조합"), 0.90, "종속기업"),
        ],
    },

    # ── 연결재무제표주석 특수관계자 (분기보고서 2024.09) ──────────────
    "5cf1351c06a6dd0f": {  # 한국정보인증 전량 매도, SVIC 65호 신규 출자, 엠로 주식 추가 취득
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "엠로"), 0.95, "종속기업(SRM)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 65호 신기술사업투자조합"), 0.90, "종속기업(신규 출자)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "한국정보인증"), 0.85, "관계기업(24.09 전량 매각)"),
        ],
    },

    # ── 재무제표주석 특수관계자 (분기보고서 2024.09) ──────────────────
    "e488223cfac04a0b": {  # SVIC 65호 신규 출자, 엠로 주식 추가 취득, 한국정보인증 매도
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "엠로"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 65호 신기술사업투자조합"), 0.90, "종속기업(신규 출자)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "한국정보인증"), 0.85, "관계기업(매각)"),
        ],
    },

    # ── 재무제표주석 특수관계자 (사업보고서 2024.12) ──────────────────
    "4de6ab78de73e6ac": {  # SVIC 39/50/65호, 엠로, 한국정보인증 매각
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "엠로"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 39호 신기술사업투자조합"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 50호 신기술사업투자조합"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 65호 신기술사업투자조합"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "한국정보인증"), 0.85, "관계기업(24년 매각)"),
        ],
    },

    # ── 재무제표주석 특수관계자 거래표 (사업보고서 2024.12) — 연결 ──
    "6a3266675376e86f": {  # SVIC 39/50/65호, 엠로 종속기업 거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "엠로"), 0.93, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 39호 신기술사업투자조합"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 50호 신기술사업투자조합"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 65호 신기술사업투자조합"), 0.88, "종속기업"),
        ],
    },

    # ── 재무제표주석 특수관계자 거래표 (사업보고서 2024.12) — 별도 ──
    "73a16e08581dfb90": {  # SVIC 39/50/65호, 엠로 종속기업 거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "엠로"), 0.93, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 50호 신기술사업투자조합"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 65호 신기술사업투자조합"), 0.88, "종속기업"),
        ],
    },

    # ── 감사보고서 특수관계자 주석 (사업보고서 2024.12) ─────────────
    "8f7c36f733f8efc1": {  # SVIC 65호 신규 출자, 엠로 추가 취득, 한국정보인증 매각
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "엠로"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 65호 신기술사업투자조합"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "한국정보인증"), 0.85, "관계기업(전량 매각)"),
        ],
    },

    # ── 연결감사보고서 특수관계자 (사업보고서 2024.12) ──────────────
    "43e8bc3794d06a8e": {  # 한국정보인증 전량 매도, 불균등 유상증자로 관계기업 제외
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "한국정보인증"), 0.85, "관계기업(24년 전량 매각)"),
        ],
    },

    # ── 연결감사보고서 특수관계자 (사업보고서 2024.12) — 별도 ───────
    "a96751611b5c17ed": {  # 한국정보인증 전량 매도, 불균등 유상증자 관계기업 제외
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "한국정보인증"), 0.85, "관계기업(24년 전량 매각)"),
        ],
    },

    # ── 재무제표주석 특수관계자 (분기보고서 2025.03) ─────────────────
    "4c52720bc2894e30": {  # SVIC 39/50호 종속기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 39호 신기술사업투자조합"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 50호 신기술사업투자조합"), 0.90, "종속기업"),
        ],
    },

    # ── 재무제표주석 특수관계자 (분기보고서 2025.03) — 별도 ─────────
    "c7916c53e575c3bb": {  # SVIC 39/50호 종속기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 39호 신기술사업투자조합"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 50호 신기술사업투자조합"), 0.90, "종속기업"),
        ],
    },

    # ── 재무제표주석 특수관계자 (반기보고서 2025.06) ─────────────────
    "20a6e7ff81cc2028": {  # SVIC 50/65호 종속기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 50호 신기술사업투자조합"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 65호 신기술사업투자조합"), 0.90, "종속기업"),
        ],
    },

    # ── 재무제표주석 특수관계자 (반기보고서 2025.06) — 별도 ─────────
    "74b69ecb0f5a1df4": {  # SVIC 50/65호 종속기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 50호 신기술사업투자조합"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 65호 신기술사업투자조합"), 0.90, "종속기업"),
        ],
    },

    # ── 재무제표주석 특수관계자 (분기보고서 2025.09) ─────────────────
    "a825be013dc829b6": {  # SVIC 50/65호 종속기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 50호 신기술사업투자조합"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 65호 신기술사업투자조합"), 0.90, "종속기업"),
        ],
    },

    # ── 재무제표주석 특수관계자 (분기보고서 2025.09) — 별도 ─────────
    "b58b3fde09558d3c": {  # SVIC 50/65호 종속기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 50호 신기술사업투자조합"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 65호 신기술사업투자조합"), 0.90, "종속기업"),
        ],
    },

    # ── 재무제표주석 특수관계자 (사업보고서 2025.12) ─────────────────
    "113e4d7f39004f15": {  # SVIC 50/65호 종속기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 50호 신기술사업투자조합"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 65호 신기술사업투자조합"), 0.90, "종속기업"),
        ],
    },

    # ── 재무제표주석 특수관계자 (사업보고서 2025.12) — 별도 ─────────
    "d256669e78324022": {  # SVIC 50/65호 종속기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 50호 신기술사업투자조합"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 65호 신기술사업투자조합"), 0.90, "종속기업"),
        ],
    },

    # ── 연결감사보고서 특수관계자 — 삼성전자 매입 거래 (사업보고서 2025.12) ──
    "f216c752169e119e": {  # 연결실체: 삼성전자로부터 기계장치 매입(전기 9,586백만원), 삼성전자 종속기업들
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.92, "그 밖의 특수관계자(기계장치 매입·IT서비스 파트너)"),
            E("SUPPLIES_TO", ("org", "삼성전자"), ("org", CORP), 0.88),
        ],
    },

    # ── 재무제표주석 특수관계자 (분기보고서 2026.03) ─────────────────
    "426ce592a2fe0d7d": {  # SVIC 50호, SDS-MP Logistics Joint Stock Company 종속기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 50호 신기술사업투자조합"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SDS-MP Logistics Joint Stock Company"), 0.88, "종속기업(베트남 합작물류법인)"),
        ],
    },

    # ── 재무제표주석 특수관계자 (분기보고서 2026.03) — 별도 ─────────
    "64930f56dc2182f6": {  # SVIC 50호, SDS-MP Logistics 종속기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 50호 신기술사업투자조합"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SDS-MP Logistics Joint Stock Company"), 0.88, "종속기업"),
        ],
    },

    # ── 연결재무제표주석 특수관계자 (분기보고서 2026.03) ─────────────
    "1a82aa5645998112": {  # SDS-MP Logistics 지분 일부 매각(지배력 상실 → 관계기업으로 전환)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SDS-MP Logistics Joint Stock Company"), 0.88, "관계기업(26.03 지분 일부 매각 후 유의적 영향력)"),
        ],
    },

    # ── 연결감사보고서 특수관계자 (분기보고서 2026.03) ──────────────
    "d1d43c69e94bf5ce": {  # SDS-MP Logistics 지분 매각, 지배력 상실
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SDS-MP Logistics Joint Stock Company"), 0.88, "관계기업(지분 매각)"),
        ],
    },

    # ── 재무제표주석 특수관계자 (분기보고서 2025.03 — 연결) ─────────
    "414292f51e225faa": {  # SVIC 39/50/65호, 엠로, Samsung SDS Global SCL Greece 종속기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "엠로"), 0.93, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 39호 신기술사업투자조합"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SVIC 50호 신기술사업투자조합"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Samsung SDS Global SCL Greece"), 0.88, "종속기업"),
        ],
    },
}


def run():
    rows_text = get_chunks(
        f"WHERE corp_code='{CORP_CODE}' AND chunk_type='text_micro' ORDER BY chunk_id"
    )
    rows_table = get_chunks(
        f"WHERE corp_code='{CORP_CODE}' AND chunk_type='table_nl' "
        f"AND embedding_text LIKE '%특수관계%' ORDER BY chunk_id"
    )
    all_rows = rows_text + rows_table
    by_id = {r["chunk_id"]: r for r in all_rows}
    print(f"[batch] 대상 text_micro {len(rows_text)}건 + table_nl(특수관계) {len(rows_table)}건 = {len(all_rows)}건")

    done = ledger_processed_ids()
    print(f"[batch] 원장 기처리 {len(done)}건 — 스킵")

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
            print(f"  [warn] {cid} 대상에 없음 — 스킵")
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

    # 2) 나머지 청크 = 엔티티/엣지 0개 (누락 0 보장)
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
    print("=== 삼성에스디에스 Stage5 추출 결과 ===")
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
