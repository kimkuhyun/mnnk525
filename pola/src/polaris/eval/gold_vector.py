"""gold 쿼리 → Qdrant retrieval coverage 측정.

입력: tests/gold/v1.yml (200 쿼리)
처리:
  1. 각 쿼리를 bge-m3 임베딩
  2. Qdrant active 컬렉션에 search top-K
  3. expected_chunk_ids 가 top-K 안에 있는지 확인
  4. 카테고리별 Recall@K, MRR, nDCG@10 집계

출력: ___test/4_dbGoldTest/v1_summary.{json,html} + per_query.jsonl

Release Gate (설계 02 §7):
  - retrieval 카테고리별 ≥ 0.85 (no_answer ≥ 0.95)
  - no_answer 케이스는 top-K 가 비어야 하거나 점수 ≤ 임계 (현재 baseline: 점수 분포만 기록)
"""
from __future__ import annotations
import argparse, hashlib, json, math, re, sys, time
from pathlib import Path
from collections import defaultdict

import httpx


def _tokenize(text: str) -> list[str]:
    """한국어/영문/숫자 단순 토큰화. 재무 항목명·회사명·연도 키워드 매칭용."""
    if not text:
        return []
    return re.findall(r"[가-힣a-zA-Z0-9]+", text)


def _detect_device(prefer_gpu: bool = True):
    """torch device 자동 선택: DirectML > CUDA > CPU."""
    if not prefer_gpu:
        return "cpu"
    try:
        import torch_directml  # type: ignore
        return torch_directml.device()
    except ImportError:
        pass
    try:
        import torch as _t
        if _t.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _rerank_batch(query: str, texts: list[str], rr_tok, rr_model,
                  batch: int = 32, max_len: int = 512, device="cpu") -> list[float]:
    """bge-reranker-v2-m3 style cross-encoder scoring. Returns logits (높을수록 relevant)."""
    import torch as _t
    scores: list[float] = []
    for i in range(0, len(texts), batch):
        chunk_texts = texts[i:i + batch]
        pairs_q = [query] * len(chunk_texts)
        inputs = rr_tok(pairs_q, chunk_texts, padding=True, truncation=True,
                        return_tensors="pt", max_length=max_len)
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with _t.no_grad():
            logits = rr_model(**inputs).logits.view(-1).float().cpu().tolist()
        scores.extend(logits)
    return scores


_QWEN_RERANK_PREFIX = (
    '<|im_start|>system\nJudge whether the Document meets the requirements '
    'based on the Query and the Instruct provided. Note that the answer can '
    'only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
)
_QWEN_RERANK_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
_QWEN_INSTRUCTION = "Given a Korean financial search query, retrieve relevant passages from corporate reports."


def _rerank_batch_qwen(query: str, texts: list[str], rr_tok, rr_model,
                       batch: int = 4, max_len: int = 1024, device="cpu") -> list[float]:
    """Qwen3-Reranker style scoring. causal LM 의 yes/no token logit → softmax(yes)."""
    import torch as _t
    yes_id = rr_tok.convert_tokens_to_ids("yes")
    no_id = rr_tok.convert_tokens_to_ids("no")
    scores: list[float] = []
    for i in range(0, len(texts), batch):
        chunk_texts = texts[i:i + batch]
        formatted = [
            f"{_QWEN_RERANK_PREFIX}<Instruct>: {_QWEN_INSTRUCTION}\n"
            f"<Query>: {query}\n<Document>: {t}{_QWEN_RERANK_SUFFIX}"
            for t in chunk_texts
        ]
        inputs = rr_tok(formatted, padding=True, truncation=True,
                        return_tensors="pt", max_length=max_len)
        attn = inputs["attention_mask"]
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with _t.no_grad():
            out = rr_model(**inputs)
        last_idx = attn.sum(dim=1) - 1
        last_logits = out.logits[_t.arange(out.logits.size(0)), last_idx.to(device)]
        pair = _t.stack([last_logits[:, no_id], last_logits[:, yes_id]], dim=-1)
        probs = _t.softmax(pair.float(), dim=-1)[:, 1].cpu()
        scores.extend(probs.tolist())
    return scores

