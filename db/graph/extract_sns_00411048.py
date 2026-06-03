"""Stage 5 비정형 추출 — 에스앤에스텍 corp_code=00411048, text_micro 전체(1,099) + table_nl 특수관계(117).

에스앤에스텍 = 반도체·디스플레이용 블랭크마스크 전문업체(국내 유일).
Product = 블랭크마스크(반도체용/디스플레이용), EUV 블랭크마스크, EUV 펠리클.
Technology = EUV Lithography, 노광공정(Photo Lithography), 위상반전막 증착기술.
SUPPLIES_TO = 에스앤에스텍 → 삼성전자(블랭크마스크 매출, 삼성전자 지분율 8.0% 대주주).
RELATED_PARTY = 에스앤에스인베스트먼트(주)(종속기업).

원장 = db/graph/ledger/extra28_00411048.jsonl (이 추출 전용).
실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_sns_00411048.py
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

CORP = "에스앤에스텍"
CORP_CODE = "00411048"

# ── 전용 원장 ─────────────────────────────────────────────────
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_DIR.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = LEDGER_DIR / "extra28_00411048.jsonl"


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
#
# 에스앤에스텍은 반도체·디스플레이 소재 전문기업
# 핵심제품: 블랭크마스크(반도체용/디스플레이용), EUV 블랭크마스크, EUV 펠리클
# 핵심기술: EUV Lithography, 노광공정(Photo Lithography), 위상반전막 증착
# 매출처: 삼성전자(지분율 8.0%, X. 대주주 이외의 이해관계자 거래 공시)
# 종속기업: 에스앤에스인베스트먼트(주), 에스앤에스랩(주)
EXTRACTIONS: dict[str, dict] = {

    # ── II. 사업의 내용: 블랭크마스크 제품 소개 (2023 사업보고서) ──
    "003bffed4fc34dcf": {  # 감사보고서 수익인식: 블랭크마스크 제조 및 판매
        "entities": [
            (P, "블랭크마스크", "블랭크마스크"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "블랭크마스크", "블랭크마스크"), 0.95),
        ],
    },
    "a1ded9e106908129": {  # II 사업개요: 반도체/FPD용 블랭크마스크 제조·판매
        "entities": [
            (P, "블랭크마스크", "블랭크마스크"),
            (P, "반도체용 블랭크마스크", "반도체용 블랭크마스크"),
            (P, "디스플레이용 블랭크마스크", "디스플레이용 블랭크마스크"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "블랭크마스크", "블랭크마스크"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체용 블랭크마스크", "반도체용 블랭크마스크"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "디스플레이용 블랭크마스크", "디스플레이용 블랭크마스크"), 0.95),
        ],
    },
    "3848806df5d719b7": {  # II 블랭크마스크 구조: 반도체용(6x6인치 석영기판, 크롬막, PR), FPD용(10세대)
        "entities": [
            (P, "반도체용 블랭크마스크", "반도체용 블랭크마스크"),
            (P, "디스플레이용 블랭크마스크", "디스플레이용 블랭크마스크"),
            (T, "위상반전막 증착기술", "위상반전막 증착기술"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체용 블랭크마스크", "반도체용 블랭크마스크"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "디스플레이용 블랭크마스크", "디스플레이용 블랭크마스크"), 0.92),
            E("USES_TECH", ("org", CORP), ("ent", T, "위상반전막 증착기술", "위상반전막 증착기술"), 0.85),
        ],
    },
    "90ef545582d22e7a": {  # II 영업개황: 국내 유일 블랭크마스크 전문업체, 국내 반도체·LCD 시장 진입
        "entities": [
            (P, "블랭크마스크", "블랭크마스크"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "블랭크마스크", "블랭크마스크"), 0.95),
        ],
    },

    # ── II. 사업의 내용: EUV 블랭크마스크 및 EUV 펠리클 (2024 사업보고서) ──
    "4057fea0656efc30": {  # IV 이사의 경영진단: EUV 블랭크마스크·EUV 펠리클 양산 투자 진행 중
        "entities": [
            (P, "EUV 블랭크마스크", "EUV 블랭크마스크"),
            (P, "EUV 펠리클", "EUV 펠리클"),
            (T, "EUV Lithography", "EUV Lithography"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "EUV 블랭크마스크", "EUV 블랭크마스크"), 0.88),
            E("PRODUCES", ("org", CORP), ("ent", P, "EUV 펠리클", "EUV 펠리클"), 0.88),
            E("USES_TECH", ("org", CORP), ("ent", T, "EUV Lithography", "EUV Lithography"), 0.88),
        ],
    },
    "90bb801bbc81207b": {  # IV 유동성: EUV용 블랭크마스크·EUV 펠리클 양산 신공장(용인) 투자
        "entities": [
            (P, "EUV 블랭크마스크", "EUV 블랭크마스크"),
            (P, "EUV 펠리클", "EUV 펠리클"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "EUV 블랭크마스크", "EUV 블랭크마스크"), 0.9),
            E("PRODUCES", ("org", CORP), ("ent", P, "EUV 펠리클", "EUV 펠리클"), 0.9),
        ],
    },
    "c57bbb11c6bc7de9": {  # IV R&D: EUV Lithography 소재기술 개발 집중
        "entities": [
            (T, "EUV Lithography", "EUV Lithography"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "EUV Lithography", "EUV Lithography"), 0.9),
        ],
    },

    # ── II. 사업의 내용: 반도체용 블랭크마스크 구조 (각 보고서 반복) ──
    "844b047f93954afc": {  # II 블랭크마스크 구조: 석영기판+크롬+PR, 위상반전막 추가 증착
        "entities": [
            (P, "반도체용 블랭크마스크", "반도체용 블랭크마스크"),
            (T, "위상반전막 증착기술", "위상반전막 증착기술"),
            (T, "Photo Lithography", "노광공정(Photo Lithography)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체용 블랭크마스크", "반도체용 블랭크마스크"), 0.95),
            E("USES_TECH", ("org", CORP), ("ent", T, "위상반전막 증착기술", "위상반전막 증착기술"), 0.85),
        ],
    },
    "94af01a492a92a3a": {  # II 사업개요(2024): 블랭크마스크 생산·판매, 포토마스크 원재료
        "entities": [
            (P, "블랭크마스크", "블랭크마스크"),
            (P, "반도체용 블랭크마스크", "반도체용 블랭크마스크"),
            (T, "Photo Lithography", "노광공정(Photo Lithography)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "블랭크마스크", "블랭크마스크"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체용 블랭크마스크", "반도체용 블랭크마스크"), 0.95),
            E("USES_TECH", ("org", CORP), ("ent", T, "Photo Lithography", "노광공정(Photo Lithography)"), 0.82),
        ],
    },

    # ── II. 사업의 내용: EUV 중심 신사업 (2025+ 보고서) ──
    "18663ca5ecc68415": {  # II(2025Q3): EUV 블랭크마스크·EUV 펠리클 양산 시설 투자 진행 중
        "entities": [
            (P, "EUV 블랭크마스크", "EUV 블랭크마스크"),
            (P, "EUV 펠리클", "EUV 펠리클"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "EUV 블랭크마스크", "EUV 블랭크마스크"), 0.88),
            E("PRODUCES", ("org", CORP), ("ent", P, "EUV 펠리클", "EUV 펠리클"), 0.88),
        ],
    },
    "1cc10914e98c8b15": {  # II(2025사업): EUV 센터 준공, 관련 제품 양산 준비
        "entities": [
            (P, "EUV 블랭크마스크", "EUV 블랭크마스크"),
            (T, "EUV Lithography", "EUV Lithography"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "EUV 블랭크마스크", "EUV 블랭크마스크"), 0.9),
            E("USES_TECH", ("org", CORP), ("ent", T, "EUV Lithography", "EUV Lithography"), 0.88),
        ],
    },
    "936e05c21fda1497": {  # II(2025반기): EUV 블랭크마스크·EUV 펠리클 양산 시설 투자 진행 중
        "entities": [
            (P, "EUV 블랭크마스크", "EUV 블랭크마스크"),
            (P, "EUV 펠리클", "EUV 펠리클"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "EUV 블랭크마스크", "EUV 블랭크마스크"), 0.9),
            E("PRODUCES", ("org", CORP), ("ent", P, "EUV 펠리클", "EUV 펠리클"), 0.9),
        ],
    },
    "4309f10f65def3eb": {  # II(2025Q1): EUV 블랭크마스크·EUV 펠리클 양산 시설 투자 진행 중
        "entities": [
            (P, "EUV 블랭크마스크", "EUV 블랭크마스크"),
            (P, "EUV 펠리클", "EUV 펠리클"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "EUV 블랭크마스크", "EUV 블랭크마스크"), 0.9),
            E("PRODUCES", ("org", CORP), ("ent", P, "EUV 펠리클", "EUV 펠리클"), 0.9),
        ],
    },
    "ffd8ba758b217c00": {  # II(2024사업): EUV 블랭크마스크·EUV 펠리클 양산 시설 투자 진행 중
        "entities": [
            (P, "EUV 블랭크마스크", "EUV 블랭크마스크"),
            (P, "EUV 펠리클", "EUV 펠리클"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "EUV 블랭크마스크", "EUV 블랭크마스크"), 0.9),
            E("PRODUCES", ("org", CORP), ("ent", P, "EUV 펠리클", "EUV 펠리클"), 0.9),
        ],
    },
    "6d2c198e6eb8b74b": {  # IV(2025사업): EUV용 블랭크마스크 양산 준비 대규모 시설투자
        "entities": [
            (P, "EUV 블랭크마스크", "EUV 블랭크마스크"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "EUV 블랭크마스크", "EUV 블랭크마스크"), 0.9),
        ],
    },
    "659590e56b120a6d": {  # IV(2025사업): EUV Lithography 소재기술 개발 집중, R&D 시설투자 424억
        "entities": [
            (T, "EUV Lithography", "EUV Lithography"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "EUV Lithography", "EUV Lithography"), 0.9),
        ],
    },
    "b2279285497a73f3": {  # II(2026Q1): EUV 센터 준공, 관련 제품 양산 준비
        "entities": [
            (P, "EUV 블랭크마스크", "EUV 블랭크마스크"),
            (T, "EUV Lithography", "EUV Lithography"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "EUV 블랭크마스크", "EUV 블랭크마스크"), 0.9),
            E("USES_TECH", ("org", CORP), ("ent", T, "EUV Lithography", "EUV Lithography"), 0.88),
        ],
    },

    # ── II. 사업의 내용: 사업 개요 (각 보고서) ──
    "0af46700e8563f9f": {  # II(2026Q1) 사업개요: 반도체·디스플레이용 블랭크마스크 생산·판매
        "entities": [
            (P, "블랭크마스크", "블랭크마스크"),
            (P, "반도체용 블랭크마스크", "반도체용 블랭크마스크"),
            (P, "디스플레이용 블랭크마스크", "디스플레이용 블랭크마스크"),
            (T, "Photo Lithography", "노광공정(Photo Lithography)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "블랭크마스크", "블랭크마스크"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체용 블랭크마스크", "반도체용 블랭크마스크"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "디스플레이용 블랭크마스크", "디스플레이용 블랭크마스크"), 0.93),
            E("USES_TECH", ("org", CORP), ("ent", T, "Photo Lithography", "노광공정(Photo Lithography)"), 0.82),
        ],
    },
    "d2d037c99ae5604d": {  # II(2025반기) 사업개요: 블랭크마스크 생산·판매
        "entities": [
            (P, "블랭크마스크", "블랭크마스크"),
            (T, "Photo Lithography", "노광공정(Photo Lithography)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "블랭크마스크", "블랭크마스크"), 0.97),
            E("USES_TECH", ("org", CORP), ("ent", T, "Photo Lithography", "노광공정(Photo Lithography)"), 0.82),
        ],
    },
    "b307caf440c403f7": {  # II(2025Q3) 사업개요: 반도체·디스플레이용 블랭크마스크 생산·판매
        "entities": [
            (P, "블랭크마스크", "블랭크마스크"),
            (P, "반도체용 블랭크마스크", "반도체용 블랭크마스크"),
            (T, "Photo Lithography", "노광공정(Photo Lithography)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "블랭크마스크", "블랭크마스크"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체용 블랭크마스크", "반도체용 블랭크마스크"), 0.95),
            E("USES_TECH", ("org", CORP), ("ent", T, "Photo Lithography", "노광공정(Photo Lithography)"), 0.82),
        ],
    },
    "23bafc9dae56254c": {  # II(2025Q1) 사업개요: 블랭크마스크 생산·판매
        "entities": [
            (P, "블랭크마스크", "블랭크마스크"),
            (T, "Photo Lithography", "노광공정(Photo Lithography)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "블랭크마스크", "블랭크마스크"), 0.97),
            E("USES_TECH", ("org", CORP), ("ent", T, "Photo Lithography", "노광공정(Photo Lithography)"), 0.82),
        ],
    },

    # ── II. 사업의 내용: 블랭크마스크 구조 반복 기술 (중복 제거용 대표 청크) ──
    "0b0733c2bb4c6749": {  # II(2025Q1) 블랭크마스크 구조: 석영기판+크롬, 위상반전막
        "entities": [
            (P, "반도체용 블랭크마스크", "반도체용 블랭크마스크"),
            (P, "디스플레이용 블랭크마스크", "디스플레이용 블랭크마스크"),
            (T, "위상반전막 증착기술", "위상반전막 증착기술"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체용 블랭크마스크", "반도체용 블랭크마스크"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "디스플레이용 블랭크마스크", "디스플레이용 블랭크마스크"), 0.92),
            E("USES_TECH", ("org", CORP), ("ent", T, "위상반전막 증착기술", "위상반전막 증착기술"), 0.85),
        ],
    },
    "347d987bb94e00bb": {  # II(2025Q3) 블랭크마스크 구조: 석영기판+크롬, 위상반전막
        "entities": [
            (P, "반도체용 블랭크마스크", "반도체용 블랭크마스크"),
            (P, "디스플레이용 블랭크마스크", "디스플레이용 블랭크마스크"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체용 블랭크마스크", "반도체용 블랭크마스크"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "디스플레이용 블랭크마스크", "디스플레이용 블랭크마스크"), 0.92),
        ],
    },
    "c7240ba6542f59b5": {  # II(2025사업) 블랭크마스크 구조
        "entities": [
            (P, "반도체용 블랭크마스크", "반도체용 블랭크마스크"),
            (P, "디스플레이용 블랭크마스크", "디스플레이용 블랭크마스크"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체용 블랭크마스크", "반도체용 블랭크마스크"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "디스플레이용 블랭크마스크", "디스플레이용 블랭크마스크"), 0.92),
        ],
    },

    # ── II. 사업의 내용: 바이오 및 과학기술 서비스업(에스앤에스랩) ──
    "5bda47f0064d64f3": {  # II(2024사업): 에스앤에스랩 — 바이오 벤처 컴퍼니빌딩 사업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "에스앤에스랩"), 0.92, "종속기업(바이오벤처 컴퍼니빌딩)"),
        ],
    },
    "5eb2a93fc9fe15db": {  # II(2025사업): 에스앤에스랩 — 바이오 벤처 컴퍼니빌딩 사업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "에스앤에스랩"), 0.92, "종속기업(바이오벤처 컴퍼니빌딩)"),
        ],
    },
    "8bdc7217dd394bf7": {  # II(2026Q1): 에스앤에스랩 — 바이오 벤처 컴퍼니빌딩 사업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "에스앤에스랩"), 0.9, "종속기업(바이오벤처 컴퍼니빌딩)"),
        ],
    },

    # ── IV. 이사의 경영진단: EUV 제품 개발 및 기술 (2023 사업보고서) ──
    "61cb2672f86296ac": {  # IV(2023사업): EUV Lithography 소재기술 개발 및 양산화
        "entities": [
            (T, "EUV Lithography", "EUV Lithography"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "EUV Lithography", "EUV Lithography"), 0.88),
        ],
    },
    "b20d3d6d4b001b6c": {  # IV(2023사업): EUV 제품 연구개발 결과 준비 중
        "entities": [
            (P, "EUV 블랭크마스크", "EUV 블랭크마스크"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "EUV 블랭크마스크", "EUV 블랭크마스크"), 0.82),
        ],
    },

    # ── X. 대주주 등과의 거래내용: 삼성전자 블랭크마스크 매출 ──
    # 삼성전자 = 지분율 8.0% 대주주 이외의 이해관계자, 블랭크마스크 매출
    "ad0a1dc0bce435b2": {  # X(2023사업): 삼성전자 블랭크마스크 매출 108억(당기), 125억(전기)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "대주주이외이해관계자(지분율 8.0%, 블랭크마스크 매출)"),
        ],
    },
    "7cb4429d6eaf320c": {  # X(2024Q1): 삼성전자 블랭크마스크 매출 23억(당기1Q)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "대주주이외이해관계자(지분율 8.0%, 블랭크마스크 매출)"),
        ],
    },
    "b50a5f80faa821fb": {  # X(2024반기): 삼성전자 블랭크마스크 매출 49억(당반기)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "대주주이외이해관계자(지분율 8.0%, 블랭크마스크 매출)"),
        ],
    },
    "cb1869f141c5e3f6": {  # X(2024Q3): 삼성전자 블랭크마스크 매출 80억(당3분기)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "대주주이외이해관계자(지분율 8.0%, 블랭크마스크 매출)"),
        ],
    },
    "66db4a372b871c52": {  # X(2024사업): 삼성전자 블랭크마스크 매출 110억(당기)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "대주주이외이해관계자(지분율 8.0%, 블랭크마스크 매출)"),
        ],
    },
    "9f683c3770f5cd9c": {  # X(2025Q1): 삼성전자 블랭크마스크 매출 35억(당1분기)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "대주주이외이해관계자(지분율 8.0%, 블랭크마스크 매출)"),
        ],
    },
    "8664e587b0826b4b": {  # X(2025반기): 삼성전자 블랭크마스크 매출 66억(당반기)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "대주주이외이해관계자(지분율 8.0%, 블랭크마스크 매출)"),
        ],
    },
    "6f62f4fd1044a9eb": {  # X(2025Q3): 삼성전자 블랭크마스크 매출 94억(당3분기)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "대주주이외이해관계자(지분율 8.0%, 블랭크마스크 매출)"),
        ],
    },
    "bbbcdd2bed6d246a": {  # X(2025사업): 삼성전자 블랭크마스크 매출 133억(당기)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "대주주이외이해관계자(지분율 8.0%, 블랭크마스크 매출)"),
        ],
    },
    "ffb9041d9b466c06": {  # X(2026Q1): 삼성전자 블랭크마스크 매출 34억(당1분기)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.97),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.97, "대주주이외이해관계자(지분율 8.0%, 블랭크마스크 매출)"),
        ],
    },

    # ── 재무제표 주석 특수관계자: 에스앤에스인베스트먼트(주) 종속기업 ──
    "4a428eb2ffa4b4e5": {  # 감사보고서(2023) 특수관계자 수입임대료: 에스앤에스인베스트먼트(주)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "에스앤에스인베스트먼트"), 0.95, "종속기업(투자·컨설팅)"),
        ],
    },
    "69d7e642ccf6d49d": {  # 재무제표주석(2023사업) 특수관계자: 에스앤에스인베스트먼트(주) 종속기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "에스앤에스인베스트먼트"), 0.95, "종속기업(투자·컨설팅)"),
        ],
    },
    "23b45d88d46bad7f": {  # 재무제표주석(2024반기) 특수관계자: 에스앤에스인베스트먼트(주) 수입임대료
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "에스앤에스인베스트먼트"), 0.95, "종속기업(투자·컨설팅)"),
        ],
    },
    "1f61ccfcdb411e7b": {  # 재무제표주석(2024Q3) 특수관계자: 에스앤에스인베스트먼트(주) 수입임대료
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "에스앤에스인베스트먼트"), 0.95, "종속기업(투자·컨설팅)"),
        ],
    },
    "15dd070ae2c6bcf0": {  # 재무제표주석(2024사업) 특수관계자: 에스앤에스인베스트먼트(주) 출자금 회수
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "에스앤에스인베스트먼트"), 0.95, "종속기업(투자·컨설팅)"),
        ],
    },
    "42acfae446f2e7e6": {  # 재무제표주석(2025반기) 특수관계자: 에스앤에스인베스트먼트(주) 수입임대료
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "에스앤에스인베스트먼트"), 0.95, "종속기업(투자·컨설팅)"),
        ],
    },
    "5e949241280cfa95": {  # 재무제표주석(2025Q3) 특수관계자: 에스앤에스인베스트먼트(주) 수입임대료
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "에스앤에스인베스트먼트"), 0.95, "종속기업(투자·컨설팅)"),
        ],
    },
    "5b69725c640b7f65": {  # 감사보고서(2025사업) 특수관계자: 에스앤에스인베스트먼트(주) 수입임대료
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "에스앤에스인베스트먼트"), 0.95, "종속기업(투자·컨설팅)"),
        ],
    },
    "260302590bcfee6e": {  # 재무제표주석(2026Q1) 특수관계자: 에스앤에스인베스트먼트(주) 수입임대료
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "에스앤에스인베스트먼트"), 0.95, "종속기업(투자·컨설팅)"),
        ],
    },

    # ── 연결감사보고서 특수관계자 목록표 ──
    "2d34e150d9a4cf5b": {  # 연결감사보고서(2023) 특수관계자 목록: 에스앤에스인베스트먼트 종속기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "에스앤에스인베스트먼트"), 0.95, "종속기업(투자·컨설팅)"),
        ],
    },
    "3476d1187b4cb0a4": {  # 연결재무제표주석(2023) 특수관계자 목록
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "에스앤에스인베스트먼트"), 0.95, "종속기업(투자·컨설팅)"),
        ],
    },

    # ── II. 사업의 내용: 영업 개황 (반도체 기업과 품질인증·판매계약) ──
    "3b36f5eb8964f7b6": {  # II(2024사업) 영업개황: 주요 국내 반도체 기업과 품질인증·판매계약
        "entities": [
            (P, "블랭크마스크", "블랭크마스크"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "블랭크마스크", "블랭크마스크"), 0.92),
        ],
    },
    "5f9a484bfdf7b9ca": {  # II(2026Q1) 영업개황: 주요 국내 반도체 기업과 품질인증·판매계약
        "entities": [
            (P, "블랭크마스크", "블랭크마스크"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "블랭크마스크", "블랭크마스크"), 0.92),
        ],
    },
    "b4e9a31a81f79e2b": {  # II(2025사업) 영업개황: 주요 국내 반도체 기업과 품질인증·판매계약
        "entities": [
            (P, "블랭크마스크", "블랭크마스크"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "블랭크마스크", "블랭크마스크"), 0.92),
        ],
    },

    # ── III 수익 인식(각 사업/분기보고서 반복) ──
    "0559f43054ed3777": {  # 재무제표주석(2024사업) 수익: 블랭크마스크 제조·판매
        "entities": [
            (P, "블랭크마스크", "블랭크마스크"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "블랭크마스크", "블랭크마스크"), 0.95),
        ],
    },
    "5db01e2c38f1003a": {  # 재무제표주석(2023사업) 수익: 블랭크마스크 제조·판매
        "entities": [
            (P, "블랭크마스크", "블랭크마스크"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "블랭크마스크", "블랭크마스크"), 0.95),
        ],
    },
    "7007b1d7b8d85b8e": {  # 감사보고서(2024사업) 수익: 블랭크마스크 제조·판매
        "entities": [
            (P, "블랭크마스크", "블랭크마스크"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "블랭크마스크", "블랭크마스크"), 0.95),
        ],
    },
    "857d9b6712f58a44": {  # 감사보고서(2025사업) 수익: 블랭크마스크 제조·판매
        "entities": [
            (P, "블랭크마스크", "블랭크마스크"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "블랭크마스크", "블랭크마스크"), 0.95),
        ],
    },
    "253ba8101f851356": {  # 연결감사보고서(2025사업) 수익: 지배기업 블랭크마스크, 종속기업 투자·컨설팅
        "entities": [
            (P, "블랭크마스크", "블랭크마스크"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "블랭크마스크", "블랭크마스크"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "에스앤에스인베스트먼트"), 0.93, "종속기업(투자·컨설팅)"),
        ],
    },
    "46e1d6da5633f826": {  # 감사보고서(2025사업) 회사개요: 블랭크마스크 제조·판매
        "entities": [
            (P, "블랭크마스크", "블랭크마스크"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "블랭크마스크", "블랭크마스크"), 0.95),
        ],
    },
    "6fb8d113efae8b4b": {  # 감사보고서(2024사업) 회사개요: 블랭크마스크 제조·판매
        "entities": [
            (P, "블랭크마스크", "블랭크마스크"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "블랭크마스크", "블랭크마스크"), 0.95),
        ],
    },

    # ── III 연결재무제표주석 수익(지배기업: 블랭크마스크, 종속기업: 투자·컨설팅) ──
    "58f569c3e27ae880": {  # 연결감사보고서(2024사업) 수익: 지배기업 블랭크마스크
        "entities": [
            (P, "블랭크마스크", "블랭크마스크"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "블랭크마스크", "블랭크마스크"), 0.95),
        ],
    },
    "288db32392be3cbf": {  # 연결재무제표주석(2025사업) 수익: 지배기업 블랭크마스크, 종속기업 투자·컨설팅
        "entities": [
            (P, "블랭크마스크", "블랭크마스크"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "블랭크마스크", "블랭크마스크"), 0.95),
        ],
    },

    # ── IV. 이사의 경영진단: EUV R&D 및 기술 개발 (2024사업) ──
    "af9cc865d9c77786": {  # IV(2024사업): EUV Lithography 소재기술 개발, OLED 디스플레이 기술 집중
        "entities": [
            (T, "EUV Lithography", "EUV Lithography"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "EUV Lithography", "EUV Lithography"), 0.9),
        ],
    },

    # ── 연결감사보고서 특수관계자 목록(2024, 2025) ──
    "369f4c92bac43659": {  # 연결감사보고서(2024사업) 특수관계자 목록: 에스앤에스인베스트먼트 종속기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "에스앤에스인베스트먼트"), 0.95, "종속기업(투자·컨설팅)"),
        ],
    },
    "3151edc132174041": {  # 연결감사보고서(2025사업) 특수관계자 목록: 에스앤에스인베스트먼트 종속기업
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "에스앤에스인베스트먼트"), 0.95, "종속기업(투자·컨설팅)"),
        ],
    },
}


def run():
    rows_text = get_chunks(
        f"WHERE corp_code='{CORP_CODE}' AND chunk_type='text_micro' ORDER BY chunk_id"
    )
    rows_table = get_chunks(
        f"WHERE corp_code='{CORP_CODE}' AND chunk_type='table_nl'"
        f" AND embedding_text LIKE '%특수관계%' ORDER BY chunk_id"
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

    # 2) 나머지 청크 = 엔티티 0개 (누락 0 보장)
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
    print("=== 에스앤에스텍 Stage5 추출 결과 ===")
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
