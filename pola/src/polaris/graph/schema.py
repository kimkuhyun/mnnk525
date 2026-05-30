"""의미 그래프 노드·엣지 Pydantic 모델 (10종).

설계 03_스키마_저장소.md §A 차용. 4계층 (schema.org + FIBO + SEM + PROV-O).
- 전역 entity 5: Organization, Person, Product, Technology, Place
- run-scoped 5: Event, Statement, Relation, ExtractionActivity, ChunkRef

격리:
- LLM 추출 노드/엣지는 라벨에 'LLMExtracted' 추가 (extracted_by 필드로도 추적).
- 사전 매칭은 신뢰 1.0, 라벨 면제.

MERGE 키:
- 전역: 단일 자연키 (corp_code, person_id, product_id, ...)
- run-scoped: (자연키, run_id) 복합 UNIQUE
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import ClassVar, Optional

from pydantic import BaseModel, ConfigDict, Field


# ────────── 공통 enum ──────────

class EntityType(str, Enum):
    Organization = "Organization"
    Person = "Person"
    Product = "Product"
    Technology = "Technology"
    Place = "Place"


class RelationType(str, Enum):
    """추출 가능한 관계 — LLM relation extractor enum 과 동일."""
    SUPPLIES_TO = "SUPPLIES_TO"
    COMPETES_WITH = "COMPETES_WITH"
    IS_SUBSIDIARY_OF = "IS_SUBSIDIARY_OF"
    PRODUCES = "PRODUCES"
    USES_TECH = "USES_TECH"
    HAS_CEO = "HAS_CEO"
    MERGED_WITH = "MERGED_WITH"
    INVESTED_IN = "INVESTED_IN"


class ProductCategory(str, Enum):
    memory_hbm = "memory_hbm"
    memory_dram = "memory_dram"
    memory_nand = "memory_nand"
    foundry = "foundry"
    display = "display"
    sensor = "sensor"
    other = "other"


class TechnologyCategory(str, Enum):
    process_lithography = "process_lithography"  # EUV, ArF 등
    process_packaging = "process_packaging"       # CoWoS, MR-MUF 등
    process_transistor = "process_transistor"     # GAA, FinFET 등
    material = "material"                          # 포토레지스트, CMP 슬러리
    equipment = "equipment"                        # TC본더, 노광장비
    standard = "standard"                          # PCIe, HBM3E 표준
    other = "other"


class ExtractorKind(str, Enum):
    """추출기 종류 — extracted_by 필드 값."""
    alias_dict = "alias_dict_v1"             # 사전 매칭 — 신뢰 1.0
    deterministic = "deterministic_rule_v1"  # DART JSON 결정론
    qwen_local = "qwen3.5:9b"                # LLM (현 OLLAMA_LLM_MODEL)


# ────────── 공통 mixin ──────────

class ProvenanceMixin(BaseModel):
    """LLM 추출 노드/엣지 공통 메타 (PROV-O)."""
    model_config = ConfigDict(use_enum_values=True)

    confidence: float = Field(1.0, ge=0.0, le=1.0,
                              description="추출 신뢰도. 사전=1.0, LLM=logit×valid×linking.")
    extracted_by: ExtractorKind = ExtractorKind.deterministic
    source_chunk_id: Optional[str] = Field(None, description="추출 근원 청크 hash16.")
    source_chunk_run_id: Optional[str] = None
    prompt_hash: Optional[str] = Field(None, description="LLM 호출 프롬프트 버전 ID (재현성).")
    pipeline_version: Optional[str] = None
    extracted_at: Optional[str] = Field(None, description="ISO8601 UTC.")


class ValidityMixin(BaseModel):
    """시간성 — Tier 2/3 reification 트리거 중 하나."""
    valid_from: Optional[str] = Field(None, description="ISO date (YYYY-MM-DD).")
    valid_to: Optional[str] = None


class MultiSourceMixin(BaseModel):
    """다중 출처 — Tier 2/3 reification 트리거 중 하나."""
    evidence_count: int = Field(1, ge=1)
    multi_source: bool = False


class GlobalEntityMeta(BaseModel):
    """전역 entity 메타 (run_id 속성 X, audit 만)."""
    first_seen_run_id: Optional[str] = None
    last_updated_run_id: Optional[str] = None
    aliases: list[str] = Field(default_factory=list, description="정규화 시 통합된 표기.")


# ────────── 전역 entity 5 ──────────

class Organization(GlobalEntityMeta, ProvenanceMixin):
    """회사. corp_code 자연키 (DART 8자리, 외부 회사는 'X' + hash7)."""
    MERGE_KEY: ClassVar[str] = "corp_code"
    LABEL: ClassVar[str] = "Organization"

    corp_code: str = Field(..., description="DART 8자리 또는 X<hash7>")
    name: str
    name_canon: Optional[str] = None
    ticker: Optional[str] = None
    ksic: Optional[str] = None
    jurirno: Optional[str] = None
    bizrno: Optional[str] = None
    archived_at: Optional[str] = None  # S-11: 검색 노출 제외 마킹


class Person(GlobalEntityMeta, ProvenanceMixin):
    """인물. person_id = hash16(person, name, birth_ym)."""
    MERGE_KEY: ClassVar[str] = "person_id"
    LABEL: ClassVar[str] = "Person"

    person_id: str
    name: str
    birth_ym: Optional[str] = None
    sexdstn: Optional[str] = None
    role_hint: Optional[str] = None
    main_career: Optional[str] = None


class Product(GlobalEntityMeta, ProvenanceMixin):
    """제품. product_id = hash16(category + canonical_name).
    LLM 추출 시 :LLMExtracted 라벨, 사전 매칭은 면제."""
    MERGE_KEY: ClassVar[str] = "product_id"
    LABEL: ClassVar[str] = "Product"

    product_id: str
    name: str
    canonical: Optional[str] = None
    category: ProductCategory = ProductCategory.other


class Technology(GlobalEntityMeta, ProvenanceMixin):
    """공정·재료·장비·표준. tech_id = hash16(category + canonical_name)."""
    MERGE_KEY: ClassVar[str] = "tech_id"
    LABEL: ClassVar[str] = "Technology"

    tech_id: str
    name: str
    canonical: Optional[str] = None
    category: TechnologyCategory = TechnologyCategory.other
    node_size_nm: Optional[int] = Field(None, description="공정 노드 (3/5/7nm) — process_transistor 만.")


class Place(GlobalEntityMeta):
    """장소. ISO 3166-1 alpha-2 (KR/US/CN/JP/TW). 사전 매칭만, LLM 추출 X."""
    MERGE_KEY: ClassVar[str] = "iso_code"
    LABEL: ClassVar[str] = "Place"

    iso_code: str = Field(..., pattern=r"^[A-Z]{2}$")
    kor_name: str


# ────────── run-scoped 5 ──────────

class RunScopedMeta(BaseModel):
    """run-scoped 노드 메타 (자연키 + run_id 복합 UNIQUE)."""
    run_id: str
    first_seen_run_id: Optional[str] = None
    last_updated_run_id: Optional[str] = None


class Event(RunScopedMeta, ProvenanceMixin, ValidityMixin, MultiSourceMixin):
    """SEM Event — actor + object + time. M&A, 투자, 출시, 정정공시 등.
    event_id = hash16(event_type + actors_sorted + date + source_chunk_id)."""
    MERGE_KEYS: ClassVar[list[str]] = ["event_id", "run_id"]
    LABEL: ClassVar[str] = "Event"

    event_id: str
    event_type: str
    label: str
    date: Optional[str] = None
    corp_code: Optional[str] = Field(None, description="주 actor corp_code.")
    rcept_no: Optional[str] = None
    endpoint: Optional[str] = None


class Statement(RunScopedMeta, ProvenanceMixin, ValidityMixin, MultiSourceMixin):
    """단순 SPO triple. LLM relation 추출 결과 중 시간/actor 단순 케이스.
    statement_id = hash16(subject + predicate + object + source_chunk_id)."""
    MERGE_KEYS: ClassVar[list[str]] = ["statement_id", "run_id"]
    LABEL: ClassVar[str] = "Statement"

    statement_id: str
    subject_id: str  # entity 의 MERGE 키 값 (corp_code, person_id, ...)
    subject_type: EntityType
    predicate: RelationType
    object_id: str
    object_type: EntityType


class Relation(RunScopedMeta, ProvenanceMixin, ValidityMixin, MultiSourceMixin):
    """Tier 2.5 — Statement 대신 더 풍부한 엣지 노드 (valid_from + conf + multi_source).
    rel_id = hash16(type + from_id + to_id + valid_from + source_chunk_id)."""
    MERGE_KEYS: ClassVar[list[str]] = ["rel_id", "run_id"]
    LABEL: ClassVar[str] = "Relation"

    rel_id: str
    type: RelationType
    from_id: str
    from_type: EntityType
    to_id: str
    to_type: EntityType


class ExtractionActivity(RunScopedMeta):
    """PROV-O Activity — LLM 호출 단위. wasGeneratedBy 의 타깃.
    activity_id = hash16(extractor + prompt_hash + run_id)."""
    MERGE_KEYS: ClassVar[list[str]] = ["activity_id", "run_id"]
    LABEL: ClassVar[str] = "ExtractionActivity"

    activity_id: str
    extractor: ExtractorKind
    pipeline_version: str
    prompt_hash: str
    model_temp: float = 0.0
    started_at: str
    ended_at: Optional[str] = None
    chunks_processed: int = 0
    entities_extracted: int = 0
    relations_extracted: int = 0


class ChunkRef(RunScopedMeta):
    """T4 lookup-only Chunk 노드. evidence 1-hop only (Chunk→Chunk 금지)."""
    MERGE_KEYS: ClassVar[list[str]] = ["chunk_id", "run_id"]
    LABEL: ClassVar[str] = "Chunk"

    chunk_id: str
    corp_code: str
    rcept_no: Optional[str] = None
    chunk_type: str  # text_micro/macro/table_nl/news_text/...
    anchor: Optional[str] = Field(None,
        description="page/section/cell — 출처 정밀 매핑용 (B-1 스냅샷 연결).")
    embedding_text_hash: Optional[str] = None
    ingest_status: str = "ready"


# ────────── 엣지 메타 ──────────

class EdgeAttrs(ProvenanceMixin, ValidityMixin):
    """공통 엣지 속성. 모든 LLM 추출 엣지에 부착."""
    run_id: str
    first_seen_run_id: Optional[str] = None
    last_updated_run_id: Optional[str] = None
    evidence_count: int = 1


# ────────── 노드 라벨 ↔ Pydantic 매핑 (Cypher 빌더용) ──────────

NODE_REGISTRY: dict[str, type[BaseModel]] = {
    Organization.LABEL: Organization,
    Person.LABEL: Person,
    Product.LABEL: Product,
    Technology.LABEL: Technology,
    Place.LABEL: Place,
    Event.LABEL: Event,
    Statement.LABEL: Statement,
    Relation.LABEL: Relation,
    ExtractionActivity.LABEL: ExtractionActivity,
    ChunkRef.LABEL: ChunkRef,
}

# 전역 vs run-scoped 분류
GLOBAL_LABELS = {Organization.LABEL, Person.LABEL, Product.LABEL,
                 Technology.LABEL, Place.LABEL}
RUN_SCOPED_LABELS = {Event.LABEL, Statement.LABEL, Relation.LABEL,
                     ExtractionActivity.LABEL, ChunkRef.LABEL}

# Reification 트리거 룰 (4조건 OR) — reifier.py 에서 사용
def should_reify(*, has_validity: bool, has_confidence: bool,
                 evidence_count: int, multi_source: bool) -> int:
    """Tier 1/2/3 결정. 0=Tier1(단순엣지), 2=Tier2(Statement/Relation), 3=Tier3(Event)."""
    triggers = [has_validity, has_confidence, evidence_count > 1, multi_source]
    if not any(triggers):
        return 1
    # Event(Tier3) 는 reifier.py 의 actor·object 분류로 별도 결정.
    return 2
