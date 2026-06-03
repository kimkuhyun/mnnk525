"""Stage 5 비정형 추출 — SK스퀘어 corp_code=01596425, text_micro 전체(~1,933) + table_nl 특수관계(~53).

SK스퀘어 = SK텔레콤에서 2021.11 인적분할된 ICT투자 지주회사.
최상위 지배기업: SK(주).
주요종속기업: 11번가(커머스), 티맵모빌리티(모빌리티/TMAP), 원스토어(앱마켓),
             드림어스컴퍼니(FLO 음악스트리밍), 인크로스(광고플랫폼), SK플래닛(주).
주요관계기업: SK하이닉스, 콘텐츠웨이브, 드림어스컴퍼니(→관계기업 전환 2025), SK쉴더스(공동기업).
기타 특수관계자: SK텔레콤(주), SK이노베이션(주), 피에스앤마케팅(주), 나일홀딩스, 블루시큐리티인베스트먼트.

원장 = db/graph/ledger/extra28_01596425.jsonl (이 추출 전용).
실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_sk_square_01596425.py
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

CORP = "SK스퀘어"
CORP_CODE = "01596425"

# 전용 원장
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_DIR.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = LEDGER_DIR / "extra28_01596425.jsonl"


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
# SK스퀘어: ICT 지주회사. Product = 앱마켓/음악스트리밍/e커머스/내비게이션 서비스,
#           Technology = AI추천/모빌리티데이터/클라우드
# 특수관계자: SK(주)(최상위), SK하이닉스(관계기업), 종속기업들, SK텔레콤(기타)

EXTRACTIONS: dict[str, dict] = {

    # ═══ II. 사업의 내용: 사업 구조 — 5개 부문 명시 ═══

    "021be850d17f8334": {  # 2024.03 분기: SK스퀘어 5개 부문 — 투자/커머스/플랫폼/모빌리티/기타
        "entities": [
            (P, "11번가", "11번가(e커머스)"),
            (P, "원스토어", "원스토어(앱마켓)"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK텔레콤"), 0.93, "분할前 지배기업(인적분할, 2021.11)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK(주)"), 0.95, "최상위 지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "11번가"), 0.95, "종속기업(커머스사업)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "티맵모빌리티"), 0.95, "종속기업(모빌리티사업)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.92, "관계기업(반도체)"),
        ],
    },

    # ═══ II. 사업의 내용: 원스토어 앱마켓 사업 ═══

    "0c60c1eeaf9b02c5": {  # 2023 사업보고서: 앱마켓 경기변동 특성 — 원스토어 앱마켓 시장
        "entities": [
            (P, "원스토어", "원스토어(앱마켓)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "원스토어"), ("ent", P, "원스토어", "원스토어(앱마켓)"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "원스토어"), 0.93, "종속기업(플랫폼사업)"),
        ],
    },
    "1001f75512fc3302": {  # 2023 사업보고서: 원스토어 수수료 인하(30%→20%), 거래액 2배 성장
        "entities": [
            (P, "원스토어", "원스토어(앱마켓)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "원스토어"), ("ent", P, "원스토어", "원스토어(앱마켓)"), 0.93),
            E("RELATED_PARTY", ("org", CORP), ("org", "원스토어"), 0.93, "종속기업(앱마켓)"),
        ],
    },
    "01bd777a6802273d": {  # 2024.06 반기: 원스토어 앱마켓 — 앱판매수수료/운영대행/광고업
        "entities": [
            (P, "원스토어", "원스토어(앱마켓)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "원스토어"), ("ent", P, "원스토어", "원스토어(앱마켓)"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "원스토어"), 0.92, "종속기업(플랫폼사업)"),
        ],
    },
    "1271da8c2a5efeed": {  # 2024.06 반기: 원스토어 수수료 인하 정책 — 2022년까지 4년 연속 거래액 성장
        "entities": [
            (P, "원스토어", "원스토어(앱마켓)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "원스토어"), ("ent", P, "원스토어", "원스토어(앱마켓)"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "원스토어"), 0.92, "종속기업"),
        ],
    },
    "018897170e135f38": {  # 2025.03 분기: 원스토어 크로스플랫폼, 대만 Happytuk 협력, 미국 시장 진출
        "entities": [
            (P, "원스토어", "원스토어(앱마켓)"),
            (T, "크로스플랫폼앱마켓", "크로스플랫폼 앱마켓"),
        ],
        "edges": [
            E("PRODUCES", ("org", "원스토어"), ("ent", P, "원스토어", "원스토어(앱마켓)"), 0.92),
            E("USES_TECH", ("org", "원스토어"), ("ent", T, "크로스플랫폼앱마켓", "크로스플랫폼 앱마켓"), 0.85),
            E("RELATED_PARTY", ("org", CORP), ("org", "원스토어"), 0.92, "종속기업(플랫폼사업)"),
        ],
    },
    "0933d156294ece27": {  # 2026.03 분기: 원스토어 앱마켓 성장성 — D2C 결제 확산, AI 전환
        "entities": [
            (P, "원스토어", "원스토어(앱마켓)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "원스토어"), ("ent", P, "원스토어", "원스토어(앱마켓)"), 0.90),
            E("RELATED_PARTY", ("org", CORP), ("org", "원스토어"), 0.92, "종속기업"),
        ],
    },

    # ═══ II. 사업의 내용: 11번가 e커머스 ═══

    "01dd81d7bded5c3a": {  # 2023.06 반기: 11번가 해외직구 강화, 신선밥상/머니한잔 신규BM 런칭
        "entities": [
            (P, "11번가", "11번가(e커머스)"),
            (P, "신선밥상", "신선밥상(산지직결 판매서비스)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "11번가"), ("ent", P, "11번가", "11번가(e커머스)"), 0.93),
            E("PRODUCES", ("org", "11번가"), ("ent", P, "신선밥상", "신선밥상(산지직결 판매서비스)"), 0.87),
            E("RELATED_PARTY", ("org", CORP), ("org", "11번가"), 0.93, "종속기업(커머스사업)"),
        ],
    },
    "06c275465cb1e8c9": {  # 2023.06 반기: 11번가 판매수수료 구조(10~12%), SK하이닉스 언급
        "entities": [
            (P, "11번가", "11번가(e커머스)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "11번가"), ("ent", P, "11번가", "11번가(e커머스)"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "11번가"), 0.93, "종속기업(커머스사업)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.92, "관계기업"),
        ],
    },
    "0c739455659c8508": {  # 2023 사업보고서 기재정정: 11번가 판매수수료, SK하이닉스 NAND
        "entities": [
            (P, "11번가", "11번가(e커머스)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "11번가"), ("ent", P, "11번가", "11번가(e커머스)"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "11번가"), 0.93, "종속기업(커머스사업)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.93, "관계기업(반도체)"),
        ],
    },
    "01ebecd79ca3ce7e": {  # 2024.09 분기: 11번가 신선밥상/우아럭스/키즈키즈/리퍼블리/OOTD 버티컬몰 런칭
        "entities": [
            (P, "11번가", "11번가(e커머스)"),
            (P, "신선밥상", "신선밥상(산지직결 판매서비스)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "11번가"), ("ent", P, "11번가", "11번가(e커머스)"), 0.93),
            E("PRODUCES", ("org", "11번가"), ("ent", P, "신선밥상", "신선밥상(산지직결 판매서비스)"), 0.87),
            E("RELATED_PARTY", ("org", CORP), ("org", "11번가"), 0.93, "종속기업(커머스사업)"),
        ],
    },

    # ═══ II. 사업의 내용: FLO 음악스트리밍 (드림어스컴퍼니) ═══

    "074be877389af0fc": {  # 2024.09 분기: FLO — 음악스트리밍→오디오 콘텐츠 확대, AI/머신러닝 차트
        "entities": [
            (P, "FLO", "FLO(음악스트리밍서비스)"),
            (T, "AI음악추천", "AI 기반 음악 추천"),
        ],
        "edges": [
            E("PRODUCES", ("org", "드림어스컴퍼니"), ("ent", P, "FLO", "FLO(음악스트리밍서비스)"), 0.95),
            E("USES_TECH", ("org", "드림어스컴퍼니"), ("ent", T, "AI음악추천", "AI 기반 음악 추천"), 0.88),
            E("RELATED_PARTY", ("org", CORP), ("org", "드림어스컴퍼니"), 0.93, "종속기업(뮤직사업)"),
        ],
    },
    "0c4f7d9d6c539b05": {  # 2025.06 반기: FLO — AI/머신러닝 차트(플로차트), 개인맞춤 추천, AWS 클라우드 이전
        "entities": [
            (P, "FLO", "FLO(음악스트리밍서비스)"),
            (T, "AI음악추천", "AI 기반 음악 추천"),
            (T, "클라우드음악서비스", "AWS 기반 클라우드 음악 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", "드림어스컴퍼니"), ("ent", P, "FLO", "FLO(음악스트리밍서비스)"), 0.95),
            E("USES_TECH", ("org", "드림어스컴퍼니"), ("ent", T, "AI음악추천", "AI 기반 음악 추천"), 0.90),
            E("USES_TECH", ("org", "드림어스컴퍼니"), ("ent", T, "클라우드음악서비스", "AWS 기반 클라우드 음악 서비스"), 0.85),
            E("RELATED_PARTY", ("org", CORP), ("org", "드림어스컴퍼니"), 0.93, "종속기업(뮤직사업)"),
        ],
    },
    "19de09077ffcd973": {  # 2024.06 반기: FLO 가격(이용권), 음반 및 디지털콘텐츠 유통, MD사업
        "entities": [
            (P, "FLO", "FLO(음악스트리밍서비스)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "드림어스컴퍼니"), ("ent", P, "FLO", "FLO(음악스트리밍서비스)"), 0.93),
            E("RELATED_PARTY", ("org", CORP), ("org", "드림어스컴퍼니"), 0.92, "종속기업(뮤직사업)"),
        ],
    },
    "172921d4f2678549": {  # 2024.06 반기 기재정정: FLO 무드(Moood:) 서비스 — AI 조인트 임베딩 아키텍처
        "entities": [
            (P, "FLO", "FLO(음악스트리밍서비스)"),
            (T, "조인트임베딩AI", "조인트 임베딩 아키텍처 AI"),
        ],
        "edges": [
            E("PRODUCES", ("org", "드림어스컴퍼니"), ("ent", P, "FLO", "FLO(음악스트리밍서비스)"), 0.95),
            E("USES_TECH", ("org", "드림어스컴퍼니"), ("ent", T, "조인트임베딩AI", "조인트 임베딩 아키텍처 AI"), 0.88),
            E("RELATED_PARTY", ("org", CORP), ("org", "드림어스컴퍼니"), 0.93, "종속기업(뮤직사업)"),
        ],
    },
    "11cc5ff264ffba87": {  # 2024 사업보고서: FLO — AWS 클라우드 이전, FLO 크리에이터스튜디오
        "entities": [
            (P, "FLO", "FLO(음악스트리밍서비스)"),
            (T, "클라우드음악서비스", "AWS 기반 클라우드 음악 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", "드림어스컴퍼니"), ("ent", P, "FLO", "FLO(음악스트리밍서비스)"), 0.95),
            E("USES_TECH", ("org", "드림어스컴퍼니"), ("ent", T, "클라우드음악서비스", "AWS 기반 클라우드 음악 서비스"), 0.87),
            E("RELATED_PARTY", ("org", CORP), ("org", "드림어스컴퍼니"), 0.92, "종속기업(뮤직사업)"),
        ],
    },
    "1a6e9d0434781ded": {  # 2024 사업보고서: FLO 서비스 곡수 9천만, AWS 클라우드 전면 이전
        "entities": [
            (P, "FLO", "FLO(음악스트리밍서비스)"),
            (T, "클라우드음악서비스", "AWS 기반 클라우드 음악 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", "드림어스컴퍼니"), ("ent", P, "FLO", "FLO(음악스트리밍서비스)"), 0.95),
            E("USES_TECH", ("org", "드림어스컴퍼니"), ("ent", T, "클라우드음악서비스", "AWS 기반 클라우드 음악 서비스"), 0.87),
            E("RELATED_PARTY", ("org", CORP), ("org", "드림어스컴퍼니"), 0.92, "종속기업(뮤직사업)"),
        ],
    },
    "1a78ee57709a56e4": {  # 2025.06 반기: FLO — AWS 클라우드 전면이전, 탄력적 서버운영
        "entities": [
            (P, "FLO", "FLO(음악스트리밍서비스)"),
            (T, "클라우드음악서비스", "AWS 기반 클라우드 음악 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", "드림어스컴퍼니"), ("ent", P, "FLO", "FLO(음악스트리밍서비스)"), 0.95),
            E("USES_TECH", ("org", "드림어스컴퍼니"), ("ent", T, "클라우드음악서비스", "AWS 기반 클라우드 음악 서비스"), 0.87),
            E("RELATED_PARTY", ("org", CORP), ("org", "드림어스컴퍼니"), 0.92, "종속기업(뮤직사업)"),
        ],
    },

    # ═══ II. 사업의 내용: 드림어스컴퍼니 — 음반유통 ═══

    "0a897dc4681066e6": {  # 2023.06 반기: 드림어스컴퍼니 — JYP, 피네이션, 물고기뮤직 음악유통
        "entities": [
            (P, "음반디지털콘텐츠유통", "음반 및 디지털콘텐츠 유통"),
        ],
        "edges": [
            E("PRODUCES", ("org", "드림어스컴퍼니"), ("ent", P, "음반디지털콘텐츠유통", "음반 및 디지털콘텐츠 유통"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "드림어스컴퍼니"), 0.92, "종속기업(뮤직사업)"),
        ],
    },
    "0c94336f30f86944": {  # 2024 사업보고서: 드림어스컴퍼니 공연사업 — 빅플래닛메이드, 미스틱스토리 등 협력
        "entities": [
            (P, "공연사업", "공연 기획 및 제작"),
        ],
        "edges": [
            E("PRODUCES", ("org", "드림어스컴퍼니"), ("ent", P, "공연사업", "공연 기획 및 제작"), 0.90),
            E("RELATED_PARTY", ("org", CORP), ("org", "드림어스컴퍼니"), 0.92, "종속기업(뮤직사업)"),
        ],
    },

    # ═══ II. 사업의 내용: 티맵모빌리티(TMAP) ═══

    "02cce8cc02565997": {  # 2026.03 분기: TMAP — 국내 최대 운행·위치 데이터, AI 시대 핵심 기반
        "entities": [
            (P, "TMAP", "TMAP(내비게이션/모빌리티 플랫폼)"),
            (T, "모빌리티데이터", "모빌리티 데이터 플랫폼"),
        ],
        "edges": [
            E("PRODUCES", ("org", "티맵모빌리티"), ("ent", P, "TMAP", "TMAP(내비게이션/모빌리티 플랫폼)"), 0.95),
            E("USES_TECH", ("org", "티맵모빌리티"), ("ent", T, "모빌리티데이터", "모빌리티 데이터 플랫폼"), 0.90),
            E("RELATED_PARTY", ("org", CORP), ("org", "티맵모빌리티"), 0.95, "종속기업(모빌리티사업)"),
        ],
    },
    "09a6a1165fc00e5a": {  # 2025 사업보고서: TMAP — AI·데이터 기반 플랫폼 경쟁, 광고/보험/물류 확장
        "entities": [
            (P, "TMAP", "TMAP(내비게이션/모빌리티 플랫폼)"),
            (T, "모빌리티데이터", "모빌리티 데이터 플랫폼"),
        ],
        "edges": [
            E("PRODUCES", ("org", "티맵모빌리티"), ("ent", P, "TMAP", "TMAP(내비게이션/모빌리티 플랫폼)"), 0.95),
            E("USES_TECH", ("org", "티맵모빌리티"), ("ent", T, "모빌리티데이터", "모빌리티 데이터 플랫폼"), 0.90),
            E("RELATED_PARTY", ("org", CORP), ("org", "티맵모빌리티"), 0.95, "종속기업(모빌리티사업)"),
        ],
    },
    "078c5042b5aa01c8": {  # 2025.03 분기: 티맵모빌리티 — 모빌리티 슈퍼앱 전략, 데이터 핵심경쟁력
        "entities": [
            (P, "TMAP", "TMAP(내비게이션/모빌리티 플랫폼)"),
            (T, "모빌리티데이터", "모빌리티 데이터 플랫폼"),
        ],
        "edges": [
            E("PRODUCES", ("org", "티맵모빌리티"), ("ent", P, "TMAP", "TMAP(내비게이션/모빌리티 플랫폼)"), 0.95),
            E("USES_TECH", ("org", "티맵모빌리티"), ("ent", T, "모빌리티데이터", "모빌리티 데이터 플랫폼"), 0.90),
            E("RELATED_PARTY", ("org", CORP), ("org", "티맵모빌리티"), 0.95, "종속기업(모빌리티사업)"),
        ],
    },
    "16b077506b2c7686": {  # 2024.09 분기: TMAP 국내 최대 이동 Data, API/Data 사업 글로벌 확장
        "entities": [
            (P, "TMAP", "TMAP(내비게이션/모빌리티 플랫폼)"),
            (T, "모빌리티데이터", "모빌리티 데이터 플랫폼"),
        ],
        "edges": [
            E("PRODUCES", ("org", "티맵모빌리티"), ("ent", P, "TMAP", "TMAP(내비게이션/모빌리티 플랫폼)"), 0.95),
            E("USES_TECH", ("org", "티맵모빌리티"), ("ent", T, "모빌리티데이터", "모빌리티 데이터 플랫폼"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "티맵모빌리티"), 0.95, "종속기업(모빌리티사업)"),
        ],
    },
    "0c2268fd1319b37b": {  # 2024 사업보고서: 모빌리티 시장 — 자율주행/UAM/AI 도입 성장
        "entities": [
            (T, "모빌리티데이터", "모빌리티 데이터 플랫폼"),
            (T, "자율주행기술", "자율주행 기술"),
        ],
        "edges": [
            E("USES_TECH", ("org", "티맵모빌리티"), ("ent", T, "모빌리티데이터", "모빌리티 데이터 플랫폼"), 0.88),
            E("USES_TECH", ("org", "티맵모빌리티"), ("ent", T, "자율주행기술", "자율주행 기술"), 0.80),
            E("RELATED_PARTY", ("org", CORP), ("org", "티맵모빌리티"), 0.95, "종속기업(모빌리티사업)"),
        ],
    },
    "09f3dac110a7b573": {  # 2023 사업보고서 기재정정: 티맵모빌리티 — 중개수수료/라이선스료/광고료 수익구조
        "entities": [
            (P, "TMAP", "TMAP(내비게이션/모빌리티 플랫폼)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "티맵모빌리티"), ("ent", P, "TMAP", "TMAP(내비게이션/모빌리티 플랫폼)"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "티맵모빌리티"), 0.95, "종속기업(모빌리티사업)"),
        ],
    },

    # ═══ II. 사업의 내용: 인크로스 광고플랫폼 ═══

    "06e342371a747c48": {  # 2026.03 분기: 인크로스 — 모바일 마케팅 플랫폼, AI 타겟팅 최적화
        "entities": [
            (P, "인크로스모바일광고", "인크로스 모바일 광고 플랫폼"),
            (T, "AI광고타겟팅", "AI 기반 광고 타겟팅"),
        ],
        "edges": [
            E("PRODUCES", ("org", "인크로스"), ("ent", P, "인크로스모바일광고", "인크로스 모바일 광고 플랫폼"), 0.88),
            E("USES_TECH", ("org", "인크로스"), ("ent", T, "AI광고타겟팅", "AI 기반 광고 타겟팅"), 0.82),
            E("RELATED_PARTY", ("org", CORP), ("org", "인크로스"), 0.92, "종속기업(광고/플랫폼사업)"),
        ],
    },

    # ═══ II. 사업의 내용: SK하이닉스 — 관계기업 반도체 ═══

    "0ac56a13f63773be": {  # 2025 사업보고서: SK하이닉스 — DRAM/NAND 메모리반도체, Substrate 공급망
        "entities": [
            (P, "DRAM", "DRAM(메모리반도체)"),
            (P, "NAND", "NAND(메모리반도체)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "SK하이닉스"), ("ent", P, "DRAM", "DRAM(메모리반도체)"), 0.97),
            E("PRODUCES", ("org", "SK하이닉스"), ("ent", P, "NAND", "NAND(메모리반도체)"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.95, "관계기업(반도체, 21.05% 지분)"),
        ],
    },
    "00a95320b6babdf4": {  # 2025 사업보고서: Substrate — 한국/일본/중국 9개사 공급망, 세계반도체 수급
        "entities": [
            (P, "DRAM", "DRAM(메모리반도체)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "SK하이닉스"), ("ent", P, "DRAM", "DRAM(메모리반도체)"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.93, "관계기업(반도체)"),
        ],
    },
    "058d8bebd0b2a9b7": {  # 2025.06 반기: PCB 공급사, 반도체 원자재 — 원가 경쟁력, 생산지 다변화
        "entities": [
            (P, "DRAM", "DRAM(메모리반도체)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "SK하이닉스"), ("ent", P, "DRAM", "DRAM(메모리반도체)"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.93, "관계기업(반도체)"),
        ],
    },

    # ═══ III. 재무제표주석: 종속기업 투자 내역 ═══

    "0071620a27e4080c": {  # 2024.06 반기: 종속기업투자 — 원스토어 지분율 46.4%→45.8%
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원스토어"), 0.95, "종속기업(지분율 45.8%)"),
        ],
    },
    "0e6290f46fa1f6fa": {  # 2024.06 반기 기재정정: 종속기업 투자내역 — 원스토어 지분율 감소
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원스토어"), 0.95, "종속기업"),
        ],
    },
    "3504d53b6a88a1a8": {  # 2025.03 분기: 종속기업투자 — id Quantique SA 지분 IonQ와 교환 계약
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원스토어"), 0.93, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "티맵모빌리티"), 0.93, "종속기업(모빌리티사업)"),
        ],
    },
    "10a4a1ddcaf6ca9a": {  # 2025 사업보고서: 공동기업투자 — SK쉴더스가 코리아시큐리티홀딩스 흡수합병(2025.12)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK쉴더스"), 0.90, "공동기업(코리아시큐리티홀딩스 통해 간접 지배)"),
        ],
    },
    "0d99019d3e55a201": {  # 2024.06 반기 기재정정: 공동기업투자 — SK쉴더스→코리아시큐리티홀딩스 포괄이전, Soteria Bidco에 28.8% 매각
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK쉴더스"), 0.90, "공동기업(코리아시큐리티홀딩스 통해)"),
        ],
    },
    "340d24b58d7bd159": {  # 2024 사업보고서: 공동기업투자 — 코리아시큐리티홀딩스(주)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK쉴더스"), 0.90, "공동기업(코리아시큐리티홀딩스 통해)"),
        ],
    },

    # ═══ III. 재무제표주석: 관계기업 투자내역 ═══

    "1fbde94ed2beba64": {  # 2024 사업보고서: 연결재무제표주석 납입자본 등
        "entities": [],
        "edges": [
            # 이 청크는 일반 회계정책 설명이라 관계기업 직접 언급 없음 — 엣지 없음
        ],
    },

    "07cef79e6c1c1161": {  # 2024.09 분기: 재무제표주석 — 코리아시큐리티홀딩스 지배력 상실, 공동기업 재분류
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK쉴더스"), 0.88, "공동기업(코리아시큐리티홀딩스)"),
        ],
    },
    "13277a8064e16b91": {  # 2024 사업보고서: 재무제표주석 — Techmaker GmbH 유상감자
        "entities": [],
        "edges": [],
    },
    "31c8d4294eb3db21": {  # 2025 사업보고서: id Quantique SA → IonQ 지분교환 완료
        "entities": [],
        "edges": [],
    },
    "25bf4dcc42a11dac": {  # 2025 사업보고서: 원스토어(주) 주주 변경 — PRS 계약, SK플래닛 자사주 소각
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원스토어"), 0.93, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK플래닛"), 0.92, "종속기업(SK플래닛 자사주 소각, 지분율 86.3%→98.5%)"),
        ],
    },
    "38a129a0b63bb336": {  # 2025 사업보고서 연결재무제표주석: 원스토어 주주변경, SK플래닛 자사주소각
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원스토어"), 0.93, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK플래닛"), 0.92, "종속기업"),
        ],
    },
    "1a2e50b448528145": {  # 2025 사업보고서 연결재무제표주석: 드림어스컴퍼니 지배력 상실→관계기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "드림어스컴퍼니"), 0.90, "관계기업(지배력 상실, 2025년)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "콘텐츠웨이브"), 0.88, "관계기업"),
        ],
    },
    "1a8b14395c52fa80": {  # 2024.09 분기: 연결재무제표주석 관계기업 — 코리아시큐리티홀딩스 지분율
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK쉴더스"), 0.88, "공동기업(코리아시큐리티홀딩스)"),
        ],
    },
    "24ddd172e9fe1520": {  # 2024.09 분기: 연결재무제표주석 — 드림어스컴퍼니(iriver 등), 원스토어(로크미디어 등), FSK L&S, 인크로스(마인드노크), 티맵모빌리티(와이엘피)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "드림어스컴퍼니"), 0.93, "종속기업(뮤직사업)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원스토어"), 0.93, "종속기업(앱마켓)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "인크로스"), 0.92, "종속기업(광고/플랫폼)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "티맵모빌리티"), 0.93, "종속기업(모빌리티)"),
        ],
    },
    "071d3aa801c05b76": {  # 2025.03 분기: 연결재무제표주석 — FSK L&S(물류), 인크로스(마인드노크), 티맵(와이엘피)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "인크로스"), 0.92, "종속기업(광고/플랫폼)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "티맵모빌리티"), 0.93, "종속기업(모빌리티)"),
        ],
    },
    "3cf166c7e7b5944c": {  # 2024.03 분기: 연결재무제표주석 — 인크로스(마인드노크), 티맵(와이엘피), SK하이닉스 자기주식 처분
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "인크로스"), 0.92, "종속기업(광고/플랫폼)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "티맵모빌리티"), 0.93, "종속기업(모빌리티)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.93, "관계기업"),
        ],
    },
    "4ac15a143c4cafb0": {  # 2025.09 분기: 연결재무제표주석 — 티맵(와이엘피)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "티맵모빌리티"), 0.93, "종속기업(모빌리티)"),
        ],
    },

    # ═══ 표: 감사보고서/연결감사보고서 특수관계자 범주 목록 ═══

    "20266c9f7db8009f": {  # 2023 사업보고서 감사보고서: 특수관계자 — SK(주)(최상위), SK플래닛 외 38사(종속), 에스케이하이닉스 외 27사(관계)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK(주)"), 0.97, "최상위 지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK플래닛"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.95, "관계기업"),
        ],
    },
    "24b0f5bed652c056": {  # 2023.06 반기 기재정정: 연결재무제표주석 특수관계자 — SK(주)(최상위), 에스케이하이닉스 외 27사(관계), 나일홀딩스·블루시큐리티인베스트먼트(유의적영향력 행사기업)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK(주)"), 0.97, "최상위 지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.95, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "나일홀딩스"), 0.85, "연결실체 일원에게 유의적 영향력 행사기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "블루시큐리티인베스트먼트"), 0.85, "연결실체 일원에게 유의적 영향력 행사기업"),
        ],
    },
    "a5eb23b6e7777627": {  # 2023.06 반기 기재정정: 재무제표주석 특수관계자 — SK쉴더스 외 42사(종속), 에스케이하이닉스 외 27사(관계)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK(주)"), 0.97, "최상위 지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK쉴더스"), 0.93, "종속기업(당시)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.95, "관계기업"),
        ],
    },
    "497fe163227a79aa": {  # 2024 사업보고서 연결감사보고서: 특수관계자 — SK(주)(최상위), 코리아시큐리티홀딩스 외 2사(공동), 에스케이하이닉스 외 23사(관계)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK(주)"), 0.97, "최상위 지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK쉴더스"), 0.90, "공동기업(코리아시큐리티홀딩스)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.95, "관계기업"),
        ],
    },
    "9f4a6d0d09b7b86c": {  # 2024 사업보고서 감사보고서: 특수관계자 — SK플래닛 외 32사(종속), 코리아시큐리티홀딩스 외 2사(공동), 에스케이하이닉스 외 23사(관계)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK(주)"), 0.97, "최상위 지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK플래닛"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK쉴더스"), 0.90, "공동기업(코리아시큐리티홀딩스)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.95, "관계기업"),
        ],
    },
    "96a377aa89cc2780": {  # 2025 사업보고서 연결감사보고서: 특수관계자 — SK쉴더스 외 1사(공동), 에스케이하이닉스 외 16사(관계)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK(주)"), 0.97, "최상위 지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK쉴더스"), 0.93, "공동기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.95, "관계기업"),
        ],
    },

    # ═══ 표: 감사보고서/연결감사보고서 특수관계자 거래 금액 ═══

    "075f2172898be6c8": {  # 2023 사업보고서 연결감사보고서: 거래 — SK(주) 최상위/에스케이하이닉스 관계기업(영업수익 464,438백만)/나일홀딩스·블루시큐리티(영향력행사기업)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK(주)"), 0.95, "최상위 지배기업(영업비용 29,703백만)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.95, "관계기업(배당수익 464,438백만)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "나일홀딩스"), 0.85, "유의적 영향력 행사기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "블루시큐리티인베스트먼트"), 0.85, "유의적 영향력 행사기업"),
        ],
    },
    "a9cc7ffcadd49bcc": {  # 2023 사업보고서 연결감사보고서: 거래 — SK(주), SK하이닉스(229,351백만), 콘텐츠웨이브, 나일홀딩스, 블루시큐리티인베스트먼트
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK(주)"), 0.95, "최상위 지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.95, "관계기업(배당수익 229,351백만)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "콘텐츠웨이브"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "나일홀딩스"), 0.85, "유의적 영향력 행사기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "블루시큐리티인베스트먼트"), 0.85, "유의적 영향력 행사기업"),
        ],
    },
    "3782abc180386cf7": {  # 2024 사업보고서 연결감사보고서: 거래 — SK(주), SK하이닉스(229,351백만), 콘텐츠웨이브, 나일홀딩스, 블루시큐리티인베스트먼트
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK(주)"), 0.95, "최상위 지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.95, "관계기업(배당수익 229,351백만)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "콘텐츠웨이브"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "나일홀딩스"), 0.85, "유의적 영향력 행사기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "블루시큐리티인베스트먼트"), 0.85, "유의적 영향력 행사기업"),
        ],
    },
    "3b0e8aaff6822e69": {  # 2025 사업보고서 연결감사보고서: 거래 — SK(주), SK하이닉스(175,421백만), SK telecom Japan, 콘텐츠웨이브, 차란차, SK쉴더스(공동)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK(주)"), 0.95, "최상위 지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.95, "관계기업(배당수익 175,421백만)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "콘텐츠웨이브"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK쉴더스"), 0.90, "공동기업"),
        ],
    },

    # ═══ 표: 연결감사보고서 채권채무 ═══

    "c547af8a6688e654": {  # 2023 사업보고서 연결감사보고서: 채권채무 — SK(주), SK하이닉스, 나일홀딩스, 블루시큐리티인베스트먼트, SK텔레콤
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK(주)"), 0.95, "최상위 지배기업(미지급금 24,139백만)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.95, "관계기업(배당금수취채권 30,108백만)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "나일홀딩스"), 0.85, "유의적 영향력 행사기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "블루시큐리티인베스트먼트"), 0.85, "유의적 영향력 행사기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK텔레콤"), 0.90, "기타 특수관계자"),
        ],
    },
    "8f0112273d4feb0c": {  # 2023.06 반기 기재정정: 연결재무제표주석 채권채무 — SK(주), SK하이닉스, 나일홀딩스, 블루시큐리티인베스트먼트, SK텔레콤
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK(주)"), 0.95, "최상위 지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.95, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "나일홀딩스"), 0.85, "유의적 영향력 행사기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "블루시큐리티인베스트먼트"), 0.85, "유의적 영향력 행사기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK텔레콤"), 0.90, "기타 특수관계자"),
        ],
    },
    "3f974336e514fdac": {  # 2025 사업보고서 연결감사보고서: 채권채무 — SK(주), SK하이닉스, 콘텐츠웨이브, 드림어스컴퍼니, SK텔레콤, SK쉴더스(공동)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK(주)"), 0.95, "최상위 지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.95, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "콘텐츠웨이브"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "드림어스컴퍼니"), 0.88, "관계기업(지배력 상실 후)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK텔레콤"), 0.90, "기타 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK쉴더스"), 0.90, "공동기업"),
        ],
    },
    "c887cedd694a63b5": {  # 2025 사업보고서 연결감사보고서: 채권채무 — SK(주), SK하이닉스, 콘텐츠웨이브, 유한회사우티, SK텔레콤, SK쉴더스(공동)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK(주)"), 0.95, "최상위 지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.95, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "콘텐츠웨이브"), 0.88, "관계기업(채권 150,000백만)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK텔레콤"), 0.90, "기타 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK쉴더스"), 0.90, "공동기업"),
        ],
    },

    # ═══ 표: 감사보고서 특수관계자 거래 (별도재무제표) ═══

    "3f5e6ea0eb04d2a8": {  # 2024 사업보고서 감사보고서: 거래 — SK(주), SK쉴더스(종속당시), 십일번가, 티맵, 인크로스, SK하이닉스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK(주)"), 0.97, "최상위 지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK쉴더스"), 0.90, "종속기업(당시)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "11번가"), 0.93, "종속기업(커머스)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "티맵모빌리티"), 0.93, "종속기업(모빌리티)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "인크로스"), 0.92, "종속기업(광고)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.95, "관계기업(배당수익 175,320백만)"),
        ],
    },
    "5ddbaeb6318205b5": {  # 2024 사업보고서 감사보고서: 채권채무 — id Quantique, 십일번가, 티맵, SK하이닉스, 콘텐츠웨이브, SK텔레콤씨에스티원(공동)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "11번가"), 0.92, "종속기업(커머스)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "티맵모빌리티"), 0.93, "종속기업(모빌리티)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.95, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "콘텐츠웨이브"), 0.88, "관계기업(채권 150,000백만)"),
        ],
    },
    "c5359c3d1fc2c4c0": {  # 2025 사업보고서 감사보고서: 채권채무 — id Quantique, 십일번가, 티맵, SK하이닉스, 콘텐츠웨이브, SK텔레콤씨에스티원
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "11번가"), 0.92, "종속기업(커머스)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "티맵모빌리티"), 0.92, "종속기업(모빌리티)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.95, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "콘텐츠웨이브"), 0.88, "관계기업"),
        ],
    },

    # ═══ 표: 감사보고서 특수관계자 거래 — 기타 SK그룹사 ═══

    "40f8ec9629e6b4e2": {  # 2023 사업보고서 연결감사보고서: 기타 거래 — 피에스앤마케팅(58,550백만), 피유엠피
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "피에스앤마케팅"), 0.88, "기타 특수관계자(영업비용 58,550백만)"),
        ],
    },
    "5599f906743363a2": {  # 2025 사업보고서 연결감사보고서: 기타 거래 — SK가스, 피에스앤마케팅(63,161백만), 피유엠피, 에스케이위탁관리부동산투자회사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "피에스앤마케팅"), 0.88, "기타 특수관계자(영업비용 63,161백만)"),
        ],
    },
    "9727232ed0fcdbbf": {  # 2025 사업보고서 연결감사보고서: 기타 거래 — 피에스앤마케팅(53,926백만), 피유엠피
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "피에스앤마케팅"), 0.88, "기타 특수관계자(영업비용 53,926백만)"),
        ],
    },

    # ═══ 표: 연결재무제표주석 특수관계자 거래 (상세) ═══

    "1d269561bcbbda35": {  # 2023.06 반기 기재정정: 연결재무제표주석 기타 — SK에너지, SK Global Chemical, 에스케이엠앤서비스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK에너지"), 0.85, "기타 특수관계자(SK그룹 계열)"),
        ],
    },
    "6919648cfb1355bb": {  # 2023.06 반기 기재정정: 연결재무제표주석 기타 — SK온, SK에너지, SK Global Chemical
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK에너지"), 0.83, "기타 특수관계자"),
        ],
    },
    "91948409362fe3d9": {  # 2023.06 반기 기재정정: 연결재무제표주석 — SK(주) 최상위, SK하이닉스(관계기업), 메이크어스, 콘텐츠웨이브
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK(주)"), 0.95, "최상위 지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.95, "관계기업(배당수익 318,635백만)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "콘텐츠웨이브"), 0.88, "관계기업"),
        ],
    },

    # ═══ 표: 재무제표주석 특수관계자 거래 (별도재무제표) ═══

    "18c035c8854d4bc8": {  # 2023.06 반기 기재정정: 재무제표주석 채권채무 — SK쉴더스, 티맵, SK하이닉스, SK이노베이션, SK텔레콤, SK렌터카
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK(주)"), 0.97, "최상위 지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK쉴더스"), 0.92, "종속기업(당시)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "티맵모빌리티"), 0.93, "종속기업(모빌리티)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK이노베이션"), 0.85, "기타 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK텔레콤"), 0.90, "기타 특수관계자"),
        ],
    },
    "69d82ec620c773e3": {  # 2023.06 반기 기재정정: 재무제표주석 거래 — SK(주), SK쉴더스, 11번가, 티맵, SK하이닉스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK(주)"), 0.97, "최상위 지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK쉴더스"), 0.92, "종속기업(당시)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "11번가"), 0.93, "종속기업(커머스)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "티맵모빌리티"), 0.93, "종속기업(모빌리티)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.93, "관계기업"),
        ],
    },
    "744f6b03a443e233": {  # 2023.06 반기 기재정정: 재무제표주석 거래 — SK(주), SK쉴더스, 11번가, 티맵
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK(주)"), 0.97, "최상위 지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK쉴더스"), 0.90, "종속기업(당시)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "11번가"), 0.93, "종속기업(커머스)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "티맵모빌리티"), 0.93, "종속기업(모빌리티)"),
        ],
    },
    "cb294dd054a68a0b": {  # 2023.06 반기 기재정정: 재무제표주석 거래 기타 — SK핀크스, SK매직, SK네트웍스, SK렌터카
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK이노베이션"), 0.83, "기타 특수관계자(SK그룹 계열)"),
        ],
    },
    "9a9d37c7c79da794": {  # 2023.06 반기 기재정정: 재무제표주석 거래 합계
        "entities": [],
        "edges": [],
    },
    "0bb39c61484993b8": {  # 2023.06 반기 기재정정: 재무제표주석 특수관계자 거래 목록 + 주요 경영진 보상
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.93, "관계기업(배당금수익 등)"),
        ],
    },

    # ═══ XI. 분할 관련 SK텔레콤 책임사항 ═══

    "01fa79e4d953cb73": {  # 2024 사업보고서 XI: 분할 전 SK텔레콤 연대책임 — 미확정손실충당부채/우발채무
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK텔레콤"), 0.93, "분할 前 지배기업(연대책임/잔존채무)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.88, "관계기업(반도체, New ICT)"),
        ],
    },

    # ═══ 연결감사보고서 연결실체 내 분할 책임 ═══

    "3307887cd5d67823": {  # 2023.06 반기 기재정정: 분할에 따른 지배기업 책임 — SK텔레콤에서 분리설립
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SK텔레콤"), 0.93, "분할 前 지배기업(인적분할, 2021.11)"),
        ],
    },

    # ═══ II. 사업의 내용: SK하이닉스 SHE 경영 ═══

    "090d38e924e19cb7": {  # 2024.09 분기: SK하이닉스 — SHE 경영시스템(ISO45001, ISO14001, KOSHA MS)
        "entities": [
            (T, "SHE경영시스템", "SHE(Safety·Health·Environment) 경영시스템"),
        ],
        "edges": [
            E("USES_TECH", ("org", "SK하이닉스"), ("ent", T, "SHE경영시스템", "SHE(Safety·Health·Environment) 경영시스템"), 0.85),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.93, "관계기업(반도체)"),
        ],
    },

    # ═══ II. 사업의 내용: 물류사업 — 에프에스케이엘앤에스 ═══

    "05dd3c10b687cbf8": {  # 2025.09 분기: 물류사업 — AI·로봇자동화·디지털트윈·블록체인 활용, 친환경 물류
        "entities": [
            (T, "AI물류자동화", "AI 기반 물류 자동화"),
        ],
        "edges": [
            E("USES_TECH", ("org", "에프에스케이엘앤에스"), ("ent", T, "AI물류자동화", "AI 기반 물류 자동화"), 0.80),
            E("RELATED_PARTY", ("org", CORP), ("org", "에프에스케이엘앤에스"), 0.88, "종속기업(물류사업)"),
        ],
    },

    # ═══ II. 사업의 내용: 드림어스컴퍼니 엔터테인먼트 — MD/공연 ═══

    "01e09fee1f3da47d": {  # 2025.09 분기: 드림어스컴퍼니 — 아티스트 MD, 공연산업 (현장성·일회성)
        "entities": [
            (P, "공연사업", "공연 기획 및 제작"),
        ],
        "edges": [
            E("PRODUCES", ("org", "드림어스컴퍼니"), ("ent", P, "공연사업", "공연 기획 및 제작"), 0.88),
            E("RELATED_PARTY", ("org", CORP), ("org", "드림어스컴퍼니"), 0.92, "종속기업(뮤직사업)"),
        ],
    },
    "06bb96db390d89a9": {  # 2023 사업보고서 기재정정: 드림어스컴퍼니 공연 계절성, MD, 디바이스 사업
        "entities": [
            (P, "공연사업", "공연 기획 및 제작"),
        ],
        "edges": [
            E("PRODUCES", ("org", "드림어스컴퍼니"), ("ent", P, "공연사업", "공연 기획 및 제작"), 0.87),
            E("RELATED_PARTY", ("org", CORP), ("org", "드림어스컴퍼니"), 0.92, "종속기업(뮤직사업)"),
        ],
    },
    "04acd28efeae20fb": {  # 2025.06 반기: K-POP 아이돌 음악 — 드림어스컴퍼니 음악IP/공연 성장
        "entities": [
            (P, "음반디지털콘텐츠유통", "음반 및 디지털콘텐츠 유통"),
        ],
        "edges": [
            E("PRODUCES", ("org", "드림어스컴퍼니"), ("ent", P, "음반디지털콘텐츠유통", "음반 및 디지털콘텐츠 유통"), 0.88),
            E("RELATED_PARTY", ("org", CORP), ("org", "드림어스컴퍼니"), 0.92, "종속기업(뮤직사업)"),
        ],
    },
    "06d128eeccc62f01": {  # 2025.09 분기: K-POP MD 산업 — 드림어스컴퍼니 K-POP MD
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "드림어스컴퍼니"), 0.88, "종속기업(뮤직사업)"),
        ],
    },
    "051d8e1d73c66030": {  # 2023 사업보고서: 뮤직 부문 계절성 — 드림어스컴퍼니 FLO 디지털싱글 음원
        "entities": [
            (P, "FLO", "FLO(음악스트리밍서비스)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "드림어스컴퍼니"), ("ent", P, "FLO", "FLO(음악스트리밍서비스)"), 0.88),
            E("RELATED_PARTY", ("org", CORP), ("org", "드림어스컴퍼니"), 0.92, "종속기업(뮤직사업)"),
        ],
    },
    "05897e3f5b807703": {  # 2024 사업보고서: 뮤직 부문 계절성 — FLO
        "entities": [
            (P, "FLO", "FLO(음악스트리밍서비스)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "드림어스컴퍼니"), ("ent", P, "FLO", "FLO(음악스트리밍서비스)"), 0.88),
            E("RELATED_PARTY", ("org", CORP), ("org", "드림어스컴퍼니"), 0.92, "종속기업(뮤직사업)"),
        ],
    },
    "01c8ef0fc94fc6a7": {  # 2023 사업보고서: 음악 시장 성장 — FLO 음악서비스 관련
        "entities": [
            (P, "FLO", "FLO(음악스트리밍서비스)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "드림어스컴퍼니"), ("ent", P, "FLO", "FLO(음악스트리밍서비스)"), 0.85),
            E("RELATED_PARTY", ("org", CORP), ("org", "드림어스컴퍼니"), 0.90, "종속기업(뮤직사업)"),
        ],
    },
    "047b9724fda34b2b": {  # 2023.06 반기 기재정정: 앱마켓 경기변동 — 원스토어 성장성
        "entities": [
            (P, "원스토어", "원스토어(앱마켓)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "원스토어"), ("ent", P, "원스토어", "원스토어(앱마켓)"), 0.88),
            E("RELATED_PARTY", ("org", CORP), ("org", "원스토어"), 0.92, "종속기업(플랫폼사업)"),
        ],
    },

    # ═══ II. 사업의 내용: 화학물질 SHE CHEMs ═══

    "01b57116ecf6b633": {  # 2023 사업보고서 기재정정: SK하이닉스 SHE CHEMs 운영
        "entities": [
            (T, "SHECHEMs", "SHE CHEMs(화학물질 입고 관리시스템)"),
        ],
        "edges": [
            E("USES_TECH", ("org", "SK하이닉스"), ("ent", T, "SHECHEMs", "SHE CHEMs(화학물질 입고 관리시스템)"), 0.85),
        ],
    },
    "0437b376b40080ab": {  # 2024 사업보고서: SK하이닉스 SHE CHEMs 운영 — 유해화학물질 관리
        "entities": [
            (T, "SHECHEMs", "SHE CHEMs(화학물질 입고 관리시스템)"),
        ],
        "edges": [
            E("USES_TECH", ("org", "SK하이닉스"), ("ent", T, "SHECHEMs", "SHE CHEMs(화학물질 입고 관리시스템)"), 0.85),
            E("RELATED_PARTY", ("org", CORP), ("org", "SK하이닉스"), 0.93, "관계기업(반도체)"),
        ],
    },
}


def run():
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
    print("=== SK스퀘어 Stage5 추출 결과 ===")
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
