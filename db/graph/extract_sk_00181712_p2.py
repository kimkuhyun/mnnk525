"""SK(주) corp_code=00181712 비정형 추출 적재 — 배치 p2 (OFFSET 3600).

대상: SELECT chunk_id,rcept_no,section_path,embedding_text FROM chunk_index
      WHERE corp_code='00181712' AND chunk_type='text_micro'
      ORDER BY chunk_id LIMIT 3600 OFFSET 3600  → 3,547개 청크

Claude 에이전트가 SK(주) 사업보고서/분기보고서/반기보고서 본문을 직접 읽고
엔티티(Product·Technology)·엣지(PRODUCES·USES_TECH·SUPPLIES_TO·RELATED_PARTY·hasObject)
를 추출한 결과를 멱등 적재한다.

SK(주)는 에너지·화학·ICT·바이오·반도체 등 광범위한 사업군을 가진 복합 지주사.
extract_helpers.resolve_org 는 3사만 알므로, SK(주) org는 corp_code='00181712' 로
직접 매칭하는 SK_ORG_MATCH 를 사용한다.

원장: db/graph/ledger/extra28_00181712_p2.jsonl  (공유 ledger 금지)
실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_sk_00181712_p2.py
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

CORP_CODE = "00181712"
WHERE = f"WHERE corp_code='{CORP_CODE}' AND chunk_type='text_micro' ORDER BY chunk_id LIMIT 3600 OFFSET 3600"

# SK(주) — 31사 마스터에 있으나 extract_helpers CORP_NAME(3사만)에 없어서
# resolve_org 가 needs_er를 반환함. 직접 corp_code 노드로 연결하기 위해 수동 구성.
SK_ORG = {
    "mode": "corp",
    "corp_code": CORP_CODE,
    "er_name": "sk",
    "id": CORP_CODE,
    "name": "SK(주)",
}

# 이 배치 전용 원장 (공유 ledger 금지)
LEDGER = Path(__file__).resolve().parent / "ledger" / "extra28_00181712_p2.jsonl"

P = "Product"
T = "Technology"


def E(rel, frm, to, conf, relation_type=None):
    d = {"rel": rel, "from": frm, "to": to, "conf": conf}
    if relation_type:
        d["relation_type"] = relation_type
    return d


# ── from/to 참조 규약 ────────────────────────────────────────
# ('sk',)          → SK(주) corp_code='00181712' 노드 (직접 MATCH)
# ('org', 이름)     → resolve_org 로 3사 or needs_er
# ('ent', label, canonical, name) → Product/Technology MERGE

EXTRACTIONS: dict[str, dict] = {

    # ── 수소/에너지 사업 (SK이엔에스, 블룸에너지 협력) ─────────────────
    "80f0ed4438edce8a": {  # SOEC 수전해 시스템, 블룸에너지 공동개발, World Energy GH2 그린수소
        "entities": [
            (T, "soec 수전해", "SOEC(Solid Oxide Electrolyzer Cell)"),
            (P, "그린수소", "그린수소"),
            (P, "그린암모니아", "그린암모니아"),
        ],
        "edges": [
            E("USES_TECH", ("sk",), ("ent", T, "soec 수전해", "SOEC(Solid Oxide Electrolyzer Cell)"), 0.9),
            E("PRODUCES", ("sk",), ("ent", P, "그린수소", "그린수소"), 0.88),
            E("PRODUCES", ("sk",), ("ent", P, "그린암모니아", "그린암모니아"), 0.82),
            E("RELATED_PARTY", ("sk",), ("org", "Bloom Energy Corporation"), 0.88, "기술협력(SOEC 수전해)"),
            E("RELATED_PARTY", ("sk",), ("org", "World Energy GH2"), 0.82, "사업협력(그린수소 프로젝트)"),
        ],
    },

    "8fa3b1497e0b8c14": {  # 블룸에너지 SOEC 수전해 공동개발 (반기보고서 2024.06)
        "entities": [
            (T, "soec 수전해", "SOEC(Solid Oxide Electrolyzer Cell)"),
            (P, "그린수소", "그린수소"),
        ],
        "edges": [
            E("USES_TECH", ("sk",), ("ent", T, "soec 수전해", "SOEC(Solid Oxide Electrolyzer Cell)"), 0.9),
            E("PRODUCES", ("sk",), ("ent", P, "그린수소", "그린수소"), 0.85),
            E("RELATED_PARTY", ("sk",), ("org", "Bloom Energy Corporation"), 0.88, "기술협력(SOEC 수전해)"),
        ],
    },

    # ── SK이노베이션 — 석유/화학/배터리 사업 ───────────────────────────
    "ee3d91d7132ab42b": {  # SK이노베이션 9개 주요 자회사, 석유·화학·배터리 밸류체인
        "entities": [
            (P, "배터리", "전기차용 배터리"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "배터리", "전기차용 배터리"), 0.9),
            E("RELATED_PARTY", ("sk",), ("org", "SK이노베이션"), 0.95, "종속기업(에너지·화학·배터리)"),
            E("RELATED_PARTY", ("sk",), ("org", "SK에너지"), 0.88, "종속기업(석유사업)"),
            E("RELATED_PARTY", ("sk",), ("org", "SK지오센트릭"), 0.88, "종속기업(화학사업)"),
            E("RELATED_PARTY", ("sk",), ("org", "SK온"), 0.92, "종속기업(배터리사업)"),
            E("RELATED_PARTY", ("sk",), ("org", "SK아이이테크놀로지"), 0.88, "종속기업(소재사업)"),
        ],
    },

    "eeee9cd34cc5c827": {  # 배터리 분리막, IRA 대응, 차세대 배터리 소재
        "entities": [
            (P, "lbs", "리튬이온 배터리 분리막(LiBS)"),
            (T, "고체전해질", "고체전해질(차세대 배터리 소재)"),
            (T, "co2 포집 분리막", "이산화탄소 포집 분리막"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "lbs", "리튬이온 배터리 분리막(LiBS)"), 0.9),
            E("USES_TECH", ("sk",), ("ent", T, "고체전해질", "고체전해질(차세대 배터리 소재)"), 0.82),
            E("USES_TECH", ("sk",), ("ent", T, "co2 포집 분리막", "이산화탄소 포집 분리막"), 0.82),
        ],
    },

    "8173d1128b62f373": {  # 분리막 IT/EV/ESS 전략 (분기보고서 2025.09)
        "entities": [
            (P, "lbs", "리튬이온 배터리 분리막(LiBS)"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "lbs", "리튬이온 배터리 분리막(LiBS)"), 0.92),
        ],
    },

    # ── SK배터리 해외 생산법인 ──────────────────────────────────────
    "8f3e9a2101ff013a": {  # SK온 해외 배터리 생산법인, BlueOval SK Ford JV
        "entities": [
            (P, "배터리", "전기차용 배터리"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "배터리", "전기차용 배터리"), 0.92),
            E("RELATED_PARTY", ("sk",), ("org", "SK Battery Manufacturing Kft."), 0.9, "종속기업(유럽 배터리 생산법인)"),
            E("RELATED_PARTY", ("sk",), ("org", "SK On Jiangsu Co., Ltd."), 0.88, "종속기업(중국 배터리 생산법인, 70%)"),
            E("RELATED_PARTY", ("sk",), ("org", "SK On Yancheng Co., Ltd."), 0.88, "종속기업(중국 배터리 생산법인)"),
            E("RELATED_PARTY", ("sk",), ("org", "BlueOval SK, LLC"), 0.9, "합작법인(Ford JV, 미국 배터리 생산)"),
            E("RELATED_PARTY", ("sk",), ("org", "Ford Motor Company"), 0.85, "합작법인 파트너(BlueOval SK)"),
        ],
    },

    # ── ENEOS UCO 원재료 매입, 윤활기유 ──────────────────────────────
    "82460d03743a2dc6": {  # ENEOS UCO 구매 약정, PT Pertamina 협력
        "entities": [
            (P, "윤활기유", "윤활기유(Base Oil)"),
            (P, "미전환유", "미전환유(UCO, Unconverted Oil)"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "윤활기유", "윤활기유(Base Oil)"), 0.88),
            E("PRODUCES", ("sk",), ("ent", P, "미전환유", "미전환유(UCO, Unconverted Oil)"), 0.8),
            E("SUPPLIES_TO", ("org", "ENEOS Corporation"), ("sk",), 0.92),
            E("RELATED_PARTY", ("sk",), ("org", "ENEOS Corporation"), 0.9, "원재료 공급계약(UCO 매입)"),
            E("RELATED_PARTY", ("sk",), ("org", "PT Pertamina (Persero)"), 0.82, "사업협력(윤활유)"),
        ],
    },

    "8256e33bce180d51": {  # SK이노베이션 트레이딩, 원유 Trading, SK온 배터리 원소재
        "entities": [
            (P, "배터리 원소재", "배터리 원소재"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "배터리 원소재", "배터리 원소재"), 0.82),
            E("RELATED_PARTY", ("sk",), ("org", "SK On Hungary Kft."), 0.88, "종속기업(유럽 배터리 생산법인)"),
            E("RELATED_PARTY", ("sk",), ("org", "SK Battery America, Inc."), 0.9, "종속기업(미국 배터리 생산법인)"),
        ],
    },

    # ── SK바이오팜 — 세노바메이트/XCOPRI ─────────────────────────────
    "82fd85f0f4be61d1": {  # 세노바메이트 SK Life Science 미국, Arvelle 유럽, 오노약품 일본, Ignis 중국
        "entities": [
            (P, "세노바메이트", "세노바메이트(Cenobamate)"),
            (P, "xcopri", "XCOPRI(세노바메이트 제품명)"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "세노바메이트", "세노바메이트(Cenobamate)"), 0.95),
            E("PRODUCES", ("sk",), ("ent", P, "xcopri", "XCOPRI(세노바메이트 제품명)"), 0.95),
            E("RELATED_PARTY", ("sk",), ("org", "SK Life Science, Inc."), 0.9, "종속기업(미국 판매법인)"),
            E("RELATED_PARTY", ("sk",), ("org", "Arvelle Therapeutics"), 0.88, "기술수출계약(유럽 판권)"),
            E("RELATED_PARTY", ("sk",), ("org", "Angelini Pharma"), 0.82, "기술수출계약(유럽, Arvelle 인수자)"),
            E("RELATED_PARTY", ("sk",), ("org", "오노약품공업"), 0.88, "기술수출계약(일본 판권)"),
            E("RELATED_PARTY", ("sk",), ("org", "Ignis Therapeutics"), 0.85, "합작법인(중국 JV)"),
        ],
    },

    "825731038851ba52": {  # 세노바메이트/솔리암페톨 FDA NDA 승인, SK Life Science (2025.06)
        "entities": [
            (P, "세노바메이트", "세노바메이트(Cenobamate)"),
            (P, "xcopri", "XCOPRI(세노바메이트 제품명)"),
            (P, "솔리암페톨", "솔리암페톨(Solriamfetol)"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "세노바메이트", "세노바메이트(Cenobamate)"), 0.95),
            E("PRODUCES", ("sk",), ("ent", P, "xcopri", "XCOPRI(세노바메이트 제품명)"), 0.95),
            E("PRODUCES", ("sk",), ("ent", P, "솔리암페톨", "솔리암페톨(Solriamfetol)"), 0.9),
            E("RELATED_PARTY", ("sk",), ("org", "SK Life Science, Inc."), 0.9, "종속기업(미국 판매법인)"),
        ],
    },

    "894e74f4bc2f7782": {  # 세노바메이트 FDA 승인, Arvelle 유럽 (2023.12)
        "entities": [
            (P, "세노바메이트", "세노바메이트(Cenobamate)"),
            (P, "xcopri", "XCOPRI(세노바메이트 제품명)"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "세노바메이트", "세노바메이트(Cenobamate)"), 0.95),
            E("PRODUCES", ("sk",), ("ent", P, "xcopri", "XCOPRI(세노바메이트 제품명)"), 0.95),
            E("RELATED_PARTY", ("sk",), ("org", "Arvelle Therapeutics"), 0.85, "기술수출계약(유럽 판권)"),
        ],
    },

    "8b163c2634237aa3": {  # 세노바메이트 Angelini, SK Life Science 미국, 오노약품 일본 (2024.09)
        "entities": [
            (P, "세노바메이트", "세노바메이트(Cenobamate)"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "세노바메이트", "세노바메이트(Cenobamate)"), 0.95),
            E("RELATED_PARTY", ("sk",), ("org", "SK Life Science, Inc."), 0.9, "종속기업(미국 판매법인)"),
            E("RELATED_PARTY", ("sk",), ("org", "Angelini Pharma"), 0.82, "기술수출계약(유럽)"),
            E("RELATED_PARTY", ("sk",), ("org", "오노약품공업"), 0.85, "기술수출계약(일본 판권)"),
        ],
    },

    "8dcc25e25f78df66": {  # 세노바메이트 XCOPRI (2025.03)
        "entities": [
            (P, "세노바메이트", "세노바메이트(Cenobamate)"),
            (P, "xcopri", "XCOPRI(세노바메이트 제품명)"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "세노바메이트", "세노바메이트(Cenobamate)"), 0.95),
            E("PRODUCES", ("sk",), ("ent", P, "xcopri", "XCOPRI(세노바메이트 제품명)"), 0.95),
            E("RELATED_PARTY", ("sk",), ("org", "Arvelle Therapeutics"), 0.82, "기술수출계약(유럽 판권)"),
        ],
    },

    "85028c281eb98591": {  # 세노바메이트 XCOPRI 미국 직판, Angelini 유럽 (2026.03)
        "entities": [
            (P, "세노바메이트", "세노바메이트(Cenobamate)"),
            (P, "xcopri", "XCOPRI(세노바메이트 제품명)"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "세노바메이트", "세노바메이트(Cenobamate)"), 0.95),
            E("PRODUCES", ("sk",), ("ent", P, "xcopri", "XCOPRI(세노바메이트 제품명)"), 0.95),
            E("RELATED_PARTY", ("sk",), ("org", "SK Life Science, Inc."), 0.9, "종속기업(미국 판매법인)"),
            E("RELATED_PARTY", ("sk",), ("org", "Angelini Pharma"), 0.82, "기술수출계약(유럽)"),
        ],
    },

    # ── SK텔레콤/ICT — AI R&D, 5G ──────────────────────────────────
    "80d95ee5eeee4a6f": {  # SKT AI R&D센터, SK브로드밴드 (2025.06)
        "entities": [
            (T, "5g", "5G 이동통신"),
            (T, "ai", "AI(인공지능)"),
        ],
        "edges": [
            E("USES_TECH", ("sk",), ("ent", T, "5g", "5G 이동통신"), 0.88),
            E("USES_TECH", ("sk",), ("ent", T, "ai", "AI(인공지능)"), 0.9),
            E("RELATED_PARTY", ("sk",), ("org", "SK텔레콤"), 0.92, "종속기업(ICT/통신)"),
            E("RELATED_PARTY", ("sk",), ("org", "SK브로드밴드"), 0.88, "종속기업(유선방송·인터넷)"),
        ],
    },

    "cb9f24163c57ace8": {  # SKT 5G 세계 최초 상용화 (2025.12)
        "entities": [
            (T, "5g", "5G 이동통신"),
        ],
        "edges": [
            E("USES_TECH", ("sk",), ("ent", T, "5g", "5G 이동통신"), 0.92),
            E("RELATED_PARTY", ("sk",), ("org", "SK텔레콤"), 0.9, "종속기업(통신·AI)"),
        ],
    },

    # ── SK스퀘어 — 투자사업, 11번가, 티맵모빌리티 ─────────────────────
    "80e273860a30abd8": {  # SK스퀘어 인적분할, 11번가, 티맵모빌리티, SK쉴더스 (2026.03)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("sk",), ("org", "SK스퀘어"), 0.92, "종속기업(투자전문지주)"),
            E("RELATED_PARTY", ("sk",), ("org", "11번가"), 0.85, "종속기업(커머스플랫폼)"),
            E("RELATED_PARTY", ("sk",), ("org", "티맵모빌리티"), 0.85, "종속기업(모빌리티플랫폼)"),
            E("RELATED_PARTY", ("sk",), ("org", "SK쉴더스"), 0.82, "종속기업(보안사업)"),
        ],
    },

    "a0bd9fdc89a66a93": {  # SK스퀘어, SK하이닉스 AI 메모리, 11번가 (2024.12)
        "entities": [
            (P, "ai 메모리", "AI 메모리"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "ai 메모리", "AI 메모리"), 0.82),
            E("RELATED_PARTY", ("sk",), ("org", "SK스퀘어"), 0.9, "종속기업(투자전문지주)"),
            E("RELATED_PARTY", ("sk",), ("org", "SK하이닉스"), 0.85, "관계기업(AI 메모리 사업)"),
            E("RELATED_PARTY", ("sk",), ("org", "11번가"), 0.82, "관계기업(커머스)"),
        ],
    },

    # ── SK CMO 바이오텍 — 의약품 위탁생산 ──────────────────────────────
    "80f320a1200c0377": {  # SK CMO 사업, SK바이오텍 (2024.03)
        "entities": [
            (T, "cmo", "CMO(의약품 위탁생산)"),
        ],
        "edges": [
            E("USES_TECH", ("sk",), ("ent", T, "cmo", "CMO(의약품 위탁생산)"), 0.9),
            E("RELATED_PARTY", ("sk",), ("org", "SK바이오텍"), 0.9, "종속기업(CMO 사업)"),
        ],
    },

    "8183f1b17dbc1705": {  # 연속공정기술, HPAPI 생산 (CMO 2025.06)
        "entities": [
            (T, "연속공정 기술", "연속공정 기술(Continuous Manufacturing)"),
            (T, "hpapi", "HPAPI(고활성 원료의약품) 생산기술"),
        ],
        "edges": [
            E("USES_TECH", ("sk",), ("ent", T, "연속공정 기술", "연속공정 기술(Continuous Manufacturing)"), 0.88),
            E("USES_TECH", ("sk",), ("ent", T, "hpapi", "HPAPI(고활성 원료의약품) 생산기술"), 0.85),
        ],
    },

    # ── 전기차 충전기 (시그넷이브이) ─────────────────────────────────
    "84db27fb98b3e278": {  # 전기차충전기 닛산/현대기아/BMW/Ford 납품 (2023.12)
        "entities": [
            (P, "전기차 충전기", "전기차 급속충전기"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "전기차 충전기", "전기차 급속충전기"), 0.9),
            E("SUPPLIES_TO", ("sk",), ("org", "현대기아차"), 0.82),
            E("SUPPLIES_TO", ("sk",), ("org", "BMW"), 0.82),
            E("SUPPLIES_TO", ("sk",), ("org", "Ford Motor Company"), 0.82),
            E("SUPPLIES_TO", ("sk",), ("org", "닛산자동차"), 0.82),
        ],
    },

    "82ad16611ed04fc1": {  # 급속충전기 병렬모듈형 분산제어 (2024.12)
        "entities": [
            (P, "전기차 충전기", "전기차 급속충전기"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "전기차 충전기", "전기차 급속충전기"), 0.9),
        ],
    },

    # ── SK에코플랜트 — 환경/건설 ────────────────────────────────────
    "81bd22ebb62bcfde": {  # SK에코플랜트 TCFD 기후변화 (2023.12)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("sk",), ("org", "SK에코플랜트"), 0.88, "종속기업(환경·건설)"),
        ],
    },

    "812a0a9bc78a4f79": {  # 폐배터리 리사이클, 니켈/코발트 (2024.03)
        "entities": [
            (T, "폐배터리 처리", "폐배터리 리사이클링(희소금속 추출)"),
        ],
        "edges": [
            E("USES_TECH", ("sk",), ("ent", T, "폐배터리 처리", "폐배터리 리사이클링(희소금속 추출)"), 0.85),
            E("RELATED_PARTY", ("sk",), ("org", "SK에코플랜트"), 0.88, "종속기업(환경·재생에너지)"),
        ],
    },

    # ── SKC — 소재/반도체 ──────────────────────────────────────────
    "904cc153f6d06526": {  # SK엔펄스 CMP Slurry 영업양도, SK에코플랜트 매각 (2025.12)
        "entities": [
            (P, "cmp slurry", "CMP Slurry(반도체 연마재)"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "cmp slurry", "CMP Slurry(반도체 연마재)"), 0.88),
            E("RELATED_PARTY", ("sk",), ("org", "SK엔펄스"), 0.88, "종속기업(CMP Slurry 사업 양도)"),
            E("RELATED_PARTY", ("sk",), ("org", "SK에코플랜트"), 0.88, "종속기업(리뉴어스 등 22개사 매각)"),
        ],
    },

    # ── ISC — 반도체 테스트 소켓 ─────────────────────────────────────
    "81ec70f1a70114ab": {  # 반도체 테스트소켓, Total Test Solution (2025.03)
        "entities": [
            (P, "반도체 테스트 소켓", "반도체 테스트 소켓(Test Socket)"),
            (P, "번인 소켓", "번인 소켓(Burn-in Socket)"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "반도체 테스트 소켓", "반도체 테스트 소켓(Test Socket)"), 0.9),
            E("PRODUCES", ("sk",), ("ent", P, "번인 소켓", "번인 소켓(Burn-in Socket)"), 0.85),
        ],
    },

    "82e9b23064c72638": {  # 반도체 테스트 소켓 (2025.06)
        "entities": [
            (P, "반도체 테스트 소켓", "반도체 테스트 소켓(Test Socket)"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "반도체 테스트 소켓", "반도체 테스트 소켓(Test Socket)"), 0.88),
        ],
    },

    # ── 반도체 웨이퍼 (SK실트론) ─────────────────────────────────────
    "81395c86bd128f54": {  # 반도체 웨이퍼 연구개발 (2025.09)
        "entities": [
            (P, "반도체 웨이퍼", "반도체 웨이퍼(Wafer)"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "반도체 웨이퍼", "반도체 웨이퍼(Wafer)"), 0.9),
        ],
    },

    "d8366c4c2c5e50e3": {  # 반도체 웨이퍼 서버/IoT 고객 (2023.12)
        "entities": [
            (P, "반도체 웨이퍼", "반도체 웨이퍼(Wafer)"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "반도체 웨이퍼", "반도체 웨이퍼(Wafer)"), 0.9),
        ],
    },

    # ── SK에어플러스 — 산업용 가스 ───────────────────────────────────
    "e063af3f7d39885c": {  # 산업용 가스 질소/산소/아르곤/액체탄산, 반도체 모듈 (2025.12)
        "entities": [
            (P, "산업용 가스", "산업용 가스(질소·산소·아르곤·액체탄산)"),
            (P, "반도체 모듈", "반도체 메모리 모듈"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "산업용 가스", "산업용 가스(질소·산소·아르곤·액체탄산)"), 0.9),
            E("PRODUCES", ("sk",), ("ent", P, "반도체 모듈", "반도체 메모리 모듈"), 0.85),
        ],
    },

    "82add5a7aaee30c6": {  # 산업용 가스 반도체/정유/화학/조선 납품 (2026.03)
        "entities": [
            (P, "산업용 가스", "산업용 가스(질소·산소·아르곤·액체탄산)"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "산업용 가스", "산업용 가스(질소·산소·아르곤·액체탄산)"), 0.88),
        ],
    },

    # ── SK이노베이션 — PX 파라자일렌 ──────────────────────────────────
    "8201e817d7b54675": {  # PX 파라자일렌, 아로마틱 (2024.06)
        "entities": [
            (P, "px 파라자일렌", "PX(파라자일렌)"),
            (P, "아로마틱", "아로마틱(BTX)"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "px 파라자일렌", "PX(파라자일렌)"), 0.9),
            E("PRODUCES", ("sk",), ("ent", P, "아로마틱", "아로마틱(BTX)"), 0.85),
        ],
    },

    # ── SK엔무브 — 윤활기유 ──────────────────────────────────────────
    "86ecb07fd3d28ad6": {  # SK엔무브 UCO 원료 매입, 윤활기유 (2025.03)
        "entities": [
            (P, "윤활기유", "윤활기유(Base Oil)"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "윤활기유", "윤활기유(Base Oil)"), 0.88),
            E("RELATED_PARTY", ("sk",), ("org", "SK엔무브"), 0.88, "종속기업(윤활유 사업)"),
        ],
    },

    # ── 윤활기유 Group III — OEM 공급 ─────────────────────────────────
    "8dcbcdb8fe244c93": {  # Group III 기유, 폭스바겐/GM/도요타 납품 (2025.12)
        "entities": [
            (P, "group iii 기유", "Group III 고급 윤활기유"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "group iii 기유", "Group III 고급 윤활기유"), 0.88),
            E("SUPPLIES_TO", ("sk",), ("org", "폭스바겐"), 0.82),
            E("SUPPLIES_TO", ("sk",), ("org", "GM"), 0.82),
            E("SUPPLIES_TO", ("sk",), ("org", "도요타"), 0.82),
        ],
    },

    "8892aa7ff5ad1caa": {  # Group III 기유, 폭스바겐/GM/도요타 (2026.03)
        "entities": [
            (P, "group iii 기유", "Group III 고급 윤활기유"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "group iii 기유", "Group III 고급 윤활기유"), 0.88),
            E("SUPPLIES_TO", ("sk",), ("org", "폭스바겐"), 0.8),
            E("SUPPLIES_TO", ("sk",), ("org", "GM"), 0.8),
            E("SUPPLIES_TO", ("sk",), ("org", "도요타"), 0.8),
        ],
    },

    # ── SK LNG/발전 사업 ────────────────────────────────────────────
    "823fdd839f585beb": {  # LNG 발전사업 (2023.12)
        "entities": [
            (P, "lng 발전", "LNG 발전"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "lng 발전", "LNG 발전"), 0.85),
        ],
    },

    "835d4c797f109378": {  # SK이노베이션 E&S CIC 전력·집단에너지 (2026.03)
        "entities": [
            (P, "lng 발전", "LNG 발전"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "lng 발전", "LNG 발전"), 0.85),
            E("RELATED_PARTY", ("sk",), ("org", "SK이노베이션"), 0.92, "종속기업(E&S 사업 통합)"),
        ],
    },

    # ── 수소 사업 ──────────────────────────────────────────────────
    "e61018767e0d8e3e": {  # 수소 탈탄소 사업 (2025.09)
        "entities": [
            (P, "수소에너지", "수소에너지"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "수소에너지", "수소에너지"), 0.85),
        ],
    },

    # ── SK반도체 플랜트 건설 ────────────────────────────────────────
    "80bf2751f8c6f999": {  # 반도체 플랜트 건설/구축 서비스 (2024.12)
        "entities": [
            (P, "반도체 플랜트", "반도체 플랜트(생산 인프라)"),
        ],
        "edges": [
            E("PRODUCES", ("sk",), ("ent", P, "반도체 플랜트", "반도체 플랜트(생산 인프라)"), 0.85),
        ],
    },

    # ── SK picglobal/ISC PIN 기술 ─────────────────────────────────
    "80d5da4f46b6514e": {  # ISC PIN 접촉 기술, SK picglobal R&D (2025.12)
        "entities": [
            (T, "pin 기술", "PIN 접촉 기술(반도체 소켓)"),
        ],
        "edges": [
            E("USES_TECH", ("sk",), ("ent", T, "pin 기술", "PIN 접촉 기술(반도체 소켓)"), 0.82),
        ],
    },

    # ── SK하이닉스 수처리 임대 ──────────────────────────────────────
    "8342916edd3b5c6c": {  # 클린인더스트리얼리츠 SK하이닉스 수처리센터 임대 (2024.03)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("sk",), ("org", "SK하이닉스"), 0.85, "계열사(수처리센터 임대)"),
        ],
    },

    # ── SK이엔에스/이노베이션 합병 ──────────────────────────────────
    "8255f021492b1b06": {  # SK이엔에스 소멸, SK이노베이션 합병, SKC/SK엔펄스 (2024.06)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("sk",), ("org", "SK이엔에스"), 0.88, "종속기업(→SK이노베이션 합병)"),
            E("RELATED_PARTY", ("sk",), ("org", "SK이노베이션"), 0.92, "종속기업(에너지·화학)"),
            E("RELATED_PARTY", ("sk",), ("org", "SKC"), 0.88, "종속기업(소재사업)"),
            E("RELATED_PARTY", ("sk",), ("org", "SK엔펄스"), 0.85, "종속기업(반도체 소재)"),
        ],
    },

    # ── SK에코플랜트 재생에너지 ─────────────────────────────────────
    "829e3d20e53ff6d5": {  # SK 하이테크사업, SK에코플랜트 환경사업 (2025.06)
        "entities": [],
        "edges": [
            E("RELATED_PARTY", ("sk",), ("org", "SK에코플랜트"), 0.85, "종속기업(환경·건설·에너지)"),
        ],
    },
}


# ── 이 배치 전용 원장 헬퍼 ────────────────────────────────
def ledger_ids() -> set[str]:
    if not LEDGER.exists():
        return set()
    ids = set()
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ids.add(json.loads(line)["chunk_id"])
        except Exception:
            continue
    return ids


def mark(chunk_id: str, n_ent: int, n_edge: int, section_path: str = None, rcept_no: str = None) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "chunk_id": chunk_id, "n_ent": n_ent, "n_edge": n_edge,
        "rcept_no": rcept_no, "section_path": section_path,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _match_and_id(driver, ref):
    """ref 해석: ('sk',) → SK org corp_code 직접, ('org', 이름) → resolve_org,
    ('ent', label, canonical, name) → Product/Technology"""
    if ref[0] == "sk":
        # SK(주) corp_code='00181712' 직접 참조 — needs_er 생성 방지
        return {"kind": "org", "org": SK_ORG}, CORP_CODE
    if ref[0] == "org":
        org = resolve_org(ref[1])
        merge_org_node(driver, org)
        return {"kind": "org", "org": org}, org["id"]
    # ('ent', label, canonical, name)
    _, label, canonical, name = ref
    eid = merge_entity(driver, label, canonical, name)
    return {"kind": "entity", "label": label, "id": eid}, eid


def run():
    rows = get_chunks(WHERE)
    by_id = {r["chunk_id"]: r for r in rows}
    done = ledger_ids()
    print(f"[batch] 청크 {len(rows)}건 (corp {CORP_CODE} text_micro OFFSET 3600), 원장 기처리 {len(done)}건")

    driver = neo4j_driver()
    conn = mariadb_conn()

    n_ent_total = n_edge_total = n_prov_total = 0
    ent_by_label: dict[str, int] = {}
    edge_by_type: dict[str, int] = {}
    processed = 0

    # 1) 추출 결과 있는 청크
    for cid, payload in EXTRACTIONS.items():
        if cid in done:
            continue
        if cid not in by_id:
            print(f"  [warn] {cid} chunk_index에 없음 — 스킵")
            continue
        row = by_id[cid]
        rcept_no = row["rcept_no"]
        n_ent = n_edge = 0

        for label, canonical, name in payload.get("entities", []):
            eid = merge_entity(driver, label, canonical, name)
            add_edge(driver, "hasObject",
                     {"kind": "chunk", "chunk_id": cid},
                     {"kind": "entity", "label": label, "id": eid},
                     chunk_id=cid, rcept_no=rcept_no, confidence=1.0)
            write_provenance(conn, cid, "hasObject", eid, cid, rcept_no, 1.0)
            n_ent += 1
            n_prov_total += 1
            ent_by_label[label] = ent_by_label.get(label, 0) + 1
            edge_by_type["hasObject"] = edge_by_type.get("hasObject", 0) + 1

        for e in payload.get("edges", []):
            rel, frm, to, conf = e["rel"], e["from"], e["to"], e["conf"]
            rtype = e.get("relation_type")
            fm, fid = _match_and_id(driver, frm)
            tm, tid = _match_and_id(driver, to)
            add_edge(driver, rel, fm, tm, chunk_id=cid, rcept_no=rcept_no,
                     confidence=conf, relation_type=rtype)
            write_provenance(conn, fid, rel, tid, cid, rcept_no, conf)
            n_edge += 1
            n_prov_total += 1
            edge_by_type[rel] = edge_by_type.get(rel, 0) + 1

        conn.commit()
        mark(cid, n_ent, n_edge, row["section_path"], rcept_no)
        n_ent_total += n_ent
        n_edge_total += n_edge
        processed += 1

    # 2) 나머지 청크 — 엣지 0으로 처리 표시 (누락 0 보장)
    extracted_ids = set(EXTRACTIONS.keys())
    zero_count = 0
    for r in rows:
        cid = r["chunk_id"]
        if cid in done or cid in extracted_ids:
            continue
        mark(cid, 0, 0, r["section_path"], r["rcept_no"])
        zero_count += 1
    processed += zero_count

    conn.close()
    driver.close()

    print("=== SK(주) 00181712 p2 추출 결과 ===")
    print(f"  이번 실행 처리 청크: {processed}  (추출유 {processed - zero_count}  / 0엣지 {zero_count})")
    print(f"  원장 누적: {len(ledger_ids())} / {len(rows)}")
    print(f"  엔티티 hasObject: {n_ent_total}  타입별: {ent_by_label}")
    print(f"  엣지(hasObject 포함) 총: {n_edge_total + n_ent_total}  타입별: {edge_by_type}")
    print(f"  provenance 행: {n_prov_total}")


if __name__ == "__main__":
    run()
