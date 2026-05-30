"""의미 그래프 LLM 추출 orchestration — P-3.4.

흐름:
  1. MariaDB chunk_index (active run, ready) 로드
  2. classify_chunk → LLM_PATH 만 필터
  3. (옵션) deterministic 추출 → graph_extracts_deterministic.jsonl
  4. LLM_PATH 청크 순회:
     - llm_entity.call_ollama → entities
     - llm_relation.call_ollama → relations (entities 동봉)
     - jsonl checkpoint append (resume-able)
  5. 통계 출력 (호출 수·평균 ms·validated 비율·에러)

산출 jsonl 위치: data/4_dbGoldTest/graph_extracts/{run_id}/
  - llm_extracts.jsonl  : 청크당 {chunk_id, entities, relations, meta}
  - llm_progress.json   : 마지막 처리 chunk_id (resume marker)

사용:
  polaris graph-extract-semantic --limit 5      # 5개만 (sanity)
  polaris graph-extract-semantic                 # 전체 (LLM_PATH)
  polaris graph-extract-semantic --resume        # 마지막 chunk_id 이후만
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from polaris.config import (
    DATA_ROOT, OLLAMA_BASE, OLLAMA_EMBED_MODEL, OLLAMA_LLM_MODEL,
    mariadb_conn,
)
from polaris.graph.common import get_active_run_id
from polaris.graph.extractors import (
    classify_chunk, ChunkClass, extract_deterministic,
)
from polaris.graph.extractors import llm_entity, llm_relation
from polaris.graph.lexicon import ALIAS_DIR, build_matcher

PIPELINE_VERSION = "polaris-0.3.0+p3.4"


def _outdir(run_id: str) -> Path:
    p = DATA_ROOT / "4_dbGoldTest" / "graph_extracts" / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=Path(__file__).resolve().parent,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def _file_sha1(path: Path) -> str:
    if not path.is_file():
        return ""
    h = hashlib.sha1()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def _lexicon_sha1() -> dict[str, str]:
    """5종 alias yaml SHA1[:16]. 추출 시점 lexicon 스냅샷용."""
    return {kind: _file_sha1(ALIAS_DIR / f"{kind}.yml")
            for kind in ("organizations", "persons", "products",
                          "technologies", "places")}


def _ollama_model_digest(model: str) -> str:
    """Ollama /api/show 로 모델 digest 조회. 실패 시 빈 문자열.

    Ollama 0.24 응답엔 details.digest 가 없고 modelfile FROM 라인의
    `blobs/sha256-<hex>` 가 사실상 모델 digest 역할을 한다. 그걸 파싱한다.
    """
    try:
        import re
        import httpx
        with httpx.Client(timeout=5) as c:
            r = c.post(f"{OLLAMA_BASE}/api/show", json={"name": model})
        if r.status_code != 200:
            return ""
        data = r.json() or {}
        # 신형: details.digest / 구형: top-level digest
        d = (data.get("details") or {}).get("digest") or data.get("digest") or ""
        if d:
            return d[:16]
        # fallback: modelfile FROM ... sha256-<hex>
        mf = data.get("modelfile") or ""
        m = re.search(r"sha256[-:]([0-9a-f]{12,})", mf)
        return m.group(1)[:16] if m else ""
    except Exception:
        return ""


def write_manifest(run_id: str, out: Path) -> Path:
    """추출 시작 시 manifest.json 작성 — 재현성 스냅샷."""
    manifest = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "git_commit": _git_commit(),
        "pipeline_version": PIPELINE_VERSION,
        "model": OLLAMA_LLM_MODEL,
        "model_temperature": 0.0,
        "prompt_hash_entity": llm_entity.prompt_hash(),
        "prompt_hash_relation": llm_relation.prompt_hash(),
        "lexicon_sha1": _lexicon_sha1(),
        "embedding_model": OLLAMA_EMBED_MODEL,
        "embedding_model_digest": _ollama_model_digest(OLLAMA_EMBED_MODEL),
        "llm_model_digest": _ollama_model_digest(OLLAMA_LLM_MODEL),
        "ollama_base": OLLAMA_BASE,
    }
    path = out / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


def _load_chunks(run_id: str) -> list[dict]:
    conn = mariadb_conn(); cur = conn.cursor()
    cur.execute("""
        SELECT chunk_id, chunk_type, embedding_text
        FROM chunk_index
        WHERE run_id = %s AND ingest_status = 'ready'
    """, (run_id,))
    out = [{"chunk_id": cid, "chunk_type": ct, "text": txt or ""}
           for cid, ct, txt in cur.fetchall()]
    cur.close(); conn.close()
    return out


def _resume_marker(out_dir: Path) -> Optional[str]:
    pf = out_dir / "llm_progress.json"
    if pf.is_file():
        try:
            return json.loads(pf.read_text(encoding="utf-8")).get("last_chunk_id")
        except Exception:
            return None
    return None


def _save_marker(out_dir: Path, chunk_id: str):
    (out_dir / "llm_progress.json").write_text(
        json.dumps({"last_chunk_id": chunk_id}, ensure_ascii=False),
        encoding="utf-8",
    )


def run_pipeline(*, limit: Optional[int] = None, resume: bool = False,
                  out_dir: Optional[Path] = None) -> dict:
    run_id = get_active_run_id()
    out = out_dir or _outdir(run_id)
    print(f"[pipeline] run_id={run_id}  out={out}")

    manifest_path = write_manifest(run_id, out)
    print(f"[pipeline] manifest: {manifest_path.name}")

    matcher = build_matcher(reload=True)
    print(f"[pipeline] lexicon stats: {matcher.stats}")

    chunks = _load_chunks(run_id)
    print(f"[pipeline] total chunks: {len(chunks):,}")

    # LLM_PATH 필터링
    llm_targets: list[dict] = []
    for ch in chunks:
        d = classify_chunk(ch["chunk_id"], ch["chunk_type"], ch["text"], matcher)
        if d.klass == ChunkClass.LLM_PATH:
            llm_targets.append(ch)
    llm_targets.sort(key=lambda c: c["chunk_id"])  # 결정론 순서
    print(f"[pipeline] LLM_PATH 청크: {len(llm_targets):,}")

    # Resume
    skip_until: Optional[str] = None
    if resume:
        skip_until = _resume_marker(out)
        if skip_until:
            print(f"[pipeline] resume: {skip_until} 이후 청크부터")

    # Limit
    if limit:
        llm_targets = llm_targets[:limit]
        print(f"[pipeline] --limit {limit} 적용 → {len(llm_targets):,} 청크")

    # 출력 파일 (append mode)
    out_jsonl = out / "llm_extracts.jsonl"

    # 통계
    stats = {
        "processed": 0, "skipped_resume": 0,
        "entities_total": 0, "relations_total": 0,
        "ent_call_ms_sum": 0, "rel_call_ms_sum": 0,
        "errors": 0,
    }

    t0 = time.time()
    started = False
    with out_jsonl.open("a", encoding="utf-8") as fp:
        for i, ch in enumerate(llm_targets, 1):
            cid = ch["chunk_id"]
            # resume skip
            if resume and skip_until and not started:
                if cid <= skip_until:
                    stats["skipped_resume"] += 1
                    continue
                started = True

            text = ch["text"]
            ents, ent_meta = llm_entity.call_ollama(text)
            rels, rel_meta = llm_relation.call_ollama(text, ents)

            record = {
                "chunk_id": cid, "chunk_type": ch["chunk_type"],
                "run_id": run_id,
                "entities": ents, "relations": rels,
                "meta": {
                    "ent": ent_meta, "rel": rel_meta,
                },
            }
            fp.write(json.dumps(record, ensure_ascii=False) + "\n")
            fp.flush()
            _save_marker(out, cid)

            stats["processed"] += 1
            stats["entities_total"] += len(ents)
            stats["relations_total"] += len(rels)
            stats["ent_call_ms_sum"] += ent_meta.get("elapsed_ms", 0)
            stats["rel_call_ms_sum"] += rel_meta.get("elapsed_ms", 0)
            if ent_meta.get("error") or rel_meta.get("error"):
                stats["errors"] += 1

            if i % 10 == 0:
                avg_ms = (stats["ent_call_ms_sum"] + stats["rel_call_ms_sum"]) / max(stats["processed"], 1)
                eta_sec = avg_ms / 1000 * (len(llm_targets) - i)
                print(f"  [{i:>4}/{len(llm_targets)}] {cid} "
                       f"ent={len(ents)} rel={len(rels)} "
                       f"avg_ms={int(avg_ms)} eta={int(eta_sec)}s")

    elapsed = time.time() - t0
    print(f"\n=== LLM 추출 완료 ({elapsed:.0f}s) ===")
    print(f"  processed       : {stats['processed']:,}")
    print(f"  skipped (resume): {stats['skipped_resume']:,}")
    print(f"  entities total  : {stats['entities_total']:,}")
    print(f"  relations total : {stats['relations_total']:,}")
    print(f"  errors          : {stats['errors']:,}")
    if stats["processed"]:
        print(f"  avg ent call ms : {stats['ent_call_ms_sum'] // stats['processed']}")
        print(f"  avg rel call ms : {stats['rel_call_ms_sum'] // stats['processed']}")
    print(f"  output          : {out_jsonl}")
    return stats


def main():
    parser = argparse.ArgumentParser(description="POLARIS 의미 그래프 LLM 추출 (P-3.4)")
    parser.add_argument("--limit", type=int, default=None,
                        help="처리할 청크 수 제한 (sanity 용)")
    parser.add_argument("--resume", action="store_true",
                        help="llm_progress.json 의 마지막 chunk_id 이후만 처리")
    args = parser.parse_args()
    rc = 0
    try:
        stats = run_pipeline(limit=args.limit, resume=args.resume)
        if stats["processed"] == 0 and not args.resume:
            rc = 1
    except KeyboardInterrupt:
        print("\n[pipeline] 사용자 중단 — 진행 상태는 llm_extracts.jsonl + llm_progress.json 에 저장됨")
        rc = 130
    return rc


if __name__ == "__main__":
    sys.exit(main())
