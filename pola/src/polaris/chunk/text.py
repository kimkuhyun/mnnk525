"""Stage C-2: 텍스트 시맨틱 청킹.

입력: ___test/2_Chuck/01_filtered/{corp}/body_clean/{rcept_no}.txt (135건)
출력:
  - ___test/2_Chuck/03_chunks/{corp}/text.jsonl (텍스트 청크)
  - ___test/2_Chuck/03_chunks/{corp}/text_meta.jsonl (parent_summary)

처리:
1. body_clean.txt → extract_sections (화이트리스트 II·III.4·IV·V·XI)
2. 각 섹션 → micro 청크 (≤1,500 토큰)
3. 3,000 토큰 초과 시 semchunk로 의미 분할 + parent_summary (llm_context_text만)
4. 3 필드 분리 (embedding_text·llm_context_text·payload)
"""
from __future__ import annotations
import json, time
from pathlib import Path
from collections import Counter

from polaris.chunk.lib.html_chapter import extract_sections
from polaris.chunk.lib.semantic_split import count_tokens, split_semantic
from polaris.chunk.lib.natural_keys_v2 import chunk_id_text
from polaris.chunk.lib.lexicon import apply_lexicon
from polaris.chunk.lib.pdf_page_index import find_page
from polaris.chunk.lib.version import (PIPELINE_VERSION, SCHEMA_VERSION,
                                         LEXICON_VERSION, CHUNKER_VERSION)
from polaris.config import (CORPS, CORP_NAMES, DATA_ROOT,
                              FILTERED_DIR, META_DIR, CHUNKS_DIR)

RAW = DATA_ROOT / "rawData"
CLEAN = FILTERED_DIR
META = META_DIR
OUT = CHUNKS_DIR

MICRO_MAX = 1500
MACRO_MAX = 3000  # semchunk 분할 임계


