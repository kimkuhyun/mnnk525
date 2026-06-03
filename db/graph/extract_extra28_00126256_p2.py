"""비정형 관계 추출 적재 — 삼성생명 (corp_code=00126256) text_micro 후반부 (OFFSET 2200, ~1,995청크).

EXTRACTIONS = Claude(에이전트)가 대상 배치 청크 본문을 읽고 본문 근거로 판단한
엔티티·엣지. 적재는 extract_helpers 멱등 헬퍼로 수행.
원장: db/graph/ledger/extra28_00126256_p2.jsonl (전용, 공유 원장 금지).
대상 청크 전부 mark_processed(엣지 0개여도) → 누락 0.

실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_extra28_00126256_p2.py
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

CORP_CODE = "00126256"
SAMSUNG_LIFE = "삼성생명"  # 주체 회사

LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_PATH = LEDGER_DIR / "extra28_00126256_p2.jsonl"

P = "Product"
T = "Technology"


def E(rel, frm, to, conf, relation_type=None):
    d = {"rel": rel, "from": frm, "to": to, "conf": conf}
    if relation_type:
        d["relation_type"] = relation_type
    return d


def mark_processed(chunk_id, n_ent, n_edge, rcept_no=None, section_path=None):
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    rec = {
        "chunk_id": chunk_id, "n_ent": n_ent, "n_edge": n_edge,
        "rcept_no": rcept_no, "section_path": section_path,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def ledger_processed_ids():
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


# ── 비정형 추출 정의 ────────────────────────────────────────────────────────
# 형식:
#   chunk_id: {
#     "entities": [(label, canonical, display_name), ...],
#     "edges":   [E(rel, from_spec, to_spec, confidence, relation_type?), ...],
#   }
#
# from_spec / to_spec:
#   ("org", "회사명문자열")              → resolve_org 매칭
#   ("ent", label, canonical, display)  → Product/Technology 엔티티
#
# 본문 근거가 확실한 청크만 엣지 부여. 근거 없으면 entities만 0, edges []로 mark.

EXTRACTIONS: dict[str, dict] = {

    # ── II. 사업의 내용 — 삼성카드 종속회사 언급 ──────────────────
    "886cd21bf1bc9618": {  # 삼성카드 통화스왑·이자율스왑 + 신용카드 사업
        "entities": [
            (P, "신용카드", "신용카드"),
            (P, "통화스왑", "통화스왑"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성카드"), ("org", SAMSUNG_LIFE), 0.92, "종속회사"),
            E("PRODUCES", ("org", "삼성카드"), ("ent", P, "신용카드", "신용카드"), 0.95),
        ],
    },

    "8919635f5ccbc797": {  # 삼성카드 신용카드 사업 + 할부리스
        "entities": [
            (P, "신용카드", "신용카드"),
            (P, "할부금융", "할부금융"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성카드"), ("org", SAMSUNG_LIFE), 0.92, "종속회사"),
            E("PRODUCES", ("org", "삼성카드"), ("ent", P, "신용카드", "신용카드"), 0.95),
            E("PRODUCES", ("org", "삼성카드"), ("ent", P, "할부금융", "할부금융"), 0.88),
        ],
    },

    "8f8bae4392e251de": {  # 삼성카드 보험대리판매, 온라인쇼핑몰, 여행알선
        "entities": [
            (P, "보험대리판매서비스", "보험대리판매서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", "삼성카드"), ("ent", P, "보험대리판매서비스", "보험대리판매서비스"), 0.82),
        ],
    },

    "8d0678f2ff6f7fcc": {  # 삼성카드 + 삼성자산운용 지점현황 (케이만 재간접PE펀드 포함)
        "entities": [
            (P, "pe펀드", "PE펀드(사모펀드)"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성카드"), ("org", SAMSUNG_LIFE), 0.90, "종속회사"),
            E("RELATED_PARTY", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.90, "종속회사"),
            E("PRODUCES", ("org", "삼성자산운용"), ("ent", P, "pe펀드", "PE펀드(사모펀드)"), 0.85),
        ],
    },

    "8e3952683e208534": {  # 삼성자산운용 케이만 Samsung Global Private Equity 펀드
        "entities": [
            (P, "samsung global private equity fund", "Samsung Global Private Equity Fund"),
        ],
        "edges": [
            E("PRODUCES", ("org", "삼성자산운용"), ("ent", P, "samsung global private equity fund", "Samsung Global Private Equity Fund"), 0.88),
        ],
    },

    "87e88eba79f6eeb0": {  # 삼성에스알에이자산운용 부동산펀드 + 삼성생명서비스손해사정
        "entities": [
            (P, "부동산펀드", "부동산펀드"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성에스알에이자산운용"), ("org", SAMSUNG_LIFE), 0.92, "종속회사"),
            E("RELATED_PARTY", ("org", "삼성생명서비스손해사정"), ("org", SAMSUNG_LIFE), 0.92, "종속회사"),
            E("PRODUCES", ("org", "삼성에스알에이자산운용"), ("ent", P, "부동산펀드", "부동산펀드"), 0.93),
        ],
    },

    "8836563a5128bae8": {  # 삼성에스알에이자산운용 부동산펀드 전문투자 (사업보고서 2023.12)
        "entities": [
            (P, "부동산펀드", "부동산펀드"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성에스알에이자산운용"), ("org", SAMSUNG_LIFE), 0.92, "종속회사"),
            E("PRODUCES", ("org", "삼성에스알에이자산운용"), ("ent", P, "부동산펀드", "부동산펀드"), 0.93),
        ],
    },

    "888346dd2f53ab96": {  # 삼성자산운용 업계1위, 펀드운용·투자자문·일임
        "entities": [
            (P, "집합투자증권(펀드)", "집합투자증권(펀드)"),
            (P, "투자일임계약", "투자일임계약"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("PRODUCES", ("org", "삼성자산운용"), ("ent", P, "집합투자증권(펀드)", "집합투자증권(펀드)"), 0.92),
            E("PRODUCES", ("org", "삼성자산운용"), ("ent", P, "투자일임계약", "투자일임계약"), 0.88),
        ],
    },

    "88d2eae5e63f15ee": {  # 삼성자산운용 설립내력 + 삼성액티브자산운용 물적분할
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("RELATED_PARTY", ("org", "삼성액티브자산운용"), ("org", SAMSUNG_LIFE), 0.90, "종속회사"),
        ],
    },

    "8ed74765aa6decdc": {  # 삼성자산운용 설립·삼성액티브자산운용 물적분할 (2023.12)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("RELATED_PARTY", ("org", "삼성액티브자산운용"), ("org", SAMSUNG_LIFE), 0.90, "종속회사"),
        ],
    },

    "9156c4b020eb5dab": {  # 삼성카드 + 삼성자산운용 + 삼성액티브자산운용
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성카드"), ("org", SAMSUNG_LIFE), 0.92, "종속회사"),
            E("RELATED_PARTY", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("RELATED_PARTY", ("org", "삼성액티브자산운용"), ("org", SAMSUNG_LIFE), 0.90, "종속회사"),
        ],
    },

    "8cf4e6f9757463d1": {  # 삼성자산운용 2024 업계1위, ETF·재간접·PEF 운용
        "entities": [
            (P, "etf", "ETF(상장지수펀드)"),
            (P, "재간접펀드", "재간접펀드"),
            (P, "사모펀드(pef)", "사모펀드(PEF)"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("PRODUCES", ("org", "삼성자산운용"), ("ent", P, "etf", "ETF(상장지수펀드)"), 0.93),
            E("PRODUCES", ("org", "삼성자산운용"), ("ent", P, "재간접펀드", "재간접펀드"), 0.88),
            E("PRODUCES", ("org", "삼성자산운용"), ("ent", P, "사모펀드(pef)", "사모펀드(PEF)"), 0.87),
        ],
    },

    "8974c7d061ddf98a": {  # 삼성자산운용 ETF·재간접·PEF (분기 2024.09)
        "entities": [
            (P, "etf", "ETF(상장지수펀드)"),
            (P, "재간접펀드", "재간접펀드"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("PRODUCES", ("org", "삼성자산운용"), ("ent", P, "etf", "ETF(상장지수펀드)"), 0.92),
        ],
    },

    "96c93170182abe87": {  # 삼성자산운용 반기 2024.06 ETF·TDF
        "entities": [
            (P, "tdf", "TDF(타겟데이트펀드)"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("PRODUCES", ("org", "삼성자산운용"), ("ent", P, "tdf", "TDF(타겟데이트펀드)"), 0.88),
            E("PRODUCES", ("org", "삼성자산운용"), ("ent", P, "etf", "ETF(상장지수펀드)"), 0.92),
        ],
    },

    "9111c60d642b99b3": {  # 삼성자산운용 ETF TDF OCIO 반기
        "entities": [
            (P, "ocio", "OCIO(외부위탁운용)"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("PRODUCES", ("org", "삼성자산운용"), ("ent", P, "etf", "ETF(상장지수펀드)"), 0.92),
            E("PRODUCES", ("org", "삼성자산운용"), ("ent", P, "tdf", "TDF(타겟데이트펀드)"), 0.88),
            E("PRODUCES", ("org", "삼성자산운용"), ("ent", P, "ocio", "OCIO(외부위탁운용)"), 0.88),
        ],
    },

    "89c2e342a8a723d9": {  # 삼성자산운용 Kodex200 ETF 최초 상장 언급 반기 2025.06
        "entities": [
            (P, "kodex 200", "Kodex 200"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("PRODUCES", ("org", "삼성자산운용"), ("ent", P, "kodex 200", "Kodex 200"), 0.95),
            E("PRODUCES", ("org", "삼성자산운용"), ("ent", P, "etf", "ETF(상장지수펀드)"), 0.93),
        ],
    },

    "8beabe4855a0befd": {  # 인공지능·대체투자 — 자산운용업계 트렌드 (삼성자산운용 맥락)
        "entities": [
            (T, "인공지능(ai)", "인공지능(AI)"),
            (P, "대체투자펀드", "대체투자펀드"),
        ],
        "edges": [
            E("USES_TECH", ("org", "삼성자산운용"), ("ent", T, "인공지능(ai)", "인공지능(AI)"), 0.78),
            E("PRODUCES", ("org", "삼성자산운용"), ("ent", P, "대체투자펀드", "대체투자펀드"), 0.83),
        ],
    },

    "8f3cc8e592509eb1": {  # 삼성자산운용 AUM 1,728조 (분기 2025.03) 국내1위
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
        ],
    },

    "8a96c5cfc9ae0d6a": {  # 삼성카드 영업수익 (2024.12 사업보고서)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성카드"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
        ],
    },

    "894343af92bdc230": {  # 삼성카드 리스/렌탈 서비스 (2025.12 사업보고서)
        "entities": [
            (P, "리스/렌탈서비스", "리스/렌탈서비스"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성카드"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("PRODUCES", ("org", "삼성카드"), ("ent", P, "리스/렌탈서비스", "리스/렌탈서비스"), 0.90),
        ],
    },

    "898cf5c8face900d": {  # 삼성카드 리스/렌탈 + 보험대리판매 (분기 2026.03)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성카드"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("PRODUCES", ("org", "삼성카드"), ("ent", P, "리스/렌탈서비스", "리스/렌탈서비스"), 0.88),
        ],
    },

    "89064c9bcd993d10": {  # 삼성카드 통화스왑 (분기 2025.03)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성카드"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
        ],
    },

    "8ef726789d05a959": {  # 삼성카드 신용카드 국내시장 플랫폼 경쟁 언급 (분기 2026.03)
        "entities": [
            (T, "결제플랫폼기술", "결제플랫폼기술"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성카드"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("USES_TECH", ("org", "삼성카드"), ("ent", T, "결제플랫폼기술", "결제플랫폼기술"), 0.78),
        ],
    },

    "90af656ef09c1156": {  # 삼성카드 신용카드 국내시장 플랫폼 경쟁 (2025.09 분기)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성카드"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
        ],
    },

    "8dd305dd0c1fe59d": {  # 삼성카드 마케팅·상품경쟁력 (2023.12)
        "entities": [
            (T, "데이터기반마케팅", "데이터기반마케팅"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성카드"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("USES_TECH", ("org", "삼성카드"), ("ent", T, "데이터기반마케팅", "데이터기반마케팅"), 0.80),
        ],
    },

    "95ab82f21a7ddb7a": {  # 삼성카드 빅데이터·디지털채널 경쟁력 (2025.12)
        "entities": [
            (T, "빅데이터분석", "빅데이터분석"),
            (T, "디지털채널", "디지털채널"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성카드"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("USES_TECH", ("org", "삼성카드"), ("ent", T, "빅데이터분석", "빅데이터분석"), 0.85),
            E("USES_TECH", ("org", "삼성카드"), ("ent", T, "디지털채널", "디지털채널"), 0.88),
        ],
    },

    "944b110a6456b35b": {  # 삼성카드 결제플랫폼 경쟁 언급 (반기 2025.06)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성카드"), ("org", SAMSUNG_LIFE), 0.92, "종속회사"),
        ],
    },

    # ── Samsung Life Insurance Thailand 태국법인 ───────────────
    "8f0ddc6ba8466ef8": {  # 태국법인 생명보험 + 태국시장 (분기 2024.03)
        "entities": [
            (P, "생명보험상품", "생명보험상품"),
            (P, "보장성보험", "보장성보험"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", "Samsung Life Insurance Thailand"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("PRODUCES", ("org", "Samsung Life Insurance Thailand"), ("ent", P, "생명보험상품", "생명보험상품"), 0.92),
            E("PRODUCES", ("org", "Samsung Life Insurance Thailand"), ("ent", P, "보장성보험", "보장성보험"), 0.88),
        ],
    },

    "8ccd0e91279f7acc": {  # 태국법인 IFRS17 + 보장성보험 중심 (분기 2025.03)
        "entities": [
            (T, "ifrs17", "IFRS17(보험계약국제회계기준)"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", "Samsung Life Insurance Thailand"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("PRODUCES", ("org", "Samsung Life Insurance Thailand"), ("ent", P, "보장성보험", "보장성보험"), 0.88),
            E("USES_TECH", ("org", SAMSUNG_LIFE), ("ent", T, "ifrs17", "IFRS17(보험계약국제회계기준)"), 0.85),
        ],
    },

    "9182082822752a8a": {  # 태국법인 채널역량 설계사 육성 (분기 2024.03)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "Samsung Life Insurance Thailand"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
        ],
    },

    "9014ea789ae12e47": {  # 태국법인 2025.06 지급여력비율 599%
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "Samsung Life Insurance Thailand"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("PRODUCES", ("org", "Samsung Life Insurance Thailand"), ("ent", P, "생명보험상품", "생명보험상품"), 0.90),
        ],
    },

    # ── 삼성에스알에이자산운용 — 부동산 전문 ─────────────────────
    "8f05e541881d70e2": {  # 삼성에스알에이자산운용 + 삼성생명서비스손해사정 설비 (2025.12)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성에스알에이자산운용"), ("org", SAMSUNG_LIFE), 0.92, "종속회사"),
            E("RELATED_PARTY", ("org", "삼성생명서비스손해사정"), ("org", SAMSUNG_LIFE), 0.92, "종속회사"),
        ],
    },

    "9090b76301e4dae7": {  # 삼성에스알에이자산운용 글로벌 부동산 운용사 도약 + 삼성생명금융서비스 (분기 2026.03)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성에스알에이자산운용"), ("org", SAMSUNG_LIFE), 0.92, "종속회사"),
            E("RELATED_PARTY", ("org", "삼성생명금융서비스"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
        ],
    },

    # ── 삼성생명금융서비스 GA — 보험대리점 ───────────────────────
    "89e9453b2b364811": {  # 삼성생명금융서비스 단독GA 유치 신사업 (반기 2024.06)
        "entities": [
            (P, "보험대리점서비스", "보험대리점서비스(GA)"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성생명금융서비스"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("PRODUCES", ("org", "삼성생명금융서비스"), ("ent", P, "보험대리점서비스", "보험대리점서비스(GA)"), 0.92),
        ],
    },

    "8dca7c032d94b116": {  # 삼성생명금융서비스 타생손보 제휴 (2025.12)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성생명금융서비스"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("PRODUCES", ("org", "삼성생명금융서비스"), ("ent", P, "보험대리점서비스", "보험대리점서비스(GA)"), 0.90),
        ],
    },

    "8ede256729bf9161": {  # 삼성생명 디지털채널·AI 신기술 (분기 2025.09)
        "entities": [
            (T, "인공지능(ai)", "인공지능(AI)"),
            (T, "디지털채널", "디지털채널"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG_LIFE), ("ent", T, "인공지능(ai)", "인공지능(AI)"), 0.87),
            E("USES_TECH", ("org", SAMSUNG_LIFE), ("ent", T, "디지털채널", "디지털채널"), 0.90),
        ],
    },

    "91207edeab35da83": {  # 삼성생명 삼성금융네트웍스 + AI 디지털화 (분기 2025.09)
        "entities": [
            (T, "인공지능(ai)", "인공지능(AI)"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG_LIFE), ("ent", T, "인공지능(ai)", "인공지능(AI)"), 0.88),
            E("RELATED_PARTY", ("org", "삼성화재"), ("org", SAMSUNG_LIFE), 0.82, "삼성금융네트웍스계열"),
            E("RELATED_PARTY", ("org", "삼성카드"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
        ],
    },

    "9131ee570f685ad2": {  # 삼성생명 자산운용·AI디지털 중점전략 (2024.12)
        "entities": [
            (T, "인공지능(ai)", "인공지능(AI)"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG_LIFE), ("ent", T, "인공지능(ai)", "인공지능(AI)"), 0.85),
            E("RELATED_PARTY", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
        ],
    },

    "88bd06f24005cd15": {  # IFRS17 경영효율 + 삼성생명 전략 (2023.12)
        "entities": [
            (T, "ifrs17", "IFRS17(보험계약국제회계기준)"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG_LIFE), ("ent", T, "ifrs17", "IFRS17(보험계약국제회계기준)"), 0.85),
        ],
    },

    # ── 삼성생명 주요 보험상품 언급 ──────────────────────────────
    "8990335b3e4e3d8e": {  # 삼성생명 유가증권 운용 + 파생상품 (2023.12)
        "entities": [
            (P, "보장성보험", "보장성보험"),
        ],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG_LIFE), ("ent", P, "생명보험상품", "생명보험상품"), 0.92),
        ],
    },

    "8b9e04af9f387e0d": {  # 삼성생명서비스손해사정 (2024.12)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성생명서비스손해사정"), ("org", SAMSUNG_LIFE), 0.92, "종속회사"),
        ],
    },

    "8b3715e3a73929ce": {  # 북경삼성치업유한공사 (2025.12)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "북경삼성치업유한공사"), ("org", SAMSUNG_LIFE), 0.90, "종속회사"),
        ],
    },

    "8d2d2e37610ee6f8": {  # 삼성에스알에이자산운용 북경 오피스 부동산 운용 (분기 2024.09)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성에스알에이자산운용"), ("org", SAMSUNG_LIFE), 0.92, "종속회사"),
        ],
    },

    "8e68e481f99d3dc2": {  # 북경 오피스 CBD 부동산 (반기 2024.06)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "북경삼성치업유한공사"), ("org", SAMSUNG_LIFE), 0.90, "종속회사"),
        ],
    },

    "8f193a9b46dcd83c": {  # 북경 오피스 CBD (분기 2025.03)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "북경삼성치업유한공사"), ("org", SAMSUNG_LIFE), 0.90, "종속회사"),
        ],
    },

    "8f461b09b7883326": {  # 삼성에스알에이자산운용 리스크관리 글로벌 네트워크 (분기 2024.09)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성에스알에이자산운용"), ("org", SAMSUNG_LIFE), 0.92, "종속회사"),
        ],
    },

    "8c631d1edbbc7db0": {  # 삼성자산운용 자기자본 + 삼성액티브자산운용 (2023.12)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("RELATED_PARTY", ("org", "삼성액티브자산운용"), ("org", SAMSUNG_LIFE), 0.90, "종속회사"),
        ],
    },

    "88847b7b7b1c3041": {  # 삼성생명 보험료적립금·운용내역 (2025.03)
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG_LIFE), ("ent", P, "생명보험상품", "생명보험상품"), 0.88),
        ],
    },

    "8fbc37abd18fb53c": {  # 삼성생명 자산운용 이익현황 (2024.12)
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG_LIFE), ("ent", P, "생명보험상품", "생명보험상품"), 0.88),
        ],
    },

    "8f583639e2c1bd26": {  # 삼성생명 자금운용실적 (2023.12)
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG_LIFE), ("ent", P, "생명보험상품", "생명보험상품"), 0.88),
        ],
    },

    "8bf7e8219e3c58c2": {  # 태국법인 모집형태 + 북경삼성치업 (분기 2024.03)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "Samsung Life Insurance Thailand"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("RELATED_PARTY", ("org", "북경삼성치업유한공사"), ("org", SAMSUNG_LIFE), 0.90, "종속회사"),
        ],
    },

    "a0ada1e1122ecfaa": {  # 삼성카드 신용카드사업 + 신용파생상품 (2023.12 기재정정)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성카드"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
        ],
    },

    "8d1a1717b15523b7": {  # 삼성카드 할부금융·자동차리스 (반기 2024.06)
        "entities": [
            (P, "할부금융", "할부금융"),
            (P, "자동차리스", "자동차리스"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성카드"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("PRODUCES", ("org", "삼성카드"), ("ent", P, "할부금융", "할부금융"), 0.90),
            E("PRODUCES", ("org", "삼성카드"), ("ent", P, "자동차리스", "자동차리스"), 0.88),
        ],
    },

    "8d701a19083e69d8": {  # 삼성카드 할부금융·리스 산업 특성 (2024.12)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성카드"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("PRODUCES", ("org", "삼성카드"), ("ent", P, "할부금융", "할부금융"), 0.90),
        ],
    },

    "8a2a6ec72d9ce564": {  # 삼성자산운용 투자일임 영업실적 (2023.12)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("PRODUCES", ("org", "삼성자산운용"), ("ent", P, "투자일임계약", "투자일임계약"), 0.88),
        ],
    },

    "8ed74765aa6decdc": {  # 삼성자산운용 2023.12 설립내력 — 중복, skip
        "entities": [],
        "edges": [],
    },

    "91b1de615f01c073": {  # 삼성자산운용 ETF수수료 증가 (사업보고서 2024.12)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("PRODUCES", ("org", "삼성자산운용"), ("ent", P, "etf", "ETF(상장지수펀드)"), 0.92),
        ],
    },

    "90fd5f25bd05ff67": {  # 태국법인 IFRS17 경험조정 감소 (사업보고서 2025.12)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "Samsung Life Insurance Thailand"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
        ],
    },

    "95a55cf5c965307e": {  # 대주주거래: 삼성자산운용 채권 운용 + 삼성증권 매매 (분기 2024.03)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("RELATED_PARTY", ("org", "삼성증권"), ("org", SAMSUNG_LIFE), 0.80, "삼성금융네트웍스계열"),
        ],
    },

    "a5fd52f76a46e4c3": {  # 대주주거래: 삼성자산운용 + 삼성증권 (반기 2024.06)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성자산운용"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("RELATED_PARTY", ("org", "삼성증권"), ("org", SAMSUNG_LIFE), 0.80, "삼성금융네트웍스계열"),
        ],
    },

    # ── IV. 경영진단 — 삼성생명 본사 실적 언급 ──────────────────
    "8baf9f0e0f1419b7": {  # 삼성생명 별도 당기순이익 + 삼성카드 영업수익 (2023.12)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성카드"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
        ],
    },

    "8c0b0447d59d92b3": {  # 삼성생명금융서비스 경영지표 (사업보고서 2025.12)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성생명금융서비스"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
        ],
    },

    "8d946e282f3c31cf": {  # 삼성생명금융서비스 영업수익 (사업보고서 2024.12)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성생명금융서비스"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
        ],
    },

    "8dbbf941b8d9143f": {  # 삼성물산 + 북경삼성치업 (2024.12 경영진단)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성물산"), ("org", SAMSUNG_LIFE), 0.82, "삼성그룹계열"),
            E("RELATED_PARTY", ("org", "북경삼성치업유한공사"), ("org", SAMSUNG_LIFE), 0.90, "종속회사"),
        ],
    },

    "8e3f8939cd31a5d7": {  # 태국법인 총자산 언급 (2023.12)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "Samsung Life Insurance Thailand"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
        ],
    },

    "906a9610b4247975": {  # 삼성카드 상품자산·대출채권 (2023.12 경영진단)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성카드"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
        ],
    },

    "907d7933ba18d6fb": {  # 삼성생명 유가증권·대출채권 운용 (2023.12)
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", SAMSUNG_LIFE), ("ent", P, "생명보험상품", "생명보험상품"), 0.85),
        ],
    },

    "90d731cec8c3720a": {  # 삼성생명 ESG경영 (2023.12)
        "entities": [],
        "edges": [],
    },

    "b749db03b317dbb0": {  # 삼성생명 ORSA 내부모형 위험관리 (2025.12)
        "entities": [
            (T, "내부모형(orsa)", "내부모형(ORSA)"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG_LIFE), ("ent", T, "내부모형(orsa)", "내부모형(ORSA)"), 0.87),
        ],
    },

    "cfd8ae0ed34a166c": {  # 삼성생명 위험관리 ALM·상품개발 (2025.12)
        "entities": [],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG_LIFE), ("ent", T, "내부모형(orsa)", "내부모형(ORSA)"), 0.82),
        ],
    },

    "e7d0b962e3de14a2": {  # 삼성카드 팩토링·리스 (2024.12)
        "entities": [
            (P, "팩토링", "팩토링(매출채권매입)"),
        ],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성카드"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
            E("PRODUCES", ("org", "삼성카드"), ("ent", P, "팩토링", "팩토링(매출채권매입)"), 0.87),
            E("PRODUCES", ("org", "삼성카드"), ("ent", P, "자동차리스", "자동차리스"), 0.88),
        ],
    },

    "95ac7c13c5f4191b": {  # 삼성생명 AI·신사업·M&A 투자 (2023.12)
        "entities": [
            (T, "인공지능(ai)", "인공지능(AI)"),
        ],
        "edges": [
            E("USES_TECH", ("org", SAMSUNG_LIFE), ("ent", T, "인공지능(ai)", "인공지능(AI)"), 0.83),
        ],
    },

    "9022dcef7f123b6d": {  # 삼성카드 보험대리판매·온라인쇼핑몰 (2023.12)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성카드"), ("org", SAMSUNG_LIFE), 0.93, "종속회사"),
        ],
    },
}


# ── 적재 실행 ────────────────────────────────────────────────────────────────
def resolve_to_match(spec, entity_cache: dict, driver):
    """추출 스펙 → add_edge용 match dict."""
    kind = spec[0]
    if kind == "org":
        org_name = spec[1]
        org = resolve_org(org_name)
        if org is None:
            # needs_er fallback
            import re
            er = re.sub(r"\s+", "", org_name.strip().lower())
            org = {"mode": "er", "er_name": er, "id": er, "name": org_name}
        merge_org_node(driver, org)
        return {"kind": "org", "org": org}
    elif kind == "ent":
        label, canonical, display = spec[1], spec[2], spec[3]
        if (label, canonical) not in entity_cache:
            eid = merge_entity(driver, label, canonical, display)
            entity_cache[(label, canonical)] = eid
        eid = entity_cache[(label, canonical)]
        return {"kind": "entity", "label": label, "id": eid}
    raise ValueError(f"Unknown spec kind: {kind}")


def main():
    print("삼성생명 text_micro 후반부 비정형 추출 적재 시작...")
    rows = get_chunks(
        "WHERE corp_code='00126256' AND chunk_type='text_micro' "
        "ORDER BY chunk_id LIMIT 2200 OFFSET 2200"
    )
    print(f"총 {len(rows)}개 청크 로드 완료")

    done_ids = ledger_processed_ids()
    print(f"기처리 {len(done_ids)}개 (원장 기준)")

    driver = neo4j_driver()
    conn = mariadb_conn()

    entity_cache: dict = {}
    stats = {"processed": 0, "skipped": 0, "ent_new": 0, "edge_new": 0}

    for row in rows:
        cid = row["chunk_id"]
        rcept = row["rcept_no"]
        spath = row["section_path"] or ""

        if cid in done_ids:
            stats["skipped"] += 1
            continue

        spec = EXTRACTIONS.get(cid)
        if spec is None:
            # 추출 대상 아님(재무주석/감사보고서 등) — mark only
            mark_processed(cid, 0, 0, rcept, spath)
            stats["processed"] += 1
            continue

        n_ent = 0
        n_edge = 0

        # 1. 엔티티 MERGE
        for ent_spec in spec.get("entities", []):
            label, canonical, display = ent_spec
            if (label, canonical) not in entity_cache:
                eid = merge_entity(driver, label, canonical, display)
                entity_cache[(label, canonical)] = eid
                n_ent += 1
                stats["ent_new"] += 1

        # 2. 엣지 MERGE + provenance
        for edge in spec.get("edges", []):
            rel = edge["rel"]
            frm = resolve_to_match(edge["from"], entity_cache, driver)
            to = resolve_to_match(edge["to"], entity_cache, driver)
            conf = edge["conf"]
            rt = edge.get("relation_type")

            add_edge(driver, rel, frm, to, cid, rcept, conf, rt)

            # provenance subject/object id
            if frm["kind"] == "org":
                subj_id = frm["org"]["id"]
            else:
                subj_id = frm["id"]
            if to["kind"] == "org":
                obj_id = to["org"]["id"]
            else:
                obj_id = to["id"]

            write_provenance(conn, subj_id, rel, obj_id, cid, rcept, conf)
            conn.commit()
            n_edge += 1
            stats["edge_new"] += 1

        mark_processed(cid, n_ent, n_edge, rcept, spath)
        stats["processed"] += 1

        if stats["processed"] % 200 == 0:
            print(f"  [{stats['processed']}/{len(rows)}] 처리중... 엔티티={stats['ent_new']} 엣지={stats['edge_new']}")

    conn.close()
    driver.close()

    print("\n=== 완료 ===")
    print(f"처리: {stats['processed']}개  스킵(기처리): {stats['skipped']}개")
    print(f"신규 엔티티: {stats['ent_new']}개  신규 엣지+provenance: {stats['edge_new']}개")


if __name__ == "__main__":
    main()
