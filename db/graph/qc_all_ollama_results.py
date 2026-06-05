"""Batch QC for Ollama extraction outputs.

Default behavior discovers corp codes that have batch/review/result files under
graph/_auto and writes:
  - graph/_auto/qc_all_summary.csv
  - graph/_auto/qc_all_summary.json
  - graph/_auto/qc_all_suspects.jsonl

This script is read-only for extraction outputs. It does not modify result files
or write to Neo4j/MariaDB.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
from pathlib import Path

from qc_ollama_results import (
    AUTO,
    HIGH_SIGNAL_RE,
    edge_flags,
    iter_jsonl,
    load_batches,
    load_results,
)

DB = Path(__file__).resolve().parent.parent
CORPS_TSV = DB / "extra28" / "corps.tsv"


def discover_codes() -> list[str]:
    codes: set[str] = set()
    for pattern in ("batch_*.json", "review_*.jsonl", "result_*.json"):
        for path in AUTO.glob(pattern):
            m = re.match(r"^(?:batch|review|result)_(\d{8})_", path.name)
            if m:
                codes.add(m.group(1))
    return sorted(codes)


def corp_names() -> dict[str, str]:
    if not CORPS_TSV.exists():
        return {}
    out: dict[str, str] = {}
    with CORPS_TSV.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            code = (row.get("corp_code") or "").strip()
            name = (row.get("name") or "").strip()
            if code and name:
                out[code] = name
    return out


def qc_corp(corp_code: str, name: str = "") -> tuple[dict, list[dict]]:
    batches = load_batches(corp_code)
    results = load_results(corp_code)
    review_files = sorted(AUTO.glob(f"review_{corp_code}_*.jsonl"))

    stats = collections.Counter()
    predicates = collections.Counter()
    reject_reasons = collections.Counter()
    suspects: list[dict] = []

    for review_file in review_files:
        if review_file.stat().st_size == 0:
            suspects.append({
                "corp_code": corp_code,
                "corp_name": name,
                "kind": "empty_review_file",
                "file": review_file.name,
                "reason": "extract may have failed before first chunk",
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
                    "corp_code": corp_code,
                    "corp_name": name,
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
                        "corp_code": corp_code,
                        "corp_name": name,
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
                        "corp_code": corp_code,
                        "corp_name": name,
                        "kind": "edge_manual_check",
                        "chunk_id": cid,
                        "file": review_file.name,
                        "result_file": (results.get(cid or "", {}).get("file")),
                        "flags": flags,
                        "edge": edge,
                        "preview": re.sub(r"\s+", " ", text)[:700],
                    })

    summary = {
        "corp_code": corp_code,
        "corp_name": name,
        "batch_chunks": len(batches),
        "result_chunks": len(results),
        "review_files": len(review_files),
        "chunks": stats["chunks"],
        "clean_edges": stats["clean_edges"],
        "rejected": stats["rejected"],
        "zero_zero": stats["zero_zero"],
        "errors": stats["errors"],
        "suspects": len(suspects),
        "predicates": dict(predicates),
        "reject_reasons": dict(reject_reasons),
    }
    return summary, suspects


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corp_codes", nargs="*", help="corp codes to QC. Defaults to discovered outputs")
    ap.add_argument("--limit", type=int, default=30, help="max suspects to print")
    args = ap.parse_args()

    names = corp_names()
    codes = args.corp_codes or discover_codes()
    if not codes:
        print("No extraction output files found.")
        return 1

    summaries: list[dict] = []
    all_suspects: list[dict] = []
    for code in codes:
        summary, suspects = qc_corp(code, names.get(code, ""))
        summaries.append(summary)
        all_suspects.extend(suspects)

    summary_json = {
        "corp_count": len(summaries),
        "totals": {
            "batch_chunks": sum(s["batch_chunks"] for s in summaries),
            "result_chunks": sum(s["result_chunks"] for s in summaries),
            "chunks": sum(s["chunks"] for s in summaries),
            "clean_edges": sum(s["clean_edges"] for s in summaries),
            "rejected": sum(s["rejected"] for s in summaries),
            "zero_zero": sum(s["zero_zero"] for s in summaries),
            "errors": sum(s["errors"] for s in summaries),
            "suspects": len(all_suspects),
        },
        "companies": summaries,
    }

    json_path = AUTO / "qc_all_summary.json"
    csv_path = AUTO / "qc_all_summary.csv"
    suspects_path = AUTO / "qc_all_suspects.jsonl"

    json_path.write_text(json.dumps(summary_json, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        fields = [
            "corp_code",
            "corp_name",
            "batch_chunks",
            "result_chunks",
            "review_files",
            "chunks",
            "clean_edges",
            "rejected",
            "zero_zero",
            "errors",
            "suspects",
        ]
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in summaries:
            writer.writerow({k: row.get(k) for k in fields})

    with suspects_path.open("w", encoding="utf-8") as fh:
        for item in all_suspects:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(json.dumps(summary_json["totals"], ensure_ascii=False, indent=2))
    print(f"summary csv : {csv_path}")
    print(f"summary json: {json_path}")
    print(f"suspects    : {suspects_path}")
    if all_suspects:
        print("\nTop suspects:")
        for item in all_suspects[: args.limit]:
            print(json.dumps(item, ensure_ascii=False)[:1000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
