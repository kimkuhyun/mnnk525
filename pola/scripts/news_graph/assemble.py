"""Workflow 추출 결과(.output JSON) → 정제된 full_<corp>.jsonl.

정제: 자기루프(subject==object)·confidence<=0·빈 주체/대상 관계 제거, doc_id 중복제거.
점검: document_unified(해당 회사) 대비 커버리지(누락 doc) 출력.

사용:
  uv run python scripts/news_graph/assemble.py <workflow_output_path> <corp_code>
  예:  uv run python scripts/news_graph/assemble.py C:\\...\\tasks\\wXXXX.output 00164779

출력:
  data/4_dbGoldTest/news_extracts/full_<corp_code>.jsonl
  → uv run python -m polaris.ingest.news_crawl.graph_load --input full_<corp_code>.jsonl
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

from polaris.config import DATA_ROOT, mariadb_conn


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit("usage: assemble.py <workflow_output_path> <corp_code>")
    src, corp = sys.argv[1], sys.argv[2]

    out = json.load(open(src, encoding="utf-8"))
    res = out.get("result", out)
    docs = res["docs"]
    by = {d["doc_id"]: d for d in docs if d.get("doc_id")}

    kept = drop = 0
    for d in by.values():
        cleaned = []
        for r in d.get("relations", []) or []:
            s, o = r.get("subject"), r.get("object")
            c = float(r.get("confidence", 0) or 0)
            if not s or not o or s == o or c <= 0:
                drop += 1
                continue
            cleaned.append(r)
            kept += 1
        d["relations"] = cleaned

    cur = mariadb_conn().cursor()
    cur.execute("SELECT doc_id FROM document_unified WHERE source_type='news' AND corp_code=%s", (corp,))
    all_ids = {r[0] for r in cur.fetchall()}
    got = set(by)
    missing = all_ids - got

    outdir = DATA_ROOT / "4_dbGoldTest" / "news_extracts"
    outdir.mkdir(parents=True, exist_ok=True)
    p = outdir / f"full_{corp}.jsonl"
    p.write_text("\n".join(json.dumps(by[k], ensure_ascii=False) for k in by), encoding="utf-8")

    ent = sum(len(x["entities"]) for x in by.values())
    print(f"docs {len(by)} / 엔티티 {ent} / 관계 {kept} (정제로 {drop} 제거)")
    print(f"커버리지: 전체 {len(all_ids)} / 추출 {len(got)} / 누락 {len(missing)}")
    if missing:
        print("  누락 doc_id (단건 백필 대상):", list(missing)[:10])
    print(f"저장: {p}")


if __name__ == "__main__":
    main()
