"""IS_MAJOR_SHAREHOLDER_OF 추출.

소스:
  - hyslrSttus  : 최대주주 현황 (회사·인물 모두 포함)
  - majorstock : 대량보유 5% (주로 기관·외부 주주)

shareholder 가 회사 → 사전 매칭 후 Organization 노드, 못 찾으면 신설 (보강 X)
shareholder 가 인물 → Person 으로 신설 (이름·관계만)
"""
from __future__ import annotations

import sys

from polaris.graph.common import (
    GraphSession, get_active_run_id, hash16, iter_dart_raw, iter_rows,
    lookup_corp_code_by_name, canonicalize_name, parse_rate, parse_amount,
    CORPS,
)

# 회사로 추정 (이름에 회사형식 또는 끝)
_ORG_HINT = ("주식회사", "(주)", "㈜", "보험", "은행", "투자", "캐피탈",
             "증권", "Co", "Inc", "Corp", "Ltd", "유한", "유한회사", "재단")


def _is_company(name: str) -> bool:
    n = name or ""
    return any(h in n for h in _ORG_HINT)


def collect(corp_codes: list[str]) -> tuple[list[dict], list[dict], list[dict]]:
    """(persons, orgs_new, edges)."""
    persons: dict[str, dict] = {}
    orgs_new: dict[str, dict] = {}  # 사전 매칭 실패한 회사 — corp_code=hash 신설
    edges: list[dict] = []

    # hyslrSttus (최대주주)
    for cc, doc in iter_dart_raw("hyslrSttus", corp_codes):
        for r in iter_rows(doc):
            nm = (r.get("nm") or "").strip()
            if not nm:
                continue
            relate = (r.get("relate") or "").strip()
            qota = parse_rate(r.get("trmend_posesn_stock_qota_rt")
                              or r.get("bsis_posesn_stock_qota_rt"))
            posesn = parse_amount(r.get("trmend_posesn_stock_co")
                                  or r.get("bsis_posesn_stock_co"))
            shr_id, shr_kind = _resolve_shareholder(nm, persons, orgs_new)
            edges.append({
                "shr_id": shr_id, "shr_kind": shr_kind,
                "corp_code": cc, "relate": relate, "qota_rt": qota,
                "posesn_stock_co": posesn, "rcept_no": r.get("rcept_no", ""),
                "src": "hyslrSttus",
            })

    # majorstock (5% 대량보유)
    for cc, doc in iter_dart_raw("majorstock", corp_codes):
        for r in iter_rows(doc):
            nm = (r.get("repror") or "").strip()
            if not nm:
                continue
            qota = parse_rate(r.get("stkrt"))
            posesn = parse_amount(r.get("stkqy"))
            shr_id, shr_kind = _resolve_shareholder(nm, persons, orgs_new)
            edges.append({
                "shr_id": shr_id, "shr_kind": shr_kind,
                "corp_code": cc, "relate": (r.get("report_tp") or "").strip(),
                "qota_rt": qota, "posesn_stock_co": posesn,
                "rcept_no": r.get("rcept_no", ""), "src": "majorstock",
            })

    return list(persons.values()), list(orgs_new.values()), edges


def _resolve_shareholder(nm: str, persons: dict, orgs_new: dict) -> tuple[str, str]:
    """이름 → (id, kind). kind='Person' 또는 'Organization'.
    회사면 corps.json 매칭 시도, 없으면 hash16 corp_code 신설."""
    if _is_company(nm):
        cc = lookup_corp_code_by_name(nm)
        if cc:
            return cc, "Organization"
        # 신설 corp_code = hash16 (8자리 알파숫자 — DART corp_code 와 형식 다름)
        cc_new = "X" + hash16("xorg", canonicalize_name(nm))[:7].upper()
        orgs_new.setdefault(cc_new, {
            "corp_code": cc_new, "name": nm,
            "name_canon": canonicalize_name(nm),
            "source": "shareholder_extract",
        })
        return cc_new, "Organization"
    # 인물
    pid = hash16("person_shr", nm)  # birth_ym 없음
    persons.setdefault(pid, {
        "person_id": pid, "name": nm, "source": "shareholder_extract",
    })
    return pid, "Person"


def load(persons: list[dict], orgs_new: list[dict], edges: list[dict],
         run_id: str) -> None:
    with GraphSession() as gs:
        BATCH = 500
        # Person 신설 (이름만 가진 주주)
        for i in range(0, len(persons), BATCH):
            batch = persons[i:i + BATCH]
            for p in batch:
                p["run_id"] = run_id
            gs.s.run("""
            UNWIND $rows AS r
            MERGE (p:Person {person_id: r.person_id})
              ON CREATE SET p.first_seen_run_id = r.run_id, p.source = r.source
            SET p.name = coalesce(p.name, r.name),
                p.last_updated_run_id = r.run_id
            """, rows=batch)

        # Organization 신설 (사전 매칭 실패한 회사형 주주)
        for i in range(0, len(orgs_new), BATCH):
            batch = orgs_new[i:i + BATCH]
            for o in batch:
                o["run_id"] = run_id
            gs.s.run("""
            UNWIND $rows AS r
            MERGE (o:Organization {corp_code: r.corp_code})
              ON CREATE SET o.first_seen_run_id = r.run_id, o.source = r.source
            SET o.name = coalesce(o.name, r.name),
                o.name_canon = r.name_canon,
                o.last_updated_run_id = r.run_id
            """, rows=batch)

        # IS_MAJOR_SHAREHOLDER_OF 엣지 (kind 별 분기)
        for i in range(0, len(edges), BATCH):
            batch = edges[i:i + BATCH]
            for e in batch:
                e["run_id"] = run_id
            # Person → Organization
            gs.s.run("""
            UNWIND [r IN $rows WHERE r.shr_kind = 'Person'] AS r
            MATCH (p:Person {person_id: r.shr_id})
            MATCH (o:Organization {corp_code: r.corp_code})
            MERGE (p)-[e:IS_MAJOR_SHAREHOLDER_OF]->(o)
              ON CREATE SET e.first_seen_run_id = r.run_id
            SET e.relate = r.relate, e.qota_rt = r.qota_rt,
                e.posesn_stock_co = r.posesn_stock_co,
                e.rcept_no = r.rcept_no, e.src = r.src,
                e.run_id = r.run_id, e.last_updated_run_id = r.run_id
            """, rows=batch)
            # Organization → Organization (회사 주주)
            gs.s.run("""
            UNWIND [r IN $rows WHERE r.shr_kind = 'Organization'] AS r
            MATCH (s:Organization {corp_code: r.shr_id})
            MATCH (o:Organization {corp_code: r.corp_code})
            MERGE (s)-[e:IS_MAJOR_SHAREHOLDER_OF]->(o)
              ON CREATE SET e.first_seen_run_id = r.run_id
            SET e.relate = r.relate, e.qota_rt = r.qota_rt,
                e.posesn_stock_co = r.posesn_stock_co,
                e.rcept_no = r.rcept_no, e.src = r.src,
                e.run_id = r.run_id, e.last_updated_run_id = r.run_id
            """, rows=batch)


def main() -> int:
    run_id = get_active_run_id()
    print(f"[extract_shareholders] run_id = {run_id}")
    persons, orgs_new, edges = collect(CORPS)
    print(f"[extract_shareholders] Person 신설 {len(persons)}, Organization 신설 {len(orgs_new)}, 엣지 {len(edges)}")
    if not edges:
        return 0
    load(persons, orgs_new, edges, run_id)
    print(f"[extract_shareholders] 적재 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
