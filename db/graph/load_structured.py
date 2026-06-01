"""정형 노드 + 정형 엣지 적재 (extracted_by 미부여 = DART 사실). 멱등 MERGE.

노드: Organization(3사 + 등장 타법인) · Person(임원·개인주주) · FilingDocument · Chunk
엣지: EXECUTIVE_OF · IS_MAJOR_SHAREHOLDER_OF · INVESTS_IN · IS_SUBSIDIARY_OF
      · reports · has_chunk

입력: db/raw/{회사}/ds002/*.json (exctv/hyslr/otrCpr) + 사업보고서 zip(종속회사)
      + MariaDB document_index / chunk_index.
"""
from __future__ import annotations

import json
from pathlib import Path

from db import (
    CORP_CODE,
    CORP_NAME,
    RAW_DIR,
    mariadb_conn,
    name_org_key,
    neo4j_driver,
    normalize_corp_name,
    parse_number,
    parse_qota_rt,
    person_id,
)
from subsidiary_parse import iter_company_subsidiaries

DS002 = "ds002"


def _load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if obj.get("status") != "000":
        return []
    return obj.get("list") or []


def _ds002_files(folder: str, prefix: str) -> list[Path]:
    d = RAW_DIR / folder / DS002
    if not d.exists():
        return []
    return sorted(d.glob(f"{prefix}__*.json"))


# ── 1) 3사 Organization (company.json) ─────────────────────
def base_orgs() -> list[dict]:
    orgs = []
    for folder, corp_code in CORP_CODE.items():
        cj = json.loads((RAW_DIR / folder / "company.json").read_text(encoding="utf-8"))
        orgs.append(
            {
                "corp_code": corp_code,
                "name": cj.get("corp_name") or CORP_NAME[corp_code],
                "stock_code": (cj.get("stock_code") or "").strip() or None,
                "founded": (cj.get("est_dt") or "").strip() or None,
            }
        )
    return orgs


# ── Cypher MERGE 헬퍼 ──────────────────────────────────────
def upsert_base_org(tx, o: dict):
    tx.run(
        """
        MERGE (org:Organization {corp_code:$corp_code})
        SET org.name=$name, org.stock_code=$stock_code, org.founded=$founded,
            org.needs_er=false, org.er_name=$er_name
        """,
        corp_code=o["corp_code"], name=o["name"], stock_code=o["stock_code"],
        founded=o["founded"], er_name=normalize_corp_name(o["name"]),
    )


def upsert_name_org(tx, name: str):
    """corp_code 없는 회사 = name 키 임시 노드(needs_er=true). corp_code 충돌 방지 위해
    er_name 으로 식별. 기존 corp_code 보유 노드는 건드리지 않음."""
    er = name_org_key(name)
    if not er:
        return
    tx.run(
        """
        MERGE (org:Organization {er_name:$er, has_corp_code:false})
        ON CREATE SET org.name=$name, org.needs_er=true, org.has_corp_code=false
        """,
        er=er, name=name,
    )


def link_org_to_target(tx, src_corp: str, target_name: str, rel: str, props: dict):
    """src(corp_code) → target(name 노드 또는 corp_code 노드) 정형 엣지.
    target 이 3사면 corp_code 매칭, 아니면 er_name 임시 노드."""
    er = normalize_corp_name(target_name)
    # 3사 corp_code 매칭 시도
    target_corp = None
    for cc, nm in CORP_NAME.items():
        if normalize_corp_name(nm) == er:
            target_corp = cc
            break
    if target_corp:
        cy = (
            "MATCH (s:Organization {corp_code:$src}) "
            "MERGE (t:Organization {corp_code:$tc}) "
            f"MERGE (s)-[r:{rel}]->(t) SET r += $props"
        )
        tx.run(cy, src=src_corp, tc=target_corp, props=props)
    else:
        cy = (
            "MATCH (s:Organization {corp_code:$src}) "
            "MERGE (t:Organization {er_name:$er, has_corp_code:false}) "
            "ON CREATE SET t.name=$name, t.needs_er=true, t.has_corp_code=false "
            f"MERGE (s)-[r:{rel}]->(t) SET r += $props"
        )
        tx.run(cy, src=src_corp, er=er, name=target_name, props=props)


