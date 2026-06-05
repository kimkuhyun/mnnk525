"""QC report for Ollama extraction review/result files.

Reads graph/_auto/batch_<corp>_*.json, review_<corp>_*.jsonl, result_<corp>_*.json
and writes non-destructive inspection reports:
  - graph/_auto/qc_<corp>_summary.json
  - graph/_auto/qc_<corp>_suspects.jsonl

This script does not modify result files or write to Neo4j/MariaDB.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUTO = HERE / "_auto"

HIGH_SIGNAL_RE = re.compile(
    r"주요\s*(매출처|고객|매입처)|고객사|거래처|매출처|판매처|납품|공급|"
    r"원재료|원부재료|협력사|제품|기술|장비|소재|반도체|HBM|DRAM|NAND|OLED|LCD|"
    r"PCB|FPCB|FPCA|패키징|웨이퍼|특수관계|관계기업|종속기업|계열회사|거래내역"
)
NOISE_RE = re.compile(
    r"은행|Bank|Branch|보증보험|증권|채권자|차입|채무보증|담보|시설자금|운영자금|"
    r"투자조합|펀드|사모|신기술투자|합자회사|공정가치|채무상품|손실충당금",
    re.IGNORECASE,
)
GENERIC_OBJECTS = {
    "기타",
    "기타 관계기업",
    "합계",
    "토지",
    "건물",
    "시설장치",
    "기계장치",
    "공구와기구",
    "차량운반구",
    "스마트폰",
    "태블릿 PC",
}


def compact(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").lower())


def iter_jsonl(path: Path):
    if not path.exists() or path.stat().st_size == 0:
        return
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield line_no, json.loads(line)
            except json.JSONDecodeError as e:
                yield line_no, {"error": f"jsonl_parse_error: {e}"}


def load_batches(corp_code: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in sorted(AUTO.glob(f"batch_{corp_code}_*.json")):
        batch = json.loads(path.read_text(encoding="utf-8"))
        for chunk in batch.get("chunks", []):
            cid = chunk.get("chunk_id")
            if cid:
                out[cid] = {
                    "batch": path.name,
                    "rcept_no": chunk.get("rcept_no"),
                    "text": chunk.get("text") or "",
                }
    return out


def load_results(corp_code: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in sorted(AUTO.glob(f"result_{corp_code}_*.json")):
        try:
            arr = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for item in arr:
            cid = item.get("chunk_id")
            if cid:
                out[cid] = {"file": path.name, **item}
    return out


def edge_flags(edge: dict, text: str) -> list[str]:
    subj = edge.get("subject") or ""
    pred = edge.get("predicate") or ""
    obj = edge.get("object") or ""
    flags: list[str] = []

    if obj in GENERIC_OBJECTS or compact(obj) in {compact(x) for x in GENERIC_OBJECTS}:
        flags.append("generic_or_asset_object")
    if NOISE_RE.search(subj) or NOISE_RE.search(obj) or NOISE_RE.search(text[:800]):
        flags.append("finance_or_investment_noise")
    if pred == "hasObject":
        flags.append("hasObject_manual_check")
    if pred in {"SUPPLIES_TO", "PRODUCES", "USES_TECH"} and "· III." in text[:120]:
        flags.append("business_edge_from_financial_note")
    if pred == "PRODUCES" and obj in {"OLED", "LCD", "스마트폰", "태블릿 PC"}:
        flags.append("application_not_product_check")
    return flags


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corp_code")
    ap.add_argument("--limit", type=int, default=80, help="max suspects to print")
    args = ap.parse_args()

    batches = load_batches(args.corp_code)
    results = load_results(args.corp_code)
    review_files = sorted(AUTO.glob(f"review_{args.corp_code}_*.jsonl"))

    stats = collections.Counter()
    predicates = collections.Counter()
    reject_reasons = collections.Counter()
    suspects: list[dict] = []

    for review_file in review_files:
        if review_file.stat().st_size == 0:
            suspects.append({
                "kind": "empty_review_file",
                "file": review_file.name,
                "reason": "extract may still be running or failed before first chunk",
            })
            continue

        for line_no, review in iter_jsonl(review_file):
            cid = review.get("chunk_id")
            clean_edges = review.get("clean_edges") or []
            rejected = review.get("rejected") or []
            text = (batches.get(cid or "", {}).get("text") or review.get("text_preview") or "")
            stats["chunks"] += 1
            stats["clean_edges"] += len(clean_edges)
            stats["rejected"] += len(rejected)

            if review.get("error"):
                stats["errors"] += 1
                suspects.append({
                    "kind": "model_error",
                    "chunk_id": cid,
                    "file": review_file.name,
                    "line": line_no,
                    "reason": review.get("error"),
                    "preview": re.sub(r"\s+", " ", text)[:500],
                })

            if not clean_edges and not rejected and not review.get("error"):
                stats["zero_zero"] += 1
                if HIGH_SIGNAL_RE.search(text):
                    suspects.append({
                        "kind": "zero_zero_high_signal",
                        "chunk_id": cid,
                        "file": review_file.name,
                        "result_file": (results.get(cid or "", {}).get("file")),
                        "reason": "no edge/reject, but text contains relation keywords",
                        "preview": re.sub(r"\s+", " ", text)[:700],
                    })

            for item in rejected:
                reject_reasons[item.get("reason", "")] += 1

            for edge in clean_edges:
                predicates[edge.get("predicate", "")] += 1
                flags = edge_flags(edge, text)
                if flags:
                    suspects.append({
                        "kind": "edge_manual_check",
                        "chunk_id": cid,
                        "file": review_file.name,
                        "result_file": (results.get(cid or "", {}).get("file")),
                        "flags": flags,
                        "edge": edge,
                        "preview": re.sub(r"\s+", " ", text)[:700],
                    })

    summary = {
        "corp_code": args.corp_code,
        "batch_chunks": len(batches),
        "result_chunks": len(results),
        "review_files": [p.name for p in review_files],
        "stats": dict(stats),
        "predicates": dict(predicates),
        "reject_reasons": dict(reject_reasons),
        "suspects": len(suspects),
    }

    summary_path = AUTO / f"qc_{args.corp_code}_summary.json"
    suspects_path = AUTO / f"qc_{args.corp_code}_suspects.jsonl"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with suspects_path.open("w", encoding="utf-8") as fh:
        for item in suspects:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"summary: {summary_path}")
    print(f"suspects: {suspects_path}")
    if suspects:
        print("\nTop suspects:")
        for item in suspects[: args.limit]:
            print(json.dumps(item, ensure_ascii=False)[:1000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
