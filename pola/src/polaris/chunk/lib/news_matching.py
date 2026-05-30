"""뉴스 → 회사 매칭 — DEPRECATED (ADR 005 + P-3.1d).

폐기 사유: 뉴스 1건 = 1청크 정책(`corp=00000000`)으로 전환 (ADR 005).
        alias 사전은 `src/polaris/data/aliases/organizations.yml` 로 통일 (P-3.1d).

호환성 유지 — 본 모듈은 yaml 에서 동적으로 dict 빌드.
신규 코드는 `polaris.graph.lexicon.build_matcher()` 사용 권장 (5 entity_type 통합).
"""
from __future__ import annotations
import warnings
from functools import lru_cache

import ahocorasick

from polaris.graph.lexicon.loader import load_aliases

_DEPRECATION_NOTE = (
    "news_matching: ADR 005 폐기 (1뉴스=1청크). alias 는 graph/lexicon yaml SSOT. "
    "신규 코드는 polaris.graph.lexicon.build_matcher() 권장."
)


# =========================================================================
# 회사 alias 사전 — yaml 기반 동적 빌더 (DEPRECATED API 호환성)
# =========================================================================

@lru_cache(maxsize=1)
def _build_legacy_corp_aliases() -> dict[str, list[str]]:
    """organizations.yml → 옛 5사 dict 포맷 (corp_code → aliases[])."""
    orgs = load_aliases("organizations") or {}
    out: dict[str, list[str]] = {}
    for cc, meta in orgs.items():
        if not isinstance(meta, dict):
            continue
        cc8 = str(cc).zfill(8) if str(cc).isdigit() else str(cc)
        aliases = [meta.get("name", "")] + (meta.get("aliases") or []) \
                  + (meta.get("ticker") or [])
        out[cc8] = [a for a in aliases if a]
    return out


@lru_cache(maxsize=1)
def _build_legacy_ambiguous() -> set[str]:
    """organizations.yml 의 ambiguous_alone 통합 set."""
    orgs = load_aliases("organizations") or {}
    s: set[str] = set()
    for meta in orgs.values():
        if isinstance(meta, dict):
            for amb in (meta.get("ambiguous_alone") or []):
                s.add(amb)
    return s


# 모듈 로드 시 1회 빌드 (yaml 변경 시 재import 또는 lexicon.invalidate_cache)
CORP_ALIASES: dict[str, list[str]] = _build_legacy_corp_aliases()
AMBIGUOUS_ALIASES: set[str] = _build_legacy_ambiguous()


def build_aho_automaton() -> ahocorasick.Automaton:
    """DEPRECATED — yaml 기반 자동. 신규 코드는 lexicon.build_matcher() 사용."""
    warnings.warn(_DEPRECATION_NOTE, DeprecationWarning, stacklevel=2)
    A = ahocorasick.Automaton()
    for corp, aliases in CORP_ALIASES.items():
        for a in aliases:
            if a in AMBIGUOUS_ALIASES:
                continue
            A.add_word(a, (corp, a))
    if CORP_ALIASES:
        A.make_automaton()
    return A


def match_news_rule(text: str, automaton: ahocorasick.Automaton) -> dict[str, list[str]]:
    """DEPRECATED — lexicon.Matcher.scan() 의 Organization 결과로 대체."""
    warnings.warn(_DEPRECATION_NOTE, DeprecationWarning, stacklevel=2)
    hits: dict[str, set[str]] = {}
    if not text:
        return {}
    for _, (corp, alias) in automaton.iter(text):
        hits.setdefault(corp, set()).add(alias)
    return {c: sorted(a) for c, a in hits.items()}


# =========================================================================
# 3차 LLM 게이트 — 룰·NER 매칭 0건인 뉴스만 LLM 분류
# 모델은 환경변수 OLLAMA_LLM_MODEL (기본 qwen3.5:9b) 로 조절.
# enum/system prompt 는 .env POLARIS_CORPS + corps.json 기반 동적 생성.
# =========================================================================

import httpx, json

from polaris.config import OLLAMA_BASE, OLLAMA_LLM_MODEL, CORPS, get_corp_meta


def _build_classify_schema() -> dict:
    enum_values = list(CORPS) + ["none"]
    return {
        "type": "object",
        "properties": {
            "matched_corps": {
                "type": "array",
                "items": {"type": "string", "enum": enum_values},
                "description": f"이 뉴스와 직접 관련된 회사 corp_code (없으면 ['none']). 총 {len(CORPS)}사."
            },
            "reason": {"type": "string", "description": "1문장 근거"}
        },
        "required": ["matched_corps", "reason"]
    }


def _build_system_prompt() -> str:
    lines = [f"{len(CORPS)}사 중 어느 회사 뉴스인지 분류한다. 직접 언급 X, 암시도 OK."]
    for cc in CORPS:
        m = get_corp_meta(cc)
        lines.append(f"- {cc} {m.get('corp_name', cc)}")
    lines.append("관련 없으면 ['none']. 추측·외부지식 금지.")
    return "\n".join(lines)


# 모듈 로드 시 1회 빌드 (CORPS 가 변경되면 import 재실행 시 갱신됨)
CLASSIFY_SCHEMA = _build_classify_schema()
LLM_SYSTEM = _build_system_prompt()


def classify_news_llm(text: str, max_chars: int = 2000) -> dict:
    """LLM 게이트 — 룰 매칭 0건 뉴스 분류."""
    snippet = text[:max_chars] if len(text) > max_chars else text
    payload = {
        "model": OLLAMA_LLM_MODEL,
        "messages": [
            {"role":"system","content": LLM_SYSTEM},
            {"role":"user","content": f"뉴스 본문:\n{snippet}\n\n위 본문이 어느 회사 관련인지 JSON으로 분류."},
        ],
        "format": CLASSIFY_SCHEMA,
        "options": {"num_ctx": 8192, "temperature": 0.1},
        "think": False, "stream": False,
    }
    try:
        with httpx.Client(timeout=60) as c:
            r = c.post(f"{OLLAMA_BASE}/api/chat", json=payload)
        msg = r.json().get("message",{}).get("content","")
        if not msg: return {"matched_corps":[], "reason":"call_fail"}
        return json.loads(msg)
    except Exception as e:
        return {"matched_corps":[], "reason": f"err_{e}"}
