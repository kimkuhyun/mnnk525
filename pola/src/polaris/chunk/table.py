"""Stage C-1: 표 청킹 (DART JSON → 휴리스틱 NL).

입력: ___test/2_Chuck/01_filtered/{corp}/dart/*.json (3,010 파일)
출력: ___test/2_Chuck/03_chunks/{corp}/table_nl.jsonl

각 청크 = 3 필드 분리 (Pipeline 03 §B-8):
- embedding_text: 본문만 (Qdrant 벡터)
- llm_context_text: prefix + 본문 + suffix(rcept_no·chunk_id·anchor)
- payload: corp_code·rcept_no·bsns_year·hash16 등 (필터·정렬용)

chunk_id = hash16(corp + rcept + section_path + offset + content_sha1) — Pipeline 03 §B-3
"""
from __future__ import annotations
import json, time, glob
from pathlib import Path
from collections import Counter, defaultdict

from polaris.chunk.lib.heuristics_table import CONVERTERS, safe_year, parse_doc_type
from polaris.chunk.lib.natural_keys_v2 import chunk_id_table
from polaris.chunk.lib.lexicon import apply_lexicon
from polaris.chunk.lib.version import PIPELINE_VERSION, SCHEMA_VERSION, LEXICON_VERSION
from polaris.config import CORPS, CORP_NAMES, FILTERED_DIR, META_DIR, CHUNKS_DIR

FILTERED = FILTERED_DIR
META = META_DIR
OUT = CHUNKS_DIR
LOG = OUT / "_c1_log.jsonl"


import re as _re_post
_NONE_TOKEN_RE = _re_post.compile(r"(\b)None(\b)")
MIN_CONTENT_LEN = 30  # 너무 짧은 청크 skip 기준


def _resolve_bsns_year_reprt_fs(item: dict, doc_meta: dict) -> tuple[int | None, str | None, str | None]:
    """payload 3 필드(bsns_year·reprt_code·fs_div) 결정 — 우선순위 명시.

    bsns_year: item.safe_year > doc_type 파싱 > None (0 금지)
    reprt_code: item.reprt_code > doc_type 파싱 > None
    fs_div: item.fs_div > None
    결정공시·이벤트 endpoint 는 보고서 연도 개념이 없으므로 None 으로 명시 — Qdrant 필터 시 "값 없음" 정직히 표현.
    """
    year_from_item = safe_year(item)  # 0 if not found
    parsed = parse_doc_type(doc_meta.get("doc_type", "")) if doc_meta else {}

    if year_from_item:
        bsns_year: int | None = year_from_item
    elif parsed.get("bsns_year"):
        bsns_year = parsed["bsns_year"]
    else:
        bsns_year = None

    item_reprt = (item.get("reprt_code") or "").strip() if item.get("reprt_code") else ""
    if item_reprt:
        reprt_code: str | None = item_reprt
    elif parsed.get("reprt_code"):
        reprt_code = parsed["reprt_code"]
    else:
        reprt_code = None

    item_fs = (item.get("fs_div") or "").strip() if item.get("fs_div") else ""
    fs_div: str | None = item_fs if item_fs else None

    return bsns_year, reprt_code, fs_div


def build_chunk(corp_code: str, corp_name: str, item: dict, endpoint: str,
                row_offset: int, variant: str, content: str,
                section_path: list[str], extra_meta: dict,
                raw_path: str, doc_meta: dict | None = None) -> dict | None:
    """단일 청크 → 3 필드 분리 dict."""
    rcept_no = item.get("rcept_no", "")
    bsns_year, reprt_code, fs_div = _resolve_bsns_year_reprt_fs(item, doc_meta or {})

    # None 잔존 후처리 — raw "None" → "(공시되지 않음)"
    content = _NONE_TOKEN_RE.sub(r"\1(공시되지 않음)\2", content)
    # 단어집 + 단위 정규화 (B-7)
    content = apply_lexicon(content)
    # 의미 있는 본문이 아니면 skip (length 또는 "(공시되지 않음)"만 가득한 경우)
    meaningful = content.replace("(공시되지 않음)", "").replace(",", "").replace(".", "").strip()
    if len(meaningful) < MIN_CONTENT_LEN:
        return None
    cid = chunk_id_table(corp_code, rcept_no, endpoint, row_offset, variant, content)

    # prefix·suffix (llm_context_text 전용)
    sp_str = "/".join(section_path) if section_path else ""
    year_label = str(bsns_year) if bsns_year else "공시일자"
    prefix = f"[{corp_name}({corp_code}) · {year_label} · {endpoint}/{variant}]"
    suffix = (f"(rcept_no={rcept_no}, chunk_id={cid}, "
              f"anchor={{section_path: '{sp_str}', endpoint: '{endpoint}', "
              f"row_offset: {row_offset}, variant: '{variant}'}}, "
              f"source=DART_{endpoint})")
    llm_ctx = f"{prefix}\n{content}\n{suffix}"

    # Contextual Retrieval (Anthropic 2024 표준): embedding_text 에 회사·연도·endpoint
    # prefix → 정형 쿼리("회사명 + 연도 + 계정명") 와 매칭 강화.
    # 본문 content 에는 이미 "항목 'XXX'" 형태로 계정명 포함됨.
    embed_prefix = f"{corp_name} {year_label} {endpoint}/{variant}".strip()
    embedding_text = f"{embed_prefix}\n\n{content}"

    payload = {
        "corp_code": corp_code,
        "corp_name": corp_name,
        "rcept_no": rcept_no,
        "bsns_year": bsns_year,
        "reprt_code": reprt_code,
        "fs_div": fs_div,
        "endpoint": endpoint,
        "variant": variant,
        "section_path": section_path,
        "row_offset": row_offset,
        "chunk_type": "table_nl",
        "source_endpoint": endpoint,
        "raw_landing_path": raw_path,
        "pipeline_version": PIPELINE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "lexicon_version": LEXICON_VERSION,
    }
    payload.update(extra_meta or {})

    return {
        "chunk_id": cid,
        "chunk_type": "table_nl",
        "embedding_text": embedding_text,
        "llm_context_text": llm_ctx,
        "payload": payload,
    }


