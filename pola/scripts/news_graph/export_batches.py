"""뉴스 그래프 추출용 배치 파일 생성 — document_unified(news) → bNNNN.json (기본 10건씩).

회사(corp_code) 단위로 뉴스 본문을 배치 파일로 쪼갠다. 각 배치 = Workflow 에이전트 1개가 처리.

사용:
  uv run python scripts/news_graph/export_batches.py <corp_code> [batch_size]
  예:  uv run python scripts/news_graph/export_batches.py 00164779      # SK하이닉스

출력:
  scripts/news_graph/<corp_code>/bNNNN.json   (배치 파일들)
  + DIR, N 출력 → Workflow 추출 스크립트(extract_workflow.template.js)에 채워 실행
"""
from __future__ import annotations
import json
import shutil
import sys
from pathlib import Path

from polaris.config import mariadb_conn

ROOT = Path(__file__).resolve().parent


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: export_batches.py <corp_code> [batch_size=10]")
    corp = sys.argv[1]
    B = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    cur = mariadb_conn().cursor()
    cur.execute("SELECT doc_id, DATE(ts), title, body FROM document_unified "
                "WHERE source_type='news' AND corp_code=%s ORDER BY ts", (corp,))
    rows = cur.fetchall()
    if not rows:
        raise SystemExit(f"corp_code={corp} 뉴스 없음 — run(크롤) + load(3DB) 먼저 실행")

    outdir = ROOT / corp
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True)

    n = 0
    for i in range(0, len(rows), B):
        batch = [{"doc_id": d, "date": str(dt), "title": t or "", "body": (b or "")[:2000]}
                 for d, dt, t, b in rows[i:i + B]]
        (outdir / f"b{i // B:04d}.json").write_text(
            json.dumps(batch, ensure_ascii=False), encoding="utf-8")
        n += 1

    print(f"corp_code={corp}: {len(rows)} docs → {n} 배치 (배치당 {B}건)")
    print(f"  범위: {rows[0][1]} ~ {rows[-1][1]}")
    print(f"  DIR = {outdir}")
    print(f"  N   = {n}")
    print("→ extract_workflow.template.js 의 DIR/N 을 위 값으로 채워 Workflow 실행")


if __name__ == "__main__":
    main()
