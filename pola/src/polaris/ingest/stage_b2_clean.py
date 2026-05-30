"""Stage B-2: LLM 요약 (qwen3.5:9b + 6단 방어).

입력: ___test/2_Chuck/01_filtered/{corp}/body_clean/{rcept_no}.txt
출력: ___test/2_Chuck/02_meta/per_doc/{corp}/{rcept_no}.summary.json (135건)
       + _b2_log.jsonl
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path

from polaris.chunk.lib.llm_summarize import summarize_with_defense

from polaris.config import DATA_ROOT, FILTERED_DIR, META_DIR
CLEAN = FILTERED_DIR
OUT = META_DIR / "per_doc"
LOG = META_DIR / "_b2_log.jsonl"

from polaris.config import CORPS as _ENV_CORPS, CORP_NAMES as _ENV_CORP_NAMES, get_corp_meta
CORPS = list(_ENV_CORPS)
CORP_NAMES = {cc: (_ENV_CORP_NAMES.get(cc) or get_corp_meta(cc).get("corp_name", cc))
              for cc in CORPS}


def main():
    t0 = time.time()
    log_lines = []
    summary = {"llm_pass": 0, "heuristic_fallback": 0, "total": 0,
               "fallback_reasons": {}, "per_corp": {}}

    for corp in CORPS:
        print(f"\n=== {CORP_NAMES[corp]} ({corp}) ===")
        body_dir = CLEAN / corp / "body_clean"
        out_dir = OUT / corp
        out_dir.mkdir(parents=True, exist_ok=True)
        corp_stat = {"llm": 0, "heuristic": 0, "elapsed": 0.0}

        files = sorted(body_dir.glob("*.txt")) if body_dir.is_dir() else []
        for i, body_path in enumerate(files, 1):
            rno = body_path.stem
            # incremental skip — summary.json 이미 있으면 LLM 재호출 X
            existing = out_dir / f"{rno}.summary.json"
            if existing.is_file():
                continue
            t_doc = time.time()
            body = body_path.read_text(encoding="utf-8")
            result = summarize_with_defense(body)
            elapsed = time.time() - t_doc
            corp_stat["elapsed"] += elapsed

            method = result.get("summary_method", "?")
            # llm_verified만 진짜 통과. 그 외(llm_low_match·llm_inconsistent·llm_call_fail·skip_short)는
            # 채택은 했으나 검증 미통과 → fallback_reasons 에 method 자체를 사유로 기록 (unknown 박멸).
            if method == "llm_verified":
                corp_stat["llm"] += 1
                summary["llm_pass"] += 1
            else:
                corp_stat["heuristic"] += 1
                summary["heuristic_fallback"] += 1
                reason = result.get("verification", {}).get("reason") or method or "unknown"
                summary["fallback_reasons"][reason] = summary["fallback_reasons"].get(reason, 0) + 1

            # 저장
            payload = {
                "rcept_no": rno,
                "corp_code": corp,
                **result,
                "elapsed_sec": round(elapsed, 1),
            }
            out_path = out_dir / f"{rno}.summary.json"
            out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                encoding="utf-8")
            log_lines.append({
                "corp": corp, "rcept_no": rno, "method": method,
                "elapsed": round(elapsed, 1),
                "verification": result.get("verification", {}),
            })
            print(f"  [{i:3d}/{len(files)}] {rno} | {method} | {elapsed:.1f}s")

        summary["per_corp"][corp] = corp_stat
        summary["total"] += len(files)
        print(f"  {corp_stat['llm']} LLM / {corp_stat['heuristic']} 휴리스틱 / "
              f"{corp_stat['elapsed']:.0f}s")

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("w", encoding="utf-8") as f:
        for line in log_lines:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    elapsed = time.time() - t0
    print(f"\n=== Stage B-2 완료 ({elapsed:.0f}s) ===")
    print(f"  LLM 통과: {summary['llm_pass']}/{summary['total']} "
          f"({summary['llm_pass']/max(1,summary['total'])*100:.1f}%)")
    print(f"  휴리스틱 fallback: {summary['heuristic_fallback']}")
    print(f"  fallback 사유: {summary['fallback_reasons']}")
    print(f"  로그: {LOG}")

    # manifest
    manifest = DATA_ROOT / "2_Chuck" / "_manifest.json"
    m = {}
    if manifest.exists():
        try: m = json.loads(manifest.read_text(encoding="utf-8"))
        except: m = {}
    m["stage_b2"] = {
        "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_sec": elapsed,
        "summary": summary,
    }
    manifest.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
