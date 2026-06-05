"""Ollama local extractor for auto_runner batches.

Reads graph/_auto/batch_<corp>_<n>.json and writes:
  - graph/_auto/result_<corp>_<n>.json  (auto_runner.py load input)
  - graph/_auto/review_<corp>_<n>.jsonl (pre-load inspection trail)

This script does not write to Neo4j/MariaDB.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import httpx

from db import normalize_corp_name
from sanitize_ollama_results import sanitize_item as sanitize_result_item

HERE = Path(__file__).resolve().parent
AUTO = HERE / "_auto"

ALLOWED_PREDS = {"PRODUCES", "USES_TECH", "SUPPLIES_TO", "RELATED_PARTY", "hasObject"}
ALLOWED_ENTITY_TYPES = {"Product", "Technology"}
BLOCKED_EXACT_NAMES = {
    "기타",
    "기타 관계기업",
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
BLOCKED_COMPACT_NAMES = {re.sub(r"\s+", "", x.lower()) for x in BLOCKED_EXACT_NAMES}
BLOCKED_ENDPOINT_RE = re.compile(
    r"(은행|Bank|Branch|보증보험|증권|채권자|차입|채무보증|담보|시설자금|운영자금)",
    re.IGNORECASE,
)

SYSTEM = (
    "너는 한국 DART 공시 본문에서 지식그래프용 JSON만 출력하는 엄격한 추출기다. "
    "본문에 없는 회사명, 제품명, 기술명은 절대 만들지 않는다. 추론, 일반상식, 약어 확장 금지."
)

USER_TEMPLATE = """공시 주체(subject) = "{subject}".

출력은 JSON object 하나만:
{{"entities":[{{"type":"Product|Technology","name":"..."}}],
  "edges":[{{"subject":"...","predicate":"PRODUCES|USES_TECH|SUPPLIES_TO|RELATED_PARTY|hasObject","object":"..."}}]}}

규칙:
1. name, subject, object는 반드시 본문에 그대로 등장한 표면형이거나 공시 주체 "{subject}"여야 한다.
2. Product는 구체 제품·부품·원자재·장비·서비스명이다.
3. Technology는 구체 기술·공정·플랫폼·form factor다.
4. SUPPLIES_TO는 실제 공급 방향이다.
   - 주요 매출처/고객사: "{subject}" -> 고객사
   - 주요 매입처/공급사: 공급사 -> "{subject}"
5. PRODUCES/USES_TECH의 subject는 "{subject}"만 허용한다.
6. 이름 없는 관계("6개사", "다수 업체")는 출력하지 않는다.
7. FPCA를 FPGA로 바꾸지 마라. 약어를 임의로 풀어 쓰지 마라.
8. 확실한 관계가 없으면 빈 배열을 출력한다.

