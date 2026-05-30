"""bge-m3 1024d 임베딩 (Ollama HTTP).

입력: ___test/2_Chuck/03_chunks/{corp}/{table_nl,text}.jsonl
출력: ___test/2_Chuck/04_embeddings/{corp}/{chunk_type}.npy   (N×1024 float32)
       + .ids.json   (chunk_id 순서 N개)
       + .meta.json  (모델·차원·norm 통계·생성시각)

설계 05 §5:
- embedding_text 만 입력 (prefix V1, ID 절대 미포함)
- 배치 32, 재시도 3회, 정규화 ON (cosine 준비)
- shape (N, 1024) / dtype float32 / norm = 1.000 ± 0.001 / NaN 0건

idempotent: --resume 옵션으로 부분 재개. --force 로 전체 재생성.
"""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path

import httpx
import numpy as np

from polaris.config import OLLAMA_BASE, OLLAMA_EMBED_MODEL, CORPS, CHUNKS_DIR, DATA_ROOT

CHUNKS = CHUNKS_DIR
EMB = DATA_ROOT / "2_Chuck" / "04_embeddings"

CHUNK_TYPES = ["table_nl", "text"]  # 파일명 기준
VECTOR_SIZE = 1024
BATCH = 32
RETRY = 3
RETRY_WAIT_SEC = 2.0
HTTP_TIMEOUT = 120.0


def fetch_model_digest(model: str = OLLAMA_EMBED_MODEL) -> str:
    """Ollama /api/show 로 모델 digest 조회. 실패 시 빈 문자열.

    재현성용 — `:latest` 태그가 시간 지나며 변경될 수 있어 digest 를 같이 기록한다.
    Ollama 0.24 는 details.digest 가 없어 modelfile FROM ... sha256-<hex> 를 파싱.
    """
    try:
        import re
        with httpx.Client(timeout=5) as c:
            r = c.post(f"{OLLAMA_BASE}/api/show", json={"name": model})
        if r.status_code != 200:
            return ""
        data = r.json() or {}
        d = (data.get("details") or {}).get("digest") or data.get("digest") or ""
        if d:
            return d[:16]
        mf = data.get("modelfile") or ""
        m = re.search(r"sha256[-:]([0-9a-f]{12,})", mf)
        return m.group(1)[:16] if m else ""
    except Exception:
        return ""


def embed_batch(client: httpx.Client, texts: list[str]) -> list[list[float]]:
    """Ollama /api/embed — 배치 1회 호출. 실패 시 재시도."""
    last_err: Exception | None = None
    for attempt in range(RETRY):
        try:
            r = client.post(
                f"{OLLAMA_BASE}/api/embed",
                json={"model": OLLAMA_EMBED_MODEL, "input": texts},
            )
            r.raise_for_status()
            d = r.json()
            embs = d.get("embeddings") or []
            if len(embs) != len(texts):
                raise RuntimeError(f"size mismatch: req={len(texts)} got={len(embs)}")
            return embs
        except Exception as e:
            last_err = e
            time.sleep(RETRY_WAIT_SEC * (attempt + 1))
    raise RuntimeError(f"embed failed after {RETRY} retries: {last_err}")