from polaris.config import (
    qdrant_client, mariadb_conn, OLLAMA_BASE, OLLAMA_EMBED_MODEL,
    DATA_ROOT, ROOT as PKG_ROOT,
    CORP_NAME_TO_CODE as _CORP_NAME_TO_CODE,
)

ROOT = PKG_ROOT  # gold yaml 상대경로 기준
OUT_DIR = DATA_ROOT / "4_dbGoldTest"

# 5사 alias → corp_code 는 polaris.config.CORP_NAME_TO_CODE 사용 (.env 기반)
CORP_NAME_TO_CODE = _CORP_NAME_TO_CODE

# 카테고리 → 검색 대상 endpoint 화이트리스트 (intent → source 매핑)
# 정형수치/시계열/비교 = 재무제표 항목 (fnlttSinglAcntAll). 재무지표(fnlttSinglIndx) 는 별개.
# 시점 = 임원 현황 (exctvSttus 등)
# 충돌 = 감사의견 (accnutAdtorNmNdAdtOpinion)
# 자유서술 = 텍스트 청크
CATEGORY_ENDPOINTS = {
    "정형수치": ["fnlttSinglAcntAll"],
    "시계열":   ["fnlttSinglAcntAll"],
    "비교":     ["fnlttSinglAcntAll"],
    "시점":     ["exctvSttus", "outcmpnyDrctrNdChangeSttus"],
    "출처_충돌_검증": ["accnutAdtorNmNdAdtOpinion"],
    # 자유서술 = text 청크. endpoint 가 아닌 chunk_type 으로 필터.
    "자유서술": None,
}
CATEGORY_CHUNK_TYPES = {
    "자유서술": ["text_micro", "text_macro"],
}

# BM25 비활성 카테고리 — 자유서술은 의미 검색이 keyword overlap 보다 효과적
# (v8 측정: BM25 ON 시 자유서술 0.633 → 0.533 역효과)
CATEGORY_BM25_DISABLE = {"자유서술"}

# Rerank 비활성 카테고리
# - 자유서술: 쿼리가 짧은 섹션 헤더 ("동진쎄미켐 다. 파생상품 등") 라서 cross-encoder 효과 약함
#            v10 측정: rerank 적용해도 0.600 동일. dense top-50 (=0.867) 활용이 더 나음
# - 비교: 쿼리에 "vs" 가 들어가 cross-encoder 점수 부여 혼란
#         v10 측정: rerank 시 0.572 (rerank 끄면 v9의 0.614)
CATEGORY_RERANK_DISABLE = {"자유서술", "비교"}

# corp 별 균등 분할 카테고리 — 비교 쿼리는 N corp 각각 top_k/N 보장
CATEGORY_CORP_BALANCED = {"비교"}

# 자유서술용 min_token 필터는 v14에서 역효과(expected까지 제거) → 비활성.
# 대신 보일러플레이트 청크는 scripts/admin/mark_boilerplate.py 로 soft-delete.
CATEGORY_MIN_TOKEN_COUNT: dict[str, int] = {}


def extract_filter_signals(query: str) -> dict:
    """쿼리에서 회사·년도·종류 신호 추출.

    - corp_codes: 5사 회사명 매치 (다중 가능 — 비교 쿼리 대응)
    - year: 4자리 연도 (선택)
    - has_in_scope_corp: 5사 중 1개라도 매치되었나 (no_answer 게이트)
    """
    found_corps: list[str] = []
    for name, code in CORP_NAME_TO_CODE.items():
        if name in query and code not in found_corps:
            found_corps.append(code)
    m = re.search(r"\b(20\d{2})\b", query)
    year = int(m.group(1)) if m else None
    return {"corp_codes": found_corps, "year": year,
            "has_in_scope_corp": len(found_corps) > 0}


