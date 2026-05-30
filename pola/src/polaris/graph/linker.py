"""Entity Linking — LLM 추출 entity → 정형 노드 매칭 (4단계).

흐름:
  Stage 1. alias yaml exact/normalized match (lexicon.Matcher)
  Stage 2. Vector ER — bge-m3 임베딩 vs Qdrant ER 컬렉션
              cos ≥ 0.75 AND (top1 - top2 ≥ 0.05)
  Stage 3. Disambiguation — 시총·문맥 키워드·이전 mention 빈도 (옵션)
  Stage 4. 실패 → unlinked_entities.jsonl (사람 검수 → yaml 보강)

output:
  LinkResult(entity_id, score, stage)  — 성공
  None                                 — unlinked (jsonl 에 기록)

product/technology 도 동일 (사전 우선, 사전 미충족만 vector ER).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from polaris.config import DATA_ROOT
from polaris.graph.common import canonicalize_name
from polaris.graph.lexicon import build_matcher

# Vector ER 임계
# ADR 010 (2026-05-27): default ON. 이전엔 enable_vector=False 가 기본이라
# Stage 1 (yaml exact) 만 동작 → Chunk 엣지 coverage 0.16% 의 주된 원인.
VECTOR_COS_MIN = 0.75
VECTOR_DELTA_MIN = 0.05
# Stage 2b — 임계 약간 완화한 substring/canonical 재시도 (alias 사전 보완용)
VECTOR_COS_MIN_LOOSE = 0.70
VECTOR_DELTA_MIN_LOOSE = 0.03

# 진단 카운터 (singleton — process 종료 시점에 출력)
_LINK_STATS = {
    "stage1_yaml": 0,
    "stage2_vector_strict": 0,
    "stage2_vector_loose": 0,
    "stage3_disamb": 0,
    "unlinked": 0,
    "by_type": {},
}


@dataclass
class LinkResult:
    entity_id: str       # 자연키 (corp_code / product_id / tech_id / person_id)
    entity_type: str     # Organization / Person / Product / Technology / Place
    score: float         # 1.0(사전) | cos similarity(vector) | 0.5+(fallback)
    stage: int           # 1/2/3
    surface: str         # 원본 입력 텍스트
    canonical: str       # 정규화된 형태


def _outdir(run_id: str) -> Path:
    p = DATA_ROOT / "4_dbGoldTest" / "graph_extracts" / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _record_unlinked(out_dir: Path, surface: str, entity_type: str,
                      source_chunk_id: str, reason: str):
    """unlinked_entities.jsonl 에 한 줄 append."""
    record = {
        "surface": surface, "entity_type": entity_type,
        "source_chunk_id": source_chunk_id,
        "canonical": canonicalize_name(surface),
        "reason": reason,
    }
    with (out_dir / "unlinked_entities.jsonl").open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, ensure_ascii=False) + "\n")


class EntityLinker:
    """Stateful linker — matcher 1회 빌드, 캐시 사용.

    사용:
      linker = EntityLinker(run_id="20260525_2308_01")
      r = linker.link("삼성전자", "Organization", source_chunk_id="...")
      if r: print(r.entity_id, r.stage)
    """

    def __init__(self, run_id: str, *, enable_vector: bool = True):
        """ADR 010 — enable_vector default 를 True 로 변경.

        이전 default(False) 는 Stage 1 (yaml exact) 만 동작했고, alias 사전에
        없는 entity 가 모두 unlinked.jsonl 로 떨어져 Chunk 엣지 coverage 가
        0.16% 까지 떨어진 주된 원인. P0 fix 의 일부.
        """
        self.run_id = run_id
        self.out_dir = _outdir(run_id)
        self.matcher = build_matcher(reload=True)
        # cache: (entity_type, canonical) → entity_id
        self._yaml_index = self._build_yaml_index()
        # vector ER (P-3.5b — 이젠 default ON)
        self.enable_vector = enable_vector
        self._vector_searcher = None
        if enable_vector:
            try:
                from polaris.graph.er_index import VectorERSearcher
                self._vector_searcher = VectorERSearcher()
            except Exception as ex:
                # vector ER 의존성 부재 시 Stage1 만으로 동작 (graceful degrade)
                import sys
                print(f"[linker] Vector ER unavailable, falling back to Stage1: {ex}",
                      file=sys.stderr)
                self.enable_vector = False

    def _build_yaml_index(self) -> dict[tuple[str, str], str]:
        """yaml 의 모든 alias → (entity_type, canonical_form) → entity_id."""
        idx: dict[tuple[str, str], str] = {}
        # matcher 의 automaton 은 (entity_type, entity_id, surface) payload 저장
        # 같은 정보를 lookup table 로 구축
        from polaris.graph.lexicon.loader import load_aliases
        for kind in ("organizations", "persons", "products", "technologies", "places"):
            data = load_aliases(kind) or {}
            type_label = {
                "organizations": "Organization",
                "persons": "Person",
                "products": "Product",
                "technologies": "Technology",
                "places": "Place",
            }[kind]
            id_field = {
                "organizations": None,   # key 자체가 corp_code
                "persons": None,
                "products": None,
                "technologies": None,
                "places": None,           # key 자체가 iso_code
            }[kind]
            for entity_key, meta in data.items():
                if not isinstance(meta, dict):
                    continue
                # entity_id 결정
                if kind == "organizations":
                    eid = str(entity_key).zfill(8) if str(entity_key).isdigit() else str(entity_key)
                else:
                    eid = str(entity_key)
                # alias 모음 (canonical/aliases/ticker/kor_name)
                names: list[str] = []
                for k in ("name", "canonical", "kor_name"):
                    if meta.get(k):
                        names.append(meta[k])
                names.extend(meta.get("aliases") or [])
                names.extend(meta.get("ticker") or [])
                ambiguous = set(meta.get("ambiguous_alone") or [])
                for n in names:
                    if not n or n in ambiguous:
                        continue
                    canon = canonicalize_name(n)
                    idx[(type_label, canon)] = eid
                    # 원본 표기도 그대로 매칭 (정규화 차이 흡수)
                    idx[(type_label, n)] = eid
        return idx

    # ────── Stage 1 ──────
    def _stage1_yaml(self, surface: str, entity_type: str) -> Optional[LinkResult]:
        canon = canonicalize_name(surface)
        eid = (self._yaml_index.get((entity_type, canon))
               or self._yaml_index.get((entity_type, surface)))
        if eid:
            return LinkResult(eid, entity_type, 1.0, 1, surface, canon)
        return None

    # ────── Stage 2 (strict) ──────
    def _stage2_vector(self, surface: str, entity_type: str) -> Optional[LinkResult]:
        if not self.enable_vector or not self._vector_searcher:
            return None
        # 현재 Organization 만 ER 인덱스 운영 (회사명 모호성 가장 큼)
        if entity_type != "Organization":
            return None
        results = self._vector_searcher.search(surface, top_k=3)
        if not results:
            return None
        top = results[0]
        if top["score"] < VECTOR_COS_MIN:
            return None
        if len(results) >= 2 and (top["score"] - results[1]["score"]) < VECTOR_DELTA_MIN:
            # 모호 — Stage 2b loose 로 넘김
            return None
        return LinkResult(top["entity_id"], entity_type,
                           float(top["score"]), 2, surface,
                           canonicalize_name(surface))

    # ────── Stage 2b (loose retry) — ADR 010 추가 ──────
    def _stage2_vector_loose(self, surface: str, entity_type: str) -> Optional[LinkResult]:
        """strict 임계(0.75/0.05) 가 빠뜨린 케이스 재시도.

        규칙:
          A. result name 의 canonical 이 query canonical 과 *정확 일치* 면 임계 무시
             (Infineon/Luxshare 같은 영문 회사명 — bge-m3 가 0.65~0.71 만 줘도 정답)
          B. 그 외엔 임계 0.70/0.03 으로 다시 검사
        """
        if not self.enable_vector or not self._vector_searcher:
            return None
        if entity_type != "Organization":
            return None
        results = self._vector_searcher.search(surface, top_k=3)
        if not results:
            return None
        top = results[0]
        # A. canonical exact-match — 임계 무시
        q_canon = canonicalize_name(surface)
        r_canon = canonicalize_name(top.get("name") or "")
        if q_canon and r_canon and q_canon == r_canon and top["score"] >= 0.55:
            return LinkResult(top["entity_id"], entity_type,
                               float(top["score"]), 2, surface, q_canon)
        # B. 임계 검사
        if top["score"] < VECTOR_COS_MIN_LOOSE:
            return None
        if len(results) >= 2 and (top["score"] - results[1]["score"]) < VECTOR_DELTA_MIN_LOOSE:
            return None
        return LinkResult(top["entity_id"], entity_type,
                           float(top["score"]), 2, surface, q_canon)

    # ────── Stage 3 ──────
    def _stage3_disambiguation(self, surface: str, entity_type: str,
                                 context: dict | None) -> Optional[LinkResult]:
        # 시연 단계는 단순 skip — Vector 가 모호하면 unlinked 처리.
        # 향후: context 의 mention frequency, 시총 prior 등 활용.
        return None

    def link(self, surface: str, entity_type: str,
              *, source_chunk_id: str = "",
              context: dict | None = None) -> Optional[LinkResult]:
        """단일 entity 링킹. 실패 시 unlinked_entities.jsonl 에 기록.

        ADR 010: 단계 카운터 노출 (_LINK_STATS) + Stage 2b (loose) 추가.
        """
        if not surface or not entity_type:
            return None
        _LINK_STATS["by_type"][entity_type] = _LINK_STATS["by_type"].get(entity_type, 0) + 1
        # Stage 1
        r = self._stage1_yaml(surface, entity_type)
        if r:
            _LINK_STATS["stage1_yaml"] += 1
            return r
        # Stage 2 (strict)
        r = self._stage2_vector(surface, entity_type)
        if r:
            _LINK_STATS["stage2_vector_strict"] += 1
            return r
        # Stage 2b (loose retry — alias 부재 회사 흡수)
        r = self._stage2_vector_loose(surface, entity_type)
        if r:
            _LINK_STATS["stage2_vector_loose"] += 1
            return r
        # Stage 3
        r = self._stage3_disambiguation(surface, entity_type, context)
        if r:
            _LINK_STATS["stage3_disamb"] += 1
            return r
        # Stage 4 — unlinked
        _LINK_STATS["unlinked"] += 1
        _record_unlinked(self.out_dir, surface, entity_type,
                          source_chunk_id, reason="all_stages_miss")
        return None

    @staticmethod
    def print_stats():
        """진행 후 카운터 출력 — pipeline.py / migration 스크립트에서 호출."""
        import sys
        total = sum(v for k, v in _LINK_STATS.items() if k not in ("by_type",))
        print("\n[linker] stats", file=sys.stderr)
        for k in ("stage1_yaml", "stage2_vector_strict", "stage2_vector_loose",
                  "stage3_disamb", "unlinked"):
            v = _LINK_STATS[k]
            pct = v * 100.0 / max(total, 1)
            print(f"  {k:25s} {v:>6} ({pct:.1f}%)", file=sys.stderr)
        print(f"  total                     {total:>6}", file=sys.stderr)
        print(f"  by_type: {_LINK_STATS['by_type']}", file=sys.stderr)

    def link_batch(self, entities: list[dict],
                    source_chunk_id: str = "") -> list[Optional[LinkResult]]:
        """LLM 추출 entities[{text, type}, ...] → [LinkResult|None, ...]."""
        return [self.link(e.get("text", ""), e.get("type", ""),
                           source_chunk_id=source_chunk_id) for e in entities]