def normalize(arr: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


def process_file(client: httpx.Client, jsonl: Path, out_npy: Path,
                 out_ids: Path, force: bool) -> dict:
    """단일 jsonl 파일 → npy + ids.json."""
    stats = {"input": str(jsonl.relative_to(DATA_ROOT)), "n": 0, "elapsed": 0, "norm_min": 0,
             "norm_max": 0, "nan": 0}
    if not jsonl.is_file():
        stats["status"] = "no_input"
        return stats
    if out_npy.is_file() and out_ids.is_file() and not force:
        # resume: 이미 있으면 skip + 검증
        arr = np.load(out_npy)
        ids = json.loads(out_ids.read_text(encoding="utf-8"))
        stats.update({"status": "skipped_existing", "n": len(ids),
                      "shape": list(arr.shape)})
        return stats

    # 입력 로드
    texts: list[str] = []
    ids: list[str] = []
    with jsonl.open(encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            t = r.get("embedding_text") or ""
            cid = r.get("chunk_id")
            if not cid or not t.strip():
                continue
            ids.append(cid)
            texts.append(t)
    n = len(texts)
    if n == 0:
        stats["status"] = "empty_input"
        return stats

    print(f"  {jsonl.relative_to(DATA_ROOT)}: {n} 청크 → 임베딩 시작 (batch={BATCH})")
    t0 = time.time()
    out_arr = np.zeros((n, VECTOR_SIZE), dtype=np.float32)
    for i in range(0, n, BATCH):
        chunk_texts = texts[i:i + BATCH]
        embs = embed_batch(client, chunk_texts)
        out_arr[i:i + len(embs)] = np.array(embs, dtype=np.float32)
        if (i // BATCH) % 20 == 0:
            print(f"    {i + len(embs)}/{n} 완료 ({(time.time()-t0):.1f}s)")

    # 정규화 + 검증
    out_arr = normalize(out_arr)
    norms = np.linalg.norm(out_arr, axis=1)
    nan_count = int(np.isnan(out_arr).sum())

    out_npy.parent.mkdir(parents=True, exist_ok=True)
    np.save(out_npy, out_arr)
    out_ids.write_text(json.dumps(ids, ensure_ascii=False), encoding="utf-8")

    stats.update({
        "status": "ok", "n": n, "elapsed": round(time.time() - t0, 1),
        "shape": list(out_arr.shape),
        "norm_min": round(float(norms.min()), 6),
        "norm_max": round(float(norms.max()), 6),
        "nan": nan_count,
    })
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="기존 npy 무시·재생성")
    ap.add_argument("--only-corp", help="특정 corp만 (예: 00118804)")
    ap.add_argument("--only-type", help="특정 type만 (예: text)")
    args = ap.parse_args()

    t0 = time.time()
    EMB.mkdir(parents=True, exist_ok=True)
    overall = []
    targets_corp = [args.only_corp] if args.only_corp else CORPS
    targets_type = [args.only_type] if args.only_type else CHUNK_TYPES

    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        for corp in targets_corp:
            print(f"\n=== {corp} ===")
            for chunk_type in targets_type:
                jsonl = CHUNKS / corp / f"{chunk_type}.jsonl"
                out_npy = EMB / corp / f"{chunk_type}.npy"
                out_ids = EMB / corp / f"{chunk_type}.ids.json"
                stats = process_file(client, jsonl, out_npy, out_ids, args.force)
                overall.append({"corp": corp, "type": chunk_type, **stats})
                if stats.get("status") == "ok":
                    print(f"    OK shape={stats['shape']} norm=[{stats['norm_min']}, {stats['norm_max']}] nan={stats['nan']}")
                elif stats.get("status") == "skipped_existing":
                    print(f"    SKIP existing (n={stats['n']})")
                else:
                    print(f"    {stats.get('status','?')}")

    # 종합 meta
    total_n = sum(s.get("n", 0) for s in overall if s.get("status") in ("ok", "skipped_existing"))
    total_nan = sum(s.get("nan", 0) for s in overall if s.get("status") == "ok")
    elapsed = time.time() - t0
    meta = {
        "model": OLLAMA_EMBED_MODEL,
        "model_digest": fetch_model_digest(OLLAMA_EMBED_MODEL),
        "vector_size": VECTOR_SIZE,
        "batch": BATCH,
        "normalized": True,
        "files": overall,
        "total_chunks_embedded": total_n,
        "total_nan": total_nan,
        "elapsed_sec": round(elapsed, 1),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    meta_path = EMB / "_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== Embedding 완료 ({elapsed:.1f}s) ===")
    print(f"  총 청크: {total_n}")
    print(f"  NaN: {total_nan}")
    print(f"  meta: {meta_path.relative_to(DATA_ROOT)}")
    return 0 if total_nan == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
