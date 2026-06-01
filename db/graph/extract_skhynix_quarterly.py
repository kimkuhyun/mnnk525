"""SK하이닉스 분기/반기보고서 4건 비정형 추출 적재 (B단계).

대상 rcept_no (각각 별도 처리·별도 원장):
  20240516001638 (2024 1분기) · 20240814001887 (2024 반기)
  20241114001712 (2024 3분기)  · 20250515002103 (2025 1분기)

추출 = Claude(에이전트)가 chunk_index 본문을 읽고 판단한 엔티티·엣지를,
'본문 앵커 텍스트가 그 청크에 실재할 때만' 결정론적으로 적재한다(환각 방어).
- 제품/기술 토큰: 'II. 사업의 내용' 청크에 토큰 문자열이 실재하면 PRODUCES/USES_TECH(SK→) + hasObject(Chunk→).
- 관계회사: '구 분 | 회사명' 특수관계자 청크에 회사명이 실재하면 RELATED_PARTY(SK→, relation_type).
- 계약: Rambus/Intel 계약표 청크 → RELATED_PARTY(라이선스/영업양수).
- 매입/매출 흐름: 대주주 대여 표·해외 제조/판매 법인 → SUPPLIES_TO(제조법인→SK 매입 / SK→판매법인 매출).
정형 재무 표(수치만)는 제외. 모든 엣지 write_provenance.

원장은 문서별 graph/ledger/<rcept>.jsonl 에만(공유 ledger 금지). 시작 시 원장 확인해 스킵.
대상 청크는 추출 0개여도 전부 mark → 누락 0. 멱등.

실행: cd db && PYTHONIOENCODING=utf-8 uv run python graph/extract_skhynix_quarterly.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_helpers import (  # noqa: E402
    add_edge,
    get_chunks,
    mariadb_conn,
    merge_entity,
    merge_org_node,
    neo4j_driver,
    resolve_org,
    write_provenance,
)

RCEPTS = [
    "20240516001638",  # 2024 1분기
    "20240814001887",  # 2024 반기
    "20241114001712",  # 2024 3분기
    "20250515002103",  # 2025 1분기
]
SKH = "SK하이닉스"  # resolve_org → corp_code 00164779
LEDGER_DIR = Path(__file__).resolve().parent / "ledger"

P, T = "Product", "Technology"

# ── 제품/기술 토큰 (II.사업의 내용 청크에 '문자열 실재' 시에만 발화) ──
# (label, anchor[, name, conf, USES_TECH?]). anchor = 청크 본문에 반드시 존재해야 함.
# 표/명시(연구결과·매출표) conf 0.85+, 본문 서술 추론 0.78~0.82.
PROD_TOKENS = [
    # 핵심 제품군 — 사업의 내용·매출표에 명시
    (P, "HBM3E", "HBM3E", 0.92),
    (P, "HBM3", "HBM3", 0.88),
    (P, "HBM", "HBM", 0.85),
    (P, "DRAM", "DRAM", 0.85),
    (P, "NAND Flash", "NAND Flash", 0.85),
    (P, "CIS", "CMOS 이미지 센서(CIS)", 0.85),  # CIS 약어
    (P, "CMOS 이미지 센서", "CMOS 이미지 센서(CIS)", 0.85),
    (P, "GDDR7", "GDDR7", 0.85),
    (P, "GDDR6", "GDDR6", 0.82),
    (P, "LPDDR5X", "LPDDR5X", 0.82),
    (P, "LPDDR5T", "LPDDR5T", 0.82),
    (P, "LPDDR5", "LPDDR5", 0.8),
    (P, "LPDDR4", "LPDDR4", 0.8),
    (P, "DDR5", "DDR5", 0.82),
    (P, "DDR4", "DDR4", 0.8),
    (P, "DDR3", "DDR3", 0.78),
    (P, "eSSD", "eSSD", 0.82),
    (P, "cSSD", "cSSD", 0.8),
    (P, "SSD", "SSD", 0.8),
    (P, "UFS", "UFS", 0.8),
    (P, "eMMC", "eMMC", 0.78),
    (P, "ZUFS 4.0", "ZUFS 4.0", 0.85),
    (P, "PCB01", "PCB01 SSD", 0.85),
    (P, "PS1012", "PS1012 eSSD", 0.85),
    (P, "CMM-DDR5", "CMM-DDR5", 0.85),
    (P, "CXL 메모리", "CXL 메모리", 0.8),
    (P, "Foundry", "Foundry", 0.82),
    (P, "파운드리", "Foundry", 0.82),
    (P, "1cnm DDR5", "1cnm DDR5", 0.85),
    (P, "238단 4D NAND", "238단 4D NAND", 0.85),
    (P, "321단", "321단 4D NAND", 0.82),
    # 기술 (공정/구조) — USES_TECH
    (T, "MR-MUF", "MR-MUF", 0.85),
    (T, "TSV", "TSV(Through Silicon Via)", 0.85),
    (T, "EUV", "EUV 공정", 0.82),
    (T, "PIM", "PIM(Processing-In-Memory)", 0.82),
    (T, "HKMG", "HKMG(High-K Metal Gate)", 0.82),
    (T, "QLC", "QLC", 0.8),
    (T, "TLC", "TLC", 0.78),
]

# ── 관계회사 (특수관계자 '구 분 | 회사명' 청크에 회사명 실재 시 RELATED_PARTY) ──
# (회사명, relation_type, conf). 회사명은 청크 본문에 그대로 존재해야 발화.
RELATED_COMPANIES = [
    ("Stratio, Inc.", "관계기업", 0.85),
    ("SK China Company Limited", "관계기업", 0.85),
    ("Gemini Partners Pte. Ltd.", "관계기업", 0.8),
    ("SK South East Asia Investment Pte. Ltd.", "관계기업", 0.85),
    ("SiFive", "관계기업", 0.85),  # SiFive Inc./SiFIVE/SiFive, Inc.
    ("SAPEON", "관계기업", 0.8),
    ("우시시신파직접회로산업원유한공사", "관계기업", 0.82),
    ("HITECH Semiconductor (Wuxi) Co., Ltd.", "공동기업", 0.85),
    ("Hystars Semiconductor (Wuxi) Co., Ltd.", "공동기업", 0.85),
    ("SK스퀘어", "기타특수관계자(지배주주)", 0.9),
    ("SK㈜", "기타특수관계자(최상위지배기업)", 0.82),
]

# ── 계약 (계약표 청크) ──
CONTRACTS = [
    ("Rambus Inc.", "특허 크로스 라이선스", 0.9),
    ("Intel Corporation", "영업양수(NAND사업)", 0.9),
]

# ── 매입/매출 법인 (해외 제조→SK 매입 / SK→판매 법인 매출) + 대여 특수관계 ──
# 제조법인: 반도체 제조 → SK가 매입(공급받음) → 법인→SK (SUPPLIES_TO)
MFG_ENTITIES = [
    "SK hynix Semiconductor (China) Ltd.",
    "SK hynix Semiconductor (Chongqing) Ltd.",
    "SK hynix Semiconductor (Dalian) Co., Ltd.",
]
# 판매법인: 반도체 판매 → SK가 매출(공급) → SK→법인 (SUPPLIES_TO)
SALES_ENTITIES = [
    "SK hynix America Inc.",
    "SK hynix Deutschland GmbH",
    "SK hynix Asia Pte. Ltd.",
    "SK hynix Semiconductor Hong Kong Ltd.",
    "SK hynix Japan Inc.",
    "SK hynix U.K. Ltd.",
    "SK hynix (Wuxi) Semiconductor Sales Ltd.",
    "SK hynix Semiconductor Taiwan Inc.",
]
# 대주주 대여 표의 차입 해외법인 → RELATED_PARTY(자금대여)
LOAN_ENTITIES = [
    "SK hynix NAND Product Solutions Corp.",
    "SK hynix Semiconductor(China) Ltd.",
    "SK hynix Semiconductor(Dalian) Co., Ltd.",
]


# ── 청크 분류 판정 (section_path + 본문 앵커) ──
def is_business_section(sp: str) -> bool:
    return bool(sp) and sp.startswith("II. 사업의 내용")


def is_specrel_chunk(txt: str) -> bool:
    """특수관계자 '구 분 | 회사명' 목록 청크(수치 표 아님)."""
    return ("특수관계자의 내역은 다음과 같습니다" in txt
            and "구 분 | 회사명" in txt
            and "관계기업" in txt and "공동기업" in txt)


def is_contract_chunk(txt: str) -> bool:
    return "Rambus Inc." in txt and "계약 유형" in txt and "Intel Corporation" in txt


def is_loan_chunk(txt: str) -> bool:
    return "대상자의 이름" in txt and "장기대여" in txt and "이자율" in txt


def is_subsidiary_list_chunk(txt: str) -> bool:
    """종속기업 표(주요영업활동=반도체 판매/제조, 지분율) — 판매/제조 흐름 근거.
    분기별 청킹 차이를 흡수: '반도체 판매' 또는 '반도체 제조' 가 지분율 표와 함께 등장."""
    has_ratio = ("소유지분율" in txt) or ("지분율(%)" in txt)
    has_biz = ("반도체 판매" in txt) or ("반도체 제조" in txt)
    has_entity = any(n in txt for n in (MFG_ENTITIES + SALES_ENTITIES))
    return has_ratio and has_biz and has_entity


# ── rcept 전용 원장 ─────────────────────────────────────────
def ledger_path(rcept: str) -> Path:
    return LEDGER_DIR / f"{rcept}.jsonl"


def ledger_ids(rcept: str) -> set[str]:
    p = ledger_path(rcept)
    if not p.exists():
        return set()
    ids = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ids.add(json.loads(line)["chunk_id"])
        except Exception:
            continue
    return ids


def mark(rcept: str, chunk_id: str, n_ent: int, n_edge: int, section_path: str = None) -> None:
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    rec = {
        "chunk_id": chunk_id, "n_ent": n_ent, "n_edge": n_edge,
        "rcept_no": rcept, "section_path": section_path,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with ledger_path(rcept).open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ── 한 청크에서 추출 산출 (driver/conn 사용) ────────────────
def extract_chunk(driver, conn, rcept, row, stats):
    cid = row["chunk_id"]
    txt = row["embedding_text"] or ""
    sp = row["section_path"] or ""
    n_ent = n_edge = 0
    ent_by_label, edge_by_type = stats["ent"], stats["edge"]

    def emit_entity(label, eid, conf):
        nonlocal n_ent, n_edge
        add_edge(driver, "hasObject",
                 {"kind": "chunk", "chunk_id": cid},
                 {"kind": "entity", "label": label, "id": eid},
                 chunk_id=cid, rcept_no=rcept, confidence=1.0)
        write_provenance(conn, cid, "hasObject", eid, cid, rcept, 1.0)
        rel = "USES_TECH" if label == T else "PRODUCES"
        add_edge(driver, rel, {"kind": "org", "org": resolve_org(SKH)},
                 {"kind": "entity", "label": label, "id": eid},
                 chunk_id=cid, rcept_no=rcept, confidence=conf)
        write_provenance(conn, resolve_org(SKH)["id"], rel, eid, cid, rcept, conf)
        n_ent += 1
        n_edge += 2
        ent_by_label[label] = ent_by_label.get(label, 0) + 1
        edge_by_type["hasObject"] = edge_by_type.get("hasObject", 0) + 1
        edge_by_type[rel] = edge_by_type.get(rel, 0) + 1

    def emit_org_edge(rel, to_name, conf, relation_type=None, reverse=False):
        nonlocal n_edge
        org = resolve_org(to_name)
        if not org:
            return
        merge_org_node(driver, org)
        a = {"kind": "org", "org": resolve_org(SKH)}
        b = {"kind": "org", "org": org}
        frm, to = (b, a) if reverse else (a, b)
        fid = (org["id"] if reverse else resolve_org(SKH)["id"])
        tid = (resolve_org(SKH)["id"] if reverse else org["id"])
        add_edge(driver, rel, frm, to, chunk_id=cid, rcept_no=rcept,
                 confidence=conf, relation_type=relation_type)
        write_provenance(conn, fid, rel, tid, cid, rcept, conf)
        n_edge += 1
        edge_by_type[rel] = edge_by_type.get(rel, 0) + 1

    # 1) 제품/기술 (사업의 내용 청크에서 토큰 실재 시)
    if is_business_section(sp):
        seen = set()
        for label, anchor, name, conf in PROD_TOKENS:
            # 영숫자 경계 매칭: DDR5 가 LPDDR5X 안에서 오발화하지 않도록.
            pat = r"(?<![A-Za-z0-9])" + re.escape(anchor) + r"(?![A-Za-z0-9])"
            if re.search(pat, txt):
                canonical = name.strip().lower()
                if (label, canonical) in seen:
                    continue
                seen.add((label, canonical))
                eid = merge_entity(driver, label, canonical, name)
                emit_entity(label, eid, conf)

    # 2) 관계회사 (특수관계자 목록 청크)
    if is_specrel_chunk(txt):
        for name, rtype, conf in RELATED_COMPANIES:
            if name in txt:
                emit_org_edge("RELATED_PARTY", name, conf, relation_type=rtype)

    # 3) 계약 (Rambus/Intel)
    if is_contract_chunk(txt):
        for name, rtype, conf in CONTRACTS:
            if name in txt:
                emit_org_edge("RELATED_PARTY", name, conf, relation_type=rtype)

    # 4) 대주주 대여 표 → RELATED_PARTY(자금대여)
    if is_loan_chunk(txt):
        for name in LOAN_ENTITIES:
            if name in txt:
                emit_org_edge("RELATED_PARTY", name, 0.85, relation_type="해외법인(자금대여)")

    # 5) 종속기업 목록(판매/제조) → SUPPLIES_TO 흐름
    if is_subsidiary_list_chunk(txt):
        for name in MFG_ENTITIES:
            if name in txt:
                emit_org_edge("SUPPLIES_TO", name, 0.85, reverse=True)  # 제조법인→SK(매입)
        for name in SALES_ENTITIES:
            if name in txt:
                emit_org_edge("SUPPLIES_TO", name, 0.85, reverse=False)  # SK→판매법인(매출)

    return n_ent, n_edge


# ── 문서 1건 처리 ──────────────────────────────────────────
def run_rcept(rcept, driver, conn):
    rows = get_chunks(f"WHERE rcept_no='{rcept}'")
    done = ledger_ids(rcept)
    stats = {"ent": {}, "edge": {}}
    n_ent_total = n_edge_total = processed = 0
    print(f"[{rcept}] 청크 {len(rows)}건, 원장 기처리 {len(done)}건")

    for row in rows:
        cid = row["chunk_id"]
        if cid in done:
            continue
        n_ent, n_edge = extract_chunk(driver, conn, rcept, row, stats)
        conn.commit()
        mark(rcept, cid, n_ent, n_edge, row["section_path"])  # 0개여도 mark → 누락 0
        n_ent_total += n_ent
        n_edge_total += n_edge
        processed += 1

    print(f"  처리 {processed}  (원장누적 {len(ledger_ids(rcept))}/{len(rows)})  "
          f"엔티티 {n_ent_total} 엣지 {n_edge_total}")
    print(f"  엔티티 타입별 {stats['ent']}")
    print(f"  엣지 타입별 {stats['edge']}")
    return {"rcept": rcept, "n_chunks": len(rows), "processed": processed,
            "n_ent": n_ent_total, "n_edge": n_edge_total,
            "ent": dict(stats["ent"]), "edge": dict(stats["edge"])}


def run():
    driver = neo4j_driver()
    conn = mariadb_conn()
    results = []
    for rcept in RCEPTS:
        results.append(run_rcept(rcept, driver, conn))
    conn.close()
    driver.close()

    print("\n=== SK하이닉스 분기/반기 4건 추출 합계 ===")
    tot_ent = tot_edge = tot_chunks = 0
    agg_ent, agg_edge = {}, {}
    for r in results:
        tot_ent += r["n_ent"]
        tot_edge += r["n_edge"]
        tot_chunks += r["n_chunks"]
        for k, v in r["ent"].items():
            agg_ent[k] = agg_ent.get(k, 0) + v
        for k, v in r["edge"].items():
            agg_edge[k] = agg_edge.get(k, 0) + v
    print(f"문서수 {len(results)}  청크합 {tot_chunks}  엔티티합 {tot_ent}  엣지합 {tot_edge}")
    print(f"엔티티 타입별 {agg_ent}")
    print(f"엣지 타입별 {agg_edge}")


if __name__ == "__main__":
    run()
