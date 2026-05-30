"""Event 추출 — DART 공시 목록 + DS005 결정공시.

Event 노드:
  event_id = hash16(rcept_no + event_type)
  (event_id, run_id) 복합 UNIQUE

엣지:
  (Event)-[:wasDerivedFrom]->(FilingDocument {rcept_no})
  (Event)-[:hasActor]->(Organization {corp_code})

DS005 결정공시는 보고서 종류가 더 구체적 (인수합병·자기주식·증자감자 등) — event_type 분류.
"""
from __future__ import annotations

import sys

from polaris.graph.common import (
    GraphSession, get_active_run_id, hash16, iter_dart_raw, iter_rows,
    parse_date_loose, CORPS,
)

# DS005 결정공시 endpoint → event_type 매핑 (대표적)
DS005_TYPE = {
    "tsstkAqDecsn": "Acquisition_OwnShares",
    "tsstkDpDecsn": "Disposal_OwnShares",
    "piicDecsn": "CapitalIncrease",  # 유상증자
    "fricDecsn": "CapitalIncrease_FreeCharge",  # 무상증자
    "stkrtbdDecsn": "ConvertibleBond",
    "bnsnDecsn": "Bonus",
    "asitInhDecsn": "AssetTransfer_In",
    "asitTrfDecsn": "AssetTransfer_Out",
    "bsnTrfDecsn": "BusinessTransfer",
    "bsnInhDecsn": "BusinessAcquisition",
    "tgcmpsBsnTrfDecsn": "AffiliateBusinessTransfer",
    "tgcmpsBsnInhDecsn": "AffiliateBusinessAcquisition",
    "mgDecsn": "Merger",
    "dvDecsn": "Division",  # 분할
    "dvmgDecsn": "DivisionMerger",  # 분할합병
    "stkExtrDecsn": "StockExchange",
    "wdCancelDecsn": "Dissolution",
    "ctrCnclsDecsn": "ContractSign",
    "bdRsltDecsn": "BondIssue",
    "exconvIsuRsltDecsn": "ExchangeableBond",
    "ovLstDecsn": "OverseasListing",
    "ovDlstDecsn": "OverseasDelisting",
    "stLstDecsn": "Listing",
    "stDlstDecsn": "Delisting",
    "bnkrptDecsn": "Bankruptcy",
    "lwstLg": "Litigation",
    "lwstSm": "Litigation",
}


def collect(corp_codes: list[str]) -> list[dict]:
    """모든 Event 후보 수집 (DS001 list 일반 공시 제외 — 너무 많음. DS005 결정공시만)."""
    events: dict[str, dict] = {}  # (event_id, corp_code) dedup

    for ep, evt_type in DS005_TYPE.items():
        for cc, doc in iter_dart_raw(ep, corp_codes):
            for r in iter_rows(doc):
                rno = (r.get("rcept_no") or "").strip()
                if not rno:
                    continue
                eid = hash16("event", rno, evt_type)
                if eid in events:
                    continue
                # 결정일 우선, 없으면 rcept_dt
                date = (parse_date_loose(r.get("dd"))
                        or parse_date_loose(r.get("rcept_dt")))
                events[eid] = {
                    "event_id": eid,
                    "event_type": evt_type,
                    "endpoint": ep,
                    "corp_code": cc,
                    "rcept_no": rno,
                    "date": date,
                    "label": (r.get("report_nm") or evt_type)[:200],
                }
    return list(events.values())


def load(events: list[dict], run_id: str) -> None:
    with GraphSession() as gs:
        BATCH = 500
        for i in range(0, len(events), BATCH):
            batch = events[i:i + BATCH]
            for e in batch:
                e["run_id"] = run_id
            gs.s.run("""
            UNWIND $rows AS r
            MERGE (ev:Event {event_id: r.event_id, run_id: r.run_id})
              ON CREATE SET ev.first_seen_run_id = r.run_id
            SET ev.event_type = r.event_type, ev.endpoint = r.endpoint,
                ev.corp_code = r.corp_code, ev.rcept_no = r.rcept_no,
                ev.date = r.date, ev.label = r.label,
                ev.last_updated_run_id = r.run_id
            WITH r, ev
            MATCH (o:Organization {corp_code: r.corp_code})
            MERGE (ev)-[a:hasActor]->(o)
              ON CREATE SET a.first_seen_run_id = r.run_id
            SET a.run_id = r.run_id, a.last_updated_run_id = r.run_id
            """, rows=batch)
            # wasDerivedFrom → FilingDocument (있을 때만)
            gs.s.run("""
            UNWIND $rows AS r
            MATCH (ev:Event {event_id: r.event_id, run_id: r.run_id})
            MATCH (fd:FilingDocument {rcept_no: r.rcept_no})
            MERGE (ev)-[d:wasDerivedFrom]->(fd)
              ON CREATE SET d.first_seen_run_id = r.run_id
            SET d.run_id = r.run_id
            """, rows=batch)


def main() -> int:
    run_id = get_active_run_id()
    print(f"[extract_events] run_id = {run_id}")
    events = collect(CORPS)
    print(f"[extract_events] Event 후보 {len(events)} (DS005 결정공시 {len(DS005_TYPE)} 종)")
    if not events:
        return 0
    load(events, run_id)
    print(f"[extract_events] 적재 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
