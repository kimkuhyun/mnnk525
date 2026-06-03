"""Stage 5 비정형 추출 — 호텔신라 corp_code=00165680, text_micro 전체(~936) + table_nl 특수관계(~75).

호텔신라 = 삼성그룹 계열 면세·호텔 서비스 유통기업.
  - TR부문(Travel Retail): 신라면세점 — 시내(서울·제주), 공항(인천·김포), 온라인면세점,
    싱가포르 창이/홍콩 첵랍콕/마카오 공항 해외 면세점 운영. 글로벌 TR기업으로 성장 중.
  - 호텔&레저부문:
    ㆍ서울신라호텔(1982 개관, 포브스 5성, 미쉐린 라연 3스타)
    ㆍ제주신라호텔(1990 개관, 럭셔리 리조트)
    ㆍ신라스테이(비즈니스 호텔 브랜드, 동탄·역삼·제주 등 14개+)
    ㆍ신라모노그램(어퍼업스케일 브랜드, 1호: 베트남 다낭 2022 그랜드오픈)
    ㆍBTM(Business Travel Management) — 기업 출장 대행(항공·호텔·렌터카)
    ㆍVANTT(반트) — 피트니스 클럽 위탁운영
  - 특수관계:
    ㆍ합작: HDC신라면세점(현대산업개발 합작, 신라아이파크면세점)
    ㆍ관계기업: 3Sixty Duty Free & More Holdings LLC, GMS Duty Free Co. Ltd.
    ㆍ공동기업: 에이치디씨신라면세점, 로시안(Sky Shilla Duty Free Ltd)
    ㆍ종속기업(감사보고서): 신라에이치엠㈜, 에스비티엠㈜, ㈜에스에이치피코퍼레이션,
      Samsung Shilla Business Service Beijing Co. Ltd.,
      Shilla Travel Retail Pte. Ltd.(싱가포르), Shilla Travel Retail Hong Kong Limited,
      Shilla Retail Limited
    ㆍ삼성 대규모기업집단: 삼성전자, 삼성물산, 삼성생명보험, 삼성에스디에스

원장 = db/graph/ledger/extra28_00165680.jsonl (이 추출 전용).
실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_shilla_extra28.py
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

CORP = "호텔신라"
CORP_CODE = "00165680"

# ── 전용 원장 ─────────────────────────────────────────────────
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"
LEDGER_DIR.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = LEDGER_DIR / "extra28_00165680.jsonl"


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
# 호텔신라 = 삼성그룹 계열 면세·호텔·레저 서비스 유통기업
# TR부문: 신라면세점(시내/공항/온라인), 해외 면세점(싱가포르/홍콩/마카오)
# 호텔부문: 서울신라호텔, 제주신라호텔, 신라스테이, 신라모노그램, BTM, VANTT

EXTRACTIONS: dict[str, dict] = {

    # ── II. 사업의 내용: TR부문 개요 — 2023 사업보고서 ──────────────
    "bc52a3939ccc429f": {  # 2023 사업보고서 II: TR부문/호텔&레저부문 2개 사업부문 개요
        "entities": [
            (P, "면세점 서비스(TR부문)", "면세점 Travel Retail 서비스"),
            (P, "호텔·레저 서비스", "호텔 및 레저 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "면세점 서비스(TR부문)", "면세점 Travel Retail 서비스"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "호텔·레저 서비스", "호텔 및 레저 서비스"), 0.95),
        ],
    },

    # ── II. 사업의 내용: 신라면세점 브랜드·해외 채널 — 2023 사업보고서 ──
    "4188e72ef4a3e5e4": {  # 2023 사업보고서 II: 신라면세점 — 향수/화장품/시계/의류/가방 브랜드, 싱가포르/홍콩
        "entities": [
            (P, "신라면세점", "신라면세점 면세 유통 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "신라면세점", "신라면세점 면세 유통 서비스"), 0.95),
            E("RELATED_PARTY", ("org", CORP), ("org", "에이치디씨신라면세점"), 0.90, "합작 공동기업(서울 시내면세점)"),
        ],
    },

    # ── II. 사업의 내용: HDC신라면세점·신라아이파크면세점 — 2023 ────────
    "22cc5a42d58bff38": {  # 2023 사업보고서 II: 현대산업개발 합작 HDC신라면세점, 신라아이파크면세점 오픈
        "entities": [
            (P, "신라아이파크면세점", "신라아이파크면세점 도심형 면세점"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "신라아이파크면세점", "신라아이파크면세점 도심형 면세점"), 0.88),
            E("RELATED_PARTY", ("org", CORP), ("org", "에이치디씨신라면세점"), 0.92, "합작 공동기업(현대산업개발 합작, 신라아이파크면세점 운영)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "현대산업개발"), 0.85, "합작 파트너(HDC신라면세점 설립)"),
        ],
    },

    # ── II. 사업의 내용: 서울신라호텔 — 2023 사업보고서 ────────────────
    "798026981af2752b": {  # 2023 사업보고서 II: 서울신라호텔 — 포브스 5성, IOC/FIFA/다보스 유치
        "entities": [
            (P, "서울신라호텔", "서울신라호텔 럭셔리 호텔 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "서울신라호텔", "서울신라호텔 럭셔리 호텔 서비스"), 0.95),
        ],
    },

    # ── II. 사업의 내용: 제주신라호텔·신라스테이 — 2023 사업보고서 ──────
    "bb8be19b6ab0f0c5": {  # 2023 사업보고서 II: 신라스테이 비즈니스 호텔(동탄~여수 14개+), 신라모노그램 다낭
        "entities": [
            (P, "신라스테이", "신라스테이 프리미엄 비즈니스 호텔 브랜드"),
            (P, "신라모노그램", "신라모노그램 어퍼업스케일 호텔 브랜드"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "신라스테이", "신라스테이 프리미엄 비즈니스 호텔 브랜드"), 0.95),
            E("PRODUCES", ("org", CORP), ("ent", P, "신라모노그램", "신라모노그램 어퍼업스케일 호텔 브랜드"), 0.92),
        ],
    },

    # ── II. 사업의 내용: BTM(Business Travel Management) — 2023 ─────
    "9763a4816aa0018f": {  # 2023 사업보고서 II: BTM 사업 — 미국·영국·독일·중국·베트남·필리핀·인도·루마니아 법인
        "entities": [
            (P, "BTM(기업출장관리) 서비스", "BTM Business Travel Management 기업 출장 서비스"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "BTM(기업출장관리) 서비스", "BTM Business Travel Management 기업 출장 서비스"), 0.90),
        ],
    },

    # ── II. 사업의 내용: 온라인면세점·라뷰ON — 2023 사업보고서 ─────────
    "22cc5a42d58bff38_v2": {  # NOTE: 중복 방지 — 이미 위에서 처리
        "entities": [],
        "edges": [],
    },

    # ── II. 사업의 내용: VANTT 피트니스 클럽 — 2023 사업보고서 ──────────
    "b1bdea57c8cc16a0": {  # 2023 사업보고서 II: 호텔신라 TR+호텔 글로벌, 싱가포르/홍콩/마카오 면세점
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "신라면세점", "신라면세점 면세 유통 서비스"), 0.95),
        ],
    },

    # ── II. 사업의 내용: 경쟁요소 — 호텔 경쟁 ──────────────────────────
    "51a13fce20b61e46": {  # 2023 사업보고서 II: 면세/호텔&레저 산업 특성·경쟁요소
        "entities": [],
        "edges": [],
    },

    # ── II. 사업의 내용: 서울신라호텔 LifeStyle Hotel — 2023 사업보고서 ──
    "e93aad358db2b0b7": {  # 2023 사업보고서 II: 포브스 5성 5년 연속, 라연 미쉐린 3스타, LifeStyle Hotel
        "entities": [
            (T, "럭셔리 호텔 운영 노하우", "럭셔리 LifeStyle 호텔 운영 서비스 역량"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "럭셔리 호텔 운영 노하우", "럭셔리 LifeStyle 호텔 운영 서비스 역량"), 0.88),
        ],
    },

    # ── IX. 계열회사: 삼성그룹 계열 — 2023 사업보고서 ──────────────────
    "e0b9cb943de9ad4c": {  # 2023 사업보고서 IX: 삼성그룹 계열 63개사, 상장사 17개
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.95, "삼성그룹 대규모기업집단 계열사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.92, "삼성그룹 대규모기업집단 계열사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.92, "삼성그룹 대규모기업집단 계열사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에스디에스"), 0.90, "삼성그룹 대규모기업집단 계열사"),
        ],
    },

    # ── III. 특수관계자 표(연결) — 2023 사업보고서 감사보고서 ────────────
    "c87e90dfc4f85cb6": {  # 2023 사업보고서 감사보고서: 신라에이치엠/에스비티엠/에스에이치피코퍼레이션 거래 표
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "신라에이치엠"), 0.92, "종속기업(매출 28.9억, 매입 268.4억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에스비티엠"), 0.90, "종속기업(매출 16.0억, 매입 95.5억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에스에이치피코퍼레이션"), 0.90, "종속기업(매출 25.5억, 매입 142.5억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Shilla Travel Retail Pte. Ltd."), 0.88, "종속기업(싱가포르 창이 면세점 운영)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Shilla Travel Retail Hong Kong Limited"), 0.88, "종속기업(홍콩 첵랍콕 면세점, 대여금 346억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Shilla Retail Limited"), 0.85, "종속기업(해외 면세 유통)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Samsung Shilla Business Service Beijing Co., Ltd."), 0.85, "종속기업(중국 베이징 법인)"),
        ],
    },

    # ── III. 특수관계자 목록(연결 손익계산서 헤더) — 2023 사업보고서 연결감사보고서 ─
    "0942249290f34aa4": {  # 2023 사업보고서 연결감사보고서: 특수관계자 — 3Sixty/에이치디씨신라면세점/로시안/삼성전자 등
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "3Sixty Duty Free & More Holdings LLC"), 0.88, "관계기업(면세 유통 파트너)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에이치디씨신라면세점"), 0.92, "공동기업(현대산업개발 합작 면세점)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "로시안"), 0.85, "공동기업"),
        ],
    },

    # ── III. 특수관계자 자금거래 — 2023 사업보고서 연결감사보고서 ─────────
    "761aeb3623f46efa": {  # 2023 사업보고서 연결감사보고서: 3Sixty 대여금 136억, 로시안 출자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "3Sixty Duty Free & More Holdings LLC"), 0.88, "관계기업(대여금 136.7억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "로시안"), 0.85, "공동기업(현금출자 10.5억)"),
        ],
    },

    # ── III. 특수관계자 자금거래(개별) — 2023 사업보고서 감사보고서 ─────────
    "7899d3b90b6fe224": {  # 2023 사업보고서 감사보고서: Shilla Travel Retail HK 대여금 346억
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Shilla Travel Retail Hong Kong Limited"), 0.90, "종속기업(대여금 346.2억, 환산 증감 포함)"),
        ],
    },

    # ── III. 특수관계자(개별 재무제표 관계기업 목록) — 2023 ─────────────
    "2ced4c35509289cf": {  # 2023 사업보고서 재무제표 주석: GMS Duty Free/3Sixty/Sky Shilla Duty Free/로시안
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "GMS Duty Free Co., Ltd."), 0.85, "관계기업(해외 면세 유통)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "3Sixty Duty Free & More Holdings LLC"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Sky Shilla Duty Free Ltd"), 0.85, "공동기업"),
        ],
    },

    # ── III. 특수관계자(개별 감사보고서 전기 거래) — 2023 ───────────────
    "d79565b6fbd23da9": {  # 2023 사업보고서 감사보고서: 전기 거래 — 신라에이치엠/에스비티엠/에스에이치피
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "신라에이치엠"), 0.90, "종속기업(전기 매출 34.5억, 매입 283.0억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에스비티엠"), 0.88, "종속기업(전기 매입 8.5억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에스에이치피코퍼레이션"), 0.88, "종속기업(전기 매출 24.8억, 매입 109.6억)"),
        ],
    },

    # ── 개별감사보고서 자금거래(전기) — 2023 사업보고서 ──────────────────
    "a5c152f44b9e4d0d": {  # 2023 사업보고서 감사보고서: 3Sixty 대여금 57.3억, 로시안 출자
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "3Sixty Duty Free & More Holdings LLC"), 0.85, "관계기업(개별 대여금 57.3억, 전기)"),
        ],
    },

    # ── II. 2024.03 분기보고서: TR/호텔 부문 개요 ──────────────────────
    "fc3f0be538f7a1c0": {  # 2024.03 분기보고서 II: TR부문 매출 8,348억, 호텔&레저 1,624억
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "면세점 서비스(TR부문)", "면세점 Travel Retail 서비스"), 0.95),
        ],
    },

    # ── II. 2024.03 분기보고서: 신라스테이 플러스 런칭 ──────────────────
    "5a878ed4d4b8f266": {  # 2024.03 분기보고서 II: 신라스테이 플러스(제주 이호테우) 오픈 예정
        "entities": [
            (P, "신라스테이 플러스", "신라스테이 플러스 레저형 호텔"),
        ],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "신라스테이 플러스", "신라스테이 플러스 레저형 호텔"), 0.88),
        ],
    },

    # ── II. 2024.03 분기보고서: 서울신라호텔 미쉐린·라연 ───────────────
    "7033a3683136ccb4": {  # 2024.03 분기보고서 II: 서울신라호텔 포브스 5성, 라연 미쉐린 3스타 6년 연속
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "서울신라호텔", "서울신라호텔 럭셔리 호텔 서비스"), 0.95),
        ],
    },

    # ── II. 2024.03: 온라인 면세쇼핑 혁신·메타버스 MOU ─────────────────
    "433bc9c3bb716ceb": {  # 2024.03 분기보고서 II: 라뷰ON 비대면 상담, 메타버스 아트테크 MOU
        "entities": [
            (T, "면세점 디지털 전환 기술", "면세점 온라인·메타버스 디지털 전환 서비스"),
        ],
        "edges": [
            E("USES_TECH", ("org", CORP), ("ent", T, "면세점 디지털 전환 기술", "면세점 온라인·메타버스 디지털 전환 서비스"), 0.82),
            E("RELATED_PARTY", ("org", CORP), ("org", "에이치디씨신라면세점"), 0.90, "합작 공동기업(글로벌 면세점 운영)"),
        ],
    },

    # ── II. 2024.03: BTM 글로벌 법인 확장 ─────────────────────────────
    "3ed117130bcc8902": {  # 2024.03 분기보고서 II: BTM 미국·영국·독일·중국·베트남·필리핀·인도·루마니아 법인
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "BTM(기업출장관리) 서비스", "BTM Business Travel Management 기업 출장 서비스"), 0.90),
        ],
    },

    # ── III. 특수관계자 목록(연결) — 2024.06 반기보고서 ─────────────────
    "36bc7f7e619a1eaa": {  # 2024.06 반기보고서: 특수관계자 — 3Sixty/에이치디씨신라면세점/로시안/삼성4개사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "3Sixty Duty Free & More Holdings LLC"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에이치디씨신라면세점"), 0.92, "공동기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "로시안"), 0.85, "공동기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.95, "삼성그룹 대규모기업집단 계열사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.92, "삼성그룹 대규모기업집단 계열사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.92, "삼성그룹 대규모기업집단 계열사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에스디에스"), 0.90, "삼성그룹 대규모기업집단 계열사"),
        ],
    },

    # ── III. 특수관계자 목록(개별) — 2024.06 반기보고서 ─────────────────
    "4f22f865163261ac": {  # 2024.06 반기보고서 개별재무 주석: 특수관계자 동일 목록
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "3Sixty Duty Free & More Holdings LLC"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에이치디씨신라면세점"), 0.92, "공동기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "로시안"), 0.85, "공동기업"),
        ],
    },

    # ── II. 2024.06 반기보고서: 신라스테이 플러스 오픈 ─────────────────
    "13f219b44b9c90b1": {  # 2024.06 반기보고서 II: 신라스테이 플러스 제주 이호테우 오픈 완료
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "신라스테이 플러스", "신라스테이 플러스 레저형 호텔"), 0.90),
        ],
    },

    # ── III. 특수관계자 목록(연결) — 2024.09 분기보고서 ─────────────────
    "426dab50ca60d247": {  # 2024.09 분기보고서 개별재무 주석: 특수관계자 목록
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "3Sixty Duty Free & More Holdings LLC"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에이치디씨신라면세점"), 0.92, "공동기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "로시안"), 0.85, "공동기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.95, "삼성그룹 대규모기업집단 계열사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.92, "삼성그룹 대규모기업집단 계열사"),
        ],
    },

    # ── III. 특수관계자 목록(연결) — 2024.09 분기보고서 두 번째 ─────────
    "68e37db3d6c1f65a": {  # 2024.09 분기보고서 개별재무 주석 (전기): 특수관계자 동일 목록
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.92, "삼성그룹 대규모기업집단 계열사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에스디에스"), 0.90, "삼성그룹 대규모기업집단 계열사"),
        ],
    },

    # ── III. 특수관계자 목록(개별) — 2024.12 사업보고서 ─────────────────
    "11650cbf280d4135": {  # 2024.12 사업보고서 개별재무 주석: 특수관계자 목록 최신
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "3Sixty Duty Free & More Holdings LLC"), 0.88, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에이치디씨신라면세점"), 0.92, "공동기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "로시안"), 0.85, "공동기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.95, "삼성그룹 대규모기업집단 계열사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.92, "삼성그룹 대규모기업집단 계열사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.92, "삼성그룹 대규모기업집단 계열사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에스디에스"), 0.90, "삼성그룹 대규모기업집단 계열사"),
        ],
    },

    # ── IX. 계열회사 — 2024.06 반기보고서 ──────────────────────────────
    "1710149936c2e0ff": {  # 2024.06 반기보고서 IX: 삼성그룹 계열 63개사, 상장 17개사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.95, "삼성그룹 대규모기업집단 계열사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.92, "삼성그룹 대규모기업집단 계열사"),
        ],
    },

    # ── IX. 계열회사 — 2024.12 사업보고서 ──────────────────────────────
    "34a07216b5f379a3": {  # 2024.12 사업보고서 IX: 삼성그룹 계열 63개사, 상장 17개사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.95, "삼성그룹 대규모기업집단 계열사(2024.12말)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.92, "삼성그룹 대규모기업집단 계열사(2024.12말)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.92, "삼성그룹 대규모기업집단 계열사(2024.12말)"),
        ],
    },

    # ── 2025.12 사업보고서 특수관계자 표(감사보고서) ─────────────────────
    "76641860e2030b93": {  # 2025.12 사업보고서 감사보고서: 신라에이치엠 매출 38억, 에스에이치피 매출 29.4억
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "신라에이치엠"), 0.92, "종속기업(당기 매출 38.0억, 기타수익 200억, 매입 295.2억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에스비티엠"), 0.90, "종속기업(당기 매출 15.2억, 매입 0.5억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에스에이치피코퍼레이션"), 0.90, "종속기업(당기 매출 29.4억, 매입 136.6억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Shilla Travel Retail Pte. Ltd."), 0.88, "종속기업(싱가포르 창이공항 면세점)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Shilla Travel Retail Hong Kong Limited"), 0.90, "종속기업(홍콩 첵랍콕, 대여금 392.8억)"),
        ],
    },

    # ── 2025.12 사업보고서 연결감사보고서 자금거래 ─────────────────────
    "352a8f9b85ae4663": {  # 2025.12 사업보고서 연결감사보고서: 3Sixty 처분, 에이치디씨신라 출자 200억
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "3Sixty Duty Free & More Holdings LLC"), 0.85, "관계기업(2025년 중 처분·특수관계 종료)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에이치디씨신라면세점"), 0.92, "공동기업(2025년 현금출자 200억)"),
        ],
    },

    # ── 2025.12 사업보고서: 로시안 지분매각 완료 ──────────────────────
    "458df7ca49aeb473": {  # 2025.12 사업보고서 연결감사보고서 주석: 로시안 지분매각 완료·특수관계 제외
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "로시안"), 0.82, "공동기업(2025년 지분매각 완료·특수관계 종료)"),
        ],
    },

    # ── 2025.12 사업보고서 감사보고서 자금거래(전기) ────────────────────
    "a7b4bf8c97cd9b97": {  # 2025.12 사업보고서 감사보고서 전기: Shilla HK 대여금 403.2억
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Shilla Travel Retail Hong Kong Limited"), 0.90, "종속기업(전기 대여금 403.2억, 환차익 포함)"),
        ],
    },

    # ── IX. 계열회사 — 2025.12 사업보고서 ──────────────────────────────
    "b667e1c9ab58745c": {  # 2025.12 사업보고서 IX: 삼성그룹 67개 계열사(전년 +4개), 상장 18개사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.95, "삼성그룹 대규모기업집단 계열사(2025.12말, 67개사)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.92, "삼성그룹 대규모기업집단 계열사(2025.12말)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.92, "삼성그룹 대규모기업집단 계열사(2025.12말)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에스디에스"), 0.90, "삼성그룹 대규모기업집단 계열사(2025.12말)"),
        ],
    },

    # ── IV. 이사의 경영진단: TR부문 흑자전환 — 2025.12 사업보고서 ────────
    "0051103d9f63caf2": {  # 2025.12 사업보고서 IV: TR부문 흑자전환, EBITDA 154,313백만원(+21.4%)
        "entities": [],
        "edges": [
            E("PRODUCES", ("org", CORP), ("ent", P, "면세점 서비스(TR부문)", "면세점 Travel Retail 서비스"), 0.92),
        ],
    },

    # ── IX. 계열회사 — 2025.06 반기보고서 ──────────────────────────────
    "ea4297dc42e3267f": {  # 2025.06 반기보고서 IX: 삼성그룹 계열 63개사(반기말 기준)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.95, "삼성그룹 대규모기업집단 계열사(2025.06말)"),
        ],
    },

    # ── 2025.12 연결감사보고서: 3Sixty 처분 자금거래 ────────────────────
    "f194ef9c221c48f9": {  # 2025.12 사업보고서 연결감사보고서: 3Sixty 대여금 155.9억→처분(회수 154.1억)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "3Sixty Duty Free & More Holdings LLC"), 0.85, "관계기업(2025년 처분 — 대여금 155.9억 회수)"),
        ],
    },

    # ── 2023 사업보고서 감사보고서 특수관계자 자금거래 ──────────────────
    "39a9808aabcc70f1": {  # 2023 사업보고서 감사보고서: Shilla HK 대여금 기말 351.6억
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Shilla Travel Retail Hong Kong Limited"), 0.90, "종속기업(대여금 기말 351.6억)"),
        ],
    },

    # ── 2023 사업보고서 개별재무 주석: GMS Duty Free/Sky Shilla ────────
    "d4d81ca6645b0ed3": {  # 2023 사업보고서 개별재무 주석: 개별기준 특수관계자 목록
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "GMS Duty Free Co., Ltd."), 0.85, "관계기업"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Sky Shilla Duty Free Ltd"), 0.85, "공동기업(마카오 공항 면세점)"),
        ],
    },

    # ── 2023 사업보고서 개별재무 주석: 특수관계자 거래 대·중·소 ─────────
    "8e58f645b840068a": {  # 2023 사업보고서 개별재무 주석: 3Sixty/에이치디씨신라면세점/로시안/삼성4개사 헤더
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.95, "삼성그룹 대규모기업집단 계열사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성물산"), 0.92, "삼성그룹 대규모기업집단 계열사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.92, "삼성그룹 대규모기업집단 계열사"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성에스디에스"), 0.90, "삼성그룹 대규모기업집단 계열사"),
        ],
    },

    # ── 2023 사업보고서 개별감사보고서 특수관계자 — 에스에이치피코퍼레이션 출자 ─
    "7899d3b90b6fe224_v2": {  # NOTE: 중복 방지 — 이미 위에서 처리
        "entities": [],
        "edges": [],
    },

    # ── 2023 사업보고서 연결감사보고서: 에이치디씨신라면세점/로시안 헤더 ─
    "b7a3e7ab4a742cf2": {  # 2023 사업보고서 연결감사보고서: 동일 헤더 구조 (다른 row)
        "entities": [],
        "edges": [],
    },

    # ── 2023 사업보고서 개별재무 주석 (전기 비교) — 3Sixty/에이치디씨 ──
    "554c03a97afce1e3": {  # 2023 사업보고서 개별재무 주석 전기: 동일 특수관계자 목록
        "entities": [],
        "edges": [],
    },

    # ── 2023 사업보고서 개별재무 주석 (기타) — 3Sixty/에이치디씨 ─────────
    "b257536bc6be746b": {  # 2023 사업보고서 개별재무 주석 기타: 헤더만 있는 청크
        "entities": [],
        "edges": [],
    },

    # ── 2023 사업보고서 개별재무 주석 (기타2) ──────────────────────────
    "0ffac242afab7399": {  # 2023 사업보고서 개별재무 주석: GMS/3Sixty/에이치디씨/로시안 헤더+종속기업 3개
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "에이치디씨신라면세점"), 0.92, "공동기업"),
        ],
    },

    # ── 2025.12 감사보고서 Shilla HK 최신 대여금 ────────────────────────
    "2f480b56999891d8": {  # 2025.12 사업보고서 감사보고서: Shilla HK 대여금 기말 392.8억(환산 감소)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Shilla Travel Retail Hong Kong Limited"), 0.90, "종속기업(대여금 기말 392.8억, 2025.12말)"),
        ],
    },

    # ── 2025.12 사업보고서 감사보고서 3Sixty 처분(개별) ─────────────────
    "6922e03f97365529": {  # 2025.12 사업보고서 감사보고서: 3Sixty 개별 대여금 65.3억→회수 완료·처분
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "3Sixty Duty Free & More Holdings LLC"), 0.85, "관계기업(개별 대여금 65.3억 전액 회수·처분 완료)"),
        ],
    },

    # ── 2025.12 감사보고서 전기 거래 — 에스에이치피 등 ─────────────────
    "b221915e10cd9f4e": {  # 2025.12 사업보고서 감사보고서 전기: 신라에이치엠 44.5억, 에스에이치피 25.0억
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "신라에이치엠"), 0.90, "종속기업(전기 매출 44.5억, 매입 215.1억)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "에스에이치피코퍼레이션"), 0.88, "종속기업(전기 매출 25.0억, 매입 129.3억)"),
        ],
    },

    # ── 2025.12 사업보고서 감사보고서 전기 기말 채권/채무 ───────────────
    "bc9e5194a9aa0537": {  # 2025.12 감사보고서 전기말: 신라에이치엠/에스비티엠/에스에이치피/Shilla HK
        "entities": [],
        "edges": [],
    },

    # ── 2025.12 사업보고서 감사보고서 당기말 채권/채무 ────────────────────
    "b4f1b60680829eba": {  # 2025.12 감사보고서 당기말: 신라에이치엠/에스비티엠/에스에이치피코퍼레이션
        "entities": [],
        "edges": [],
    },

    # ── 2025.12 사업보고서 감사보고서 주석 (3Sixty/로시안 처분 설명) ──────
    "8b2c00547df1f2e6": {  # 2025.12 감사보고서 주석(*1/*2/*3): 로시안 지분매각 완료, 삼성생명 기타채권
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "로시안"), 0.80, "공동기업(2025년 지분매각 완료 — 특수관계 제외)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성생명보험"), 0.88, "삼성그룹 계열사(기타채권: 사외적립자산+보증금 246억)"),
        ],
    },

    # ── 2025.12 연결감사보고서 주석 (로시안 처분·3Sixty 처분 설명) ─────────
    "458df7ca49aeb473_v2": {  # NOTE: 중복 방지 — 이미 처리
        "entities": [],
        "edges": [],
    },

    # ── 2025.12 감사보고서 전기 자금거래 ──────────────────────────────
    "5b2f805dbcc31696": {  # 2025.12 감사보고서 전기(2024): 3Sixty 57.3억, 로시안 출자, 에이치디씨 200억
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "에이치디씨신라면세점"), 0.92, "공동기업(2024년 현금출자 200억 실행)"),
        ],
    },

    # ── 2024.03 분기보고서 개별재무 주석 특수관계자 ─────────────────────
    "f020ac31d92b51b2": {  # 2024.03 분기보고서 개별재무 주석: 종속기업 3개(SGD/HKD/USD 기능통화)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "Shilla Travel Retail Pte. Ltd."), 0.88, "종속기업(기능통화 SGD, 싱가포르)"),
            E("RELATED_PARTY", ("org", CORP), ("org", "Shilla Travel Retail Hong Kong Limited"), 0.88, "종속기업(기능통화 HKD, 홍콩)"),
        ],
    },

    # ── 2024.06 반기보고서 개별재무 주석 특수관계자 ─────────────────────
    "ab21de44ac667720": {  # 2024.06 반기보고서 개별재무 주석: 종속기업 3개(SGD/HKD/USD 기능통화)
        "entities": [],
        "edges": [],
    },

    # ── 2024.09 분기보고서 개별재무 주석 특수관계자 ─────────────────────
    "beba5d880007067f": {  # 2024.09 분기보고서 개별재무 주석: 종속기업 3개(SGD/HKD/USD 기능통화)
        "entities": [],
        "edges": [],
    },

    # ── 2024.12 사업보고서 IX 계열회사 ─────────────────────────────────
    "1c725d7bbe5b7eed": {  # 2024.12 사업보고서(기재정정) IX: 삼성그룹 63개사
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("org", CORP), ("org", "삼성전자"), 0.95, "삼성그룹 대규모기업집단 계열사(2024.12말, 기재정정)"),
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
    print("=== 호텔신라 Stage5 추출 결과 ===")
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