def upsert_person_exec(tx, pid: str, name: str, birth_ym: str, corp_code: str, props: dict):
    tx.run(
        """
        MERGE (p:Person {person_id:$pid})
        SET p.name=$name, p.birth_ym=$birth_ym
        WITH p
        MATCH (o:Organization {corp_code:$corp})
        MERGE (p)-[r:EXECUTIVE_OF]->(o) SET r += $props
        """,
        pid=pid, name=name, birth_ym=birth_ym, corp=corp_code, props=props,
    )


def link_person_shareholder(tx, pid: str, name: str, birth_ym: str, corp_code: str, props: dict):
    tx.run(
        """
        MERGE (p:Person {person_id:$pid})
        SET p.name=$name, p.birth_ym=$birth_ym
        WITH p
        MATCH (o:Organization {corp_code:$corp})
        MERGE (p)-[r:IS_MAJOR_SHAREHOLDER_OF]->(o) SET r += $props
        """,
        pid=pid, name=name, birth_ym=birth_ym, corp=corp_code, props=props,
    )


# 개인 주주 식별: 이름에 회사 접미사가 없고 길이 짧으면 개인으로 본다(보수적).
_ORG_HINT = ("주", "㈜", "Co", "Inc", "Corp", "Ltd", "LLC", "보험", "증권", "은행",
             "투자", "신탁", "캐피탈", "홀딩스", "전자", "물산", "생명", "화재", "Fund")


def _looks_like_person(name: str) -> bool:
    n = (name or "").strip()
    if not n:
        return False
    if any(h in n for h in _ORG_HINT):
        return False
    # 한글 2~4자 = 개인명일 확률 높음
    return 2 <= len(n) <= 5


