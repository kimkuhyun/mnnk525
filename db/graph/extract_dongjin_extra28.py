"""Stage 5 비정형 추출 -- 동진쎄미켐 corp_code=00118804, text_micro 전체(~1,176) + table_nl 특수관계(~178).

동진쎄미켐 = 반도체/디스플레이 전자재료(포토레지스트/감광액 등) + 발포제 제조사.
주요 매출처: 삼성전자, SK하이닉스, 엘지디스플레이, 삼성디스플레이, BOE Technology.
최상위지배기업: 동진홀딩스(주). 관계기업: 동남산업, 동남투자자산, DONGJIN ITALIA S.R.L., (주)에스지글로벌.
그 밖의 특수관계자: (주)동진첨단소재, PT.Dongjin Indonesia, 명부산업, (주)미세테크, (주)동남케미텍,
Tokyo Electronic Materials, UNICELL CO.,LTD., Scarlet Kim & Co.,Inc., (주)코렉스, 이브이에스텍.
신규사업(차세대): 연료전지 MEA, 이차전지 도전재 슬러리, CNT 도전재, 실리콘 음극재.
2026.01.01 발포제사업부문 물적분할 -> 동진이노켐.

원장 = db/graph/ledger/extra28_00118804.jsonl (이 추출 전용).
실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_dongjin_extra28.py
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

CORP = "동진쎄미켐"
CORP_CODE = "00118804"

# -- 전용 원장 -----------------------------------------------------------------
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_DIR.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = LEDGER_DIR / "extra28_00118804.jsonl"


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


# -- Claude 추출 결과 (청크별) ---------------------------------------------------
# from/to = ('org', 회사명) | ('ent', label, canonical, name)
#
# 동진쎄미켐 핵심 사업: 전자재료(감광액=포토레지스트, 박리액, 식각액, 세척액) + 발포제.
# 삼성전자, SK하이닉스에 반도체 소재 공급; 엘지디스플레이, 삼성디스플레이에 디스플레이 소재 공급.
# 최상위지배기업 = 동진홀딩스(주).
# 관계기업 = 동남산업, 동남투자자산, DONGJIN ITALIA S.R.L., (주)에스지글로벌.
# 그 밖의 특수관계자 = (주)동진첨단소재(원료 공급), PT.Dongjin Indonesia(발포제 생산),
#   명부산업, (주)미세테크, (주)동남케미텍, Tokyo Electronic Materials, UNICELL CO.,LTD.,
#   Scarlet Kim & Co.,Inc., (주)코렉스, 이브이에스텍.
EXTRACTIONS: dict[str, dict] = {

    # -- II. 사업의 내용: 제품/기술 (2023 사업보고서) ----------------------------

    "0fc161d6b59773a4": {  # 전자재료사업: 감광액/박리액/세척액/식각액 납품. 발포제사업: 산업용 기초소재.
        "entities": [
            (P, "감광액", "감광액"),
            (P, "박리액", "박리액"),
            (P, "세척액", "세척액"),
            (P, "식각액", "식각액"),
            (P, "발포제", "발포제"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "감광액", "감광액"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "박리액", "박리액"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "세척액", "세척액"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "식각액", "식각액"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "발포제", "발포제"), 0.92),
        ],
    },

    "0c8a17b338d25030": {  # Microsphere 발포제: 세계 네 번째 상용화. 발포제 성장성.
        "entities": [
            (P, "마이크로스피어", "마이크로스피어 발포제"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "마이크로스피어", "마이크로스피어 발포제"), 0.92),
        ],
    },

    "1bbba7d417906877": {  # 반도체 소재 주요 매출처: 삼성전자, 하이닉스. 디스플레이: 엘지디스플레이, 삼성디스플레이.
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "엘지디스플레이"), 0.92),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.90),
        ],
    },

    # -- II. 사업의 내용 (2024 사업보고서) ----------------------------------------

    "035a557052781b55": {  # 2024 수주/공급: 삼성전자, 엘지디스플레이, 삼성디스플레이 감광액 등 전자재료 공급.
        "entities": [
            (P, "감광액", "감광액"),
        ],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "엘지디스플레이"), 0.92),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.90),
            E("PRODUCES", ("org", CORP), ("ent", P, "감광액", "감광액"), 0.95),
        ],
    },

    "18ea39bc4d239094": {  # 원재료: (주)동진첨단소재 특수관계인. 감광액/박리액/식각액 제조 원료 매입.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "동진첨단소재"), 0.90, "그 밖의 특수관계자(원재료 공급사)"),
        ],
    },

    "22ad3301ce73ed2e": {  # 전자재료사업 특성: 반도체/디스플레이 전방산업 연관, CAPEX Plan 영향.
        "entities": [
            (T, "반도체전자재료기술", "반도체·디스플레이용 전자재료 기술"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "반도체전자재료기술", "반도체·디스플레이용 전자재료 기술"), 0.88),
        ],
    },

    # -- II. 사업의 내용: 신에너지 신사업 (2025/2026 보고서) -----------------------

    "090ee5c79c5039c5": {  # 차세대 신재생에너지: 연료전지 MEA, 이차전지 도전재 슬러리, CNT 도전재, 실리콘 음극재.
        "entities": [
            (P, "연료전지MEA", "고출력·고내구성 MEA"),
            (P, "도전재슬러리", "고출력·고용량 도전재 슬러리"),
            (T, "촉매기술", "연료전지 촉매 기술"),
            (T, "전해질기술", "연료전지 전해질 기술"),
            (T, "전극제작기술", "MEA 전극 제작 기술"),
            (T, "바인더용해기술", "이차전지 바인더 용해 기술"),
            (T, "도전재분산기술", "고밀도 도전재 분산 기술"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "연료전지MEA", "고출력·고내구성 MEA"), 0.90),
            E("PRODUCES", ("org", CORP), ("ent", P, "도전재슬러리", "고출력·고용량 도전재 슬러리"), 0.88),
            E("USES_TECH", ("org", CORP), ("ent", T, "촉매기술", "연료전지 촉매 기술"), 0.88),
            E("USES_TECH", ("org", CORP), ("ent", T, "전해질기술", "연료전지 전해질 기술"), 0.87),
            E("USES_TECH", ("org", CORP), ("ent", T, "전극제작기술", "MEA 전극 제작 기술"), 0.87),
            E("USES_TECH", ("org", CORP), ("ent", T, "바인더용해기술", "이차전지 바인더 용해 기술"), 0.85),
            E("USES_TECH", ("org", CORP), ("ent", T, "도전재분산기술", "고밀도 도전재 분산 기술"), 0.85),
        ],
    },

    "0f1a00a44d20f9cd": {  # 2026: CNT 도전재, 실리콘 음극재 개발. 발포제사업부문 물적분할 -> 동진이노켐.
        "entities": [
            (P, "CNT도전재", "CNT 도전재"),
            (P, "실리콘음극재", "실리콘 음극재"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "CNT도전재", "CNT 도전재"), 0.85),
            E("PRODUCES", ("org", CORP), ("ent", P, "실리콘음극재", "실리콘 음극재"), 0.82),
            E("RELATED_PARTY", ("org", CORP), ("org", "동진이노켐"), 0.95, "물적분할 자회사(발포제사업부문, 2026.01)"),
        ],
    },

    # -- II. 사업의 내용 (2026 분기) ----------------------------------------------

    "0a984dadefbdf4a9": {  # 2026 1Q: 삼성전자, 하이닉스 = 반도체소재 주매출처. 엘지디스플레이, 삼성디스플레이 = 디스플레이소재.
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "엘지디스플레이"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.88),
        ],
    },

    "115ab2969de175af": {  # 2026 1Q 수주/공급: 삼성전자(주), BOE Technology, SK하이닉스 공급.
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "SK하이닉스"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "BOE Technology Group"), 0.88),
        ],
    },

    "16c522a44a5aae95": {  # 2025 3Q 수주: 삼성전자, 엘지디스플레이, 삼성디스플레이 공급 기본계약.
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "엘지디스플레이"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.88),
        ],
    },

    "2b37a6491bb2eee0": {  # 2024 1Q 경쟁우위: 메이커와 공동개발 전략. 반도체/디스플레이용 맞춤 신제품 개발.
        "entities": [
            (T, "고객공동개발", "반도체·디스플레이 메이커 공동 개발"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "고객공동개발", "반도체·디스플레이 메이커 공동 개발"), 0.82),
        ],
    },

    "0e74dd1f3c2c0fc8": {  # 2024 반기보고서: 10세대 이상 디스플레이 신규공장 투자 -> 재료수요 증가.
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "엘지디스플레이"), 0.88),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성디스플레이"), 0.87),
        ],
    },

    "0c5e83fda7805c79": {  # 발포제 특성: Microsphere 상용화(세계 4번째). 발포제 해외수요 증가.
        "entities": [
            (P, "마이크로스피어", "마이크로스피어 발포제"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "마이크로스피어", "마이크로스피어 발포제"), 0.92),
        ],
    },

    "119ddc58697e82dd": {  # 2025 반기: Microsphere 발포제 성장, 발포제 해외 수요신장.
        "entities": [
            (P, "마이크로스피어", "마이크로스피어 발포제"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "마이크로스피어", "마이크로스피어 발포제"), 0.92),
        ],
    },

    "278403f004b40b2f": {  # 발포제 산업: Microsphere 판매신장 두드러져.
        "entities": [
            (P, "마이크로스피어", "마이크로스피어 발포제"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "마이크로스피어", "마이크로스피어 발포제"), 0.90),
        ],
    },

    # -- 원재료 공급사 특수관계 (II. 사업의 내용, 재무제표주석) -------------------

    "1ced82397235fe85": {  # 원재료: Mitsubishi Gas Chemical, PURAC ASIA, Ashland, 동진첨단소재, 엔씨켐, 미원상사 매입.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "동진첨단소재"), 0.88, "그 밖의 특수관계자(원재료 공급사)"),
        ],
    },

    # -- 특수관계자 목록 (연결/별도 재무제표 주석, 감사보고서) ---------------------

    "04ae17ee92bd45d2": {  # 2023 감사보고서: 최상위지배기업=동진홀딩스(주). 관계기업/그 밖의 특수관계자 목록.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "동진홀딩스"), 0.97, "최상위지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동남산업"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동진첨단소재"), 0.88, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "PT.Dongjin Indonesia"), 0.88, "그 밖의 특수관계자(발포제 생산)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Tokyo Electronic Materials"), 0.85, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "UNICELL CO.,LTD."), 0.85, "그 밖의 특수관계자"),
        ],
    },

    "20d42560d076c4d7": {  # 2024 연결재무제표주석: 특수관계자 목록 확정. 최상위=동진홀딩스, 관계기업 4개, 그 밖의 9개.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "동진홀딩스"), 0.97, "최상위지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동남산업"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동남투자자산"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "DONGJIN ITALIA S.R.L."), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에스지글로벌"), 0.85, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동진첨단소재"), 0.90, "그 밖의 특수관계자(원재료 공급사)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "PT.Dongjin Indonesia"), 0.88, "그 밖의 특수관계자(발포제 생산)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "코렉스"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "명부산업"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "미세테크"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동남케미텍"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Tokyo Electronic Materials"), 0.85, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "UNICELL CO.,LTD."), 0.85, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Scarlet Kim & Co.,Inc."), 0.82, "그 밖의 특수관계자"),
        ],
    },

    "1685e268dbc5c981": {  # 2024 연결감사보고서: 특수관계자 목록(확정, 동일).
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "동진홀딩스"), 0.97, "최상위지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동남산업"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동남투자자산"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "DONGJIN ITALIA S.R.L."), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에스지글로벌"), 0.85, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동진첨단소재"), 0.90, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "PT.Dongjin Indonesia"), 0.88, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "코렉스"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "명부산업"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "미세테크"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동남케미텍"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Tokyo Electronic Materials"), 0.85, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "UNICELL CO.,LTD."), 0.85, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Scarlet Kim & Co.,Inc."), 0.82, "그 밖의 특수관계자"),
        ],
    },

    "3249d2eaf4977419": {  # 2025 반기 연결재무제표주석: 특수관계자 목록.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "동진홀딩스"), 0.97, "최상위지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동남산업"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동남투자자산"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "DONGJIN ITALIA S.R.L."), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동진첨단소재"), 0.90, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "PT.Dongjin Indonesia"), 0.88, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "명부산업"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "미세테크"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동남케미텍"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Tokyo Electronic Materials"), 0.85, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "UNICELL CO.,LTD."), 0.85, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Scarlet Kim & Co.,Inc."), 0.82, "그 밖의 특수관계자"),
        ],
    },

    "236b4da1b5f45264": {  # 2025 반기 별도재무제표주석: 특수관계자 목록 확정.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "동진홀딩스"), 0.97, "최상위지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동진첨단소재"), 0.90, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "PT.Dongjin Indonesia"), 0.88, "그 밖의 특수관계자"),
        ],
    },

    "28236e8cea51e520": {  # 2025 3Q: 관계기업=이브이에스텍, 그 밖의=PT.Dongjin Indonesia, (주)미세테크.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "이브이에스텍"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "PT.Dongjin Indonesia"), 0.88, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "미세테크"), 0.83, "그 밖의 특수관계자"),
        ],
    },

    "264583eb9129e368": {  # 2024 3Q 연결재무제표주석: 특수관계자 목록.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "동진홀딩스"), 0.97, "최상위지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동남산업"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동남투자자산"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "DONGJIN ITALIA S.R.L."), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에스지글로벌"), 0.85, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동진첨단소재"), 0.90, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "PT.Dongjin Indonesia"), 0.88, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "코렉스"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "명부산업"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "미세테크"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동남케미텍"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Tokyo Electronic Materials"), 0.85, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "UNICELL CO.,LTD."), 0.85, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Scarlet Kim & Co.,Inc."), 0.82, "그 밖의 특수관계자"),
        ],
    },

    "4340c98f7d12bde8": {  # 2024 반기 별도재무제표주석: 종속기업 목록 + 그 밖의 특수관계자.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "동진첨단소재"), 0.90, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "PT.Dongjin Indonesia"), 0.88, "그 밖의 특수관계자(발포제 생산)"),
        ],
    },

    # -- 연결재무제표주석 채권채무 표 (특수관계자 거래) ---------------------------

    "1f99c50b002bdab8": {  # 2023 연결재무제표주석: 동진홀딩스, DONGJIN ITALIA, 동남투자자산 채권채무.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "동진홀딩스"), 0.97, "최상위지배기업(채권채무 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "DONGJIN ITALIA S.R.L."), 0.88, "관계기업(채권채무 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동남투자자산"), 0.85, "관계기업(채권 거래)"),
        ],
    },

    "012d20b089d056fc": {  # 2024 3Q 연결재무제표주석: 동진홀딩스, DONGJIN ITALIA, 동남투자자산 채권채무.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "동진홀딩스"), 0.97, "최상위지배기업(채권채무 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "DONGJIN ITALIA S.R.L."), 0.88, "관계기업(채권채무 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동남투자자산"), 0.85, "관계기업(채권 거래)"),
        ],
    },

    "069b648ebd265189": {  # 2024 1Q 연결재무제표주석: 동진홀딩스, DONGJIN ITALIA, 동남산업 채권채무.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "동진홀딩스"), 0.97, "최상위지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "DONGJIN ITALIA S.R.L."), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동남산업"), 0.88, "관계기업"),
        ],
    },

    "150313be08187ec7": {  # 2024 3Q 연결재무제표주석: 동진홀딩스(채무 50,000), DONGJIN ITALIA(채권).
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "동진홀딩스"), 0.97, "최상위지배기업(채권채무 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "DONGJIN ITALIA S.R.L."), 0.88, "관계기업(채권 거래)"),
        ],
    },

    "31943203be3ead2c": {  # 2025 연결감사보고서: 동진홀딩스, DONGJIN ITALIA, 동남투자자산, 그 밖의 특수관계자 채권채무.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "동진홀딩스"), 0.97, "최상위지배기업(채권채무 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "DONGJIN ITALIA S.R.L."), 0.88, "관계기업(채권 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동남투자자산"), 0.85, "관계기업"),
        ],
    },

    "44b393fe7b9a01a7": {  # 2024 연결감사보고서: 동진홀딩스, DONGJIN ITALIA, 동남투자자산 채권채무.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "동진홀딩스"), 0.97, "최상위지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "DONGJIN ITALIA S.R.L."), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동남투자자산"), 0.85, "관계기업"),
        ],
    },

    # -- 별도재무제표주석 채권채무 표 (특수관계자 거래) ---------------------------

    "189277f132d8af71": {  # 2023 별도재무제표주석: 종속기업(무한동진쎄미켐, DONGJIN USA INC 등) 매출채권.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "DONGJIN USA INC"), 0.88, "종속기업(별도 매출채권 거래)"),
        ],
    },

    "33bc2eefadac6aba": {  # 2023 감사보고서: 종속기업(무한동진쎄미켐, DONGJIN USA INC) 채권채무.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "DONGJIN USA INC"), 0.88, "종속기업"),
        ],
    },

    "08036490840ae49a": {  # 2025 1Q 별도재무제표주석: DONGJIN USA INC, Dongjin Global Holdings, DONGJIN SEMICHEM TEXAS 매출채권.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "DONGJIN USA INC"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Dongjin Global Holdings"), 0.88, "종속기업(대여금)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "DONGJIN SEMICHEM TEXAS INC"), 0.88, "종속기업"),
        ],
    },

    # -- 별도재무제표주석 매입(그 밖의 특수관계자 원재료 구매) ---------------------

    "3d5d942c1144a0fd": {  # 2024 반기 연결재무제표주석: (주)동진첨단소재 원재료 311억, PT.Dongjin Indonesia 원재료 44억 매입.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "동진첨단소재"), 0.92, "그 밖의 특수관계자(원재료 공급: 311억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "PT.Dongjin Indonesia"), 0.88, "그 밖의 특수관계자(원재료 공급: 44억)"),
        ],
    },

    # -- 별도재무제표주석 그 밖의 특수관계자 채권채무 -----------------------------

    "02ec20cfec63bcd9": {  # 2024 1Q 별도재무제표주석: Tokyo Electronic Materials(채권 82백만, 채무 95백만), UNICELL(채권 2,487백만).
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Tokyo Electronic Materials"), 0.88, "그 밖의 특수관계자(채권채무 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "UNICELL CO.,LTD."), 0.88, "그 밖의 특수관계자(채권 거래)"),
        ],
    },

    "2584efcd65a60204": {  # 2024 3Q 별도재무제표주석: UNICELL CO.,LTD. 채권 2,143백만.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "UNICELL CO.,LTD."), 0.87, "그 밖의 특수관계자"),
        ],
    },

    "436b570bfd65c918": {  # 2025 1Q 별도재무제표주석: UNICELL CO.,LTD. 채권 1,956백만.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "UNICELL CO.,LTD."), 0.87, "그 밖의 특수관계자"),
        ],
    },

    "0a572fee1a70cf89": {  # 2025 감사보고서: 명부산업, (주)동남케미텍, Tokyo Electronic Materials 채권채무.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "명부산업"), 0.85, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동남케미텍"), 0.85, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Tokyo Electronic Materials"), 0.87, "그 밖의 특수관계자(채무: 107백만)"),
        ],
    },

    "0b17f624eac307d2": {  # 2025 감사보고서: 종속기업(무한동진쎄미켐, DONGJIN USA INC, Dongjin Global Holdings) 채권채무.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "DONGJIN USA INC"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Dongjin Global Holdings"), 0.88, "종속기업(대여금)"),
        ],
    },

    "09e0b766e0fd984b": {  # 2025 감사보고서 매출: 리앤안투자, 엘씨에이치투자 기타수익.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "리앤안투자"), 0.80, "그 밖의 특수관계자(기타수익 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엘씨에이치투자"), 0.80, "그 밖의 특수관계자(기타수익 거래)"),
        ],
    },

    # -- 연결감사보고서 특수관계자 목록 (2025) ------------------------------------

    "2df89cfc564cafdc": {  # 2025 별도재무제표주석: 특수관계자 목록. 동진홀딩스 최상위지배기업.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "동진홀딩스"), 0.97, "최상위지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동진첨단소재"), 0.90, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "PT.Dongjin Indonesia"), 0.88, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "코렉스"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "명부산업"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "미세테크"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동남케미텍"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Tokyo Electronic Materials"), 0.85, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "UNICELL CO.,LTD."), 0.85, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Scarlet Kim & Co.,Inc."), 0.82, "그 밖의 특수관계자"),
        ],
    },

    # -- 연결재무제표주석 별도거래 표 (1Q 2025) ------------------------------------

    "1207c7cb50f93a99": {  # 2025 1Q 별도재무제표주석: 종속기업 매출 (DONGJIN USA INC, Dongjin Sweden AB, DONGJIN SEMICHEM TEXAS).
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "DONGJIN USA INC"), 0.88, "종속기업(매출 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Dongjin Sweden AB"), 0.88, "종속기업(기타수익 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "DONGJIN SEMICHEM TEXAS INC"), 0.88, "종속기업(매출 거래)"),
        ],
    },

    "18ae6fc419f2f0af": {  # 2024 반기 별도재무제표주석: DONGJIN USA INC, Dongjin Sweden AB, DONGJIN SEMICHEM TEXAS 매출.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "DONGJIN USA INC"), 0.88, "종속기업(매출 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Dongjin Sweden AB"), 0.87, "종속기업(매출 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "DONGJIN SEMICHEM TEXAS INC"), 0.88, "종속기업(매출 거래)"),
        ],
    },

    "288bfc74ef837df7": {  # 2024 1Q 연결재무제표주석: 동진홀딩스(기타수익 17,657천원), DONGJIN ITALIA(매출 262,623천원).
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "동진홀딩스"), 0.95, "최상위지배기업(기타수익 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "DONGJIN ITALIA S.R.L."), 0.88, "관계기업(매출 거래)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "동남산업"), 0.85, "관계기업(기타수익 거래)"),
        ],
    },

    # -- 연결재무제표주석 별도거래 (1Q 2024 구매) ----------------------------------

    "308ca2a70ec2e307": {  # 2024 1Q 별도재무제표주석: 종속기업(신암정유/대만동진화성 등) 원부재료 매입.
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "신암정유"), 0.88, "종속기업(원부재료 매입)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "대만동진화성고분유한공사"), 0.85, "종속기업(원부재료 매입)"),
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
    print(f"[batch] 원장 기처리 {len(done)}건 -- 스킵")

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
            print(f"  [warn] {cid} 대상에 없음 -- 스킵")
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
    print("=== 동진쎄미켐 Stage5 추출 결과 ===")
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
