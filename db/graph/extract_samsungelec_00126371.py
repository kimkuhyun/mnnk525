"""Stage 5 비정형 추출 — 삼성전기 corp_code=00126371, text_micro 전체(~1,131) + table_nl 특수관계.

삼성전기 = 컴포넌트(MLCC·인덕터·칩저항) + 광학솔루션(카메라모듈) + 패키지솔루션(반도체패키지기판).
제품(Product) = MLCC, 파워인덕터, 탄탈캐패시터, 칩저항, 카메라모듈, 반도체패키지기판(FCBGA), 통신모듈.
기술(Technology) = OIS(광학식손떨림보정), 폴디드줌, ADAS 카메라, 5G mmWave, FCBGA, 적층세라믹기술.
특수관계자 = 삼성전자(최대주주·최대매출처·원재료 매입처), 삼성글로벌리서치(관계기업),
              스템코(관계기업), 삼성물산·삼성에스디에스·삼성웰스토리(기타특수관계자).

원장 = db/graph/ledger/extra28_00126371.jsonl (이 추출 전용).
실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_samsungelec_00126371.py
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

CORP = "삼성전기"
CORP_CODE = "00126371"

# 전용 원장
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_DIR.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = LEDGER_DIR / "extra28_00126371.jsonl"


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
# 삼성전기 핵심:
#   3사업부문: 컴포넌트(MLCC/인덕터/칩저항) · 광학솔루션(카메라모듈) · 패키지솔루션(반도체패키지기판)
#   주요 매출처: 삼성전자·종속회사(매출 27~31%)
#   원재료 매입: 삼성전자(센서 IC), SONY(센서 IC), MITSUBISHI/RESONAC(CCL/PPG), SHOEI/GUANGBO(PASTE/POWDER), LG화학(CCL/PPG)
#   특수관계: 삼성전자(유의적영향력=최대주주), 삼성글로벌리서치·스템코(관계기업), 삼성물산·에스디에스·웰스토리(기타)
EXTRACTIONS: dict[str, dict] = {

    # ── II. 사업의 내용: 사업부문 개요 (사업보고서 2023.12) ──────────
    "057cfd448c9b2c4c": {  # 컴포넌트(MLCC·인덕터·칩저항)·광학통신솔루션(카메라모듈·통신모듈)·패키지솔루션(반도체패키지기판) 3사업부문
        "entities": [
            (P, "mlcc", "MLCC (적층세라믹콘덴서)"),
            (P, "카메라모듈", "카메라모듈"),
            (P, "반도체패키지기판", "반도체패키지기판"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "mlcc", "MLCC (적층세라믹콘덴서)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "카메라모듈", "카메라모듈"), 0.96),
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체패키지기판", "반도체패키지기판"), 0.96),
        ],
    },

    # ── II. 사업의 내용: 주요제품 현황 + 센서IC 매입처 (사업보고서 2023.12) ──
    "00e4d6ba80488e8d": {  # MLCC·카메라모듈·반도체패키지기판, 센서IC=삼성전자(*최대주주)
        "entities": [
            (P, "mlcc", "MLCC (적층세라믹콘덴서)"),
            (P, "카메라모듈", "카메라모듈"),
            (P, "반도체패키지기판", "반도체패키지기판"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "mlcc", "MLCC (적층세라믹콘덴서)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "카메라모듈", "카메라모듈"), 0.96),
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체패키지기판", "반도체패키지기판"), 0.96),
            E("SUPPLIES_TO", ("org", "삼성전자"), ("org", CORP), 0.90),
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주, 센서IC 공급)"),
        ],
    },

    # ── II. 사업의 내용: 센서IC 매입 (기재정정 사업보고서 2023.12) ──
    "1a708cf56b28bd03": {  # MITSUBISHI/LG화학으로부터 CCL/PPG 매입하여 기판 제조
        "entities": [
            (P, "반도체패키지기판", "반도체패키지기판"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체패키지기판", "반도체패키지기판"), 0.96),
            E("SUPPLIES_TO", ("org", "LG화학"), ("org", CORP), 0.87),
        ],
    },

    # ── II. 사업의 내용: 원재료 매입처 (사업보고서 2023.12) ──────────
    "33d7077ca46953a5": {  # 센서IC=삼성전자·SONY, CCL/PPG=MITSUBISHI·LG화학
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성전자"), ("org", CORP), 0.92),
            E("SUPPLIES_TO", ("org", "SONY"), ("org", CORP), 0.88),
            E("SUPPLIES_TO", ("org", "LG화학"), ("org", CORP), 0.87),
        ],
    },

    # ── II. 사업의 내용: 광학통신솔루션 — OIS·Folded Zoom 카메라 (사업보고서 2023.12) ──
    "194d033f07d3f1f7": {  # 카메라모듈 OIS, Folded/멀티카메라; 통신모듈 RF/Cellular FEM
        "entities": [
            (P, "카메라모듈", "카메라모듈"),
            (T, "ois", "OIS (광학식 손떨림 보정)"),
            (T, "folded zoom", "폴디드줌 (Folded Zoom)"),
            (P, "통신모듈", "통신모듈 (RF/FEM)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "카메라모듈", "카메라모듈"), 0.96),
            E("USES_TECH", ("org", CORP), ("ent", T, "ois", "OIS (광학식 손떨림 보정)"), 0.92),
            E("USES_TECH", ("org", CORP), ("ent", T, "folded zoom", "폴디드줌 (Folded Zoom)"), 0.90),
            E("PRODUCES", ("org", CORP), ("ent", P, "통신모듈", "통신모듈 (RF/FEM)"), 0.90),
        ],
    },

    # ── II. 사업의 내용: 패키지솔루션 FCBGA (기재정정 사업보고서 2023.12) ──
    "0945136ba60346b8": {  # 반도체패키지기판 FCBGA; 서버·모바일 AP·5G mmWave 안테나용
        "entities": [
            (P, "반도체패키지기판", "반도체패키지기판"),
            (T, "fcbga", "FCBGA (Flip Chip BGA 기판)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체패키지기판", "반도체패키지기판"), 0.96),
            E("USES_TECH", ("org", CORP), ("ent", T, "fcbga", "FCBGA (Flip Chip BGA 기판)"), 0.93),
        ],
    },

    # ── II. 사업의 내용: 컴포넌트 — MLCC 수동소자 전체 (사업보고서 2024.12) ──
    "36d1e171579401f0": {  # MLCC·파워인덕터·탄탈캐패시터·칩저항 등 수동소자
        "entities": [
            (P, "mlcc", "MLCC (적층세라믹콘덴서)"),
            (P, "파워인덕터", "파워인덕터 (Power Inductor)"),
            (P, "탄탈캐패시터", "탄탈캐패시터 (Tantalum Capacitor)"),
            (P, "칩저항", "칩저항 (Chip Resistor)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "mlcc", "MLCC (적층세라믹콘덴서)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "파워인덕터", "파워인덕터 (Power Inductor)"), 0.96),
            E("PRODUCES", ("org", CORP), ("ent", P, "탄탈캐패시터", "탄탈캐패시터 (Tantalum Capacitor)"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "칩저항", "칩저항 (Chip Resistor)"), 0.95),
        ],
    },

    # ── II. 사업의 내용: 컴포넌트 — MLCC 수동소자 (사업보고서 2025.12) ──
    "36886f3c7866cdf3": {  # MLCC·파워인덕터·탄탈캐패시터·칩저항 수동소자
        "entities": [
            (P, "mlcc", "MLCC (적층세라믹콘덴서)"),
            (P, "파워인덕터", "파워인덕터 (Power Inductor)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "mlcc", "MLCC (적층세라믹콘덴서)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "파워인덕터", "파워인덕터 (Power Inductor)"), 0.96),
        ],
    },

    # ── II. 사업의 내용: 고신뢰성 MLCC 전장·AI서버 (분기보고서 2024.09) ──
    "06a70011ab6f1ef0": {  # 고온/초고용량 MLCC, AI서버/위성인터넷 신시장 개발, 고신뢰성 MLCC
        "entities": [
            (P, "mlcc", "MLCC (적층세라믹콘덴서)"),
            (T, "적층세라믹기술", "적층 세라믹 재료/공정기술"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "mlcc", "MLCC (적층세라믹콘덴서)"), 0.97),
            E("USES_TECH", ("org", CORP), ("ent", T, "적층세라믹기술", "적층 세라믹 재료/공정기술"), 0.92),
        ],
    },

    # ── II. 사업의 내용: MLCC 경쟁우위 (분기보고서 2026.03) ─────────
    "1ebe3f1cac695658": {  # 초소형/고용량 MLCC, AI서버 확산, 전력소모 증가로 MLCC 수요 확대
        "entities": [
            (P, "mlcc", "MLCC (적층세라믹콘덴서)"),
            (P, "파워인덕터", "파워인덕터 (Power Inductor)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "mlcc", "MLCC (적층세라믹콘덴서)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "파워인덕터", "파워인덕터 (Power Inductor)"), 0.93),
        ],
    },

    # ── II. 사업의 내용: 광학솔루션 — OIS·ADAS카메라 (반기보고서 2025.06) ──
    "0a9699b3b63a3a32": {  # 카메라모듈 OIS, Folded Zoom; 전장용 ADAS 카메라(5M 고화소)
        "entities": [
            (P, "카메라모듈", "카메라모듈"),
            (T, "ois", "OIS (광학식 손떨림 보정)"),
            (T, "adas 카메라", "ADAS 카메라 (전장용 고화소 카메라)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "카메라모듈", "카메라모듈"), 0.96),
            E("USES_TECH", ("org", CORP), ("ent", T, "ois", "OIS (광학식 손떨림 보정)"), 0.93),
            E("USES_TECH", ("org", CORP), ("ent", T, "adas 카메라", "ADAS 카메라 (전장용 고화소 카메라)"), 0.92),
        ],
    },

    # ── II. 사업의 내용: 광학솔루션 카메라 전략 (분기보고서 2024.09) ──
    "1961903254075302": {  # 고화소 Wide/Tele 카메라, OIS, Folded Zoom; ADAS 고화소 전장카메라
        "entities": [
            (P, "카메라모듈", "카메라모듈"),
            (T, "folded zoom", "폴디드줌 (Folded Zoom)"),
            (T, "adas 카메라", "ADAS 카메라 (전장용 고화소 카메라)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "카메라모듈", "카메라모듈"), 0.96),
            E("USES_TECH", ("org", CORP), ("ent", T, "folded zoom", "폴디드줌 (Folded Zoom)"), 0.92),
            E("USES_TECH", ("org", CORP), ("ent", T, "adas 카메라", "ADAS 카메라 (전장용 고화소 카메라)"), 0.92),
        ],
    },

    # ── II. 사업의 내용: 광학솔루션 카메라전략 (반기보고서 2024.06) ──
    "149465bb46ecc095": {  # 고화소 빅센서, 조리개, Folded Zoom; ADAS 5M 카메라; xEV 전통OEM 대응
        "entities": [
            (P, "카메라모듈", "카메라모듈"),
            (T, "folded zoom", "폴디드줌 (Folded Zoom)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "카메라모듈", "카메라모듈"), 0.96),
            E("USES_TECH", ("org", CORP), ("ent", T, "folded zoom", "폴디드줌 (Folded Zoom)"), 0.92),
        ],
    },

    # ── II. 사업의 내용: 패키지솔루션 FCBGA 전략 (분기보고서 2024.03) ──
    "1ce78b378d0b5600": {  # FCBGA 기판 AP/CPU/서버용; 5G mmWave 안테나용; AI 가속기 신규응용처
        "entities": [
            (P, "반도체패키지기판", "반도체패키지기판"),
            (T, "fcbga", "FCBGA (Flip Chip BGA 기판)"),
            (T, "5g mmwave 안테나기판", "5G mmWave 안테나용 기판"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체패키지기판", "반도체패키지기판"), 0.96),
            E("USES_TECH", ("org", CORP), ("ent", T, "fcbga", "FCBGA (Flip Chip BGA 기판)"), 0.93),
            E("USES_TECH", ("org", CORP), ("ent", T, "5g mmwave 안테나기판", "5G mmWave 안테나용 기판"), 0.90),
        ],
    },

    # ── II. 사업의 내용: 패키지솔루션 FCBGA 전략 (사업보고서 2025.12) ──
    "20898b96df807293": {  # AP/CPU/서버 고다층 대면적; AI 가속기 신규응용처
        "entities": [
            (P, "반도체패키지기판", "반도체패키지기판"),
            (T, "fcbga", "FCBGA (Flip Chip BGA 기판)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체패키지기판", "반도체패키지기판"), 0.96),
            E("USES_TECH", ("org", CORP), ("ent", T, "fcbga", "FCBGA (Flip Chip BGA 기판)"), 0.93),
        ],
    },

    # ── II. 사업의 내용: 패키지솔루션 개요 (분기보고서 2025.09) ─────
    "333263040123b8c1": {  # FCBGA 반도체패키지기판, CPU/GPU/AP/NPU용
        "entities": [
            (P, "반도체패키지기판", "반도체패키지기판"),
            (T, "fcbga", "FCBGA (Flip Chip BGA 기판)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체패키지기판", "반도체패키지기판"), 0.96),
            E("USES_TECH", ("org", CORP), ("ent", T, "fcbga", "FCBGA (Flip Chip BGA 기판)"), 0.93),
        ],
    },

    # ── II. 사업의 내용: 패키지솔루션 개요 (분기보고서 2025.03) ─────
    "18aa68cc7a50c668": {  # MLCC·인덕터·칩저항 수동소자 + FCBGA 기판 + 카메라모듈 3사업
        "entities": [
            (P, "mlcc", "MLCC (적층세라믹콘덴서)"),
            (P, "반도체패키지기판", "반도체패키지기판"),
            (P, "카메라모듈", "카메라모듈"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "mlcc", "MLCC (적층세라믹콘덴서)"), 0.97),
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체패키지기판", "반도체패키지기판"), 0.96),
            E("PRODUCES", ("org", CORP), ("ent", P, "카메라모듈", "카메라모듈"), 0.96),
        ],
    },

    # ── II. 사업의 내용: 3사업부문 개요 (분기보고서 2025.03) ─────────
    "2d3fe2c8eb4e6881": {  # MLCC·인덕터·칩저항 + 반도체패키지기판 + 카메라모듈; 매출처=삼성전자
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.93),
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주, 최대매출처)"),
        ],
    },

    # ── II. 사업의 내용: 주요매출처 삼성전자 (반기보고서 2024.06) ────
    "2795d3e92474157f": {  # 주요 매출처=삼성전자·종속회사(매출 31.3%)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주, 최대매출처 31.3%)"),
        ],
    },

    # ── II. 사업의 내용: 주요매출처 삼성전자 (사업보고서 2025.12) ────
    "0bc550ed241bd973": {  # 주요 매출처=삼성전자·종속회사(매출 27%)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주, 최대매출처 27%)"),
        ],
    },

    # ── II. 사업의 내용: 주요매출처 삼성전자 (분기보고서 2025.09) ────
    "20e0820f934c993f": {  # 주요 매출처=삼성전자·종속회사(매출 28.5%)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.95),
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.94, "유의적인 영향력을 미치는 회사(최대주주, 최대매출처 28.5%)"),
        ],
    },

    # ── II. 사업의 내용: 센서IC 매입처 (사업보고서 2024.12) ──────────
    "1aaf6c9df2e6e52c": {  # 센서IC=삼성전자·SONY 매입; CCL/PPG=MITSUBISHI·LG화학 매입
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성전자"), ("org", CORP), 0.93),
            E("SUPPLIES_TO", ("org", "SONY"), ("org", CORP), 0.90),
            E("SUPPLIES_TO", ("org", "LG화학"), ("org", CORP), 0.88),
        ],
    },

    # ── II. 사업의 내용: 원재료 매입처 (반기보고서 2025.06) ──────────
    "2ee3e1498cdf8c7d": {  # 센서IC=삼성전자·SONY, CCL/PPG=MITSUBISHI·RESONAC
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성전자"), ("org", CORP), 0.93),
            E("SUPPLIES_TO", ("org", "SONY"), ("org", CORP), 0.90),
        ],
    },

    # ── II. 사업의 내용: 원재료 매입처 (분기보고서 2026.03) ──────────
    "39fc5ffa3c0db01e": {  # 센서IC=삼성전자·SONY, CCL/PPG=MITSUBISHI·RESONAC
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성전자"), ("org", CORP), 0.93),
            E("SUPPLIES_TO", ("org", "SONY"), ("org", CORP), 0.90),
        ],
    },

    # ── II. 사업의 내용: 원재료 매입처 (분기보고서 2025.03) ──────────
    "1954196c71854b3c": {  # 센서IC=삼성전자·SONY 매입, CCL/PPG 상승
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성전자"), ("org", CORP), 0.92),
            E("SUPPLIES_TO", ("org", "SONY"), ("org", CORP), 0.89),
        ],
    },

    # ── II. 사업의 내용: 전장카메라 OIS·Folded Zoom 고부가 (분기보고서 2024.03) ──
    "0c8f945b8e80d1cb": {  # 전장카메라 ADAS 5M 고화소, 통신모듈 내재화·소형화
        "entities": [
            (T, "adas 카메라", "ADAS 카메라 (전장용 고화소 카메라)"),
            (P, "통신모듈", "통신모듈 (RF/FEM)"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "adas 카메라", "ADAS 카메라 (전장용 고화소 카메라)"), 0.92),
            E("PRODUCES", ("org", CORP), ("ent", P, "통신모듈", "통신모듈 (RF/FEM)"), 0.90),
        ],
    },

    # ── II. 사업의 내용: 카메라모듈 전장·로봇 (분기보고서 2026.03) ──
    "385d401c8d7d18ae": {  # 전장/로봇용 카메라모듈, 초접사 폴디드줌 Flagship 스마트폰 공급
        "entities": [
            (P, "카메라모듈", "카메라모듈"),
            (T, "folded zoom", "폴디드줌 (Folded Zoom)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "카메라모듈", "카메라모듈"), 0.96),
            E("USES_TECH", ("org", CORP), ("ent", T, "folded zoom", "폴디드줌 (Folded Zoom)"), 0.92),
        ],
    },

    # ── II. 사업의 내용: 패키지솔루션 — 기판 시장여건 (사업보고서 2025.12) ──
    "144f656dc1745571": {  # BGA·FCBGA 기판; 박형/고밀도/고다층화/선폭미세화
        "entities": [
            (P, "반도체패키지기판", "반도체패키지기판"),
            (T, "fcbga", "FCBGA (Flip Chip BGA 기판)"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체패키지기판", "반도체패키지기판"), 0.96),
            E("USES_TECH", ("org", CORP), ("ent", T, "fcbga", "FCBGA (Flip Chip BGA 기판)"), 0.93),
        ],
    },

    # ── II. 사업의 내용: 기판 산업 성장성 (분기보고서 2026.03) ──────
    "00a1b184c0626341": {  # AI/서버·네트웍·자율주행 고성능 컴퓨팅 성장, 고부가 패키지기판 수요 증가
        "entities": [
            (P, "반도체패키지기판", "반도체패키지기판"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체패키지기판", "반도체패키지기판"), 0.95),
        ],
    },

    # ── II. 사업의 내용: 연구개발 — 제품 특허 스마트폰·전장 (사업보고서 2024.12) ──
    "00ce36974ffefaa9": {  # 스마트폰·디스플레이·PC·TV·전장용 부품 특허; MLCC·카메라모듈·기판
        "entities": [],
        "edges": [],  # 연구개발 개황 — 제품 언급 반복이나 구체 엣지 없음
    },

    # ── II. 사업의 내용: 주요매출처·수주 (분기보고서 2024.09) ──────
    "1a9936deac7476e7": {  # 주요제품 현황·가격변동; 센서IC=삼성전자(*최대주주)
        "entities": [],
        "edges": [
            E("SUPPLIES_TO", ("org", "삼성전자"), ("org", CORP), 0.91),
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.94, "유의적인 영향력을 미치는 회사(최대주주, 원재료 공급)"),
        ],
    },

    # ── X. 대주주 거래: 삼성전자 대주주와의 거래 (분기보고서 2024.09) ──
    "2d71451b4991dcd5": {  # 대주주 삼성전자와의 자산양수도·영업거래; 거래금액 시장가치 산정
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주, 대주주거래)"),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.90),
        ],
    },

    # ── X. 대주주 거래: 삼성전자 대주주와의 거래 (반기보고서 2024.06) ──
    "3a3cfe4f55f8326b": {  # 대주주(삼성전자) 자산양수도 및 영업거래
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주, 대주주거래)"),
            E("SUPPLIES_TO", ("org", CORP), ("org", "삼성전자"), 0.90),
        ],
    },

    # ── 감사보고서: 삼성전자 배당금·종속기업 거래 (사업보고서 2025.12) ──
    "00b5f84323f4006b": {  # 삼성전자에 배당금 지급; 종속기업 거래내역; 삼성생명 퇴직급여
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주, 배당 수령)"),
            E("RELATED_PARTY", ("org", "삼성생명보험"), ("org", CORP), 0.85, "기타 특수관계자(확정급여형 퇴직급여제도)"),
        ],
    },

    # ── 연결감사보고서: 특수관계자 24-1 목록 (사업보고서 2023.12) ─
    "1414ff9fe8620950": {  # 특수관계자: 삼성전자(유의적영향력), 계열사들
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주)"),
        ],
    },

    # ── table_nl: 특수관계자 목록 (반기보고서 2024.06) ─────────────
    "16e164dbda550e09": {  # 삼성전자=유의적영향력; 종속기업 해외법인들
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주)"),
        ],
    },

    # ── table_nl: 특수관계자 목록 연결 (분기보고서 2026.03) ─────────
    "18dbf07af338910e": {  # 삼성전자=유의적영향력; 삼성글로벌리서치·스템코=관계기업; 삼성물산·에스디에스·웰스토리=기타
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성글로벌리서치"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "스템코"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.87, "기타 특수관계자(삼성그룹 계열)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에스디에스"), 0.87, "기타 특수관계자(삼성그룹 계열)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성웰스토리"), 0.87, "기타 특수관계자(삼성그룹 계열)"),
        ],
    },

    # ── table_nl: 재무제표주석 특수관계자 거래표 (사업보고서 2025.12) 연결 ──
    "3cf7e939f8a1b824": {  # 삼성전자=유의적영향력; 삼성글로벌리서치·스템코=관계기업; 기타특수관계자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성글로벌리서치"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "스템코"), 0.90, "관계기업"),
        ],
    },

    # ── table_nl: 재무제표주석 특수관계자 거래표 (분기보고서 2026.03) 연결 ──
    "02496d71d8a38667": {  # 삼성전자=유의적영향력; 삼성글로벌리서치·스템코=관계기업; 기타특수관계자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성글로벌리서치"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "스템코"), 0.90, "관계기업"),
        ],
    },

    # ── table_nl: 특수관계자 거래 연결 (분기보고서 2024.09) ─────────
    "3f820bc25a60dbb7": {  # 삼성전자=유의적영향력; 기타특수관계자들
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주)"),
        ],
    },

    # ── table_nl: 특수관계자 거래 연결 (분기보고서 2025.09) ─────────
    "24cfe91dcb545990": {  # 삼성전자=유의적영향력
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주)"),
        ],
    },

    # ── table_nl: 특수관계자 거래 연결 (사업보고서 2025.12) ─────────
    "0f85165e65434f3f": {  # 삼성전자=유의적영향력
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주)"),
        ],
    },

    # ── table_nl: 특수관계자 거래 연결 (반기보고서 2025.06) ─────────
    "1d55ddbd6cb69adc": {  # 삼성전자=유의적영향력
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주)"),
        ],
    },

    # ── table_nl: 특수관계자 거래 연결 (분기보고서 2025.03) ─────────
    "331d2eb78fc00bab": {  # 삼성전자=유의적영향력; 관계기업 포함
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성글로벌리서치"), 0.90, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "스템코"), 0.90, "관계기업"),
        ],
    },

    # ── table_nl: 특수관계자 거래 연결 (사업보고서 2023.12) ─────────
    "18b2ab8cbfda3b4c": {  # 삼성전자=유의적영향력
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주)"),
        ],
    },

    # ── table_nl: 특수관계자 거래 연결 (기재정정 사업보고서 2023.12) ──
    "039ded08981b8ab0": {  # 삼성전자=유의적영향력
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주)"),
        ],
    },

    # ── table_nl: 특수관계자 거래 연결 (기재정정 사업보고서 2023.12) ──
    "2a650d481a0e8c3b": {  # 삼성전자=유의적영향력
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주)"),
        ],
    },

    # ── table_nl: 재무제표주석 특수관계자 거래표 (분기보고서 2024.03) ──
    "36418446d66b4327": {  # 삼성전자=유의적영향력
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주)"),
        ],
    },

    # ── table_nl: 재무제표주석 특수관계자 거래표 (반기보고서 2025.06) 별도 ──
    "2df6ee33312101a5": {  # 삼성전자=유의적영향력
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주)"),
        ],
    },

    # ── table_nl: 재무제표주석 특수관계자 거래표 (반기보고서 2025.06) 연결 ──
    "3ef6b2e05a485f3f": {  # 삼성전자=유의적영향력
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주)"),
        ],
    },

    # ── table_nl: 재무제표주석 특수관계자 거래표 (분기보고서 2025.09) 별도 ──
    "2a35a217bba6405c": {  # 삼성전자=유의적영향력
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주)"),
        ],
    },

    # ── table_nl: 재무제표주석 특수관계자 거래표 (반기보고서 2024.06) 별도 ──
    "08cc16c4fdbb31f3": {  # 삼성전자=유의적영향력
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주)"),
        ],
    },

    # ── table_nl: 재무제표주석 특수관계자 거래표 (분기보고서 2026.03) 연결 ──
    "0fe6a9e4ad605ad6": {  # 삼성전자=유의적영향력
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주)"),
        ],
    },

    # ── table_nl: 재무제표주석 특수관계자 거래표 (분기보고서 2026.03) 별도 ──
    "3fdcf13f75356743": {  # 삼성전자=유의적영향력
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", "삼성전자"), ("org", CORP), 0.95, "유의적인 영향력을 미치는 회사(최대주주)"),
        ],
    },

    # ── II. 사업의 내용: 연구개발 — 수동소자·카메라모듈·기판 (반기보고서 2024.06) ──
    "3ae746a0937cbfd4": {  # 수동소자/카메라모듈/차세대패키지기판 집중 육성; 기술개발 개요
        "entities": [
            (P, "mlcc", "MLCC (적층세라믹콘덴서)"),
            (P, "카메라모듈", "카메라모듈"),
            (P, "반도체패키지기판", "반도체패키지기판"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "mlcc", "MLCC (적층세라믹콘덴서)"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "카메라모듈", "카메라모듈"), 0.93),
            E("PRODUCES", ("org", CORP), ("ent", P, "반도체패키지기판", "반도체패키지기판"), 0.93),
        ],
    },

    # ── IX. 계열회사: 삼성그룹 계열 (기재정정 사업보고서 2023.12) ────
    "09e471e41f6a90e0": {  # 삼성그룹 63개 계열사; 삼성전자·삼성물산·삼성에스디에스 등
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.88, "그 밖의 특수관계자(삼성그룹 계열)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.85, "기타 특수관계자(삼성그룹 계열)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에스디에스"), 0.85, "기타 특수관계자(삼성그룹 계열)"),
        ],
    },
}


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

    # 2) 나머지 청크 = 엔티티/엣지 0개 (누락 0 보장)
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
    print("=== 삼성전기 Stage5 추출 결과 ===")
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
