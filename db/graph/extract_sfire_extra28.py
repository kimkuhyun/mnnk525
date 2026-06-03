"""Stage 5 비정형 추출 — 삼성화재해상보험 corp_code=00139214, text_micro 전체(~3,362) + table_nl 특수관계(~370).

삼성화재 = 손해보험사. 제품(Product) = 보험상품 라인, 서비스(Product/Technology) = 손해사정·출동·디지털.
특수관계자 위주(종속·관계기업·그 밖의 특수관계자) + 해외파트너 + 서비스 엔티티.

원장 = db/graph/ledger/extra28_00139214.jsonl (이 추출 전용).
실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_sfire_extra28.py
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

CORP = "삼성화재해상보험"  # resolve_org → corp_code 00139214
CORP_CODE = "00139214"

# ── 전용 원장 ─────────────────────────────────────────────────
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_DIR.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = LEDGER_DIR / "extra28_00139214.jsonl"


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
# 삼성화재는 보험사라 Product=보험상품/서비스, Technology=InsurTech/디지털 기술
# 특수관계자 = 종속기업(삼성화재애니카손해사정, 삼성화재서비스손해사정, 삼성화재금융서비스보험대리점, 해외법인)
#             + 관계기업(삼성재산보험(중국), Petrolimex Insurance, 신공항하이웨이, Fortuna Topco)
#             + 그 밖의 특수관계자(삼성전자, 삼성디스플레이, 삼성생명)
EXTRACTIONS: dict[str, dict] = {

    # ── II. 사업의 내용: 보험상품 라인 (2023 사업보고서) ──────
    "576e499654859b4a": {  # 기타사업 산업특성: 손해사정서비스, 고객상담, 출동서비스, 보험대리점 영업
        "entities": [
            (P, "손해사정서비스", "손해사정서비스"),
            (P, "고객상담서비스", "고객상담서비스"),
            (P, "출동서비스", "출동서비스"),
            (P, "보험대리점영업", "보험대리점 영업"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "손해사정서비스", "손해사정서비스"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "고객상담서비스", "고객상담서비스"), 0.9),
            E("PRODUCES", ("org", CORP), ("ent", P, "출동서비스", "출동서비스"), 0.9),
            E("PRODUCES", ("org", CORP), ("ent", P, "보험대리점영업", "보험대리점 영업"), 0.88),
        ],
    },
    "c5ec93b54d1f8d9f": {  # 사업부문별: 국내외 손해보험업, 기타(손해사정·상담·출동·보험대리점)
        "entities": [
            (P, "일반보험", "일반보험"),
            (P, "자동차보험", "자동차보험"),
            (P, "장기손해보험", "장기손해보험"),
            (P, "개인연금보험", "개인연금"),
            (P, "퇴직연금보험", "퇴직연금"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "일반보험", "일반보험"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "자동차보험", "자동차보험"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "장기손해보험", "장기손해보험"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "개인연금보험", "개인연금"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "퇴직연금보험", "퇴직연금"), 0.92),
        ],
    },
    "068a7a8627d16cf5": {  # 분기보고서 보험상품 라인: 일반보험/자동차보험/장기손해보험/개인연금/퇴직연금
        "entities": [
            (P, "일반보험", "일반보험"),
            (P, "자동차보험", "자동차보험"),
            (P, "장기손해보험", "장기손해보험"),
            (P, "개인연금보험", "개인연금"),
            (P, "퇴직연금보험", "퇴직연금"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "일반보험", "일반보험"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "자동차보험", "자동차보험"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "장기손해보험", "장기손해보험"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "개인연금보험", "개인연금"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "퇴직연금보험", "퇴직연금"), 0.92),
        ],
    },
    "7c954036f8a92301": {  # 기타사업 경쟁력: 손해사정·상담·출동·보험대리점 서비스 역량
        "entities": [
            (P, "손해사정서비스", "손해사정서비스"),
            (P, "고객상담서비스", "고객상담서비스"),
            (P, "출동서비스", "출동서비스"),
            (P, "보험대리점영업", "보험대리점 영업"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "손해사정서비스", "손해사정서비스"), 0.9),
            E("PRODUCES", ("org", CORP), ("ent", P, "고객상담서비스", "고객상담서비스"), 0.88),
            E("PRODUCES", ("org", CORP), ("ent", P, "출동서비스", "출동서비스"), 0.9),
            E("PRODUCES", ("org", CORP), ("ent", P, "보험대리점영업", "보험대리점 영업"), 0.88),
        ],
    },
    "83a713de089674c1": {  # 출동서비스: 삼성화재애니카손해사정(주) 통해 사고·고장출동, 애니카랜드 정비소
        "entities": [
            (P, "출동서비스", "출동서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "출동서비스", "출동서비스"), 0.92),
            # 삼성화재애니카손해사정(주)를 통해 제공 → SUPPLIES_TO(역방향 종속기업이 제공)
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재애니카손해사정"), 0.92, "종속기업(출동서비스 운영)"),
        ],
    },
    "9b22681566d6db83": {  # 손해사정 매출 2,782억(23년): 삼성화재애니카손해사정(주) 통해 운영
        "entities": [
            (P, "손해사정서비스", "손해사정서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "손해사정서비스", "손해사정서비스"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재애니카손해사정"), 0.92, "종속기업(손해사정서비스 운영)"),
        ],
    },
    "b115f27ba299e2f7": {  # 손해사정서비스 시장여건: 삼성화재서비스손해사정(주) 통해 상담서비스
        "entities": [
            (P, "손해사정서비스", "손해사정서비스"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재서비스손해사정"), 0.9, "종속기업(고객상담서비스 운영)"),
        ],
    },
    "d49388753b106802": {  # 기타사업 서비스: 손해사정(삼성화재애니카, 삼성화재서비스), 고객상담(1588-5114)
        "entities": [
            (P, "손해사정서비스", "손해사정서비스"),
            (P, "고객상담서비스", "고객상담서비스"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재애니카손해사정"), 0.92, "종속기업(손해사정서비스)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재서비스손해사정"), 0.9, "종속기업(손해사정/고객상담서비스)"),
            E("PRODUCES", ("org", CORP), ("ent", P, "손해사정서비스", "손해사정서비스"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "고객상담서비스", "고객상담서비스"), 0.88),
        ],
    },

    # ── II. 사업의 내용: 경쟁력 — 데이터/디지털/헬스케어 기술 ──
    "06b70f7af049e79e": {  # 경쟁력 요인: 광범위한 데이터 축적·분석으로 보험료 산출, Risk별 손해율 관리
        "entities": [
            (T, "빅데이터 보험료산출", "빅데이터 기반 보험료 산출"),
            (T, "손해율관리", "Risk별 손해율 관리"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "빅데이터 보험료산출", "빅데이터 기반 보험료 산출"), 0.85),
            E("USES_TECH", ("org", CORP), ("ent", T, "손해율관리", "Risk별 손해율 관리"), 0.82),
        ],
    },
    "fa46be7ae4db3878": {  # 경쟁우위 수단: 대면 전속채널+멀티채널, 리스크컨설팅, 개인자산관리 역량
        "entities": [
            (T, "멀티채널전략", "멀티채널 운용 전략"),
            (T, "리스크컨설팅", "리스크 컨설팅"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "멀티채널전략", "멀티채널 운용 전략"), 0.82),
            E("USES_TECH", ("org", CORP), ("ent", T, "리스크컨설팅", "리스크 컨설팅"), 0.85),
        ],
    },

    # ── II. 사업의 내용: 해외사업 — 캐노피우스(Canopius) 종속·투자 ──
    "315f01638414e289": {  # 신규사업: 캐노피우스(Canopius Group Limited) 지분투자(2019), Fortuna Topco Limited
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Canopius Group Limited"), 0.92, "종속기업(영국 로이즈 손보사, 지분투자)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Fortuna Topco Limited"), 0.9, "종속기업(캐노피우스 100% 주주)"),
        ],
    },
    "20a7191c4b38e48e": {  # 해외사업: 캐노피우스 로이즈5위권, 텐센트와 중국합작법인 전환(2022)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Canopius Group Limited"), 0.9, "종속기업(글로벌 특종보험사)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "텐센트"), 0.88, "합작법인 파트너(중국법인 전환)"),
        ],
    },
    "92edff65b048d5da": {  # IV 경영진단 신규사업: 캐노피우스 지분투자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Canopius Group Limited"), 0.9, "종속기업(지분투자, 2019)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Fortuna Topco Limited"), 0.88, "종속기업(캐노피우스 지주사)"),
        ],
    },
    "adf5560b083e1ae6": {  # IV 전망: Canopius사와 경제적 시너지, 피투자사 사업협력
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Canopius Group Limited"), 0.88, "종속기업(사업시너지)"),
        ],
    },

    # ── II. 사업의 내용: 해외사업 보험영업 범위 ──────────────
    "16e9b5c9414cf33b": {  # 반기보고서(2025.06): 해외법인 FY25반기 매출 3,630억, 재물·적하·배상·자동차 보험판매
        "entities": [
            (P, "재물보험", "재물보험"),
            (P, "적하보험", "적하보험"),
            (P, "배상책임보험", "배상책임보험"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "재물보험", "재물보험"), 0.9),
            E("PRODUCES", ("org", CORP), ("ent", P, "적하보험", "적하보험"), 0.88),
            E("PRODUCES", ("org", CORP), ("ent", P, "배상책임보험", "배상책임보험"), 0.9),
        ],
    },
    "0b09c93150eb07e4": {  # 2025년 사업보고서 해외사업 FY25 매출 6,890억: 보험영업+투자영업
        "entities": [
            (P, "재물보험", "재물보험"),
            (P, "적하보험", "적하보험"),
            (P, "배상책임보험", "배상책임보험"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "재물보험", "재물보험"), 0.9),
            E("PRODUCES", ("org", CORP), ("ent", P, "적하보험", "적하보험"), 0.88),
            E("PRODUCES", ("org", CORP), ("ent", P, "배상책임보험", "배상책임보험"), 0.9),
        ],
    },

    # ── II. 사업의 내용: 중국법인·텐센트 합작사업 ──────────────
    "01975240f92f1349": {  # 2025 사업보고서: 중국법인 온라인보험(건강상해·택배반송), 디지털 비즈니스
        "entities": [
            (P, "건강상해보험", "건강상해보험"),
            (P, "택배반송보험", "택배반송보험"),
            (T, "디지털보험", "디지털 보험"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "건강상해보험", "건강상해보험"), 0.88),
            E("PRODUCES", ("org", CORP), ("ent", P, "택배반송보험", "택배반송보험"), 0.88),
            E("USES_TECH", ("org", CORP), ("ent", T, "디지털보험", "디지털 보험"), 0.85),
            E("RELATED_PARTY", ("org", CORP), ("org", "텐센트"), 0.88, "합작법인 파트너(중국법인, 온라인보험)"),
        ],
    },
    "03e0f875454be005": {  # 반기보고서: 중국 텐센트 합작법인 출범(2022.11.24), 캐노피우스 성장
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "텐센트"), 0.9, "합작법인 파트너(중국법인, 2022.11 출범)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Canopius Group Limited"), 0.9, "종속기업(글로벌 특종보험사)"),
        ],
    },
    "0c407ba4b197dd68": {  # 2024 반기보고서: 텐센트 중국합작법인, 캐노피우스 AmTrust Lloyd's 인수
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "텐센트"), 0.9, "합작법인 파트너(중국법인)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Canopius Group Limited"), 0.88, "종속기업"),
        ],
    },
    "0c2fc4581346a06b": {  # 2024 사업보고서: 캐노피우스 M&A 추진, 해외 8개국 사업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Canopius Group Limited"), 0.88, "종속기업(영국 로이즈 손보사)"),
        ],
    },
    "1b62d206ed18ce63": {  # 2026 분기보고서: 캐노피우스 이사회 의석·주주권리 확대, 사업협력
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Canopius Group Limited"), 0.9, "종속기업(로이즈시장 5위권, 사업협력 확대)"),
        ],
    },

    # ── II. 사업의 내용: 베트남·싱가포르·유럽법인 (해외법인) ──────
    "a6e5bebd6b7a3cad": {  # 2023 사업보고서: 유럽·베트남·싱가포르 법인 보험수익/서비스비용 공시
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재 유럽법인"), 0.9, "종속기업(해외법인, 유럽)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재 베트남법인"), 0.9, "종속기업(해외법인, 베트남)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재 싱가포르법인"), 0.88, "종속기업(해외법인, 싱가포르)"),
        ],
    },
    "03f8d3758bcd692e": {  # 2025 분기보고서: 유럽·베트남·싱가포르 법인 영업규모
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재 유럽법인"), 0.9, "종속기업(해외법인, 유럽)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재 베트남법인"), 0.9, "종속기업(해외법인, 베트남)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재 싱가포르법인"), 0.88, "종속기업(해외법인, 싱가포르)"),
        ],
    },

    # ── 기타사업: 국내 종속기업 — 손해사정·보험대리점 ────────────
    "1835041357b92288": {  # 2024 사업보고서: 기타사업 손해사정(삼성화재애니카+삼성화재서비스, 24년 2,623억)
        "entities": [
            (P, "손해사정서비스", "손해사정서비스"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재애니카손해사정"), 0.92, "종속기업(손해사정서비스 운영)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재서비스손해사정"), 0.9, "종속기업(손해사정/상담서비스 운영)"),
            E("PRODUCES", ("org", CORP), ("ent", P, "손해사정서비스", "손해사정서비스"), 0.92),
        ],
    },
    "05294a24cbfde9bf": {  # 2025 분기보고서: 손해사정매출 670억(1Q25), 삼성화재애니카+삼성화재서비스
        "entities": [
            (P, "손해사정서비스", "손해사정서비스"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재애니카손해사정"), 0.92, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재서비스손해사정"), 0.9, "종속기업"),
            E("PRODUCES", ("org", CORP), ("ent", P, "손해사정서비스", "손해사정서비스"), 0.9),
        ],
    },
    "006b36c2573e96ec": {  # 2025 반기보고서: 출동서비스 6가지(비상구난·긴급견인·비상급유·배터리충전·타이어교체·잠금장치해제)
        "entities": [
            (P, "출동서비스", "출동서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "출동서비스", "출동서비스"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재애니카손해사정"), 0.9, "종속기업(출동서비스 운영)"),
        ],
    },
    "1fd02b231527ccea": {  # 2023 사업보고서: 출동서비스 6가지 분야 명시
        "entities": [
            (P, "출동서비스", "출동서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "출동서비스", "출동서비스"), 0.92),
        ],
    },

    # ── 연결감사보고서 특수관계자 채권·채무 표 (table_nl) ────────
    # 종속기업 목록 명시 청크들: 03beffbfd8db3bb9, 60b0f88cdb467445, 3fd24efcf154d988
    "03beffbfd8db3bb9": {  # 표: 종속기업(삼성화재서비스, 삼성화재애니카, 삼성화재금융서비스, 삼성화재인도네시아법인)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재서비스손해사정"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재애니카손해사정"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재금융서비스보험대리점"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재 인도네시아법인"), 0.9, "종속기업"),
        ],
    },
    "60b0f88cdb467445": {  # 표(감사보고서): 종속기업 동일
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재서비스손해사정"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재애니카손해사정"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재금융서비스보험대리점"), 0.95, "종속기업"),
        ],
    },
    "3fd24efcf154d988": {  # 표(재무제표주석): 종속기업(전기)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재서비스손해사정"), 0.93, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재애니카손해사정"), 0.93, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재금융서비스보험대리점"), 0.93, "종속기업"),
        ],
    },

    # ── 연결재무제표주석 특수관계자 거래 표 (table_nl) ───────────
    # 관계기업: 삼성재산보험(중국), Petrolimex Insurance Corporation, 신공항하이웨이, Fortuna Topco
    "15c646c375900924": {  # 연결재무제표주석 관계기업: 삼성재산보험(중국)/Petrolimex/Fortuna Topco/삼성전자(그 밖)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성재산보험(중국)유한공사"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Petrolimex Insurance Corporation"), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Fortuna Topco Limited"), 0.9, "관계기업(캐노피우스 지주)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.88, "그 밖의 특수관계자(삼성그룹 계열)"),
        ],
    },
    "4ac024506302fcec": {  # 연결재무제표주석: 관계기업 채권채무(전기)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성재산보험(중국)유한공사"), 0.92, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Petrolimex Insurance Corporation"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Fortuna Topco Limited"), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.87, "그 밖의 특수관계자"),
        ],
    },
    "20548497ed264b11": {  # 연결감사보고서: 관계기업+그밖(삼성전자·삼성디스플레이·삼성SRA 등)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Fortuna Topco Limited"), 0.9, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.88, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성디스플레이"), 0.85, "그 밖의 특수관계자"),
        ],
    },
    "6aa252df3bc7df70": {  # 연결감사보고서 거래: 삼성재산보험(중국)/신공항하이웨이/Petrolimex/Fortuna Topco 보험료 수수
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성재산보험(중국)유한공사"), 0.93, "관계기업(보험료 수수)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "신공항하이웨이"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Petrolimex Insurance Corporation"), 0.88, "관계기업(보험료 수수)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Fortuna Topco Limited"), 0.9, "관계기업"),
        ],
    },

    # ── 연결감사보고서 — 삼성생명 최대주주 관계 ────────────────────
    "8ee8d41791e9fae9": {  # 최대주주: 삼성생명보험(주) 7,099,088주(14.98%) 보유
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.95, "그 밖의 특수관계자(최대주주, 14.98%)"),
        ],
    },
    "aa46b9411667a8a0": {  # 연결재무제표주석: 삼성생명보험 최대주주
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.95, "그 밖의 특수관계자(최대주주, 14.98%)"),
        ],
    },
    "1f2ded26ed01f21a": {  # 2024 사업보고서: 삼성생명 최대주주
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.95, "그 밖의 특수관계자(최대주주)"),
        ],
    },
    "392a0cf0c6ff3810": {  # 2024 사업보고서 연결재무제표주석: 삼성생명보험 최대주주
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.95, "그 밖의 특수관계자(최대주주)"),
        ],
    },

    # ── 재무제표주석 특수관계자 목록표 — 종속기업 지분율 포함 ──────
    "694396eb606dbb72": {  # 재무제표주석: 종속기업 지분율 100%목록(삼성화재서비스, 애니카, 금융서비스보험대리점 등)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재서비스손해사정"), 0.95, "종속기업(지분율 100%)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재애니카손해사정"), 0.95, "종속기업(지분율 100%)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재금융서비스보험대리점"), 0.95, "종속기업(보험대리업)"),
        ],
    },

    # ── 연결재무제표주석 특수관계자 자금거래표 ─────────────────────
    "699d8e39645a11fd": {  # 연결감사보고서: 관계기업 신공항하이웨이 자금회수 거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "신공항하이웨이"), 0.88, "관계기업(자금거래)"),
        ],
    },

    # ── II. 사업의 내용: 핵심 경쟁력 기술 (2025 reports) ──────────
    "019189bb3afd509f": {  # 2025 사업보고서: 손해보험 경쟁력 — 데이터축적·분석 역량
        "entities": [
            (T, "빅데이터 보험료산출", "빅데이터 기반 보험료 산출"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "빅데이터 보험료산출", "빅데이터 기반 보험료 산출"), 0.85),
        ],
    },
    "0678df5b7951543e": {  # 분기보고서(2024.03): 손해보험사 경쟁력 요인 — 데이터/Risk/자산운용
        "entities": [
            (T, "빅데이터 보험료산출", "빅데이터 기반 보험료 산출"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "빅데이터 보험료산출", "빅데이터 기반 보험료 산출"), 0.83),
        ],
    },

    # ── IV. 이사의 경영진단: 헬스케어·데이터기반 신사업 ──────────
    "d3a9521856f01664": {  # 2023 사업보고서 IV: Canopius사 경제적 시너지, 데이터기반 사업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Canopius Group Limited"), 0.88, "종속기업(경제적 시너지)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "텐센트"), 0.87, "합작법인 파트너"),
        ],
    },

    # ── II 해외사업: Petrolimex Insurance Corporation (베트남 관계기업) ──
    "0b98502ec22ebe05": {  # 2024 분기보고서 II: 해외사업 8개국 — 한국계시장·글로벌영업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Petrolimex Insurance Corporation"), 0.85, "관계기업(베트남)"),
        ],
    },
    "10e64b15ecd12b33": {  # 2023 사업보고서 II: 해외사업 8개국 — 한국계시장 글로벌영업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Canopius Group Limited"), 0.87, "종속기업"),
        ],
    },
    "0b98502ec22ebe05": {  # 분기보고서 II 해외사업 경쟁력: 관계사+한국계시장
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Canopius Group Limited"), 0.87, "종속기업"),
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
    print("=== 삼성화재해상보험 Stage5 추출 결과 ===")
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
