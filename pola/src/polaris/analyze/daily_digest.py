"""일별 뉴스 요약 — document_unified news 를 (corp_code, DATE(ts)) 묶어 Ollama 한국어 2~3문장 요약
→ news_daily_summary.

엔진: 로컬 Ollama qwen3.5:9b (format=json 금지, think=False, num_ctx=8192, temperature=0).
재개 가능: 이미 있는 (corp_code, date) 는 skip. 입력 본문 ~6000자 절단.

실행:  uv run python -m polaris.analyze.daily_digest            # 전체(재개)
       uv run python -m polaris.analyze.daily_digest --limit 10  # 일부(테스트)
"""
from __future__ import annotations

import argparse
from collections import defaultdict

import httpx

from polaris.config import CORP_NAMES, OLLAMA_BASE, mariadb_conn

MODEL = "qwen3.5:9b"
MAX_CHARS = 6000

PROMPT = (
    "다음은 {date} 에 '{corp}' 관련 뉴스 기사 {n}건의 제목과 본문 발췌이다.\n"
    "이 뉴스들을 2~3문장으로 간결하게 한국어로 요약하라. 추가 설명 없이 요약문만 출력하라.\n\n"
    "[기사 모음]\n{text}"
)


def ensure_tables(cur) -> None:
    cur.execute("""CREATE TABLE IF NOT EXISTS news_daily_summary (
        corp_code    VARCHAR(8)  NOT NULL,
        date         DATE        NOT NULL,
        summary      TEXT,
        article_count INT        NOT NULL DEFAULT 0,
        PRIMARY KEY (corp_code, date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")


def summarize(client: httpx.Client, corp_name: str, date_str: str, articles: list[tuple]) -> str:
    """articles: list of (title, body)"""
    parts = []
    total = 0
    for title, body in articles:
        snippet = f"[제목] {title or ''}\n{(body or '')[:500]}"
        if total + len(snippet) > MAX_CHARS:
            break
        parts.append(snippet)
        total += len(snippet)

    text = "\n\n".join(parts)
    prompt = PROMPT.format(
        date=date_str,
        corp=corp_name,
        n=len(articles),
        text=text[:MAX_CHARS],
    )
    r = client.post(f"{OLLAMA_BASE}/api/chat", json={
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "think": False,
        "stream": False,
        "options": {"temperature": 0, "num_ctx": 8192},
    })
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="처리할 (corp,date) 그룹 수 제한")
    args = ap.parse_args()

    NAMES = CORP_NAMES  # config(.env) 단일 소스

    conn = mariadb_conn()
    cur = conn.cursor()
    ensure_tables(cur)
    conn.commit()

    # 이미 처리된 (corp_code, date) 수집
    cur.execute("SELECT corp_code, date FROM news_daily_summary")
    done_set: set[tuple] = set()
    for corp, d in cur.fetchall():
        done_set.add((corp, str(d)))

    # document_unified 에서 news 전체 조회 (corp_code, DATE(ts), title, body)
    cur.execute("""SELECT corp_code, DATE(ts) AS day, title, body
                   FROM document_unified
                   WHERE source_type='news' AND ts IS NOT NULL
                   ORDER BY corp_code, day""")
    rows = cur.fetchall()

    # (corp_code, date_str) → [(title, body), ...]
    groups: dict[tuple, list] = defaultdict(list)
    for corp, day, title, body in rows:
        key = (corp, str(day))
        if key not in done_set:
            groups[key].append((title, body))

    pending = list(groups.items())
    if args.limit:
        pending = pending[: args.limit]

    print(f"[daily_digest] 미처리 그룹 {len(pending)} 개 (모델 {MODEL})")

    processed = 0
    with httpx.Client(timeout=120) as client:
        for (corp, date_str), articles in pending:
            corp_name = NAMES.get(corp, corp)
            try:
                summary = summarize(client, corp_name, date_str, articles)
            except Exception as e:
                print(f"  skip ({corp}, {date_str}): {str(e)[:60]}")
                continue
            cur.execute(
                """INSERT INTO news_daily_summary (corp_code, date, summary, article_count)
                   VALUES (%s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE summary=VALUES(summary),
                                            article_count=VALUES(article_count)""",
                (corp, date_str, summary, len(articles)),
            )
            processed += 1
            if processed % 20 == 0:
                conn.commit()
                print(f"  {processed}/{len(pending)}")

    conn.commit()
    cur.execute("SELECT COUNT(*) FROM news_daily_summary")
    total = cur.fetchone()[0]
    cur.close()
    conn.close()
    print(f"[daily_digest] 처리 {processed} 그룹 → news_daily_summary 누적 {total} 행")


if __name__ == "__main__":
    main()