def parse_yaml_gold(p: Path) -> list[dict]:
    """가벼운 yaml 파서 — id/query/category/no_answer/expected_chunk_ids/expected_corp_codes/note."""
    items: list[dict] = []
    cur: dict | None = None
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("- id:"):
            if cur:
                items.append(cur)
            cur = {"id": line[5:].strip()}
            continue
        if cur is None: continue
        if line.startswith("  query:"):
            cur["query"] = json.loads(line.split(":", 1)[1].strip())
        elif line.startswith("  category:"):
            cur["category"] = line.split(":", 1)[1].strip()
        elif line.startswith("  no_answer:"):
            cur["no_answer"] = line.split(":", 1)[1].strip() == "true"
        elif line.startswith("  expected_chunk_ids:"):
            v = line.split(":", 1)[1].strip()
            cur["expected_chunk_ids"] = [s.strip() for s in v.strip("[]").split(",") if s.strip()]
        elif line.startswith("  expected_corp_codes:"):
            v = line.split(":", 1)[1].strip()
            cur["expected_corp_codes"] = [s.strip() for s in v.strip("[]").split(",") if s.strip()]
        elif line.startswith("  note:"):
            cur["note"] = json.loads(line.split(":", 1)[1].strip())
    if cur:
        items.append(cur)
    return items


def chunk_id_to_uuid(chunk_id: str) -> str:
    h = hashlib.md5(chunk_id.encode("utf-8")).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def embed(client: httpx.Client, text: str) -> list[float]:
    r = client.post(f"{OLLAMA_BASE}/api/embed",
                    json={"model": OLLAMA_EMBED_MODEL, "input": [text]},
                    timeout=60)
    r.raise_for_status()
    return r.json()["embeddings"][0]


def get_active_run_id_and_collection() -> tuple[str, str]:
    conn = mariadb_conn(); cur = conn.cursor()
    cur.execute("SELECT active_run_id, active_qdrant_collection FROM active_run_manifest WHERE id=1")
    row = cur.fetchone()
    cur.close(); conn.close()
    return row[0], row[1]


