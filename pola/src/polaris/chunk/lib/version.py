"""Pipeline 버전 잠금 — 청크·그래프 모든 row에 부여.

운영·롤백 시 schema 변경 식별. immutable.
"""
from __future__ import annotations

PIPELINE_VERSION = "2026.05.24.v1"
SCHEMA_VERSION = "polaris-3db.v1"
CHUNKER_VERSION = "semchunk-4.0.0 + bge-m3-tokenizer.v1"
LEXICON_VERSION = "v1"
