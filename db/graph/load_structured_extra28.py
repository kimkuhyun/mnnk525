"""28개 연결사 정형 노드+엣지 적재 (extracted_by 미부여 = DART 사실). 멱등 MERGE.

load_structured.py 와 동일 로직. 대상만 28개사 + resolve_org 에 3사+28사(=31사)
corp_code 마스터 포함 → 회사 간 지분 엣지를 실제 corp_code 노드끼리 연결(다홉 체인).

노드: Organization(28개사) · Person(임원·개인주주) · FilingDocument · Chunk
엣지: EXECUTIVE_OF · IS_MAJOR_SHAREHOLDER_OF · INVESTS_IN · IS_SUBSIDIARY_OF
      · reports · has_chunk

입력: db/raw/{회사}/ds002/*.json + 사업보고서 zip(종속회사) + MariaDB chunk_index/document_index.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

# graph/ 디렉토리가 sys.path 에 있어야 db·subsidiary_parse import 가능
GRAPH_DIR = Path(__file__).resolve().parent
if str(GRAPH_DIR) not in sys.path:
    sys.path.insert(0, str(GRAPH_DIR))

from db import (
    mariadb_conn,
    neo4j_driver,
    normalize_corp_name,
    parse_number,
    parse_qota_rt,
    person_id,
)

RAW_DIR = Path(r"C:\Users\kimkuhyn\Desktop\mnnk525\db\raw")

# ── 28개사 corp_code / 폴더명 매핑 ─────────────────────────
EXTRA28: list[tuple[str, str]] = [
    ("00126362", "삼성SDI"),
    ("00126371", "삼성전기"),
    ("00126186", "삼성에스디에스"),
    ("00912006", "삼성디스플레이"),
    ("00149655", "삼성물산"),
    ("00126256", "삼성생명"),
    ("00139214", "삼성화재"),
    ("00126478", "삼성중공업"),
    ("00877059", "삼성바이오로직스"),
    ("00148276", "제일기획"),
    ("00158501", "에스원"),
    ("00165680", "호텔신라"),
    ("00181712", "SK"),
    ("01596425", "SK스퀘어"),
    ("01555631", "SK키파운드리"),
    ("01265516", "SK하이닉스시스템IC"),
    ("00652706", "SK하이스텍"),
    ("00415390", "SK하이이엔지"),
    ("00560070", "한미네트웍스"),
    ("01241987", "한화세미텍"),
    ("00118804", "동진쎄미켐"),
    ("01489648", "솔브레인"),
    ("01135941", "원익IPS"),
    ("00216647", "원익홀딩스"),
    ("01261893", "케이씨텍"),
    ("00411048", "에스앤에스텍"),
    ("00223434", "에프에스티"),
    ("01478712", "대덕전자"),
]

# 원본 3사
BASE3: dict[str, str] = {
    "00126380": "삼성전자(주)",
    "00164779": "SK하이닉스(주)",
    "00161383": "한미반도체(주)",
}

# 전체 31사 corp_code → name (resolve_org 매칭용)
ALL_CORP_NAME: dict[str, str] = dict(BASE3)

# 28사 company.json 에서 이름 로드 → ALL_CORP_NAME 채움
def _load_company_name(corp_code: str, folder: str) -> str:
    cj_path = RAW_DIR / folder / "company.json"
    if cj_path.exists():
        try:
            cj = json.loads(cj_path.read_text(encoding="utf-8"))
            nm = (cj.get("corp_name") or "").strip()
            if nm:
                return nm
        except Exception:
            pass
    return folder  # fallback = 폴더명

for cc, folder in EXTRA28:
    nm = _load_company_name(cc, folder)
    ALL_CORP_NAME[cc] = nm

# ── 사업보고서(XII 종속회사 파싱) rcept 목록 ─────────────────
# 리스트 json 에서 '사업보고서' rcept_no 자동 수집
def _collect_annual_rects(folder: str) -> list[str]:
    list_dir = RAW_DIR / folder / "list"
    if not list_dir.exists():
        return []
    rects: list[str] = []
    for lf in sorted(list_dir.glob("list_*.json")):
        try:
            obj = json.loads(lf.read_text(encoding="utf-8"))
        except Exception:
            continue
        for item in obj.get("list", []):
            if "사업보고서" in (item.get("report_nm") or ""):
                rn = (item.get("rcept_no") or "").strip()
                if rn and rn not in rects:
                    rects.append(rn)
    return rects

BIZ_REPORT_RCEPT28: dict[str, list[str]] = {}
for cc, folder in EXTRA28:
    BIZ_REPORT_RCEPT28[folder] = _collect_annual_rects(folder)

DS002 = "ds002"


# ── JSON 로더 ─────────────────────────────────────────────
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


# ── Organization MERGE ─────────────────────────────────────
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


def base_orgs_extra28() -> list[dict]:
    orgs = []
    for corp_code, folder in EXTRA28:
        cj_path = RAW_DIR / folder / "company.json"
        try:
            cj = json.loads(cj_path.read_text(encoding="utf-8"))
        except Exception:
            cj = {}
        orgs.append({
            "corp_code": corp_code,
            "name": ALL_CORP_NAME[corp_code],
            "stock_code": (cj.get("stock_code") or "").strip() or None,
            "founded": (cj.get("est_dt") or "").strip() or None,
        })
    return orgs


# ── resolve_org: 31사 corp_code 로 매칭 ────────────────────
def resolve_org_corp(target_name: str) -> str | None:
    """target_name 이 31사(3+28) 중 하나면 corp_code 반환, 아니면 None."""
    er = normalize_corp_name(target_name)
    if not er:
        return None
    for cc, nm in ALL_CORP_NAME.items():
        if normalize_corp_name(nm) == er:
            return cc
    return None


def link_org_to_target(tx, src_corp: str, target_name: str, rel: str, props: dict,
                       reverse: bool = False):
    """src(corp_code) → target(31사 corp_code 노드 또는 needs_er 임시 노드).
    reverse=True 면 target→src 방향(최대주주현황: 명시 회사가 주주, 공시회사가 피소유)."""
    target_corp = resolve_org_corp(target_name)
    edge = f"(t)-[r:{rel}]->(s)" if reverse else f"(s)-[r:{rel}]->(t)"
    if target_corp:
        cy = (
            "MATCH (s:Organization {corp_code:$src}) "
            "MERGE (t:Organization {corp_code:$tc}) "
            f"MERGE {edge} SET r += $props"
        )
        tx.run(cy, src=src_corp, tc=target_corp, props=props)
    else:
        er = normalize_corp_name(target_name)
        if not er:
            return
        cy = (
            "MATCH (s:Organization {corp_code:$src}) "
            "MERGE (t:Organization {er_name:$er, has_corp_code:false}) "
            "ON CREATE SET t.name=$name, t.needs_er=true, t.has_corp_code=false "
            f"MERGE {edge} SET r += $props"
        )
        tx.run(cy, src=src_corp, er=er, name=target_name, props=props)


# ── Person MERGE ───────────────────────────────────────────
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


_ORG_HINT = ("주", "㈜", "Co", "Inc", "Corp", "Ltd", "LLC", "보험", "증권", "은행",
             "투자", "신탁", "캐피탈", "홀딩스", "전자", "물산", "생명", "화재", "Fund",
             "SDI", "SDS", "스퀘어", "바이오", "중공업", "에스디에스", "이엔지", "IPS",
             "반도체", "세미텍", "네트웍스")


def _looks_like_person(name: str) -> bool:
    n = (name or "").strip()
    if not n:
        return False
    if any(h in n for h in _ORG_HINT):
        return False
    return 2 <= len(n) <= 5


# ── 종속회사 파싱 (subsidiary_parse 직접 포팅) ─────────────
import re
import zipfile

_GROUP_START = re.compile(r'<TABLE-GROUP[^>]*ACLASS="SUB_CMPN"', re.IGNORECASE)
_CRP_NM = re.compile(r'ACODE="CRP_NM"[^>]*>([^<]*)<', re.IGNORECASE)
_EST_DT = re.compile(r'ACODE="EST_DT"[^>]*>([^<]*)<', re.IGNORECASE)
_TR = re.compile(r"<TR\b.*?</TR>", re.IGNORECASE | re.DOTALL)


def _read_main_xml(zip_path: Path, rcept_no: str) -> str | None:
    if not zip_path.exists():
        return None
    with zipfile.ZipFile(zip_path) as zf:
        target = f"{rcept_no}.xml"
        names = zf.namelist()
        pick = target if target in names else None
        if pick is None:
            xmls = [n for n in names if n.lower().endswith(".xml")]
            if not xmls:
                return None
            pick = max(xmls, key=lambda n: zf.getinfo(n).file_size)
        data = zf.read(pick)
    for enc in ("utf-8", "cp949", "euc-kr"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _extract_group(xml: str) -> str | None:
    m = _GROUP_START.search(xml)
    if not m:
        return None
    start = m.start()
    end = xml.find("</TABLE-GROUP>", start)
    if end < 0:
        end = len(xml)
    return xml[start:end]


def _clean_name(raw: str) -> str:
    s = (raw or "").strip()
    return re.sub(r"\s+", " ", s)


def _parse_subsidiaries(zip_path: Path, rcept_no: str) -> list[dict]:
    xml = _read_main_xml(zip_path, rcept_no)
    if xml is None:
        return []
    group = _extract_group(xml)
    if group is None:
        return []
    rows: list[dict] = []
    seen: set[str] = set()
    for trm in _TR.finditer(group):
        tr = trm.group(0)
        nm = _CRP_NM.search(tr)
        if not nm:
            continue
        name = _clean_name(nm.group(1))
        if not name or name in ("상호", "-"):
            continue
        if name in seen:
            continue
        seen.add(name)
        est = _EST_DT.search(tr)
        founded = _clean_name(est.group(1)) if est else ""
        rows.append({"name": name, "founded": founded, "rcept_no": rcept_no})
    return rows


def iter_company_subsidiaries_extra28():
    """28개사 폴더별 (폴더, corp_code, [subs]) 산출."""
    for corp_code, folder in EXTRA28:
        docs_dir = RAW_DIR / folder / "documents"
        rcepts = BIZ_REPORT_RCEPT28.get(folder, [])
        merged: dict[str, dict] = {}
        used_rcept: list[str] = []
        for rcept in sorted(rcepts, reverse=True):
            zip_path = docs_dir / f"{rcept}.zip"
            subs = _parse_subsidiaries(zip_path, rcept)
            if subs:
                used_rcept.append(rcept)
            for s in subs:
                if s["name"] not in merged:
                    merged[s["name"]] = s
        if merged:
            yield folder, corp_code, used_rcept, list(merged.values())


# ── MAIN ───────────────────────────────────────────────────
def main() -> None:
    d = neo4j_driver()
    counters = {
        "exec": 0, "msh_org": 0, "msh_person": 0,
        "invest": 0, "subs": 0, "reports": 0, "has_chunk": 0,
    }

    with d.session() as s:
        # 1) 28개사 Organization MERGE
        print("[1] 28개사 Organization MERGE ...")
        for o in base_orgs_extra28():
            s.execute_write(upsert_base_org, o)
        print(f"    완료: {len(EXTRA28)}개사")

        # 2) 임원 / 주주 / 출자 엣지
        print("[2] 임원/주주/출자 엣지 ...")
        for corp_code, folder in EXTRA28:
            ds002_dir = RAW_DIR / folder / DS002
            if not ds002_dir.exists():
                print(f"    [{folder}] ds002 없음 - 건너뜀")
                continue

            # 2-1 임원 EXECUTIVE_OF
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
                    props: dict = {"rcept_no": rcept}
                    if row.get("ofcps"):
                        props["ofcps"] = row["ofcps"].strip()
                    s.execute_write(upsert_person_exec, pid, nm, birth, corp_code, props)
                    counters["exec"] += 1

            # 2-2 최대주주(hyslrSttus)
            seen_msh: set[str] = set()
            for f in _ds002_files(folder, "hyslrSttus"):
                for row in _load_json(f):
                    nm = (row.get("nm") or "").strip()
                    if not nm or nm == "-":
                        continue
                    rcept = (row.get("rcept_no") or "").strip()
                    qota = parse_qota_rt(
                        row.get("trmend_posesn_stock_qota_rt")
                        or row.get("bsis_posesn_stock_qota_rt")
                    )
                    stock = parse_number(
                        row.get("trmend_posesn_stock_co")
                        or row.get("bsis_posesn_stock_co")
                    )
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
                                        "IS_MAJOR_SHAREHOLDER_OF", props, reverse=True)
                        counters["msh_org"] += 1

            # 2-3 타법인출자 INVESTS_IN
            seen_inv: set[str] = set()
            for f in _ds002_files(folder, "otrCprInvstmntSttus"):
                for row in _load_json(f):
                    inv = (row.get("inv_prm") or "").strip()
                    if not inv or inv == "-":
                        continue
                    rcept = (row.get("rcept_no") or "").strip()
                    qota = parse_qota_rt(
                        row.get("trmend_blce_qota_rt")
                        or row.get("bsis_blce_qota_rt")
                    )
                    props = {"rcept_no": rcept}
                    if qota is not None:
                        props["qota_rt"] = qota
                    key = f"{normalize_corp_name(inv)}|{rcept}"
                    if key in seen_inv:
                        continue
                    seen_inv.add(key)
                    s.execute_write(link_org_to_target, corp_code, inv, "INVESTS_IN", props)
                    counters["invest"] += 1

            print(f"    [{folder}] exec={counters['exec']} msh={counters['msh_org']+counters['msh_person']} inv={counters['invest']}")

        print("[ok] 임원/주주/출자 엣지")

        # 3) IS_SUBSIDIARY_OF
        print("[3] IS_SUBSIDIARY_OF ...")
        for folder, parent_corp, used_rcepts, subs in iter_company_subsidiaries_extra28():
            for sub in subs:
                er = normalize_corp_name(sub["name"])
                if not er:
                    continue
                # 자회사가 31사 중 하나면 corp_code 노드 재사용
                child_corp = resolve_org_corp(sub["name"])
                if child_corp:
                    def _link_known(tx, cc=child_corp, pc=parent_corp, rc=sub["rcept_no"]):
                        tx.run(
                            """
                            MATCH (child:Organization {corp_code:$cc})
                            MATCH (parent:Organization {corp_code:$pc})
                            MERGE (child)-[r:IS_SUBSIDIARY_OF]->(parent)
                            SET r.rcept_no=$rc
                            """,
                            cc=cc, pc=pc, rc=rc,
                        )
                    s.execute_write(_link_known)
                else:
                    def _link_unknown(tx, child=sub["name"], cer=er,
                                      fnd=sub["founded"], pc=parent_corp,
                                      rc=sub["rcept_no"]):
                        tx.run(
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
                    s.execute_write(_link_unknown)
                counters["subs"] += 1
        print(f"[ok] IS_SUBSIDIARY_OF: {counters['subs']}건")

        # 4) FilingDocument + reports (document_index — 28개사만)
        print("[4] FilingDocument + reports ...")
        conn = mariadb_conn()
        cur = conn.cursor()
        extra28_codes = [cc for cc, _ in EXTRA28]
        placeholders = ",".join(["%s"] * len(extra28_codes))
        cur.execute(
            f"SELECT rcept_no, corp_code, doc_type, date FROM document_index "
            f"WHERE corp_code IN ({placeholders})",
            extra28_codes,
        )
        docs = cur.fetchall()

        BATCH = 500
        batch: list[dict] = []
        all_corps_set = set(extra28_codes)

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

        for rcept_no, corp_code, doc_type, date in docs:
            batch.append({
                "rcept_no": rcept_no,
                "corp_code": corp_code if corp_code in all_corps_set else "",
                "doc_type": doc_type,
                "date": date.isoformat() if date else None,
            })
            counters["reports"] += 1 if corp_code in all_corps_set else 0
            if len(batch) >= BATCH:
                s.execute_write(flush_docs, batch)
                batch = []
        if batch:
            s.execute_write(flush_docs, batch)
        print(f"[ok] FilingDocument {len(docs)}건 + reports {counters['reports']}건")

        # 5) Chunk + has_chunk (chunk_index — 28개사만)
        print("[5] Chunk + has_chunk ...")
        cur.execute(
            f"SELECT chunk_id, corp_code, rcept_no, chunk_type, section_path "
            f"FROM chunk_index WHERE corp_code IN ({placeholders})",
            extra28_codes,
        )
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
                "chunk_id": chunk_id, "corp_code": corp_code,
                "rcept_no": rcept_no, "chunk_type": chunk_type,
                "section_path": section_path,
            })
            counters["has_chunk"] += 1
            if len(cbatch) >= BATCH:
                s.execute_write(flush_chunks, cbatch)
                cbatch = []
        if cbatch:
            s.execute_write(flush_chunks, cbatch)
        print(f"[ok] Chunk {len(chunks)}건 + has_chunk {counters['has_chunk']}건")

        cur.close()
        conn.close()

    d.close()
    print("\n=== load_structured_extra28 카운터 ===")
    for k, v in counters.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