본문:
{text}
"""


def strip_code_fence(text: str) -> str:
    s = (text or "").strip()
    if s.startswith("```"):
        parts = s.split("```")
        if len(parts) >= 3:
            s = parts[1]
            if s.lstrip().lower().startswith("json"):
                s = s.lstrip()[4:]
    return s.strip()


def parse_json_response(text: str) -> dict:
    s = strip_code_fence(text)
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        start = s.find("{")
        end = s.rfind("}")
        if start < 0 or end <= start:
            raise
        obj = json.loads(s[start : end + 1])
    if isinstance(obj, list):
        obj = obj[0] if obj else {}
    if not isinstance(obj, dict):
        return {}
    return obj


def compact(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").lower())


def is_blocked_name(name: str) -> bool:
    n = (name or "").strip()
    if not n:
        return True
    if n in BLOCKED_EXACT_NAMES or compact(n) in BLOCKED_COMPACT_NAMES:
        return True
    return len(n) <= 1


def is_finance_endpoint(name: str) -> bool:
    return bool(BLOCKED_ENDPOINT_RE.search(name or ""))


def is_subject_name(name: str, subject: str) -> bool:
    return normalize_corp_name(name) == normalize_corp_name(subject)


def anchored(name: str, text: str, subject: str) -> bool:
    if not name:
        return False
    if is_subject_name(name, subject):
        return True
    low_name = name.lower().strip()
    low_text = (text or "").lower()
    if low_name in low_text:
        return True
    return compact(name) in compact(text)


def clean_item(raw: dict, *, chunk_id: str, subject: str, text: str) -> tuple[dict, dict]:
    entities = []
    entity_names = set()
    rejected = []

    for ent in raw.get("entities", []) or []:
        if not isinstance(ent, dict):
            continue
        typ = (ent.get("type") or "").strip()
        name = (ent.get("name") or "").strip()
        if typ not in ALLOWED_ENTITY_TYPES:
            rejected.append({"kind": "entity", "name": name, "reason": "bad_type"})
            continue
        if not name or len(name) > 80 or "\n" in name:
            rejected.append({"kind": "entity", "name": name, "reason": "bad_name"})
            continue
        if is_blocked_name(name) or is_finance_endpoint(name):
            rejected.append({"kind": "entity", "name": name, "reason": "blocked_noise"})
            continue
        if not anchored(name, text, subject):
            rejected.append({"kind": "entity", "name": name, "reason": "not_in_text"})
            continue
        entities.append({"type": typ, "name": name})
        entity_names.add(name)

    edges = []
    for edge in raw.get("edges", []) or []:
        if not isinstance(edge, dict):
            continue
        subj = (edge.get("subject") or "").strip()
        pred = (edge.get("predicate") or "").strip()
        obj = (edge.get("object") or "").strip()

        def reject(reason: str):
            rejected.append({
                "kind": "edge", "subject": subj, "predicate": pred,
                "object": obj, "reason": reason,
            })

        if pred not in ALLOWED_PREDS:
            reject("bad_predicate")
            continue
        if is_blocked_name(obj) or (subj and is_blocked_name(subj)):
            reject("blocked_noise")
            continue
        if pred == "hasObject":
            if not obj or (obj not in entity_names and not anchored(obj, text, subject)):
                reject("object_not_in_text")
                continue
            edges.append({"subject": "CHUNK", "predicate": pred, "object": obj})
            continue
        if not subj or not obj:
            reject("missing_endpoint")
            continue
        if compact(subj) == compact(obj):
            reject("self_loop")
            continue
        if pred in {"PRODUCES", "USES_TECH"}:
            if not is_subject_name(subj, subject):
                reject("subject_must_be_filing_company")
                continue
            if is_finance_endpoint(obj):
                reject("finance_noise")
                continue
            if obj not in entity_names and not anchored(obj, text, subject):
                reject("object_not_in_text")
                continue
            edges.append({"subject": subject, "predicate": pred, "object": obj})
            continue
        if pred in {"SUPPLIES_TO", "RELATED_PARTY"}:
            if pred == "SUPPLIES_TO" and (is_finance_endpoint(subj) or is_finance_endpoint(obj)):
                reject("finance_endpoint")
                continue
            if not anchored(subj, text, subject) or not anchored(obj, text, subject):
                reject("endpoint_not_in_text")
                continue
            edges.append({"subject": subj, "predicate": pred, "object": obj})

    clean = {"chunk_id": chunk_id, "entities": entities, "edges": edges}
    clean, rule_rejected = sanitize_result_item(clean, text, subject)
    if rule_rejected:
        rejected.extend({**item, "stage": "sanitize_rules"} for item in rule_rejected)
    review = {
        "chunk_id": chunk_id,
        "raw_entities": raw.get("entities", []),
        "raw_edges": raw.get("edges", []),
        "clean_entities": clean["entities"],
        "clean_edges": clean["edges"],
        "rejected": rejected,
        "text_preview": re.sub(r"\s+", " ", text or "")[:300],
    }
    return clean, review


def call_ollama(client: httpx.Client, *, base: str, model: str, subject: str, text: str) -> dict:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER_TEMPLATE.format(subject=subject, text=text)},
        ],
        "stream": False,
        "format": "json",
        "think": False,
        "options": {
            "temperature": 0,
            "top_p": 0.1,
            "num_predict": 1024,
        },
    }
    r = client.post(f"{base.rstrip('/')}/api/chat", json=payload)
    r.raise_for_status()
    data = r.json()
    content = ((data.get("message") or {}).get("content") or data.get("response") or "").strip()
    return parse_json_response(content)


def process_batch(path: Path, *, base: str, model: str, timeout: int) -> tuple[int, int, int]:
    batch = json.loads(path.read_text(encoding="utf-8"))
    subject = batch["subject"]
    chunks = batch.get("chunks", [])
    result_path = path.with_name(path.name.replace("batch_", "result_"))
    review_path = path.with_name(path.name.replace("batch_", "review_").replace(".json", ".jsonl"))

    results = []
    n_edge = 0
    n_reject = 0
    with httpx.Client(timeout=timeout) as client, review_path.open("w", encoding="utf-8") as review_file:
        for i, chunk in enumerate(chunks, 1):
            cid = chunk["chunk_id"]
            text = chunk.get("text") or ""
            try:
                raw = call_ollama(client, base=base, model=model, subject=subject, text=text)
                clean, review = clean_item(raw, chunk_id=cid, subject=subject, text=text)
            except Exception as e:  # noqa: BLE001
                clean = {"chunk_id": cid, "entities": [], "edges": []}
                review = {
                    "chunk_id": cid,
                    "error": str(e),
                    "clean_entities": [],
                    "clean_edges": [],
                    "rejected": [{"kind": "chunk", "reason": "model_or_parse_error"}],
                    "text_preview": re.sub(r"\s+", " ", text)[:300],
                }
            results.append(clean)
            n_edge += len(clean["edges"])
            n_reject += len(review.get("rejected", []))
            review_file.write(json.dumps(review, ensure_ascii=False) + "\n")
            print(f"  {path.name} {i}/{len(chunks)} {cid}: edges={len(clean['edges'])} rejected={len(review.get('rejected', []))}")

    result_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(chunks), n_edge, n_reject


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corp_code")
    ap.add_argument("--model", default="qwen3.5:9b")
    ap.add_argument("--base", default="http://localhost:11434")
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args()

    batches = sorted(AUTO.glob(f"batch_{args.corp_code}_*.json"))
    if not batches:
        print(f"batch 없음: {AUTO / ('batch_' + args.corp_code + '_*.json')}")
        return 1

    total_chunks = total_edges = total_rejected = 0
    for batch in batches:
        n_chunk, n_edge, n_reject = process_batch(
            batch, base=args.base, model=args.model, timeout=args.timeout
        )
        total_chunks += n_chunk
        total_edges += n_edge
        total_rejected += n_reject

    print("\n=== ollama_extract summary ===")
    print(f"model={args.model}")
    print(f"chunks={total_chunks} clean_edges={total_edges} rejected={total_rejected}")
    print(f"review: {AUTO / ('review_' + args.corp_code + '_*.jsonl')}")
    print(f"result: {AUTO / ('result_' + args.corp_code + '_*.json')}")
    print("검수 후 적재: uv run python graph/auto_runner.py load " + args.corp_code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
