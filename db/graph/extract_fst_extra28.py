"""Stage 5 비정형 추출 — 에프에스티 corp_code=00223434, text_micro 전체(~1,160) + table_nl 특수관계.

에프에스티(FST) = 반도체·FPD 소재/장비 전문업체.
주력제품: 반도체 펠리클(Pellicle) + 온도조절기(칠러, Chiller/TCU)
사업구조:
  - 펠리클사업부: 반도체/FPD용 포토마스크 보호막
  - TCU사업부: 반도체·디스플레이 챔버 온도조절 장비
  - EUV Pellicle: 차세대 EUV 노광공정 펠리클 개발 중
종속기업: (주)에스피텍(EUV 프레임·도금), (주)화인세라텍(Probe Card·세라믹),
          (주)에프엑스티(CVD-SiC 소재), (주)아이엠디(전극 Paste),
          XIAN FST, WUXI FST, FINE SEMITECH USA CORP
관계기업: (주)오로스테크놀로지, (주)시옷플랫폼, (주)이솔, Advanced Semiconductor Products
주요 고객/주주: 삼성전자(주) — 매출 80~90% 공급처 / 주요주주
특수관계법인: (주)시엠테크놀로지 — 주요 매입처(연 8,000~9,000백만원)
기타 특수관계자: (주)탐스, (주)페넌트인베스트먼트, (주)파워팩터스, (주)피에스플라즈마

원장 = db/graph/ledger/extra28_00223434.jsonl (이 추출 전용).
실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_fst_extra28.py
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

CORP = "에프에스티"
CORP_CODE = "00223434"

# 전용 원장
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_DIR.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = LEDGER_DIR / "extra28_00223434.jsonl"


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
# FST = 반도체 소재/장비 전문사.
# Product: 반도체펠리클, FPD펠리클, 칠러(온도조절기), EUV 펠리클, CVD-SiC 소재, Probe Card
# Technology: EUV lithography, 극저온칠러기술, CVD-SiC 공정
# 핵심 매출처: 삼성전자 (SUPPLIES_TO 에프에스티→삼성전자)
# 특수관계: 시엠테크놀로지(매입처), 오로스테크놀로지/시옷플랫폼/이솔(관계기업)

EXTRACTIONS: dict[str, dict] = {

    # ═══ 일반사항: 회사 개요 ═══

    "0deca6aa13bf91b0": {  # 2023 사업보고서 재무제표주석: 에프에스티 설립, 반도체 FPD 생산용 Pellicle·Chiller 제조판매
        "entities": [
            (P, "반도체펠리클", "반도체 펠리클(Pellicle)"),
            (P, "칠러", "칠러(Chiller/온도조절기)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체펠리클", "반도체 펠리클(Pellicle)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "칠러", "칠러(Chiller/온도조절기)"), 0.97),
        ],
    },
    "0e17c22c35e0ceb1": {  # 2025.09 분기보고서 연결재무제표주석: 에프에스티 + 에스피텍 등 7개 종속기업, 오로스테크놀로지 등 3개 관계기업
        "entities": [
            (P, "반도체펠리클", "반도체 펠리클(Pellicle)"),
            (P, "칠러", "칠러(Chiller/온도조절기)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체펠리클", "반도체 펠리클(Pellicle)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "칠러", "칠러(Chiller/온도조절기)"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
        ],
    },
    "1cb6bacc6a717f33": {  # 2024 사업보고서 연결재무제표주석: 에스피텍 등 7개 종속기업, 오로스테크놀로지 등 3개 관계기업
        "entities": [
            (P, "반도체펠리클", "반도체 펠리클(Pellicle)"),
            (P, "칠러", "칠러(Chiller/온도조절기)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체펠리클", "반도체 펠리클(Pellicle)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "칠러", "칠러(Chiller/온도조절기)"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "에스피텍"), 0.95, "종속기업(EUV 프레임·도금)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
        ],
    },

    # ═══ II. 사업의 내용: 펠리클 사업 ═══

    "1c7334ebd674f0a0": {  # 2023 사업보고서: 펠리클사업부·TCU사업부·종속회사 XIAN/WUXI/FINE SEMITECH
        "entities": [
            (P, "반도체펠리클", "반도체 펠리클(Pellicle)"),
            (P, "FPD펠리클", "FPD 펠리클(TFT-LCD/OLED용)"),
            (P, "칠러", "칠러(Chiller/온도조절기)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체펠리클", "반도체 펠리클(Pellicle)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "FPD펠리클", "FPD 펠리클(TFT-LCD/OLED용)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "칠러", "칠러(Chiller/온도조절기)"), 0.97),
        ],
    },
    "25067401dfe2e8dd": {  # 2024.09 분기: 펠리클사업부·TCU사업부·XIAN FST·WUXI FST·FINE SEMITECH USA
        "entities": [
            (P, "반도체펠리클", "반도체 펠리클(Pellicle)"),
            (P, "FPD펠리클", "FPD 펠리클(TFT-LCD/OLED용)"),
            (P, "칠러", "칠러(Chiller/온도조절기)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체펠리클", "반도체 펠리클(Pellicle)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "FPD펠리클", "FPD 펠리클(TFT-LCD/OLED용)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "칠러", "칠러(Chiller/온도조절기)"), 0.97),
        ],
    },
    "1b17518bf1b5ac63": {  # 2025 사업보고서: 주력=포토마스크용 보호막 펠리클 + 온도조절장비 칠러, 재료부문 매출 1,663억(59%)
        "entities": [
            (P, "반도체펠리클", "반도체 펠리클(Pellicle)"),
            (P, "칠러", "칠러(Chiller/온도조절기)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체펠리클", "반도체 펠리클(Pellicle)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "칠러", "칠러(Chiller/온도조절기)"), 0.97),
        ],
    },
    "222b304717a82a0f": {  # 2023 사업보고서: FPD 펠리클·반도체 펠리클 제품 설명
        "entities": [
            (P, "반도체펠리클", "반도체 펠리클(Pellicle)"),
            (P, "FPD펠리클", "FPD 펠리클(TFT-LCD/OLED용)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체펠리클", "반도체 펠리클(Pellicle)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "FPD펠리클", "FPD 펠리클(TFT-LCD/OLED용)"), 0.95),
        ],
    },
    "22925dd84f6d2e89": {  # 2025 사업보고서: 반도체 펠리클 시장 특성 — 클린룸 설비, 진입장벽 높은 산업
        "entities": [
            (P, "반도체펠리클", "반도체 펠리클(Pellicle)"),
            (P, "FPD펠리클", "FPD 펠리클(TFT-LCD/OLED용)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체펠리클", "반도체 펠리클(Pellicle)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "FPD펠리클", "FPD 펠리클(TFT-LCD/OLED용)"), 0.90),
        ],
    },
    "223f324930a400a9": {  # 2023 사업보고서: 펠리클 초대형화·고품질화 — 칠러 핵심경쟁요소, 에스피텍 반도체 펠리클 프레임
        "entities": [
            (P, "반도체펠리클", "반도체 펠리클(Pellicle)"),
            (P, "칠러", "칠러(Chiller/온도조절기)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체펠리클", "반도체 펠리클(Pellicle)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "칠러", "칠러(Chiller/온도조절기)"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "에스피텍"), 0.95, "종속기업(반도체 펠리클용 프레임)"),
        ],
    },
    "070d737924f9a1e6": {  # 2024.06 반기: 펠리클 초대형화·칠러 — 에스피텍 반도체 펠리클 프레임 종속회사
        "entities": [
            (P, "반도체펠리클", "반도체 펠리클(Pellicle)"),
            (P, "칠러", "칠러(Chiller/온도조절기)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체펠리클", "반도체 펠리클(Pellicle)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "칠러", "칠러(Chiller/온도조절기)"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "에스피텍"), 0.95, "종속기업(반도체 펠리클용 프레임)"),
        ],
    },
    "03d6f2ea8d9b16db": {  # 2025.06 반기: 펠리클 초대형화 → 에스피텍 프레임. 칠러 해외 END User 확대
        "entities": [
            (P, "반도체펠리클", "반도체 펠리클(Pellicle)"),
            (P, "칠러", "칠러(Chiller/온도조절기)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체펠리클", "반도체 펠리클(Pellicle)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "칠러", "칠러(Chiller/온도조절기)"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "에스피텍"), 0.95, "종속기업(반도체 펠리클용 프레임·EUV 도금)"),
        ],
    },
    "196e6feb66fa38a5": {  # 2024 사업보고서: 펠리클 초대형화 → 에스피텍 프레임. 칠러 해외 설비Maker·END User
        "entities": [
            (P, "반도체펠리클", "반도체 펠리클(Pellicle)"),
            (P, "칠러", "칠러(Chiller/온도조절기)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체펠리클", "반도체 펠리클(Pellicle)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "칠러", "칠러(Chiller/온도조절기)"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "에스피텍"), 0.95, "종속기업(반도체 펠리클용 프레임)"),
        ],
    },
    "0e58aa6e4d209f8f": {  # 2025.06 반기: FPD 펠리클 — OLED TV·모바일·차량용 디스플레이 시장
        "entities": [
            (P, "FPD펠리클", "FPD 펠리클(TFT-LCD/OLED용)"),
            (P, "칠러", "칠러(Chiller/온도조절기)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "FPD펠리클", "FPD 펠리클(TFT-LCD/OLED용)"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "칠러", "칠러(Chiller/온도조절기)"), 0.90),
        ],
    },
    "1e7bf827987f0dc3": {  # 2025.03 분기: FPD 펠리클 — OLED 성장, FPD 펠리클 AR코팅 소재 개발
        "entities": [
            (P, "FPD펠리클", "FPD 펠리클(TFT-LCD/OLED용)"),
            (P, "칠러", "칠러(Chiller/온도조절기)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "FPD펠리클", "FPD 펠리클(TFT-LCD/OLED용)"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "칠러", "칠러(Chiller/온도조절기)"), 0.88),
        ],
    },

    # ═══ II. 사업의 내용: EUV Pellicle 신규사업 ═══

    "04d279536a881712": {  # 2024.03 분기: EUV Pellicle 연구개발, EUV Pellicle mounter&demounter 장비 개발완료, EUVO(EUV light generation system)
        "entities": [
            (P, "EUV펠리클", "EUV Pellicle(EUV 노광공정용)"),
            (T, "EUV리소그래피", "EUV Lithography 공정기술"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "EUV펠리클", "EUV Pellicle(EUV 노광공정용)"), 0.90),
            E("USES_TECH", ("org", CORP), ("ent", T, "EUV리소그래피", "EUV Lithography 공정기술"), 0.88),
        ],
    },
    "0fe9f723fd9fd411": {  # 2024.09 분기: EUV Pellicle 연구개발, EUV Pod 검사장비, EUVO(EUV light generation system)
        "entities": [
            (P, "EUV펠리클", "EUV Pellicle(EUV 노광공정용)"),
            (T, "EUV리소그래피", "EUV Lithography 공정기술"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "EUV펠리클", "EUV Pellicle(EUV 노광공정용)"), 0.90),
            E("USES_TECH", ("org", CORP), ("ent", T, "EUV리소그래피", "EUV Lithography 공정기술"), 0.88),
        ],
    },
    "218da80d688344b9": {  # 2025 사업보고서: EUV Pellicle mounter&demounter 개발완료, EUVO 광원시스템
        "entities": [
            (P, "EUV펠리클", "EUV Pellicle(EUV 노광공정용)"),
            (T, "EUV리소그래피", "EUV Lithography 공정기술"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "EUV펠리클", "EUV Pellicle(EUV 노광공정용)"), 0.90),
            E("USES_TECH", ("org", CORP), ("ent", T, "EUV리소그래피", "EUV Lithography 공정기술"), 0.88),
        ],
    },

    # ═══ II. 사업의 내용: 칠러 — 극저온 기술 ═══

    "220d75244565d20b": {  # 2025.06 반기: 극저온 칠러 기술 — 글로벌 주요 고객사 적용 중, CO2 친환경 칠러 개발
        "entities": [
            (P, "칠러", "칠러(Chiller/온도조절기)"),
            (T, "극저온칠러기술", "극저온 칠러 기술(반도체 Etching 공정용)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "칠러", "칠러(Chiller/온도조절기)"), 0.97),
            E("USES_TECH", ("org", CORP), ("ent", T, "극저온칠러기술", "극저온 칠러 기술(반도체 Etching 공정용)"), 0.90),
        ],
    },

    # ═══ II. 사업의 내용: 에스피텍 — EUV 프레임·도금 ═══

    "2435e4188030d8d2": {  # 2025.06 반기: 에스피텍 — EUV 공정 무결점 EUV 프레임, Optical frame 도금 기술, EUV 소재 특수 도금
        "entities": [
            (P, "EUV프레임", "EUV 펠리클 프레임(반도체 노광공정용)"),
            (T, "EUV도금기술", "EUV 공정용 특수 도금 기술"),
        ],
        "edges": [
            E("PRODUCES", ("org", "에스피텍"), ("ent", P, "EUV프레임", "EUV 펠리클 프레임(반도체 노광공정용)"), 0.92),
            E("USES_TECH", ("org", "에스피텍"), ("ent", T, "EUV도금기술", "EUV 공정용 특수 도금 기술"), 0.88),
            E("RELATED_PARTY", ("org", CORP), ("org", "에스피텍"), 0.97, "종속기업(EUV 프레임·특수도금)"),
        ],
    },

    # ═══ II. 사업의 내용: 화인세라텍 ═══

    "04e4d99a1edfa345": {  # 2025.06 반기: 화인세라텍 Probe Card용 세라믹 제품
        "entities": [
            (P, "ProbeCard세라믹", "Probe Card용 세라믹 부품"),
        ],
        "edges": [
            E("PRODUCES", ("org", "화인세라텍"), ("ent", P, "ProbeCard세라믹", "Probe Card용 세라믹 부품"), 0.88),
            E("RELATED_PARTY", ("org", CORP), ("org", "화인세라텍"), 0.95, "종속기업(Probe Card 세라믹)"),
        ],
    },

    # ═══ II. 사업의 내용: 에프엑스티 — CVD-SiC ═══

    "01554eee56919ccd": {  # 2025.03 분기: 에프엑스티 CVD-SiC 소재 양산 공급, 설비 증설. 아이엠디 전극 Paste
        "entities": [
            (P, "CVDSiC소재", "CVD-SiC 소재(반도체 공정용)"),
            (P, "전극Paste", "전극 Paste(Chip 부품용)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "에프엑스티"), ("ent", P, "CVDSiC소재", "CVD-SiC 소재(반도체 공정용)"), 0.92),
            E("PRODUCES", ("org", "아이엠디"), ("ent", P, "전극Paste", "전극 Paste(Chip 부품용)"), 0.88),
            E("RELATED_PARTY", ("org", CORP), ("org", "에프엑스티"), 0.95, "종속기업(CVD-SiC 소재)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "아이엠디"), 0.93, "종속기업(전극 Paste)"),
        ],
    },
    "06fa16fb5f7abbdb": {  # 2023 사업보고서: 에프엑스티 CVD-SiC 양산 공급. 클라넷 폐가스 처리 스크러버
        "entities": [
            (P, "CVDSiC소재", "CVD-SiC 소재(반도체 공정용)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "에프엑스티"), ("ent", P, "CVDSiC소재", "CVD-SiC 소재(반도체 공정용)"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "에프엑스티"), 0.95, "종속기업(CVD-SiC 소재)"),
        ],
    },
    "15bcd0f1768bc3fe": {  # 2025 사업보고서: 아이엠디 전극 Paste — 전기차 전장용·전력반도체용 도전성 접착제
        "entities": [
            (P, "전극Paste", "전극 Paste(Chip 부품용)"),
        ],
        "edges": [
            E("PRODUCES", ("org", "아이엠디"), ("ent", P, "전극Paste", "전극 Paste(Chip 부품용)"), 0.90),
            E("RELATED_PARTY", ("org", CORP), ("org", "아이엠디"), 0.93, "종속기업(전극 Paste)"),
        ],
    },

    # ═══ II. 사업의 내용: 제품 현황·가격변동 ═══

    "1eef0e87514af9f0": {  # 2025.09 분기: 주요 제품 현황 — 펠리클/칠러 내수·수출
        "entities": [
            (P, "반도체펠리클", "반도체 펠리클(Pellicle)"),
            (P, "칠러", "칠러(Chiller/온도조절기)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체펠리클", "반도체 펠리클(Pellicle)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "칠러", "칠러(Chiller/온도조절기)"), 0.97),
        ],
    },

    # ═══ II. 사업의 내용: 판매경로·판매방법 ═══

    "1b1c4cf05b2ee26a": {  # 2025 사업보고서: 판매경로 — 펠리클사업부·칠러·APS사업부 3개 본부. 직접판매/위탁판매
        "entities": [
            (P, "반도체펠리클", "반도체 펠리클(Pellicle)"),
            (P, "칠러", "칠러(Chiller/온도조절기)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체펠리클", "반도체 펠리클(Pellicle)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "칠러", "칠러(Chiller/온도조절기)"), 0.97),
        ],
    },

    # ═══ II. 사업의 내용: 시장 현황 ═══

    "0085f707cc5e1ceb": {  # 2025.03 분기: 파운드리 시장 — TSMC 66%, 삼성전자 9%. 경기변동 특성
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.85),
        ],
    },
    "0a8b46f390598aef": {  # 2025.09 분기: 파운드리 시장 — TSMC/삼성전자 언급
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.85),
        ],
    },

    # ═══ X. 대주주 등과의 거래내용: 삼성전자 매출 + 시엠테크놀로지 매입 ═══

    "25663c8903fddf64": {  # 2023 사업보고서: 삼성전자(주) 주요주주 — 매출 84,243,840천원. 시엠테크놀로지 특수관계법인 — 매입 7,286,004천원
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "특수관계법인(주요 매입처)"),
        ],
    },
    "81da40fa0f56a6fd": {  # 2023 사업보고서 X: 삼성전자 매출 84,243,840천원/전기 89,935,984천원
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "특수관계법인(매입처)"),
        ],
    },
    "191e2694bee12399": {  # 2024.03 분기: 삼성전자 매출 18,748,801천원, 시엠테크놀로지 매입 1,991,768천원
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "특수관계법인(매입처)"),
        ],
    },
    "5fce42a130f70851": {  # 2024.06 반기: 삼성전자 매출 32,187,463천원, 시엠테크놀로지 매입 4,250,692천원
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "특수관계법인(매입처)"),
        ],
    },
    "ecf363bac1cf07d5": {  # 2024.09 분기: 삼성전자 매출 48,888,687천원, 시엠테크놀로지 매입 6,260,349천원
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "특수관계법인(매입처)"),
        ],
    },
    "665a0b4062e6c6b2": {  # 2024 사업보고서: 삼성전자 매출 79,696,133천원, 시엠테크놀로지 매입 8,503,585천원
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "특수관계법인(매입처)"),
        ],
    },
    "7d599e4ddf406f8a": {  # 2025.03 분기: 삼성전자 매출 18,635,399천원, 시엠테크놀로지 매입 2,004,443천원
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "특수관계법인(매입처)"),
        ],
    },
    "bb8c30c5c9c23561": {  # 2025.06 반기: 삼성전자 매출 41,310,280천원, 시엠테크놀로지 매입 4,262,434천원
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "특수관계법인(매입처)"),
        ],
    },
    "c20f8806a8ae47af": {  # 2025.09 분기: 삼성전자 매출 58,889,236천원, 시엠테크놀로지 매입 6,566,105천원
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "특수관계법인(매입처)"),
        ],
    },
    "0d4c0acf2c25198c": {  # 2025 사업보고서: 삼성전자 매출 76,387,711천원, 시엠테크놀로지 매입 8,449,682천원
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "특수관계법인(매입처)"),
        ],
    },
    "db84ad8d84b1189e": {  # 2026.03 분기: 삼성전자 매출 25,634,043천원, 시엠테크놀로지 매입 2,304,863천원
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "특수관계법인(매입처)"),
        ],
    },

    # ═══ 채권채무 테이블 (주요주주·특수관계 잔액) ═══

    "38863a8300e75ebe": {  # 2023 사업보고서: 채권채무 — 삼성전자 채권 7,414,327, 시엠테크놀로지 채무 1,794,245
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "특수관계법인(채무 잔액)"),
        ],
    },
    "319935808853536a": {  # 2024.03 분기: 채권채무 — 삼성전자 채권 8,304,431
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.88, "특수관계법인(채무)"),
        ],
    },
    "bb852ba574430bca": {  # 2024.06 반기: 채권채무 — 삼성전자 채권 4,975,102
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.88, "특수관계법인(채무)"),
        ],
    },
    "4bc7b440e230111c": {  # 2024.09 분기: 채권채무 — 삼성전자 채권 7,400,698
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.88, "특수관계법인(채무)"),
        ],
    },
    "d1b8cfc8f6335eef": {  # 2024 사업보고서: 채권채무 — 삼성전자 채권 7,400,698, 시엠테크놀로지 채무 1,905,738
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.88, "특수관계법인(채무)"),
        ],
    },
    "a6bf5b7902b90123": {  # 2025.03 분기: 채권채무 — 삼성전자 채권 9,030,148
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.88, "특수관계법인(채무)"),
        ],
    },
    "3d9574316a0d7fff": {  # 2025.06 반기: 채권채무 — 삼성전자 채권 8,261,554
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.88, "특수관계법인(채무)"),
        ],
    },
    "f71e8c115fb8b801": {  # 2025.09 분기: 채권채무 — 삼성전자 채권 5,994,479
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.88, "특수관계법인(채무)"),
        ],
    },
    "d6f7831d62015b3e": {  # 2025 사업보고서: 채권채무 — 삼성전자 채권 9,001,816, 시엠테크놀로지 채무 1,920,983
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.88, "특수관계법인(채무)"),
        ],
    },
    "6ef93bb9ff4f345e": {  # 2026.03 분기: 채권채무 — 삼성전자 채권 7,991,723, 시엠테크놀로지 채무 3,903,065
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.88, "특수관계법인(채무)"),
        ],
    },

    # ═══ 특수관계자 현황 표 (관계기업·기타특수관계자) ═══

    "6763eefa2350cf20": {  # 2023 사업보고서 연결재무제표주석: 관계기업=오로스테크놀로지·이솔·시옷플랫폼·피에스플라즈마, 기타=시엠테크놀로지·탐스·페넌트인베스트먼트·파워팩터스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "이솔"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시옷플랫폼"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "기타 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "탐스"), 0.85, "기타 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "파워팩터스"), 0.85, "기타 특수관계자"),
        ],
    },
    "70e61cf4be94ef90": {  # 2023 사업보고서 연결감사보고서: 관계기업=오로스테크놀로지·이솔·시옷플랫폼·피에스플라즈마, 기타=시엠테크놀로지·탐스·페넌트·파워팩터스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "이솔"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시옷플랫폼"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "기타 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "탐스"), 0.85, "기타 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "파워팩터스"), 0.85, "기타 특수관계자"),
        ],
    },
    "88a8b6ba673d0b68": {  # 2023 사업보고서 재무제표주석: 관계기업=오로스테크놀로지·피에스플라즈마·시옷플랫폼·이솔, 기타=시엠테크놀로지·탐스·파워팩터스·피에스플라즈마
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "이솔"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "기타 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "탐스"), 0.85, "기타 특수관계자"),
        ],
    },
    "1befd76b059e1da8": {  # 2024.03 분기 연결재무제표주석: 관계기업=오로스테크놀로지·시옷플랫폼·이솔, 기타=시엠테크놀로지·탐스·페넌트·파워팩터스·피에스플라즈마(소멸)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "이솔"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시옷플랫폼"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "기타 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "탐스"), 0.85, "기타 특수관계자"),
        ],
    },
    "3f883912a53500be": {  # 2024.06 반기 연결재무제표주석: 관계기업=오로스테크놀로지·시옷플랫폼·이솔, 기타=시엠테크놀로지·탐스·페넌트·파워팩터스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "이솔"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시옷플랫폼"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "기타 특수관계자"),
        ],
    },
    "a3b1963ec8a6a0c5": {  # 2024.09 분기 연결재무제표주석: 관계기업=오로스테크놀로지·시옷플랫폼·이솔, 기타=시엠테크놀로지·탐스·페넌트·파워팩터스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "이솔"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시옷플랫폼"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "기타 특수관계자"),
        ],
    },
    "de450455ca768aa0": {  # 2024 사업보고서 연결재무제표주석: 관계기업=오로스테크놀로지·시옷플랫폼·이솔, 기타=시엠테크놀로지·탐스·페넌트·파워팩터스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "이솔"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시옷플랫폼"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "기타 특수관계자"),
        ],
    },
    "5cb454c6d5a391fd": {  # 2025.03 분기 연결재무제표주석: 관계기업=오로스테크놀로지·시옷플랫폼·이솔, 기타=시엠테크놀로지·탐스·페넌트·파워팩터스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "이솔"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시옷플랫폼"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "기타 특수관계자"),
        ],
    },
    "04b55f0937dc7ef3": {  # 2025.06 반기 연결재무제표주석: 관계기업=오로스테크놀로지·시옷플랫폼·이솔, 기타=시엠테크놀로지·탐스·페넌트·파워팩터스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "이솔"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시옷플랫폼"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "기타 특수관계자"),
        ],
    },
    "075b35f6fbfc1ad3": {  # 2025.09 분기 연결재무제표주석: 관계기업=오로스테크놀로지·시옷플랫폼·이솔·Advanced Semiconductor Products, 기타=시엠테크놀로지·탐스·페넌트·파워팩터스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "이솔"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "기타 특수관계자"),
        ],
    },
    "5242c355cf14c74d": {  # 2025 사업보고서 연결재무제표주석: 관계기업=오로스테크놀로지·시옷플랫폼·이솔·Advanced Semiconductor Products, 기타=시엠테크놀로지·탐스·페넌트·파워팩터스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "이솔"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "기타 특수관계자"),
        ],
    },
    "7305b4cbf8e541b1": {  # 2025 사업보고서 연결감사보고서: 관계기업=오로스테크놀로지·시옷플랫폼·이솔·Advanced Semiconductor Products
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "이솔"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "기타 특수관계자"),
        ],
    },
    "0d878d6d659b111f": {  # 2025 사업보고서 감사보고서: 관계기업=오로스테크놀로지·시옷플랫폼·이솔·Advanced Semiconductor Products
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "이솔"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "기타 특수관계자"),
        ],
    },
    "b32006f0fe784473": {  # 2026.03 분기 연결재무제표주석: 관계기업=오로스테크놀로지·시옷플랫폼·이솔·Advanced Semiconductor Products
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "이솔"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "기타 특수관계자"),
        ],
    },
    "38e0cb750c2bd410": {  # 2025 사업보고서 재무제표주석: 관계기업=오로스테크놀로지·시옷플랫폼·이솔·Advanced Semiconductor Products
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "이솔"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "기타 특수관계자"),
        ],
    },
    "3ec596c9a20fe051": {  # 2024 사업보고서 재무제표주석: 관계기업=오로스테크놀로지·시옷플랫폼·이솔, 기타=시엠테크놀로지·탐스·파워팩터스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "이솔"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "기타 특수관계자"),
        ],
    },
    "379c8e4631ee5b52": {  # 2024.09 분기 재무제표주석: 관계기업=오로스테크놀로지·시옷플랫폼·이솔, 기타=시엠테크놀로지·탐스·파워팩터스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "이솔"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "기타 특수관계자"),
        ],
    },
    "abedf9379cc2aa5e": {  # 2024.03 분기 재무제표주석: 관계기업=오로스테크놀로지·시옷플랫폼·이솔, 기타=시엠테크놀로지·탐스·파워팩터스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "이솔"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "기타 특수관계자"),
        ],
    },
    "c63d6f64847fedfd": {  # 2024.06 반기 재무제표주석: 관계기업=오로스테크놀로지·시옷플랫폼·이솔, 기타=시엠테크놀로지·탐스·파워팩터스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "이솔"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "기타 특수관계자"),
        ],
    },
    "f3d62d2524ef23a3": {  # 2025.06 반기 재무제표주석: 관계기업=오로스테크놀로지·시옷플랫폼·이솔, 기타=시엠테크놀로지·탐스·파워팩터스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "이솔"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "기타 특수관계자"),
        ],
    },
    "0c3c3520abcc41b8": {  # 2025.09 분기 재무제표주석: 관계기업=오로스테크놀로지·시옷플랫폼·이솔·Advanced Semiconductor Products
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "이솔"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "기타 특수관계자"),
        ],
    },
    "e1812e6b72d786d1": {  # 2025.03 분기 재무제표주석: 관계기업=오로스테크놀로지·시옷플랫폼·이솔, 기타=시엠테크놀로지·탐스·파워팩터스
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "이솔"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "기타 특수관계자"),
        ],
    },
    "fd26ed477301715d": {  # 2026.03 분기 재무제표주석: 관계기업=오로스테크놀로지·시옷플랫폼·이솔·Advanced Semiconductor Products
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "오로스테크놀로지"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "이솔"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "기타 특수관계자"),
        ],
    },

    # ═══ 자금거래·배당 — 시엠테크놀로지 ═══

    # "25663c8903fddf64_2" was a duplicate key stub — covered by 25663c8903fddf64 above

    # ═══ XI. 특수관계자 채권채무 — 아이엠디 ═══

    "e40ef503905ce11d": {  # 2025 사업보고서 XI: 아이엠디 — 미수금 2,049,300, 미지급금 5,296,588, 기타채무 62,777,372(종속기업)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "아이엠디"), 0.95, "종속기업(내부 채권채무)"),
        ],
    },

    # ═══ XI. 종속기업 현황 ═══

    "dd0036232fe267b1": {  # 2026.03 분기 재무제표주석 종속기업 현황: 에스피텍 100%, XIAN FST 100%, WUXI FST 100%, FINE SEMITECH USA 100%, 화인세라텍 57.17%, 에프엑스티 51.18%, 아이엠디 100%
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "에스피텍"), 0.97, "종속기업(지분율 100%)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "화인세라텍"), 0.95, "종속기업(지분율 57.17%)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에프엑스티"), 0.95, "종속기업(지분율 51.18%)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "아이엠디"), 0.95, "종속기업(지분율 100%)"),
        ],
    },

    # ═══ IX. 계열회사 ═══

    "0db821dfd2dbc2aa": {  # 2024.09 분기: IX. 계열회사 — 계열회사 현황 관련 설명
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.85, "기타 특수관계자(계열)"),
        ],
    },

    # ═══ X. 대주주 등과의 거래: 자금거래 시엠테크놀로지 ═══

    "f6b7c5138c7a7ab4": {  # 2024.03 분기: 시엠테크놀로지 배당금 지급 91,933
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "특수관계법인(배당금)"),
        ],
    },
    "95aa5170c7f33ea3": {  # 2024.06 반기: 시엠테크놀로지 배당금 지급 91,933
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "특수관계법인(배당금)"),
        ],
    },
    "d898c4086d6c2284": {  # 2024.09 분기: 시엠테크놀로지 배당금 지급 91,933
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "특수관계법인(배당금)"),
        ],
    },
    "d4fc29eb8ea8dfed": {  # 2024 사업보고서: 시엠테크놀로지 배당금 지급 91,933
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "특수관계법인(배당금)"),
        ],
    },
    "bfcaf387b6ba9d7d": {  # 2025.03 분기: 시엠테크놀로지 배당금 지급 9,193
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "특수관계법인(배당금)"),
        ],
    },
    "f18643f6c97dac0c": {  # 2025.06 반기: 시엠테크놀로지 배당금 지급 9,193
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "특수관계법인(배당금)"),
        ],
    },
    "a61465eef7ee37c2": {  # 2025.09 분기: 시엠테크놀로지 배당금 지급 9,193
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "특수관계법인(배당금)"),
        ],
    },
    "5684767b9687a518": {  # 2025 사업보고서: 시엠테크놀로지 배당금 지급 9,193
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "특수관계법인(배당금)"),
        ],
    },
    "ab3da209d8941039": {  # 2026.03 분기: 시엠테크놀로지 배당금 지급 9,285
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.90, "특수관계법인(배당금)"),
        ],
    },

    # ═══ X. 대주주 거래 — X.대주주 거래내용 텍스트 ═══
    "0dd1fbaf9d54f0a3": {  # 2025.06 반기: X. 대주주 등과의 거래내용
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.90),
            E("RELATED_PARTY", ("org", CORP), ("org", "시엠테크놀로지"), 0.88, "특수관계법인"),
        ],
    },
}


# ── 메인 실행 로직 ─────────────────────────────────────────────────────────
def main():
    print(f"[FST 비정형 추출] CORP={CORP}, CORP_CODE={CORP_CODE}")
    driver = neo4j_driver()
    conn = mariadb_conn()

    already = ledger_processed_ids()
    print(f"  원장 기처리: {len(already)}개")

    # 전체 chunk_id 목록 조회
    import pymysql.cursors
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        "SELECT chunk_id, rcept_no, section_path, chunk_type, embedding_text "
        "FROM chunk_index "
        "WHERE corp_code=%s "
        "AND (chunk_type='text_micro' OR (chunk_type='table_nl' AND embedding_text LIKE '%%특수관계%%')) "
        "ORDER BY chunk_id",
        (CORP_CODE,),
    )
    all_chunks = {r["chunk_id"]: r for r in cur.fetchall()}
    cur.close()
    print(f"  DB 청크수: {len(all_chunks)}")

    extraction_chunk_ids = set(EXTRACTIONS.keys())
    total_ent = 0
    total_edge = 0
    processed_count = 0

    for chunk_id, data in EXTRACTIONS.items():
        if chunk_id in already:
            continue
        row = all_chunks.get(chunk_id)
        if row is None:
            # chunk_id가 DB에 없으면 스킵 (원장에 n_ent=0으로 기록)
            mark_processed(chunk_id, 0, 0, None, None)
            continue
        rcept_no = row["rcept_no"]
        section_path = row["section_path"]

        n_ent = 0
        n_edge = 0

        # 엔티티 MERGE
        eid_map: dict[tuple, str] = {}
        for label, canonical, name in data.get("entities", []):
            eid = merge_entity(driver, label, canonical, name=name)
            eid_map[(label, canonical)] = eid
            n_ent += 1

        # 엣지 MERGE
        for ed in data.get("edges", []):
            rel_type = ed["rel"]
            conf = ed["conf"]
            relation_type = ed.get("relation_type")

            def resolve_match(spec):
                kind = spec[0]
                if kind == "org":
                    org_name = spec[1]
                    org = resolve_org(org_name)
                    if org is None:
                        return None
                    merge_org_node(driver, org)
                    return {"kind": "org", "org": org}
                elif kind == "ent":
                    _, lbl, canonical, _ = spec
                    eid = eid_map.get((lbl, canonical))
                    if eid is None:
                        eid = merge_entity(driver, lbl, canonical)
                    return {"kind": "entity", "label": lbl, "id": eid}
                return None

            from_match = resolve_match(ed["from"])
            to_match = resolve_match(ed["to"])
            if from_match is None or to_match is None:
                continue

            add_edge(
                driver, rel_type, from_match, to_match,
                chunk_id, rcept_no, conf,
                relation_type=relation_type,
            )

            # provenance
            sub_id = from_match["org"]["id"] if from_match["kind"] == "org" else from_match["id"]
            obj_id = to_match["org"]["id"] if to_match["kind"] == "org" else to_match["id"]
            write_provenance(conn, sub_id, rel_type, obj_id, chunk_id, rcept_no, conf)
            conn.commit()
            n_edge += 1

        mark_processed(chunk_id, n_ent, n_edge, rcept_no, section_path)
        total_ent += n_ent
        total_edge += n_edge
        processed_count += 1

    # 추출 대상 이외의 청크는 엔티티/엣지 없이 mark_processed
    for chunk_id, row in all_chunks.items():
        if chunk_id in already or chunk_id in extraction_chunk_ids:
            continue
        mark_processed(chunk_id, 0, 0, row["rcept_no"], row["section_path"])

    driver.close()
    conn.close()
    print(f"[완료] 추출청크={processed_count}, 엔티티={total_ent}, 엣지={total_edge}")
    print(f"  원장: {LEDGER_PATH}")


if __name__ == "__main__":
    main()
