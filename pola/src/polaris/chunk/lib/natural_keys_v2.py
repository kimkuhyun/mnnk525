"""Pipeline 03 §B-3 chunk_id 생성 (hash16, immutable).

hash16(corp_code + rcept_no + section_path + offset + content_sha1)
→ BLAKE2b digest_size=8 (= 16 hex chars)
"""
from __future__ import annotations
import hashlib


def hash16(s: str) -> str:
    """BLAKE2b 16자 hex."""
    return hashlib.blake2b(s.encode("utf-8"), digest_size=8).hexdigest()


def content_sha1(text: str) -> str:
    """본문 SHA1 (full hash)."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def chunk_id_table(corp_code: str, rcept_no: str, endpoint: str,
                    row_offset: int, variant: str, content: str) -> str:
    """표 청크 chunk_id.

    section_path = endpoint + variant (예: 'fnlttSinglAcntAll/full')
    offset = row_offset (item index in JSON list)
    """
    section_path = f"{endpoint}/{variant}"
    csha1 = content_sha1(content)
    key = f"{corp_code}|{rcept_no}|{section_path}|{row_offset}|{csha1}"
    return hash16(key)


def chunk_id_text(corp_code: str, rcept_no: str, section_path: list[str],
                   offset: int, content: str) -> str:
    """텍스트 청크 chunk_id.

    section_path = 'II-1-가' 형식
    """
    sp = "-".join(section_path) if section_path else ""
    csha1 = content_sha1(content)
    key = f"{corp_code}|{rcept_no}|{sp}|{offset}|{csha1}"
    return hash16(key)
