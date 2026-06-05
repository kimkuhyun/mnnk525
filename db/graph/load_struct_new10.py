"""신규 10사 정형 엣지 적재 (extra28 로더 함수 재사용, steps 1-3만).

FilingDocument/has_chunk(steps 4-5)는 v3 다이어트로 제거됨 → 여기선 적재 안 함.
대상: corps.tsv 하위 10사. ds002(임원·주주·출자) + 사업보고서(종속) → Neo4j.
재무는 별도(load_finmetric 경로). 멱등 MERGE.
"""
from __future__ import annotations

import sys
from pathlib import Path

GRAPH_DIR = Path(__file__).resolve().parent
if str(GRAPH_DIR) not in sys.path:
    sys.path.insert(0, str(GRAPH_DIR))

from db import neo4j_driver, normalize_corp_name, parse_number, parse_qota_rt, person_id
import load_structured_extra28 as L

NEW10 = {
    "00105873", "00105961", "00138020", "00139889", "00152686",
    "00158219", "00227333", "00301246", "00445054", "00447609",
}


def main() -> None:
    targets = [(cc, folder) for cc, folder in L.EXTRA28 if cc in NEW10]
    print(f"[대상] {len(targets)}개사: {[f for _, f in targets]}")
    d = neo4j_driver()
    c = {"exec": 0, "msh_org": 0, "msh_person": 0, "invest": 0, "subs": 0}
    with d.session() as s:
        # 1) Organization 보강(stock_code/founded)
        for o in L.base_orgs_extra28():
            if o["corp_code"] in NEW10:
                s.execute_write(L.upsert_base_org, o)

        # 2) 임원/주주/출자
        for corp_code, folder in targets:
            for f in L._ds002_files(folder, "exctvSttus"):
                seen: set[str] = set()
                for row in L._load_json(f):
                    nm = (row.get("nm") or "").strip()
                    if not nm:
                        continue
                    birth = (row.get("birth_ym") or "").strip()
                    pid = person_id(corp_code, nm, birth)
                    rcept = (row.get("rcept_no") or "").strip()
                    key = f"{pid}|{rcept}"
                    if key in seen:
                        continue
                    seen.add(key)
                    props = {"rcept_no": rcept}
                    if row.get("ofcps"):
                        props["ofcps"] = row["ofcps"].strip()
                    s.execute_write(L.upsert_person_exec, pid, nm, birth, corp_code, props)
                    c["exec"] += 1

            seen_msh: set[str] = set()
            for f in L._ds002_files(folder, "hyslrSttus"):
                for row in L._load_json(f):
                    nm = (row.get("nm") or "").strip()
                    if not nm or nm == "-":
                        continue
                    rcept = (row.get("rcept_no") or "").strip()
                    qota = parse_qota_rt(row.get("trmend_posesn_stock_qota_rt")
                                         or row.get("bsis_posesn_stock_qota_rt"))
                    stock = parse_number(row.get("trmend_posesn_stock_co")
                                         or row.get("bsis_posesn_stock_co"))
                    props = {"rcept_no": rcept}
                    if qota is not None:
                        props["qota_rt"] = qota
                    if stock is not None:
                        props["posesn_stock_co"] = stock
                    if L._looks_like_person(nm):
                        pid = person_id(corp_code, nm, "")
                        key = f"P|{pid}|{rcept}"
                        if key in seen_msh:
                            continue
                        seen_msh.add(key)
                        s.execute_write(L.link_person_shareholder, pid, nm, "", corp_code, props)
                        c["msh_person"] += 1
                    else:
                        key = f"O|{normalize_corp_name(nm)}|{rcept}"
                        if key in seen_msh:
                            continue
                        seen_msh.add(key)
                        s.execute_write(L.link_org_to_target, corp_code, nm,
                                        "IS_MAJOR_SHAREHOLDER_OF", props, reverse=True)
                        c["msh_org"] += 1

            seen_inv: set[str] = set()
            for f in L._ds002_files(folder, "otrCprInvstmntSttus"):
                for row in L._load_json(f):
                    inv = (row.get("inv_prm") or "").strip()
                    if not inv or inv == "-":
                        continue
                    rcept = (row.get("rcept_no") or "").strip()
                    qota = parse_qota_rt(row.get("trmend_blce_qota_rt")
                                         or row.get("bsis_blce_qota_rt"))
                    props = {"rcept_no": rcept}
                    if qota is not None:
                        props["qota_rt"] = qota
                    key = f"{normalize_corp_name(inv)}|{rcept}"
                    if key in seen_inv:
                        continue
                    seen_inv.add(key)
                    s.execute_write(L.link_org_to_target, corp_code, inv, "INVESTS_IN", props)
                    c["invest"] += 1

        # 3) IS_SUBSIDIARY_OF (대상 10사만)
        for folder, parent_corp, used_rcepts, subs in L.iter_company_subsidiaries_extra28():
            if parent_corp not in NEW10:
                continue
            for sub in subs:
                er = normalize_corp_name(sub["name"])
                if not er:
                    continue
                child_corp = L.resolve_org_corp(sub["name"])
                if child_corp:
                    s.execute_write(lambda tx, cc=child_corp, pc=parent_corp, rc=sub["rcept_no"]: tx.run(
                        "MATCH (child:Organization {corp_code:$cc}) "
                        "MATCH (parent:Organization {corp_code:$pc}) "
                        "MERGE (child)-[r:IS_SUBSIDIARY_OF]->(parent) SET r.rcept_no=$rc",
                        cc=cc, pc=pc, rc=rc))
                else:
                    s.execute_write(lambda tx, child=sub["name"], cer=er, fnd=sub["founded"],
                                    pc=parent_corp, rc=sub["rcept_no"]: tx.run(
                        "MERGE (child:Organization {er_name:$cer, has_corp_code:false}) "
                        "ON CREATE SET child.name=$cname, child.needs_er=true, child.has_corp_code=false "
                        "SET child.founded=coalesce(child.founded,$fnd) "
                        "WITH child MATCH (parent:Organization {corp_code:$pc}) "
                        "MERGE (child)-[r:IS_SUBSIDIARY_OF]->(parent) SET r.rcept_no=$rc",
                        cer=cer, cname=child, fnd=(fnd or None), pc=pc, rc=rc))
                c["subs"] += 1
    d.close()
    print("=== 신규10사 정형 적재 카운터 ===")
    for k, v in c.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
