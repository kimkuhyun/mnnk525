"""tests/gold/graph_semantic_v1.yml 스키마 검증.

검증 항목:
  - 파일이 list 로 시작 (yaml.safe_load 결과 list)
  - 각 항목 dict + 필수 키 (id, category)
  - id 유일성
  - category 가 허용된 enum (entity / relation / event / entity_linking)
  - 카테고리별 필수 필드:
      entity_linking : alias, expected_corp_code
      entity         : chunk_id, expected_entities
      relation       : chunk_id, expected_triples
      event          : chunk_id, expected_events
  - eval 모듈이 빈 entity/relation/event 슬롯도 import 가능
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
import yaml

GOLD = (Path(__file__).resolve().parent / "gold" / "graph_semantic_v1.yml")
ALLOWED = {"entity", "relation", "event", "entity_linking"}
REQUIRED_BY_CAT = {
    "entity_linking": ("alias", "expected_corp_code"),
    "entity":         ("chunk_id", "expected_entities"),
    "relation":       ("chunk_id", "expected_triples"),
    "event":          ("chunk_id", "expected_events"),
}


@pytest.fixture(scope="module")
def gold_items() -> list[dict]:
    assert GOLD.is_file(), f"gold 없음: {GOLD}"
    data = yaml.safe_load(GOLD.read_text(encoding="utf-8"))
    assert isinstance(data, list), "최상위는 list 여야 함"
    return data


def test_each_item_is_dict_with_required_keys(gold_items):
    for it in gold_items:
        assert isinstance(it, dict), f"항목이 dict 아님: {it!r}"
        assert "id" in it and isinstance(it["id"], str), f"id 누락: {it}"
        assert "category" in it, f"category 누락: {it}"


def test_id_uniqueness(gold_items):
    ids = [it["id"] for it in gold_items]
    dups = [k for k, n in Counter(ids).items() if n > 1]
    assert not dups, f"id 중복: {dups}"


def test_category_enum(gold_items):
    bad = [(it["id"], it["category"]) for it in gold_items
           if it["category"] not in ALLOWED]
    assert not bad, f"허용되지 않은 category: {bad}"


def test_required_fields_per_category(gold_items):
    fails = []
    for it in gold_items:
        cat = it["category"]
        for key in REQUIRED_BY_CAT[cat]:
            if key not in it:
                fails.append((it["id"], cat, key))
    assert not fails, f"카테고리별 필수 필드 누락: {fails[:10]}"


def test_entity_linking_corp_code_format(gold_items):
    """expected_corp_code 는 8자 corp_code (DART) 또는 X-prefix 외부 코드."""
    fails = []
    for it in gold_items:
        if it["category"] != "entity_linking":
            continue
        cc = str(it.get("expected_corp_code", ""))
        if not cc:
            fails.append(it["id"])
            continue
        ok = (cc.isdigit() and len(cc) == 8) or cc.startswith("X")
        if not ok:
            fails.append((it["id"], cc))
    assert not fails, f"corp_code 형식 오류: {fails}"


def test_eval_module_imports_with_empty_slots():
    """entity/relation/event 슬롯이 비어있어도 eval 모듈은 정상 import 되고
    SEMANTIC_GATES 가 4 카테고리 모두 정의되어야 함."""
    from polaris.graph.eval import gold_semantic
    assert set(gold_semantic.SEMANTIC_GATES.keys()) == ALLOWED
    for cat, gate in gold_semantic.SEMANTIC_GATES.items():
        assert all(k in gate for k in ("P", "R", "F1")), f"{cat} gate 누락"


def test_gold_path_is_target_of_eval_default():
    """eval 모듈의 기본 GOLD_PATH 가 실제 yaml 과 같은 파일을 가리켜야 함."""
    from polaris.graph.eval import gold_semantic
    assert gold_semantic.GOLD_PATH.resolve() == GOLD.resolve()
