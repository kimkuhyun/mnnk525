"""BusinessGroup + AFFILIATED_WITH 추출 — 공정위 FTC 대규모기업집단.

소스:
  - appnGroupSttusList     : 그룹 메타 (unityGrupCode, smerNm, repreCmpny, 계열사 수)
  - affiliationCompSttusList : 그룹별 계열사 명단 (jurirno/bizrno → corp_code 매칭)

자연키:
  BusinessGroup.unityGrupCode (전역 UNIQUE)
  계열사 매칭: jurirno → corp_code (corps.json), 실패 시 hash16 신설.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

from polaris.graph.common import (
    GraphSession, get_active_run_id, hash16, canonicalize_name,
    lookup_corp_code_by_jurirno, lookup_corp_code_by_name,
)
from polaris.config import DATA_ROOT

FTC_DIR = DATA_ROOT / "rawData" / "_common" / "ftc"

# 6 종 파일명 패턴 (chunk/ftc.py 와 동일)
_FNAME_PATTERNS = [
    (re.compile(r"^([a-zA-Z]+)__(\d{4})_([A-Z][0-9]{6,7})_p(\d+)\.xml$"),
     lambda m: (m.group(1), m.group(2), m.group(3))),
    (re.compile(r"^([a-zA-Z]+)__(\d{4})_p(\d+)\.xml$"),
     lambda m: (m.group(1), m.group(2), None)),
    (re.compile(r"^([a-zA-Z]+)__(\d{6})_([0-9]{13})_p(\d+)\.xml$"),
     lambda m: (m.group(1), m.group(2)[:4], m.group(3))),
    (re.compile(r"^([a-zA-Z]+)__(\d{6})_p(\d+)\.xml$"),
     lambda m: (m.group(1), m.group(2)[:4], None)),
    (re.compile(r"^([a-zA-Z]+)__([A-Z][0-9]{6,7})_p(\d+)\.xml$"),
     lambda m: (m.group(1), None, m.group(2))),
]


def _parse_fname(name: str):
    for rgx, fn in _FNAME_PATTERNS:
        m = rgx.match(name)
        if m: return fn(m)
    return None


def _parse_xml(path: Path) -> list[dict]:
    try:
        tree = ET.parse(path)
    except Exception:
        return []
    rows = []
    for child in tree.getroot():
        if child.tag in ("numOfRows", "pageNo", "resultCode",
                          "resultMsg", "totalCount"):
            continue
        row = {sub.tag: (sub.text or "").strip() for sub in child}
        if row:
            rows.append(row)
    return rows


def collect() -> tuple[list[dict], list[dict], list[dict]]:
    """(groups, orgs_new, edges)."""
    groups: dict[str, dict] = {}
    orgs_new: dict[str, dict] = {}
    edges: list[dict] = []  # (corp_code, unityGrupCode, year)

    # 1) 그룹 메타 (appnGroupSttusList — year_only, gid 없음)
    base = FTC_DIR / "appnGroupSttusList"
    if base.is_dir():
        for xf in sorted(base.glob("*.xml")):
            parsed = _parse_fname(xf.name)
            if not parsed:
                continue
            _, year, _ = parsed
            for r in _parse_xml(xf):
                gid = r.get("unityGrupCode", "").strip()
                if not gid:
                    continue
                groups[gid] = {
                    "unityGrupCode": gid,
                    "name": r.get("unityGrupNm", ""),
                    "smer_nm": r.get("smerNm", ""),
                    "repre_cmpny": r.get("repreCmpny", ""),
                    "sum_cmpny_co": r.get("sumCmpnyCo", ""),
                    "entrprs_cl": r.get("entrprsCl", ""),
                    "year": int(year) if year and year.isdigit() else None,
                }

    # 2) 계열사 명단 (affiliationCompSttusList — year_group)
    base = FTC_DIR / "affiliationCompSttusList"
    if base.is_dir():
        for xf in sorted(base.glob("*.xml")):
            parsed = _parse_fname(xf.name)
            if not parsed:
                continue
            _, year, gid = parsed
            if not gid:
                continue
            for r in _parse_xml(xf):
                jur = (r.get("jurirno") or "").strip()
                nm = (r.get("entrprsNm") or "").strip()
                if not nm:
                    continue
                # corp_code 매칭: jurirno 우선, 없으면 이름
                cc = (lookup_corp_code_by_jurirno(jur) if jur else None) \
                     or lookup_corp_code_by_name(nm)
                if not cc:
                    cc = "X" + hash16("xorg", canonicalize_name(nm), jur or "")[:7].upper()
                    orgs_new.setdefault(cc, {
                        "corp_code": cc, "name": nm,
                        "name_canon": canonicalize_name(nm),
                        "jurirno": jur, "bizrno": (r.get("bizrno") or "").strip(),
                        "source": "ftc_affiliation",
                    })
                edges.append({
                    "corp_code": cc,
                    "unityGrupCode": gid,
                    "year": int(year) if year and year.isdigit() else None,
                    "induty_nm": r.get("indutyNm", ""),
                    "induty_code": r.get("indutyCode", ""),
                })

    return list(groups.values()), list(orgs_new.values()), edges


def load(groups: list[dict], orgs_new: list[dict], edges: list[dict],
         run_id: str) -> None:
    with GraphSession() as gs:
        BATCH = 500
        # BusinessGroup MERGE
        for i in range(0, len(groups), BATCH):
            batch = groups[i:i + BATCH]
            for g in batch:
                g["run_id"] = run_id
            gs.s.run("""
            UNWIND $rows AS r
            MERGE (bg:BusinessGroup {unityGrupCode: r.unityGrupCode})
              ON CREATE SET bg.first_seen_run_id = r.run_id
            SET bg.name = r.name, bg.smer_nm = r.smer_nm,
                bg.repre_cmpny = r.repre_cmpny,
                bg.sum_cmpny_co = r.sum_cmpny_co,
                bg.entrprs_cl = r.entrprs_cl, bg.year = r.year,
                bg.last_updated_run_id = r.run_id
            """, rows=batch)

        # 신설 Organization
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
                o.jurirno = coalesce(o.jurirno, r.jurirno),
                o.bizrno = coalesce(o.bizrno, r.bizrno),
                o.last_updated_run_id = r.run_id
            """, rows=batch)

        # AFFILIATED_WITH 엣지
        for i in range(0, len(edges), BATCH):
            batch = edges[i:i + BATCH]
            for e in batch:
                e["run_id"] = run_id
            gs.s.run("""
            UNWIND $rows AS r
            MATCH (o:Organization {corp_code: r.corp_code})
            MATCH (bg:BusinessGroup {unityGrupCode: r.unityGrupCode})
            MERGE (o)-[a:AFFILIATED_WITH]->(bg)
              ON CREATE SET a.first_seen_run_id = r.run_id
            SET a.year = r.year, a.induty_nm = r.induty_nm,
                a.induty_code = r.induty_code,
                a.run_id = r.run_id, a.last_updated_run_id = r.run_id,
                a.unityGrupCode = r.unityGrupCode,
                a.group_name = bg.name,
                a.repre_cmpny = bg.repre_cmpny
            """, rows=batch)


def main() -> int:
    run_id = get_active_run_id()
    print(f"[extract_ftc_groups] run_id = {run_id}")
    groups, orgs_new, edges = collect()
    print(f"[extract_ftc_groups] BusinessGroup {len(groups)}, Org 신설 {len(orgs_new)}, AFFILIATED_WITH {len(edges)}")
    if not groups and not edges:
        return 0
    load(groups, orgs_new, edges, run_id)
    print(f"[extract_ftc_groups] 적재 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
