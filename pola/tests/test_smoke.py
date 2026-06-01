"""스모크 테스트 — 핵심 모듈 import 가능성 + 설정 sanity (DB·네트워크 불필요).

import 만으로도 mark_boilerplate(ROOT)·gold_graph(sys/ROOT) 같은 NameError 류를 조기 검출.
실행: uv run pytest tests/test_smoke.py
"""
from __future__ import annotations

import importlib

import pytest


def test_config_corps_is_three():
    from polaris import config
    assert len(config.CORPS) == 3, config.CORPS
    assert "00126380" in config.CORPS  # 삼성전자(시드)
    # CORP_NAMES 가 CORPS 와 정합
    assert set(config.CORP_NAMES) == set(config.CORPS)


@pytest.mark.parametrize("mod", [
    "polaris.config",
    "polaris.analyze.sentiment",
    "polaris.analyze.daily_digest",
    "polaris.analyze.stock_load",
    "polaris.ingest.ir_report_ingest",
    "polaris.db.load_qdrant",
    "polaris.db.load_neo4j",
    "polaris.embed.bge_m3",
    "polaris.graph.loader_semantic",
    "polaris.admin.mark_boilerplate",
    "polaris.eval.gold_graph",
])
def test_module_imports(mod):
    importlib.import_module(mod)
