"""감성 분석 — 뉴스 본문의 회사에 대한 긍/부정/중립 → sentiment_daily (썸트렌드식 감성 추이).

엔진: 로컬 Ollama qwen (재현성 — 누구나 로컬, LLM 키 불필요). 기사가 *해당 회사*에 호의적/부정적인지
'논조'를 판단(사전 카운트보다 정확). 구조화 출력(format=json, think=False, num_ctx).
재개 가능: doc_sentiment 에 결과 저장 → 재실행 시 미처리분만. 마지막에 sentiment_daily 집계.

실행:  uv run python -m polaris.analyze.sentiment            # 전체(재개)
       uv run python -m polaris.analyze.sentiment --limit 50  # 일부(테스트)
"""
from __future__ import annotations

import argparse
import json

import httpx

from polaris.config import CORP_NAMES, OLLAMA_BASE, mariadb_conn

MODEL = "qwen3.5:9b"
NAMES = CORP_NAMES  # config(.env) 단일 소스

PROMPT = (
    "다음 뉴스 기사가 '{corp}'에 대해 어떤 논조인지 판단하라.\n"
    "긍정(호재·성과·수혜)=pos, 부정(악재·리스크·소송·부진)=neg, 중립(단순사실·무관)=neu.\n"
    'JSON 한 줄만 출력: {{"sentiment":"pos|neg|neu"}}\n\n'
    "[기사]\n{text}"
)


def ensure_tables(cur) -> None:
    cur.execute("""CREATE TABLE IF NOT EXISTS doc_sentiment (
        doc_id     VARCHAR(32) PRIMARY KEY,
        corp_code  VARCHAR(8),
        label      VARCHAR(4)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    cur.execute("""CREATE TABLE IF NOT EXISTS sentiment_daily (
        corp_code VARCHAR(8) NOT NULL,
        date      DATE        NOT NULL,
        pos INT DEFAULT 0, neg INT DEFAULT 0, neu INT DEFAULT 0,
        PRIMARY KEY (corp_code, date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")


def classify(client: httpx.Client, corp_name: str, text: str) -> str:
    r = client.post(f"{OLLAMA_BASE}/api/chat", json={
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT.format(corp=corp_name, text=text[:1500])}],
        "format": "json",
        "think": False,
        "stream": False,
        "options": {"temperature": 0, "num_ctx": 4096},
    })
    r.raise_for_status()
    obj = json.loads(r.json()["message"]["content"])
    lab = str(obj.get("sentiment", "neu")).lower()
    return lab if lab in ("pos", "neg", "neu") else "neu"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    conn = mariadb_conn()
    cur = conn.cursor()
    ensure_tables(cur)
    conn.commit()

    cur.execute("""SELECT d.doc_id, d.corp_code, d.title, d.body
                   FROM document_unified d
                   LEFT JOIN doc_sentiment s ON s.doc_id=d.doc_id
                   WHERE d.source_type='news' AND s.doc_id IS NULL""")
    rows = cur.fetchall()
    if args.limit:
        rows = rows[:args.limit]
    print(f"[sentiment] 미처리 {len(rows)} 건 (모델 {MODEL})")

    done = 0
    with httpx.Client(timeout=60) as client:
        for doc_id, corp, title, body in rows:
            text = f"{title or ''}\n{body or ''}"
            try:
                lab = classify(client, NAMES.get(corp, "해당 기업"), text)
            except Exception as e:
                print(f"  skip {doc_id}: {str(e)[:60]}")
                continue
            cur.execute("INSERT INTO doc_sentiment (doc_id,corp_code,label) VALUES (%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE label=VALUES(label)", (doc_id, corp, lab))
            done += 1
            if done % 50 == 0:
                conn.commit()
                print(f"  {done}/{len(rows)}")
    conn.commit()

    # 집계 → sentiment_daily
    cur.execute("DELETE FROM sentiment_daily")
    cur.execute("""INSERT INTO sentiment_daily (corp_code, date, pos, neg, neu)
        SELECT d.corp_code, DATE(d.ts),
               SUM(s.label='pos'), SUM(s.label='neg'), SUM(s.label='neu')
        FROM document_unified d JOIN doc_sentiment s ON s.doc_id=d.doc_id
        WHERE d.source_type='news' AND d.ts IS NOT NULL
        GROUP BY d.corp_code, DATE(d.ts)""")
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM sentiment_daily")
    n = cur.fetchone()[0]
    cur.close()
    conn.close()
    print(f"[sentiment] 처리 {done} 건 → sentiment_daily {n} 행 집계 완료")


if __name__ == "__main__":
    main()
