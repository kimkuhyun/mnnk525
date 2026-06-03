"""Stage 5 비정형 추출 — 에스원 corp_code=00158501, text_micro 전체(~798) + table_nl 특수관계(~222).

에스원 = 삼성그룹 계열 시스템경비·물리보안 회사.
사업: 시큐리티(물리보안/디지털보안) + 인프라(부동산FM/PM, 통합보안SI).
핵심관계:
  - SECOM CO., LTD.(일본, 유의적 영향력 행사 = 25.65% 주주, 기술지원계약)
  - 삼성전자/삼성생명보험/삼성디스플레이 등 삼성그룹 계열(기타 특수관계자)
  - 종속기업: (주)휴먼티에스에스, 에스원씨알엠(주), 삼성(북경)안방계통기술유한공사,
             S-1 CORPORATION VIETNAM CO., LTD, S-1 CORPORATION HUNGARY LLC,
             에스브이아이씨35호신기술사업투자조합
  - 공동기업: 코람코전문투자형사모부동산신탁제78호
  - 기타 특수관계자: 삼성에프엔위탁관리부동산투자회사(주)

원장 = db/graph/ledger/extra28_00158501.jsonl (이 추출 전용).
실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_s1_00158501.py
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

CORP = "에스원"
CORP_CODE = "00158501"

# 전용 원장
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_DIR.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = LEDGER_DIR / "extra28_00158501.jsonl"


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
# 에스원 = 보안서비스 + 부동산 FM/PM + 보안SI
# Product = 시큐리티서비스 상품라인, 인프라서비스 솔루션
# Technology = AI관제, 지능형영상분석, IoT, SVMS 등
# 특수관계자 = SECOM(유의적영향력), 삼성 계열(기타특수관계자), 종속기업(휴먼티에스에스 등)
# SECOM CO., LTD. → 유의적 영향력을 행사하는 회사(주주 25.65%, 기술지원계약, Royalty 지급)
EXTRACTIONS: dict[str, dict] = {

    # ── II. 사업의 내용: 시큐리티 사업 개요 (물리보안/디지털보안) ──
    "1e5d217a36ad8a98": {  # 분기보고서(2025.09): 시큐리티(물리보안+디지털보안) + 인프라사업 개요
        "entities": [
            (P, "물리보안서비스", "물리보안 서비스"),
            (P, "디지털보안서비스", "디지털보안 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "물리보안서비스", "물리보안 서비스"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "디지털보안서비스", "디지털보안 서비스"), 0.92),
        ],
    },
    "1b4e5df57175efae": {  # 사업보고서(2023.12): 수원/대구 통합관제센터, 방범보안 18년 연속 1위
        "entities": [
            (P, "물리보안서비스", "물리보안 서비스"),
            (T, "통합관제센터", "통합관제센터 이중화 시스템"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "물리보안서비스", "물리보안 서비스"), 0.95),
            E("USES_TECH", ("org", CORP), ("ent", T, "통합관제센터", "통합관제센터 이중화 시스템"), 0.9),
        ],
    },
    "00bc75fce26bad4c": {  # 반기보고서(2025.06): 수원/대구 통합관제센터, 방범보안 20년 연속 1위
        "entities": [
            (P, "물리보안서비스", "물리보안 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "물리보안서비스", "물리보안 서비스"), 0.95),
        ],
    },
    "211f46cae5bc55fd": {  # 분기보고서(2025.09): 수원/대구 통합관제센터
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "물리보안서비스", "물리보안 서비스"), 0.93),
        ],
    },

    # ── II. 사업의 내용: 인프라 사업 — 부동산 FM/PM + 보안SI ──
    "09f2e5454dc950f7": {  # 분기보고서(2025.03): FM/PM/부동산컨설팅, 보안SI 설명
        "entities": [
            (P, "FM시설관리서비스", "FM(Facility Management) 서비스"),
            (P, "PM부동산관리서비스", "PM(Property Management) 서비스"),
            (P, "보안SI서비스", "보안 SI(System Integration) 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "FM시설관리서비스", "FM(Facility Management) 서비스"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "PM부동산관리서비스", "PM(Property Management) 서비스"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "보안SI서비스", "보안 SI(System Integration) 서비스"), 0.92),
        ],
    },
    "12f5a32047f52da3": {  # 분기보고서(2024.03): 부동산 FM/PM + 보안SI 상세 설명
        "entities": [
            (P, "FM시설관리서비스", "FM(Facility Management) 서비스"),
            (P, "보안SI서비스", "보안 SI(System Integration) 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "FM시설관리서비스", "FM(Facility Management) 서비스"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "보안SI서비스", "보안 SI(System Integration) 서비스"), 0.92),
        ],
    },
    "1817fb66665c32e5": {  # 분기보고서(2025.09): FM/PM/부동산컨설팅 설명
        "entities": [
            (P, "FM시설관리서비스", "FM(Facility Management) 서비스"),
            (P, "PM부동산관리서비스", "PM(Property Management) 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "FM시설관리서비스", "FM(Facility Management) 서비스"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "PM부동산관리서비스", "PM(Property Management) 서비스"), 0.9),
        ],
    },

    # ── II. 사업의 내용: 스마트 건물관리 솔루션 '블루스캔' ──────────
    "05adf56a19fd06ae": {  # 분기보고서(2025.03): 블루스캔 스마트 건물관리 솔루션, 스마트케어존
        "entities": [
            (P, "블루스캔", "블루스캔 스마트 건물관리 솔루션"),
            (P, "스마트케어존", "스마트케어존 공간케어 솔루션"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "블루스캔", "블루스캔 스마트 건물관리 솔루션"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "스마트케어존", "스마트케어존 공간케어 솔루션"), 0.92),
        ],
    },
    "24cb8c2703e26109": {  # 분기보고서(2025.09): 블루스캔 + 스마트케어존, 보안SI
        "entities": [
            (P, "블루스캔", "블루스캔 스마트 건물관리 솔루션"),
            (P, "스마트케어존", "스마트케어존 공간케어 솔루션"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "블루스캔", "블루스캔 스마트 건물관리 솔루션"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "스마트케어존", "스마트케어존 공간케어 솔루션"), 0.92),
        ],
    },
    "12f1eb7494d61a76": {  # 분기보고서(2024.09): 블루스캔 + 스마트케어존
        "entities": [
            (P, "블루스캔", "블루스캔 스마트 건물관리 솔루션"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "블루스캔", "블루스캔 스마트 건물관리 솔루션"), 0.93),
        ],
    },
    "22ddccdc9f4a98f5": {  # 반기보고서(2025.06): 블루스캔 + 지능형 모니터링 시스템
        "entities": [
            (P, "블루스캔", "블루스캔 스마트 건물관리 솔루션"),
            (T, "지능형영상분석", "지능형 영상분석 기술"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "블루스캔", "블루스캔 스마트 건물관리 솔루션"), 0.93),
            E("USES_TECH", ("org", CORP), ("ent", T, "지능형영상분석", "지능형 영상분석 기술"), 0.88),
        ],
    },

    # ── II. 사업의 내용: 보안SI 경쟁력 ──────────────────────────
    "293513e7efb27f50": {  # 분기보고서(2025.09): 시큐리티 경쟁력 - 독자 기술(센서, 컨트롤러, 지능형영상감시)
        "entities": [
            (T, "지능형영상분석", "지능형 영상분석 기술"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "지능형영상분석", "지능형 영상분석 기술"), 0.9),
        ],
    },
    "0e84a7c5ef7694d1": {  # 사업보고서(2025.12): 보안SI — 빌딩/공장/국가중요시설 설계구축운영
        "entities": [
            (P, "보안SI서비스", "보안 SI(System Integration) 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "보안SI서비스", "보안 SI(System Integration) 서비스"), 0.93),
        ],
    },
    "20b5f9c42bfd50fe": {  # 사업보고서(2023.12): 보안SI — GOP·발전소 등 국가주요시설
        "entities": [
            (P, "보안SI서비스", "보안 SI(System Integration) 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "보안SI서비스", "보안 SI(System Integration) 서비스"), 0.92),
        ],
    },

    # ── II. 사업의 내용: 연구개발 — AI관제/도어캠/SVMS ──────────
    "16eeb1fd309b44b4": {  # 사업보고서(2025.12): AI관제 기반기술, AI도어캠, SVMS 플러그인 모듈화
        "entities": [
            (T, "AI관제기반기술", "AI 관제 기반기술"),
            (T, "AI도어캠", "AI 기반 도어캠 지능형 영상분석"),
            (T, "SVMS플랫폼", "SVMS(보안영상관리시스템) 플러그인 기반 모듈화"),
            (P, "블루스캔", "블루스캔 스마트 건물관리 솔루션"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "AI관제기반기술", "AI 관제 기반기술"), 0.92),
            E("USES_TECH", ("org", CORP), ("ent", T, "AI도어캠", "AI 기반 도어캠 지능형 영상분석"), 0.9),
            E("USES_TECH", ("org", CORP), ("ent", T, "SVMS플랫폼", "SVMS(보안영상관리시스템) 플러그인 기반 모듈화"), 0.88),
            E("PRODUCES", ("org", CORP), ("ent", P, "블루스캔", "블루스캔 스마트 건물관리 솔루션"), 0.9),
        ],
    },
    "a015864b0940ab1e": {  # 분기보고서(2025.09): AI관제, AI도어캠IoT 연동서버, 영상캡셔닝
        "entities": [
            (T, "AI관제기반기술", "AI 관제 기반기술"),
            (T, "AI도어캠", "AI 기반 도어캠 지능형 영상분석"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "AI관제기반기술", "AI 관제 기반기술"), 0.92),
            E("USES_TECH", ("org", CORP), ("ent", T, "AI도어캠", "AI 기반 도어캠 지능형 영상분석"), 0.9),
        ],
    },
    "679f45051d0e140a": {  # 반기보고서(2025.06): AI도어캠 IoT플랫폼 연동 서버 개발
        "entities": [
            (T, "AI도어캠", "AI 기반 도어캠 지능형 영상분석"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "AI도어캠", "AI 기반 도어캠 지능형 영상분석"), 0.9),
        ],
    },
    "4ad0c92dac4caabe": {  # 분기보고서(2025.03): AI도어캠 IoT플랫폼 연동, 원격제어 확대
        "entities": [
            (T, "AI도어캠", "AI 기반 도어캠 지능형 영상분석"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "AI도어캠", "AI 기반 도어캠 지능형 영상분석"), 0.88),
        ],
    },
    "dd34ea08c34ae900": {  # 사업보고서(2024.12): IoT센서연동, 얼굴리더 AI, 무인매장솔루션
        "entities": [
            (T, "AI얼굴인식", "AI 기반 얼굴리더 인식"),
            (P, "무인매장솔루션", "무인매장 보안 솔루션"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "AI얼굴인식", "AI 기반 얼굴리더 인식"), 0.88),
            E("PRODUCES", ("org", CORP), ("ent", P, "무인매장솔루션", "무인매장 보안 솔루션"), 0.88),
        ],
    },

    # ── II. 사업의 내용: SECOM CO., LTD. 기술지원계약 ───────────
    # SECOM = 유의적 영향력을 행사하는 회사(25.65% 주주), 기술지원계약 → Royalty 0.55% 지급
    "008a67c66a629259": {  # 사업보고서(2023.12): SECOM 기술지원계약, Royalty 0.55%, R&D 개요
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(기술지원계약, Royalty지급)"),
        ],
    },
    "0d8ea44d38681fc9": {  # 사업보고서(2025.12): SECOM 기술지원계약
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(기술지원계약, Royalty지급)"),
        ],
    },
    "18f27ab894399111": {  # 반기보고서(2025.06): SECOM 기술지원계약
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(기술지원계약)"),
        ],
    },
    "54210f388019ffea": {  # 반기보고서(2024.06): SECOM 기술지원계약
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(기술지원계약)"),
        ],
    },
    "aa259b224f79c634": {  # 사업보고서(2024.12): SECOM 기술지원계약
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(기술지원계약)"),
        ],
    },
    "9ce01c0f91e59dd0": {  # 분기보고서(2024.03): SECOM 기술지원계약
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(기술지원계약)"),
        ],
    },
    "4196e8090a0c2f8b": {  # 분기보고서(2024.09): SECOM 기술지원계약 언급(유동성 위험 컨텍스트 내)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.93, "유의적영향력을행사하는회사(기술지원계약)"),
        ],
    },
    "6c64bc78b5c2ac8d": {  # 분기보고서(2025.09): SECOM 기술지원계약 언급
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.93, "유의적영향력을행사하는회사(기술지원계약)"),
        ],
    },
    "885bcf72668c9453": {  # 분기보고서(2026.03): SECOM 기술지원계약
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(기술지원계약)"),
        ],
    },
    "b17b7afc3996595c": {  # 분기보고서(2025.03): SECOM 기술지원계약
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(기술지원계약)"),
        ],
    },

    # ── 연결감사보고서: 지급보증 및 약정 — SECOM 기술지원계약 ─────
    "0fe40e6a6cca28e2": {  # 연결감사보고서(2023.12): SECOM 기술지원계약, Royalty
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(기술지원계약, Royalty지급)"),
        ],
    },
    "280140bd9813f556": {  # 연결감사보고서(2023.12): SECOM 기술지원계약
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(기술지원계약)"),
        ],
    },
    "6a48de141a81b4b3": {  # 연결감사보고서(2024.12): SECOM 기술지원계약
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(기술지원계약)"),
        ],
    },
    "535a0ab706039368": {  # 연결감사보고서(2025.12): SECOM 기술지원계약
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(기술지원계약)"),
        ],
    },

    # ── 감사보고서: 재무제표주석 SECOM 기술지원계약 ──────────────
    "d1f7f7af15d5225c": {  # 감사보고서(2023.12): SECOM 기술지원계약
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(기술지원계약, Royalty지급)"),
        ],
    },
    "d5aee39c94dad80f": {  # 재무제표주석(2023.12): SECOM 기술지원계약
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(기술지원계약)"),
        ],
    },
    "cc10cc0783edca35": {  # 감사보고서(2024.12): SECOM 기술지원계약
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(기술지원계약)"),
        ],
    },

    # ── 재무제표/연결주석: SECOM 배당금 지급 및 특수관계자 거래 ──────
    "0e753f0399fdf429": {  # 재무제표주석(2023.12): SECOM 배당금 243억, 휴먼티에스에스 배당 수령
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(배당금지급)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "휴먼티에스에스"), 0.92, "종속기업(배당금수령)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "코람코전문투자형사모부동산신탁제78호"), 0.88, "공동기업(배당금수령)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에프엔위탁관리부동산투자회사"), 0.88, "기타의특수관계자(배당금수령)"),
        ],
    },
    "3061e04259617511": {  # 연결감사보고서(2023.12): 특수관계자 거래 - SECOM 배당 지급
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(배당금지급243억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "코람코전문투자형사모부동산신탁제78호"), 0.88, "공동기업"),
        ],
    },
    "43f7034b8f40d271": {  # 감사보고서(2023.12): SECOM 배당, 휴먼티에스에스 배당, 삼성에프엔 배당
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(배당금지급)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "휴먼티에스에스"), 0.92, "종속기업(배당금수령)"),
        ],
    },
    "ad92a5212eda503d": {  # 연결재무제표주석(2023.12): SECOM 배당 지급, 코람코 배당
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(배당금지급)"),
        ],
    },

    # ── 재무제표주석: SECOM 주주현황(지분율 25.65%) ───────────────
    "94898b25eb096cf5": {  # 재무제표주석(2023.12): 주주 = SECOM 25.65%, 삼성계열 20.57%
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(지분25.65%, 최대주주)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.88, "기타의특수관계자(삼성그룹계열)"),
        ],
    },
    "e2494e0477bb8b16": {  # 감사보고서(2023.12): 주주 = SECOM 25.65%, 삼성계열 20.57%
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(지분25.65%)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.88, "기타의특수관계자(삼성그룹계열)"),
        ],
    },

    # ── 연결재무제표주석: 일반적 사항 — 종속기업 목록 ─────────────
    "1a0353d944c4f5f3": {  # 연결재무제표주석(2023.12): 종속기업 = 휴먼티에스에스 등 6개사, SECOM 출자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(1980년출자, 합작투자기업설립)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "휴먼티에스에스"), 0.95, "종속기업"),
        ],
    },
    "6aa56bbb4e8e5b0f": {  # 연결감사보고서(2024.12): 종속기업 = 휴먼티에스에스 등 6개사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.93, "유의적영향력을행사하는회사(합작투자기업)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "휴먼티에스에스"), 0.95, "종속기업"),
        ],
    },
    "7d4f9dd02c26a2fc": {  # 연결감사보고서(2023.12): 종속기업 6개사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "휴먼티에스에스"), 0.95, "종속기업"),
        ],
    },
    "b8b0f95a23b6502d": {  # 연결감사보고서(2025.12): 종속기업 6개사, SECOM 출자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.93, "유의적영향력을행사하는회사(1980년출자)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "휴먼티에스에스"), 0.95, "종속기업"),
        ],
    },

    # ── 특수관계자 현황표(감사보고서/연결) — 종속기업 명시 ──────────
    "05dec21989cba706": {  # 감사보고서(2023.12): 종속기업 목록 = 휴먼티에스에스, 에스원씨알엠, 삼성(북경)안방...
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "휴먼티에스에스"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에스원씨알엠"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성(북경)안방계통기술유한공사"), 0.92, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "S-1 CORPORATION VIETNAM CO LTD"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "S-1 CORPORATION HUNGARY LLC"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "코람코전문투자형사모부동산신탁제78호"), 0.88, "공동기업"),
        ],
    },

    # ── 재무제표주석 특수관계자 채권채무 표 ─────────────────────
    "04d9965c9ba64eb6": {  # 연결재무제표주석(2023.12): SECOM 기타채무, 삼성전자 매출채권 595억
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(채권채무)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.92, "기타의특수관계자(매출채권595억)"),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.88),
        ],
    },
    "190a7ec235b9fc98": {  # 감사보고서(2023.12): 에스원씨알엠, 삼성(북경), 베트남, 헝가리 채권채무
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "에스원씨알엠"), 0.95, "종속기업(매입채무)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성(북경)안방계통기술유한공사"), 0.92, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "S-1 CORPORATION VIETNAM CO LTD"), 0.9, "종속기업"),
        ],
    },
    "0b0a7bd2238706d1": {  # 감사보고서(2025.12): 에스원씨알엠, 삼성(북경), 베트남, 헝가리 채권채무
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "휴먼티에스에스"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에스원씨알엠"), 0.95, "종속기업(매입채무)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성(북경)안방계통기술유한공사"), 0.92, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사"),
        ],
    },

    # ── 연결재무제표주석: 삼성전자 주요 매출처(SUPPLIES_TO) ──────
    "1900136b20c61d34": {  # 연결재무제표주석(2023.12): 삼성전자 매출 4,796억, 삼성생명 650억, 삼성디스플레이
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.95, "기타의특수관계자(주요매출처)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.9, "기타의특수관계자(주요매출처)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성디스플레이"), 0.88, "기타의특수관계자"),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.92),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성생명보험"), 0.88),
        ],
    },
    "23fb3e3dcaf11a7d": {  # 연결감사보고서(2025.12): 삼성전자 5,338억, 삼성생명 826억, 삼성디스플레이
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.95, "기타의특수관계자(주요매출처5338억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.92, "기타의특수관계자(주요매출처826억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성디스플레이"), 0.88, "기타의특수관계자"),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성생명보험"), 0.9),
        ],
    },

    # ── 특수관계자 거래 표(연결/별도): SECOM + 삼성계열 분류 ────────
    "0383edce955cfd98": {  # 연결재무제표주석(2024.06 반기): 특수관계자 = SECOM, 삼성에프엔, 기타
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에프엔위탁관리부동산투자회사"), 0.88, "기타의특수관계자"),
        ],
    },
    "11010c125406cba6": {  # 연결재무제표주석(2024.03 분기): SECOM, 삼성에프엔
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에프엔위탁관리부동산투자회사"), 0.88, "기타의특수관계자"),
        ],
    },
    "160a2689fac82b8e": {  # 연결재무제표주석(2024.09 분기): SECOM, 코람코, 삼성에프엔
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "코람코전문투자형사모부동산신탁제78호"), 0.88, "공동기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에프엔위탁관리부동산투자회사"), 0.88, "기타의특수관계자"),
        ],
    },
    "15db318ccd2e8e4a": {  # 연결재무제표주석(2025.09 분기): SECOM, 코람코, 기타
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "코람코전문투자형사모부동산신탁제78호"), 0.88, "공동기업"),
        ],
    },
    "229e1e7fefc5c0c9": {  # 연결재무제표주석(2025.12): SECOM, 코람코, 기타
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "코람코전문투자형사모부동산신탁제78호"), 0.88, "공동기업"),
        ],
    },

    # ── 재무제표주석 특수관계자 표(별도): 종속기업 + SECOM + 삼성에프엔 ──
    "0f19079bcf8592f9": {  # 재무제표주석(2024.06 반기): 휴먼티에스에스, S-1헝가리, SECOM, 코람코, 삼성에프엔
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "휴먼티에스에스"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "S-1 CORPORATION HUNGARY LLC"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "코람코전문투자형사모부동산신탁제78호"), 0.88, "공동기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에프엔위탁관리부동산투자회사"), 0.88, "기타의특수관계자"),
        ],
    },
    "1d993379b81ba0bc": {  # 재무제표주석(2024.06 반기): 휴먼티에스에스, S-1헝가리, SECOM, 코람코, 삼성에프엔
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "휴먼티에스에스"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "S-1 CORPORATION HUNGARY LLC"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "코람코전문투자형사모부동산신탁제78호"), 0.88, "공동기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에프엔위탁관리부동산투자회사"), 0.88, "기타의특수관계자"),
        ],
    },
    "12e755843a835ae6": {  # 재무제표주석(2024.09 분기): 휴먼티에스에스, S-1헝가리, SECOM, 코람코, 삼성에프엔
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "휴먼티에스에스"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "코람코전문투자형사모부동산신탁제78호"), 0.88, "공동기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에프엔위탁관리부동산투자회사"), 0.88, "기타의특수관계자"),
        ],
    },

    # ── 재무제표주석 별도(2025 사업/분기보고서) 특수관계자 ───────────
    "1b2ff46f3822a81c": {  # 재무제표주석(2025.12): 종속기업2, SECOM, 코람코, 기타2
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "코람코전문투자형사모부동산신탁제78호"), 0.88, "공동기업"),
        ],
    },
    "1ff98dfb879f3e47": {  # 재무제표주석(2024.03 분기): 종속기업16, SECOM×4, 기타6
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사"),
        ],
    },
    "021dbbda5f7ce1d2": {  # 재무제표주석(2024.09 분기): 종속기업20, SECOM×4, 기타
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사"),
        ],
    },

    # ── 연결감사보고서/재무제표주석: 삼성에프엔 배당, 삼성그룹 계열 ──
    "17126959dbeb905d": {  # 감사보고서(2025.12): 에스원씨알엠, 삼성(북경), 베트남, 헝가리 거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "에스원씨알엠"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성(북경)안방계통기술유한공사"), 0.92, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "S-1 CORPORATION VIETNAM CO LTD"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "S-1 CORPORATION HUNGARY LLC"), 0.9, "종속기업"),
        ],
    },

    # ── IX. 계열회사: 삼성그룹 소속 공표 ────────────────────────
    "0a1161d931458c89": {  # 계열회사(2023.12): 삼성그룹 63개 계열사, 에스원 상장
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.88, "기타의특수관계자(삼성그룹계열)"),
        ],
    },
    "9072dea5ffa811a3": {  # 계열회사(2024.12): 삼성그룹 63개 계열사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.88, "기타의특수관계자(삼성그룹계열)"),
        ],
    },
    "68479e7d6f4adea2": {  # 계열회사(2025.12): 삼성그룹 67개 계열사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.88, "기타의특수관계자(삼성그룹계열)"),
        ],
    },
    "e5670979530d4aae": {  # 계열회사(2024.06 반기): 삼성그룹 63개
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.88, "기타의특수관계자(삼성그룹계열)"),
        ],
    },
    "b143e338513da1f6": {  # 계열회사(2025.06 반기): 삼성그룹 63개
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.88, "기타의특수관계자(삼성그룹계열)"),
        ],
    },

    # ── II. 사업의 내용: 경기변동특성, 산업 규제 ─────────────────
    "0cbb127d69c919df": {  # 분기보고서(2024.03): 물리보안 시큐리티서비스 경기변동특성, 원격모니터링
        "entities": [
            (T, "원격모니터링기술", "원격 모니터링 및 실시간 제어 기술"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "원격모니터링기술", "원격 모니터링 및 실시간 제어 기술"), 0.85),
        ],
    },
    "1195e24d7c485494": {  # 분기보고서(2025.03): 원격 모니터링, 긴급대처, 사용자인증
        "entities": [
            (T, "원격모니터링기술", "원격 모니터링 및 실시간 제어 기술"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "원격모니터링기술", "원격 모니터링 및 실시간 제어 기술"), 0.85),
        ],
    },
    "0f20d7988ac56280": {  # 반기보고서(2024.06): 물리보안 산업, 유무선통신+IT 첨단기술
        "entities": [
            (P, "물리보안서비스", "물리보안 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "물리보안서비스", "물리보안 서비스"), 0.93),
        ],
    },

    # ── 연결재무제표주석: 약정사항(SECOM) + 공급자금융약정 ───────────
    "1b5b1dcc90bef581": {  # 연결감사보고서(2025.12): SECOM 기술지원계약 약정, 주요경영진보상
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(기술지원계약약정)"),
        ],
    },
    "049ee8f7552a9667": {  # 연결감사보고서(2024.12): 주요경영진보상, 영업부문보고 (시큐리티+인프라)
        "entities": [
            (P, "시큐리티서비스", "시큐리티 사업"),
            (P, "인프라서비스", "인프라 사업"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "시큐리티서비스", "시큐리티 사업"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "인프라서비스", "인프라 사업"), 0.92),
        ],
    },

    # ── 연결재무제표주석: 종속기업 요약재무 ────────────────────────
    "0809ff47ffa4917d": {  # 연결감사보고서(2023.12): 종속기업 요약재무정보
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "휴먼티에스에스"), 0.95, "종속기업(요약재무)"),
        ],
    },
    "14daff04c1bb4e6a": {  # 연결재무제표주석(2024.12): 종속기업 요약재무
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "휴먼티에스에스"), 0.95, "종속기업"),
        ],
    },

    # ── 사업의 미래비전/신규사업 청크 ─────────────────────────────
    "1b08da63fad5f423": {  # 사업보고서(2023.12): 부동산서비스 역량 - 초고층빌딩/호텔/병원/연구소 FM
        "entities": [
            (P, "FM시설관리서비스", "FM(Facility Management) 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "FM시설관리서비스", "FM(Facility Management) 서비스"), 0.93),
        ],
    },
    "11934d1bc3ee1430": {  # 사업보고서(2024.12) IV: FM/PM, 보안SI 시큐리티+인프라 사업
        "entities": [
            (P, "FM시설관리서비스", "FM(Facility Management) 서비스"),
            (P, "PM부동산관리서비스", "PM(Property Management) 서비스"),
            (P, "보안SI서비스", "보안 SI(System Integration) 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "FM시설관리서비스", "FM(Facility Management) 서비스"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "PM부동산관리서비스", "PM(Property Management) 서비스"), 0.9),
            E("PRODUCES", ("org", CORP), ("ent", P, "보안SI서비스", "보안 SI(System Integration) 서비스"), 0.9),
        ],
    },
    "28c498df502f95f5": {  # 반기보고서(2024.06): 부동산서비스(IBS 도입)+보안SI 성장 전망
        "entities": [
            (P, "보안SI서비스", "보안 SI(System Integration) 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "보안SI서비스", "보안 SI(System Integration) 서비스"), 0.9),
        ],
    },
    "07c99222644b8577": {  # 반기보고서(2024.06): 연구개발비용, 시큐리티서비스 첨단기술력
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "물리보안서비스", "물리보안 서비스"), 0.88),
        ],
    },

    # ── 별도재무제표주석 SECOM 관련(1580x 감사보고서 등) ───────────
    "a7770724674af505": {  # 감사보고서(2024.12): SECOM 출자, 주주현황
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(출자)"),
        ],
    },
    "db62eba938f455e6": {  # 감사보고서(2025.12): SECOM 출자, 주주
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.95, "유의적영향력을행사하는회사(지분25.65%)"),
        ],
    },
    "55979a36ed018c48": {  # 감사보고서(2025.12): 확정급여채무 민감도분석
        "entities": [],
        "edges": [],
    },

    # ── 별도재무제표주석: 삼성에프엔위탁관리부동산투자회사 약정 ────────
    "0ce903155f4fa926": {  # 재무제표주석(2025.12): 대규모 특수관계자표
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에프엔위탁관리부동산투자회사"), 0.88, "기타의특수관계자"),
        ],
    },
    "0ee841260442097e": {  # 재무제표주석(2025.12): 대규모 특수관계자표
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에프엔위탁관리부동산투자회사"), 0.88, "기타의특수관계자"),
        ],
    },
    "11a062f7f46b8c3b": {  # 재무제표주석(2025.12): 대규모 특수관계자표
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에프엔위탁관리부동산투자회사"), 0.88, "기타의특수관계자"),
        ],
    },
    "17054afbd6975c2a": {  # 연결재무제표주석(2025.12): 종속기업 등 대규모 특수관계자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.93, "유의적영향력을행사하는회사"),
        ],
    },
    "104effea2b093bb7": {  # 연결재무제표주석(2025.09): 종속기업 등 대규모 특수관계자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.93, "유의적영향력을행사하는회사"),
        ],
    },
    "18b14fd12dea5af9": {  # 연결재무제표주석(2025.09): 대규모 특수관계자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.93, "유의적영향력을행사하는회사"),
        ],
    },
    "093999ee9f65b355": {  # 연결재무제표주석(2025.03): 대규모 특수관계자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.93, "유의적영향력을행사하는회사"),
        ],
    },
    "2212c70abfb8683d": {  # 재무제표주석(2025.06): 대규모 특수관계자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에프엔위탁관리부동산투자회사"), 0.88, "기타의특수관계자"),
        ],
    },
    "04b72aaa57c882a4": {  # 연결재무제표주석(2026.03): 대규모 특수관계자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.93, "유의적영향력을행사하는회사"),
        ],
    },
    "0935eeec2f49c730": {  # 재무제표주석(2026.03): 대규모 특수관계자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에프엔위탁관리부동산투자회사"), 0.88, "기타의특수관계자"),
        ],
    },
    "1239aa073a94af2c": {  # 연결재무제표주석(2026.03): 대규모 특수관계자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.93, "유의적영향력을행사하는회사"),
        ],
    },
    "07ee7432919c1008": {  # 재무제표주석(2024.12): 특수관계자 제외 주석
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "SECOM CO LTD"), 0.9, "유의적영향력을행사하는회사"),
        ],
    },

    # ── IV. 이사의 경영진단: 시큐리티+인프라 사업 보고 ────────────
    "037dd7c83fe10118": {  # 사업보고서(2023.12) IV: IFRS 관련, 한국채택국제회계기준 도입
        "entities": [],
        "edges": [],
    },
    "257fee21eba44e5a": {  # 분기보고서(2026.03): 시큐리티 사업 특성/개요
        "entities": [
            (P, "물리보안서비스", "물리보안 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "물리보안서비스", "물리보안 서비스"), 0.92),
        ],
    },

    # ── 연결재무제표주석: 영업부문 (시큐리티/인프라 2부문) ───────────
    "049ee8f7552a9667": {  # 연결감사보고서(2024.12): 시큐리티/인프라 2사업부문 보고
        "entities": [
            (P, "시큐리티서비스", "시큐리티 사업"),
            (P, "인프라서비스", "인프라 사업"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "시큐리티서비스", "시큐리티 사업"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "인프라서비스", "인프라 사업"), 0.92),
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
    print("=== 에스원 Stage5 추출 결과 ===")
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
