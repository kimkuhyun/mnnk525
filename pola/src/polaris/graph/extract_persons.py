"""Person + EXECUTIVE_OF 추출 — DART exctvSttus (임원 현황).

person_id = hash16(nm + birth_ym) — 같은 인물 dedup (회사 옮겨도 동일 노드)
EXECUTIVE_OF 엣지에 직위/등기여부/상근/담당업무/임기 보존.
"""
from __future__ import annotations

import sys

from polaris.graph.common import (
    GraphSession, get_active_run_id, hash16, iter_dart_raw, iter_rows,
    parse_date_loose, CORPS,
)


def collect(corp_codes: list[str]) -> tuple[list[dict], list[dict]]:
    """exctvSttus raw → (persons, exec_edges).
    rows 는 (corp, rcept) 단위 임원 명단."""
    persons: dict[str, dict] = {}  # person_id → properties
    edges: list[dict] = []
    for cc, doc in iter_dart_raw("exctvSttus", corp_codes):
        for r in iter_rows(doc):
            nm = (r.get("nm") or "").strip()
            birth = (r.get("birth_ym") or "").strip()
            if not nm:
                continue
            pid = hash16("person", nm, birth)
            persons[pid] = {
                "person_id": pid, "name": nm, "birth_ym": birth,
                "sexdstn": r.get("sexdstn", ""),
                "main_career": (r.get("main_career") or "")[:500],
            }
            edges.append({
                "person_id": pid,
                "corp_code": cc,
                "ofcps": (r.get("ofcps") or "").strip(),
                "rgist_exctv_at": r.get("rgist_exctv_at", ""),
                "fte_at": r.get("fte_at", ""),
                "chrg_job": (r.get("chrg_job") or "")[:200],
                "hffc_pd": (r.get("hffc_pd") or "").strip(),
                "tenure_end": parse_date_loose(r.get("tenure_end_on")),
                "rcept_no": r.get("rcept_no", ""),
            })
    return list(persons.values()), edges


def load(persons: list[dict], edges: list[dict], run_id: str) -> None:
    with GraphSession() as gs:
        # Person MERGE — 전역 entity (run_id 메타만)
        BATCH = 500
        for i in range(0, len(persons), BATCH):
            batch = persons[i:i + BATCH]
            for p in batch:
                p["run_id"] = run_id
            gs.s.run("""
            UNWIND $rows AS r
            MERGE (p:Person {person_id: r.person_id})
              ON CREATE SET p.first_seen_run_id = r.run_id
            SET p.name = r.name, p.birth_ym = r.birth_ym,
                p.sexdstn = r.sexdstn, p.main_career = r.main_career,
                p.last_updated_run_id = r.run_id
            """, rows=batch)

        # EXECUTIVE_OF 엣지 (idempotent, run_id audit)
        for i in range(0, len(edges), BATCH):
            batch = edges[i:i + BATCH]
            for e in batch:
                e["run_id"] = run_id
            gs.s.run("""
            UNWIND $rows AS r
            MATCH (p:Person {person_id: r.person_id})
            MATCH (o:Organization {corp_code: r.corp_code})
            MERGE (p)-[e:EXECUTIVE_OF]->(o)
              ON CREATE SET e.first_seen_run_id = r.run_id
            SET e.ofcps = r.ofcps, e.rgist_exctv_at = r.rgist_exctv_at,
                e.fte_at = r.fte_at, e.chrg_job = r.chrg_job,
                e.hffc_pd = r.hffc_pd, e.tenure_end = r.tenure_end,
                e.rcept_no = r.rcept_no, e.run_id = r.run_id,
                e.last_updated_run_id = r.run_id
            """, rows=batch)


def main() -> int:
    run_id = get_active_run_id()
    print(f"[extract_persons] run_id = {run_id}")
    persons, edges = collect(CORPS)
    print(f"[extract_persons] Person 후보 {len(persons)}, EXECUTIVE_OF {len(edges)}")
    if not persons:
        return 0
    load(persons, edges, run_id)
    print(f"[extract_persons] 적재 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
