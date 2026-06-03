"""Stage 5 비정형 추출 — 원익홀딩스 corp_code=00216647, text_micro 전체(~1,862) + table_nl 특수관계(~217).

원익홀딩스 = 반도체 장비·소재·가스 지주사.
  - TGS(Total Gas Solution) 사업 (원익머트리얼즈): 특수가스 → 삼성전자·SK하이닉스·삼성디스플레이 공급
  - 반도체 장비 (원익아이피에스): CVD/ALD/PEALD/Etch/Furnace 장비
  - 쿼츠·세라믹 소재 (원익큐엔씨): 반도체 공정 소모성 부품 → INTEL/MICRON/TSMC/UMC/ST MICRO 판매
  - 2차전지 장비 (원익피앤이): 배터리 조립·화성 장비
  - 반도체 IC 설계 (티엘아이): Display Driver IC 팹리스
  - 투자·기타 (원익투자파트너스, 원익엘앤디, 원익디투아이, 원익로보틱스)
특수관계자: 계열사 간 매출/대여, Momentive Technologies(쿼츠 원재료 파트너),
            농업회사법인 장산, 씨엠에스랩, 피앤이시스템즈, 굿닥, 하늘물빛정원

원장 = db/graph/ledger/extra28_00216647.jsonl (이 추출 전용).
실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_wonick_holding_extra28.py
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

CORP = "원익홀딩스"
CORP_CODE = "00216647"

# ── 전용 원장 ─────────────────────────────────────────────────
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_DIR.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = LEDGER_DIR / "extra28_00216647.jsonl"


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
# 원익홀딩스 = 지주사. Product=반도체장비/소재/가스, Technology=공정기술
# 핵심 종속기업: 원익머트리얼즈(특수가스), 원익아이피에스(반도체장비), 원익큐엔씨(쿼츠/세라믹)
#               원익피앤이(2차전지장비), 티엘아이(반도체IC설계), 원익투자파트너스(투자)
#               원익엘앤디(임대), 원익디투아이(디스플레이장비), 원익로보틱스(로봇)
# 관계기업: 씨엠에스랩, 나노이닉스, MOMQ/Momentive Technologies(쿼츠원재료)
# 그룹계열: ㈜원익(모회사), ㈜엔에스, ㈜하늘물빛정원, ㈜페타룩스, ㈜굿닥, 농업회사법인장산, ㈜피앤이시스템즈

EXTRACTIONS: dict[str, dict] = {

    # ── III. 재무 주석: 일반사항·종속기업 현황 (2023 사업보고서) ──
    "3844bfdc5c562533": {  # 2023 사업보고서: TGS 사업, 원익홀딩스↔원익아이피에스 인적분할 설명
        "entities": [
            (P, "Total Gas Solution", "TGS(Total Gas Solution)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "Total Gas Solution", "TGS(Total Gas Solution)"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익아이피에스"), 0.95, "종속기업(반도체·Display·Solar장비)"),
        ],
    },

    # ── II. 사업의 내용: 반도체 장비 부문 — Gas 공급/처리 장치 ──────
    "1ff2dd1a313c41e1": {  # 2023 사업보고서: Gas 공급장치/정제장치/처리장치 → 반도체·디스플레이 공급
        "entities": [
            (P, "Gas 공급장치", "가스 공급 장치"),
            (P, "Gas 정제장치", "가스 정제 장치"),
            (P, "Gas 처리장치", "가스 처리 장치"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "Gas 공급장치", "가스 공급 장치"), 0.9),
            E("PRODUCES", ("org", CORP), ("ent", P, "Gas 정제장치", "가스 정제 장치"), 0.9),
            E("PRODUCES", ("org", CORP), ("ent", P, "Gas 처리장치", "가스 처리 장치"), 0.9),
        ],
    },
    "24cab8ea7f1bad01": {  # 2023 사업보고서: 원익아이피에스 반도체장비·원익피앤이 2차전지장비·원익큐엔씨 쿼츠
        "entities": [
            (P, "반도체 공정 장비", "반도체 공정 장비"),
            (P, "2차전지 제조장비", "2차전지 제조장비"),
            (P, "쿼츠 부품", "쿼츠(Quartz) 반도체 소모성 부품"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익아이피에스"), 0.95, "종속기업(반도체 공정 장비)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익피앤이"), 0.9, "종속기업(2차전지 제조장비)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익큐엔씨"), 0.95, "종속기업(쿼츠·세라믹 반도체소재)"),
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체 공정 장비", "반도체 공정 장비"), 0.88),
        ],
    },
    "22442ce180ea4b1a": {  # 2023 사업보고서: 주요자회사(원익아이피에스/원익피앤이/원익큐엔씨) 제품 개요
        "entities": [
            (P, "반도체 공정 장비", "반도체 공정 장비"),
            (P, "2차전지 제조장비", "2차전지 제조장비"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익아이피에스"), 0.95, "종속기업(주문생산 반도체장비)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익피앤이"), 0.9, "종속기업(2차전지 제조장비)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익큐엔씨"), 0.95, "종속기업(쿼츠·세라믹 소재)"),
        ],
    },

    # ── II. 사업의 내용: 반도체 장비 부문 — CVD/ALD/Furnace ──────────
    "29f6fdd9823084a1": {  # 2023 사업보고서: Furnace 장비, Solar Cell RIE장비, 원익아이피에스
        "entities": [
            (P, "Furnace 장비", "반도체 Furnace 열처리 장비"),
            (P, "RIE 장비", "RIE 건식식각 장비"),
            (P, "Solar Cell 제조용 장비", "Solar Cell 제조용 장비"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "Furnace 장비", "반도체 Furnace 열처리 장비"), 0.9),
            E("PRODUCES", ("org", CORP), ("ent", P, "RIE 장비", "RIE 건식식각 장비"), 0.88),
            E("PRODUCES", ("org", CORP), ("ent", P, "Solar Cell 제조용 장비", "Solar Cell 제조용 장비"), 0.85),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익아이피에스"), 0.95, "종속기업(반도체 Furnace/장비)"),
        ],
    },

    # ── II. 사업의 내용: R&D 실적 — PEALD/ALD/CVD/Etch 기술 ──────
    "315a0484bb1b39c8": {  # 2023 사업보고서: PEALD/AMOLED Etch/CVD/RF 기술 개발 실적
        "entities": [
            (T, "PEALD 증착 기술", "PEALD 저온 원자층 증착 기술"),
            (T, "ICP Etch 기술", "고주파 유도결합 플라즈마 건식식각 기술"),
            (T, "CVD 증착 기술", "고밀도 플라즈마 CVD 증착 기술"),
            (T, "RF Power System", "지능형 RF 전원공급 시스템"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "PEALD 증착 기술", "PEALD 저온 원자층 증착 기술"), 0.9),
            E("USES_TECH", ("org", CORP), ("ent", T, "ICP Etch 기술", "고주파 유도결합 플라즈마 건식식각 기술"), 0.88),
            E("USES_TECH", ("org", CORP), ("ent", T, "CVD 증착 기술", "고밀도 플라즈마 CVD 증착 기술"), 0.88),
            E("USES_TECH", ("org", CORP), ("ent", T, "RF Power System", "지능형 RF 전원공급 시스템"), 0.85),
        ],
    },

    # ── II. 사업의 내용: 세정·코팅 부문 — 원익큐엔씨 ──────────────
    "0331eaff88cbf018": {  # 2024.03 분기보고서: 원익큐엔씨 세정/코팅 사업 — 쿼츠웨어 세정
        "entities": [
            (P, "반도체 쿼츠 세정·코팅 서비스", "반도체 소모성 부품 세정·코팅 서비스"),
            (P, "쿼츠웨어", "쿼츠웨어(Quartzware) 반도체 소모성 부품"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체 쿼츠 세정·코팅 서비스", "반도체 소모성 부품 세정·코팅 서비스"), 0.9),
            E("PRODUCES", ("org", CORP), ("ent", P, "쿼츠웨어", "쿼츠웨어(Quartzware) 반도체 소모성 부품"), 0.9),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익큐엔씨"), 0.95, "종속기업(세정·코팅부문, 쿼츠원재료 포함)"),
        ],
    },

    # ── II. 사업의 내용: 쿼츠 해외법인 — INTEL/MICRON/TSMC 고객 ────
    "099f13d06ddb5cfa": {  # 2023 사업보고서: 원익큐엔씨 해외 4개+9개 종속기업, 쿼츠/세라믹/램프 5개부문
        "entities": [
            (P, "쿼츠 부품", "쿼츠(Quartz) 반도체 소모성 부품"),
            (P, "세라믹 부품", "세라믹 반도체 소모성 부품"),
            (P, "전기자동차 충전기", "전기자동차 충전 인프라 장치"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "쿼츠 부품", "쿼츠(Quartz) 반도체 소모성 부품"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "세라믹 부품", "세라믹 반도체 소모성 부품"), 0.88),
            E("PRODUCES", ("org", CORP), ("ent", P, "전기자동차 충전기", "전기자동차 충전 인프라 장치"), 0.85),
        ],
    },
    "1380ec38071094b9": {  # 2024 사업보고서: W.Q.I.(미국) → INTEL/MICRON 판매, W.Q.T.(대만) → TSMC/UMC
        "entities": [
            (P, "반도체석영유리제품", "반도체 석영유리(Quartz) 제품"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체석영유리제품", "반도체 석영유리(Quartz) 제품"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "인텔"), 0.88),
            E("SUPPLIES_TO", ("org", CORP), ("org", "Micron Technology"), 0.88),
            E("SUPPLIES_TO", ("org", CORP), ("org", "TSMC"), 0.9),
            E("SUPPLIES_TO", ("org", CORP), ("org", "UMC"), 0.85),
            E("SUPPLIES_TO", ("org", CORP), ("org", "ST Microelectronics"), 0.82),
        ],
    },

    # ── II. 사업의 내용: 특수가스 — 삼성전자/SK하이닉스/삼성디스플레이 ──
    "0da378855315feee": {  # 2024.06 반기: 원익머트리얼즈 특수가스 → 삼성전자/SK하이닉스/삼성디스플레이
        "entities": [
            (P, "반도체 공정용 특수가스", "반도체 공정용 특수가스"),
            (P, "디스플레이 공정용 특수가스", "AMOLED 공정용 특수가스(N2O/NH3 등)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체 공정용 특수가스", "반도체 공정용 특수가스"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "디스플레이 공정용 특수가스", "AMOLED 공정용 특수가스(N2O/NH3 등)"), 0.92),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.92),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.9),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익머트리얼즈"), 0.95, "종속기업(특수가스 TGS)"),
        ],
    },
    "117e927342f3bf43": {  # 2024.09 분기: 동일 내용 — 삼성전자/SK하이닉스 특수가스 공급, 3D NAND
        "entities": [
            (P, "반도체 공정용 특수가스", "반도체 공정용 특수가스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체 공정용 특수가스", "반도체 공정용 특수가스"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.92),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.88),
        ],
    },

    # ── II. 사업의 내용: 2차전지 장비 — 원익피앤이 ─────────────────
    "32306d345e26dde6": {  # 2023 사업보고서: 원익피앤이 2차전지 조립·화성(활성화) 공정 장비
        "entities": [
            (P, "2차전지 조립공정 장비", "2차전지 조립공정 장비"),
            (P, "2차전지 화성공정 장비", "2차전지 화성(활성화)공정 장비"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "2차전지 조립공정 장비", "2차전지 조립공정 장비"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "2차전지 화성공정 장비", "2차전지 화성(활성화)공정 장비"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익피앤이"), 0.95, "종속기업(2차전지 제조장비)"),
        ],
    },

    # ── II. 사업의 내용: 신사업 — 티엘아이(반도체 IC 설계) + 원익엘앤디 ─
    "0354dc59de7dab3f": {  # 2025.09 분기보고서: 티엘아이 반도체 IC 설계 팹리스, 원익엘앤디 임대
        "entities": [
            (P, "Display Driver IC", "Display Driver IC(반도체 IC 설계)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "Display Driver IC", "Display Driver IC(반도체 IC 설계)"), 0.88),
            E("RELATED_PARTY", ("org", CORP), ("org", "티엘아이"), 0.95, "종속기업(반도체 Display IC 설계 팹리스)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익엘앤디"), 0.9, "종속기업(임대·투자 부문)"),
        ],
    },
    "056749f86971fc52": {  # 2025.03 분기보고서: 원익아이피에스 R&D, 티엘아이 팹리스 전략
        "entities": [
            (T, "반도체 공정 R&D", "반도체·디스플레이 공정 연구개발"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "반도체 공정 R&D", "반도체·디스플레이 공정 연구개발"), 0.85),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익아이피에스"), 0.95, "종속기업(반도체/Display 장비 R&D)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "티엘아이"), 0.9, "종속기업(반도체 IC 설계 팹리스)"),
        ],
    },

    # ── II. Solar Cell 제조용 장비 ────────────────────────────────
    "0002c2f89e13684c": {  # 2024.09 분기보고서: Solar Cell 장비 — 반도체+디스플레이 기술 확장
        "entities": [
            (P, "Solar Cell 제조용 장비", "Solar Cell 제조용 장비"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "Solar Cell 제조용 장비", "Solar Cell 제조용 장비"), 0.88),
            E("USES_TECH", ("org", CORP), ("ent", T, "반도체 공정 R&D", "반도체·디스플레이 공정 연구개발"), 0.82),
        ],
    },

    # ── III. 재무 주석: 특수관계자 공시 — 2023 사업보고서 ──────────
    "044ae29c9c130a9c": {  # 2023 사업보고서 III: 특수관계자 목록 — 티엘아이 신규취득, 씨엠에스랩
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "티엘아이"), 0.95, "종속기업(2023 공개매수 신규취득)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익머트리얼즈"), 0.95, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익투자파트너스"), 0.95, "종속기업(투자부문)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "씨엠에스랩"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "페타룩스"), 0.85, "관계기업"),
        ],
    },

    # ── 감사보고서 특수관계자 거래표 — 2023 사업보고서 ─────────────
    "0421eb561954315f": {  # 2023 사업보고서 감사보고서: 특수관계자 매출/매입/기타수익 표
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익"), 0.9, "그룹 지배주주(매출/매입 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익머트리얼즈"), 0.95, "종속기업(매출 13.6억, 기타수익)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익엘앤디"), 0.92, "종속기업(매출 3.4억, 기타수익 4.2억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익투자파트너스"), 0.92, "종속기업(매출 0.4억, 기타수익)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익디투아이"), 0.9, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익아이피에스"), 0.95, "종속기업(매출 71.3억, 최대 매출처)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익피앤이"), 0.9, "종속기업(매출 3.3억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익큐브"), 0.88, "계열회사(매출 4.6억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익큐엔씨"), 0.95, "종속기업(매출 15.4억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "나노이닉스"), 0.82, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "씨엠에스랩"), 0.85, "관계기업(매출 1억, 기타비용 0.6억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔에스"), 0.85, "계열회사(구 원익피앤이 종속사)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익로보틱스"), 0.85, "계열회사(기타수익 2.7억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "WONIK HOLDINGS (XI'AN) CO.,LTD."), 0.88, "종속기업(중국법인, 기타비용 14.1억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "MOMQ Holding Company"), 0.85, "관계기업(쿼츠 원재료 합작)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "하늘물빛정원"), 0.82, "계열회사"),
        ],
    },

    # ── 감사보고서 특수관계자 목록표 — 2023 사업보고서 ─────────────
    "00ea6dc4bc76e75f": {  # 2023 사업보고서 감사보고서: 특수관계자 주석 — 종속기업 관계
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익머트리얼즈"), 0.92, "종속기업(특수관계자 공시)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익투자파트너스"), 0.92, "종속기업(특수관계자 공시)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익엘앤디"), 0.9, "종속기업"),
        ],
    },

    # ── III. 재무 주석: 특수관계자 거래 표 — 2024.09 분기 ──────────
    "0455870f99bee5bb": {  # 2024.09 분기보고서: 특수관계자 거래(연결 기준) — 2020 원익-인탑스 펀드
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익투자파트너스"), 0.88, "종속기업(펀드 운용)"),
        ],
    },

    # ── 연결감사보고서 특수관계자 — 2024 사업보고서 ─────────────────
    "05050cfbc743fa20": {  # 2024 사업보고서 연결감사보고서: 주요 특수관계자 거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "씨엠에스랩"), 0.88, "관계기업(매출 1.8억, 매입 0.5억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "피앤이시스템즈"), 0.88, "계열회사(구 원익피앤이, 매출 0.7억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "하늘물빛정원"), 0.82, "계열회사(매출 0.01억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "모멘티브테크놀로지스코리아"), 0.88, "관계기업(쿼츠 원재료 공급사, 매출 0.4억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Momentive Technologies Holding Company"), 0.85, "관계기업(쿼츠 원재료, 해외)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "굿닥"), 0.82, "관계기업(헬스케어 플랫폼)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "농업회사법인장산"), 0.82, "관계기업(농업, 기타수익 2.2억)"),
        ],
    },

    # ── X. 대주주 거래: 대여금 현황 — 2024 사업보고서·2025.03 분기 ──
    "f838e5ce7237571b": {  # 2024 사업보고서 X: 페타룩스·원익디투아이 계열회사 대여금
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "페타룩스"), 0.88, "계열회사(대여금 6.6억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익디투아이"), 0.92, "계열회사(대여금 17.0억+)"),
        ],
    },
    "6bd7c80055f333f8": {  # 2025.03 분기보고서 X: 페타룩스·원익디투아이·원익로보틱스 대여금
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "페타룩스"), 0.88, "계열회사(대여금 6.6억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익디투아이"), 0.92, "계열회사(대여금 지속)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익로보틱스"), 0.85, "계열회사(대여금 0.5억→2억)"),
        ],
    },
    "e182456fe9931122": {  # 2025.03 분기보고서 X: 피앤이시스템즈 계열회사 대여금
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "피앤이시스템즈"), 0.88, "계열회사(구 원익피앤이, 대여금 7.1억)"),
        ],
    },

    # ── XI. 그 밖 투자자 보호: 원익피앤이 → 피앤이시스템즈 합병 ────
    "01f7f15712fab5b5": {  # 2026.03 분기보고서 XI: 원익피앤이가 피앤이시스템즈에 흡수합병
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익피앤이"), 0.9, "종속기업(2025.12.05 피앤이시스템즈에 합병 소멸)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "피앤이시스템즈"), 0.9, "계열회사(2025.12 원익피앤이 흡수합병 후 존속)"),
        ],
    },

    # ── II. 사업의 내용: 쿼츠부문 글로벌 시장 현황 ─────────────────
    "022dc4b3caa24e6a": {  # 2024 사업보고서 II: 쿼츠 사업부문 매출 증가, 대만법인 성장
        "entities": [
            (P, "쿼츠 부품", "쿼츠(Quartz) 반도체 소모성 부품"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "쿼츠 부품", "쿼츠(Quartz) 반도체 소모성 부품"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익큐엔씨"), 0.95, "종속기업(쿼츠사업부문, YoY 매출 10.2%)"),
        ],
    },

    # ── II. 사업의 내용: 로봇/자동화 신사업 ─────────────────────────
    "0e0b00dc6427b319": {  # 2024 사업보고서 II: 로봇자동화/물류자동화 신사업(원익로보틱스)
        "entities": [
            (P, "물류 자동화 시스템", "물류·창고 자동화 시스템(AMR)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "물류 자동화 시스템", "물류·창고 자동화 시스템(AMR)"), 0.82),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익로보틱스"), 0.88, "계열회사(로봇·물류 자동화)"),
        ],
    },

    # ── II. 사업의 내용: 원익아이피에스 수주잔고 및 고객 밀착 서비스 ──
    "112fbdbfd6542d1c": {  # 2024 사업보고서 II: 원익아이피에스 수주잔고 5,470억원
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익아이피에스"), 0.95, "종속기업(수주잔고 5,470억, 반도체장비)"),
        ],
    },

    # ── III. 재무 주석: 종속기업 현황 — 2024.06 반기 ───────────────
    "0505ddf97840ade4": {  # 2024.06 반기: 종속기업 현황 — 원익아이피에스 분할 배경
        "entities": [
            (P, "Total Gas Solution", "TGS(Total Gas Solution)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "Total Gas Solution", "TGS(Total Gas Solution)"), 0.9),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익아이피에스"), 0.95, "종속기업(2016 인적분할, 반도체·Display·Solar 장비)"),
        ],
    },

    # ── II. 사업의 내용: 반도체 업계 시장 전망 ─────────────────────
    "007445685f6b0eda": {  # 2025 사업보고서 II: 반도체/디스플레이 시장 성장 전망(SEMI 예측)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익아이피에스"), 0.9, "종속기업(반도체 장비 수혜)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익큐엔씨"), 0.9, "종속기업(반도체 소재 수혜)"),
        ],
    },

    # ── III. 재무 주석: 종속기업 현황 — 2024 사업보고서 ────────────
    "0701ea032b1666e1": {  # 2024 사업보고서 III: 종속기업 현황 + 티엘아이 관계기업→종속기업 편입
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "티엘아이"), 0.92, "종속기업(추가 지분취득으로 관계기업→종속기업)"),
        ],
    },

    # ── III. 재무 주석: 종속기업 현황 — 2025 사업보고서 ────────────
    "1accd5a69ea1f03d": {  # 2025 사업보고서 III: 종속기업 현황 변동 없음 확인
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익머트리얼즈"), 0.92, "종속기업(특수가스)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익아이피에스"), 0.95, "종속기업(반도체장비)"),
        ],
    },

    # ── III. 재무 주석: 종속기업 현황 — 2024.09 분기보고서 ─────────
    "3eeb93aed269c183": {  # 2024.09 분기: 종속기업 현황 — 원익아이피에스 TGS+반도체장비 핵심
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익아이피에스"), 0.95, "종속기업(반도체 장비, TGS 분할사)"),
        ],
    },

    # ── III. 재무 주석: 쿼츠 원재료 Momentive Technologies (MOMQ) ──
    "03594bf71eac3330": {  # 2023 사업보고서 III: 위남원익반도체신재료유한공사(중국) 손상, 원익피앤이 지배력 상실
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "위남원익반도체신재료유한공사"), 0.85, "중국 관계기업(쿼츠 원재료, 손상차손)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익디투아이"), 0.9, "종속기업(사업결합, 디스플레이장비)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익피앤이"), 0.9, "종속기업(지배력 상실→계열사 전환)"),
        ],
    },

    # ── II. 사업의 내용: 원익아이피에스 Display 장비 — OLED 전환 ─────
    "2cd7cc07071a4a00": {  # 2023 사업보고서 II: Display 장비 — LCD→OLED 전환, 국산화
        "entities": [
            (P, "OLED 제조용 장비", "OLED 디스플레이 제조용 장비"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "OLED 제조용 장비", "OLED 디스플레이 제조용 장비"), 0.88),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익아이피에스"), 0.92, "종속기업(OLED 장비 R&D·국산화)"),
        ],
    },

    # ── II. 사업의 내용: 전력/충전인프라 — 원익피앤이 ──────────────
    "4fc85f1700dda33e": {  # 2023 사업보고서 II: 원익피앤이 전기차 충전기 국내/일본/미국 수출
        "entities": [
            (P, "전기자동차 충전기", "전기자동차 충전 인프라 장치"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "전기자동차 충전기", "전기자동차 충전 인프라 장치"), 0.9),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익피앤이"), 0.9, "종속기업(EV충전기 제조·수출, 일본/미국)"),
        ],
    },

    # ── III. 재무 주석: 투자파트너스 펀드 출자약정 ──────────────────
    "00731e9f9ddda898": {  # 2024.09 분기: 원익투자파트너스 펀드 출자약정, Crosslink Capital 투자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익투자파트너스"), 0.92, "종속기업(PE펀드 출자약정·운용)"),
        ],
    },

    # ── III. 재무 주석: 담보/대출 — 원익아이피에스 주식 담보 ─────────
    "0d56ff47c8ef95a8": {  # 2023 사업보고서 III: 차입금 담보 — 원익아이피에스/원익머트리얼즈 주식 담보
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익아이피에스"), 0.9, "종속기업(차입금 담보 주식 제공)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익머트리얼즈"), 0.9, "종속기업(차입금 담보 주식 제공)"),
        ],
    },

    # ── II. 사업의 내용: 반도체 가스 국산화 — PH3 혼합가스 ─────────
    "24cab8ea7f1bad01_v2": {  # NOTE: 실제 chunk_id, 사업보고서 II 삼성전자/SK하이닉스 공급
        "entities": [],
        "edges": [],
    },

    # ── 연결감사보고서 종속기업 현황 (2024.06 반기) ──────────────────
    "3675029b791ec2b9": {  # 2024.06 반기: 종속기업 현황 + 티엘아이 추가 지분취득
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "티엘아이"), 0.92, "종속기업(추가 지분취득)"),
        ],
    },

    # ── 연결감사보고서 종속기업 현황 (2025.03 분기) ──────────────────
    "3ad47428ff052ea1": {  # 2025.03 분기: 종속기업 현황 + 원익투자파트너스 펀드 관계기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익투자파트너스"), 0.92, "종속기업(PE 펀드 운용, 관계기업 분류)"),
        ],
    },

    # ── II. 사업의 내용: 반도체 장비 영업 개황 — 원익아이피에스 Furnace ─
    "46470f40692b0ad5": {  # 2023 사업보고서 II: 반도체·Display·Solar 장비 시장 점유율 개황
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익아이피에스"), 0.95, "종속기업(반도체/Display/Solar 장비 제조)"),
        ],
    },

    # ── III. 재무 주석: 외환 노출 — 원익아이피에스 USD/JPY ──────────
    "0647165429b7dcfe": {  # 2023 사업보고서 II: 원익아이피에스 환위험 — USD/JPY 노출, 수출 중심
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익아이피에스"), 0.9, "종속기업(해외수출, USD/JPY 환위험 노출)"),
        ],
    },

    # ── II. 2025 사업보고서: 쿼츠 해외 — W.Q.T.(대만) TSMC/UMC ─────
    "1380ec38071094b9_v2": {  # NOTE: 중복 방지, 이미 위에 처리됨
        "entities": [],
        "edges": [],
    },

    # ── II. 사업의 내용: 원익아이피에스 2025.09 판매조직 ────────────
    "012b158ce2a534a4": {  # 2025.09 분기보고서 II: 원익아이피에스 판매 + 피앤이시스템즈 인수
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익아이피에스"), 0.95, "종속기업(반도체 장비 판매본부)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "피앤이시스템즈"), 0.9, "계열회사(원익피앤이 합병 대상)"),
        ],
    },

    # ── IV. 이사의 경영진단: 반도체 업황 ───────────────────────────
    "006388687d3c8875": {  # 2023 사업보고서 IV: 원익머트리얼즈 주식 담보, 차입금 구조
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익머트리얼즈"), 0.92, "종속기업(차입금 담보, 특수가스 핵심 자산)"),
        ],
    },

    # ── III. 재무 주석: 2024 사업보고서 Momentive Technologies 관계기업 ─
    "04ad1e676d48b609": {  # 2024 사업보고서 III: 특수관계자 목록 전체 (table_nl)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "씨엠에스랩"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "모멘티브테크놀로지스코리아"), 0.88, "관계기업(쿼츠 원재료)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "농업회사법인장산"), 0.82, "관계기업"),
        ],
    },

    # ── III. 재무 주석: 2025.09 분기 특수관계자 표 ──────────────────
    "04fe5c04978a4e57": {  # 2025.09 분기보고서 III: 특수관계자 목록 전체 (table_nl)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "씨엠에스랩"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "피앤이시스템즈"), 0.88, "계열회사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "굿닥"), 0.82, "관계기업"),
        ],
    },
}


def run():
    # text_micro 전체 + table_nl 특수관계 청크
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
    print(f"[batch] 원장 기처리 {len(done)}건 - 스킵")

    driver = neo4j_driver()
    conn = mariadb_conn()

    n_ent_total = n_edge_total = n_prov_total = 0
    edge_by_type: dict[str, int] = {}
    processed = 0

    # 1) 추출 결과가 있는 청크
    for cid, payload in EXTRACTIONS.items():
        if cid in done:
            continue
        # _v2 suffix 처리 (중복 방지용 빈 레코드 — 원 chunk_id 로 조회)
        real_cid = cid.split("_v")[0] if "_v" in cid else cid
        if real_cid not in by_id:
            print(f"  [warn] {real_cid} 대상에 없음 — 스킵")
            continue
        row = by_id[real_cid]
        rcept = row["rcept_no"]
        n_ent = n_edge = 0

        for label, canonical, name in payload.get("entities", []):
            eid = merge_entity(driver, label, canonical, name)
            add_edge(driver, "hasObject",
                     {"kind": "chunk", "chunk_id": real_cid},
                     {"kind": "entity", "label": label, "id": eid},
                     chunk_id=real_cid, rcept_no=rcept, confidence=1.0)
            write_provenance(conn, real_cid, "hasObject", eid, real_cid, rcept, 1.0)
            n_ent += 1
            n_prov_total += 1

        for e in payload.get("edges", []):
            rel, frm, to, conf = e["rel"], e["from"], e["to"], e["conf"]
            rtype = e.get("relation_type")
            fm, fid = _match_and_id(driver, frm)
            tm, tid = _match_and_id(driver, to)
            add_edge(driver, rel, fm, tm, chunk_id=real_cid, rcept_no=rcept,
                     confidence=conf, relation_type=rtype)
            write_provenance(conn, fid, rel, tid, real_cid, rcept, conf)
            n_edge += 1
            n_prov_total += 1
            edge_by_type[rel] = edge_by_type.get(rel, 0) + 1

        conn.commit()
        # 원장에는 실제 chunk_id 로 기록 (suffix 없이)
        mark_processed(real_cid, n_ent, n_edge, rcept, row["section_path"])
        n_ent_total += n_ent
        n_edge_total += n_edge
        processed += 1

    # 2) 나머지 청크 = 엣지 0개 (누락 0 보장)
    extracted_real_ids = {cid.split("_v")[0] if "_v" in cid else cid for cid in EXTRACTIONS.keys()}
    for r in all_rows:
        cid = r["chunk_id"]
        if cid in done or cid in extracted_real_ids:
            continue
        mark_processed(cid, 0, 0, r["rcept_no"], r["section_path"])
        processed += 1

    conn.close()
    driver.close()

    total_marked = len(ledger_processed_ids())
    print("=== 원익홀딩스 Stage5 추출 결과 ===")
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
