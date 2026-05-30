"""3k 토큰 초과 청크의 의미 단위 분할.

1차: semchunk (bge-m3 토크나이저 — 임베딩 모델 정확 일치)
2차 fallback: 단순 문단 split

bge-m3 max context = 8192 tokens. chunk_size 2800 = 안전 마진 (3000 한도 X).
"""
from __future__ import annotations
import semchunk
from transformers import AutoTokenizer

# bge-m3 토크나이저 (임베딩 모델과 정확 일치)
_TOKENIZER = AutoTokenizer.from_pretrained("BAAI/bge-m3")


def count_tokens(text: str) -> int:
    """bge-m3 토크나이저 기반 토큰 카운트 (임베딩 정확)."""
    if not text:
        return 0
    return len(_TOKENIZER.encode(text, add_special_tokens=False))


def _chunker_callable(text: str) -> int:
    """semchunk 호환 — text → 토큰 수."""
    return count_tokens(text)


# semchunk chunker — bge-m3 토큰 기반 의미 분할
_CHUNKER = semchunk.chunkerify(_chunker_callable, chunk_size=2800)


def split_semantic(text: str, max_tokens: int = 3000) -> list[str]:
    """text 토큰이 max_tokens 초과면 의미 단위 분할.

    Returns: 분할된 청크 list. 1개면 분할 불필요.
    """
    if not text or count_tokens(text) <= max_tokens:
        return [text] if text else []
    try:
        chunks = _CHUNKER(text)
        return [c for c in chunks if c and c.strip()]
    except Exception:
        # fallback: 문단 단위 split
        return _split_paragraphs(text, max_tokens)


def _split_paragraphs(text: str, max_tokens: int) -> list[str]:
    """문단 경계 기준 단순 분할."""
    paras = text.split("\n\n")
    out = []
    cur, cur_tokens = [], 0
    for p in paras:
        pt = count_tokens(p)
        if cur_tokens + pt > max_tokens and cur:
            out.append("\n\n".join(cur))
            cur, cur_tokens = [], 0
        cur.append(p)
        cur_tokens += pt
    if cur:
        out.append("\n\n".join(cur))
    return out
