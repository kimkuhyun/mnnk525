# ADR 001 — Contextual Retrieval (헤더 prefix)

**상태**: 적용 · 2026-05-25

## 결정
청크 `embedding_text` 에 `corp_name + doc_type + section_headings` prefix 추가.

## 배경
자유서술 카테고리 ("한미반도체 1. 사업의 개요") recall@10 = 0.567. BM25/rerank/Qwen reranker 다 적용해도 동일.

## 진단
`run_stage_c2.py` 의 `embedding_text = content` (본문만). 청크 임베딩에 "1. 사업의 개요" 같은 섹션 신호 전혀 없음 → 쿼리와 매칭 실패.

## 대안
- min_token_count 필터: 역효과 (정답까지 제거)
- Qwen3-Reranker-0.6B: 효과 없음 (쿼리 짧음의 한계)
- **헤더 prefix 추가**: 채택

## 결과
자유서술 0.567 → **0.867** (+0.30). 다른 모든 leverage 합친 것보다 큼.

## 참고
- Anthropic Contextual Retrieval (2026): https://www.anthropic.com/news/contextual-retrieval
- 운영 도구: `polaris reembed-text` (in-place 재임베딩, 26초)
