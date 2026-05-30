"""Stage B-4: 뉴스 회사 매칭 (3차 하이브리드).

입력: news_raw 테이블 (RDB SSOT). 파일 백업: data/rawData/_common/news/*.json
출력:
  - news_raw.meta UPDATE (matched_corps, rule_hits, llm_hits, method)
  - data/2_Chuck/02_meta/news_matched.jsonl (backward compat)
"""
from __future__ import annotations
import json, sys, time
from collections import Counter

from polaris.chunk.lib.news_matching import build_aho_automaton, match_news_rule, classify_news_llm
from polaris.config import DATA_ROOT, mariadb_conn

OUT = DATA_ROOT / "2_Chuck" / "02_meta" / "news_matched.jsonl"


def _fetch_news_raw() -> list[dict]:
    """news_raw 에서 모든 뉴스 SELECT."""
    conn = mariadb_conn(); cur = conn.cursor()
    cur.execute("""SELECT news_id, url, title, body, publisher, published, meta
                   FROM news_raw ORDER BY news_id""")
    rows = []
    for r in cur.fetchall():
        meta = json.loads(r[6]) if r[6] else {}
        rows.append({
            "news_id": r[0], "url": r[1] or "", "title": r[2] or "",
            "body": r[3] or "", "publisher": r[4] or "",
            "published": str(r[5]) if r[5] else "",
            "meta": meta,
        })
    cur.close(); conn.close()
    return rows


def _update_meta(news_id: str, meta: dict) -> None:
    conn = mariadb_conn(); cur = conn.cursor()
    cur.execute("UPDATE news_raw SET meta=%s WHERE news_id=%s",
                (json.dumps(meta, ensure_ascii=False), news_id))
    conn.commit(); cur.close(); conn.close()


def main():
    t0 = time.time()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    automaton = build_aho_automaton()
    news_list = _fetch_news_raw()
    cached_count = sum(1 for n in news_list if n["meta"].get("method"))
    print(f"뉴스: {len(news_list)}건 (RDB news_raw, 기존 matched cache: {cached_count})")

    rows = []
    stats = Counter()
    llm_calls = 0
    llm_total = 0.0
    cached = 0
    rule_rechecked = 0

    for i, n in enumerate(news_list, 1):
        nid = n["news_id"]
        m = n["meta"] or {}
        needs_rule_recheck = bool(m.get("needs_rule_recheck"))

        # 증분 skip: meta 에 method 있고 rule_recheck 안 필요하면 그대로 사용
        if m.get("method") and not needs_rule_recheck:
            rows.append({
                "news_id": nid, "url": n["url"], "title": n["title"][:200],
                "published": n["published"], "publisher": n["publisher"],
                "matched_corps": m.get("matched_corps", []),
                "rule_hits": m.get("rule_hits", {}),
                "llm_hits": m.get("llm_hits", {}),
                "method": m.get("method"),
            })
            cached += 1
            if m.get("matched_corps"):
                stats["matched"] += 1
                for c in m["matched_corps"]:
                    stats[f"hit_{c}"] += 1
            else:
                stats["unmatched"] += 1
            continue

        text = (n["title"] + " " + n["body"]).strip()
        if not text:
            stats["empty"] += 1
            continue

        # 룰 재실행 (Aho-Corasick = ms 단위, 비용 0)
        rule_hits = match_news_rule(text, automaton)

        if needs_rule_recheck:
            # 신규 회사 추가 → 룰만 재실행, 기존 LLM 결과 보존
            llm_hits = m.get("llm_hits") or {}
            method = m.get("method") or ("rule" if rule_hits else "none")
            # 룰로 새 회사 새로 잡혔으면 method 갱신
            old_rule_hits = m.get("rule_hits") or {}
            if set(rule_hits.keys()) - set(old_rule_hits.keys()):
                method = "rule" if not llm_hits else f"{method}+rule_recheck"
            rule_rechecked += 1
        else:
            method = "rule" if rule_hits else "llm_gate"
            llm_hits = {}
            if not rule_hits:
                ts = time.time()
                r = classify_news_llm(text)
                llm_total += time.time() - ts
                llm_calls += 1
                matched = r.get("matched_corps", [])
                for c in matched:
                    if c != "none":
                        llm_hits[c] = ["LLM_classified"]
                method = "llm" if llm_hits else "none"

        final_hits = {**llm_hits, **rule_hits}
        if final_hits:
            stats["matched"] += 1
            for c in final_hits:
                stats[f"hit_{c}"] += 1
        else:
            stats["unmatched"] += 1

        meta_new = {
            "matched_corps": list(final_hits.keys()),
            "rule_hits": rule_hits,
            "llm_hits": llm_hits,
            "method": method,
        }
        _update_meta(nid, meta_new)

        rows.append({
            "news_id": nid, "url": n["url"], "title": n["title"][:200],
            "published": n["published"], "publisher": n["publisher"],
            **meta_new,
        })

        if i % 100 == 0:
            print(f"  {i}/{len(news_list)} (LLM 호출 {llm_calls}, 평균 {llm_total/max(1,llm_calls):.1f}s)")

    # backward compat: jsonl 작성 (load-news 가 폴백으로 읽을 수 있음)
    with OUT.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    elapsed = time.time() - t0
    print(f"\n=== Stage B-4 완료 ({elapsed:.0f}s) ===")
    print(f"  총 {len(rows)} 뉴스 (증분 cached: {cached}, rule_recheck: {rule_rechecked})")
    print(f"  매칭: {stats['matched']} / 무관: {stats['unmatched']} / 빈본문: {stats['empty']}")
    print(f"  LLM 호출: {llm_calls} (평균 {llm_total/max(1,llm_calls):.1f}s)")
    print(f"  회사별 매칭:")
    for k, n in stats.most_common():
        if k.startswith("hit_"):
            corp = k[4:]
            print(f"    {corp}: {n}")

    manifest = DATA_ROOT / "2_Chuck" / "_manifest.json"
    m = {}
    if manifest.exists():
        try: m = json.loads(manifest.read_text(encoding="utf-8"))
        except: m = {}
    m["stage_b4"] = {
        "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_sec": elapsed,
        "total": len(rows),
        "matched": stats["matched"],
        "unmatched": stats["unmatched"],
        "llm_calls": llm_calls,
        "by_corp": {k[4:]: v for k, v in stats.items() if k.startswith("hit_")},
    }
    manifest.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
