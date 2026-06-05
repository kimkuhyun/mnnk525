"""Haiku 비정형 추출 프롬프트 (확정본) + 사전필터 + 후처리 훅.

설계: 03_neo4j.md §2-2 (claude 엣지 6종). 환각방어 = 본문 앵커 실재 검증.
파이프라인: 사전필터 → Haiku 추출(표면형) → entity_normalize.canonical(캐논화) → add_edge/merge_entity/write_provenance.
프롬프트는 '발견'만 담당 — 캐논 통일은 후처리(entity_normalize)에서. 그래서 신규 엔티티도 잡힘.

검증 이력: Haiku가 4청크에서 스펙 제외·재무표 정확히 비움 확인. recall 보강:
부품/원자재도 Product, module form factor도 Technology 로 명시.
"""
from __future__ import annotations

# ── 사전필터: 추출에서 제외할 청크 WHERE 절 ────────────────
# 순수 재무수치 표(재무제표 주석 中 관계키워드 없는 것) = fin_metric 영역 → 스킵.
# 특수관계/관계기업/종속기업/사업결합 언급 주석은 보존(RELATED_PARTY/SUPPLIES_TO 후보).
SKIP_WHERE = (
    "NOT ( (section_path LIKE 'III.%주석%' OR section_path LIKE '%재무제표 주석%') "
    "AND NOT (embedding_text LIKE '%특수관계%' OR embedding_text LIKE '%관계기업%' "
    "OR embedding_text LIKE '%종속기업%' OR embedding_text LIKE '%사업결합%') )"
)

# ── 금융기관 노이즈 가드 ──────────────────────────────────
# 차입금·보증·예금·주관 문맥의 은행/보증보험/증권 등은 거래 상대가 아니다 → SUPPLIES_TO/RELATED_PARTY object 부적합.
# (투자조합·펀드·캐피탈·자산운용은 실제 투자 특수관계일 수 있어 제외하지 않음.)
_FINANCE_KW = (
    "은행", "보증보험", "손해보험", "화재해상",
    "증권", "저축은행", "신용보증", "수출입은행",
)


def _is_financial_org(name: str) -> bool:
    return any(k in name for k in _FINANCE_KW)


# ── 추출 프롬프트 ──────────────────────────────────────────
SYSTEM = (
    "너는 한국 기업 공시(DART) 본문에서 지식그래프용 엔티티·관계를 뽑는 추출기다. "
    "본문에 명시적 근거가 있는 것만 추출하고, 추측·일반상식·본문에 없는 것은 금지한다(환각 방어)."
)

PROMPT = """공시 주체(subject) = "{subject}".

## 추출 스키마 (이 6종만)
- entity `Product`: 구체 제품·부품·원자재·서비스명 (예: DRAM, NAND, PCB, HBM, 보험상품, 호텔서비스)
- entity `Technology`: 구체 기술·공정·플랫폼·form factor (예: TLC, EUV, CXL, SOCAMM, AI)
- edge `PRODUCES`: ({subject} → Product/Technology) — 주체가 만들거나 개발·제공
- edge `USES_TECH`: ({subject} → Technology) — 주체가 사용·적용하는 기술
- edge `SUPPLIES_TO`: 실제 공급 방향(공급사 → 수요사). 주체의 주요 매출처/고객사는 `{subject} → 고객사`, 주체의 주요 매입처/공급사는 `공급사 → {subject}`.
- edge `RELATED_PARTY`: ({subject} → 상대회사) — 특수관계/거래 상대, **이름 명시된** 경우만
- edge `hasObject`: (CHUNK → Product/Technology) — 청크가 그 엔티티를 언급(주어는 청크 자리표시자 "CHUNK")

## 규칙
1. 엔티티는 캐논(정규)형. **스펙 수치는 제품/기술이 아님 → 제외**: 용량(96GB), 단수(321단),
   공정노드(1cnm·10나노), 세대수식(6세대), 속도(9.6Gbps). 예: "321단 1Tb TLC"→ TLC 만.
2. 고객사 시스템·타사 제품은 주체 제품이 아님 → 제외.
3. 공급사·고객사·거래상대 **이름이 본문에 없으면**(예: "6개사로부터 공급") SUPPLIES_TO/RELATED_PARTY 만들지 말 것.
4. 순수 재무수치·지분법·계정과목 표는 엔티티·엣지 모두 빈 배열.
5. 제품 vs 기술: 완제품·부품·원자재·서비스=Product, 공정·인터페이스·패키징·플랫폼·form factor=Technology.

## 출력 (JSON만, 설명 금지)
{{"entities":[{{"type":"Product|Technology","name":"..."}}],
  "edges":[{{"subject":"...","predicate":"PRODUCES|USES_TECH|SUPPLIES_TO|RELATED_PARTY|hasObject","object":"..."}}]}}

## 청크 본문
{text}
"""


def build_messages(subject: str, text: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": PROMPT.format(subject=subject, text=text)},
    ]


# ── 후처리: 앵커 검증 + 캐논화 ─────────────────────────────
def verify_and_canonicalize(extracted: dict, chunk_text: str):
    """Haiku 출력 → (캐논 엔티티, 엣지) 로 정제.
    - 앵커 검증: entity name(또는 핵심 토큰)이 chunk_text 에 실재할 때만 채택(환각방어).
    - 캐논화: entity_normalize.canonical 로 표면형→캐논 통일.
    반환: {"entities":[(canon, type)], "edges":[(subj, pred, obj_canon)]}
    """
    from entity_normalize import canonical

    text_low = (chunk_text or "").lower()
    ent_map = {}  # surface → (canon, type)
    out_ent = []
    for e in extracted.get("entities", []):
        nm = (e.get("name") or "").strip()
        typ = e.get("type") or "Product"
        if not nm:
            continue
        if typ not in ("Product", "Technology"):
            continue  # 스키마 외 타입(Organization 등) 버림
        # 앵커: 이름 또는 첫 토큰이 본문에 실재
        head = nm.split()[0].lower() if nm.split() else nm.lower()
        if nm.lower() not in text_low and head not in text_low:
            continue  # 환각 — 버림
        cano = canonical(nm, typ)
        if cano is None:
            continue  # 블록리스트(일반어·조직명) — 버림
        canon, ctyp = cano
        ent_map[nm] = (canon, ctyp)
        out_ent.append((canon, ctyp))

    out_edge = []
    for r in extracted.get("edges", []):
        subj = (r.get("subject") or "").strip()
        pred = (r.get("predicate") or "").strip()
        obj = (r.get("object") or "").strip()
        if pred not in ("PRODUCES", "USES_TECH", "SUPPLIES_TO", "RELATED_PARTY", "hasObject"):
            continue
        # 금융기관(차입·보증 문맥)은 거래/공급 상대가 아님 → 노이즈 드롭
        if pred in ("SUPPLIES_TO", "RELATED_PARTY") and _is_financial_org(obj):
            continue
        # object 가 엔티티면 캐논으로 치환
        if obj in ent_map:
            obj = ent_map[obj][0]
        out_edge.append((subj, pred, obj))
    return {"entities": out_ent, "edges": out_edge}