def load_doc_index() -> dict:
    """document_index.jsonl → {rcept_no: row}. 표 청크 payload 의
    bsns_year/reprt_code 백필용 (item 에 raw 값이 없을 때 doc_type 파싱)."""
    out: dict = {}
    p = META / "document_index.jsonl"
    if p.is_file():
        with p.open(encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                rno = row.get("rcept_no")
                if rno:
                    out[rno] = row
    return out


def process_corp(corp_code: str, doc_idx: dict) -> tuple[list[dict], Counter, Counter]:
    """corp dart/ 모두 → 청크 list."""
    corp_name = CORP_NAMES[corp_code]
    dart_dir = FILTERED / corp_code / "dart"
    chunks = []
    ep_counter = Counter()       # endpoint별 청크 수
    skip_counter = Counter()     # 미매핑 endpoint 카운트

    if not dart_dir.is_dir():
        return chunks, ep_counter, skip_counter

    for jf in sorted(dart_dir.glob("*.json")):
        endpoint = jf.stem.split("__")[0]
        if endpoint not in CONVERTERS:
            skip_counter[endpoint] += 1
            continue
        try:
            payload_data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if payload_data.get("status") != "ok":
            continue
        items = (payload_data.get("data") or {}).get("list") or []
        if not items:
            continue

        converter = CONVERTERS[endpoint]
        from polaris.config import DATA_ROOT as _DR
        try:
            raw_path = str(jf.relative_to(_DR).as_posix())
        except ValueError:
            raw_path = str(jf.as_posix())

        for i, item in enumerate(items):
            try:
                sub_chunks = converter(corp_name, item)
            except Exception:
                continue
            doc_meta = doc_idx.get(item.get("rcept_no", ""), {})
            for sc in sub_chunks:
                chunk = build_chunk(
                    corp_code=corp_code,
                    corp_name=corp_name,
                    item=item,
                    endpoint=endpoint,
                    row_offset=i,
                    variant=sc["variant"],
                    content=sc["content"],
                    section_path=sc["section_path"],
                    extra_meta=sc["extra_meta"],
                    raw_path=raw_path,
                    doc_meta=doc_meta,
                )
                if chunk is None:
                    continue
                chunks.append(chunk)
                ep_counter[endpoint] += 1

    return chunks, ep_counter, skip_counter


def main():
    import re as _re; globals()['re'] = _re  # build_chunk에서 사용
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)

    doc_idx = load_doc_index()
    print(f"document_index loaded: {len(doc_idx)} docs (bsns_year/reprt_code 백필용)")

    total_chunks = 0
    log_lines = []
    overall_ep = Counter()
    overall_skip = Counter()

    for corp in CORPS:
        name = CORP_NAMES[corp]
        chunks, ep_c, skip_c = process_corp(corp, doc_idx)
        out_jsonl = OUT / corp / "table_nl.jsonl"
        out_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with out_jsonl.open("w", encoding="utf-8") as f:
            for ch in chunks:
                f.write(json.dumps(ch, ensure_ascii=False) + "\n")
        total_chunks += len(chunks)
        overall_ep.update(ep_c)
        overall_skip.update(skip_c)
        # endpoint별 분포 로그
        log_lines.append({"corp": corp, "name": name,
                           "chunks": len(chunks), "by_endpoint": dict(ep_c),
                           "skipped_endpoints": dict(skip_c)})
        print(f"  {name}: {len(chunks)} 청크 ({len(ep_c)} endpoint)")

    with LOG.open("w", encoding="utf-8") as f:
        for line in log_lines:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    elapsed = time.time() - t0
    print(f"\n=== Stage C-1 완료 ({elapsed:.1f}s) ===")
    print(f"  총 청크: {total_chunks}")
    print(f"  처리 endpoint: {len(overall_ep)}")
    print(f"  미매핑 endpoint: {len(overall_skip)} (스킵)")
    print(f"  Top 10 endpoint:")
    for ep, n in overall_ep.most_common(10):
        print(f"    {ep}: {n}")
    if overall_skip:
        print(f"  미매핑 (CONVERTERS에 없음):")
        for ep, n in overall_skip.most_common(10):
            print(f"    {ep}: {n}")

    # manifest
    from polaris.config import DATA_ROOT as _DR
    manifest = _DR / "2_Chuck" / "_manifest.json"
    m = {}
    if manifest.exists():
        try: m = json.loads(manifest.read_text(encoding="utf-8"))
        except: m = {}
    m["stage_c1"] = {
        "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_sec": elapsed,
        "total_chunks": total_chunks,
        "by_endpoint": dict(overall_ep),
        "skipped": dict(overall_skip),
    }
    manifest.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
