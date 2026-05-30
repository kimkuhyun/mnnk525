"""Vector Entity Resolution 인덱스 — Organization linker Stage 2.

목표: LLM 추출 회사명 (alias yaml 미매칭) → Neo4j Organization corp_code 매핑.

구성:
- Qdrant 컬렉션 `polaris-org-er` (1024d cosine, in-memory 수준 ~수천 vectors)
- Organization embed_text = "{name} {aliases} {ksic} {summary[:200]}"
- bge-m3 임베딩 (기존 OLLAMA_EMBED_MODEL 재사용)

빌드:
  polaris graph-rebuild-er-index            # 활성 컬렉션 재빌드
  polaris graph-rebuild-er-index --dry-run  # 대상만 출력
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import time
from typing import Optional

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, FieldCondition, Filter, MatchValue,
    PayloadSchemaType, PointStruct, VectorParams,
)

from polaris.config import (
    OLLAMA_BASE, OLLAMA_EMBED_MODEL, QDRANT_HOST, QDRANT_HTTP_PORT,
    neo4j_driver,
)
from polaris.graph.lexicon.loader import load_aliases

COLLECTION = "polaris-org-er"
DIM = 1024
BATCH = 32


def _qdrant() -> QdrantClient:
    return QdrantClient(host=QDRANT_HOST, port=QDRANT_HTTP_PORT, timeout=60)


def _embed_batch(http: httpx.Client, texts: list[str]) -> list[list[float]]:
    r = http.post(f"{OLLAMA_BASE}/api/embed",
                  json={"model": OLLAMA_EMBED_MODEL, "input": texts})
    r.raise_for_status()
    return r.json().get("embeddings", [])


def _build_embed_text(meta: dict) -> str:
    """Organization → ER embed text (name + aliases + ksic + summary)."""
    name = meta.get("name") or ""
    aliases = " ".join(meta.get("aliases") or [])
    tickers = " ".join(meta.get("ticker") or [])
    ksic = meta.get("ksic") or ""
    subs = " ".join(meta.get("subsidiaries") or [])
    summary = meta.get("summary") or ""
    return " ".join([name, aliases, tickers, ksic, subs, summary[:200]]).strip()


def _collect_targets() -> list[dict]:
    """Org 후보 = yaml organizations + Neo4j Organization (보강 entity 포함)."""
    targets: dict[str, dict] = {}

    # 1. yaml organizations.yml (메인 source)
    orgs = load_aliases("organizations") or {}
    for cc, meta in orgs.items():
        if not isinstance(meta, dict):
            continue
        cc8 = str(cc).zfill(8) if str(cc).isdigit() else str(cc)
        targets[cc8] = {
            "corp_code": cc8,
            "name": meta.get("name", cc8),
            "aliases": meta.get("aliases") or [],
            "ticker": meta.get("ticker") or [],
            "subsidiaries": meta.get("subsidiaries") or [],
            "source": "yaml",
        }

    # 2. Neo4j 신규 Organization (그래프 추출에서 만들어진 X 접두) — 이름만 있으면 보강
    drv = neo4j_driver()
    with drv.session() as s:
        for r in s.run("""
            MATCH (o:Organization)
            WHERE o.corp_code IS NOT NULL AND o.name IS NOT NULL
            RETURN o.corp_code AS cc, o.name AS name,
                   coalesce(o.aliases, []) AS aliases,
                   o.ksic AS ksic
        """):
            cc = r["cc"]
            if cc in targets:
                # yaml 우선, ksic 만 보강
                if r["ksic"] and not targets[cc].get("ksic"):
                    targets[cc]["ksic"] = r["ksic"]
                continue
            targets[cc] = {
                "corp_code": cc, "name": r["name"],
                "aliases": list(r["aliases"]) if r["aliases"] else [],
                "ksic": r["ksic"] or "",
                "source": "neo4j_extract",
            }
    drv.close()
    return list(targets.values())


def _point_id(corp_code: str) -> str:
    h = hashlib.md5(("orgER:" + corp_code).encode()).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def rebuild_index(*, dry_run: bool = False) -> dict:
    targets = _collect_targets()
    print(f"[er_index] 대상 Organization: {len(targets)}")
    if dry_run:
        for t in targets[:10]:
            print(f"  {t['corp_code']}: {t['name']} ({t['source']})")
        return {"total": len(targets), "dry_run": True}

    qc = _qdrant()
    # 컬렉션 재생성 (drop + create)
    try:
        qc.delete_collection(COLLECTION)
    except Exception:
        pass
    qc.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=DIM, distance=Distance.COSINE),
    )
    # payload 인덱스 — corp_code 검색용
    try:
        qc.create_payload_index(COLLECTION, "corp_code",
                                  field_schema=PayloadSchemaType.KEYWORD)
    except Exception:
        pass

    t0 = time.time()
    with httpx.Client(timeout=120) as http:
        for i in range(0, len(targets), BATCH):
            batch = targets[i:i + BATCH]
            texts = [_build_embed_text(t) for t in batch]
            embeds = _embed_batch(http, texts)
            points = []
            for t, v in zip(batch, embeds):
                points.append(PointStruct(
                    id=_point_id(t["corp_code"]),
                    vector=v,
                    payload={
                        "corp_code": t["corp_code"],
                        "name": t["name"],
                        "source": t.get("source", ""),
                    },
                ))
            qc.upsert(collection_name=COLLECTION, points=points)
    elapsed = time.time() - t0
    print(f"[er_index] upsert {len(targets)} (elapsed {elapsed:.1f}s)")
    return {"total": len(targets), "elapsed_sec": round(elapsed, 1)}


class VectorERSearcher:
    """Online linker Stage 2 — bge-m3 embed → Qdrant top-k cosine."""

    def __init__(self):
        self.qc = _qdrant()
        self._http = httpx.Client(timeout=60)

    def __del__(self):
        try:
            self._http.close()
        except Exception:
            pass

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """ADR 010 — qdrant_client 1.18+ 에서 .search() 가 제거되어
        AttributeError 가 except 에 묵살되며 *모든 ER 검색이 0건 반환* 하던 버그.
        .query_points() 로 교체. 동일 패턴이 retrieval.py 에도 있었음 (ADR 016)."""
        if not query:
            return []
        r = self._http.post(f"{OLLAMA_BASE}/api/embed",
                            json={"model": OLLAMA_EMBED_MODEL, "input": [query]})
        if r.status_code != 200:
            return []
        vec = (r.json().get("embeddings") or [None])[0]
        if not vec:
            return []
        try:
            res = self.qc.query_points(
                collection_name=COLLECTION,
                query=vec,
                limit=top_k,
                with_payload=True,
            )
            hits = res.points if hasattr(res, "points") else res
        except Exception as ex:
            import sys
            print(f"[er_index] query_points failed: {type(ex).__name__}: {ex}",
                  file=sys.stderr)
            return []
        return [{"entity_id": h.payload.get("corp_code", ""),
                 "name": h.payload.get("name", ""),
                 "score": float(h.score)} for h in hits if h.payload]


def main():
    parser = argparse.ArgumentParser(description="POLARIS Organization ER 인덱스 빌드")
    parser.add_argument("--dry-run", action="store_true", help="대상만 출력")
    args = parser.parse_args()
    rebuild_index(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
