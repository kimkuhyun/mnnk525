"""API 응답 모델 (프론트 src/types.ts 미러). FastAPI 가 /docs 스키마 자동 생성."""
from __future__ import annotations

from pydantic import BaseModel


# ── 관계지도 ──
class GraphNode(BaseModel):
    id: str
    name: str
    seed: bool = False  # 조회한 중심 회사만 True
    degree: int = 1
    group: str | None = None  # 중심과의 대표 관계그룹 → 노드 색
    logo: str | None = None  # 로고 이미지 URL (있으면 노드 이미지, 없으면 라벨)
    kind: str = "org"  # 'seed'|'org'|'news_entity'|'person'|'product'|'meta'
    count: int | None = None  # meta 노드일 때 접힌 멤버 수, 아니면 None


class GraphLink(BaseModel):
    source: str
    target: str
    group: str
    weight: float
    directed: bool = False


class GraphData(BaseModel):
    nodes: list[GraphNode]
    links: list[GraphLink]


# ── 트렌드(대시보드) ──
class MentionPoint(BaseModel):
    date: str
    count: int


class RelationTopItem(BaseModel):
    group: str
    target: str
    weight: float


class TrendData(BaseModel):
    mentions: list[MentionPoint]
    relationTop: list[RelationTopItem]
    sentiment: None = None  # 향후
    keywords: None = None  # 향후


# ── 회사 프로파일 ──
class KV(BaseModel):
    label: str
    value: str


class Exec(BaseModel):
    name: str
    position: str | None = None


class Subsidiary(BaseModel):
    name: str
    stake: float | None = None


class NewsItem(BaseModel):
    docId: str
    title: str
    date: str
    url: str
    publisher: str | None = None


class Shareholder(BaseModel):
    name: str
    stake: float | None = None


class StockSummary(BaseModel):
    lastClose: float
    changePct: float | None = None
    asOf: str
    spark: list[float] = []


class DisputeItem(BaseModel):
    target: str
    evidenceCount: int


class CompanyProfile(BaseModel):
    code: str
    name: str
    summary: str | None = None
    finance: list[KV]
    execs: list[Exec]
    subsidiaries: list[Subsidiary]
    products: list[str]
    recentNews: list[NewsItem]
    shareholders: list[Shareholder] = []
    stock: StockSummary | None = None
    overview: list[KV] = []
    disputes: list[DisputeItem] = []


# ── 행보 타임라인 ──
class ActivityItem(BaseModel):
    date: str
    group: str
    predicate: str
    target: str
    evidenceCount: int
    docId: str | None = None


# ── 감성 추이 ──
class SentimentPoint(BaseModel):
    date: str
    pos: int
    neg: int
    neu: int


# ── 노드 상세 (클릭 드릴다운) ──
class NodeRelation(BaseModel):
    group: str
    predicate: str
    target: str
    evidenceCount: int
    directed: bool
    source: str = "news"          # 'news'|'dart'


class NodeDetail(BaseModel):
    id: str
    name: str
    kind: str
    isSeed: bool
    relations: list[NodeRelation]
    evidence: list["EvidenceItem"]
    profile: CompanyProfile | None = None


# ── 근거 ──
class EvidenceItem(BaseModel):
    docId: str
    title: str
    date: str
    url: str
    publisher: str | None = None
    snippet: str | None = None


# ── 신규 카드 API ──
class StockPoint(BaseModel):
    date: str
    close: float
    changePct: float | None = None
    volume: int | None = None


class RelationTop(BaseModel):
    nodeId: str
    target: str
    group: str
    predicate: str
    evidenceCount: int


class DailyDigestItem(BaseModel):
    date: str
    summary: str
    articleCount: int
    headlines: list[NewsItem]


# ── 신규 엔드포인트 모델 ──
class FinancialPoint(BaseModel):
    indicator: str
    year: int
    value: float
    fsDiv: str
    period: str = "FY"            # 'FY'|'1Q'|'2Q'|'3Q'|'4Q'


class OwnershipItem(BaseModel):
    name: str
    stake: float | None = None
    kind: str  # 'subsidiary'|'shareholder'


class MacroPoint(BaseModel):
    name: str
    value: str
    unit: str | None = None
    asOf: str | None = None
    source: str | None = None


# ── 브리핑 ──
class DisclosureItem(BaseModel):
    date: str
    docType: str
    title: str
    summary: str | None = None
    rcept: str | None = None


class BriefingData(BaseModel):
    date: str | None = None
    summary: str | None = None
    articleCount: int
    headlines: list[NewsItem]
    disclosures: list[DisclosureItem]


# ── 관계 변화 감지 (GET /changes/{corp}?days=60) ──
class ChangeItem(BaseModel):
    group: str
    predicate: str
    target: str
    status: str  # 'new'|'dropped'
    date: str
    evidenceCount: int
    targetId: str = ""            # 상대 노드 id (BE가 항상 채움)


class ChangesData(BaseModel):
    newItems: list[ChangeItem]
    dropped: list[ChangeItem]


# ── 노드 근거 드릴다운 (GET /api/node-evidence/{corp}/{node}) ──
class EvidenceDoc(BaseModel):
    docId: str
    docType: str  # 'news'|'disclosure'
    title: str
    date: str
    url: str
    publisher: str | None = None
    snippet: str


class EdgeEvidence(BaseModel):
    group: str
    predicate: str
    directed: bool
    evidenceCount: int
    firstDate: str
    lastDate: str
    docs: list[EvidenceDoc]
    source: str = "news"          # 'news'|'dart'
    stake: float | None = None
    purpose: str | None = None
    amount: str | None = None
    firstAcq: str | None = None


class NodeEvidence(BaseModel):
    id: str
    name: str
    kind: str
    edges: list[EdgeEvidence]


# ── IR 보고서 ──
class IrReport(BaseModel):
    rceptNo: str
    corpCode: str
    docType: str
    date: str
    title: str
    summary: str
    source: str  # 'dart'|'news' 등
