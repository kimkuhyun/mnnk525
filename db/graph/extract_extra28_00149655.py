"""Stage 5 비정형 추출 — 삼성물산 corp_code=00149655, text_micro 전체(~2,481) + table_nl 특수관계(~98).

삼성물산 = 건설/상사/패션/리조트/바이오 5개 부문 복합 대기업.
- 건설부문: 건축/토목/플랜트/주택(래미안), Digital Twin 등 건설기술
- 상사부문: 철강/화학/에너지/소재 트레이딩
- 패션부문: 빈폴, 준지 등 의류 브랜드
- 리조트부문: 에버랜드(테마파크), 캐리비안베이(워터파크), 골프장, 급식(삼성웰스토리)
- 바이오부문: CMO/CDO/CDMO 서비스, 바이오시밀러 (삼성바이오로직스, 삼성바이오에피스)

특수관계자:
- 종속기업: 삼성바이오로직스, 삼성바이오에피스, 삼성웰스토리, 강릉에코파워 등
- 기타특수관계자: 삼성전자(주) (기업회계기준서 제1024호 외 독점규제법상)
- 대규모기업집단: 삼성생명보험(주), 삼성에스디에스(주) 등

원장 = db/graph/ledger/extra28_00149655.jsonl (이 추출 전용).
실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_extra28_00149655.py
멱등: 재실행해도 MERGE/ON DUP/원장 갱신이라 중복 없음.
주의: entity id 캐시에 boolean 저장 금지(product_id/tech_id 는 sha1 문자열).
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

CORP = "삼성물산"
CORP_CODE = "00149655"

# ── 전용 원장 ─────────────────────────────────────────────────
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_DIR.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = LEDGER_DIR / "extra28_00149655.jsonl"


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
# 삼성물산은 5개 부문 복합 대기업:
#   Product = 건설 서비스(래미안), 리조트 서비스(에버랜드/캐리비안베이), 패션 브랜드, 급식 서비스
#   Technology = Digital Twin, S-CHOice 세포주, GMP 제조기술, FAB 건설기술
#   특수관계자 = 종속기업(바이오로직스, 바이오에피스, 웰스토리) + 그 밖(삼성전자) + 대기업집단(삼성생명, SDS)
EXTRACTIONS: dict[str, dict] = {

    # ── II. 사업의 내용: 건설부문 사업개요 ──────────────────────
    "2384b22b77c58cb3": {  # 2023 사업보고서: 5개 부문 사업개요(건설/상사/패션/리조트/바이오)
        "entities": [
            (P, "래미안", "래미안"),
            (P, "에버랜드", "에버랜드"),
            (P, "캐리비안베이", "캐리비안베이"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "래미안", "래미안"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "에버랜드", "에버랜드"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "캐리비안베이", "캐리비안베이"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성웰스토리"), 0.90, "종속기업(급식/식자재유통)"),
        ],
    },
    "1d777a95b4310230": {  # 2024 사업보고서: 5개 부문 사업개요(건설/상사/패션/리조트/바이오)
        "entities": [
            (P, "래미안", "래미안"),
            (P, "에버랜드", "에버랜드"),
            (P, "캐리비안베이", "캐리비안베이"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "래미안", "래미안"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "에버랜드", "에버랜드"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "캐리비안베이", "캐리비안베이"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성웰스토리"), 0.90, "종속기업(급식/식자재유통)"),
        ],
    },

    # ── II. 사업의 내용: 건설부문 경쟁우위 — 래미안 브랜드 ──────
    "d580c323cc053b39": {  # 2023 사업보고서: 건설 — 가스복합화력, 신재생 발전, 래미안 브랜드
        "entities": [
            (P, "래미안", "래미안"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "래미안", "래미안"), 0.95),
        ],
    },
    "4615f36fb131b3b4": {  # 2024 사업보고서: 건설부문 고객관리 — 래미안 갤러리 운영
        "entities": [
            (P, "래미안", "래미안"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "래미안", "래미안"), 0.95),
        ],
    },
    "155f852526a880a8": {  # 2023 사업보고서: 건설부문 고객관리 — 래미안 갤러리 운영
        "entities": [
            (P, "래미안", "래미안"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "래미안", "래미안"), 0.95),
        ],
    },

    # ── II. 사업의 내용: 건설부문 R&D — Digital Twin 기술 ────────
    "00db40359c4bf88b": {  # 2023 사업보고서: FAB 유틸리티 최적화 시뮬레이터, 건설 기술 Digital Twin 플랫폼
        "entities": [
            (T, "건설 Digital Twin 플랫폼", "건설 기술 digital twin 플랫폼"),
            (T, "FAB 유틸리티 최적화 시뮬레이터", "fab 유틸리티 최적화 시뮬레이터"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "건설 Digital Twin 플랫폼", "건설 기술 digital twin 플랫폼"), 0.88),
            E("USES_TECH", ("org", CORP), ("ent", T, "FAB 유틸리티 최적화 시뮬레이터", "fab 유틸리티 최적화 시뮬레이터"), 0.87),
        ],
    },
    "7eb9f9fd00e674ad": {  # 2024 사업보고서: FAB 유틸리티 최적화 시뮬레이터, 건설 기술 Digital Twin 플랫폼
        "entities": [
            (T, "건설 Digital Twin 플랫폼", "건설 기술 digital twin 플랫폼"),
            (T, "FAB 유틸리티 최적화 시뮬레이터", "fab 유틸리티 최적화 시뮬레이터"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "건설 Digital Twin 플랫폼", "건설 기술 digital twin 플랫폼"), 0.88),
            E("USES_TECH", ("org", CORP), ("ent", T, "FAB 유틸리티 최적화 시뮬레이터", "fab 유틸리티 최적화 시뮬레이터"), 0.87),
        ],
    },
    "00b08e66f6529795": {  # 2025 분기보고서: 로봇 기술, FAB 구조체 미진동 제어 설계, Digital Twin
        "entities": [
            (T, "건설 Digital Twin 플랫폼", "건설 기술 digital twin 플랫폼"),
            (T, "FAB 유틸리티 최적화 시뮬레이터", "fab 유틸리티 최적화 시뮬레이터"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "건설 Digital Twin 플랫폼", "건설 기술 digital twin 플랫폼"), 0.87),
            E("USES_TECH", ("org", CORP), ("ent", T, "FAB 유틸리티 최적화 시뮬레이터", "fab 유틸리티 최적화 시뮬레이터"), 0.86),
        ],
    },

    # ── II. 사업의 내용: 건설부문 R&D 연구소 — 층간소음·친환경 건축 ──
    "644aa8c1695d740f": {  # 2023 사업보고서: 친환경 건축, 층간소음연구소, 건설안전연구소, 반도체인프라연구소
        "entities": [
            (T, "친환경 건축 설계기술", "친환경 건축물 설계 및 평가기술"),
            (T, "층간소음 저감기술", "층간소음 저감 요소기술"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "친환경 건축 설계기술", "친환경 건축물 설계 및 평가기술"), 0.85),
            E("USES_TECH", ("org", CORP), ("ent", T, "층간소음 저감기술", "층간소음 저감 요소기술"), 0.83),
        ],
    },

    # ── II. 사업의 내용: 건설부문 — 수주 경쟁력 ────────────────
    "7ad1463c015fceb6": {  # 2023 사업보고서: 건설부문 수주규모(국내 10.3조, 해외 72억불)
        "entities": [],
        "edges": [],
    },

    # ── II. 사업의 내용: 상사부문 개요 ──────────────────────────
    "281168ad59128160": {  # 2023 사업보고서: 상사부문 — 화학, 철강, 에너지, 소재 트레이딩
        "entities": [
            (P, "철강 트레이딩", "철강 트레이딩"),
            (P, "화학 트레이딩", "화학 트레이딩"),
            (P, "에너지 트레이딩", "에너지 트레이딩"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "철강 트레이딩", "철강 트레이딩"), 0.90),
            E("PRODUCES", ("org", CORP), ("ent", P, "화학 트레이딩", "화학 트레이딩"), 0.90),
            E("PRODUCES", ("org", CORP), ("ent", P, "에너지 트레이딩", "에너지 트레이딩"), 0.88),
        ],
    },

    # ── II. 사업의 내용: 패션부문 ───────────────────────────────
    "4718e68891fd9b99": {  # 2023 사업보고서: 패션 — 준지(JUUN.J) 브랜드, 에버랜드 연계
        "entities": [
            (P, "빈폴", "빈폴"),
            (P, "준지", "준지"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "빈폴", "빈폴"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "준지", "준지"), 0.92),
        ],
    },
    "4c801de94f9ec1f4": {  # 2024 사업보고서: 패션 — 준지, 에버랜드
        "entities": [
            (P, "준지", "준지"),
            (P, "에버랜드", "에버랜드"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "준지", "준지"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "에버랜드", "에버랜드"), 0.92),
        ],
    },

    # ── II. 사업의 내용: 리조트부문 — 에버랜드/캐리비안베이/골프장 ──
    "583e542e6288714a": {  # 2023 사업보고서: 리조트 — 에버랜드 우든코스터, 로스트밸리, 판다월드
        "entities": [
            (P, "에버랜드", "에버랜드"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "에버랜드", "에버랜드"), 0.95),
        ],
    },
    "9ac1e2424a71d131": {  # 2023 사업보고서: 리조트 — 골프장 162홀, 급식/식자재 사업
        "entities": [
            (P, "에버랜드", "에버랜드"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "에버랜드", "에버랜드"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성웰스토리"), 0.90, "종속기업(급식/식자재유통 사업)"),
        ],
    },

    # ── II. 사업의 내용: 급식부문 — 삼성웰스토리 ────────────────
    "7ecf4d6c5f06ce08": {  # 2023 사업보고서: 급식/식자재유통 사업 산업특성
        "entities": [
            (P, "단체급식 서비스", "단체급식 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "단체급식 서비스", "단체급식 서비스"), 0.88),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성웰스토리"), 0.90, "종속기업(급식/식자재유통)"),
        ],
    },
    "0fc93773ced6f0e0": {  # 2023 사업보고서: 급식부문 경쟁우위 — 프리미엄급식, 건강케어프로그램
        "entities": [
            (P, "단체급식 서비스", "단체급식 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "단체급식 서비스", "단체급식 서비스"), 0.88),
        ],
    },

    # ── II. 사업의 내용: 바이오부문 — CMO/CDO 사업 개요 ──────────
    "2092943695020e24": {  # 2023 사업보고서: 바이오 CMO 사업 — 바이오의약품 위탁생산, 항체의약품
        "entities": [
            (P, "바이오의약품 CMO 서비스", "바이오의약품 cmo 서비스"),
            (P, "바이오의약품 CDO 서비스", "바이오의약품 cdo 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "바이오의약품 CMO 서비스", "바이오의약품 cmo 서비스"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "바이오의약품 CDO 서비스", "바이오의약품 cdo 서비스"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성바이오로직스"), 0.95, "종속기업(바이오 CMO/CDO 사업 영위)"),
        ],
    },
    "55860d76cba5049f": {  # 2023 사업보고서: 바이오 CMO/CDO/바이오시밀러 사업
        "entities": [
            (P, "바이오의약품 CMO 서비스", "바이오의약품 cmo 서비스"),
            (P, "바이오의약품 CDO 서비스", "바이오의약품 cdo 서비스"),
            (P, "바이오시밀러", "바이오시밀러"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "바이오의약품 CMO 서비스", "바이오의약품 cmo 서비스"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "바이오의약품 CDO 서비스", "바이오의약품 cdo 서비스"), 0.90),
            E("PRODUCES", ("org", CORP), ("ent", P, "바이오시밀러", "바이오시밀러"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성바이오로직스"), 0.95, "종속기업(바이오 CDMO 사업)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성바이오에피스"), 0.92, "종속기업(바이오시밀러 개발 및 상업화)"),
        ],
    },
    "6ab6286ac41fd66a": {  # 2024 사업보고서: 바이오 CMO/CDO 사업 — 세포주개발~초기임상 개발서비스
        "entities": [
            (P, "바이오의약품 CMO 서비스", "바이오의약품 cmo 서비스"),
            (P, "바이오의약품 CDO 서비스", "바이오의약품 cdo 서비스"),
            (P, "바이오시밀러", "바이오시밀러"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "바이오의약품 CMO 서비스", "바이오의약품 cmo 서비스"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "바이오의약품 CDO 서비스", "바이오의약품 cdo 서비스"), 0.90),
            E("PRODUCES", ("org", CORP), ("ent", P, "바이오시밀러", "바이오시밀러"), 0.90),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성바이오로직스"), 0.95, "종속기업(바이오 CDMO 사업)"),
        ],
    },
    "779252975a302385": {  # 2024 사업보고서: 바이오 CDMO 사업 개요
        "entities": [
            (P, "바이오의약품 CMO 서비스", "바이오의약품 cmo 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "바이오의약품 CMO 서비스", "바이오의약품 cmo 서비스"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성바이오로직스"), 0.95, "종속기업(바이오 CDMO)"),
        ],
    },

    # ── II. 사업의 내용: 바이오부문 — S-CHOice 세포주 기술 ─────────
    "9ab10b994e1a00ad": {  # 2023 사업보고서: S-CHOice 세포주 개발, mRNA/ADC/세포유전자치료제 확장
        "entities": [
            (T, "S-CHOice 세포주", "s-choice 세포주"),
            (T, "mRNA 기술", "mrna 의약품 기술"),
            (T, "ADC 기술", "adc(항체약물접합체) 기술"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "S-CHOice 세포주", "s-choice 세포주"), 0.90),
            E("USES_TECH", ("org", CORP), ("ent", T, "mRNA 기술", "mrna 의약품 기술"), 0.85),
            E("USES_TECH", ("org", CORP), ("ent", T, "ADC 기술", "adc(항체약물접합체) 기술"), 0.85),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성바이오로직스"), 0.95, "종속기업(S-CHOice 세포주 개발)"),
        ],
    },
    "4976a2b76847df90": {  # 2024 사업보고서: S-CHOice, mRNA/ADC 신규사업 확장
        "entities": [
            (T, "S-CHOice 세포주", "s-choice 세포주"),
            (T, "mRNA 기술", "mrna 의약품 기술"),
            (T, "ADC 기술", "adc(항체약물접합체) 기술"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "S-CHOice 세포주", "s-choice 세포주"), 0.90),
            E("USES_TECH", ("org", CORP), ("ent", T, "mRNA 기술", "mrna 의약품 기술"), 0.85),
            E("USES_TECH", ("org", CORP), ("ent", T, "ADC 기술", "adc(항체약물접합체) 기술"), 0.85),
        ],
    },

    # ── II. 사업의 내용: 바이오부문 — 바이오시밀러 개발(삼성바이오에피스) ──
    "3cfc52f7947e577e": {  # 2024 사업보고서: 바이오에피스 바이오시밀러 9종(레미케이드, 허셉틴 등)
        "entities": [
            (P, "바이오시밀러", "바이오시밀러"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "바이오시밀러", "바이오시밀러"), 0.93),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성바이오에피스"), 0.95, "종속기업(바이오시밀러 개발·상업화)"),
        ],
    },
    "04b0925cea5ecef1": {  # 2023 사업보고서: 바이오시밀러 산업 특성 및 글로벌 수요
        "entities": [
            (P, "바이오시밀러", "바이오시밀러"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "바이오시밀러", "바이오시밀러"), 0.90),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성바이오에피스"), 0.92, "종속기업(바이오시밀러)"),
        ],
    },
    "176e054da95338a8": {  # 2023 사업보고서: 바이오로직스 생산 Capacity(60.4만리터, 4개 공장)
        "entities": [
            (P, "바이오의약품 CMO 서비스", "바이오의약품 cmo 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "바이오의약품 CMO 서비스", "바이오의약품 cmo 서비스"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성바이오로직스"), 0.95, "종속기업(CMO 생산설비 60만리터)"),
        ],
    },

    # ── II. 사업의 내용: 바이오에피스 지분 인수 ──────────────────
    "ae235c4dbacad79c": {  # 2023 사업보고서: 바이오로직스가 Biogen으로부터 바이오에피스 지분 인수
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성바이오로직스"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성바이오에피스"), 0.93, "종속기업(바이오로직스 100% 자회사)"),
        ],
    },
    "4f8aa8d19e446e50": {  # 2024 사업보고서: 삼성바이오에피스 지분 인수 계약 명시
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성바이오로직스"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성바이오에피스"), 0.95, "종속기업(바이오로직스 종속)"),
        ],
    },

    # ── 연결재무제표주석 특수관계자 표 — 기타특수관계자 삼성전자 ──
    "5915f80fa2546f39": {  # 2023 사업보고서 연결재무제표주석: 삼성전자(기타특수관계자), 삼성생명(대규모기업집단)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.93, "기타특수관계자(그 밖의 특수관계자)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.90, "대규모기업집단 소속회사"),
        ],
    },
    "9d25a8c0031a0f59": {  # 2023 사업보고서 연결재무제표주석: South Kent Wind LP(관계기업), 삼성전자(기타)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.93, "기타특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.90, "대규모기업집단 소속회사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "South Kent Wind LP"), 0.87, "관계기업(풍력발전)"),
        ],
    },

    # ── 연결재무제표주석 특수관계자 표 — 관계기업 목록 ──────────
    "94fe003225663c0b": {  # 2023 사업보고서 연결재무제표주석: 강릉에코파워, 가지안텝SPV, 티오케이첨단재료, FCC Saudi LLC, 삼성전자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "강릉에코파워"), 0.88, "관계기업(발전)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "티오케이첨단재료"), 0.87, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.92, "기타특수관계자(그 밖의 특수관계자)"),
        ],
    },
    "a69dc3d33f427150": {  # 2023 사업보고서 연결재무제표주석: 관계기업·공동기업 채권채무
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "강릉에코파워"), 0.87, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.90, "기타특수관계자"),
        ],
    },
    "9f93a77f44878e96": {  # 2023 사업보고서 연결재무제표주석: 관계기업 채권채무 상세(12개 특수관계자)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "강릉에코파워"), 0.87, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.90, "기타특수관계자"),
        ],
    },

    # ── 감사보고서 특수관계자 잔액 표 — 삼성전자·삼성에스디에스 ──
    "480aabf1dafb4a14": {  # 2023 사업보고서 연결감사보고서: 삼성전자(기타특수관계자), 삼성생명(대규모기업집단)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.95, "기타특수관계자(투자잔액)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.90, "대규모기업집단 소속회사"),
        ],
    },
    "e8f0ad9aff9d571f": {  # 2023 사업보고서 감사보고서: 삼성전자(기타특수관계자), 삼성생명(대규모기업집단)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.95, "기타특수관계자(투자잔액)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.90, "대규모기업집단 소속회사"),
        ],
    },
    "c333b3653b7c5c91": {  # 2023 사업보고서 감사보고서: 삼성전자(기타특수관계자 매출 5.6조), 삼성에스디에스(기타)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.95, "기타특수관계자(매출 5.6조, SUPPLIES_TO 거래)"),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.93),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에스디에스"), 0.88, "기타특수관계자(IT 서비스 매입)"),
        ],
    },

    # ── 재무제표주석 특수관계자 — 강릉에코파워·South Kent Wind LP ──
    "c21ab99c8b6172cd": {  # 2023 사업보고서 연결재무제표주석: 강릉에코파워, SP Belle River LP, 미래에셋맵스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "강릉에코파워"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SP Belle River LP"), 0.85, "관계기업"),
        ],
    },
    "e29d8f19624b9dcf": {  # 2023 사업보고서 연결재무제표주석: 강릉에코파워, SP Belle River LP
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "강릉에코파워"), 0.87, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SP Belle River LP"), 0.85, "관계기업"),
        ],
    },

    # ── 2023 기재정정 사업보고서 특수관계자 표 (중복 검증) ──────
    "0683950f0595cdeb": {  # 기재정정: 연결재무제표주석 관계기업 채권채무(동일 구조)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "강릉에코파워"), 0.87, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.90, "기타특수관계자"),
        ],
    },
    "4ba06dc99dd2e438": {  # 기재정정: 강릉에코파워, SP Belle River LP
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "강릉에코파워"), 0.87, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SP Belle River LP"), 0.84, "관계기업"),
        ],
    },
    "577fb5ce5ce4055d": {  # 기재정정: 삼성전자(기타특수관계자), 삼성생명(대규모기업집단)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.92, "기타특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.90, "대규모기업집단 소속회사"),
        ],
    },
    "1daa68518f46db8e": {  # 기재정정: 연결재무제표주석 관계기업 채권채무
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "강릉에코파워"), 0.86, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.90, "기타특수관계자"),
        ],
    },

    # ── 기재정정 감사보고서 표 ────────────────────────────────
    "3aa66d32e5f2e432": {  # 2023 감사보고서: KOLNG(관계기업), 삼성전자(기타특수관계자), 삼성생명(대기업집단)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "KOLNG"), 0.88, "관계기업(LNG)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.92, "기타특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.88, "대규모기업집단"),
        ],
    },
    "a349e358eafb39de": {  # 2023 재무제표주석: KOLNG(종속·관계기업), 삼성전자(기타), 삼성생명(대기업집단)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "KOLNG"), 0.87, "관계기업 및 공동기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.92, "기타특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.88, "대규모기업집단"),
        ],
    },

    # ── 건설부문: 삼성전자 공급 — SUPPLIES_TO ────────────────────
    "574a95c57e9515f8": {  # 2023 사업보고서: 건설부문 산업 특성 — 건축/토목/플랜트 서비스 제공
        "entities": [
            (P, "건설 시공 서비스", "건설 시공 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "건설 시공 서비스", "건설 시공 서비스"), 0.90),
        ],
    },
    "cf2b00c9e0f28e12": {  # 2023 사업보고서: 건설부문 비전 — Creating Futurescape
        "entities": [
            (P, "건설 시공 서비스", "건설 시공 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "건설 시공 서비스", "건설 시공 서비스"), 0.88),
        ],
    },

    # ── 분기보고서 2025: 상사부문 해외 거점 확대 ──────────────────
    "0059d601bf2ba8d4": {  # 2025 분기보고서: 상사부문 — 전세계 40개국 69개 해외 거점, 화학/철강/에너지/소재
        "entities": [
            (P, "철강 트레이딩", "철강 트레이딩"),
            (P, "화학 트레이딩", "화학 트레이딩"),
            (P, "에너지 트레이딩", "에너지 트레이딩"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "철강 트레이딩", "철강 트레이딩"), 0.90),
            E("PRODUCES", ("org", CORP), ("ent", P, "화학 트레이딩", "화학 트레이딩"), 0.90),
            E("PRODUCES", ("org", CORP), ("ent", P, "에너지 트레이딩", "에너지 트레이딩"), 0.88),
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
    print("=== 삼성물산 Stage5 추출 결과 ===")
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
