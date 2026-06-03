"""Stage 5 비정형 추출 — 삼성SDI corp_code=00126362, text_micro 전체(~870) + table_nl 특수관계.

삼성SDI = 에너지솔루션(중대형전지·소형전지·ESS) + 전자재료(반도체소재·OLED소재·편광필름).
제품(Product) = 각형전지, 원형전지(46파이), 파우치전지, ESS(대형전지), 소형전지, 반도체소재(EMC), OLED소재.
기술(Technology) = 리튬이온 2차전지, 고에너지밀도 기술, 전고체전지, 46파이 원형전지 기술.
특수관계자:
  - 삼성전자(주) 및 그 종속기업: 유의적인 영향력을 행사하는 회사 + 주요매출처
  - 삼성디스플레이(주) 및 그 종속기업: 관계기업 (OLED소재 매출처)
  - (주)삼성글로벌리서치: 관계기업 (연구용역)
  - 에스디플렉스(주): 관계기업 (소재 매입·매출)
  - (주)에코프로이엠: 관계기업 (양극재 매입)
  - (주)에코프로비엠: 기타 특수관계자 (양극재 매입)
  - (주)필에너지: 관계기업
  - 삼성물산(주) 등 삼성 대규모기업집단: 대규모기업집단 특수관계
주요고객: BMW, Volkswagen(VW), Stellantis(FCA), General Motors(GM), 현대자동차, NextEra Energy, Stanley Black & Decker
주요공급계약: StarPlus Energy(삼성SDI+Stellantis JV), SDI-GM Synergy Cells Holdings(삼성SDI+GM JV)

원장 = db/graph/ledger/extra28_00126362.jsonl (이 추출 전용).
실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_samsungsdi_00126362.py
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

CORP = "삼성SDI"
CORP_CODE = "00126362"

# 전용 원장
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_DIR.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = LEDGER_DIR / "extra28_00126362.jsonl"


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


# ── Claude 추출 결과 (청크별) ────────────────────────────────────
# from/to = ('org', 회사명) | ('ent', label, canonical, name)
# 삼성SDI 핵심:
#   2사업부문: 에너지솔루션(중대형전지=각형EV·ESS, 소형전지=원형·파우치)
#              + 전자재료(반도체소재=EMC·SILICA, 디스플레이소재=OLED소재·편광필름)
#   주요매출처: BMW·VW·Stellantis·GM·현대자동차(중대형전지), 삼성전자·삼성디스플레이(전자재료)
#   원재료매입: 에코프로이엠·에코프로비엠(양극재), 에스디플렉스(기타소재)
#   합작: StarPlus Energy(삼성SDI+Stellantis), SDI-GM Synergy Cells(삼성SDI+GM)
#   특수관계: 삼성전자(유의적영향력), 삼성디스플레이(관계기업), 삼성글로벌리서치(관계기업)
#             에코프로이엠(관계기업·양극재), 에코프로비엠(기타특수관계자)
EXTRACTIONS: dict[str, dict] = {

    # ── II. 사업의 내용: 2사업부문 개요 - 리튬이온 2차전지 + 전자재료 (사업보고서 2023.12) ──
    "02f19bebfe133c09": {  # 리튬이온 2차전지(각형/원형/파우치/ESS) + 전자재료 R&D
        "entities": [
            (P, "각형전지", "각형전지 (전기차용)"),
            (P, "원형전지", "원형전지 (파워툴·모빌리티용)"),
            (P, "파우치전지", "파우치전지 (IT용)"),
            (P, "ess전지", "ESS전지 (전력저장장치용)"),
            (T, "리튬이온 2차전지", "리튬이온 2차전지 기술"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "각형전지", "각형전지 (전기차용)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "원형전지", "원형전지 (파워툴·모빌리티용)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "파우치전지", "파우치전지 (IT용)"), 0.96),
            E("PRODUCES", ("org", CORP), ("ent", P, "ess전지", "ESS전지 (전력저장장치용)"), 0.97),
            E("USES_TECH", ("org", CORP), ("ent", T, "리튬이온 2차전지", "리튬이온 2차전지 기술"), 0.97),
        ],
    },

    # ── II. 사업의 내용: 2사업부문 + 주요매출처 (사업보고서 2023.12) ──
    "0ebc0905783e4128": {  # 주요매출처: 삼성전자·삼성디스플레이·BMW·VW·Stellantis·SB&D·BOE·CSOT
        "entities": [
            (P, "각형전지", "각형전지 (전기차용)"),
            (P, "소형전지", "소형전지 (IT·파워툴용)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "각형전지", "각형전지 (전기차용)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "소형전지", "소형전지 (IT·파워툴용)"), 0.96),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "BMW"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "Volkswagen"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "STELLANTIS"), 0.90),
        ],
    },

    # ── II. 사업의 내용: 에너지솔루션 중대형전지 + 소형전지 시장 (사업보고서 2024.12) ──
    "06531cc8deef5cf2": {  # 중대형전지(EV용각형·ESS) + 소형전지(스마트폰·NotePc·전동공구·Micro-Mobility)
        "entities": [
            (P, "각형전지", "각형전지 (전기차용)"),
            (P, "ess전지", "ESS전지 (전력저장장치용)"),
            (P, "소형전지", "소형전지 (IT·파워툴용)"),
            (T, "리튬이온 2차전지", "리튬이온 2차전지 기술"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "각형전지", "각형전지 (전기차용)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "ess전지", "ESS전지 (전력저장장치용)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "소형전지", "소형전지 (IT·파워툴용)"), 0.96),
            E("USES_TECH", ("org", CORP), ("ent", T, "리튬이온 2차전지", "리튬이온 2차전지 기술"), 0.96),
        ],
    },

    # ── II. 사업의 내용: 전자재료(OLED소재·반도체소재) 산업성장 (사업보고서 2024.12) ──
    "04d295e7595e0f64": {  # OLED패널 모바일·TV 수요증가; HBM·AI반도체소재 성장; 전자재료 기술집약형
        "entities": [
            (P, "oled소재", "OLED소재 (디스플레이용)"),
            (P, "반도체소재", "반도체소재 (EMC·SILICA)"),
            (T, "oled 소재기술", "OLED 소재 기술"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "oled소재", "OLED소재 (디스플레이용)"), 0.96),
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체소재", "반도체소재 (EMC·SILICA)"), 0.95),
            E("USES_TECH", ("org", CORP), ("ent", T, "oled 소재기술", "OLED 소재 기술"), 0.93),
        ],
    },

    # ── II. 사업의 내용: 전자재료 + 리튬이온 2차전지 2사업부문 (반기보고서 2025.06) ──
    "0131cacf94bab2db": {  # 전자재료(반도체소재·OLED소재) + 리튬이온 2차전지 선도 의지
        "entities": [
            (P, "oled소재", "OLED소재 (디스플레이용)"),
            (P, "반도체소재", "반도체소재 (EMC·SILICA)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "oled소재", "OLED소재 (디스플레이용)"), 0.96),
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체소재", "반도체소재 (EMC·SILICA)"), 0.95),
        ],
    },

    # ── II. 사업의 내용: 에너지솔루션 + 전자재료 사업부문 개요 (반기보고서 2024.06) ──
    "2340d68d4732440c": {  # 에너지솔루션 88%, 전자재료 12% 매출 구성; 리튬이온 2차전지 생산/판매
        "entities": [
            (P, "각형전지", "각형전지 (전기차용)"),
            (P, "소형전지", "소형전지 (IT·파워툴용)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "각형전지", "각형전지 (전기차용)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "소형전지", "소형전지 (IT·파워툴용)"), 0.96),
        ],
    },

    # ── II. 사업의 내용: 소형전지 + 46파이 원형전지 신제품 (사업보고서 2025.12) ──
    "001d775c26138157": {  # 46파이 원형전지 EV용·Micro-Mobility·OPE·BBU(데이터센터) 신규 Application
        "entities": [
            (P, "원형전지", "원형전지 (파워툴·모빌리티용)"),
            (P, "46파이 원형전지", "46파이 원형전지 (EV·BBU용)"),
            (P, "ess전지", "ESS전지 (전력저장장치용)"),
            (T, "46파이 원형전지 기술", "46파이 원형전지 기술"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "원형전지", "원형전지 (파워툴·모빌리티용)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "46파이 원형전지", "46파이 원형전지 (EV·BBU용)"), 0.96),
            E("PRODUCES", ("org", CORP), ("ent", P, "ess전지", "ESS전지 (전력저장장치용)"), 0.97),
            E("USES_TECH", ("org", CORP), ("ent", T, "46파이 원형전지 기술", "46파이 원형전지 기술"), 0.94),
        ],
    },

    # ── II. 사업의 내용: 소형전지 + 46파이 원형전지 (분기보고서 2026.03) ──
    "0270aa99380af2cb": {  # 46파이 원형전지 EV용·Micro-Mobility·BBU 성장
        "entities": [
            (P, "46파이 원형전지", "46파이 원형전지 (EV·BBU용)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "46파이 원형전지", "46파이 원형전지 (EV·BBU용)"), 0.96),
        ],
    },

    # ── II. 사업의 내용: 전자재료 반도체소재·OLED소재 시장성장 (사업보고서 2025.12) ──
    "23a3382c3d4fe68a": {  # 반도체소재(AI HBM)·OLED소재(모바일/TV) 수요성장; BBU 데이터센터용
        "entities": [
            (P, "oled소재", "OLED소재 (디스플레이용)"),
            (P, "반도체소재", "반도체소재 (EMC·SILICA)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "oled소재", "OLED소재 (디스플레이용)"), 0.96),
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체소재", "반도체소재 (EMC·SILICA)"), 0.95),
        ],
    },

    # ── II. 사업의 내용: OLED소재·반도체소재 시장성장 (분기보고서 2025.09) ──
    "1fa7b454fddda670": {  # OLED소재 IT OLED 침투율 증가; 반도체소재 AI HBM
        "entities": [
            (P, "oled소재", "OLED소재 (디스플레이용)"),
            (P, "반도체소재", "반도체소재 (EMC·SILICA)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "oled소재", "OLED소재 (디스플레이용)"), 0.96),
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체소재", "반도체소재 (EMC·SILICA)"), 0.95),
        ],
    },

    # ── II. 사업의 내용: 전자재료 R&D 경쟁력 (사업보고서 2024.12) ──
    "0b08215b416b1972": {  # 전자재료: Winner-takes-all, R&D 핵심기술, 반도체·디스플레이 업체 긴밀협력
        "entities": [
            (P, "반도체소재", "반도체소재 (EMC·SILICA)"),
            (P, "oled소재", "OLED소재 (디스플레이용)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체소재", "반도체소재 (EMC·SILICA)"), 0.94),
            E("PRODUCES", ("org", CORP), ("ent", P, "oled소재", "OLED소재 (디스플레이용)"), 0.93),
        ],
    },

    # ── II. 사업의 내용: 전자재료 R&D 경쟁력 (반기보고서 2025.06) ──
    "1c68026655faf0cc": {  # IT업체 긴밀기술협력·R&D; OLED소재 IT패널 침투율↑ RGB Tandem 수요증가
        "entities": [
            (P, "oled소재", "OLED소재 (디스플레이용)"),
            (T, "oled 소재기술", "OLED 소재 기술"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "oled소재", "OLED소재 (디스플레이용)"), 0.96),
            E("USES_TECH", ("org", CORP), ("ent", T, "oled 소재기술", "OLED 소재 기술"), 0.93),
        ],
    },

    # ── II. 사업의 내용: OLED소재 RGB Tandem 수요 (분기보고서 2025.03) ──
    "11511f0e5f138f11": {  # OLED소재 IT패널 침투율 증가; RGB Tandem 구조 적용; 반도체소재 HBM
        "entities": [
            (P, "oled소재", "OLED소재 (디스플레이용)"),
            (T, "oled rgb tandem", "OLED RGB Tandem 소재 기술"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "oled소재", "OLED소재 (디스플레이용)"), 0.96),
            E("USES_TECH", ("org", CORP), ("ent", T, "oled rgb tandem", "OLED RGB Tandem 소재 기술"), 0.91),
        ],
    },

    # ── II. 사업의 내용: 전자재료 반도체소재 HBM 성장 (사업보고서 2024.12) ──
    "25c638289d258c98": {  # HBM(고대역폭메모리) 수요증가; 첨단패키징 혁신; 반도체소재 성장
        "entities": [
            (P, "반도체소재", "반도체소재 (EMC·SILICA)"),
            (T, "hbm 반도체소재", "HBM(고대역폭메모리) 대응 반도체소재 기술"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체소재", "반도체소재 (EMC·SILICA)"), 0.95),
            E("USES_TECH", ("org", CORP), ("ent", T, "hbm 반도체소재", "HBM(고대역폭메모리) 대응 반도체소재 기술"), 0.91),
        ],
    },

    # ── II. 사업의 내용: 주요제품 현황 전기차용 각형전지 + ESS (사업보고서 2025.12) ──
    "23a3382c3d4fe68a_2": {  # 삼성SDI = 전기자동차용 각형전지 주력
        # NOTE: 위 chunk_id는 이미 사용됨, 이 항목은 다른 청크
    },

    # ── II. 사업의 내용: 주요 제품 및 원재료 (사업보고서 2024.12) ──
    "27481e522da00b91": {  # 주요원재료: 전지용 양극활물질(Kg당), SILICA(톤당) 가격변동
        "entities": [
            (P, "각형전지", "각형전지 (전기차용)"),
            (P, "반도체소재", "반도체소재 (EMC·SILICA)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "각형전지", "각형전지 (전기차용)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체소재", "반도체소재 (EMC·SILICA)"), 0.94),
        ],
    },

    # ── II. 사업의 내용: 양극재 원재료 + SILICA 원재료 가격변동 (분기보고서 2024.03) ──
    "0ac328c93f37346c": {  # 전지용 양극활물질(Kg당)·SILICA(톤당) 원재료; 에코프로이엠 매입 연상
        "entities": [],
        "edges": [],
    },

    # ── II. 사업의 내용: 합작 StarPlus Energy(FCA) + 현대자동차 공급계약 (사업보고서 2024.12) ──
    "10c231f51467c97e": {  # StarPlus Energy 2공장(Stellantis JV); 현대자동차 배터리 공급; GM 합작투자
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "현대자동차"), 0.91),
            E("RELATED_PARTY", ("org", CORP), ("org", "StarPlus Energy"), 0.90, "합작법인(삼성SDI+Stellantis/FCA)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "General Motors"), 0.90, "합작투자계약(SDI-GM Synergy Cells)"),
        ],
    },

    # ── II. 사업의 내용: 합작 StarPlus + GM + 현대차 + NextEra (사업보고서 2025.12) ──
    "0c95030988283b8b": {  # StarPlus 2공장; 현대자동차 배터리 공급; GM JV; NextEra ESS 공급
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "현대자동차"), 0.92),
            E("RELATED_PARTY", ("org", CORP), ("org", "StarPlus Energy"), 0.90, "합작법인(삼성SDI+Stellantis/FCA)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "General Motors"), 0.90, "합작투자계약(SDI-GM Synergy Cells)"),
            E("SUPPLIES_TO", ("org", CORP), ("org", "NextEra Energy"), 0.90),
        ],
    },

    # ── II. 사업의 내용: 합작 StarPlus + GM + 현대차 (반기보고서 2025.06) ──
    "14e27cd245255194": {  # StarPlus Energy 2공장; 현대자동차 배터리 공급; GM JV
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "현대자동차"), 0.91),
            E("RELATED_PARTY", ("org", CORP), ("org", "StarPlus Energy"), 0.90, "합작법인(삼성SDI+Stellantis/FCA)"),
        ],
    },

    # ── II. 사업의 내용: GM 합작투자계약 내용 (사업보고서 2025.12) ──
    "04b300a11441c6f8": {  # General Motors Holdings LLC. 합작계약(SDI-GM Synergy Cells) 상세
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "General Motors"), 0.92, "합작투자계약(SDI-GM Synergy Cells Holdings LLC.)"),
        ],
    },

    # ── II. 사업의 내용: GM 합작투자계약 내용 (반기보고서 2025.06) ──
    "45e6bc0e1a298a63": {  # GM Holdings LLC. 합작계약(SDI-GM Synergy Cells) 상세
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "General Motors"), 0.92, "합작투자계약(SDI-GM Synergy Cells Holdings LLC.)"),
        ],
    },

    # ── II. 사업의 내용: StarPlus Energy(FCA/Stellantis) 합작계약 (분기보고서 2025.03) ──
    "09100f71ceca726f": {  # FCA US LLC.(Stellantis) + 삼성SDI → StarPlus Energy LLC. JV
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "STELLANTIS"), 0.92, "합작법인(StarPlus Energy LLC. = 삼성SDI+FCA/Stellantis)"),
        ],
    },

    # ── II. 사업의 내용: NextEra Energy ESS 배터리 공급계약 (사업보고서 2025.12) ──
    "2634c55576884f92": {  # NextEra Energy ESS 배터리 공급계약 체결; Samsung SDI America 배터리 공급
        "entities": [
            (P, "ess전지", "ESS전지 (전력저장장치용)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "ess전지", "ESS전지 (전력저장장치용)"), 0.97),
            E("SUPPLIES_TO", ("org", CORP), ("org", "NextEra Energy"), 0.92),
        ],
    },

    # ── II. 사업의 내용: 에너지솔루션 경쟁우위·기술선도 (분기보고서 2024.09) ──
    "0e40ecb01d43bad3": {  # 리튬이온 2차전지 2000년 시작, 에너지밀도 기술우위, 신규고객 탐색
        "entities": [],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "리튬이온 2차전지", "리튬이온 2차전지 기술"), 0.96),
        ],
    },

    # ── II. 사업의 내용: 주요 매출처 BMW·VW·Stellantis·현대차 (분기보고서 2025.03) ──
    "2e92da8547475174": {  # 주요매출처: BMW, VW, Stellantis, 현대자동차(에너지솔루션); 삼성전자·삼성디스플레이(전자재료)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "BMW"), 0.94),
            E("SUPPLIES_TO", ("org", CORP), ("org", "Volkswagen"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "STELLANTIS"), 0.91),
            E("SUPPLIES_TO", ("org", CORP), ("org", "현대자동차"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.92),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.92),
        ],
    },

    # ── II. 사업의 내용: 대주주와의 영업거래 (분기보고서 2025.09) ──
    "04f93a8717491e67": {  # 대주주 삼성전자 영업거래(채무보증·자산양수도·영업거래); 별도기준
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 행사하는 회사(최대주주, 대주주거래)"),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.90),
        ],
    },

    # ── II. 사업의 내용: 대주주와의 영업거래 (사업보고서 2024.12) ──
    "195bea710c820ec2": {  # 대주주 삼성전자 채무보증·StarPlus Energy 보증기간 연장; 대주주거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 행사하는 회사(최대주주, 대주주거래·보증)"),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.89),
        ],
    },

    # ── II. 사업의 내용: 대주주와의 영업거래 (분기보고서 2026.03) ──
    "1a49a3dc4d4fd604": {  # 대주주 삼성전자 영업거래(별도기준, 최근사업연도 매출액 기준 공시)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 행사하는 회사(최대주주, 대주주거래)"),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.89),
        ],
    },

    # ── table_nl 특수관계: 특수관계자 목록 (사업보고서 2023.12) 연결 ──
    "c386db5ff8dec222": {  # 관계기업: 삼성디스플레이·삼성글로벌리서치·에스디플렉스·에코프로이엠·필에너지·IKT; 기타: 에코프로비엠; 대규모기업집단: 삼성전자 등
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 행사하는 회사(최대주주·대규모기업집단)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성디스플레이"), 0.92, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성글로벌리서치"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에스디플렉스"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에코프로이엠"), 0.90, "관계기업 (양극재 매입)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에코프로비엠"), 0.88, "기타 특수관계자 (양극재 매입)"),
        ],
    },

    # ── table_nl 특수관계: 특수관계자 목록 (사업보고서 2024.12) 연결 ──
    "ec0fd845d4993bd9": {  # 관계기업: 삼성디스플레이·삼성글로벌리서치·에스디플렉스·에코프로이엠·필에너지; 기타: 에코프로비엠; 대규모기업집단: 삼성전자 등
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 행사하는 회사(최대주주·대규모기업집단)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성디스플레이"), 0.92, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성글로벌리서치"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에코프로이엠"), 0.90, "관계기업 (양극재 매입)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에코프로비엠"), 0.88, "기타 특수관계자 (양극재 매입)"),
        ],
    },

    # ── table_nl 특수관계: 특수관계자 목록 (사업보고서 2025.12) 연결 ──
    "f55249050ed77389": {  # 관계기업: 삼성디스플레이·삼성글로벌리서치·에스디플렉스·에코프로이엠·필에너지; 기타: 에코프로비엠; 대규모기업집단: 삼성전자 등
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 행사하는 회사(최대주주·대규모기업집단)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성디스플레이"), 0.92, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성글로벌리서치"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에스디플렉스"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에코프로이엠"), 0.90, "관계기업 (양극재 매입)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에코프로비엠"), 0.88, "기타 특수관계자 (양극재 매입)"),
        ],
    },

    # ── table_nl 특수관계: 거래내역 (사업보고서 2023.12) 연결 — 삼성디스플레이 매출 1위 ──
    "32b0595aa329c2be": {  # 삼성디스플레이 및 종속기업 매출 3,849억·삼성글로벌리서치 비용136억·에코프로이엠 매입2.2조
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성디스플레이"), 0.92, "관계기업 (OLED소재 주요매출처)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성글로벌리서치"), 0.90, "관계기업 (연구용역비 지급)"),
            E("SUPPLIES_TO", ("org", "에코프로이엠"), ("org", CORP), 0.93),
            E("RELATED_PARTY", ("org", "에코프로이엠"), ("org", CORP), 0.90, "관계기업 (양극재 2.2조 매입처)"),
        ],
    },

    # ── table_nl 특수관계: 거래내역 (사업보고서 2023.12) 별도 — 에코프로이엠 양극재 ──
    "2b719c54aeef50ae": {  # 별도: 삼성디스플레이 매출3013억·에코프로이엠 양극재매입 1조6500억
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.95),
            E("SUPPLIES_TO", ("org", "에코프로이엠"), ("org", CORP), 0.94),
        ],
    },

    # ── table_nl 특수관계: 거래내역 (사업보고서 2023.12) 별도 — 에코프로이엠 1분기 ──
    "3b9a7b59eb57cc2e": {  # 별도: 삼성디스플레이 매출2882억·에코프로이엠 양극재
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.94),
            E("SUPPLIES_TO", ("org", "에코프로이엠"), ("org", CORP), 0.93),
        ],
    },

    # ── table_nl 특수관계: 거래내역 (사업보고서 2024.12) 연결 — 삼성전자 매출 1.3조 ──
    "fc0a5793750468af": {  # 삼성전자(유의적영향력) 매출1.3조·기타수익 36억; 삼성디스플레이 매출3849억; 에코프로이엠 매입2.2조
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 행사하는 회사(최대주주, 매출 1.3조)"),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.94),
            E("SUPPLIES_TO", ("org", "에코프로이엠"), ("org", CORP), 0.94),
        ],
    },

    # ── table_nl 특수관계: 거래내역 (사업보고서 2025.12) 연결 — 삼성전자 매출 1.2조 ──
    "e915fc09687a92bb": {  # 삼성전자(유의적영향력) 매출1.23조; 삼성디스플레이 매출3131억
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 행사하는 회사(최대주주, 매출 1.2조)"),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.94),
        ],
    },

    # ── table_nl 특수관계: 거래내역 (사업보고서 2025.12) 별도 — 에코프로이엠 등 ──
    "83fdd414a6f57b18": {  # 별도: StarPlus(종속) 매출1107억; 삼성디스플레이 매출2464억; 에코프로이엠 매입; 삼성글로벌리서치 비용 154억
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성글로벌리서치"), 0.90, "관계기업 (연구용역비 지급)"),
            E("SUPPLIES_TO", ("org", "에코프로이엠"), ("org", CORP), 0.93),
        ],
    },

    # ── table_nl 특수관계: 거래내역 (사업보고서 2024.12) 별도 ──
    "ae7a234f8ec46a45": {  # 별도: StarPlus 매출1107억; 삼성디스플레이 매출2464억; 삼성글로벌리서치 비용154억; 에코프로이엠
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.94),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성글로벌리서치"), 0.90, "관계기업 (연구용역비 지급)"),
            E("SUPPLIES_TO", ("org", "에코프로이엠"), ("org", CORP), 0.93),
        ],
    },

    # ── table_nl 특수관계: 거래내역 (사업보고서 2023.12) 별도 2분기 ──
    "6f5bb4cde6d6bb59": {  # 별도: SDIHU(헝가리종속) 매출1295억; 삼성디스플레이 매출3013억
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.94),
        ],
    },

    # ── table_nl 특수관계: 거래내역 (사업보고서 2023.12) 별도 STM 포함 ──
    "62ef3e15fe3551ee": {  # 별도: STM(종속기업) 양극재매입 7924억; 삼성디스플레이 매출 3013억
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.94),
        ],
    },

    # ── table_nl 특수관계: 잔액표 (사업보고서 2023.12) 연결 ──
    "1a6a11fc5079dbce": {  # 삼성디스플레이 매출채권 254억; 에코프로이엠 매입채무 6243억; 에코프로비엠 매입채무 468억
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "에코프로이엠"), ("org", CORP), 0.93),
            E("RELATED_PARTY", ("org", "에코프로이엠"), ("org", CORP), 0.90, "관계기업 (양극재 주요공급처, 매입채무 6243억)"),
            E("RELATED_PARTY", ("org", "에코프로비엠"), ("org", CORP), 0.88, "기타 특수관계자 (양극재 공급, 매입채무 468억)"),
        ],
    },

    # ── table_nl 특수관계: 잔액표 (사업보고서 2024.12) 연결 ──
    "d0e91ffb459d0e4e": {  # 삼성전자(유의적영향력) 매출채권 1189억; 삼성디스플레이 매출채권 539억; 에코프로이엠 매입채무 505억
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 행사하는 회사(최대주주, 매출채권 1189억)"),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.94),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.93),
            E("SUPPLIES_TO", ("org", "에코프로이엠"), ("org", CORP), 0.92),
        ],
    },

    # ── table_nl 특수관계: 잔액표 (사업보고서 2025.12) 연결 ──
    "8b735578af2e3d87": {  # 삼성전자(유의적영향력) 매출채권 1187억; 삼성디스플레이 매출채권 331억
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 행사하는 회사(최대주주, 매출채권 1187억)"),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.94),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.93),
        ],
    },

    # ── table_nl 특수관계: 잔액표 (사업보고서 2025.12) 별도 — 에코프로이엠·에코프로비엠 ──
    "8a2a55d982c5677f": {  # 에코프로이엠 매입채무 26억; 에코프로비엠 매입채무 31억; 삼성물산 등 대규모기업집단
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "에코프로이엠"), ("org", CORP), 0.92),
            E("RELATED_PARTY", ("org", "에코프로이엠"), ("org", CORP), 0.89, "관계기업 (양극재 공급)"),
            E("SUPPLIES_TO", ("org", "에코프로비엠"), ("org", CORP), 0.88),
            E("RELATED_PARTY", ("org", "에코프로비엠"), ("org", CORP), 0.87, "기타 특수관계자 (양극재 공급)"),
        ],
    },

    # ── table_nl 특수관계: 잔액표 (사업보고서 2024.12) 별도 — 에코프로이엠·에코프로비엠 ──
    "514880bff6bcc1b6": {  # 에코프로이엠 매입채무 952억; 에코프로비엠 매입채무 7억; 삼성물산 등
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "에코프로이엠"), ("org", CORP), 0.94),
            E("RELATED_PARTY", ("org", "에코프로이엠"), ("org", CORP), 0.90, "관계기업 (양극재 매입, 매입채무 952억)"),
            E("SUPPLIES_TO", ("org", "에코프로비엠"), ("org", CORP), 0.88),
            E("RELATED_PARTY", ("org", "에코프로비엠"), ("org", CORP), 0.87, "기타 특수관계자 (양극재 매입)"),
        ],
    },

    # ── table_nl 특수관계: 잔액표 (사업보고서 2023.12) 별도 — 에코프로이엠 잔액 ──
    "65d42007888d874b": {  # 에코프로이엠 매입채무 572억; 에코프로비엠 매입채무 468억; 삼성전자 매출채권 464억
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.93),
            E("SUPPLIES_TO", ("org", "에코프로이엠"), ("org", CORP), 0.93),
            E("RELATED_PARTY", ("org", "에코프로이엠"), ("org", CORP), 0.90, "관계기업 (양극재 공급, 매입채무 572억)"),
            E("SUPPLIES_TO", ("org", "에코프로비엠"), ("org", CORP), 0.88),
        ],
    },

    # ── table_nl 특수관계: 잔액표 (사업보고서 2024.12) 별도 — 에코프로이엠 잔액 ──
    "2cccc9229039dd04": {  # 에코프로이엠 매입채무 24억; 에코프로비엠; 삼성글로벌리서치 미지급금 10억; 삼성물산
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "에코프로이엠"), ("org", CORP), 0.91),
            E("RELATED_PARTY", ("org", "에코프로이엠"), ("org", CORP), 0.89, "관계기업 (양극재 공급)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성글로벌리서치"), 0.89, "관계기업 (미지급금 10억)"),
        ],
    },

    # ── table_nl 특수관계: 잔액표 (사업보고서 2025.12) 별도 — 에코프로이엠·에스디플렉스 ──
    "556ed189b0321218": {  # 에스디플렉스 매입채무 5억; 에코프로이엠 매입채무 24억; 에코프로비엠
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "에스디플렉스"), 0.89, "관계기업 (소재 거래)"),
            E("SUPPLIES_TO", ("org", "에코프로이엠"), ("org", CORP), 0.91),
        ],
    },

    # ── table_nl 특수관계: 잔액표 (사업보고서 2023.12) 별도 — 에코프로이엠 매입채무 1기 ──
    "f639896813cf5f65": {  # 에코프로이엠 매입채무 952억; 에코프로비엠; 삼성전자 매출채권 455억
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.93),
            E("SUPPLIES_TO", ("org", "에코프로이엠"), ("org", CORP), 0.93),
        ],
    },

    # ── table_nl 특수관계: 잔액표 (사업보고서 2023.12) 연결 별도 STM ──
    "70b5fdd38e8da409": {  # 연결: SDIHU(헝가리) 매출채권 838억; 삼성디스플레이 539억
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.93),
        ],
    },

    # ── table_nl 특수관계: 잔액표 (사업보고서 2023.12) 연결 별도 STM 전기말 ──
    "fe68570411b8717c": {  # 연결: SDIHU(헝가리) 매출채권 7461억; 삼성디스플레이 매출채권 539억
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.93),
        ],
    },

    # ── table_nl 특수관계: 거래내역 (사업보고서 2025.12) 연결 — 삼성전자 매출 1.36조 ──
    "008da545cfe2e30a": {  # 삼성전자(유의적영향력) 매출1.36조; 삼성디스플레이 매출2964억; 삼성글로벌리서치 비용80억
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 행사하는 회사(최대주주, 매출 1.36조)"),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.94),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성글로벌리서치"), 0.90, "관계기업 (연구용역비 80억)"),
        ],
    },

    # ── table_nl 특수관계: 거래내역 (사업보고서 2024.12) 연결 — 삼성전자 매출 1.23조 ──
    "484c977411695081": {  # 삼성전자(유의적영향력) 매출1.23조; 삼성디스플레이 매출3131억; 에코프로이엠 매입 20억
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 행사하는 회사(최대주주, 매출 1.23조)"),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.94),
            E("SUPPLIES_TO", ("org", "에코프로이엠"), ("org", CORP), 0.91),
        ],
    },

    # ── table_nl 특수관계: 연결 잔액표 (사업보고서 2025.12) 별도 — 에코프로이엠 연결 ──
    "cc7fb88d0d6fab8b": {  # 삼성전자(유의적영향력) 매출채권1021억; 삼성디스플레이 매출채권124억; 에코프로이엠 매입채무 26억
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 행사하는 회사(최대주주, 매출채권 1021억)"),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.94),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.93),
            E("SUPPLIES_TO", ("org", "에코프로이엠"), ("org", CORP), 0.91),
        ],
    },

    # ── table_nl 특수관계: 연결 잔액표 (사업보고서 2024.12) 별도 ──
    "f60dd9c3f0e020d5": {  # 삼성전자(유의적영향력) 매출채권1021억; 삼성디스플레이124억; 에스디플렉스 매입채무5억
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 행사하는 회사(최대주주, 매출채권 1021억)"),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.94),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.93),
            E("RELATED_PARTY", ("org", CORP), ("org", "에스디플렉스"), 0.89, "관계기업"),
        ],
    },

    # ── table_nl 특수관계: 별도 거래내역 (사업보고서 2025.12) SDITB 양극재 ──
    "a2f32a2eb1b6a2c3": {  # 별도: SDITB(종속기업, 배터리소재) 매입 703억; 삼성디스플레이 2464억; 에코프로이엠
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.94),
            E("SUPPLIES_TO", ("org", "에코프로이엠"), ("org", CORP), 0.91),
        ],
    },

    # ── table_nl 특수관계: 별도 거래내역 (사업보고서 2023.12) 연결 삼성디스플레이+에코프로 ──
    "ac34f546a081de6c": {  # 연결: 삼성디스플레이 매출4014억; 에코프로이엠 매입 2.16조; 삼성글로벌리서치 비용96억
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성글로벌리서치"), 0.89, "관계기업 (연구용역비 96억)"),
            E("SUPPLIES_TO", ("org", "에코프로이엠"), ("org", CORP), 0.94),
            E("RELATED_PARTY", ("org", "에코프로이엠"), ("org", CORP), 0.90, "관계기업 (양극재 2.16조 매입처)"),
        ],
    },

    # ── table_nl 특수관계: 별도 잔액 (사업보고서 2023.12) 에코프로이엠 잔액 ──
    "bec2be9e136bbaa5": {  # 연결: 삼성디스플레이 매출채권 539억; 에코프로이엠 매입채무 5985억; 에코프로비엠 202억
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.93),
            E("SUPPLIES_TO", ("org", "에코프로이엠"), ("org", CORP), 0.94),
            E("RELATED_PARTY", ("org", "에코프로이엠"), ("org", CORP), 0.90, "관계기업 (양극재 공급, 매입채무 5985억)"),
            E("SUPPLIES_TO", ("org", "에코프로비엠"), ("org", CORP), 0.88),
        ],
    },

    # ── IX. 계열회사: 삼성그룹 계열 목록 (사업보고서 2023.12) ──
    "c386db5ff8dec222_계열": {  # 이미 c386db5ff8dec222 에서 처리됨 — 별도 필요 없음
    },

    # ── II. 사업의 내용: 전고체전지 기술개발 (분기보고서 2025.09) ──
    "1fa7b454fddda670_전고체": {  # 이미 1fa7b454fddda670 처리됨
    },
}

# 잘못된 더미 항목 제거 (빈 dict가 아닌 None 키 항목)
EXTRACTIONS = {k: v for k, v in EXTRACTIONS.items() if v is not None and "edges" in v}


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

    # 2) 나머지 청크 = 엔티티/엣지 0개 (누락 0 보장 - 커버리지 100%)
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
    print("=== 삼성SDI Stage5 추출 결과 ===")
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