def main() -> None:
    d = neo4j_driver()
    counters = {"exec": 0, "msh_org": 0, "msh_person": 0, "invest": 0, "subs": 0,
                "reports": 0, "has_chunk": 0, "name_org": 0}

    with d.session() as s:
        # 1) 3사 Organization
        for o in base_orgs():
            s.execute_write(upsert_base_org, o)
        print("[ok] 3사 Organization MERGE")

        # 2) 임원 EXECUTIVE_OF + 개인주주/법인주주 IS_MAJOR_SHAREHOLDER_OF + INVESTS_IN
        for folder, corp_code in CORP_CODE.items():
            # 2-1 임원
            seen_exec: set[str] = set()
            for f in _ds002_files(folder, "exctvSttus"):
                for row in _load_json(f):
                    nm = (row.get("nm") or "").strip()
                    if not nm:
                        continue
                    birth = (row.get("birth_ym") or "").strip()
                    pid = person_id(corp_code, nm, birth)
                    rcept = (row.get("rcept_no") or "").strip()
                    key = f"{pid}|{rcept}"
                    if key in seen_exec:
                        continue
                    seen_exec.add(key)
                    props = {"rcept_no": rcept}
                    if row.get("ofcps"):
                        props["ofcps"] = row["ofcps"].strip()
                    s.execute_write(upsert_person_exec, pid, nm, birth, corp_code, props)
                    counters["exec"] += 1

            # 2-2 최대주주(hyslrSttus): 법인=IS_MAJOR_SHAREHOLDER_OF(Org→Org), 개인=Person→Org
            seen_msh: set[str] = set()
            for f in _ds002_files(folder, "hyslrSttus"):
                for row in _load_json(f):
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
                    if _looks_like_person(nm):
                        pid = person_id(corp_code, nm, "")
                        key = f"P|{pid}|{rcept}"
                        if key in seen_msh:
                            continue
                        seen_msh.add(key)
                        s.execute_write(link_person_shareholder, pid, nm, "", corp_code, props)
                        counters["msh_person"] += 1
                    else:
                        key = f"O|{normalize_corp_name(nm)}|{rcept}"
                        if key in seen_msh:
                            continue
                        seen_msh.add(key)
                        s.execute_write(link_org_to_target, corp_code, nm,
                                        "IS_MAJOR_SHAREHOLDER_OF", props)
                        counters["msh_org"] += 1

            # 2-3 타법인출자 INVESTS_IN (Org→Org, 피출자=inv_prm)
            seen_inv: set[str] = set()
            for f in _ds002_files(folder, "otrCprInvstmntSttus"):
                for row in _load_json(f):
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
                    s.execute_write(link_org_to_target, corp_code, inv, "INVESTS_IN", props)
                    counters["invest"] += 1

        print("[ok] 임원/주주/출자 엣지")

        # 3) IS_SUBSIDIARY_OF (사업보고서 XII 종속회사 → 모회사 corp_code)
        folder_to_corp = {f: c for f, c in CORP_CODE.items()}
        for folder, used_rcepts, subs in iter_company_subsidiaries():
            parent_corp = folder_to_corp[folder]
            rcept = used_rcepts[0] if used_rcepts else ""
            for sub in subs:
                # 자회사 → 모회사 방향 (IS_SUBSIDIARY_OF: child Org → parent Org)
                er = normalize_corp_name(sub["name"])
                if not er:
                    continue
                s.execute_write(
                    lambda tx, child=sub["name"], cer=er, fnd=sub["founded"],
                    pc=parent_corp, rc=sub["rcept_no"]: tx.run(
                        """
                        MERGE (child:Organization {er_name:$cer, has_corp_code:false})
                        ON CREATE SET child.name=$cname, child.needs_er=true,
                                      child.has_corp_code=false
                        SET child.founded=coalesce(child.founded,$fnd)
                        WITH child
                        MATCH (parent:Organization {corp_code:$pc})
                        MERGE (child)-[r:IS_SUBSIDIARY_OF]->(parent)
                        SET r.rcept_no=$rc
                        """,
                        cer=cer, cname=child, fnd=(fnd or None), pc=pc, rc=rc,
                    )
                )
                counters["subs"] += 1
        print("[ok] IS_SUBSIDIARY_OF 엣지")

        # 4) FilingDocument + reports (document_index)
        conn = mariadb_conn()
        cur = conn.cursor()
        cur.execute("SELECT rcept_no, corp_code, doc_type, date FROM document_index")
        docs = cur.fetchall()
        # 배치 MERGE
        BATCH = 500
        batch: list[dict] = []

        def flush_docs(tx, rows):
            tx.run(
                """
                UNWIND $rows AS row
                MERGE (f:FilingDocument {rcept_no: row.rcept_no})
                SET f.doc_type = row.doc_type, f.date = row.date
                WITH f, row
                WHERE row.corp_code IS NOT NULL AND row.corp_code <> ''
                MATCH (o:Organization {corp_code: row.corp_code})
                MERGE (o)-[:reports]->(f)
                """,
                rows=rows,
            )

        known_corps = set(CORP_CODE.values())
        for rcept_no, corp_code, doc_type, date in docs:
            batch.append({
                "rcept_no": rcept_no,
                "corp_code": corp_code if corp_code in known_corps else "",
                "doc_type": doc_type,
                "date": date.isoformat() if date else None,
            })
            counters["reports"] += 1 if (corp_code in known_corps) else 0
            if len(batch) >= BATCH:
                s.execute_write(flush_docs, batch)
                batch = []
        if batch:
            s.execute_write(flush_docs, batch)
        print(f"[ok] FilingDocument {len(docs)}건 + reports")

        # 5) Chunk + has_chunk (chunk_index)
        cur.execute("SELECT chunk_id, corp_code, rcept_no, chunk_type, section_path FROM chunk_index")
        chunks = cur.fetchall()
        cbatch: list[dict] = []

        def flush_chunks(tx, rows):
            tx.run(
                """
                UNWIND $rows AS row
                MERGE (c:Chunk {chunk_id: row.chunk_id})
                SET c.corp_code = row.corp_code, c.chunk_type = row.chunk_type,
                    c.section_path = row.section_path
                WITH c, row
                WHERE row.rcept_no IS NOT NULL AND row.rcept_no <> ''
                MATCH (f:FilingDocument {rcept_no: row.rcept_no})
                MERGE (f)-[:has_chunk]->(c)
                """,
                rows=rows,
            )

        for chunk_id, corp_code, rcept_no, chunk_type, section_path in chunks:
            cbatch.append({
                "chunk_id": chunk_id, "corp_code": corp_code, "rcept_no": rcept_no,
                "chunk_type": chunk_type, "section_path": section_path,
            })
            counters["has_chunk"] += 1
            if len(cbatch) >= BATCH:
                s.execute_write(flush_chunks, cbatch)
                cbatch = []
        if cbatch:
            s.execute_write(flush_chunks, cbatch)
        print(f"[ok] Chunk {len(chunks)}건 + has_chunk")

        cur.close()
        conn.close()

    d.close()
    print("=== load_structured 카운터 ===")
    for k, v in counters.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
