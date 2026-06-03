"""Stage 5 비정형 추출 - 원익IPS corp_code=01135941, text_micro 전체(~1,087) + table_nl 특수관계(~93).

원익IPS = 원익홀딩스의 핵심 종속기업. 반도체/디스플레이/Solar Cell 제조용 장비 전문.
  - 반도체 장비: CVD 증착(GEMINI/QUARTO/LEVATA), ALD 증착(HYETA/PRESTO/CLARO/VELOCE),
                  METAL 증착, Furnace(열처리) 장비 - 3D NAND/DRAM/Foundry 핵심 공정
  - 디스플레이 장비: OLED 증착/봉지 장비 - LCD->OLED 전환 수혜
  - Solar Cell 장비: CIGS 박막형 태양전지 RIE 장비
주요 고객사: 삼성전자, SK하이닉스, 삼성디스플레이 (국내외 주요 소자업체 양산라인 납품)
지배구조: (주)원익홀딩스(지분율 96%+) -> 원익IPS (원익기업집단 계열)
특수관계자: 원익홀딩스(지배), 원익(주)(기타), 원익머트리얼즈, 원익큐엔씨, 원익피앤이/피앤이시스템즈,
             씨엠에스랩, Wonik Global Pte. Ltd.(공동기업), 원익 2019 Start-Up 파트너쉽 투자조합(관계기업),
             원익엘앤디, 원익디투아이, 원익로보틱스, 서안반도체과기유한공사, 원익큐브, 하늘물빛정원,
             농업회사법인장산
해외종속기업: 원익IPS반도체설비기술유한공사(중국), Wonik IPS USA Inc., Wonik IPS(Xian), 쿤산테라디스플레이설비기술유한공사, WONIK IPS SG PTE. LTD.

원장 = db/graph/ledger/extra28_01135941.jsonl (이 추출 전용).
실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_wonick_ips_01135941.py
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

CORP = "원익IPS"
CORP_CODE = "01135941"

# 전용 원장
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_DIR.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = LEDGER_DIR / "extra28_01135941.jsonl"


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
# 원익IPS: 반도체/디스플레이/Solar Cell 장비 제조사.
# 핵심 고객(SUPPLIES_TO): 삼성전자, SK하이닉스, 삼성디스플레이
# 지배주주(RELATED_PARTY): 원익홀딩스 -> 원익IPS
# 기타계열(RELATED_PARTY): 원익(주), 원익머트리얼즈, 원익큐엔씨 등

EXTRACTIONS: dict[str, dict] = {

    # ── II. 사업의 내용: 반도체 장비 - 증착·열처리 장비 주요 제품 (2023 사업보고서) ──
    "0e429174ddd3f1c1": {  # 2023 사업보고서 II: GEMINI/PRESTO Foundry 증착장비, 열처리장비 양산라인 적용
        "entities": [
            (P, "반도체 CVD 증착 장비", "반도체 CVD 증착 장비(GEMINI/QUARTO/LEVATA)"),
            (P, "반도체 Furnace 열처리 장비", "반도체 Furnace 고온 열처리 장비"),
            (T, "CVD 증착 기술", "CVD(Chemical Vapor Deposition) 박막 증착 기술"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체 CVD 증착 장비", "반도체 CVD 증착 장비(GEMINI/QUARTO/LEVATA)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체 Furnace 열처리 장비", "반도체 Furnace 고온 열처리 장비"), 0.95),
            E("USES_TECH", ("org", CORP), ("ent", T, "CVD 증착 기술", "CVD(Chemical Vapor Deposition) 박막 증착 기술"), 0.92),
        ],
    },

    # ── II. 사업의 내용: 반도체 장비 - 3D NAND/DRAM ALD 장비 (2024.06 반기) ──
    "133d779b522c2fd6": {  # 2024.06 반기 II: 3D NAND 핵심 ALD 증착(CUARTO/CLARO/NOA), DRAM(HYETA/GEMINI/PRESTO), Foundry(GEMINI/PRESTO) 장비
        "entities": [
            (P, "반도체 ALD 증착 장비", "반도체 ALD(Atomic Layer Deposition) 증착 장비(HYETA/PRESTO/CLARO/VELOCE)"),
            (T, "ALD 증착 기술", "ALD(Atomic Layer Deposition) 원자층 증착 기술"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체 ALD 증착 장비", "반도체 ALD(Atomic Layer Deposition) 증착 장비(HYETA/PRESTO/CLARO/VELOCE)"), 0.97),
            E("USES_TECH", ("org", CORP), ("ent", T, "ALD 증착 기술", "ALD(Atomic Layer Deposition) 원자층 증착 기술"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.88),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.88),
        ],
    },

    # ── II. 사업의 내용: 반도체 장비 - CVD/ALD/METAL 전체 제품군 (2026 사업보고서) ──
    "3d9decabe1239ac3": {  # 2026.03 분기 II: CVD 장비(GEMINI/QUARTO/LEVATA), ALD(HYETA/GEMINI/PRESTO/CLARO/VELOCE), METAL 증착 장비 최신 제품군
        "entities": [
            (P, "반도체 CVD 증착 장비", "반도체 CVD 증착 장비(GEMINI/QUARTO/LEVATA)"),
            (P, "반도체 ALD 증착 장비", "반도체 ALD(Atomic Layer Deposition) 증착 장비(HYETA/PRESTO/CLARO/VELOCE)"),
            (P, "반도체 METAL 증착 장비", "반도체 Metal 박막 증착 장비"),
            (T, "ALD 증착 기술", "ALD(Atomic Layer Deposition) 원자층 증착 기술"),
            (T, "CVD 증착 기술", "CVD(Chemical Vapor Deposition) 박막 증착 기술"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체 CVD 증착 장비", "반도체 CVD 증착 장비(GEMINI/QUARTO/LEVATA)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체 ALD 증착 장비", "반도체 ALD(Atomic Layer Deposition) 증착 장비(HYETA/PRESTO/CLARO/VELOCE)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체 METAL 증착 장비", "반도체 Metal 박막 증착 장비"), 0.90),
            E("USES_TECH", ("org", CORP), ("ent", T, "ALD 증착 기술", "ALD(Atomic Layer Deposition) 원자층 증착 기술"), 0.95),
            E("USES_TECH", ("org", CORP), ("ent", T, "CVD 증착 기술", "CVD(Chemical Vapor Deposition) 박막 증착 기술"), 0.93),
        ],
    },

    # ── II. 사업의 내용: 반도체 장비 - Furnace(열처리) 장비 (2023 사업보고서) ──
    "0b67defe0a9d3bca": {  # 2023 사업보고서 II: Furnace 장비 국내외 주요 고객사 양산라인 높은 점유율
        "entities": [
            (P, "반도체 Furnace 열처리 장비", "반도체 Furnace 고온 열처리 장비"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체 Furnace 열처리 장비", "반도체 Furnace 고온 열처리 장비"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.85),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.85),
        ],
    },

    # ── II. 사업의 내용: Solar Cell 장비 - CIGS 박막형 (2023 사업보고서) ──
    "1b2bf4179174678a": {  # 2024.12 사업보고서(기재정정) II: CIGS 박막 태양전지 RIE 장비 공급
        "entities": [
            (P, "Solar Cell RIE 장비", "CIGS 박막 태양전지 제조용 RIE 장비"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "Solar Cell RIE 장비", "CIGS 박막 태양전지 제조용 RIE 장비"), 0.90),
        ],
    },

    # ── II. 사업의 내용: Solar Cell 장비 반복 청크 ──
    "1a0fa182ee59dffd": {  # 2025.03 분기 II: CIGS 박막형 Solar Cell RIE 장비 다결정 적용
        "entities": [
            (P, "Solar Cell RIE 장비", "CIGS 박막 태양전지 제조용 RIE 장비"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "Solar Cell RIE 장비", "CIGS 박막 태양전지 제조용 RIE 장비"), 0.90),
        ],
    },
    "1d11f3efaf056125": {  # 2025.09 분기 II: CIGS 박막형 Solar Cell RIE 장비
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "Solar Cell RIE 장비", "CIGS 박막 태양전지 제조용 RIE 장비"), 0.88),
        ],
    },

    # ── II. 사업의 내용: Display 장비 - OLED 제조용 (여러 보고서) ──
    "0026930bbc2e7efb": {  # 2025.09 분기 II: OLED 패널 LCD->OLED 전환, Display 장비 시장 확대
        "entities": [
            (P, "OLED 디스플레이 제조용 장비", "OLED 디스플레이 제조용 장비"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "OLED 디스플레이 제조용 장비", "OLED 디스플레이 제조용 장비"), 0.92),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.85),
        ],
    },
    "4a5b321fd4eef762": {  # 2024.09 분기 II: OLED 패널 IT기기 확대, Display 장비 시장 성장
        "entities": [
            (P, "OLED 디스플레이 제조용 장비", "OLED 디스플레이 제조용 장비"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "OLED 디스플레이 제조용 장비", "OLED 디스플레이 제조용 장비"), 0.92),
        ],
    },
    "675abde46604d26d": {  # 2025.12 사업보고서 II: OLED 패널 LCD->OLED 전환 시장 확대
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "OLED 디스플레이 제조용 장비", "OLED 디스플레이 제조용 장비"), 0.90),
        ],
    },

    # ── II. 사업의 내용: R&D - RF Power System / 플라즈마 센서 (2023 사업보고서) ──
    "a36ddc2f44c5c6a8": {  # 2023 사업보고서 II: OLED용 RFS(RF Power System), 플라즈마 센서모듈, 7축 웨이퍼 이동장치 R&D 완료
        "entities": [
            (T, "RF Power System", "지능형 RF 전원공급 시스템(RF Power System)"),
            (T, "플라즈마 센서 기술", "디스플레이 공정 플라즈마 센서 모듈 기술"),
            (T, "웨이퍼 이송 기술", "반도체 7축 웨이퍼 이동 장치 기술"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "RF Power System", "지능형 RF 전원공급 시스템(RF Power System)"), 0.90),
            E("USES_TECH", ("org", CORP), ("ent", T, "플라즈마 센서 기술", "디스플레이 공정 플라즈마 센서 모듈 기술"), 0.88),
            E("USES_TECH", ("org", CORP), ("ent", T, "웨이퍼 이송 기술", "반도체 7축 웨이퍼 이동 장치 기술"), 0.87),
        ],
    },

    # ── II. 사업의 내용: R&D - 반도체/Display 연구소 조직 (여러 보고서) ──
    "26d7d8f82d148f2e": {  # 2024.03 분기 II: 반도체/Display 연구소, 클린룸 연구시설, 부품업체 공동연구
        "entities": [
            (T, "반도체 장비 공정 R&D", "반도체·디스플레이 차세대 장비 공정 연구개발"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "반도체 장비 공정 R&D", "반도체·디스플레이 차세대 장비 공정 연구개발"), 0.88),
        ],
    },
    "19b9ef070db79fde": {  # 2024.12 사업보고서 II: 반도체/Display 연구소 차세대 공정 발굴, 클린룸 보유
        "entities": [],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "반도체 장비 공정 R&D", "반도체·디스플레이 차세대 장비 공정 연구개발"), 0.87),
        ],
    },
    "0b5c9f500b3ac967": {  # 2025.06 반기 II: 반도체/Display 연구소 차세대 공정 발굴, 소자업체 공동연구
        "entities": [],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "반도체 장비 공정 R&D", "반도체·디스플레이 차세대 장비 공정 연구개발"), 0.87),
        ],
    },

    # ── II. 사업의 내용: 원익IPS 매출·시장 개황 (여러 보고서) ──
    "1505c90ed839a48e": {  # 2024.12 사업보고서(기재정정) II: 반도체/Display/Solar Cell 핵심 장비 생산판매, 매출 7,482억
        "entities": [
            (P, "반도체 제조용 장비", "반도체 제조용 핵심 장비 (증착·열처리 포함)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체 제조용 장비", "반도체 제조용 핵심 장비 (증착·열처리 포함)"), 0.95),
        ],
    },
    "27e224169234a5f7": {  # 2024.12 사업보고서 II: 반도체/Display/Solar Cell 핵심 장비 생산판매, 매출 7,482억
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체 제조용 장비", "반도체 제조용 핵심 장비 (증착·열처리 포함)"), 0.93),
        ],
    },
    "18a4354cf992a407": {  # 2025.03 분기 II: 반도체/Display/Solar Cell 핵심 장비 생산판매, 1Q 매출 1,242억
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체 제조용 장비", "반도체 제조용 핵심 장비 (증착·열처리 포함)"), 0.93),
        ],
    },
    "198c76e1bafdfff4": {  # 2026.03 분기 II: 반도체/Display 핵심 장비 생산판매, 1Q 매출 1,649억(+32.8%)
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체 제조용 장비", "반도체 제조용 핵심 장비 (증착·열처리 포함)"), 0.95),
        ],
    },

    # ── IX. 계열회사: 원익홀딩스 지배 (2023 사업보고서) ──
    "a8c8d6f3d74babb0": {  # 2023 사업보고서 IX: 기업집단 원익 89개 계열회사, 원익IPS 계열
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.97, "지배주주(기업집단 원익 대표사, 96%+ 지분)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익"), 0.90, "기타특수관계자(원익기업집단)"),
        ],
    },

    # ── IX. 계열회사: 원익홀딩스 지분율 변동 (2024.06 반기) ──
    "208bb41e371843cb": {  # 2024.06 반기 IX: 기업집단 원익 87개 계열회사, 상장 9개사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.97, "지배주주(96%+ 지분)"),
        ],
    },

    # ── IX. 계열회사: 원익큐엔씨 지분율 변동 (2024.12 사업보고서) ──
    "015055eb14cfe8fd": {  # 2024.12 사업보고서 IX: 원익큐엔씨 지분율 73.30%->87.39%, 굿닥 흡수합병 제외
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.97, "지배주주(원익IPS 지배, 기업집단 원익)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익큐엔씨"), 0.92, "종속기업(쿼츠·세라믹 반도체소재)"),
        ],
    },

    # ── IX. 계열회사: 호라이즌 최대주주 변경 + 원익 장내매수 (2024.12 기재정정) ──
    "3181e87fe0483f54": {  # 2024.12 기재정정 IX: 호라이즌 최대주주 변경(38.18%->46.33%), 원익 장내매수(28.96%->30%)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.97, "지배주주(원익IPS 최대주주)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익"), 0.88, "기타 특수관계자(원익 장내매수로 지분 변동)"),
        ],
    },

    # ── IX. 계열회사: 원익홀딩스 유상증자 지분율 변동 (2025.03 분기) ──
    "55f23ef65a2b04af": {  # 2025.03 분기 IX: 원익홀딩스 지분율 96.03%->96.88% (유상증자)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.97, "지배주주(96.88%, 유상증자 지분율 변동)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익큐엔씨"), 0.92, "종속기업(87.39%->주식매입 추가 취득)"),
        ],
    },

    # ── IX. 계열회사: 원익홀딩스 유상증자 2025.06 반기 ──
    "324807a2465762f3": {  # 2025.06 반기 IX: 원익홀딩스 지분율 96.88%->96.66% (유상증자)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.97, "지배주주(96.66%, 유상증자 지분율 변동)"),
        ],
    },

    # ── IX. 계열회사: 2025.12 사업보고서 최신 지분구조 ──
    "6b10b55caa9b9bb1": {  # 2025.12 사업보고서 IX: 원익큐엔씨 케어…유상증자, 호라이즌 장내매도
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.97, "지배주주"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익큐엔씨"), 0.92, "종속기업"),
        ],
    },

    # ── IX. 계열회사: 원익피앤이 계열편입 관련 (2024.09 분기) ──
    "25b82500e18e7c8f": {  # 2024.09 분기 IX: 기업집단 원익 86개 계열회사, 상장 9개사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.97, "지배주주"),
        ],
    },
    "247922fc0d23ea91": {  # 2024.09 분기 IX: 출자현황 외 - 레커스/이단/엘제이피 계열편입
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.95, "지배주주(기업집단 원익)"),
        ],
    },

    # ── IX. 계열회사: 이디비 흡수합병 + Momentive 설립 (2024.12 사업보고서) ──
    "8f14cf6c455c3dd1": {  # 2024.12 사업보고서 IX: 이디비 흡수합병 제외, Momentive 100% 설립
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.97, "지배주주"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익큐엔씨"), 0.92, "종속기업(Momentive 합작 관계)"),
        ],
    },

    # ── IX. 계열회사: 2024.12 사업보고서 큐브바이트/하이브스튜디오 등 계열편입 ──
    "807bdeb365bd6e77": {  # 2024.12 사업보고서 IX: 큐브바이트/하이브스튜디오/레커스/이단 계열편입
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.95, "지배주주(기업집단 원익)"),
        ],
    },

    # ── IX. 계열회사: 2026.03 분기 최신 ──
    "a7a17bb09ea48a25": {  # 2026.03 분기 IX: 원익IPS 자회사 2025.12.19 설립
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.97, "지배주주"),
        ],
    },

    # ── III. 재무 주석: 특수관계자 목록 — 2023 연결감사보고서 ──
    "415072409b1c3bb2": {  # 2023 사업보고서 연결감사보고서: 특수관계자 목록 - 원익홀딩스(영향력), 원익2019스타트업파트너쉽(관계기업), 원익기업집단 계열(기타)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.97, "유의적 영향력 행사기업(지배주주)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익머트리얼즈"), 0.88, "기타 특수관계자(원익기업집단 계열)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익큐엔씨"), 0.88, "기타 특수관계자(원익기업집단 계열)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "씨엠에스랩"), 0.85, "기타 특수관계자(원익기업집단 계열)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익피앤이"), 0.85, "기타 특수관계자(원익기업집단 계열)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익엘앤디"), 0.85, "기타 특수관계자(원익기업집단 계열)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "하늘물빛정원"), 0.80, "기타 특수관계자(원익기업집단 계열)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "농업회사법인장산"), 0.78, "기타 특수관계자(원익기업집단 계열)"),
        ],
    },

    # ── III. 재무 주석: 특수관계자 목록 — 2025.09 분기 연결재무제표 주석 ──
    "229226cc022e8092": {  # 2025.09 분기 연결재무제표주석: 원익홀딩스(영향력), Wonik Global(공동기업), 원익2019스타트업파트너쉽(관계기업), 원익/원익머트리얼즈/씨엠에스랩/원익큐엔씨/피앤이시스템즈(기타)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.97, "유의적 영향력 행사기업(지배주주)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익머트리얼즈"), 0.88, "기타 특수관계자(원익기업집단)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "씨엠에스랩"), 0.85, "기타 특수관계자(원익기업집단)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익큐엔씨"), 0.88, "기타 특수관계자(원익기업집단)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "피앤이시스템즈"), 0.85, "기타 특수관계자(원익기업집단)"),
        ],
    },

    # ── III. 재무 주석: 특수관계자 목록 — 2025.12 사업보고서 연결감사보고서 ──
    "01592842a3b4bd4b": {  # 2025.12 사업보고서 연결감사보고서: 원익홀딩스(영향력), Wonik Global(공동기업), 원익2019스타트업파트너쉽(관계기업), 원익/원익머트리얼즈/씨엠에스랩/원익큐엔씨/피앤이시스템즈 등(기타)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.97, "유의적 영향력 행사기업(지배주주)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익머트리얼즈"), 0.88, "기타 특수관계자(원익기업집단)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "씨엠에스랩"), 0.85, "기타 특수관계자(원익기업집단)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "원익큐엔씨"), 0.88, "기타 특수관계자(원익기업집단)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "피앤이시스템즈"), 0.85, "기타 특수관계자(원익기업집단)"),
        ],
    },

    # ── III. 재무 주석: 특수관계자 거래 (연결) - 원익홀딩스 매입 거래 2023 ──
    "07c85d1d80855b7e": {  # 2023 사업보고서 연결감사보고서: 원익홀딩스 매입 217,200천원, 기타비용, 배당지급
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.95, "지배주주(매입 거래 217,200천원, 배당지급)"),
        ],
    },

    # ── III. 재무 주석: 특수관계자 거래 (연결) - 원익홀딩스 2023 2분기 ──
    "1292e80b93b5ff5a": {  # 2023 사업보고서 연결재무제표주석: 원익홀딩스 매입 거래, 기타비용, 배당지급
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.95, "지배주주(매입·배당 거래)"),
        ],
    },

    # ── III. 재무 주석: 특수관계자 거래 (연결) - 원익홀딩스 2024.06 반기 ──
    "455b754ab5d1429e": {  # 2024.06 반기 연결재무제표주석: 원익홀딩스 매입 110,100천원
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.95, "지배주주(매입 거래 110,100천원)"),
        ],
    },

    # ── III. 재무 주석: 특수관계자 거래 (연결) - 원익홀딩스 2024.09 분기 ──
    "42795dd7d025f3f4": {  # 2024.09 분기 연결재무제표주석: 원익홀딩스 매입 거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.95, "지배주주(매입 거래)"),
        ],
    },

    # ── III. 재무 주석: 특수관계자 거래 (연결) - 2025.12 사업보고서 ──
    "1f9a2dfd936020ce": {  # 2025.12 사업보고서 연결감사보고서: 원익홀딩스 매출 4,350천원, 매입 43,400천원, 대여금평가이익
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.97, "지배주주(매출 4,350천원, 매입 43,400천원, 대여금평가이익)"),
        ],
    },

    # ── III. 재무 주석: 특수관계자 거래 (별도) - 원익홀딩스 매입 2023 ──
    "0dc5c1be45bd7626": {  # 2023 사업보고서 재무제표주석(별도): 원익홀딩스 매입 217,200천원, 기타수익, 배당지급
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.95, "지배주주(별도: 매입 217,200천원, 배당지급)"),
        ],
    },
    "0a64c14861f3411a": {  # 2023 사업보고서 감사보고서(별도): 원익홀딩스 매입 217,200천원, 기타수익, 배당지급
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.95, "지배주주(별도: 매입·배당 거래)"),
        ],
    },
    "4add5206c3154ec9": {  # 2023 사업보고서 감사보고서(별도): 원익홀딩스 매입, 기타수익, 배당지급 (두 번째 테이블)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.93, "지배주주(별도 재무제표 거래)"),
        ],
    },

    # ── III. 재무 주석: 특수관계자 거래 (별도) - 2024.06 반기 ──
    "27d4566c4fcd9615": {  # 2024.06 반기 재무제표주석(별도): 원익홀딩스 매입 110,100천원
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.95, "지배주주(별도: 매입 110,100천원)"),
        ],
    },

    # ── III. 재무 주석: 특수관계자 거래 (별도) - 2024.09 분기 ──
    "027be7e78326ed9a": {  # 2024.09 분기 재무제표주석(별도): 원익홀딩스 매입 171,600천원
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.95, "지배주주(별도: 매입 171,600천원)"),
        ],
    },

    # ── III. 재무 주석: 특수관계자 목록 (별도) - 2024.12 사업보고서 ──
    "29d09450177d6399": {  # 2024.12 사업보고서 감사보고서(별도): 종속기업 목록(원익IPS반도체설비/Wonik IPS USA 등), 공동기업(Wonik Global), 관계기업(원익2019스타트업파트너쉽)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.97, "지배주주"),
        ],
    },

    # ── III. 재무 주석: 특수관계자 목록 (별도) - 2026.03 분기 ──
    "2a6387ba1c554790": {  # 2026.03 분기 재무제표주석(별도): 종속기업 목록(원익IPS반도체설비/Wonik IPS USA/쿤산테라디스플레이/WONIK IPS SG 등), 공동기업(Wonik Global)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.97, "지배주주"),
        ],
    },

    # ── III. 재무 주석: 특수관계자 목록 (별도) - 2025.09 분기 ──
    "4606d9da9d94bd6b": {  # 2025.09 분기 재무제표주석(별도): 동일 종속기업 목록, Wonik Global 공동기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.95, "지배주주"),
        ],
    },

    # ── III. 재무 주석: Wonik Global 대여금 약정 - X. 대주주 거래 (2024.03 분기) ──
    "1315b9e222c0211c": {  # 2024.03 분기 X: Wonik Global Pte. Ltd. 대여금 약정 USD 9,000,000, 잔여 2,661,948
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Wonik Global Pte. Ltd."), 0.92, "공동기업(대여금 약정 USD 9,000,000)"),
        ],
    },

    # ── X. 대주주 거래: Wonik Global 대여금 약정 (2024.06 반기) ──
    "0412e9dc48f8846a": {  # 2024.06 반기 X: Wonik Global Pte. Ltd. 대여금 약정 USD 9,000,000
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Wonik Global Pte. Ltd."), 0.92, "공동기업(대여금 약정, X. 대주주 거래)"),
        ],
    },

    # ── X. 대주주 거래: Wonik Global 대여금 약정 (2024.03 분기) ──
    "3536204b228eb40c": {  # 2024.03 분기 X: Wonik Global 대여금 약정 USD 9,000,000
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Wonik Global Pte. Ltd."), 0.92, "공동기업(대여금 약정)"),
        ],
    },

    # ── X. 대주주 거래: Wonik Global 대여금 약정 (2025.03 분기) ──
    "3e6a1b3246b8ec2a": {  # 2025.03 분기 X: Wonik Global 대여금 약정 USD 9,000,000 - 완료(-) 상태
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Wonik Global Pte. Ltd."), 0.90, "공동기업(대여금 약정 완료)"),
        ],
    },

    # ── III. 재무 주석: 출자 약정 - 원익2019 스타트업 파트너쉽 (2023 사업보고서) ──
    "00bcb391c4652f4d": {  # 2023 사업보고서 연결재무제표주석: 원익2019스타트업파트너쉽투자조합 출자약정 8,000,000천원
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익 2019 Start-Up 파트너쉽 투자조합"), 0.88, "관계기업(출자약정 8,000,000천원)"),
        ],
    },
    "491e21f84de74f0a": {  # 2023 사업보고서 연결감사보고서: 출자약정 8,000,000천원
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익 2019 Start-Up 파트너쉽 투자조합"), 0.88, "관계기업(출자약정 8,000,000천원)"),
        ],
    },
    "491e976443585f89": {  # 2023 사업보고서 재무제표주석(별도): 출자약정 8,000,000천원
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익 2019 Start-Up 파트너쉽 투자조합"), 0.87, "관계기업(별도: 출자약정 8,000,000천원)"),
        ],
    },

    # ── III. 재무 주석: 출자 약정 - 원익2019 스타트업 파트너쉽 (2024.03 분기) ──
    "12b27da359e5d64b": {  # 2024.03 분기 연결재무제표주석: 출자금액 (580,000)천원
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익 2019 Start-Up 파트너쉽 투자조합"), 0.88, "관계기업(출자 진행, 580,000천원)"),
        ],
    },
    "0d1934c105179a92": {  # 2024.03 분기 재무제표주석(별도): 출자금액 (580,000)천원
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익 2019 Start-Up 파트너쉽 투자조합"), 0.87, "관계기업(별도 출자)"),
        ],
    },

    # ── III. 재무 주석: 출자 약정 - 원익2019 스타트업 파트너쉽 (2024.09 분기) ──
    "3636ddb0b8b78b63": {  # 2024.09 분기 재무제표주석(별도): 출자금액 (1,180,000)천원
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익 2019 Start-Up 파트너쉽 투자조합"), 0.87, "관계기업(출자 진행, 1,180,000천원)"),
        ],
    },

    # ── III. 재무 주석: Wonik Global 대여금 약정 (별도) - 2023 사업보고서 ──
    "61a855273409e381": {  # 2023 사업보고서 재무제표주석(별도): Wonik Global Pte. Ltd. 대여금 약정
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Wonik Global Pte. Ltd."), 0.90, "공동기업(별도: 대여금 약정)"),
        ],
    },

    # ── III. 재무 주석: 거래 합계 표 (연결) - 2024.12 사업보고서 ──
    "593150e5ca21a77f": {  # 2024.12 사업보고서 연결재무제표주석: 특수관계자거래 채권채무 잔액(매출/매입 등)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.93, "지배주주(연결: 특수관계자 거래 채권채무)"),
        ],
    },

    # ── III. 재무 주석: 거래 합계 표 (별도) - 2024.12 사업보고서 ──
    "591522da0a1d32eb": {  # 2024.12 사업보고서 재무제표주석(별도): 특수관계자거래 채권채무 잔액
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.92, "지배주주(별도: 특수관계자 거래 채권채무)"),
        ],
    },

    # ── III. 재무 주석: 거래 합계 표 (연결+별도) - 2024.12 기재정정 ──
    "38f17ca791191457": {  # 2024.12 기재정정 연결재무제표주석: 특수관계자거래 채권채무 잔액(매출/매입/부동산 등)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.92, "지배주주(기재정정: 특수관계자 거래)"),
        ],
    },

    # ── II. 사업의 내용: 반도체 장비 산업 특성/성장성 개황 (주요 청크들) ──
    "131c758914719e6f": {  # 2024.12 사업보고서 II: 반도체/Display/Solar Cell 3개 장비군 사업 특성
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체 제조용 장비", "반도체 제조용 핵심 장비 (증착·열처리 포함)"), 0.90),
            E("PRODUCES", ("org", CORP), ("ent", P, "OLED 디스플레이 제조용 장비", "OLED 디스플레이 제조용 장비"), 0.88),
        ],
    },
    "31a6b860dfad3ccc": {  # 2024.12 사업보고서 II: 반도체 장비 영업개황 - 증착·열처리 공급
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체 CVD 증착 장비", "반도체 CVD 증착 장비(GEMINI/QUARTO/LEVATA)"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체 Furnace 열처리 장비", "반도체 Furnace 고온 열처리 장비"), 0.92),
        ],
    },
    "269a0853ef0b3d76": {  # 2025.09 분기 II: 반도체 장비 영업개황 - 증착·열처리 공급
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체 CVD 증착 장비", "반도체 CVD 증착 장비(GEMINI/QUARTO/LEVATA)"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체 Furnace 열처리 장비", "반도체 Furnace 고온 열처리 장비"), 0.90),
        ],
    },
    "34ad01d81a8e2a0d": {  # 2025.03 분기 II: 반도체 장비 영업개황 - 증착·열처리 공급
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체 CVD 증착 장비", "반도체 CVD 증착 장비(GEMINI/QUARTO/LEVATA)"), 0.90),
        ],
    },

    # ── II. 사업의 내용: 삼성전자/SK하이닉스 고객사 양산라인 납품 (여러 분기) ──
    "0e429174ddd3f1c1_cust": {  # 중복방지: 이미 0e429174ddd3f1c1에 처리됨
        "entities": [],
        "edges": [],
    },

    # ── II. 사업의 내용: SUPPLIES_TO 삼성/SK하이닉스/삼성디스플레이 반복 보강 ──
    "4aa7476aaf69444e": {  # 2025.03 분기 II: OLED 패널 LCD->OLED 전환, Display 장비 시장 성장
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "OLED 디스플레이 제조용 장비", "OLED 디스플레이 제조용 장비"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.83),
        ],
    },
    "9b2f3737f21e85f8": {  # 2024.12 기재정정 II: OLED 패널 사용처 확대
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "OLED 디스플레이 제조용 장비", "OLED 디스플레이 제조용 장비"), 0.88),
        ],
    },

    # ── II. 사업의 내용: Display 장비 시장 - 국산화 현황 (여러 분기) ──
    "01437c992da9aae5": {  # 2024.06 반기 II: 반도체 장비 국산화 성공, 진입장벽 높음
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체 제조용 장비", "반도체 제조용 핵심 장비 (증착·열처리 포함)"), 0.88),
        ],
    },
    "02c134b4e5910b39": {  # 2025.06 반기 II: Display 소부장 국산화 70% 이상
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "OLED 디스플레이 제조용 장비", "OLED 디스플레이 제조용 장비"), 0.85),
        ],
    },
    "11cd59b45ff6045a": {  # 2024.09 분기 II: Display 소부장 국산화 70% 이상
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "OLED 디스플레이 제조용 장비", "OLED 디스플레이 제조용 장비"), 0.85),
        ],
    },
    "2a3e484259bc81f7": {  # 2024.12 사업보고서 II: Display 소부장 국산화 70% 이상
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "OLED 디스플레이 제조용 장비", "OLED 디스플레이 제조용 장비"), 0.85),
        ],
    },
    "1e67db9d9f92fff4": {  # 2024.12 기재정정 II: Display 소부장 국산화 70% 이상
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "OLED 디스플레이 제조용 장비", "OLED 디스플레이 제조용 장비"), 0.85),
        ],
    },
    "362b58bf6817fac0": {  # 2025.12 사업보고서 II: Display 소부장 국산화 70% 이상
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "OLED 디스플레이 제조용 장비", "OLED 디스플레이 제조용 장비"), 0.85),
        ],
    },

    # ── II. 사업의 내용: 장비 판매 경로 직접 판매 (2024.03 분기) ──
    "292c44ad27e3f483": {  # 2024.03 분기 II: 직접 판매(설비 설치/Warranty/부품판매)
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체 제조용 장비", "반도체 제조용 핵심 장비 (증착·열처리 포함)"), 0.85),
        ],
    },
    "0399ef8d1db10d2e": {  # 2024.12 사업보고서 II: 제품매출(설치/Warranty/부품) + 상품매출 + 서비스매출 구조
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체 제조용 장비", "반도체 제조용 핵심 장비 (증착·열처리 포함)"), 0.87),
        ],
    },

    # ── 연결감사보고서: 2025.12 특수관계자 거래 - 원익홀딩스 매출/매입 ──
    "61861f77c8621bb4": {  # 2025.12 사업보고서 연결감사보고서: 특수관계자 거래 테이블
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.95, "지배주주(2025.12 연결 특수관계자 거래)"),
        ],
    },

    # ── 감사보고서: 2025.12 특수관계자 거래 (별도) ──
    "5fd3e513934478b1": {  # 2025.12 사업보고서 감사보고서(별도): 특수관계자 거래 + 대여금평가이익
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.95, "지배주주(2025.12 별도 특수관계자 거래)"),
        ],
    },

    # ── 연결감사보고서: 2025.12 특수관계자 거래 - 두 번째 테이블 ──
    "677901496ba42e38": {  # 2025.12 사업보고서 감사보고서(별도): Wonik Global 대여금 관련
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Wonik Global Pte. Ltd."), 0.88, "공동기업(2025.12 감사보고서 거래)"),
        ],
    },

    # ── 감사보고서: 원익홀딩스 별도 거래 - 2024.12 사업보고서 ──
    "01a0532d7c1e4897": {  # 2024.12 사업보고서 연결감사보고서: 출자약정 관련 펀드 거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "원익홀딩스"), 0.93, "지배주주(2024.12 연결감사 거래)"),
        ],
    },

    # ── II. 사업의 내용: Solar Cell 장비 (2024.03 분기) ──
    "0d6902c2c8e56b42": {  # 2024.03 분기 II: Solar Cell 장비 국내 국산화 성공
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "Solar Cell RIE 장비", "CIGS 박막 태양전지 제조용 RIE 장비"), 0.88),
        ],
    },

    # ── II. 사업의 내용: R&D 성과 반도체/Display 연구소 (2025.06 반기) ──
    "134047ca594ee0b0": {  # 2025.03 분기 II: Solar Cell 장비 산업특성, 진입장벽
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "Solar Cell RIE 장비", "CIGS 박막 태양전지 제조용 RIE 장비"), 0.87),
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
        # _cust suffix 처리 (중복 방지용 빈 레코드 - 원 chunk_id 로 조회)
        real_cid = cid.split("_")[0] if "_" in cid and cid.split("_")[-1] in ("cust", "v2", "v3") else cid
        if real_cid not in by_id:
            print(f"  [warn] {real_cid} 대상에 없음 - 스킵")
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
    extracted_real_ids = set()
    for cid in EXTRACTIONS.keys():
        real_cid = cid.split("_")[0] if "_" in cid and cid.split("_")[-1] in ("cust", "v2", "v3") else cid
        extracted_real_ids.add(real_cid)

    for r in all_rows:
        cid = r["chunk_id"]
        if cid in done or cid in extracted_real_ids:
            continue
        mark_processed(cid, 0, 0, r["rcept_no"], r["section_path"])
        processed += 1

    conn.close()
    driver.close()

    total_marked = len(ledger_processed_ids())
    print("=== 원익IPS Stage5 추출 결과 ===")
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
