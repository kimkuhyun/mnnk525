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


class CompanyProfile(BaseModel):
    code: str
    name: str
    summary: str | None = None
    finance: list[KV]
    execs: list[Exec]
    subsidiaries: list[Subsidiary]
    products: list[str]
    recentNews: list[NewsItem]


# ── 행보 타임라인 ──
class ActivityItem(BaseModel):
    date: str
    group: str
    predicate: str
    target: str
    evidenceCount: int
    docId: str | None = None


# ── 연관어 ──
class KeywordItem(BaseModel):
    term: str
    freq: int


# ── 감성 추이 ──
class SentimentPoint(BaseModel):
    date: str
    pos: int
    neg: int
    neu: int


# ── 근거 ──
class EvidenceItem(BaseModel):
    docId: str
    title: str
    date: str
    url: str
    publisher: str | None = None
    snippet: str | None = None
