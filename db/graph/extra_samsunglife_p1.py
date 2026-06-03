"""비정형 관계 추출 적재 — 삼성생명 (corp_code=00126256) text_micro 전반부 (OFFSET 0, LIMIT 2200).

이 파일의 EXTRACTIONS = Claude(에이전트)가 대상 청크 본문을 읽고
본문 근거로 판단한 엔티티·엣지다. 보험사 특성상 제조 Product 없음;
서비스·금융상품·기술, 계열사·특수관계자 관계 중심.

원장: graph/ledger/extra28_00126256_p1.jsonl (rcept 다중 포함, 배치 전용).
시작 시 원장 확인 → 처리완료 청크 스킵 → 전체 청크 mark_processed(엣지 0개여도).

실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extra_samsunglife_p1.py
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

CORP_CODE = "00126256"
SAMSUNG_LIFE = "삼성생명"  # resolve_org → needs_er (3사 외)

# 배치 전용 원장 (공유 원장 금지)
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_PATH = LEDGER_DIR / "extra28_00126256_p1.jsonl"

P = "Product"
T = "Technology"


def E(rel, frm, to, conf, relation_type=None):
    d = {"rel": rel, "from": frm, "to": to, "conf": conf}
    if relation_type:
        d["relation_type"] = relation_type
    return d


# ── 전용 원장 헬퍼 ──────────────────────────────────────────
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
# 삼성생명 특성: 보험사(생명보험·금융계열지주격) — Product 제조 없음.
# 추출 대상: 서비스 Product(보험/카드/ETF/플랫폼), Technology(IFRS17/K-ICS/모니모 등),
#            계열사 RELATED_PARTY, 위탁운용 SUPPLIES_TO.

EXTRACTIONS: dict[str, dict] = {

    # ══ 삼성생명 본체 — 보험 서비스·기술 ══════════════════════════

    # 삼성금융네트웍스 공동브랜드 + 모니모 통합플랫폼 출시 언급 (복수 청크 반복)
    "0327e3c169774bb0": {  # 삼성금융5개사(생명,화재,카드,증권,자산운용) 삼성금융네트웍스 론칭, 모니모 출시
        "entities": [
            (P, "삼성금융네트웍스", "삼성금융네트웍스"),
            (P, "모니모", "모니모"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG_LIFE), ("ent", P, "삼성금융네트웍스", "삼성금융네트웍스"), 0.88),
            E("PRODUCES", ("org", SAMSUNG_LIFE), ("ent", P, "모니모", "모니모"), 0.88),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성화재"), 0.85, "금융계열(삼성금융네트웍스)"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성카드"), 0.85, "금융계열(삼성금융네트웍스)"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성증권"), 0.85, "금융계열(삼성금융네트웍스)"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성자산운용"), 0.85, "금융계열(삼성금융네트웍스)"),
        ],
    },

    # II.사업 삼성생명 핵심전략 — 보장성보험, IFRS17, K-ICS, 방카슈랑스
    "056e078f25afd6b7": {  # 방카슈랑스·GA채널, 배타적사용권 8건, 자산운용, M&A
        "entities": [
            (T, "ifrs17", "IFRS17(보험국제회계기준)"),
            (T, "k-ics", "K-ICS(신지급여력제도)"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG_LIFE), ("ent", T, "ifrs17", "IFRS17(보험국제회계기준)"), 0.88),
            E("USES_TECH", ("org", SAMSUNG_LIFE), ("ent", T, "k-ics", "K-ICS(신지급여력제도)"), 0.88),
        ],
    },
    "062760b51628e6d2": {  # IFRS17/K-ICS 시행 → 차별적 자본력, 보장성보험 경쟁우위
        "entities": [],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG_LIFE), ("ent", T, "ifrs17", "IFRS17(보험국제회계기준)"), 0.9),
            E("USES_TECH", ("org", SAMSUNG_LIFE), ("ent", T, "k-ics", "K-ICS(신지급여력제도)"), 0.9),
        ],
    },
    "08105cacae84b9ff": {  # 삼성자산운용·SRA와 협업 ALM, 시니어리빙/헬스케어/신탁 신사업
        "entities": [
            (P, "시니어리빙서비스", "시니어리빙서비스"),
            (P, "헬스케어서비스", "헬스케어서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG_LIFE), ("ent", P, "시니어리빙서비스", "시니어리빙서비스"), 0.78),
            E("PRODUCES", ("org", SAMSUNG_LIFE), ("ent", P, "헬스케어서비스", "헬스케어서비스"), 0.78),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성자산운용"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성SRA자산운용"), 0.88, "종속기업"),
        ],
    },

    # ══ 1. 삼성카드 (주요 종속회사) ══════════════════════════════

    # 삼성카드 신용카드·카드금융·할부리스 서비스
    "04470027d1965e7f": {  # 삼성카드 종속회사 소개 — 신용카드 시장, 카드금융
        "entities": [
            (P, "신용카드", "신용카드"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성카드"), 0.95, "종속기업"),
            E("PRODUCES", ("org", "삼성카드"), ("ent", P, "신용카드", "신용카드"), 0.92),
        ],
    },
    "010138bef8a03789": {  # 삼성카드 기타수익사업 — 통신판매·온라인 판매채널
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성카드"), 0.93, "종속기업"),
        ],
    },
    "04a65fdfcce9c086": {  # 삼성카드 신용카드시장 경쟁력 — 데이터분석, 디지털채널, 파트너십
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성카드"), 0.92, "종속기업"),
        ],
    },
    "0414cdcf0d4d5006": {  # 삼성카드 상품개발/회원유치/가맹점 마케팅, 할부리스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성카드"), 0.92, "종속기업"),
        ],
    },
    "06fe97b2a52fc165": {  # 삼성카드 다이렉트오토, Tesla·Polestar 단독카드계약
        "entities": [
            (P, "다이렉트오토", "다이렉트오토"),
        ],
        "edges": [
            E("PRODUCES", ("org", "삼성카드"), ("ent", P, "다이렉트오토", "다이렉트오토"), 0.88),
            E("RELATED_PARTY", ("org", "삼성카드"), ("org", "Tesla"), 0.85, "단독카드결제계약"),
            E("RELATED_PARTY", ("org", "삼성카드"), ("org", "Polestar"), 0.82, "단독카드결제계약"),
        ],
    },
    "07ff0b7fc6894cdd": {  # 삼성카드 1,291만 회원/305만 가맹점, 신용판매·카드금융
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성카드"), 0.92, "종속기업"),
        ],
    },

    # ══ 2. 삼성자산운용 (주요 종속회사) ══════════════════════════

    # 삼성자산운용 — ETF(KODEX), 펀드 운용
    "05f21500e499ec92": {  # 삼성자산운용 KODEX 200, ETF 1위 운용사, 액티브ETF·신재생에너지ETF
        "entities": [
            (P, "kodex 200", "KODEX 200"),
            (P, "etf", "ETF"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성자산운용"), 0.92, "종속기업"),
            E("PRODUCES", ("org", "삼성자산운용"), ("ent", P, "kodex 200", "KODEX 200"), 0.92),
            E("PRODUCES", ("org", "삼성자산운용"), ("ent", P, "etf", "ETF"), 0.9),
        ],
    },
    "00e5c244f90e1453": {  # 삼성자산운용 인프라펀드·실물자산펀드·인수금융펀드·PE·PD 펀드
        "entities": [
            (P, "인프라펀드", "인프라펀드"),
            (P, "글로벌pe펀드", "글로벌 PE펀드"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성자산운용"), 0.92, "종속기업"),
            E("PRODUCES", ("org", "삼성자산운용"), ("ent", P, "인프라펀드", "인프라펀드"), 0.88),
            E("PRODUCES", ("org", "삼성자산운용"), ("ent", P, "글로벌pe펀드", "글로벌 PE펀드"), 0.85),
        ],
    },
    "01558657dff4e893": {  # 삼성자산운용 물적분할 → 삼성액티브자산운용 설립, Amplify 지분취득
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성자산운용"), 0.92, "종속기업"),
            E("RELATED_PARTY", ("org", "삼성자산운용"), ("org", "삼성액티브자산운용"), 0.88, "물적분할(설립)"),
            E("RELATED_PARTY", ("org", "삼성자산운용"), ("org", "Amplify"), 0.82, "지분취득"),
        ],
    },
    "075f1840fc6ca041": {  # 삼성자산운용 가치투자역량, 전문인력, 위험관리
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성자산운용"), 0.9, "종속기업"),
        ],
    },

    # ══ 3. Samsung Life Insurance (Thailand) ══════════════════════

    "007fd171942c1fa4": {  # 태국법인 — 태국 생보시장, IFRS17 보장성보험 전환
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "Samsung Life Insurance (Thailand)"), 0.92, "종속기업"),
            E("USES_TECH", ("org", "Samsung Life Insurance (Thailand)"), ("ent", T, "ifrs17", "IFRS17(보험국제회계기준)"), 0.82),
        ],
    },
    "020ac4e30d5d48d5": {  # 태국법인 설립(1997), 현지 생명보험, 동남아시아 허브
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "Samsung Life Insurance (Thailand)"), 0.93, "종속기업"),
        ],
    },
    "03f3483bf2e186c0": {  # 태국법인 설계사 11,922명, 설계사채널 중심, 5개 육성센터
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "Samsung Life Insurance (Thailand)"), 0.93, "종속기업"),
        ],
    },
    "04090a87a43fae67": {  # Samsung Life Insurance (Thailand) — K-IFRS 별도재무 건전성
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "Samsung Life Insurance (Thailand)"), 0.92, "종속기업"),
        ],
    },

    # ══ 4. 북경삼성치업유한공사 ══════════════════════════════════

    "0122191eff3033ed": {  # 북경삼성치업유한공사 — 베이징 CBD 오피스빌딩, 임대·운영
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "북경삼성치업유한공사"), 0.9, "종속기업"),
        ],
    },
    "028ddd186f8ed858": {  # 북경삼성치업유한공사 지급여력비율(RBC)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "북경삼성치업유한공사"), 0.88, "종속기업"),
        ],
    },
    "02139f6e77ac74cd": {  # 북경삼성치업유한공사 — RBC 지급여력비율(2025사업보고서)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "북경삼성치업유한공사"), 0.88, "종속기업"),
        ],
    },
    "03e061819bd7fb46": {  # 북경삼성치업유한공사 CBD 경쟁강점/약점
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "북경삼성치업유한공사"), 0.88, "종속기업"),
        ],
    },

    # ══ 5. 삼성생명서비스손해사정 ══════════════════════════════

    "00a050e028252cd3": {  # 삼성생명서비스손해사정 설립(2000), 2011년 자회사 편입, 콜센터 위탁운영
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성생명서비스손해사정"), 0.93, "종속기업"),
        ],
    },
    "02827d33692189cc": {  # 삼성생명서비스손해사정 고객접점 중요성, 삼성에스알에이자산운용 소개
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성생명서비스손해사정"), 0.92, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성SRA자산운용"), 0.92, "종속기업"),
        ],
    },

    # ══ 6. 삼성생명금융서비스 ══════════════════════════════════

    "05346501dc6a9861": {  # 삼성생명금융서비스 설립(2015), 보험금융판매전문회사, 보험대리점업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성생명금융서비스"), 0.93, "종속기업"),
        ],
    },
    "0584bf79765cd780": {  # 삼성생명금융서비스 — AFC유니온지점, 초대형GA 성장, 생손보제휴 확대
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성생명금융서비스"), 0.93, "종속기업"),
        ],
    },

    # ══ 7. 삼성에스알에이(SRA)자산운용 ══════════════════════════

    "065ef3700ed20254": {  # 삼성자산운용 자산운용업(ETF, 재간접펀드, PEF) + 삼성SRA 오피스 공실률
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성SRA자산운용"), 0.9, "종속기업"),
        ],
    },
    "0327e3c169774bb0": {  # 위 중복 — 삼성금융네트웍스·모니모 (이미 위에 등록)
        # 이 chunk_id는 위에서 처리
    },

    # ══ IX. 계열회사 — 삼성그룹 계열 현황 ══════════════════════

    "42f2d0b8e7f4c8de": {  # 사업보고서2023 삼성그룹 63개 계열사, 상장17·비상장46
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성전자"), 0.88, "대규모기업집단계열회사"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성물산"), 0.85, "대규모기업집단계열회사"),
        ],
    },
    "4a6ca5745ca1e323": {  # 기재정정사업보고서2023 삼성그룹 63개 계열사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성전자"), 0.88, "대규모기업집단계열회사"),
        ],
    },
    "d1e2bd1b724bc3f2": {  # 기재정정2023 삼성그룹 63개 계열사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성전자"), 0.88, "대규모기업집단계열회사"),
        ],
    },
    "7d2675bedac73a9f": {  # 사업보고서2024 삼성그룹 63개 계열사, 상장17·비상장46
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성전자"), 0.88, "대규모기업집단계열회사"),
        ],
    },
    "570ec3e1004c7ba8": {  # 기재정정사업보고서2024 삼성그룹 63개 계열사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성전자"), 0.88, "대규모기업집단계열회사"),
        ],
    },
    "2e71ccb9ec9acd48": {  # 사업보고서2025 삼성그룹 67개 계열사(4개 증가), 상장18·비상장49
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성전자"), 0.88, "대규모기업집단계열회사"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성에피스홀딩스"), 0.82, "계열사신규편입"),
        ],
    },
    "1e179254de5266ab": {  # 기재정정사업보고서2025 삼성그룹 67개 계열사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성전자"), 0.88, "대규모기업집단계열회사"),
        ],
    },
    "3dd593db40d23ad7": {  # 반기보고서2024 삼성그룹 63개 계열사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성전자"), 0.85, "대규모기업집단계열회사"),
        ],
    },
    "034f43131ccdb0bf": {  # 기재정정반기2024 삼성그룹 63개 계열사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성전자"), 0.85, "대규모기업집단계열회사"),
        ],
    },
    "57f5d5d93bd61571": {  # 반기보고서2025 삼성그룹 63개 계열사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성전자"), 0.85, "대규모기업집단계열회사"),
        ],
    },

    # ══ X. 대주주 거래내용 — 삼성자산운용·삼성증권 위탁거래 ══════

    "510b734d777cfc17": {  # 사업보고서2023 — 삼성자산운용 운용 채권/수익증권을 삼성증권 통해 매수·매도
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.88, ),
            E("SUPPLIES_TO", ("org", "삼성증권"), ("org", SAMSUNG_LIFE), 0.85, ),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성자산운용"), 0.9, "종속기업(위탁운용)"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성증권"), 0.88, "관계기업(위탁매매)"),
        ],
    },
    "625ee70740314cd1": {  # 기재정정2023 — 삼성자산운용 수익증권/채권 삼성증권 통해 매매
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.88),
            E("SUPPLIES_TO", ("org", "삼성증권"), ("org", SAMSUNG_LIFE), 0.85),
        ],
    },
    "b9fce8f8fd945954": {  # 기재정정2023 — 삼성자산운용 수익증권/채권 삼성증권 통해 매매
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.88),
            E("SUPPLIES_TO", ("org", "삼성증권"), ("org", SAMSUNG_LIFE), 0.85),
        ],
    },
    "3ec3f868211f1264": {  # 반기2024 — 삼성자산운용 수익증권/채권 삼성증권 통해 매매
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.88),
            E("SUPPLIES_TO", ("org", "삼성증권"), ("org", SAMSUNG_LIFE), 0.85),
        ],
    },
    "a5fd52f76a46e4c3": {  # 기재정정반기2024 — 삼성자산운용 수익증권/채권 삼성증권 통해 매매
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.88),
            E("SUPPLIES_TO", ("org", "삼성증권"), ("org", SAMSUNG_LIFE), 0.85),
        ],
    },
    "dd66d5a0adafc4e1": {  # 사업보고서2024 — 삼성자산운용 수익증권/채권 삼성증권 통해 매매
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.88),
            E("SUPPLIES_TO", ("org", "삼성증권"), ("org", SAMSUNG_LIFE), 0.85),
        ],
    },
    "82cbccda06891ddb": {  # 기재정정사업보고서2024 — 삼성자산운용 수익증권/채권 삼성증권 통해 매매
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.88),
            E("SUPPLIES_TO", ("org", "삼성증권"), ("org", SAMSUNG_LIFE), 0.85),
        ],
    },
    "2e8f64247c6888ea": {  # 분기2024.09 — 삼성자산운용 수익증권/채권 삼성증권 통해 매매
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.88),
            E("SUPPLIES_TO", ("org", "삼성증권"), ("org", SAMSUNG_LIFE), 0.85),
        ],
    },
    "e48259c042330bdc": {  # 기재정정분기2024.09 — 삼성자산운용 수익증권/채권 삼성증권
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.88),
            E("SUPPLIES_TO", ("org", "삼성증권"), ("org", SAMSUNG_LIFE), 0.85),
        ],
    },
    "2f1c5247c4702ffa": {  # 분기2025.03 — 삼성증권 통해 주식 장내처분, 삼성자산운용 채권
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.88),
            E("SUPPLIES_TO", ("org", "삼성증권"), ("org", SAMSUNG_LIFE), 0.85),
        ],
    },
    "ec1dc265b7a6d945": {  # 기재정정분기2025.03 — 삼성자산운용 채권 삼성증권 통해
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.88),
            E("SUPPLIES_TO", ("org", "삼성증권"), ("org", SAMSUNG_LIFE), 0.85),
        ],
    },
    "fc2b7a43f9febfc6": {  # 반기2025 — 삼성증권 통해 주식 장내처분, 삼성자산운용 채권
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.88),
            E("SUPPLIES_TO", ("org", "삼성증권"), ("org", SAMSUNG_LIFE), 0.85),
        ],
    },
    "f7abdc3eb91bdfa3": {  # 분기2025.09 — 삼성자산운용 수익증권/채권 삼성증권 통해
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.88),
            E("SUPPLIES_TO", ("org", "삼성증권"), ("org", SAMSUNG_LIFE), 0.85),
        ],
    },
    "cf612254106acf9a": {  # 사업보고서2025 — 삼성자산운용 수익증권/채권 삼성증권 통해 + 잠실빌딩처분
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.88),
            E("SUPPLIES_TO", ("org", "삼성증권"), ("org", SAMSUNG_LIFE), 0.85),
        ],
    },
    "fd11b33bc5b505b3": {  # 기재정정사업보고서2025 — 삼성자산운용/삼성증권 위탁
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.88),
            E("SUPPLIES_TO", ("org", "삼성증권"), ("org", SAMSUNG_LIFE), 0.85),
        ],
    },
    "62ec81e47631aaac": {  # 분기2026.03 — 삼성증권 주식 장내처분, 삼성자산운용 채권, 잠실빌딩처분이익
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.88),
            E("SUPPLIES_TO", ("org", "삼성증권"), ("org", SAMSUNG_LIFE), 0.85),
        ],
    },
    "56c44363a069b9f6": {},  # 분기보고서(분기미기재) — 0엣지
    "95a55cf5c965307e": {  # 기재정정분기2024.03 — 삼성자산운용 채권 삼성증권 통해
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.88),
            E("SUPPLIES_TO", ("org", "삼성증권"), ("org", SAMSUNG_LIFE), 0.85),
        ],
    },
    "b257f8d24f09079e": {  # 기재정정분기2024.03(2) — 삼성자산운용 채권 삼성증권 통해
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.88),
            E("SUPPLIES_TO", ("org", "삼성증권"), ("org", SAMSUNG_LIFE), 0.85),
        ],
    },
    "e6554a31882aab3c": {  # 분기2024.03 — 삼성자산운용 채권 삼성증권 통해
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.88),
            E("SUPPLIES_TO", ("org", "삼성증권"), ("org", SAMSUNG_LIFE), 0.85),
        ],
    },

    # ══ 특수관계자 표(table_nl) — 종속/관계기업 분류 ══════════════

    # 종속기업/관계기업 분류 표 (여러 보고서 반복)
    "b1c9e9ffa8691c0d": {  # 2026.03분기 별도주석 — 종속기업 목록 (삼성생명서비스손해사정, 삼성SRA자산운용 등)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성생명서비스손해사정"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "Samsung Life Insurance (Thailand)"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "북경삼성치업유한공사"), 0.92, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성SRA자산운용"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성자산운용"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성카드"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성생명금융서비스"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성노블라이프"), 0.92, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성증권"), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "에이앤디신용정보"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "신공항하이웨이"), 0.85, "관계기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "코리아크레딧뷰로"), 0.85, "관계기업"),
        ],
    },
    "5887e918c22c9442": {  # 기재정정사업보고서2025 별도주석 — 종속/관계기업 목록
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성생명서비스손해사정"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "Samsung Life Insurance (Thailand)"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성SRA자산운용"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성자산운용"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성카드"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성생명금융서비스"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성노블라이프"), 0.92, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성증권"), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "신공항하이웨이"), 0.85, "관계기업"),
        ],
    },
    "4fa0ac72da28b491": {  # 2026.03분기 연결주석 — 관계기업(삼성증권, 에이앤디, 신공항하이웨이, 코리아크레딧뷰로 등), 대규모기업집단(삼성전자 외 54개)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성증권"), 0.92, "관계기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "에이앤디신용정보"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "신공항하이웨이"), 0.85, "관계기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "코리아크레딧뷰로"), 0.85, "관계기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성전자"), 0.9, "대규모기업집단계열회사"),
        ],
    },

    # 특수관계자 거래내역 — 삼성전자 임대료수익·배당·지급수수료
    "0111e2641329684d": {  # 사업보고서2023 감사보고서 — 삼성전자 배당금수익 733,842백만, 임대료수익 4,905백만; 삼성물산 임대료수익 905백만
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성전자"), 0.93, "대규모기업집단계열회사(배당·임대거래)"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성물산"), 0.88, "대규모기업집단계열회사(임대거래)"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성에스디에스"), 0.85, "대규모기업집단계열회사(IT서비스거래)"),
        ],
    },

    # 특수관계자 채권·채무 — 삼성생명서비스손해사정, 태국법인, SRA, 삼성자산운용, 삼성액티브, 삼성헤지, 삼성카드
    "00768bc5b9dd6788": {  # 기재정정분기2024.03 별도주석 채권채무표 — 삼성생명서비스손해사정, 태국법인, 삼성SRA, 삼성자산운용, 삼성액티브, 삼성헤지, 삼성카드
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성생명서비스손해사정"), 0.93, "종속기업(채권채무)"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "Samsung Life Insurance (Thailand)"), 0.92, "종속기업(채권)"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성SRA자산운용"), 0.92, "종속기업(채권채무)"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성자산운용"), 0.93, "종속기업(채권채무)"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성액티브자산운용"), 0.88, "종속기업(채권채무)"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성헤지자산운용"), 0.85, "종속기업(채무)"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성카드"), 0.93, "종속기업(채권채무)"),
        ],
    },

    # 관계기업 거래 — 삼성증권, 삼성선물, 에이앤디신용정보, 신공항하이웨이, 코리아크레딧뷰로
    "02f399f954a46d94": {  # 기재정정분기2025.03 연결주석 관계기업 거래 — 삼성증권(임대/기타수익/지급수수료), 삼성선물, 에이앤디신용정보, 신공항하이웨이, 코리아크레딧뷰로
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성증권"), 0.92, "관계기업(거래)"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성선물"), 0.88, "관계기업(거래)"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "에이앤디신용정보"), 0.88, "관계기업(거래)"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "신공항하이웨이"), 0.85, "관계기업(거래)"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "코리아크레딧뷰로"), 0.85, "관계기업(거래)"),
        ],
    },

    # 자금대여·자금차입·현금출자 — 신공항하이웨이, 삼성벤처38호 등
    "00bb982ba10334e2": {  # 기재정정분기2024.09 연결주석 — 관계기업 자금대여/차입/출자 (신공항하이웨이, 삼성벤처38호)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "신공항하이웨이"), 0.85, "관계기업(자금대여)"),
        ],
    },
    "031ab69bb9adcb47": {  # 기재정정반기2024 별도주석 — 자금대여/차입/출자 (신공항하이웨이, 삼성벤처38호)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "신공항하이웨이"), 0.85, "관계기업(자금대여)"),
        ],
    },
    "02ec5809a9a42d7c": {  # 기재정정분기2024.03 별도주석 — 자금대여/차입/출자 (종속기업SRA, 관계기업)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성SRA자산운용"), 0.9, "종속기업(자금대여)"),
        ],
    },

    # 종속기업별 수익/비용 거래표 — 임대료수익, 배당금수익, 기타수익, 지급수수료
    "00082b21a8bb3702": {  # 분기2024.09 별도주석 — 종속기업 임대료수익, 배당금수익, 지급수수료
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성카드"), 0.92, "종속기업(거래)"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성자산운용"), 0.92, "종속기업(거래)"),
        ],
    },
    "015b10bc18dacf62": {  # 사업보고서2024 별도주석 — 종속기업 임대료수익22,652/배당금수익848,177/지급수수료383,844백만
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성카드"), 0.93, "종속기업(거래)"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성자산운용"), 0.93, "종속기업(거래)"),
        ],
    },

    # ══ II. 사업 — 삼성SRA자산운용 ══════════════════════════════

    "02827d33692189cc": {  # 삼성에스알에이자산운용 부동산전문운용사, AUM 20조원 (이미 위 병합)
        # 이 chunk_id는 위에서 이미 등록됨 (중복 허용, Python dict 마지막 것만 유효)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성생명서비스손해사정"), 0.92, "종속기업"),
            E("RELATED_PARTY", ("org", SAMSUNG_LIFE), ("org", "삼성SRA자산운용"), 0.93, "종속기업"),
        ],
    },
}

# 중복 chunk_id 제거 (Python dict 마지막 값 유효, 이미 내장됨)
# "0327e3c169774bb0"와 "02827d33692189cc"는 각각 한 번만 처리됨


def _match_and_id(driver, ref):
    if ref[0] == "org":
        org = resolve_org(ref[1])
        merge_org_node(driver, org)
        return {"kind": "org", "org": org}, org["id"]
    _, label, canonical, name = ref
    eid = merge_entity(driver, label, canonical, name)
    return {"kind": "entity", "label": label, "id": eid}, eid


def run():
    rows = get_chunks(
        f"WHERE corp_code='{CORP_CODE}' AND chunk_type='text_micro' "
        f"ORDER BY chunk_id LIMIT 2200 OFFSET 0"
    )
    by_id = {r["chunk_id"]: r for r in rows}
    print(f"[batch] 대상 청크 {len(rows)}건 (corp_code {CORP_CODE}, text_micro p1)")

    # table_nl 특수관계 청크 추가 (별도 쿼리)
    table_rows = get_chunks(
        f"WHERE corp_code='{CORP_CODE}' AND chunk_type='table_nl' "
        f"AND embedding_text LIKE '%특수관계%'"
    )
    for r in table_rows:
        by_id[r["chunk_id"]] = r
    print(f"[batch] table_nl 특수관계 추가 {len(table_rows)}건 → 총 {len(by_id)}건")

    done = ledger_processed_ids()
    print(f"[ledger] 기처리 {len(done)}건 (스킵 대상)")

    driver = neo4j_driver()
    conn = mariadb_conn()

    n_ent_total = n_edge_total = n_prov_total = 0
    edge_by_type: dict[str, int] = {}
    processed = skipped = 0

    # 1) 추출 결과가 있는 청크
    for cid, payload in EXTRACTIONS.items():
        if not payload:  # 빈 dict — 엔티티·엣지 없음
            if cid in by_id and cid not in done:
                row = by_id[cid]
                mark_processed(cid, 0, 0, row["rcept_no"], row["section_path"])
                processed += 1
            continue
        if cid not in by_id:
            print(f"  [warn] {cid} 대상 배치에 없음 — 스킵")
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
                     chunk_id=cid, rcept_no=row["rcept_no"], confidence=1.0)
            write_provenance(conn, cid, "hasObject", eid, cid, row["rcept_no"], 1.0)
            n_ent += 1
            n_prov_total += 1

        for e in payload.get("edges", []):
            rel, frm, to, conf = e["rel"], e["from"], e["to"], e["conf"]
            rtype = e.get("relation_type")
            fm, fid = _match_and_id(driver, frm)
            tm, tid = _match_and_id(driver, to)
            add_edge(driver, rel, fm, tm, chunk_id=cid, rcept_no=row["rcept_no"],
                     confidence=conf, relation_type=rtype)
            write_provenance(conn, fid, rel, tid, cid, row["rcept_no"], conf)
            n_edge += 1
            n_prov_total += 1
            edge_by_type[rel] = edge_by_type.get(rel, 0) + 1

        conn.commit()
        mark_processed(cid, n_ent, n_edge, row["rcept_no"], row["section_path"])
        n_ent_total += n_ent
        n_edge_total += n_edge
        processed += 1

    # 2) 나머지 대상 청크(text_micro p1)는 엣지 0개로 처리 표시 (누락 0 보장)
    extracted_ids = set(EXTRACTIONS.keys())
    for r in rows:  # text_micro rows만
        cid = r["chunk_id"]
        if cid in extracted_ids or cid in done:
            continue
        mark_processed(cid, 0, 0, r["rcept_no"], r["section_path"])
        processed += 1

    conn.close()
    driver.close()

    total_done = len(ledger_processed_ids())
    print("=== 삼성생명 p1 비정형 추출 결과 ===")
    print(f"  이번 실행 처리 청크: {processed}  (기처리 스킵 {skipped})")
    print(f"  원장 누적 처리 청크: {total_done} / {len(rows)} (text_micro)")
    print(f"  엔티티(Product/Tech) hasObject: {n_ent_total}")
    print(f"  엣지 총: {n_edge_total}  타입별: {edge_by_type}")
    print(f"  provenance 행: {n_prov_total}")


if __name__ == "__main__":
    run()
