"""Stage C-2b: text 청크 요약 sidecar 생성.

입력: ___test/2_Chuck/03_chunks/{corp}/text.jsonl
출력: ___test/2_Chuck/02_meta/chunk_summary.jsonl
       {chunk_id, summary, summary_method, summary_version}

설계 의도:
- 요약은 청크 payload 안에 박지 않는다 — sidecar 로 분리.
- 임시(Claude 수동) → 정식(qwen3.5:9b 로컬) 교체 시 sidecar 파일만 갈아끼우면 끝.
  벡터·청크 재생성 0건.
- 적재 단계(Qdrant)에서 chunk_id 로 join → payload 의 chunk_summary 필드에 주입.

표 청크(table_nl)는 NL 변환 자체가 자기설명적이라 요약 생성 안 함 (의도).
"""
from __future__ import annotations
import argparse, json, time
from pathlib import Path

from polaris.chunk.lib.llm_summarize import summarize_chunk
from polaris.chunk.lib.version import PIPELINE_VERSION
from polaris.config import CORPS, CHUNKS_DIR, META_DIR

CHUNKS = CHUNKS_DIR
META = META_DIR
OUT = META / "chunk_summary.jsonl"

SUMMARY_VERSION = "v1"


def iter_text_chunks():
    """모든 corp 의 text.jsonl 을 순차로 yield."""
    for corp in CORPS:
        p = CHUNKS / corp / "text.jsonl"
        if not p.is_file():
            continue
        with p.open(encoding="utf-8") as f:
            for line in f:
                try:
                    yield corp, json.loads(line)
                except Exception:
                    continue


def load_existing(out_path: Path) -> dict[str, dict]:
    """이미 채워진 요약은 보존. chunk_id → row."""
    existing: dict[str, dict] = {}
    if out_path.is_file():
        with out_path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if cid := row.get("chunk_id"):
                    existing[cid] = row
    return existing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="기존 요약(qwen_local_v1·claude_temp 포함) 덮어쓰기")
    ap.add_argument("--pending-only", action="store_true",
                    help="summary_method='pending'·'llm_call_fail' 만 재시도")
    args = ap.parse_args()

    t0 = time.time()
    existing = load_existing(OUT)

    new_rows = []
    stats = {"total": 0, "qwen_ok": 0, "fail": 0, "kept_claude": 0,
             "kept_qwen": 0, "skipped_short": 0}

    for corp, ch in iter_text_chunks():
        stats["total"] += 1
        cid = ch.get("chunk_id")
        if not cid:
            continue
        prev = existing.get(cid)

        # 기존 요약 정책
        if prev and not args.force:
            prev_method = prev.get("summary_method", "")
            # pending/fail 만 재시도 모드
            if args.pending_only and prev_method not in ("pending", "llm_call_fail"):
                new_rows.append(prev)
                if prev_method == "claude_temp":
                    stats["kept_claude"] += 1
                elif prev_method == "qwen_local_v1":
                    stats["kept_qwen"] += 1
                continue
            # 기본: claude_temp 는 보존, qwen_local_v1 도 보존, pending/fail 만 재시도
            if prev_method in ("claude_temp", "qwen_local_v1"):
                new_rows.append(prev)
                if prev_method == "claude_temp":
                    stats["kept_claude"] += 1
                else:
                    stats["kept_qwen"] += 1
                continue

        # LLM 호출
        text = ch.get("embedding_text") or ""
        result = summarize_chunk(text)
        method = result["summary_method"]
        if method == "qwen_local_v1":
            stats["qwen_ok"] += 1
        elif method == "skip_short":
            stats["skipped_short"] += 1
        else:
            stats["fail"] += 1

        new_rows.append({
            "chunk_id": cid,
            "corp_code": corp,
            "summary": result["summary"],
            "summary_method": method,
            "summary_version": SUMMARY_VERSION,
            "pipeline_version": PIPELINE_VERSION,
        })

    # 저장 (chunk_id 순)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    new_rows.sort(key=lambda r: (r.get("corp_code", ""), r.get("chunk_id", "")))
    with OUT.open("w", encoding="utf-8") as f:
        for row in new_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    elapsed = time.time() - t0
    print(f"\n=== Stage C-2b 완료 ({elapsed:.1f}s) ===")
    print(f"  text 청크 총: {stats['total']}")
    print(f"  qwen 신규 OK: {stats['qwen_ok']}")
    print(f"  claude_temp 보존: {stats['kept_claude']}")
    print(f"  qwen 기존 보존: {stats['kept_qwen']}")
    print(f"  fail: {stats['fail']}")
    print(f"  skip(짧음): {stats['skipped_short']}")
    print(f"  저장: {OUT}")

    # manifest
    from polaris.config import DATA_ROOT as _DR
    manifest = _DR / "2_Chuck" / "_manifest.json"
    m = {}
    if manifest.exists():
        try: m = json.loads(manifest.read_text(encoding="utf-8"))
        except: m = {}
    m["stage_c2b"] = {
        "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_sec": elapsed,
        "stats": stats,
        "summary_version": SUMMARY_VERSION,
    }
    manifest.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
