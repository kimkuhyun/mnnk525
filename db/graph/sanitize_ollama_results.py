"""Sanitize Ollama extraction result files before graph load.

Default mode is dry-run:
  uv run python graph/sanitize_ollama_results.py

Apply mode backs up original result files and overwrites result_<corp>_*.json:
  uv run python graph/sanitize_ollama_results.py --apply

This is intentionally rule-based and auditable. It removes broad recurring
noise before Neo4j load while keeping review_*.jsonl as the original audit log.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUTO = HERE / "_auto"
DB = HERE.parent
CORPS_TSV = DB / "extra28" / "corps.tsv"

BUSINESS_PREDICATES = {"PRODUCES", "USES_TECH", "SUPPLIES_TO"}
ALL_PREDICATES = BUSINESS_PREDICATES | {"RELATED_PARTY", "hasObject"}

GENERIC_NAMES = {
    "",
    "기타",
    "기타 관계기업",
    "그 밖의 특수관계자",
    "합계",
    "관계",
    "채권자",
    "신용공여 종류",
    "신용공여 목적",
    "채무보증",
    "시설자금",
    "운영자금",
    "일반자금",
    "차입금",
    "보증",
    "담보",
}
ASSET_NAMES = {
    "토지",
    "건물",
    "구축물",
    "기계장치",
    "시설장치",
    "공구와기구",
    "차량운반구",
    "건설중인 자산",
    "건설중인자산",
    "비품",
}
APPLICATION_NAMES = {
    "스마트폰",
    "태블릿 PC",
    "태블릿",
    "자동차",
    "TV",
    "OLED TV",
    "Galaxy S series",
    "Galaxy Watch",
    "Buds Series",
    "OLED Panel",
    "Wired Charger",
    "End-User",
}
BUSINESS_DIVISION_NAMES = {
    "광학솔루션",
    "기판소재",
    "전장부품",
    "패키지솔루션",
    "모빌리티솔루션",
    "광학/기판사업부",
    "모빌리티솔루션 사업부",
    "외 시장",
    "내수",
    "수출",
    "해외법인",
    "완성차 업체",
    "부동산전세계약",
    "Display 제품",
    "Display패널용",
    "Display",
    "박막사업",
    "박막",
    "화학",
    "반도체",
    "디스플레이 제조용 케미컬",
    "통신모듈",
    "AI 제품군",
    "스마트폰용 HDI",
    "Memory Module",
    "FC-CSP",
    "FBGA 제품",
    "글로벌 메모리 고객사 3사",
    "반도체 제조사",
    "고객사",
    "주요고객(A)",
    "주요고객(B)",
    "한국",
    "장비업체",
}
MATERIAL_OR_PRODUCT_ENDPOINTS = {
    "PCB",
    "FPCB",
    "FPCA",
    "OLED",
    "LCD",
    "Glass",
    "Drive IC",
    "Back-Light",
    "Image Sensor",
    "Lens",
    "Actuator",
    "FCCL",
    "Chemical",
    "CCL/PP",
    "IC",
    "SiC Wafer",
    "Tunsten NAND",
    "Tungsten NAND",
    "eMCP제품",
    "Lead Frame",
    "Gold Wire",
    "EMC",
    "EPOXY",
    "플레이트",
    "알루미나(Al2O3)",
    "Solder Ball",
}

FINANCE_ENDPOINT_RE = re.compile(
    r"은행|Bank|Branch|보증보험|증권|채권자|차입|채무보증|담보|시설자금|운영자금|"
    r"이자율스왑|통화스왑|일반자금대출",
    re.IGNORECASE,
)
INVESTMENT_VEHICLE_RE = re.compile(
    r"투자조합|펀드|사모|신기술투자|합자회사|First\s*Dream|퍼즐화인|프렌드\s*혁신성장|"
    r"미디어커머스\d*호|신성장\d*호|투자\b",
    re.IGNORECASE,
)
FINANCE_TEXT_RE = re.compile(
    r"채무보증|신용공여|보증계약|보증기간|채권자|시설자금|운영자금|차입|"
    r"파생상품|주가수익스왑|공정가치|채무상품|손실충당금",
    re.IGNORECASE,
)
BUSINESS_SIGNAL_RE = re.compile(
    r"주요\s*(매출처|고객|매입처)|고객사|거래처|매출처|판매처|납품|공급|"
    r"원재료|원부재료|협력사|제품|기술|장비|소재|반도체|HBM|DRAM|NAND|OLED|LCD|"
    r"PCB|FPCB|FPCA|패키징|웨이퍼|생산품목|주요 제품"
)
LICENSE_OR_CONTRACT_RE = re.compile(
    r"기술도입/공급계약|계약 상대방|계약상대방|기부채납|사용수익|특허 실시권|라이선스",
    re.IGNORECASE,
)
COMPLIANCE_OR_ESG_RE = re.compile(
    r"ISO\s*\d+|환경경영|안전보건|에너지경영|온실가스|배출권|녹색경영|"
    r"Chemical Management System|CMS:|인증|검증기관",
    re.IGNORECASE,
)
MARKET_TABLE_RE = re.compile(
    r"시장점유율|헤더:\s*구 분\s*\|\s*회사명\s*\|\s*20\d{2}년 매출액|"
    r"헤더:\s*20\d{2}년\s*\|.*매출액\\(억원\\)|"
    r"헤더:\s*업체\s*\|\s*매출액",
    re.IGNORECASE,
)
PIPE_TABLE_HEADER_RE = re.compile(
    r"피투자회사|투자회사|회사명|업체명|거래처|고객사|매출처|매입처|구\s*분|내역",
    re.IGNORECASE,
)


def compact(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").lower())


GENERIC_COMPACT = {compact(x) for x in GENERIC_NAMES}
ASSET_COMPACT = {compact(x) for x in ASSET_NAMES}
APPLICATION_COMPACT = {compact(x) for x in APPLICATION_NAMES}
BUSINESS_DIVISION_COMPACT = {compact(x) for x in BUSINESS_DIVISION_NAMES}
MATERIAL_OR_PRODUCT_COMPACT = {compact(x) for x in MATERIAL_OR_PRODUCT_ENDPOINTS}


def corp_names() -> dict[str, str]:
    if not CORPS_TSV.exists():
        return {}
    out: dict[str, str] = {}
    with CORPS_TSV.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            code = (row.get("corp_code") or "").strip()
            name = (row.get("name") or "").strip()
            if code and name:
                out[code] = name
    return out


def discover_codes() -> list[str]:
    codes = set()
    for p in AUTO.glob("result_*.json"):
        m = re.match(r"result_(\d{8})_\d+\.json$", p.name)
        if m:
            codes.add(m.group(1))
    return sorted(codes)


def clean_name(name: str) -> str:
    n = (name or "").strip()
    n = re.sub(r"\s+", " ", n)
    n = n.replace("㈜", "(주)")
    n = n.replace("（주）", "(주)")
    n = re.sub(r"\s+\(주\)", "(주)", n)
    n = n.strip(" \t\r\n,;:")
    # Table chunking sometimes leaves a dangling opening parenthesis.
    while n.endswith("(") or n.endswith("["):
        n = n[:-1].rstrip()
    return n


def section_kind(text: str) -> str:
    head = (text or "")[:180]
    if "· II. 사업의 내용" in head:
        return "business"
    if "· III. 재무에 관한 사항" in head or "감사보고서" in head:
        return "financial"
    if "· IX." in head or "· X." in head:
        return "governance"
    if "· XI." in head:
        return "legal"
    return "other"


def is_generic(name: str) -> bool:
    n = clean_name(name)
    c = compact(n)
    return c in GENERIC_COMPACT or "기타" in n or "합계" == n


def is_asset(name: str) -> bool:
    return compact(clean_name(name)) in ASSET_COMPACT


def is_application_only(name: str) -> bool:
    return compact(clean_name(name)) in APPLICATION_COMPACT


def is_business_division_or_market(name: str) -> bool:
    return compact(clean_name(name)) in BUSINESS_DIVISION_COMPACT


def is_material_or_product_endpoint(name: str) -> bool:
    return compact(clean_name(name)) in MATERIAL_OR_PRODUCT_COMPACT


def is_imprecise_endpoint(name: str) -> bool:
    n = clean_name(name)
    has_list_comma = "," in n and not re.search(
        r"\b(Inc|Incorporated|Ltd|Limited|Co|Corp|Corporation|LLC|GmbH|Pte)\b",
        n,
        re.IGNORECASE,
    )
    return bool(
        re.search(r"(\s|^)(등|외)$", n)
        or n.endswith(" 등")
        or n.endswith(" 외")
        or has_list_comma
        or " 업체" in n
        or " 시장" in n
        or "사업부" in n
        or "고객사" in n
        or "제조사" in n
        or "제품군" in n
        or "Big Customer" in n
        or n in {"고객", "당사"}
    )


def is_pipe_delimited_table_list(name: str) -> bool:
    n = clean_name(name)
    if "|" not in n:
        return False
    parts = [clean_name(p) for p in re.split(r"\s*\|\s*", n) if clean_name(p)]
    return len(parts) >= 3 and (len(n) > 80 or PIPE_TABLE_HEADER_RE.search(n) is not None)


def split_name_list(name: str) -> list[str]:
    n = clean_name(name)
    if not n:
        return []
    if "|" in n and not is_pipe_delimited_table_list(n):
        parts = [clean_name(p) for p in re.split(r"\s*\|\s*", n) if clean_name(p)]
        if 1 < len(parts) <= 4:
            return parts
    if "," not in n:
        return [n] if n else []
    if re.search(r"\b(Inc|Incorporated|Ltd|Limited|Co|Corp|Corporation|LLC|GmbH|Pte)\b", n, re.I):
        return [n]
    parts = [clean_name(p) for p in re.split(r"\s*,\s*", n) if clean_name(p)]
    return parts or [n]


def is_non_org_supply_endpoint(name: str) -> bool:
    return (
        is_generic(name)
        or is_asset(name)
        or is_application_only(name)
        or is_business_division_or_market(name)
        or is_material_or_product_endpoint(name)
        or is_imprecise_endpoint(name)
    )


def is_finance_or_fund(name: str) -> bool:
    n = clean_name(name)
    return bool(FINANCE_ENDPOINT_RE.search(n) or INVESTMENT_VEHICLE_RE.search(n))


def chunk_texts(corp_code: str) -> dict[str, str]:
    out = {}
    for path in AUTO.glob(f"batch_{corp_code}_*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        for chunk in data.get("chunks", []):
            cid = chunk.get("chunk_id")
            if cid:
                out[cid] = chunk.get("text") or ""
    return out


def reject_reason(edge: dict, text: str, ent_names: set[str]) -> str | None:
    pred = edge.get("predicate", "")
    subj = clean_name(edge.get("subject", ""))
    obj = clean_name(edge.get("object", ""))
    skind = section_kind(text)
    text_low = (text or "").lower()

    if pred not in ALL_PREDICATES:
        return "bad_predicate"
    if not obj or is_generic(obj):
        return "generic_object"
    if subj and is_generic(subj):
        return "generic_subject"
    if is_pipe_delimited_table_list(obj) or (subj and is_pipe_delimited_table_list(subj)):
        return "pipe_delimited_table_list"
    if "및 그 종속기업" in obj or "및 그 종속기업" in subj:
        return "group_level_name"
    if is_finance_or_fund(obj) or (subj and is_finance_or_fund(subj)):
        return "finance_or_investment_endpoint"

    if pred == "hasObject":
        if skind != "business":
            return "hasObject_outside_business"
        if is_asset(obj) or is_application_only(obj):
            return "generic_asset_or_application_object"
        if obj not in ent_names:
            return "hasObject_without_entity"
        return None

    if pred in BUSINESS_PREDICATES:
        if skind != "business":
            return "business_predicate_outside_business_section"
        if pred == "SUPPLIES_TO" and MARKET_TABLE_RE.search(text[:1600]):
            return "market_or_competitor_table_not_supply"
        if FINANCE_TEXT_RE.search(text[:1200]):
            return "business_predicate_finance_context"
        if pred == "SUPPLIES_TO" and LICENSE_OR_CONTRACT_RE.search(text[:1200]):
            return "supply_from_license_or_contract_context"
        if pred in {"PRODUCES", "USES_TECH"} and (is_asset(obj) or is_application_only(obj)):
            return "generic_asset_or_application_object"
        if pred in {"PRODUCES", "USES_TECH"} and obj == "Hybrid Bonder" and "hybrid bonder" not in text_low:
            return "hybrid_bonder_without_exact_evidence"
        if pred == "USES_TECH" and COMPLIANCE_OR_ESG_RE.search(obj + " " + text[:500]):
            return "compliance_or_esg_not_core_technology"
        if pred in {"PRODUCES", "USES_TECH"} and is_business_division_or_market(obj):
            return "business_division_or_market_object"
        if pred == "SUPPLIES_TO" and not BUSINESS_SIGNAL_RE.search(text[:1200]):
            return "supply_without_business_signal"
        if pred == "SUPPLIES_TO" and (
            is_non_org_supply_endpoint(subj) or is_non_org_supply_endpoint(obj)
        ):
            return "non_org_supply_endpoint"
        return None

    if pred == "RELATED_PARTY":
        if skind == "legal":
            return "related_party_from_legal_section"
        if is_asset(obj):
            return "asset_as_related_party"
        return None

    return None


def sanitize_item(item: dict, text: str, corp_name: str = "") -> tuple[dict, list[dict]]:
    entities = []
    ent_seen = set()
    rejected = []
    for ent in item.get("entities", []) or []:
        typ = ent.get("type")
        name = clean_name(ent.get("name", ""))
        if typ not in {"Product", "Technology"}:
            rejected.append({"kind": "entity", "name": name, "reason": "bad_entity_type"})
            continue
        if is_generic(name) or is_asset(name) or is_finance_or_fund(name):
            rejected.append({"kind": "entity", "name": name, "reason": "noise_entity"})
            continue
        key = (typ, compact(name))
        if key in ent_seen:
            continue
        ent_seen.add(key)
        entities.append({"type": typ, "name": name})

    ent_names = {e["name"] for e in entities}
    edges = []
    edge_seen = set()
    for edge in item.get("edges", []) or []:
        base = {
            "subject": clean_name(edge.get("subject", "")),
            "predicate": edge.get("predicate", ""),
            "object": clean_name(edge.get("object", "")),
        }
        candidates = [base]
        if base["predicate"] == "SUPPLIES_TO":
            subjects = split_name_list(base["subject"])
            objects = split_name_list(base["object"])
            if len(subjects) > 1 or len(objects) > 1:
                candidates = [
                    {"subject": s, "predicate": base["predicate"], "object": o}
                    for s in subjects for o in objects
                ]
        for cleaned in candidates:
            if corp_name and cleaned["subject"] in {"당사", "회사", "연결실체"}:
                cleaned["subject"] = corp_name
            if corp_name and cleaned["object"] in {"당사", "회사", "연결실체"}:
                cleaned["object"] = corp_name
            reason = reject_reason(cleaned, text, ent_names)
            if reason:
                rejected.append({"kind": "edge", **cleaned, "reason": reason})
                continue
            key = (compact(cleaned["subject"]), cleaned["predicate"], compact(cleaned["object"]))
            if key in edge_seen:
                continue
            edge_seen.add(key)
            edges.append(cleaned)

    return {"chunk_id": item.get("chunk_id"), "entities": entities, "edges": edges}, rejected


def sanitize_corp(corp_code: str, *, apply: bool, backup_dir: Path | None,
                  corp_name: str = "") -> tuple[dict, list[dict]]:
    texts = chunk_texts(corp_code)
    summary = collections.Counter()
    rejected_rows = []
    for result_path in sorted(AUTO.glob(f"result_{corp_code}_*.json")):
        data = json.loads(result_path.read_text(encoding="utf-8"))
        new_data = []
        for item in data:
            cid = item.get("chunk_id")
            before_edges = len(item.get("edges") or [])
            before_entities = len(item.get("entities") or [])
            clean, rejected = sanitize_item(item, texts.get(cid, ""), corp_name)
            after_edges = len(clean.get("edges") or [])
            after_entities = len(clean.get("entities") or [])
            summary["chunks"] += 1
            summary["before_edges"] += before_edges
            summary["after_edges"] += after_edges
            summary["removed_edges"] += before_edges - after_edges
            summary["before_entities"] += before_entities
            summary["after_entities"] += after_entities
            summary["removed_entities"] += before_entities - after_entities
            for row in rejected:
                row = {"corp_code": corp_code, "result_file": result_path.name, "chunk_id": cid, **row}
                rejected_rows.append(row)
                summary[f"reject:{row['reason']}"] += 1
            new_data.append(clean)
        if apply:
            assert backup_dir is not None
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(result_path, backup_dir / result_path.name)
            result_path.write_text(json.dumps(new_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return dict(summary), rejected_rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corp_codes", nargs="*", help="corp codes. Defaults to all result files")
    ap.add_argument("--apply", action="store_true", help="overwrite result files after backup")
    args = ap.parse_args()

    names = corp_names()
    codes = args.corp_codes or discover_codes()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = AUTO / f"backup_results_{stamp}" if args.apply else None

    all_summary = []
    all_rejected = []
    for code in codes:
        name = names.get(code, "")
        summary, rejected = sanitize_corp(code, apply=args.apply, backup_dir=backup_dir,
                                          corp_name=name)
        summary = {"corp_code": code, "corp_name": name, **summary}
        all_summary.append(summary)
        all_rejected.extend(rejected)

    mode = "applied" if args.apply else "dry_run"
    summary_path = AUTO / f"sanitize_{mode}_summary.json"
    csv_path = AUTO / f"sanitize_{mode}_summary.csv"
    rejected_path = AUTO / f"sanitize_{mode}_rejected.jsonl"

    summary_path.write_text(json.dumps(all_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    keys = [
        "corp_code", "corp_name", "chunks", "before_edges", "after_edges", "removed_edges",
        "before_entities", "after_entities", "removed_entities",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys)
        writer.writeheader()
        for row in all_summary:
            writer.writerow({k: row.get(k, 0) for k in keys})
    with rejected_path.open("w", encoding="utf-8") as fh:
        for row in all_rejected:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    totals = {
        "mode": mode,
        "corp_count": len(all_summary),
        "before_edges": sum(x.get("before_edges", 0) for x in all_summary),
        "after_edges": sum(x.get("after_edges", 0) for x in all_summary),
        "removed_edges": sum(x.get("removed_edges", 0) for x in all_summary),
        "before_entities": sum(x.get("before_entities", 0) for x in all_summary),
        "after_entities": sum(x.get("after_entities", 0) for x in all_summary),
        "removed_entities": sum(x.get("removed_entities", 0) for x in all_summary),
        "backup_dir": str(backup_dir) if backup_dir else None,
    }
    print(json.dumps(totals, ensure_ascii=False, indent=2))
    print(f"summary json: {summary_path}")
    print(f"summary csv : {csv_path}")
    print(f"rejected    : {rejected_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
