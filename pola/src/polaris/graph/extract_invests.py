"""INVESTS_IN + IS_SUBSIDIARY 추출 — DART otrCprInvstmntSttus (타법인 출자).

target = invested 회사 (inv_prm). 사전 매칭 시도 → 못 찾으면 신설.
qota_rt ≥ 50% → IS_SUBSIDIARY 엣지 추가.
"""
from __future__ import annotations

import sys

from polaris.graph.common import (
    GraphSession, get_active_run_id, hash16, iter_dart_raw, iter_rows,
    lookup_corp_code_by_name, canonicalize_name,
    parse_rate, parse_amount, parse_date_loose, CORPS,
)


def collect(corp_codes: list[str]) -> tuple[list[dict], list[dict]]:
    """(targets_new, edges)."""
    targets_new: dict[str, dict] = {}
    edges: list[dict] = []
    for cc, doc in iter_dart_raw("otrCprInvstmntSttus", corp_codes):
        for r in iter_rows(doc):
            tgt_name = (r.get("inv_prm") or "").strip()
            if not tgt_name:
                continue
            # target Organization 매칭
            tgt_cc = lookup_corp_code_by_name(tgt_name)
            if not tgt_cc:
                tgt_cc = "X" + hash16("xorg", canonicalize_name(tgt_name))[:7].upper()
                targets_new.setdefault(tgt_cc, {
                    "corp_code": tgt_cc, "name": tgt_name,
                    "name_canon": canonicalize_name(tgt_name),
                    "source": "invest_extract",
                })
            qota = parse_rate(r.get("trmend_blce_qota_rt")
                              or r.get("bsis_blce_qota_rt"))
            amount = parse_amount(r.get("trmend_blce_acntbk_amount")
                                  or r.get("bsis_blce_acntbk_amount"))
            qty = parse_amount(r.get("trmend_blce_qy")
                               or r.get("bsis_blce_qy"))
            edges.append({
                "investor": cc, "target": tgt_cc,
                "purps": (r.get("invstmnt_purps") or "").strip(),
                "qota_rt": qota, "amount": amount, "qty": qty,
                "first_acq": parse_date_loose(r.get("frst_acqs_de")),
                "rcept_no": r.get("rcept_no", ""),
                "is_subsidiary": (qota is not None and qota >= 50.0),
            })
    return list(targets_new.values()), edges


def load(targets_new: list[dict], edges: list[dict], run_id: str) -> None:
    with GraphSession() as gs:
        BATCH = 500
        # 신설 target Organization
        for i in range(0, len(targets_new), BATCH):
            batch = targets_new[i:i + BATCH]
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

        # INVESTS_IN 엣지
        for i in range(0, len(edges), BATCH):
            batch = edges[i:i + BATCH]
            for e in batch:
                e["run_id"] = run_id
            gs.s.run("""
            UNWIND $rows AS r
            MATCH (i:Organization {corp_code: r.investor})
            MATCH (t:Organization {corp_code: r.target})
            MERGE (i)-[v:INVESTS_IN]->(t)
              ON CREATE SET v.first_seen_run_id = r.run_id
            SET v.purps = r.purps, v.qota_rt = r.qota_rt,
                v.amount = r.amount, v.qty = r.qty,
                v.first_acq = r.first_acq, v.rcept_no = r.rcept_no,
                v.run_id = r.run_id, v.last_updated_run_id = r.run_id
            """, rows=batch)

            # IS_SUBSIDIARY (qota_rt ≥ 50%)
            sub_batch = [e for e in batch if e["is_subsidiary"]]
            if sub_batch:
                gs.s.run("""
                UNWIND $rows AS r
                MATCH (i:Organization {corp_code: r.investor})
                MATCH (t:Organization {corp_code: r.target})
                MERGE (t)-[s:IS_SUBSIDIARY_OF]->(i)
                  ON CREATE SET s.first_seen_run_id = r.run_id
                SET s.qota_rt = r.qota_rt, s.rcept_no = r.rcept_no,
                    s.run_id = r.run_id, s.last_updated_run_id = r.run_id
                """, rows=sub_batch)


def main() -> int:
    run_id = get_active_run_id()
    print(f"[extract_invests] run_id = {run_id}")
    targets_new, edges = collect(CORPS)
    print(f"[extract_invests] target 신설 {len(targets_new)}, INVESTS_IN {len(edges)}")
    sub_count = sum(1 for e in edges if e["is_subsidiary"])
    print(f"[extract_invests]   - 자회사 (qota≥50%): {sub_count}")
    if not edges:
        return 0
    load(targets_new, edges, run_id)
    print(f"[extract_invests] 적재 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