def load_doc_index() -> dict:
    """document_index.jsonl → {rcept_no: row}."""
    out = {}
    p = META / "document_index.jsonl"
    if p.is_file():
        with p.open(encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                out[row["rcept_no"]] = row
    return out


def build_text_chunk(corp_code: str, corp_name: str, rcept_no: str,
                      doc_meta: dict, section_path: list[str], headings: list[str],
                      offset: int, content: str, total_token: int,
                      is_split: bool = False, split_idx: int = 0,
                      parent_summary: str = "",
                      pdf_path: Path | None = None) -> dict:
    # 단어집 + 단위 정규화 (B-7)
    content = apply_lexicon(content)
    cid = chunk_id_text(corp_code, rcept_no, section_path + [str(split_idx)], offset, content)
    sp_str = "-".join(section_path) + (f"#{split_idx}" if is_split else "")

    # F11: PDF 페이지 매핑 (best-effort)
    pdf_page = find_page(pdf_path, content) if pdf_path else None

    prefix = f"[{corp_name}({corp_code}) · {doc_meta.get('doc_type','')} · {sp_str}]"
    page_str = f", page: {pdf_page}" if pdf_page else ""
    suffix = (f"(rcept_no={rcept_no}, chunk_id={cid}, "
              f"anchor={{section_path: '{'/'.join(section_path)}', "
              f"offset: {offset}, split_idx: {split_idx}{page_str}}}, "
              f"source=DART_body.html)")
    if is_split and parent_summary:
        llm_ctx = f"{prefix}\n[부모 섹션 요약: {parent_summary}]\n{content}\n{suffix}"
    else:
        llm_ctx = f"{prefix}\n{content}\n{suffix}"

    # Contextual Retrieval (Anthropic 2024 표준): embedding_text 에 회사·문서·섹션 헤더
    # prefix → 자유서술 쿼리("회사명 + 섹션 헤더")와의 의미 매칭 향상.
    # 기존엔 content 만 임베딩되어 "1. 사업의 개요" 같은 섹션 신호가 벡터에 없었음.
    heading_str = " > ".join(headings) if headings else sp_str
    embed_prefix = f"{corp_name} {doc_meta.get('doc_type', '')} {heading_str}".strip()
    embedding_text = f"{embed_prefix}\n\n{content}"

    payload = {
        "corp_code": corp_code,
        "corp_name": corp_name,
        "rcept_no": rcept_no,
        "doc_type": doc_meta.get("doc_type", ""),
        "date": doc_meta.get("date", ""),
        "section_path": section_path,
        "section_headings": headings,
        "offset": offset,
        "split_idx": split_idx,
        "is_split": is_split,
        "token_count": count_tokens(content),
        "chunk_type": "text_micro" if total_token <= MICRO_MAX else "text_macro",
        "anchor": {
            "section_path": "/".join(section_path),
            "section_headings": headings,
            "line_offset": offset,
            "split_idx": split_idx,
            "pdf_page": pdf_page,  # None if no match
        },
        "pipeline_version": PIPELINE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "lexicon_version": LEXICON_VERSION,
        "chunker_version": CHUNKER_VERSION,
    }
    return {
        "chunk_id": cid,
        "chunk_type": payload["chunk_type"],
        "embedding_text": embedding_text,
        "llm_context_text": llm_ctx,
        "payload": payload,
    }


def process_corp(corp_code: str, doc_idx: dict) -> tuple[list[dict], list[dict], Counter]:
    """corp body_clean 처리 → (text chunks, text_meta, stats)."""
    corp_name = CORP_NAMES[corp_code]
    body_dir = CLEAN / corp_code / "body_clean"
    chunks, metas = [], []
    stats = Counter()

    if not body_dir.is_dir():
        return chunks, metas, stats

    for body_path in sorted(body_dir.glob("*.txt")):
        rno = body_path.stem
        doc_meta = doc_idx.get(rno, {})
        body = body_path.read_text(encoding="utf-8")
        sections = extract_sections(body)
        stats["docs"] += 1
        stats["sections"] += len(sections)

        # F11: PDF 경로 (best-effort 페이지 매핑)
        pdf_path = RAW / corp_code / "documents" / rno / "original.pdf"
        if not pdf_path.is_file():
            pdf_path = None

        for sec_offset, sec in enumerate(sections):
            sec_text = sec["text"]
            sec_tokens = count_tokens(sec_text)

            if sec_tokens <= MACRO_MAX:
                ch = build_text_chunk(corp_code, corp_name, rno, doc_meta,
                                       sec["section_path"], sec["headings"],
                                       sec_offset, sec_text, sec_tokens,
                                       is_split=False, pdf_path=pdf_path)
                chunks.append(ch)
                stats["micro" if sec_tokens <= MICRO_MAX else "macro"] += 1
            else:
                parts = split_semantic(sec_text, MACRO_MAX)
                p_sum = (doc_meta.get("summary_short", "") or sec_text[:200]).strip()
                metas.append({
                    "rcept_no": rno, "corp_code": corp_code,
                    "section_path": sec["section_path"],
                    "section_headings": sec["headings"],
                    "parent_token_count": sec_tokens,
                    "parent_summary": p_sum,
                    "split_count": len(parts),
                })
                for si, part in enumerate(parts):
                    ch = build_text_chunk(corp_code, corp_name, rno, doc_meta,
                                           sec["section_path"], sec["headings"],
                                           sec_offset, part, count_tokens(part),
                                           is_split=True, split_idx=si,
                                           parent_summary=p_sum,
                                           pdf_path=pdf_path)
                    chunks.append(ch)
                stats["split"] += 1
                stats["split_chunks"] += len(parts)

    return chunks, metas, stats


def main():
    t0 = time.time()
    doc_idx = load_doc_index()
    print(f'document_index loaded: {len(doc_idx)} docs')

    OUT.mkdir(parents=True, exist_ok=True)
    overall_stats = Counter()
    total_chunks = 0

    for corp in CORPS:
        name = CORP_NAMES[corp]
        chunks, metas, stats = process_corp(corp, doc_idx)
        out_text = OUT / corp / "text.jsonl"
        out_meta = OUT / corp / "text_meta.jsonl"
        out_text.parent.mkdir(parents=True, exist_ok=True)
        with out_text.open("w", encoding="utf-8") as f:
            for ch in chunks:
                f.write(json.dumps(ch, ensure_ascii=False) + "\n")
        with out_meta.open("w", encoding="utf-8") as f:
            for m in metas:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")
        total_chunks += len(chunks)
        overall_stats.update(stats)
        print(f"  {name}: {stats['docs']} 문서, {stats['sections']} 섹션 → "
              f"{len(chunks)} 청크 (micro {stats['micro']}, macro {stats['macro']}, "
              f"split {stats['split']}->{stats['split_chunks']})")

    elapsed = time.time() - t0
    print(f"\n=== Stage C-2 완료 ({elapsed:.1f}s) ===")
    print(f"  총 청크: {total_chunks}")
    print(f"  통계: {dict(overall_stats)}")

    # manifest
    manifest = DATA_ROOT / "2_Chuck" / "_manifest.json"
    m = {}
    if manifest.exists():
        try: m = json.loads(manifest.read_text(encoding="utf-8"))
        except: m = {}
    m["stage_c2"] = {
        "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_sec": elapsed,
        "total_chunks": total_chunks,
        "stats": dict(overall_stats),
    }
    manifest.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
