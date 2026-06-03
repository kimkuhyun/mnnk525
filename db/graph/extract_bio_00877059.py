"""Stage 5 비정형 추출 — 삼성바이오로직스 corp_code=00877059,
text_micro 전체(~1,305건) + table_nl 특수관계(7건).

삼성바이오로직스 = 바이오 CDMO 기업 (CMO+CDO+바이오시밀러 개발·상업화(에피스)).
Product = CMO/CDO 서비스, 바이오시밀러 제품, mRNA/ADC/세포유전자 등 신규 모달리티.
Technology = S-CHOice®, S-DUAL™, DEVELOPICK™ 등 독자 플랫폼, GMP 품질 역량.
특수관계자 = 삼성에피스(종속), Samsung Biologics America(종속), 에임드바이오(관계),
               삼성물산(지배기업), 삼성전자(유의적영향력), 삼성웰스토리·삼성SDS 등(기타).

원장 = db/graph/ledger/extra28_00877059.jsonl (이 추출 전용).
실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_bio_00877059.py
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

CORP = "삼성바이오로직스"
CORP_CODE = "00877059"

# 전용 원장
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_DIR.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = LEDGER_DIR / "extra28_00877059.jsonl"

P = "Product"
T = "Technology"


def E(rel, frm, to, conf, relation_type=None):
    d = {"rel": rel, "from": frm, "to": to, "conf": conf}
    if relation_type:
        d["relation_type"] = relation_type
    return d


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


# ── Claude 추출 결과 (청크별, 본문 근거 있는 것만) ──────────────────────────
# 삼성바이오로직스 특성:
#   CDMO 부문(삼성바이오로직스 본체): CMO·CDO 서비스 → Product/Technology
#   바이오의약품 개발·상업화 부문(삼성바이오에피스): 바이오시밀러 → Product + SUPPLIES_TO 파트너
# 특수관계자: 삼성에피스홀딩스·Samsung Biologics America·에임드바이오(관계기업)
#              삼성물산(지배기업)·삼성전자(유의적영향력)·삼성웰스토리·삼성SDS(기타)

EXTRACTIONS: dict[str, dict] = {

    # ══ I. 사업개요 — CDMO 부문 설명 ══════════════════════════════════

    # 사업보고서(2023.12) — 사업개요: CDMO 2부문, 삼성바이오에피스 종속편입
    "20f6a69645a13bdc": {
        "entities": [
            (P, "cmo 위탁생산", "CMO(위탁생산) 서비스"),
            (P, "cdo 위탁개발", "CDO(위탁개발) 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmo 위탁생산", "CMO(위탁생산) 서비스"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "cdo 위탁개발", "CDO(위탁개발) 서비스"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성바이오에피스"), 0.97, "종속기업(바이오시밀러 개발·상업화 부문)"),
        ],
    },

    # 분기보고서(2024.03) — 사업개요: CMO+CDO, Samsung Biologics America 종속, Moderna mRNA 완제
    "4bd1fb03b767e1ab": {
        "entities": [
            (P, "cmo 위탁생산", "CMO(위탁생산) 서비스"),
            (P, "cdo 위탁개발", "CDO(위탁개발) 서비스"),
            (P, "mrna 백신 완제 위탁생산", "mRNA 백신 완제(DP) 위탁생산"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmo 위탁생산", "CMO(위탁생산) 서비스"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "cdo 위탁개발", "CDO(위탁개발) 서비스"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "mrna 백신 완제 위탁생산", "mRNA 백신 완제(DP) 위탁생산"), 0.88),
            E("RELATED_PARTY", ("org", CORP), ("org", "Samsung Biologics America"), 0.95, "종속기업(CDO 미국거점)"),
            E("SUPPLIES_TO", ("org", CORP), ("org", "Moderna"), 0.88),
        ],
    },

    # 반기보고서(2024.06) — 사업개요: CMO+CDO, Samsung Biologics America
    "35a1dc9f54fb68eb": {
        "entities": [
            (P, "cmo 위탁생산", "CMO(위탁생산) 서비스"),
            (P, "cdo 위탁개발", "CDO(위탁개발) 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmo 위탁생산", "CMO(위탁생산) 서비스"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "cdo 위탁개발", "CDO(위탁개발) 서비스"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "Samsung Biologics America"), 0.95, "종속기업(CDO 미국거점)"),
        ],
    },

    # 반기보고서(2025.06) — 사업개요: CDMO 부문(CMO+CDO), 78만 리터 생산설비
    "1256164d215db571": {
        "entities": [
            (P, "cmo 위탁생산", "CMO(위탁생산) 서비스"),
            (P, "cdo 위탁개발", "CDO(위탁개발) 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmo 위탁생산", "CMO(위탁생산) 서비스"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "cdo 위탁개발", "CDO(위탁개발) 서비스"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성바이오에피스"), 0.95, "종속기업(바이오시밀러 개발·상업화 부문)"),
        ],
    },

    # 반기보고서(2025.06) — CDO 서비스: S-CHOice®, S-Tensify™, DEVELOPICK™
    "12ae3b7d37db509c": {
        "entities": [
            (T, "s-choice 세포주", "S-CHOice®(자체 세포주 플랫폼)"),
            (T, "s-tensify 고농도제형", "S-Tensify™(고농도 제형 플랫폼)"),
            (T, "developick 항체선별", "DEVELOPICK™(항체 후보물질 선별 플랫폼)"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "s-choice 세포주", "S-CHOice®(자체 세포주 플랫폼)"), 0.92),
            E("USES_TECH", ("org", CORP), ("ent", T, "s-tensify 고농도제형", "S-Tensify™(고농도 제형 플랫폼)"), 0.90),
            E("USES_TECH", ("org", CORP), ("ent", T, "developick 항체선별", "DEVELOPICK™(항체 후보물질 선별 플랫폼)"), 0.88),
        ],
    },

    # ══ II. 사업의 내용 — CDO 플랫폼: S-CHOice, S-DUAL, DEVELOPICK ══════

    # 사업보고서(2024.12) — CDO: S-CHOice®, S-DUAL™ 이중항체 플랫폼
    "0270ce0fde886794": {
        "entities": [
            (T, "s-choice 세포주", "S-CHOice®(자체 세포주 플랫폼)"),
            (T, "s-dual 이중항체", "S-DUAL™(이중항체 플랫폼)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cdo 위탁개발", "CDO(위탁개발) 서비스"), 0.92),
            E("USES_TECH", ("org", CORP), ("ent", T, "s-choice 세포주", "S-CHOice®(자체 세포주 플랫폼)"), 0.92),
            E("USES_TECH", ("org", CORP), ("ent", T, "s-dual 이중항체", "S-DUAL™(이중항체 플랫폼)"), 0.90),
        ],
    },

    # 분기보고서(2024.09) — CDO 플랫폼: S-DUAL™, DEVELOPICK™, S-CHOsient™, S-Glyn™
    "170c87b2a5afa213": {
        "entities": [
            (T, "s-dual 이중항체", "S-DUAL™(이중항체 플랫폼)"),
            (T, "developick 항체선별", "DEVELOPICK™(항체 후보물질 선별 플랫폼)"),
            (T, "s-chosient 임시발현", "S-CHOsient™(임시발현 플랫폼)"),
            (T, "s-glyn 글리코실화분석", "S-Glyn™(글리코실화 분석 기반 물질 개발 플랫폼)"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "s-dual 이중항체", "S-DUAL™(이중항체 플랫폼)"), 0.92),
            E("USES_TECH", ("org", CORP), ("ent", T, "developick 항체선별", "DEVELOPICK™(항체 후보물질 선별 플랫폼)"), 0.90),
            E("USES_TECH", ("org", CORP), ("ent", T, "s-chosient 임시발현", "S-CHOsient™(임시발현 플랫폼)"), 0.88),
            E("USES_TECH", ("org", CORP), ("ent", T, "s-glyn 글리코실화분석", "S-Glyn™(글리코실화 분석 기반 물질 개발 플랫폼)"), 0.85),
        ],
    },

    # [기재정정]사업보고서(2024.12) — CDO 플랫폼: DEVELOPICK™, S-CHOsient™, S-Glyn™, S-Tensify™
    "1c6dd3153c162ee4": {
        "entities": [
            (T, "developick 항체선별", "DEVELOPICK™(항체 후보물질 선별 플랫폼)"),
            (T, "s-chosient 임시발현", "S-CHOsient™(임시발현 플랫폼)"),
            (T, "s-glyn 글리코실화분석", "S-Glyn™(글리코실화 분석 기반 물질 개발 플랫폼)"),
            (T, "s-tensify 고농도제형", "S-Tensify™(고농도 제형 플랫폼)"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "developick 항체선별", "DEVELOPICK™(항체 후보물질 선별 플랫폼)"), 0.90),
            E("USES_TECH", ("org", CORP), ("ent", T, "s-chosient 임시발현", "S-CHOsient™(임시발현 플랫폼)"), 0.88),
            E("USES_TECH", ("org", CORP), ("ent", T, "s-glyn 글리코실화분석", "S-Glyn™(글리코실화 분석 기반 물질 개발 플랫폼)"), 0.85),
            E("USES_TECH", ("org", CORP), ("ent", T, "s-tensify 고농도제형", "S-Tensify™(고농도 제형 플랫폼)"), 0.90),
        ],
    },

    # 분기보고서(2025.09) — 신규사업: CDO, mRNA, ADC, 세포/유전자 치료제 + S-CHOice®
    "14c5e82c0094e618": {
        "entities": [
            (P, "cmo 위탁생산", "CMO(위탁생산) 서비스"),
            (P, "cdo 위탁개발", "CDO(위탁개발) 서비스"),
            (P, "mrna 위탁생산", "mRNA 위탁생산 서비스"),
            (P, "adc 위탁생산", "ADC(항체약물접합체) 위탁생산 서비스"),
            (P, "세포유전자치료제 위탁생산", "세포/유전자 치료제 위탁생산 서비스"),
            (T, "s-choice 세포주", "S-CHOice®(자체 세포주 플랫폼)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmo 위탁생산", "CMO(위탁생산) 서비스"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "cdo 위탁개발", "CDO(위탁개발) 서비스"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "mrna 위탁생산", "mRNA 위탁생산 서비스"), 0.90),
            E("PRODUCES", ("org", CORP), ("ent", P, "adc 위탁생산", "ADC(항체약물접합체) 위탁생산 서비스"), 0.90),
            E("PRODUCES", ("org", CORP), ("ent", P, "세포유전자치료제 위탁생산", "세포/유전자 치료제 위탁생산 서비스"), 0.85),
            E("USES_TECH", ("org", CORP), ("ent", T, "s-choice 세포주", "S-CHOice®(자체 세포주 플랫폼)"), 0.92),
        ],
    },

    # 사업보고서(2025.12) — 신규사업: mRNA, ADC, 세포/유전자치료제 — ADC GMP Ready(2025 1Q)
    "0a4accb6b1da2e33": {
        "entities": [
            (P, "mrna 위탁생산", "mRNA 위탁생산 서비스"),
            (P, "adc 위탁생산", "ADC(항체약물접합체) 위탁생산 서비스"),
            (P, "세포유전자치료제 위탁생산", "세포/유전자 치료제 위탁생산 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "mrna 위탁생산", "mRNA 위탁생산 서비스"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "adc 위탁생산", "ADC(항체약물접합체) 위탁생산 서비스"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "세포유전자치료제 위탁생산", "세포/유전자 치료제 위탁생산 서비스"), 0.85),
        ],
    },

    # 분기보고서(2025.03) — 신규사업: CDO+mRNA+ADC+세포/유전자 + S-CHOice® CDO
    "164811d8dea7e416": {
        "entities": [
            (P, "cdo 위탁개발", "CDO(위탁개발) 서비스"),
            (P, "mrna 위탁생산", "mRNA 위탁생산 서비스"),
            (P, "adc 위탁생산", "ADC(항체약물접합체) 위탁생산 서비스"),
            (P, "세포유전자치료제 위탁생산", "세포/유전자 치료제 위탁생산 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cdo 위탁개발", "CDO(위탁개발) 서비스"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "mrna 위탁생산", "mRNA 위탁생산 서비스"), 0.88),
            E("PRODUCES", ("org", CORP), ("ent", P, "adc 위탁생산", "ADC(항체약물접합체) 위탁생산 서비스"), 0.88),
            E("PRODUCES", ("org", CORP), ("ent", P, "세포유전자치료제 위탁생산", "세포/유전자 치료제 위탁생산 서비스"), 0.82),
        ],
    },

    # 분기보고서(2024.03) — 신규사업: CDO+mRNA+ADC+세포/유전자치료제, 5공장 증설
    "1dfe3897903c916b": {
        "entities": [
            (P, "mrna 위탁생산", "mRNA 위탁생산 서비스"),
            (P, "adc 위탁생산", "ADC(항체약물접합체) 위탁생산 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmo 위탁생산", "CMO(위탁생산) 서비스"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "mrna 위탁생산", "mRNA 위탁생산 서비스"), 0.88),
            E("PRODUCES", ("org", CORP), ("ent", P, "adc 위탁생산", "ADC(항체약물접합체) 위탁생산 서비스"), 0.85),
        ],
    },

    # 사업보고서(2023.12) IV경영진단 — CDO 신규사업, S-CHOice™, S-DUAL™, DEVELOPICK™
    "13544d46118e9c9c": {
        "entities": [
            (T, "s-choice 세포주", "S-CHOice®(자체 세포주 플랫폼)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cdo 위탁개발", "CDO(위탁개발) 서비스"), 0.90),
            E("USES_TECH", ("org", CORP), ("ent", T, "s-choice 세포주", "S-CHOice®(자체 세포주 플랫폼)"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "mrna 위탁생산", "mRNA 위탁생산 서비스"), 0.85),
        ],
    },

    # ══ II. 사업의 내용 — 바이오의약품 개발·상업화 부문(삼성바이오에피스) ══

    # [기재정정]사업보고서(2024.12) — 에피스: 7종 바이오시밀러 판매(자가면역4·항암2·안과1), 파트너십
    "0d1a590dfe59e803": {
        "entities": [
            (P, "바이오시밀러", "바이오시밀러(Biosimilar)"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성바이오에피스"), 0.97, "종속기업(바이오시밀러 개발·상업화)"),
            E("PRODUCES", ("org", "삼성바이오에피스"), ("ent", P, "바이오시밀러", "바이오시밀러(Biosimilar)"), 0.95),
        ],
    },

    # 분기보고서(2025.09) — 에피스 연구개발: 파이프라인 현황(바이오시밀러 개발완료 목록)
    "1aefad67f37f6105": {
        "entities": [
            (P, "바이오시밀러", "바이오시밀러(Biosimilar)"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성바이오에피스"), 0.95, "종속기업(바이오시밀러 개발·상업화)"),
            E("PRODUCES", ("org", "삼성바이오에피스"), ("ent", P, "바이오시밀러", "바이오시밀러(Biosimilar)"), 0.93),
        ],
    },

    # 사업보고서(2023.12) — 에피스 산업특성: 바이오시밀러 개념 설명(오리지널 복제 의약품)
    "0da91d4dadcf653a": {
        "entities": [
            (P, "바이오시밀러", "바이오시밀러(Biosimilar)"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성바이오에피스"), 0.95, "종속기업(바이오시밀러)"),
            E("PRODUCES", ("org", "삼성바이오에피스"), ("ent", P, "바이오시밀러", "바이오시밀러(Biosimilar)"), 0.93),
        ],
    },

    # 사업보고서(2023.12) — 에피스 경쟁상황: 렘시마, 허쥬마, 허셉틴·아바스틴·휴미라 시밀러
    "042f261fc5f8beab": {
        "entities": [
            (P, "바이오시밀러", "바이오시밀러(Biosimilar)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "삼성바이오에피스"), ("ent", P, "바이오시밀러", "바이오시밀러(Biosimilar)"), 0.92),
        ],
    },

    # 사업보고서(2024.12) IV경영진단 — 에피스: Biogen, Organon, Sandoz 파트너십 글로벌 마케팅
    "39da030884d87afb": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성바이오에피스"), ("org", "Biogen"), 0.92, "글로벌 바이오시밀러 파트너(마케팅)"),
            E("RELATED_PARTY", ("org", "삼성바이오에피스"), ("org", "Organon"), 0.92, "글로벌 바이오시밀러 파트너(마케팅)"),
            E("RELATED_PARTY", ("org", "삼성바이오에피스"), ("org", "Sandoz"), 0.90, "글로벌 바이오시밀러 파트너(마케팅)"),
        ],
    },

    # 반기보고서(2024.06) — 에피스 판매방법: 파트너십 통해 판매(유럽/북미/아시아)
    "13bfc4494eadc5b8": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성바이오에피스"), 0.95, "종속기업(바이오시밀러 개발·상업화)"),
        ],
    },

    # ══ II. 사업의 내용 — 경쟁상황: Lonza, WuXi, Boehringer Ingelheim ══

    # 사업보고서(2024.12) — 경쟁상황: 30만L 규모 경쟁사(Lonza·WuXi·Boehringer)
    "35f67ceafbaf8bc9": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Lonza"), 0.85, "글로벌 CMO 경쟁사(스위스)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "WuXi Biologics"), 0.85, "글로벌 CMO 경쟁사(중국)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Boehringer Ingelheim"), 0.85, "글로벌 CMO 경쟁사(독일)"),
        ],
    },

    # [기재정정]사업보고서(2024.12) — 경쟁상황: Lonza·WuXi·Boehringer
    "4cde099b4addf008": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Lonza"), 0.85, "글로벌 CMO 경쟁사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "WuXi Biologics"), 0.85, "글로벌 CMO 경쟁사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Boehringer Ingelheim"), 0.85, "글로벌 CMO 경쟁사"),
        ],
    },

    # 반기보고서(2025.06) — 경쟁상황: Lonza·WuXi·Boehringer·FUJIFILM Diosynth
    "1f3f78a2bf3d3780": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Lonza"), 0.85, "글로벌 CMO 경쟁사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "WuXi Biologics"), 0.85, "글로벌 CMO 경쟁사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Boehringer Ingelheim"), 0.85, "글로벌 CMO 경쟁사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "FUJIFILM Diosynth Biotechnologies"), 0.82, "글로벌 CMO 경쟁사(일본)"),
        ],
    },

    # 분기보고서(2024.09) — 경쟁상황: Boehringer Ingelheim·FUJIFILM Diosynth 공격적 증설
    "1e89f56f8bb45a8b": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Boehringer Ingelheim"), 0.85, "글로벌 CMO 경쟁사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "FUJIFILM Diosynth Biotechnologies"), 0.82, "글로벌 CMO 경쟁사"),
        ],
    },

    # 사업보고서(2025.12) — 경쟁상황: FUJIFILM Biotechnologies 언급
    "1be5218a51df6615": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "FUJIFILM Diosynth Biotechnologies"), 0.82, "글로벌 CMO 경쟁사"),
        ],
    },

    # 분기보고서(2026.03) — 경쟁상황: 경쟁사 포함, Samsung Biologics America 미국거점 확보
    "13362f2f60237845": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Samsung Biologics America"), 0.95, "종속기업(미국 CDMO 거점)"),
        ],
    },

    # ══ II. 사업의 내용 — GMP/품질관리 경쟁력 ══════════════════════

    # 사업보고서(2023.12) — 경쟁력: GMP 준수, 품질관리 역량, 잠재고객 신뢰도
    "042f261fc5f8beab": {  # 중복 chunk_id — 마지막 dict 값이 유효
        "entities": [
            (T, "gmp 품질관리", "GMP(Good Manufacturing Practice) 품질관리"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "gmp 품질관리", "GMP(Good Manufacturing Practice) 품질관리"), 0.92),
        ],
    },

    # [기재정정]사업보고서(2024.12) — 경쟁력: Track Record 관리, 품질관리 역량
    "0d1a590dfe59e803": {  # 중복 chunk_id (다른 내용) - 이 항목은 위에서 이미 정의됨
        # 바이오에피스 7종 바이오시밀러 판매 내용을 위에서 처리했으므로 여기는 스킵
        "entities": [],
        "edges": [],
    },

    # ══ II. 사업의 내용 — Biogen 지분 취득(파생상품) ══════════════

    # 반기보고서(2024.06) — Biogen Therapeutics Inc. 지분 취득 계약(에피스 주식 매매)
    "00dbb39c6dc343bf": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Biogen"), 0.90, "전 주주(삼성바이오에피스 지분 매각)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성바이오에피스"), 0.97, "종속기업(지분 100% 취득)"),
        ],
    },

    # ══ II. 사업의 내용 — 판매방법: CMO 수주산업, 품질승인 후 매출인식 ══

    # 반기보고서(2024.06) — CMO 판매방법: 수주계약, 품질승인(QR) 시점 매출인식
    "14aab4f7ae9085fc": {
        "entities": [
            (P, "cmo 위탁생산", "CMO(위탁생산) 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmo 위탁생산", "CMO(위탁생산) 서비스"), 0.95),
        ],
    },

    # ══ II. 사업의 내용 — 인텔리전스/IP: 바이오의약품 제조기술 특허 ══

    # 사업보고서(2023.12) — CDMO 지식재산권: 바이오의약품 제조기술·공정·설비 특허
    "04c90224de2cadfd": {
        "entities": [
            (T, "gmp 품질관리", "GMP(Good Manufacturing Practice) 품질관리"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "gmp 품질관리", "GMP(Good Manufacturing Practice) 품질관리"), 0.88),
        ],
    },

    # 반기보고서(2024.06) — CDMO IP: 바이오의약품 제조기술/설비 관련 특허 2건 등록
    "101afadc446b235d": {
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmo 위탁생산", "CMO(위탁생산) 서비스"), 0.90),
        ],
    },

    # [기재정정]사업보고서(2024.12) — CDMO IP: 제조기술/설비 특허
    "0b756a769b1eba73": {
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmo 위탁생산", "CMO(위탁생산) 서비스"), 0.90),
        ],
    },

    # ══ II. 사업의 내용 — 산업 특성: CDMO 바이오의약품 위탁개발·생산 ══

    # 사업보고서(2023.12) — CDMO 산업: 항체의약품 CMO, 대규모 투자 필요성
    "16d644c6f31a66f1": {
        "entities": [
            (P, "cmo 위탁생산", "CMO(위탁생산) 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmo 위탁생산", "CMO(위탁생산) 서비스"), 0.95),
        ],
    },

    # 분기보고서(2024.09) — CDMO 산업: 바이오 CDMO 위탁개발·생산사업
    "11da32d5111aae64": {
        "entities": [
            (P, "cmo 위탁생산", "CMO(위탁생산) 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmo 위탁생산", "CMO(위탁생산) 서비스"), 0.95),
        ],
    },

    # 분기보고서(2025.03) — CDMO 산업: 바이오 CDMO 위탁개발·생산사업
    "0066f036ee23dae2": {
        "entities": [
            (P, "cmo 위탁생산", "CMO(위탁생산) 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "cmo 위탁생산", "CMO(위탁생산) 서비스"), 0.95),
        ],
    },

    # ══ II. 사업의 내용 — 에피스 인적분할: 삼성에피스홀딩스 설립(2025.11) ══

    # [기재정정]사업보고서(2025.12) — 에피스홀딩스 인적분할: CDMO 사업 집중, 삼성에피스홀딩스 설립
    "1a8fb19db5fc8aee": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에피스홀딩스"), 0.95, "분할설립(삼성바이오에피스 지분 100% 승계)"),
            E("RELATED_PARTY", ("org", "삼성에피스홀딩스"), ("org", "삼성바이오에피스"), 0.97, "종속기업(지분 100%)"),
        ],
    },

    # 사업보고서(2025.12) — 에피스홀딩스 인적분할 완료, CDMO 집중
    "600ef502167535ad": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에피스홀딩스"), 0.95, "분할설립(삼성바이오에피스 지분 100% 승계)"),
        ],
    },

    # 분기보고서(2026.03) — 사업개요: 삼성에피스홀딩스 설립 후 순수 CDMO 집중
    "6558afebb6719852": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에피스홀딩스"), 0.95, "분할설립(CDMO 분리)"),
        ],
    },

    # ══ IX. 계열회사 — 삼성그룹 계열사 현황 ══════════════════════════

    # [기재정정]사업보고서(2025.12) IX — 삼성그룹 67개 계열사 (+삼성에피스홀딩스·에피스넥스랩 신규)
    "0a7bf934027ef626": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에피스홀딩스"), 0.95, "계열사신규편입(분할설립)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에피스넥스랩"), 0.90, "계열사신규편입"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.92, "지배기업(삼성그룹 계열)"),
        ],
    },

    # 사업보고서(2025.12) IX — 삼성그룹 67개 계열사, 삼성에피스홀딩스 편입
    "2314059166a04d9c": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.92, "지배기업(삼성그룹)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에피스홀딩스"), 0.95, "계열사신규편입"),
        ],
    },

    # ══ XI. 기타 — Samsung Biologics America(HGS 지분 취득), GlaxoSmithKline ══

    # 분기보고서(2026.03) XI — Samsung Biologics America: HGS(Human Genome Sciences) 지분 인수, GlaxoSmithKline
    "230436e7fe1e6008": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Samsung Biologics America"), 0.95, "종속기업(미국 생산거점)"),
            E("RELATED_PARTY", ("org", "Samsung Biologics America"), ("org", "Human Genome Sciences"), 0.90, "지분인수(GlaxoSmithKline 보유 주식 800주)"),
            E("RELATED_PARTY", ("org", "Samsung Biologics America"), ("org", "GlaxoSmithKline"), 0.88, "지분 매도인"),
        ],
    },

    # [기재정정]사업보고서(2025.12) XI — HGS 지분 인수 계약(2025.12월 결의, 2026 1Q 완료)
    "4730afb977873b36": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Samsung Biologics America"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", "Samsung Biologics America"), ("org", "Human Genome Sciences"), 0.90, "지분인수(미국 생산거점)"),
        ],
    },

    # ══ table_nl 특수관계자 채권·채무 표 ══════════════════════════════

    # 사업보고서(2023.12) 연결감사보고서 — 채권채무 표: 삼성물산·삼성전자·에임드바이오·삼성웰스토리
    "6b1bf33cd803715c": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.95, "지배기업(채무 잔액)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.92, "유의적 영향력 보유 기업(채무 잔액)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에임드바이오"), 0.88, "관계기업(채권채무 잔액)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성웰스토리"), 0.88, "기타 특수관계자"),
        ],
    },

    # 사업보고서(2023.12) 재무제표 주석 — 특수관계자 현황: Samsung Biologics America·에피스(종속), 에임드바이오(관계)
    "96da280970cb95a3": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.97, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.93, "유의적 영향력 보유 기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성바이오에피스"), 0.97, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Samsung Biologics America"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에임드바이오"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성웰스토리"), 0.88, "기타 특수관계자"),
        ],
    },

    # 사업보고서(2023.12) 연결재무제표 주석 — 특수관계자 현황: 삼성물산(지배), 삼성전자, 에임드바이오(관계), 삼성엔지니어링·삼성SDS·삼성화재·삼성생명(대규모기업집단)
    "f136aa1f30f0d741": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.97, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.93, "유의적 영향력 보유 기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에임드바이오"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성웰스토리"), 0.88, "기타 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에스디에스"), 0.85, "대규모기업집단(IT서비스)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성엔지니어링"), 0.85, "대규모기업집단"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재해상보험"), 0.82, "대규모기업집단"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.82, "대규모기업집단"),
        ],
    },

    # 사업보고서(2023.12) 연결감사보고서 — 전기 채권채무: 삼성물산·삼성전자·삼성웰스토리
    "ef478a8fe96b2fd3": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.95, "지배기업(전기 채무)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.92, "유의적 영향력(전기 채무)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성웰스토리"), 0.88, "기타 특수관계자"),
        ],
    },

    # 사업보고서(2023.12) 연결감사보고서 — 전기 채권채무: 삼성SDS America·Samsung Hospitality America
    "0f2466dc485d62c2": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에스디에스"), 0.85, "대규모기업집단(IT서비스, 전기 채무)"),
        ],
    },

    # 사업보고서(2023.12) 연결감사보고서 — 전전기 채권채무: SDS America
    "238bad8aa78948d1": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에스디에스"), 0.83, "대규모기업집단(IT서비스)"),
        ],
    },

    # 사업보고서(2024.12) 연결감사보고서 — 채권채무: 삼성물산·삼성전자·에임드바이오·삼성웰스토리·Samsung Electronics America
    "3232a83fbc93c746": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.97, "지배기업(채무 잔액)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.93, "유의적 영향력 보유(채무 잔액)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에임드바이오"), 0.90, "관계기업(채권채무 잔액)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성웰스토리"), 0.88, "기타 특수관계자(채무)"),
        ],
    },

    # ══ 사업보고서(2024.12)/분기보고서(2025.09) — 에임드바이오·BrickBio 관계기업 ══

    # 분기보고서(2025.09) — 에임드바이오·BrickBio 관계기업 유의적영향력
    "2bc2680a3cd20645": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "에임드바이오"), 0.90, "관계기업(유의적 영향력)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "BrickBio"), 0.85, "관계기업(유의적 영향력)"),
        ],
    },

    # 사업보고서(2023.12) — 종속기업: 삼성바이오에피스·Samsung Biologics America, 관계기업: SVIC 54호·에임드바이오
    "2205474d59da5314": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성바이오에피스"), 0.97, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Samsung Biologics America"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에임드바이오"), 0.90, "관계기업"),
        ],
    },

    # ══ 사업보고서(2025.12)/분기보고서(2026.03) — 인적분할 후 특수관계 갱신 ══

    # 사업보고서(2025.12) 감사보고서 — 인적분할: 삼성에피스홀딩스 신설, 에피스 지분 이전
    "7658ac0edc691a21": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에피스홀딩스"), 0.97, "분할설립(에피스 지분 100% 이전)"),
        ],
    },

    # 사업보고서(2025.12) 연결감사보고서 — Biogen 지분 취득 최종: 총 USD 23억(조건부대가 포함), 삼성에피스홀딩스로 의무 이관
    "151d763769c2b86a": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Biogen"), 0.88, "전 주주(에피스 지분 USD 23억에 취득)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에피스홀딩스"), 0.95, "분할설립(지급 의무 이관)"),
        ],
    },

    # [기재정정]사업보고서(2025.12) XI — 삼성에피스홀딩스 분할 신설: 에피스·에피스넥스랩 자회사 포함
    "2a804c610112bb04": {
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에피스홀딩스"), 0.97, "분할설립(에피스 자회사 포함)"),
            E("RELATED_PARTY", ("org", "삼성에피스홀딩스"), ("org", "삼성바이오에피스"), 0.97, "종속기업(지분 100%)"),
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
    processed = skipped = 0

    # 1) 추출 결과가 있는 청크
    for cid, payload in EXTRACTIONS.items():
        if not payload:
            if cid in by_id and cid not in done:
                row = by_id[cid]
                mark_processed(cid, 0, 0, row["rcept_no"], row["section_path"])
                processed += 1
            continue
        if cid not in by_id:
            print(f"  [warn] {cid} 대상에 없음 — 스킵")
            continue
        if cid in done:
            skipped += 1
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
    print("=== 삼성바이오로직스 Stage5 추출 결과 ===")
    print(f"  이번 처리 청크: {processed}  (기처리 스킵 {skipped}, 원장 누적 {total_marked} / 대상 {len(all_rows)})")
    print(f"  엔티티(Product/Tech) hasObject: {n_ent_total}")
    print(f"  엣지 총: {n_edge_total}  타입별: {edge_by_type}")
    print(f"  provenance 행: {n_prov_total}")


if __name__ == "__main__":
    run()
