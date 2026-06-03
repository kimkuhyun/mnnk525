"""Stage 5 비정형 추출 — 삼성중공업 corp_code=00126478, text_micro 전체(~1,067) + table_nl 특수관계.

삼성중공업 = 1974년 설립, 거제 소재 조선·해양플랜트 전문 조선사.
주요 제품: LNG선, LNG-FSRU, LNG-FPSO(FLNG), 쇄빙유조선, 초대형컨테이너선, 드릴십, 해양플랫폼.
기술: 고부가가치선 디지털 기술 접목, 해양플랜트 엔지니어링.
특수관계자: 삼성전자, 삼성생명, 삼성화재, 삼성SDS, 삼성물산, 삼성전기, 삼성SDI, 삼성디스플레이,
            삼성웰스토리, KC LNG Tech, Zvezda Samsung Heavy Industries LLC(관계기업).
종속기업: 국내 2개사(블록제작), 해외 8개사(블록제작/해양설계/드릴십 매각목적), Curious Crete Limited(시추선 관련).

원장 = db/graph/ledger/extra28_00126478.jsonl (이 추출 전용).
실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_samsungheavy_00126478.py
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

CORP = "삼성중공업"
CORP_CODE = "00126478"

# 전용 원장
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_DIR.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = LEDGER_DIR / "extra28_00126478.jsonl"


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
# 삼성중공업: 조선·해양플랜트 전문 조선사.
# Product = LNG선, LNG-FSRU, LNG-FPSO(FLNG), 쇄빙유조선, 초대형컨테이너선, 드릴십, 해양플랫폼, FPU, 원유운반선
# Technology = 디지털선박기술, 고부가가치선박기술
# 특수관계자: 삼성 그룹 계열사들(그 밖의 특수관계자), KC LNG Tech(관계기업), Zvezda Samsung(관계기업)

EXTRACTIONS: dict[str, dict] = {

    # ═══ II. 사업의 내용: 사업 구조 — 조선해양/토건 2개 부문 ═══

    "5880a912a8b6230e": {  # 2023.12 사보: 조선해양부문 + 토건부문 사업구분, 종속회사 10개사
        "entities": [
            (P, "LNG선", "LNG운반선(LNG carrier)"),
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
            (P, "FPU", "FPU(부유식 생산설비)"),
            (P, "해양플랫폼", "해양플랫폼"),
            (P, "초대형컨테이너선", "초대형 컨테이너선"),
            (P, "원유운반선", "원유운반선"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG선", "LNG운반선(LNG carrier)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "FPU", "FPU(부유식 생산설비)"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "해양플랫폼", "해양플랫폼"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "초대형컨테이너선", "초대형 컨테이너선"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "원유운반선", "원유운반선"), 0.93),
        ],
    },

    "0dae34540af21685": {  # 2024.12 기재정정 사보: 조선해양부문/토건부문, LNG선·FPSO·해양플랫폼
        "entities": [
            (P, "LNG선", "LNG운반선(LNG carrier)"),
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
            (P, "해양플랫폼", "해양플랫폼"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG선", "LNG운반선(LNG carrier)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "해양플랫폼", "해양플랫폼"), 0.95),
        ],
    },

    "c935376accde90b8": {  # 2024.12 사보: 조선해양부문/토건부문, LNG선·FPSO·해양플랫폼
        "entities": [
            (P, "LNG선", "LNG운반선(LNG carrier)"),
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
            (P, "해양플랫폼", "해양플랫폼"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG선", "LNG운반선(LNG carrier)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "해양플랫폼", "해양플랫폼"), 0.95),
        ],
    },

    "a9d37898b01dd6fe": {  # 2025.09 분기: 조선해양/토건 사업구분
        "entities": [
            (P, "LNG선", "LNG운반선(LNG carrier)"),
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
            (P, "해양플랫폼", "해양플랫폼"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG선", "LNG운반선(LNG carrier)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "해양플랫폼", "해양플랫폼"), 0.95),
        ],
    },

    "9aa38f73650470ab": {  # 2025.03 분기: 조선해양/토건 사업구분
        "entities": [
            (P, "LNG선", "LNG운반선(LNG carrier)"),
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
            (P, "해양플랫폼", "해양플랫폼"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG선", "LNG운반선(LNG carrier)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "해양플랫폼", "해양플랫폼"), 0.95),
        ],
    },

    "f6f647f93179c8b1": {  # 2025.12 사보: 조선해양/토건 사업구분
        "entities": [
            (P, "LNG선", "LNG운반선(LNG carrier)"),
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
            (P, "해양플랫폼", "해양플랫폼"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG선", "LNG운반선(LNG carrier)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "해양플랫폼", "해양플랫폼"), 0.95),
        ],
    },

    "910071fd76473dc4": {  # 2026.03 분기: 조선해양/토건 사업구분
        "entities": [
            (P, "LNG선", "LNG운반선(LNG carrier)"),
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
            (P, "해양플랫폼", "해양플랫폼"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG선", "LNG운반선(LNG carrier)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "해양플랫폼", "해양플랫폼"), 0.95),
        ],
    },

    # ═══ II. 사업의 내용: 고부가가치선 판매전략 ═══

    "48f17ea2771d1174": {  # 2023.12 사보: LNG선·LNG-FSRU·쇄빙유조선·컨선·FPSO·드릴십 판매전략
        "entities": [
            (P, "LNG선", "LNG운반선(LNG carrier)"),
            (P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"),
            (P, "쇄빙유조선", "쇄빙유조선(Arctic Shuttle Tanker)"),
            (P, "초대형컨테이너선", "초대형 컨테이너선"),
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
            (P, "해양플랫폼", "해양플랫폼"),
            (P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG선", "LNG운반선(LNG carrier)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "쇄빙유조선", "쇄빙유조선(Arctic Shuttle Tanker)"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "초대형컨테이너선", "초대형 컨테이너선"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "해양플랫폼", "해양플랫폼"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"), 0.92),
        ],
    },

    "e92d3936efbfa485": {  # 2023.12 기재정정 사보: LNG선·FSRU·쇄빙유조선·컨선·FPSO·드릴십 판매전략
        "entities": [
            (P, "LNG선", "LNG운반선(LNG carrier)"),
            (P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"),
            (P, "쇄빙유조선", "쇄빙유조선(Arctic Shuttle Tanker)"),
            (P, "초대형컨테이너선", "초대형 컨테이너선"),
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
            (P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG선", "LNG운반선(LNG carrier)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "쇄빙유조선", "쇄빙유조선(Arctic Shuttle Tanker)"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "초대형컨테이너선", "초대형 컨테이너선"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"), 0.92),
        ],
    },

    "6e88190bab537ed3": {  # 2024.06 반기: 고부가가치선 판매전략
        "entities": [
            (P, "LNG선", "LNG운반선(LNG carrier)"),
            (P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"),
            (P, "쇄빙유조선", "쇄빙유조선(Arctic Shuttle Tanker)"),
            (P, "초대형컨테이너선", "초대형 컨테이너선"),
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
            (P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG선", "LNG운반선(LNG carrier)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "쇄빙유조선", "쇄빙유조선(Arctic Shuttle Tanker)"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "초대형컨테이너선", "초대형 컨테이너선"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"), 0.92),
        ],
    },

    "abcc0943b8ef6eb6": {  # 2024.03 분기: 고부가가치선 판매전략
        "entities": [
            (P, "LNG선", "LNG운반선(LNG carrier)"),
            (P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"),
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
            (P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG선", "LNG운반선(LNG carrier)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"), 0.92),
        ],
    },

    "f4fa8231f1125055": {  # 2024.09 분기: 고부가가치선 판매전략
        "entities": [
            (P, "LNG선", "LNG운반선(LNG carrier)"),
            (P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"),
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
            (P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG선", "LNG운반선(LNG carrier)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"), 0.92),
        ],
    },

    "93f8329272d09e77": {  # 2024.12 사보: FSRU·쇄빙유조선·컨선·FPSO·드릴십 판매전략
        "entities": [
            (P, "LNG선", "LNG운반선(LNG carrier)"),
            (P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"),
            (P, "쇄빙유조선", "쇄빙유조선(Arctic Shuttle Tanker)"),
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
            (P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG선", "LNG운반선(LNG carrier)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "쇄빙유조선", "쇄빙유조선(Arctic Shuttle Tanker)"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"), 0.92),
        ],
    },

    "193d1f396122b07a": {  # 2024.12 기재정정: FSRU·쇄빙유조선·컨선·FPSO·드릴십
        "entities": [
            (P, "LNG선", "LNG운반선(LNG carrier)"),
            (P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"),
            (P, "쇄빙유조선", "쇄빙유조선(Arctic Shuttle Tanker)"),
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
            (P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG선", "LNG운반선(LNG carrier)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "쇄빙유조선", "쇄빙유조선(Arctic Shuttle Tanker)"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"), 0.92),
        ],
    },

    "db84cfb6e362199c": {  # 2024.12 기재정정: FSRU·쇄빙유조선·컨선·FPSO·드릴십
        "entities": [
            (P, "LNG선", "LNG운반선(LNG carrier)"),
            (P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"),
            (P, "쇄빙유조선", "쇄빙유조선(Arctic Shuttle Tanker)"),
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
            (P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG선", "LNG운반선(LNG carrier)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "쇄빙유조선", "쇄빙유조선(Arctic Shuttle Tanker)"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"), 0.92),
        ],
    },

    "14578a29430f95eb": {  # 2025.09 분기: FSRU·쇄빙유조선·컨선·FPSO·드릴십
        "entities": [
            (P, "LNG선", "LNG운반선(LNG carrier)"),
            (P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"),
            (P, "쇄빙유조선", "쇄빙유조선(Arctic Shuttle Tanker)"),
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
            (P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG선", "LNG운반선(LNG carrier)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "쇄빙유조선", "쇄빙유조선(Arctic Shuttle Tanker)"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"), 0.92),
        ],
    },

    "a2ccda7b8614d72e": {  # 2025.03 분기: FSRU·쇄빙유조선·컨선·FPSO·드릴십
        "entities": [
            (P, "LNG선", "LNG운반선(LNG carrier)"),
            (P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"),
            (P, "쇄빙유조선", "쇄빙유조선(Arctic Shuttle Tanker)"),
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
            (P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG선", "LNG운반선(LNG carrier)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "쇄빙유조선", "쇄빙유조선(Arctic Shuttle Tanker)"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"), 0.92),
        ],
    },

    "c5da6e575d3a710c": {  # 2025.06 반기: FSRU·쇄빙유조선·컨선·FPSO·드릴십
        "entities": [
            (P, "LNG선", "LNG운반선(LNG carrier)"),
            (P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"),
            (P, "쇄빙유조선", "쇄빙유조선(Arctic Shuttle Tanker)"),
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
            (P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG선", "LNG운반선(LNG carrier)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "쇄빙유조선", "쇄빙유조선(Arctic Shuttle Tanker)"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"), 0.92),
        ],
    },

    "0170d420dd0f4512": {  # 2025.12 사보: FSRU·쇄빙유조선·컨선·FPSO·드릴십
        "entities": [
            (P, "LNG선", "LNG운반선(LNG carrier)"),
            (P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"),
            (P, "쇄빙유조선", "쇄빙유조선(Arctic Shuttle Tanker)"),
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
            (P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG선", "LNG운반선(LNG carrier)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "쇄빙유조선", "쇄빙유조선(Arctic Shuttle Tanker)"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"), 0.92),
        ],
    },

    "4b08933764a04f4a": {  # 2026.03 분기: FSRU·쇄빙유조선·컨선·FPSO·드릴십
        "entities": [
            (P, "LNG선", "LNG운반선(LNG carrier)"),
            (P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"),
            (P, "쇄빙유조선", "쇄빙유조선(Arctic Shuttle Tanker)"),
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
            (P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG선", "LNG운반선(LNG carrier)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FSRU", "LNG-FSRU(부유식 LNG 저장·재기화 설비)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "쇄빙유조선", "쇄빙유조선(Arctic Shuttle Tanker)"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"), 0.92),
        ],
    },

    # ═══ II. 사업의 내용: R&D — 고부가가치 선박 디지털기술 접목 ═══

    "040f81e3d1a2c812": {  # 2024.12 기재정정: R&D 디지털기술 접목 고부가가치 선박 및 해양 설비
        "entities": [
            (T, "디지털선박기술", "고부가가치 선박·해양 설비 디지털 기술"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "디지털선박기술", "고부가가치 선박·해양 설비 디지털 기술"), 0.90),
        ],
    },

    "511ca1267446f0f5": {  # 2024.09 분기: R&D 디지털기술 접목
        "entities": [
            (T, "디지털선박기술", "고부가가치 선박·해양 설비 디지털 기술"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "디지털선박기술", "고부가가치 선박·해양 설비 디지털 기술"), 0.90),
        ],
    },

    "549b4cafbc27e803": {  # 2024.12 기재정정: R&D 디지털기술 접목
        "entities": [
            (T, "디지털선박기술", "고부가가치 선박·해양 설비 디지털 기술"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "디지털선박기술", "고부가가치 선박·해양 설비 디지털 기술"), 0.90),
        ],
    },

    "6d83de89b07fad8d": {  # 2024.06 반기: R&D 디지털기술 접목
        "entities": [
            (T, "디지털선박기술", "고부가가치 선박·해양 설비 디지털 기술"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "디지털선박기술", "고부가가치 선박·해양 설비 디지털 기술"), 0.90),
        ],
    },

    "2aeb3b0615592231": {  # 2025.03 분기: R&D 디지털기술 접목
        "entities": [
            (T, "디지털선박기술", "고부가가치 선박·해양 설비 디지털 기술"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "디지털선박기술", "고부가가치 선박·해양 설비 디지털 기술"), 0.90),
        ],
    },

    "2db8048bd66cf1bf": {  # 2026.03 분기: R&D 디지털기술 접목
        "entities": [
            (T, "디지털선박기술", "고부가가치 선박·해양 설비 디지털 기술"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "디지털선박기술", "고부가가치 선박·해양 설비 디지털 기술"), 0.90),
        ],
    },

    "3cd66432a9bfba19": {  # 2025.12 사보: R&D 디지털기술 접목
        "entities": [
            (T, "디지털선박기술", "고부가가치 선박·해양 설비 디지털 기술"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "디지털선박기술", "고부가가치 선박·해양 설비 디지털 기술"), 0.90),
        ],
    },

    # ═══ II. 사업의 내용: 해양시장 — FLNG 수요 언급 ═══

    "6add306dc2b3e326": {  # 2023.12 사보: FLNG(LNG-FPSO) 수요 전망
        "entities": [
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.93),
        ],
    },

    "40ef42c6ede30c03": {  # 2024.09 분기: FLNG 수요 전망
        "entities": [
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.92),
        ],
    },

    "d8d7ac74811f05a9": {  # 2024.06 반기: FLNG 수요 전망
        "entities": [
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.90),
        ],
    },

    "518662b034ff0ed3": {  # 2024.12 기재정정: FLNG 수요 전망
        "entities": [
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.90),
        ],
    },

    "7169ac77031fee5e": {  # 2024.12 기재정정: FLNG 수요 전망
        "entities": [
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.90),
        ],
    },

    "b84c3e9dcc24e795": {  # 2024.12 사보: FLNG 수요 전망
        "entities": [
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.90),
        ],
    },

    "9ae4424e9e430165": {  # 2025.03 분기: FLNG 수요
        "entities": [
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.90),
        ],
    },

    "9919892ca916a91b": {  # 2025.06 반기: FLNG 수요
        "entities": [
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.90),
        ],
    },

    "9f20771b1fa1bc3f": {  # 2025.09 분기: FLNG 수요
        "entities": [
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.90),
        ],
    },

    "9ceb1a12c6586251": {  # 2026.03 분기: LNG선·FLNG 발주 전망
        "entities": [
            (P, "LNG선", "LNG운반선(LNG carrier)"),
            (P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG선", "LNG운반선(LNG carrier)"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG-FPSO", "LNG-FPSO(부유식 액화천연가스 생산·저장·하역설비)"), 0.90),
        ],
    },

    # ═══ IV. 이사의 경영진단: LNG운반선·컨선·해양설비 수주 집중 ═══

    "0f8f0d4ead1b3423": {  # 2025.12 사보 MD&A: LNG운반선·컨선·해양설비 수주
        "entities": [
            (P, "LNG선", "LNG운반선(LNG carrier)"),
            (P, "초대형컨테이너선", "초대형 컨테이너선"),
            (P, "해양플랫폼", "해양플랫폼"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "LNG선", "LNG운반선(LNG carrier)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "초대형컨테이너선", "초대형 컨테이너선"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "해양플랫폼", "해양플랫폼"), 0.93),
        ],
    },

    # ═══ II. 사업의 내용: 종속기업 — 드릴십 매각 목적 국내 2개사 ═══

    "b0b19ea546920ed1": {  # 2024.09 분기: 종속기업 10개사 중 국내 2개사 드릴십 매각 목적
        "entities": [
            (P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"), 0.85),
        ],
    },

    # ═══ 감사보고서: 특수관계자와의 거래 (별도재무제표) ═══

    "83b9b13a5be54d5c": {  # 2023.12 사보 감사: 특수관계자 — 삼성생명·삼성화재·삼성웰스토리·삼성SDS·삼성전자·삼성물산, KC LNG Tech(관계기업), Zvezda Samsung(관계기업)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "KC LNG Tech Co.,Ltd"), 0.92, "관계기업(LNG 기술)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.93, "그 밖의 특수관계자(동일 대규모기업집단)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재해상보험"), 0.93, "그 밖의 특수관계자(동일 대규모기업집단)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에스디에스"), 0.92, "그 밖의 특수관계자(동일 대규모기업집단)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.92, "그 밖의 특수관계자(동일 대규모기업집단)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.92, "그 밖의 특수관계자(동일 대규모기업집단)"),
        ],
    },

    "71ca9b692c6fa0a3": {  # 2023.12 사보 감사: 특수관계자 차입·지급보증 — Curious Crete Limited 종속기업 시추선 매각
        "entities": [
            (P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Curious Crete Limited"), 0.90, "종속기업(시추선 매각 목적)"),
        ],
    },

    "addcf8778569b924": {  # 2024.12 사보 감사: Curious Crete Limited 드릴십 4척 전량 매각 완료, 유상감자
        "entities": [
            (P, "드릴십", "드릴십(Drillship, 반잠수식 시추선)"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Curious Crete Limited"), 0.90, "종속기업(시추선 4척 매각 완료·유상감자)"),
        ],
    },

    "02780e810a20bd9e": {  # 2025.12 사보 감사: 특수관계자 자금거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Curious Crete Limited"), 0.88, "종속기업(시추선 관련)"),
        ],
    },

    # ═══ 연결감사보고서: 특수관계자와의 거래 ═══

    "90cbb0aad19f416d": {  # 2023.12 사보 연결감사: 특수관계자 거래 — 삼성생명 퇴직연금, 그 밖의 특수관계자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.92, "그 밖의 특수관계자(퇴직연금운용자산)"),
        ],
    },

    "dc57571b831788e7": {  # 2024.12 사보 연결감사: 특수관계자 거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.92, "그 밖의 특수관계자(퇴직연금운용자산)"),
        ],
    },

    "9129bab6766401fa": {  # 2025.12 사보 연결감사: 특수관계자 거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.92, "그 밖의 특수관계자(퇴직연금운용자산)"),
        ],
    },

    # ═══ III. 재무에 관한 사항: 연결재무제표주석 특수관계자 (상세 테이블) ═══

    "d7884b3043bc11af": {  # 2023.12 사보 연결주석: 특수관계자 — KC LNG Tech·Zvezda Samsung·삼성화재·삼성생명·삼성웰스토리·삼성SDS·삼성전자·삼성물산
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "KC LNG Tech Co.,Ltd"), 0.93, "관계기업(LNG 기술)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재해상보험"), 0.93, "그 밖의 특수관계자(동일 기업집단)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.93, "그 밖의 특수관계자(동일 기업집단)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에스디에스"), 0.92, "그 밖의 특수관계자(동일 기업집단)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.92, "그 밖의 특수관계자(동일 기업집단)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.92, "그 밖의 특수관계자(동일 기업집단)"),
        ],
    },

    # ═══ III. 재무에 관한 사항: 재무제표주석 특수관계자 (별도) ═══

    "acf3c9b7369aa685": {  # 2023.12 사보 별도주석: 특수관계자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재해상보험"), 0.92, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.92, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에스디에스"), 0.90, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.90, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.90, "그 밖의 특수관계자"),
        ],
    },

    "e91ad7cf69be940a": {  # 2023.12 사보 별도주석: 특수관계자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재해상보험"), 0.92, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.92, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에스디에스"), 0.90, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.90, "그 밖의 특수관계자"),
        ],
    },

    # ═══ 기재정정: 특수관계자 테이블 ═══

    "8aa363a2e49838a5": {  # 2023.12 기재정정 연결주석: 특수관계자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "KC LNG Tech Co.,Ltd"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재해상보험"), 0.92, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.92, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에스디에스"), 0.90, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.90, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.90, "그 밖의 특수관계자"),
        ],
    },

    "c39b093dda790b27": {  # 2023.12 기재정정 연결주석: 특수관계자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재해상보험"), 0.92, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.92, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에스디에스"), 0.90, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.90, "그 밖의 특수관계자"),
        ],
    },

    "2e072a1c262be4da": {  # 2023.12 기재정정 별도주석: 특수관계자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재해상보험"), 0.90, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.90, "그 밖의 특수관계자"),
        ],
    },

    "1b602ab367a2e154": {  # 2023.12 기재정정 별도주석: 특수관계자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재해상보험"), 0.90, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.90, "그 밖의 특수관계자"),
        ],
    },

    "f978f1cd81589142": {  # 2023.12 사보 연결주석: 특수관계자 상세 테이블
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "KC LNG Tech Co.,Ltd"), 0.93, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성화재해상보험"), 0.92, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.92, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에스디에스"), 0.90, "그 밖의 특수관계자"),
        ],
    },

    "d7884b3043bc11af_dup": {  # 중복방지를 위한 빈 항목 (위에서 처리)
        "entities": [],
        "edges": [],
    },

}

# ── 관계기업 KC LNG Tech, Zvezda Samsung별도 처리: needs_er 노드 ──
# KC LNG Tech Co.,Ltd 는 정규화명 'kclngtechco.ltd' → needs_er
# Zvezda Samsung Heavy Industries LLC → needs_er

# EXTRACTIONS에서 중복 chunk_id (잘못 추가된 _dup 제거)
EXTRACTIONS.pop("d7884b3043bc11af_dup", None)


def process_chunk(drv, mconn, chunk: dict, extractions: dict) -> tuple[int, int]:
    """청크 한 개를 처리: 엔티티 MERGE + 엣지 MERGE + provenance 적재. (n_ent, n_edge) 반환."""
    cid = chunk["chunk_id"]
    rcept = chunk["rcept_no"]
    sec = chunk.get("section_path", "")
    ext = extractions.get(cid)
    if not ext:
        return 0, 0

    n_ent = 0
    n_edge = 0

    # 1) 엔티티 MERGE
    eid_map: dict[tuple, str] = {}  # (label, canonical) -> eid
    for label, canonical, name in ext.get("entities", []):
        eid = merge_entity(drv, label, canonical, name)
        eid_map[(label, canonical)] = eid
        n_ent += 1

    # 2) 엣지 MERGE + provenance
    for e in ext.get("edges", []):
        rel = e["rel"]
        conf = e["conf"]
        relation_type = e.get("relation_type")

        # from 노드
        frm_spec = e["from"]
        if frm_spec[0] == "org":
            org = resolve_org(frm_spec[1])
            if org is None:
                continue
            merge_org_node(drv, org)
            frm_match = {"kind": "org", "org": org}
            subj_id = org["id"]
        else:  # ('ent', label, canonical, name)
            _, label, canonical, _name = frm_spec
            eid = eid_map.get((label, canonical)) or merge_entity(drv, label, canonical, _name)
            frm_match = {"kind": "entity", "label": label, "id": eid}
            subj_id = eid

        # to 노드
        to_spec = e["to"]
        if to_spec[0] == "org":
            org2 = resolve_org(to_spec[1])
            if org2 is None:
                continue
            merge_org_node(drv, org2)
            to_match = {"kind": "org", "org": org2}
            obj_id = org2["id"]
        else:
            _, label2, canonical2, _name2 = to_spec
            eid2 = eid_map.get((label2, canonical2)) or merge_entity(drv, label2, canonical2, _name2)
            to_match = {"kind": "entity", "label": label2, "id": eid2}
            obj_id = eid2

        add_edge(drv, rel, frm_match, to_match,
                 chunk_id=cid, rcept_no=rcept, confidence=conf,
                 relation_type=relation_type)
        write_provenance(mconn, subj_id, rel, obj_id, cid, rcept, conf)
        n_edge += 1

    return n_ent, n_edge


def main():
    print(f"[extract_samsungheavy_00126478] 삼성중공업 비정형 추출 시작")
    already = ledger_processed_ids()
    print(f"  이미 처리된 chunk_id: {len(already)}개")

    drv = neo4j_driver()
    mconn = mariadb_conn()

    # 대상 청크 조회
    where = (
        "WHERE corp_code='00126478' "
        "AND (chunk_type='text_micro' OR (chunk_type='table_nl' AND embedding_text LIKE '%특수관계%')) "
        "ORDER BY chunk_id"
    )
    chunks = get_chunks(where)
    print(f"  대상 청크 총: {len(chunks)}개")

    total_ent = 0
    total_edge = 0
    processed = 0
    skipped = 0

    for chunk in chunks:
        cid = chunk["chunk_id"]
        if cid in already:
            skipped += 1
            continue

        n_ent, n_edge = process_chunk(drv, mconn, chunk, EXTRACTIONS)
        total_ent += n_ent
        total_edge += n_edge
        mark_processed(cid, n_ent, n_edge,
                       rcept_no=chunk.get("rcept_no"),
                       section_path=chunk.get("section_path"))
        processed += 1

    mconn.commit()
    mconn.close()
    drv.close()

    print(f"  신규 처리: {processed}개 | 스킵(기처리): {skipped}개")
    print(f"  엔티티 MERGE: {total_ent}건 | 엣지 MERGE: {total_edge}건")
    print("[extract_samsungheavy_00126478] 완료")


if __name__ == "__main__":
    main()