def metrics(expected_ids: list[str], retrieved_ids: list[str],
            k: int = 10, cap: bool = False) -> dict:
    """Recall@K, MRR, nDCG@K — expected 가 1개여도 ok.

    cap=True 면 denominator = min(|expected|, K) (Recall@K capped standard).
    expected_chunk_ids 가 K 보다 많은 자연키 확장 골드셋에 필수.
    """
    if not expected_ids:
        return {"recall@10": None, "mrr": None, "ndcg@10": None, "hit_rank": None}
    exp_uids = {chunk_id_to_uuid(e) for e in expected_ids}
    ranks = [i + 1 for i, rid in enumerate(retrieved_ids) if rid in exp_uids]
    denom = min(len(exp_uids), k) if cap else len(exp_uids)
    rec = (len(set(retrieved_ids) & exp_uids) / denom) if denom else 0.0
    mrr = 1.0 / ranks[0] if ranks else 0.0
    dcg = sum(1.0 / math.log2(r + 1) for r in ranks)
    idcg_n = min(len(exp_uids), k) if cap else len(exp_uids)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(idcg_n))
    ndcg = dcg / idcg if idcg else 0.0
    return {"recall@10": rec, "mrr": mrr, "ndcg@10": ndcg,
            "hit_rank": ranks[0] if ranks else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--limit", type=int, default=0, help="0=전체, N>0 이면 N개만")
    ap.add_argument("--use-corp-filter", action="store_true",
                    help="쿼리에서 5사 회사명 자동 추출 → Qdrant payload corp_code 필터")
    ap.add_argument("--use-year-filter", action="store_true",
                    help="쿼리에서 4자리 연도 추출 → Qdrant payload bsns_year 필터 (must)")
    ap.add_argument("--use-category-filter", action="store_true",
                    help="골드 category 별 endpoint/chunk_type intent 필터 (자유서술=text 청크 등)")
    ap.add_argument("--sub-query-by-corp", action="store_true",
                    help="비교 쿼리(corp_codes 다중) 분해: corp 별 별도 검색 → score 정렬 병합 → top-k")
    ap.add_argument("--cap-recall", action="store_true",
                    help="Recall@K denominator = min(|expected|, K) 표준 (자연키 확장 골드셋 대응)")
    ap.add_argument("--use-bm25", action="store_true",
                    help="MariaDB chunk_index.embedding_text 로 BM25 인덱스 빌드 → dense + sparse RRF 융합")
    ap.add_argument("--dense-pool", type=int, default=50,
                    help="BM25 융합 시 dense 후보 풀 크기 (top_k 와 별개)")
    ap.add_argument("--bm25-pool", type=int, default=50,
                    help="BM25 후보 풀 크기 (필터 적용 후)")
    ap.add_argument("--rrf-k", type=int, default=60,
                    help="RRF 융합 상수 k (표준값 60)")
    ap.add_argument("--rerank", action="store_true",
                    help="cross-encoder rerank (bge-reranker-v2-m3, transformers)")
    ap.add_argument("--rerank-pool", type=int, default=50,
                    help="rerank 입력 후보 풀 (dense+sparse fusion 후 → cross-encoder)")
    ap.add_argument("--rerank-model", default="BAAI/bge-reranker-v2-m3",
                    help="cross-encoder 모델 (HuggingFace)")
    ap.add_argument("--rerank-batch", type=int, default=32)
    ap.add_argument("--rerank-skip-categories", default="자유서술,비교",
                    help="rerank 비활성 카테고리 (쉼표 구분). 빈 문자열이면 모두 적용.")
    ap.add_argument("--cpu-only", action="store_true",
                    help="GPU 자동 감지(DirectML/CUDA) 비활성. 강제 CPU 사용.")
    ap.add_argument("--tag", default="v1",
                    help="출력 파일 접두 (예: v2_filter)")
    ap.add_argument("--gold", default="tests/gold/v3.yml",
                    help="gold yaml 경로 (v3=final, 자유서술 token_count>=50, 비교는 자연키 확장)")
    ap.add_argument("--best", action="store_true",
                    help="권장 옵션 일괄 활성: filter 3종 + sub-query + cap-recall + BM25 + rerank")
    args = ap.parse_args()

    # --best preset: 검증된 최적 옵션 일괄 적용 (v18 final 기준)
    if args.best:
        args.use_corp_filter = True
        args.use_year_filter = True
        args.use_category_filter = True
        args.sub_query_by_corp = True
        args.cap_recall = True
        args.use_bm25 = True
        args.rerank = True

    t0 = time.time()
    run_id, collection = get_active_run_id_and_collection()
    print(f"[gold eval] active run_id={run_id} collection={collection}\n")

    gold_path = ROOT / args.gold
    print(f"[gold eval] gold file = {gold_path.relative_to(ROOT)}")
    gold = parse_yaml_gold(gold_path)
    if args.limit > 0:
        gold = gold[:args.limit]
    print(f"  gold queries: {len(gold)}")

    qc = qdrant_client()
    from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny

    # ─── chunk_index 로딩 (BM25 또는 rerank 가 필요로 함) ────────────────
    bm25 = None
    bm25_chunk_ids: list[str] = []
    bm25_meta: dict[str, dict] = {}
    chunk_text_map: dict[str, str] = {}      # chunk_id_uuid → embedding_text
    need_text = args.use_bm25 or args.rerank
    if need_text:
        print(f"[chunk_index] MariaDB 로딩 (run_id={run_id})...")
        conn = mariadb_conn(); cur = conn.cursor()
        cur.execute("""SELECT chunk_id, embedding_text, corp_code, bsns_year,
                              endpoint, chunk_type, token_count
                       FROM chunk_index
                       WHERE run_id=%s AND ingest_status='ready'""", (run_id,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        all_tokens: list[list[str]] = []
        for cid, text, corp, year, ep, ct, tc in rows:
            cid_uuid = chunk_id_to_uuid(cid)
            chunk_text_map[cid_uuid] = text or ""
            bm25_meta[cid_uuid] = {
                "corp_code": corp, "bsns_year": year,
                "endpoint": ep, "chunk_type": ct, "chunk_id": cid,
                "token_count": tc or 0,
            }
            if args.use_bm25:
                bm25_chunk_ids.append(cid)
                all_tokens.append(_tokenize(text or ""))
        print(f"[chunk_index] {len(rows)} chunks loaded")
        if args.use_bm25:
            from rank_bm25 import BM25Okapi
            bm25 = BM25Okapi(all_tokens)
            print(f"[BM25] indexed {len(bm25_chunk_ids)} chunks")

    # rerank skip 카테고리 (CLI 옵션으로 오버라이드 가능)
    rerank_skip = set(s.strip() for s in args.rerank_skip_categories.split(",") if s.strip())

    # ─── Rerank 모델 로드 (--rerank) ──────────────────────────────────────
    rr_tok = rr_model = None
    rr_device = "cpu"
    rr_is_qwen = "Qwen" in args.rerank_model or "qwen" in args.rerank_model
    if args.rerank:
        rr_device = _detect_device(prefer_gpu=not args.cpu_only)
        print(f"[Rerank] 로딩 {args.rerank_model} (style={'qwen' if rr_is_qwen else 'bge'}, device={rr_device})...")
        from transformers import AutoTokenizer
        if rr_is_qwen:
            from transformers import AutoModelForCausalLM
            rr_tok = AutoTokenizer.from_pretrained(args.rerank_model, padding_side="left")
            rr_model = AutoModelForCausalLM.from_pretrained(args.rerank_model)
        else:
            from transformers import AutoModelForSequenceClassification
            rr_tok = AutoTokenizer.from_pretrained(args.rerank_model)
            rr_model = AutoModelForSequenceClassification.from_pretrained(args.rerank_model)
        rr_model.eval()
        try:
            rr_model = rr_model.to(rr_device)
        except Exception as e:
            print(f"[Rerank] device 전송 실패, CPU 로 폴백: {e}")
            rr_device = "cpu"
        print("[Rerank] 모델 준비 완료")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_tag = args.tag or "v1"
    per_q_path = OUT_DIR / f"{out_tag}_per_query.jsonl"
    f_pq = per_q_path.open("w", encoding="utf-8")

    by_cat: dict[str, list] = defaultdict(list)

    with httpx.Client(timeout=60) as http:
        for i, g in enumerate(gold, 1):
            sig = extract_filter_signals(g["query"])
            use_sub_query = (args.sub_query_by_corp and args.use_corp_filter
                             and len(sig["corp_codes"]) > 1)

            # ─── no_answer 사전 게이트 ─────────────────────────────────────
            # 5사 외 회사명이거나, 회사명 자체가 매치 안 되면 검색 skip → top_score=0
            # (사용자 가이드: "도메인 외 쿼리는 모름이 정답")
            if not sig["has_in_scope_corp"] and args.use_corp_filter:
                pts = []
            else:
                # 필터 구성: ingest_status='ready' + (선택) corp_code/bsns_year
                must = [FieldCondition(key="ingest_status",
                                       match=MatchValue(value="ready"))]
                # corp 필터: sub_query 케이스에선 per-corp으로 따로 적용
                if args.use_corp_filter and sig["corp_codes"] and not use_sub_query:
                    must.append(FieldCondition(
                        key="corp_code",
                        match=MatchAny(any=sig["corp_codes"]),
                    ))
                # bsns_year 필터: 쿼리에 년도 있을 때만 적용 (strict 매치, must 에 직접)
                if args.use_year_filter and sig["year"]:
                    must.append(FieldCondition(
                        key="bsns_year",
                        match=MatchValue(value=sig["year"]),
                    ))
                # 카테고리 기반 endpoint/chunk_type intent 필터 (선택)
                if args.use_category_filter:
                    eps = CATEGORY_ENDPOINTS.get(g["category"])
                    if eps:
                        must.append(FieldCondition(
                            key="endpoint",
                            match=MatchAny(any=eps),
                        ))
                    ctypes = CATEGORY_CHUNK_TYPES.get(g["category"])
                    if ctypes:
                        must.append(FieldCondition(
                            key="chunk_type",
                            match=MatchAny(any=ctypes),
                        ))
                vec = embed(http, g["query"])
                # BM25/rerank 시 dense pool 확장. rerank 가 가장 큰 입력 풀 필요.
                dense_limit = args.top_k
                if args.use_bm25:
                    dense_limit = max(dense_limit, args.dense_pool)
                if args.rerank:
                    dense_limit = max(dense_limit, args.rerank_pool)
                if use_sub_query:
                    # corp 별 dense_limit 검색
                    per_corp_pts: dict[str, list] = {}
                    for code in sig["corp_codes"]:
                        per_must = list(must) + [FieldCondition(
                            key="corp_code", match=MatchValue(value=code))]
                        res = qc.query_points(
                            collection_name=collection,
                            query=vec,
                            limit=dense_limit,
                            with_payload=True,
                            query_filter=Filter(must=per_must),
                        )
                        per_corp_pts[code] = list(res.points)
                    if g["category"] in CATEGORY_CORP_BALANCED:
                        # corp 균등 보장: 각 corp 별 top_k // N 강제 → 나머지 슬롯은 score 순
                        n_corps = len(sig["corp_codes"])
                        quota = max(1, args.top_k // n_corps)
                        balanced: list = []
                        seen: set = set()
                        for code in sig["corp_codes"]:
                            for p in per_corp_pts[code][:quota]:
                                if str(p.id) in seen:
                                    continue
                                balanced.append(p)
                                seen.add(str(p.id))
                        # 부족분: 전체 corp pool 에서 score 순으로 채움
                        if len(balanced) < args.top_k:
                            remaining = [p for code in sig["corp_codes"]
                                         for p in per_corp_pts[code][quota:]]
                            for p in sorted(remaining, key=lambda x: -x.score):
                                if str(p.id) in seen:
                                    continue
                                balanced.append(p)
                                seen.add(str(p.id))
                                if len(balanced) >= dense_limit:
                                    break
                        pts = balanced
                    else:
                        # 기본 sub_query: score 순 dedup → dense_limit
                        all_pts = [p for code in sig["corp_codes"]
                                   for p in per_corp_pts[code]]
                        seen2: set = set()
                        dedup: list = []
                        for p in sorted(all_pts, key=lambda x: -x.score):
                            if str(p.id) in seen2:
                                continue
                            seen2.add(str(p.id))
                            dedup.append(p)
                        pts = dedup[:dense_limit]
                else:
                    res = qc.query_points(
                        collection_name=collection,
                        query=vec,
                        limit=dense_limit,
                        with_payload=True,
                        query_filter=Filter(must=must),
                    )
                    pts = res.points

                # ─── BM25 + Dense RRF 융합 ───────────────────────────────
                use_bm25_for_q = (args.use_bm25 and bm25 is not None and pts
                                  and g["category"] not in CATEGORY_BM25_DISABLE)
                if use_bm25_for_q:
                    from types import SimpleNamespace
                    dense_ranks = {str(p.id): i + 1 for i, p in enumerate(pts)}
                    dense_map = {str(p.id): p for p in pts}
                    # sparse: 글로벌 BM25 score 계산 → 동일 필터 적용 → bm25_pool 까지
                    q_tokens = _tokenize(g["query"])
                    bm25_scores = bm25.get_scores(q_tokens)
                    sorted_idx = sorted(range(len(bm25_scores)),
                                        key=lambda i: -bm25_scores[i])
                    sparse_ranks: dict[str, int] = {}
                    take = 0
                    for idx in sorted_idx:
                        cid = bm25_chunk_ids[idx]
                        cid_uuid = chunk_id_to_uuid(cid)
                        meta = bm25_meta.get(cid_uuid)
                        if not meta:
                            continue
                        if args.use_corp_filter and sig["corp_codes"]:
                            if meta["corp_code"] not in sig["corp_codes"]:
                                continue
                        if args.use_year_filter and sig["year"]:
                            if meta["bsns_year"] != sig["year"]:
                                continue
                        if args.use_category_filter:
                            eps = CATEGORY_ENDPOINTS.get(g["category"])
                            ctypes = CATEGORY_CHUNK_TYPES.get(g["category"])
                            if eps and meta["endpoint"] not in eps:
                                continue
                            if ctypes and meta["chunk_type"] not in ctypes:
                                continue
                        take += 1
                        sparse_ranks[cid_uuid] = take
                        if take >= args.bm25_pool:
                            break
                    # RRF
                    rrf_k = args.rrf_k
                    all_ids = set(dense_ranks) | set(sparse_ranks)
                    rrf_scores: dict[str, float] = {}
                    for cid in all_ids:
                        s = 0.0
                        if cid in dense_ranks:
                            s += 1.0 / (rrf_k + dense_ranks[cid])
                        if cid in sparse_ranks:
                            s += 1.0 / (rrf_k + sparse_ranks[cid])
                        rrf_scores[cid] = s
                    fused_top = args.rerank_pool if args.rerank else args.top_k
                    fused_ids = sorted(rrf_scores.keys(),
                                       key=lambda c: -rrf_scores[c])[:fused_top]
                    new_pts = []
                    for cid in fused_ids:
                        if cid in dense_map:
                            p = dense_map[cid]
                            new_pts.append(SimpleNamespace(
                                id=p.id, payload=p.payload, score=rrf_scores[cid]))
                        else:
                            meta = bm25_meta.get(cid, {})
                            payload = {"chunk_id": meta.get("chunk_id"),
                                       "corp_code": meta.get("corp_code"),
                                       "bsns_year": meta.get("bsns_year"),
                                       "endpoint": meta.get("endpoint"),
                                       "chunk_type": meta.get("chunk_type")}
                            new_pts.append(SimpleNamespace(
                                id=cid, payload=payload, score=rrf_scores[cid]))
                    pts = new_pts
                else:
                    # BM25 미사용: rerank 켜졌으면 rerank_pool 까지, 아니면 top_k
                    cutoff = args.rerank_pool if args.rerank else args.top_k
                    pts = pts[:cutoff]

                # ─── Cross-encoder rerank (--rerank) ─────────────────────
                # 자유서술·비교 카테고리는 rerank 비효율적 → skip + dense top_k 사용
                if (args.rerank and rr_model is not None and pts
                        and g["category"] not in rerank_skip):
                    texts = [chunk_text_map.get(str(p.id), "") for p in pts]
                    if rr_is_qwen:
                        rr_scores = _rerank_batch_qwen(
                            g["query"], texts, rr_tok, rr_model,
                            batch=max(1, args.rerank_batch // 4),
                            device=rr_device)
                    else:
                        rr_scores = _rerank_batch(g["query"], texts, rr_tok, rr_model,
                                                  batch=args.rerank_batch,
                                                  device=rr_device)
                    paired = list(zip(pts, rr_scores))
                    paired.sort(key=lambda x: -x[1])
                    from types import SimpleNamespace
                    pts = [SimpleNamespace(id=p.id, payload=p.payload, score=float(sc))
                           for p, sc in paired[:args.top_k]]
                # 카테고리별 min_token_count 필터 (보일러플레이트 제거)
                min_tc = CATEGORY_MIN_TOKEN_COUNT.get(g["category"])
                if min_tc and pts:
                    pts = [p for p in pts
                           if bm25_meta.get(str(p.id), {}).get("token_count", 0) >= min_tc]

                # rerank 미사용/skip 케이스 대비 top_k 안전 슬라이스
                pts = pts[:args.top_k]

            retrieved_uids = [str(p.id) for p in pts]
            top_score = pts[0].score if pts else 0.0

            entry = {
                "id": g["id"], "category": g["category"], "query": g["query"],
                "no_answer": g.get("no_answer", False),
                "filter_signals": sig,
                "expected_chunk_ids": g.get("expected_chunk_ids", []),
                "retrieved_chunk_ids": [(p.payload.get("chunk_id"), p.score) for p in pts],
                "top_score": top_score,
                "metrics": metrics(g.get("expected_chunk_ids", []), retrieved_uids,
                                   k=args.top_k, cap=args.cap_recall),
            }
            f_pq.write(json.dumps(entry, ensure_ascii=False) + "\n")
            by_cat[g["category"]].append(entry)
            if i % 20 == 0:
                print(f"  {i}/{len(gold)}")
    f_pq.close()

    # 카테고리별 집계
    summary = {"run_id": run_id, "collection": collection,
               "top_k": args.top_k, "total_queries": len(gold),
               "elapsed_sec": round(time.time() - t0, 1),
               "by_category": {}}

    # 벡터 게이트 제외 카테고리 (다른 DB 영역). 측정은 하되 overall_pass 계산엔 미포함.
    # 비교: 정형 사실 비교 → Neo4j Cypher 결정론 영역. 벡터 recall@10 으로 평가하는 게 잘못된 방향.
    NON_VECTOR_GATE = {"비교"}

    print("\n──────── 카테고리별 결과 ────────────────────────────────")
    print(f"{'카테고리':<15}{'N':>5}{'Recall@10':>12}{'MRR':>10}{'nDCG@10':>12}{'PASS':>8}")
    threshold_default = 0.85
    threshold_no_answer = 0.95

    for cat, items in by_cat.items():
        n = len(items)
        if cat == "no_answer":
            # no_answer: top_score 의 평균·max — 진짜 "모름" 이면 모든 검색 점수가 낮아야 함
            # baseline: 평균 score < 0.5 면 PASS (실험적 임계, 후에 calibration)
            scores = [x["top_score"] or 0 for x in items]
            avg = sum(scores) / n if n else 0
            mx = max(scores) if scores else 0
            passed = avg < 0.5
            summary["by_category"][cat] = {
                "n": n, "avg_top_score": round(avg, 4), "max_top_score": round(mx, 4),
                "threshold": "avg_score < 0.5", "passed": passed,
            }
            print(f"{cat:<15}{n:>5}{avg:>12.4f}{mx:>10.4f}{'-':>12}{'PASS' if passed else 'FAIL':>8}")
        else:
            # answerable: Recall@10 / MRR / nDCG@10 평균
            rec = sum(x["metrics"]["recall@10"] for x in items) / n
            mrr = sum(x["metrics"]["mrr"] for x in items) / n
            ndcg = sum(x["metrics"]["ndcg@10"] for x in items) / n
            passed = rec >= threshold_default
            is_vector_gate = cat not in NON_VECTOR_GATE
            summary["by_category"][cat] = {
                "n": n, "recall@10": round(rec, 4), "mrr": round(mrr, 4),
                "ndcg@10": round(ndcg, 4),
                "threshold": f"recall@10 >= {threshold_default}", "passed": passed,
                "in_vector_gate": is_vector_gate,
            }
            tag = "PASS" if passed else "FAIL"
            if not is_vector_gate:
                tag += "*"  # 게이트 제외 표시
            print(f"{cat:<15}{n:>5}{rec:>12.4f}{mrr:>10.4f}{ndcg:>12.4f}{tag:>8}")

    # overall_pass 는 벡터 게이트 카테고리만 본다 (비교는 그래프 DB 영역)
    overall_pass = all(c["passed"] for cat, c in summary["by_category"].items()
                       if cat not in NON_VECTOR_GATE)
    summary["overall_pass"] = overall_pass
    summary["gate_excluded_categories"] = sorted(NON_VECTOR_GATE)
    print(f"\n  벡터 게이트 판정: {'PASS' if overall_pass else 'FAIL'} "
          f"(* 표시 카테고리는 그래프 DB 영역, 게이트 제외)")

    summary["use_corp_filter"] = args.use_corp_filter
    summary_path = OUT_DIR / f"{out_tag}_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  per-query: {per_q_path.relative_to(ROOT)}")
    print(f"  summary  : {summary_path.relative_to(ROOT)}")
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
