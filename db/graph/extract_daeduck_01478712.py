"""Stage 5 비정형 추출 — 대덕전자 corp_code=01478712, text_micro 전체(~879) + table_nl 특수관계.

대덕전자 = 2020년 5월 1일 (주)대덕에서 인적분할, PCB 전문기업.
주요 제품: FCBGA(비메모리 반도체용 패키지 기판), FCCSP, FCBOC, CSP, SiP(메모리/비메모리 반도체 패키지 기판), MLB 기판(네트워크·검사장비용).
기술: 고밀도 반도체 패키지 기판 기술, 고층 MLB 기판 기술, AI 서버용 고부가가치 PCB 기술.
주요 매출처: 삼성전자, 에스케이하이닉스, 앰코테크놀로지코리아, 스태츠칩팩코리아.
지배기업: (주)대덕. 종속기업: Daeduck Vietnam Co., Ltd, Daeduck Electronics (SHANGHAI) Co., Ltd., DD USA, INC.
특수관계자(그 밖의): 엔알랩(주), (주)와이솔, (주)디아이티, WISOL JAPAN Co.,Ltd.

원장 = db/graph/ledger/extra28_01478712.jsonl (이 추출 전용).
실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_daeduck_01478712.py
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

CORP = "대덕전자"
CORP_CODE = "01478712"

# 전용 원장
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_DIR.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = LEDGER_DIR / "extra28_01478712.jsonl"


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
# 대덕전자: 반도체 패키지기판(FCBGA/CSP/SiP)·PCB 전문기업.
# Product = FCBGA기판, FCCSP기판, FCBOC기판, CSP기판, SiP기판, MLB기판, 반도체 패키지 기판
# Technology = 고밀도 반도체 패키지 기판 기술, 고층 MLB 기판 기술, AI서버용 고부가가치 PCB 기술
# 매출처: 삼성전자(00126380), 에스케이하이닉스(00164779), 앰코테크놀로지코리아(needs_er), 스태츠칩팩코리아(needs_er)
# 특수관계자: (주)대덕(지배기업), Daeduck Vietnam(종속), Daeduck Shanghai(종속), DD USA(종속),
#             엔알랩(그 밖의), (주)와이솔(그 밖의), (주)디아이티(그 밖의), WISOL JAPAN(그 밖의)

EXTRACTIONS: dict[str, dict] = {

    # ═══ II. 사업의 내용: 영업개황 — FCBGA/FCCSP/CSP/SiP/MLB 생산 + 주요 거래처 ═══

    "e590372b52ba5569": {  # 2023.12 사보: 영업개황 FCBGA·FCCSP·FCBOC·CSP·SiP·MLB 생산 + 삼성전자·SK하이닉스 납품
        "entities": [
            (P, "FCBGA기판", "FCBGA 반도체 패키지 기판(Flip Chip Ball Grid Array Substrate)"),
            (P, "FCCSP기판", "FCCSP 반도체 패키지 기판(Flip Chip Chip Scale Package Substrate)"),
            (P, "FCBOC기판", "FCBOC 반도체 패키지 기판(Flip Chip Board on Chip Substrate)"),
            (P, "CSP기판", "CSP 반도체 패키지 기판(Chip Scale Package Substrate)"),
            (P, "SiP기판", "SiP 반도체 패키지 기판(System in Package Substrate)"),
            (P, "MLB기판", "MLB 기판(Multi Layer Board, 다층 인쇄회로기판)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "FCBGA기판", "FCBGA 반도체 패키지 기판(Flip Chip Ball Grid Array Substrate)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "FCCSP기판", "FCCSP 반도체 패키지 기판(Flip Chip Chip Scale Package Substrate)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "FCBOC기판", "FCBOC 반도체 패키지 기판(Flip Chip Board on Chip Substrate)"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "CSP기판", "CSP 반도체 패키지 기판(Chip Scale Package Substrate)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "SiP기판", "SiP 반도체 패키지 기판(System in Package Substrate)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "MLB기판", "MLB 기판(Multi Layer Board, 다층 인쇄회로기판)"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.92),
            E("SUPPLIES_TO", ("org", CORP), ("org", "에스케이하이닉스"), 0.90),
        ],
    },

    "596ce4457e48eb11": {  # 2023.12 사보: 주요 거래처 — 삼성전자·SK하이닉스·앰코테크놀로지코리아·스태츠칩팩코리아
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "에스케이하이닉스"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "앰코테크놀로지코리아"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "스태츠칩팩코리아"), 0.88),
        ],
    },

    "48e438b6e6b0b813": {  # 2024.03 분기: 영업개황 FCBGA·FCCSP·FCBOC·CSP·SiP·MLB 생산
        "entities": [
            (P, "FCBGA기판", "FCBGA 반도체 패키지 기판(Flip Chip Ball Grid Array Substrate)"),
            (P, "FCCSP기판", "FCCSP 반도체 패키지 기판(Flip Chip Chip Scale Package Substrate)"),
            (P, "MLB기판", "MLB 기판(Multi Layer Board, 다층 인쇄회로기판)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "FCBGA기판", "FCBGA 반도체 패키지 기판(Flip Chip Ball Grid Array Substrate)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "FCCSP기판", "FCCSP 반도체 패키지 기판(Flip Chip Chip Scale Package Substrate)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "MLB기판", "MLB 기판(Multi Layer Board, 다층 인쇄회로기판)"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "에스케이하이닉스"), 0.88),
        ],
    },

    "4692c3b39a0285e1": {  # 2024.03 분기: 주요 거래처 — 삼성전자·SK하이닉스·앰코·스태츠칩팩
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "에스케이하이닉스"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "앰코테크놀로지코리아"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "스태츠칩팩코리아"), 0.88),
        ],
    },

    "1694425c51211856": {  # 2024.06 반기: 영업개황 FCBGA·FCCSP·CSP·SiP·MLB
        "entities": [
            (P, "FCBGA기판", "FCBGA 반도체 패키지 기판(Flip Chip Ball Grid Array Substrate)"),
            (P, "MLB기판", "MLB 기판(Multi Layer Board, 다층 인쇄회로기판)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "FCBGA기판", "FCBGA 반도체 패키지 기판(Flip Chip Ball Grid Array Substrate)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "MLB기판", "MLB 기판(Multi Layer Board, 다층 인쇄회로기판)"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "에스케이하이닉스"), 0.88),
        ],
    },

    "0366b80162da5b91": {  # 2024.06 반기: 주요 거래처 — 삼성전자·SK하이닉스·앰코·스태츠칩팩
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "에스케이하이닉스"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "앰코테크놀로지코리아"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "스태츠칩팩코리아"), 0.88),
        ],
    },

    "d9707a60b292dd2c": {  # 2024.09 분기: 영업개황 FCBGA·FCCSP·CSP·SiP·MLB
        "entities": [
            (P, "FCBGA기판", "FCBGA 반도체 패키지 기판(Flip Chip Ball Grid Array Substrate)"),
            (P, "MLB기판", "MLB 기판(Multi Layer Board, 다층 인쇄회로기판)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "FCBGA기판", "FCBGA 반도체 패키지 기판(Flip Chip Ball Grid Array Substrate)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "MLB기판", "MLB 기판(Multi Layer Board, 다층 인쇄회로기판)"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "에스케이하이닉스"), 0.88),
        ],
    },

    "6ba1d64c889c1903": {  # 2024.09 분기: 주요 거래처 — 삼성전자·SK하이닉스·앰코·스태츠칩팩
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "에스케이하이닉스"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "앰코테크놀로지코리아"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "스태츠칩팩코리아"), 0.88),
        ],
    },

    "50d8a0a81cb0f83a": {  # 2024.12 사보: 영업개황 FCBGA·FCCSP·CSP·SiP·MLB
        "entities": [
            (P, "FCBGA기판", "FCBGA 반도체 패키지 기판(Flip Chip Ball Grid Array Substrate)"),
            (P, "MLB기판", "MLB 기판(Multi Layer Board, 다층 인쇄회로기판)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "FCBGA기판", "FCBGA 반도체 패키지 기판(Flip Chip Ball Grid Array Substrate)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "MLB기판", "MLB 기판(Multi Layer Board, 다층 인쇄회로기판)"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "에스케이하이닉스"), 0.88),
        ],
    },

    "19e244f4ce29c7ae": {  # 2024.12 사보: 주요 거래처 — 삼성전자·SK하이닉스·앰코·스태츠칩팩
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "에스케이하이닉스"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "앰코테크놀로지코리아"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "스태츠칩팩코리아"), 0.88),
        ],
    },

    "972b417db4a08cee": {  # 2025.03 분기: 영업개황 패키지기판·MLB
        "entities": [
            (P, "FCBGA기판", "FCBGA 반도체 패키지 기판(Flip Chip Ball Grid Array Substrate)"),
            (P, "MLB기판", "MLB 기판(Multi Layer Board, 다층 인쇄회로기판)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "FCBGA기판", "FCBGA 반도체 패키지 기판(Flip Chip Ball Grid Array Substrate)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "MLB기판", "MLB 기판(Multi Layer Board, 다층 인쇄회로기판)"), 0.93),
        ],
    },

    "069e5146551440b5": {  # 2025.03 분기: 주요 거래처 — 삼성전자·SK하이닉스·앰코·스태츠칩팩
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "에스케이하이닉스"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "앰코테크놀로지코리아"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "스태츠칩팩코리아"), 0.88),
        ],
    },

    "610b763d7045a578": {  # 2025.06 반기: 영업개황 패키지기판·MLB
        "entities": [
            (P, "FCBGA기판", "FCBGA 반도체 패키지 기판(Flip Chip Ball Grid Array Substrate)"),
            (P, "MLB기판", "MLB 기판(Multi Layer Board, 다층 인쇄회로기판)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "FCBGA기판", "FCBGA 반도체 패키지 기판(Flip Chip Ball Grid Array Substrate)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "MLB기판", "MLB 기판(Multi Layer Board, 다층 인쇄회로기판)"), 0.93),
        ],
    },

    "006d4df5ed007182": {  # 2025.06 반기: 주요 거래처 — 삼성전자·SK하이닉스·앰코·스태츠칩팩
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "에스케이하이닉스"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "앰코테크놀로지코리아"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "스태츠칩팩코리아"), 0.88),
        ],
    },

    "751af8316ec74356": {  # 2025.09 분기: 영업개황 패키지기판·MLB
        "entities": [
            (P, "FCBGA기판", "FCBGA 반도체 패키지 기판(Flip Chip Ball Grid Array Substrate)"),
            (P, "MLB기판", "MLB 기판(Multi Layer Board, 다층 인쇄회로기판)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "FCBGA기판", "FCBGA 반도체 패키지 기판(Flip Chip Ball Grid Array Substrate)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "MLB기판", "MLB 기판(Multi Layer Board, 다층 인쇄회로기판)"), 0.93),
        ],
    },

    "cd3756a6d1a1844a": {  # 2025.09 분기: 주요 거래처 — 삼성전자·SK하이닉스·앰코·스태츠칩팩
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "에스케이하이닉스"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "앰코테크놀로지코리아"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "스태츠칩팩코리아"), 0.88),
        ],
    },

    "90196b8610d10689": {  # 2025.12 사보: 영업개황 패키지기판·MLB
        "entities": [
            (P, "FCBGA기판", "FCBGA 반도체 패키지 기판(Flip Chip Ball Grid Array Substrate)"),
            (P, "MLB기판", "MLB 기판(Multi Layer Board, 다층 인쇄회로기판)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "FCBGA기판", "FCBGA 반도체 패키지 기판(Flip Chip Ball Grid Array Substrate)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "MLB기판", "MLB 기판(Multi Layer Board, 다층 인쇄회로기판)"), 0.93),
        ],
    },

    "aa98e01ecbcc44d4": {  # 2025.12 사보: 주요 거래처 — 삼성전자·SK하이닉스·앰코·스태츠칩팩
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "에스케이하이닉스"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "앰코테크놀로지코리아"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "스태츠칩팩코리아"), 0.88),
        ],
    },

    "75c07162c6d8bc27": {  # 2026.03 분기: 영업개황 패키지기판·MLB
        "entities": [
            (P, "FCBGA기판", "FCBGA 반도체 패키지 기판(Flip Chip Ball Grid Array Substrate)"),
            (P, "MLB기판", "MLB 기판(Multi Layer Board, 다층 인쇄회로기판)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "FCBGA기판", "FCBGA 반도체 패키지 기판(Flip Chip Ball Grid Array Substrate)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "MLB기판", "MLB 기판(Multi Layer Board, 다층 인쇄회로기판)"), 0.93),
        ],
    },

    "5e43a19a19be1168": {  # 2026.03 분기: 주요 거래처 — 삼성전자·SK하이닉스·앰코·스태츠칩팩
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("SUPPLIES_TO", ("org", CORP), ("org", "에스케이하이닉스"), 0.93),
            E("SUPPLIES_TO", ("org", CORP), ("org", "앰코테크놀로지코리아"), 0.90),
            E("SUPPLIES_TO", ("org", CORP), ("org", "스태츠칩팩코리아"), 0.88),
        ],
    },

    # ═══ IV. 이사의 경영진단: FCBGA 핵심 전략제품 + AI서버 수요 ═══

    "ee8c7f11801b38f4": {  # 2023.12 사보 MD&A: FCBGA = 핵심 제품, AI·CPU·서버·데이터센터용 비메모리칩 적용
        "entities": [
            (P, "FCBGA기판", "FCBGA 반도체 패키지 기판(Flip Chip Ball Grid Array Substrate)"),
            (T, "반도체패키지기판기술", "고부가가치 반도체 패키지 서브스트레이트 기술(Package Substrate Technology)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "FCBGA기판", "FCBGA 반도체 패키지 기판(Flip Chip Ball Grid Array Substrate)"), 0.97),
            E("USES_TECH", ("org", CORP), ("ent", T, "반도체패키지기판기술", "고부가가치 반도체 패키지 서브스트레이트 기술(Package Substrate Technology)"), 0.90),
        ],
    },

    "cd9e045b562cb8f9": {  # 2025.12 사보 MD&A: FCBGA 핵심전략제품 + 패키지서브스트레이트 집중 + AI확산 수요
        "entities": [
            (P, "FCBGA기판", "FCBGA 반도체 패키지 기판(Flip Chip Ball Grid Array Substrate)"),
            (T, "반도체패키지기판기술", "고부가가치 반도체 패키지 서브스트레이트 기술(Package Substrate Technology)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "FCBGA기판", "FCBGA 반도체 패키지 기판(Flip Chip Ball Grid Array Substrate)"), 0.97),
            E("USES_TECH", ("org", CORP), ("ent", T, "반도체패키지기판기술", "고부가가치 반도체 패키지 서브스트레이트 기술(Package Substrate Technology)"), 0.92),
        ],
    },

    "a487272fbd4cb10c": {  # 2025.12 사보 MD&A: AI패러다임 + 첨단패키징·데이터센터 인프라 수요 + 기술중심 경영
        "entities": [
            (T, "반도체패키지기판기술", "고부가가치 반도체 패키지 서브스트레이트 기술(Package Substrate Technology)"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "반도체패키지기판기술", "고부가가치 반도체 패키지 서브스트레이트 기술(Package Substrate Technology)"), 0.88),
        ],
    },

    "8e9d200b9b5734fb": {  # 2025.12 사보 MD&A: 네트워크 핵심시장 + AI확산·데이터센터 수요
        "entities": [
            (T, "반도체패키지기판기술", "고부가가치 반도체 패키지 서브스트레이트 기술(Package Substrate Technology)"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "반도체패키지기판기술", "고부가가치 반도체 패키지 서브스트레이트 기술(Package Substrate Technology)"), 0.85),
        ],
    },

    # ═══ 특수관계자 테이블 — (주)대덕(지배기업) ═══

    "236173400a3ced9f": {  # 2023.12 사보 별도주석: 특수관계자 현황 — (주)대덕 지배기업, 엔알랩·와이솔 그 밖의
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.95, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.90, "그 밖의 특수관계자((주)대덕의 종속기업)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.90, "그 밖의 특수관계자((주)대덕의 종속기업)"),
        ],
    },

    "2d0d7821c4dfc0eb": {  # 2023.12 사보 연결감사: 특수관계자 현황 — (주)대덕 지배기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.95, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.88, "그 밖의 특수관계자((주)대덕의 종속기업)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.88, "그 밖의 특수관계자((주)대덕의 종속기업)"),
        ],
    },

    "878c8e347843d0e6": {  # 2023.12 사보 연결감사보고서: 특수관계자 현황
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.95, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.88, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.88, "그 밖의 특수관계자"),
        ],
    },

    "b7d4cd246c479a2f": {  # 2023.12 사보 연결주석: 특수관계자 거래금액 테이블
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.93, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.87, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.87, "그 밖의 특수관계자"),
        ],
    },

    "2a5bd54c4a945523": {  # 2024.03 분기 연결주석: 특수관계자 현황 — (주)대덕 지배기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.95, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.88, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.88, "그 밖의 특수관계자"),
        ],
    },

    "80a0f901298a5936": {  # 2024.03 분기 별도주석: 특수관계자 현황
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.95, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.88, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.88, "그 밖의 특수관계자"),
        ],
    },

    "1ba307213f39c29e": {  # 2024.06 반기 별도주석: 특수관계자 현황 — (주)대덕 지배기업, 와이솔·엔알랩 그 밖의
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.95, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.88, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.88, "그 밖의 특수관계자"),
        ],
    },

    "a2d9b60368c5fae2": {  # 2024.06 반기 연결주석: 특수관계자 현황
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.95, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.87, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.87, "그 밖의 특수관계자"),
        ],
    },

    "a3a428db18e5d8d1": {  # 2024.09 분기 별도주석: 특수관계자 현황 — (주)대덕·Daeduck Vietnam 종속기업·엔알랩·와이솔
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.95, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.87, "그 밖의 특수관계자((주)대덕의 종속기업)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.87, "그 밖의 특수관계자((주)대덕의 종속기업)"),
        ],
    },

    "ba326a5b38d56cb9": {  # 2024.09 분기 연결주석: 특수관계자 거래금액
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.93, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.85, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.85, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "WISOL JAPAN Co.,Ltd"), 0.83, "그 밖의 특수관계자"),
        ],
    },

    "42932412106516ae": {  # 2024.12 사보 감사보고서: 특수관계자 현황 — (주)대덕 지배기업, Daeduck Vietnam 종속
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.95, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.87, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)디아이티"), 0.85, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "WISOL JAPAN Co.,Ltd"), 0.83, "그 밖의 특수관계자"),
        ],
    },

    "a27ebca7533e9d06": {  # 2024.12 사보 별도주석: 특수관계자 현황
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.95, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.87, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)디아이티"), 0.85, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "WISOL JAPAN Co.,Ltd"), 0.83, "그 밖의 특수관계자"),
        ],
    },

    "128cf1243e1b2e3a": {  # 2024.12 사보 별도주석: 특수관계자 거래금액
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.93, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.85, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)디아이티"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "WISOL JAPAN Co.,Ltd"), 0.80, "그 밖의 특수관계자"),
        ],
    },

    "15d8510f5c81558b": {  # 2024.12 사보 연결주석: 특수관계자 거래금액 — (주)대덕·엔알랩·디아이티·WISOL JAPAN
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.93, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.85, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)디아이티"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "WISOL JAPAN Co.,Ltd"), 0.80, "그 밖의 특수관계자"),
        ],
    },

    "a8cd973802720f35": {  # 2024.12 사보 연결주석: 특수관계자 거래금액2
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.92, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)디아이티"), 0.80, "그 밖의 특수관계자"),
        ],
    },

    "b2b166272fb0ceeb": {  # 2024.12 사보 연결주석: 특수관계자 채권·채무
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.92, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.82, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "WISOL JAPAN Co.,Ltd"), 0.80, "그 밖의 특수관계자"),
        ],
    },

    "1b669f7f444da1c6": {  # 2024.12 사보 별도주석: 특수관계자 채권·채무
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.93, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)디아이티"), 0.80, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "WISOL JAPAN Co.,Ltd"), 0.78, "그 밖의 특수관계자"),
        ],
    },

    "5ce2a04a7ea1b812": {  # 2024.12 사보 별도주석: 특수관계자 거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.92, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.87, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.82, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)디아이티"), 0.80, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "WISOL JAPAN Co.,Ltd"), 0.78, "그 밖의 특수관계자"),
        ],
    },

    "ba75580359b313e6": {  # 2024.12 사보 별도주석: 특수관계자 거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.92, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.82, "그 밖의 특수관계자"),
        ],
    },

    "bafe2f886a72206c": {  # 2024.12 사보 연결주석: 특수관계자 추가 거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.91, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.81, "그 밖의 특수관계자"),
        ],
    },

    "c21a90a1350e3f82": {  # 2024.12 사보 연결주석: 특수관계자 채권채무
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.91, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.81, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.79, "그 밖의 특수관계자"),
        ],
    },

    "fe30aa5bb4473c98": {  # 2024.12 사보 연결주석: 특수관계자 자금거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.90, "지배기업"),
        ],
    },

    "69525920424c9385": {  # 2025.03 분기 연결주석: 특수관계자 현황 — (주)대덕·엔알랩·와이솔·WISOL JAPAN
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.95, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.87, "그 밖의 특수관계자((주)대덕의 종속기업)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.87, "그 밖의 특수관계자((주)대덕의 종속기업)"),
        ],
    },

    "14635f0771e8d48a": {  # 2025.03 분기 연결주석: 특수관계자 거래금액 — (주)대덕·엔알랩·와이솔·WISOL JAPAN
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.93, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.84, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "WISOL JAPAN Co.,Ltd"), 0.80, "그 밖의 특수관계자"),
        ],
    },

    "08b8b14a0527360a": {  # 2025.03 분기 연결주석: 특수관계자 거래금액2
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.92, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.82, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.82, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "WISOL JAPAN Co.,Ltd"), 0.80, "그 밖의 특수관계자"),
        ],
    },

    "0f6392a45bf66cdd": {  # 2025.03 분기 별도주석: 특수관계자 거래금액 — (주)대덕·Daeduck Vietnam·엔알랩·와이솔·디아이티·WISOL JAPAN
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.93, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.84, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)디아이티"), 0.80, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "WISOL JAPAN Co.,Ltd"), 0.78, "그 밖의 특수관계자"),
        ],
    },

    "3aade223dc49f6a3": {  # 2025.03 분기 별도주석: 특수관계자 거래금액2
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.92, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.87, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.82, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.82, "그 밖의 특수관계자"),
        ],
    },

    "3cf74141432acfde": {  # 2025.03 분기 별도주석: 특수관계자 채권채무
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.91, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.86, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.80, "그 밖의 특수관계자"),
        ],
    },

    "5b8b807537b85774": {  # 2025.03 분기 별도주석: 특수관계자 채권채무2
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.91, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.85, "종속기업"),
        ],
    },

    "aeb382ede299f424": {  # 2025.03 분기 연결주석: 특수관계자 채권채무
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.91, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.80, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.80, "그 밖의 특수관계자"),
        ],
    },

    "e88b0d771031c4e8": {  # 2025.03 분기 연결주석: 특수관계자 자금거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.90, "지배기업"),
        ],
    },

    "c27909f7e0680a69": {  # 2025.03 분기 연결주석: 특수관계자 기타거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.90, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.80, "그 밖의 특수관계자"),
        ],
    },

    "0c47c3f8a3551471": {  # 2025.06 반기 연결주석: 특수관계자 거래금액 — (주)대덕·엔알랩·와이솔·WISOL JAPAN
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.93, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.84, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "WISOL JAPAN Co.,Ltd"), 0.80, "그 밖의 특수관계자"),
        ],
    },

    "21ff2f285472203d": {  # 2025.06 반기 연결주석: 특수관계자 거래금액2
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.92, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.82, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)디아이티"), 0.80, "그 밖의 특수관계자"),
        ],
    },

    "2c612a474922df6b": {  # 2025.06 반기 별도주석: 특수관계자 거래 상세 — (주)대덕·Daeduck Vietnam·Shanghai·DD USA·엔알랩·와이솔
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.95, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.85, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.83, "그 밖의 특수관계자"),
        ],
    },

    "a391a283d3050ed3": {  # 2025.06 반기 별도주석: 특수관계자 거래금액2
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.92, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.87, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.82, "그 밖의 특수관계자"),
        ],
    },

    "3ffe5ca96801df35": {  # 2025.06 반기 별도주석: 특수관계자 채권채무 상세
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.93, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.80, "그 밖의 특수관계자"),
        ],
    },

    "51142dbbc671ef54": {  # 2025.06 반기 별도주석: 특수관계자 채권채무2
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.91, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.86, "종속기업"),
        ],
    },

    "b922d1675ec097d6": {  # 2025.06 반기 연결주석: 특수관계자 채권채무
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.91, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.80, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.79, "그 밖의 특수관계자"),
        ],
    },

    "cc70b479bc51f910": {  # 2025.06 반기 연결주석: 특수관계자 거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.90, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.80, "그 밖의 특수관계자"),
        ],
    },

    "c75db21f70988e82": {  # 2025.06 반기 연결주석: 자금거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.90, "지배기업"),
        ],
    },

    "c8d483815b742a0b": {  # 2025.06 반기 별도주석: 자금거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.90, "지배기업"),
        ],
    },

    "13ca83b9ec9dd5ed": {  # 2025.09 분기 별도주석: 특수관계자 현황 — (주)대덕·Daeduck Vietnam·Shanghai·DD USA·와이솔·엔알랩·WISOL
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.95, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.87, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.87, "그 밖의 특수관계자"),
        ],
    },

    "15a106dacc59e35a": {  # 2025.09 분기 연결주석: 특수관계자 거래금액 상세 — (주)대덕·엔알랩·와이솔·디아이티
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.93, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.84, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)디아이티"), 0.80, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "WISOL JAPAN Co.,Ltd"), 0.78, "그 밖의 특수관계자"),
        ],
    },

    "3fe7f9d68b671fa7": {  # 2025.09 분기 연결주석: 특수관계자 거래금액2
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.92, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.82, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.82, "그 밖의 특수관계자"),
        ],
    },

    "74ebadd34e31e760": {  # 2025.09 분기 연결주석: 특수관계자 거래금액3
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.91, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.80, "그 밖의 특수관계자"),
        ],
    },

    "38fd7f5ebd820673": {  # 2025.09 분기 별도주석: 특수관계자 거래금액 — (주)대덕·Daeduck Vietnam·엔알랩·디아이티·WISOL JAPAN
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.93, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)디아이티"), 0.80, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "WISOL JAPAN Co.,Ltd"), 0.78, "그 밖의 특수관계자"),
        ],
    },

    "56c76516a65d9c2e": {  # 2025.09 분기 별도주석: 특수관계자 거래금액2
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.92, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.86, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.81, "그 밖의 특수관계자"),
        ],
    },

    "621644dcbd93ae17": {  # 2025.09 분기 별도주석: 특수관계자 채권채무 상세
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.93, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.82, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.80, "그 밖의 특수관계자"),
        ],
    },

    "bdd1cf46c1300031": {  # 2025.09 분기 별도주석: 특수관계자 채권채무2
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.91, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.85, "종속기업"),
        ],
    },

    "d1c4948e656a665d": {  # 2025.09 분기 연결주석: 특수관계자 채권채무
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.91, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.80, "그 밖의 특수관계자"),
        ],
    },

    "f852da21121fa02b": {  # 2025.09 분기 연결주석: 자금거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.90, "지배기업"),
        ],
    },

    "91e805c712ec5ea9": {  # 2025.12 사보 연결감사보고서: 특수관계자 현황
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.95, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.87, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.87, "그 밖의 특수관계자"),
        ],
    },

    "0765a6847c30dcd4": {  # 2025.12 사보 연결주석: 특수관계자 거래금액 — (주)대덕·엔알랩·디아이티·WISOL JAPAN
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.93, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.84, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)디아이티"), 0.81, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "WISOL JAPAN Co.,Ltd"), 0.79, "그 밖의 특수관계자"),
        ],
    },

    "40f8197b3e9e6b3b": {  # 2025.12 사보 연결주석: 특수관계자 거래금액2
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.92, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.82, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.80, "그 밖의 특수관계자"),
        ],
    },

    "80f5cf217753259b": {  # 2025.12 사보 연결주석: 특수관계자 거래금액3
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.91, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.80, "그 밖의 특수관계자"),
        ],
    },

    "07ed14c9ea1f262a": {  # 2025.12 사보 별도주석: 특수관계자 거래금액 — (주)대덕·Daeduck Vietnam·Shanghai·DD USA·엔알랩·와이솔·디아이티·WISOL JAPAN
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.95, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.85, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)디아이티"), 0.81, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "WISOL JAPAN Co.,Ltd"), 0.79, "그 밖의 특수관계자"),
        ],
    },

    "6fe6ffd22c6283fe": {  # 2025.12 사보 별도주석: 특수관계자 채권채무 — (주)대덕·Daeduck Vietnam·엔알랩·와이솔·디아이티·WISOL JAPAN
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.93, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.80, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)디아이티"), 0.78, "그 밖의 특수관계자"),
        ],
    },

    "829090f9136cdcf5": {  # 2025.12 사보 별도주석: 특수관계자 채권채무2
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.92, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.86, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.81, "그 밖의 특수관계자"),
        ],
    },

    "c17f9e2182aafbf2": {  # 2025.12 사보 연결주석: 특수관계자 채권채무
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.92, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.81, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.79, "그 밖의 특수관계자"),
        ],
    },

    "da7812d3f5b0f6c6": {  # 2025.12 사보 연결주석: 특수관계자 자금거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.90, "지배기업"),
        ],
    },

    "e02b367b4663e160": {  # 2025.12 사보 별도주석: 자금거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.90, "지배기업"),
        ],
    },

    "ec2627879ee828fc": {  # 2025.12 사보 별도주석: 특수관계자 추가거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.90, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.79, "그 밖의 특수관계자"),
        ],
    },

    "fe959db4aa5ac66e": {  # 2025.12 사보 연결주석: 추가 특수관계 거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.89, "지배기업"),
        ],
    },

    "1ffdc94610517b00": {  # 2026.03 분기 별도주석: 특수관계자 현황 — (주)대덕·Daeduck Vietnam·Shanghai·DD USA·엔알랩·와이솔·WISOL
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.95, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.90, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.87, "그 밖의 특수관계자((주)대덕의 종속기업)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.87, "그 밖의 특수관계자((주)대덕의 종속기업)"),
        ],
    },

    "8472eb8a794bcd17": {  # 2026.03 분기 연결주석: 특수관계자 현황 — (주)대덕·엔알랩·와이솔·WISOL JAPAN
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.95, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.87, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.87, "그 밖의 특수관계자"),
        ],
    },

    "880f49d5d7bddbd0": {  # 2026.03 분기 별도주석: 특수관계자 거래금액 — (주)대덕·Daeduck Vietnam·Shanghai·DD USA·엔알랩·와이솔·디아이티·WISOL JAPAN
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.93, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.88, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.84, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)디아이티"), 0.80, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "WISOL JAPAN Co.,Ltd"), 0.78, "그 밖의 특수관계자"),
        ],
    },

    "937ae6a0229233b9": {  # 2026.03 분기 별도주석: 특수관계자 거래금액2
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.92, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.86, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.81, "그 밖의 특수관계자"),
        ],
    },

    "968bdc7592162a7b": {  # 2026.03 분기 별도주석: 특수관계자 채권채무
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.93, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Daeduck Vietnam Co., Ltd"), 0.87, "종속기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.82, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.79, "그 밖의 특수관계자"),
        ],
    },

    "ab931ab9948849fb": {  # 2026.03 분기 연결주석: 특수관계자 거래금액 — (주)대덕·엔알랩·와이솔·WISOL JAPAN
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.93, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.83, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.82, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "WISOL JAPAN Co.,Ltd"), 0.79, "그 밖의 특수관계자"),
        ],
    },

    "ca111af93df7f394": {  # 2026.03 분기 연결주석: 특수관계자 거래금액2
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.91, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.80, "그 밖의 특수관계자"),
        ],
    },

    "d39a2f14f51a90cf": {  # 2026.03 분기 연결주석: 특수관계자 채권채무
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.91, "지배기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "엔알랩(주)"), 0.80, "그 밖의 특수관계자"),
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)와이솔"), 0.79, "그 밖의 특수관계자"),
        ],
    },

    "d84fed3e7c2ee3ff": {  # 2026.03 분기 별도주석: 자금거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.90, "지배기업"),
        ],
    },

    "f65d926b34d25bfa": {  # 2026.03 분기 연결주석: 자금거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "(주)대덕"), 0.90, "지배기업"),
        ],
    },

}


def process_chunk(drv, mconn, chunk: dict, extractions: dict) -> tuple[int, int]:
    """청크 한 개를 처리: 엔티티 MERGE + 엣지 MERGE + provenance 적재. (n_ent, n_edge) 반환."""
    cid = chunk["chunk_id"]
    rcept = chunk["rcept_no"]
    ext = extractions.get(cid)
    if not ext:
        return 0, 0

    n_ent = 0
    n_edge = 0

    # 1) 엔티티 MERGE
    eid_map: dict[tuple, str] = {}
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
        else:
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
    print(f"[extract_daeduck_01478712] 대덕전자 비정형 추출 시작")
    already = ledger_processed_ids()
    print(f"  이미 처리된 chunk_id: {len(already)}개")

    drv = neo4j_driver()
    mconn = mariadb_conn()

    where = (
        "WHERE corp_code='01478712' "
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
    print("[extract_daeduck_01478712] 완료")


if __name__ == "__main__":
    main()
