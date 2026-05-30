"""POLARIS CLI - typer 단일 진입점.

명령:
  polaris verify              # 3DB 적재 정합 8/8 체크
  polaris eval [--tag T]      # 벡터 평가 (BM25+Dense+RRF+Rerank, 권장 옵션 일괄)
  polaris graph-eval          # Neo4j Cypher 평가 (비교 카테고리)
  polaris load-finmetric      # DART JSON → Neo4j FinMetric 노드 적재
  polaris mark-boilerplate    # 짧은 보일러플레이트 청크 soft-delete
  polaris reembed-text        # text 청크 in-place 재임베딩 (Contextual prefix)

내부 구현은 각 모듈의 main() 호출 (sys.argv 조작으로 argparse 호환).
"""
from __future__ import annotations
import sys
from contextlib import contextmanager
from pathlib import Path

import typer

app = typer.Typer(no_args_is_help=True, help="POLARIS CLI - 반도체 5사 GraphRAG")


@contextmanager
def _isolated_argv(label: str):
    """typer 옵션이 sys.argv 에 남아 안쪽 모듈 argparse 와 충돌하지 않도록 격리.
    label 만 단일 인자로 sys.argv 에 두고 호출 후 원복."""
    saved = sys.argv
    sys.argv = [label]
    try:
        yield
    finally:
        sys.argv = saved


@app.command()
def verify():
    """3DB(MariaDB·Qdrant·Neo4j) 적재 정합 10/10 검증."""
    from polaris.admin import verify_ingestion
    with _isolated_argv("polaris-verify"):
        raise SystemExit(verify_ingestion.main())


@app.command(name="eval")
def eval_vector(
    tag: str = typer.Option("final", help="출력 파일 접두 (예: v18_final → tag=v18_final)"),
    gold: str = typer.Option("tests/gold/v3.yml", help="gold yaml 경로 (패키지 루트 기준)"),
    top_k: int = typer.Option(10, help="검색 top-k"),
    best: bool = typer.Option(True, "--best/--no-best",
                              help="권장 옵션 일괄 활성 (필터+sub-query+cap+BM25+rerank)"),
):
    """벡터 골드셋 평가 (run_gold_vector). 6 카테고리 게이트."""
    from polaris.eval import gold_vector as _gv
    argv = ["polaris-eval", "--top-k", str(top_k), "--tag", tag, "--gold", gold]
    if best:
        argv.append("--best")
    sys.argv = argv
    raise SystemExit(_gv.main())


@app.command(name="graph-eval")
def eval_graph():
    """Neo4j Cypher 평가 (비교 카테고리 정형 영역). F1 1.0 기대."""
    from polaris.eval import gold_graph
    with _isolated_argv("polaris-graph-eval"):
        raise SystemExit(gold_graph.main())


@app.command(name="graph-diag")
def graph_diag_cmd(
    corp: str = typer.Option(None, help="단일 회사 corp_code (없으면 .env CORPS 전체)"),
    json_out: bool = typer.Option(False, "--json", help="JSON 만 출력 (파이핑용)"),
    out: str = typer.Option(None, help="결과 JSON 저장 경로"),
):
    """Neo4j 정형 그래프 진단 (C-01~C-15). PASS/WARN/FAIL 리포트."""
    from polaris.db import graph_diag
    argv = ["polaris-graph-diag"]
    if corp: argv += ["--corp", corp]
    if json_out: argv += ["--json"]
    if out: argv += ["--out", out]
    sys.argv = argv
    raise SystemExit(graph_diag.main())


@app.command(name="graph-extract")
def graph_extract_cmd(
    only: str = typer.Option("all",
        help="csv 추출기 (persons,shareholders,invests,ftc_groups,events,all)"),
):
    """그래프 영역 자동 추출 — Person/EXECUTIVE_OF, IS_MAJOR_SHAREHOLDER_OF, INVESTS_IN/IS_SUBSIDIARY, BusinessGroup/AFFILIATED_WITH, Event/wasDerivedFrom.

    DART raw json + FTC XML → Neo4j MERGE (결정론, idempotent)."""
    from polaris.graph import extract_all
    sys.argv = ["polaris-graph-extract", "--only", only]
    raise SystemExit(extract_all.main())


@app.command(name="graph-extract-semantic")
def graph_extract_semantic_cmd(
    limit: int = typer.Option(0, help="처리할 청크 수 제한 (0=전체, sanity 용)"),
    resume: bool = typer.Option(False, "--resume",
        help="llm_progress.json 의 마지막 chunk_id 이후만 처리"),
):
    """P-3.4: 의미 그래프 LLM 추출 — qwen3.5:9b strict JSON Entity + Relation.

    LLM_PATH 청크만 (≤30% 통과율). 결과 jsonl: data/4_dbGoldTest/graph_extracts/{run_id}/."""
    from polaris.graph import pipeline
    argv = ["polaris-graph-extract-semantic"]
    if limit > 0: argv += ["--limit", str(limit)]
    if resume: argv += ["--resume"]
    sys.argv = argv
    raise SystemExit(pipeline.main())


@app.command(name="graph-rebuild-er-index")
def graph_rebuild_er_index_cmd(
    dry_run: bool = typer.Option(False, "--dry-run", help="대상만 출력"),
):
    """P-3.5: Organization ER 인덱스 (Qdrant polaris-org-er) 재빌드.

    bge-m3 임베딩 → Vector 기반 Entity Linking Stage 2 활성화."""
    from polaris.graph import er_index
    argv = ["polaris-graph-rebuild-er-index"]
    if dry_run: argv += ["--dry-run"]
    sys.argv = argv
    raise SystemExit(er_index.main())


@app.command(name="graph-load-semantic")
def graph_load_semantic_cmd(
    limit: int = typer.Option(0, help="처리 records 제한 (0=전체)"),
):
    """P-3.6: 의미 그래프 jsonl → Neo4j MERGE (Statement/Relation/Event :LLMExtracted).

    링킹 + Reification + Chunk evidence + ExtractionActivity."""
    from polaris.graph import loader_semantic
    argv = ["polaris-graph-load-semantic"]
    if limit > 0: argv += ["--limit", str(limit)]
    sys.argv = argv
    raise SystemExit(loader_semantic.main())


@app.command(name="graph-semantic-eval")
def graph_semantic_eval_cmd(
    gold: str = typer.Option("tests/gold/graph_semantic_v1.yml",
        help="gold yaml 경로"),
):
    """P-3.7: 의미 그래프 평가 — entity/relation/event/linking P/R/F1.

    게이트: entity F1≥0.75, relation F1≥0.70, linking F1≥0.87. FAIL 시 standby 폐기."""
    from polaris.graph.eval import gold_semantic
    sys.argv = ["polaris-graph-semantic-eval", "--gold", gold]
    raise SystemExit(gold_semantic.main())


@app.command(name="load-finmetric")
def load_finmetric_cmd():
    """DART fnlttSinglAcntAll JSON → Neo4j (Organization)-[:HAS_METRIC]->(FinMetric)."""
    from polaris.admin import load_finmetric
    with _isolated_argv("polaris-load-finmetric"):
        raise SystemExit(load_finmetric.main())


@app.command(name="load-chunk-nodes")
def load_chunk_nodes_cmd():
    """P-3.2: MariaDB chunk_index → Neo4j (:Chunk) T4 lookup 노드. 의미 그래프 evidence 링크 anchor."""
    from polaris.admin import load_chunk_nodes
    with _isolated_argv("polaris-load-chunk-nodes"):
        raise SystemExit(load_chunk_nodes.main())


@app.command(name="mark-boilerplate")
def mark_boilerplate_cmd(
    dry_run: bool = typer.Option(False, "--dry-run", help="실제 변경 없이 후보만 출력"),
):
    """token_count<50 + '기재 생략' 패턴 청크를 soft-delete (ingest_status='pending')."""
    from polaris.admin import mark_boilerplate
    label = "polaris-mark" + (" --dry-run" if dry_run else "")
    with _isolated_argv(label):
        raise SystemExit(mark_boilerplate.main(dry_run=dry_run))


@app.command(name="reembed-text")
def reembed_text_cmd():
    """text 청크 in-place 재임베딩 (Contextual Retrieval prefix 적용)."""
    from polaris.admin import reembed_text_contextual
    with _isolated_argv("polaris-reembed-text"):
        raise SystemExit(reembed_text_contextual.main())


@app.command(name="reembed-table")
def reembed_table_cmd():
    """table_nl 청크 in-place 재임베딩 (corp_name·year·endpoint prefix 적용)."""
    from polaris.admin import reembed_table_contextual
    with _isolated_argv("polaris-reembed-table"):
        raise SystemExit(reembed_table_contextual.main())


SOURCE_MODULES = {
    "news": ("polaris.chunk.news", "뉴스 (한경/매경 RSS) - 선행: ingest --stage b4"),
    "krx": ("polaris.chunk.krx", "KRX 일별 OHLCV (월별 요약)"),
    "bok": ("polaris.chunk.bok", "BOK 거시 시계열 + Neo4j MacroIndicator"),
    "kosis": ("polaris.chunk.kosis", "KOSIS 통계표 메타"),
    "ftc": ("polaris.chunk.ftc", "FTC 공정위 대규모기업집단"),
}


@app.command(name="load-source")
def load_source_cmd(
    name: str = typer.Argument(..., help="news / krx / bok / kosis / ftc / all"),
):
    """6 종 source 청킹·임베딩·3DB 적재. all 이면 5종 순차 실행.

    예시:
      polaris load-source news     # 뉴스만
      polaris load-source all      # 5종 전부 (news, krx, bok, kosis, ftc)
    """
    import importlib
    targets = list(SOURCE_MODULES) if name == "all" else [name]
    for t in targets:
        if t not in SOURCE_MODULES:
            typer.echo(f"unknown source: {t}. choose: {list(SOURCE_MODULES)} or 'all'")
            raise typer.Exit(1)
        mod_name, desc = SOURCE_MODULES[t]
        typer.echo(f"=== load-source {t} - {desc} ===")
        mod = importlib.import_module(mod_name)
        with _isolated_argv(f"polaris-load-{t}"):
            rc = mod.main()
        if rc not in (None, 0):
            typer.echo(f"[{t}] non-zero exit: {rc}")
            raise typer.Exit(rc)


# 하위 호환 alias (옛 명령 그대로 동작)
@app.command(name="load-news", hidden=True)
def _alias_load_news():
    from polaris.chunk import news
    with _isolated_argv("polaris-load-news"):
        raise SystemExit(news.main())


@app.command(name="load-kosis", hidden=True)
def _alias_load_kosis():
    from polaris.chunk import kosis
    with _isolated_argv("polaris-load-kosis"):
        raise SystemExit(kosis.main())


@app.command(name="load-bok", hidden=True)
def _alias_load_bok():
    from polaris.chunk import bok
    with _isolated_argv("polaris-load-bok"):
        raise SystemExit(bok.main())


@app.command(name="load-krx", hidden=True)
def _alias_load_krx():
    from polaris.chunk import krx
    with _isolated_argv("polaris-load-krx"):
        raise SystemExit(krx.main())


@app.command(name="load-ftc", hidden=True)
def _alias_load_ftc():
    from polaris.chunk import ftc
    with _isolated_argv("polaris-load-ftc"):
        raise SystemExit(ftc.main())


@app.command()
def ingest(
    stage: str = typer.Option("all",
        help="all=bulk_collect / a,b1,b2,b3,b4=단일 stage"),
    only: str = typer.Option("",
        help="bulk_collect 단계 제한 (stage=all 일 때만): dart,documents,krx,news,ftc,bok,kosis 중 콤마"),
    skip: str = typer.Option("",
        help="bulk_collect 에서 제외: dart,documents,krx,news,ftc,bok,kosis 중 콤마"),
    corp_codes: str = typer.Option("",
        help="corp_code 콤마. 비우면 .env POLARIS_CORPS 전체"),
    from_year: int = typer.Option(2025, help="시작 사업연도"),
    to_year: int = typer.Option(0, help="종료 사업연도 (0=올해)"),
    news_since: str = typer.Option("2026-01-01", help="이 날짜 이후 뉴스만"),
    profile: str = typer.Option("normal", help="rate-limit: slow / normal / fast"),
):
    """raw 데이터 수집·정제 - bulk_collect (stage=all, 기본) 또는 b1~b4 단일 stage.

    예시:
      polaris ingest                                    # 6종 전체 수집 (5사+추가)
      polaris ingest --only dart,krx --from-year 2024   # DART + KRX 만
      polaris ingest --corp-codes 00160843,00369657 --only dart,krx
      polaris ingest --stage b4                         # 뉴스 회사 매칭 단일
    """
    from polaris.ingest import (stage_a_collect, stage_b1_html,
                                 stage_b2_clean, stage_b3_doc_index, stage_b4_news)
    single_stage_mods = {"a": stage_a_collect, "b1": stage_b1_html,
                          "b2": stage_b2_clean, "b3": stage_b3_doc_index,
                          "b4": stage_b4_news}
    if stage in single_stage_mods:
        if only or skip or corp_codes:
            typer.echo(f"[warn] --only/--skip/--corp-codes 는 --stage all 일 때만 적용 (현재 stage={stage} 무시)")
        raise SystemExit(single_stage_mods[stage].main())
    if stage != "all":
        typer.echo(f"unknown stage: {stage}. choose: all/a/b1/b2/b3/b4")
        raise typer.Exit(1)

    # bulk_collect: argv 조립
    from polaris.ingest import bulk_collect as _bc
    argv = ["polaris-ingest"]
    if only: argv += ["--only", only]
    if skip: argv += ["--skip", skip]
    if corp_codes: argv += ["--corp-codes", corp_codes]
    argv += ["--from-year", str(from_year),
             "--to-year", str(to_year),
             "--news-since", news_since,
             "--profile", profile]
    sys.argv = argv
    raise SystemExit(_bc.app(standalone_mode=False))


@app.command(name="init-db")
def init_db(db: str = typer.Option("all", help="qdrant / mariadb / neo4j / all")):
    """3DB 초기화 - 스키마·인덱스 생성 (Blue/Green standby 패턴)."""
    from polaris.db import init_qdrant, init_mariadb, init_neo4j
    mods = {"qdrant": init_qdrant, "mariadb": init_mariadb, "neo4j": init_neo4j}
    for t in (list(mods) if db == "all" else [db]):
        typer.echo(f"=== init {t} ===")
        with _isolated_argv(f"polaris-init-{t}"):
            mods[t].main()


@app.command(name="load")
def load(db: str = typer.Option("all", help="qdrant / mariadb / neo4j / all")):
    """3DB 적재 - 청크·메타·그래프 (standby 컬렉션).
    순서: mariadb 가 먼저 standby_run_id 발급해야 qdrant/neo4j 가 그걸 사용 가능."""
    from polaris.db import load_qdrant, load_mariadb, load_neo4j
    # 순서 강제: mariadb → qdrant → neo4j
    order = ["mariadb", "qdrant", "neo4j"]
    mods = {"qdrant": load_qdrant, "mariadb": load_mariadb, "neo4j": load_neo4j}
    targets = order if db == "all" else [db]
    for t in targets:
        if t not in mods:
            typer.echo(f"unknown db: {t}"); raise typer.Exit(1)
        typer.echo(f"=== load {t} ===")
        with _isolated_argv(f"polaris-load-{t}"):
            mods[t].main()


@app.command(name="promote-run")
def promote_run_cmd():
    """블루/그린 스위치 - standby → active (active_run_manifest 갱신)."""
    from polaris.db import promote_run
    with _isolated_argv("polaris-promote-run"):
        raise SystemExit(promote_run.main())


def _detect_new_corps_and_mark_rule_recheck() -> int:
    """.env CORPS vs Neo4j Organization 비교. 신규 회사 있으면
    news_raw.meta 에 rule_recheck 마커 (LLM 결과 보존, 룰만 재실행).
    Returns: 마크된 row 수 (0 이면 신규 회사 없음)."""
    import json as _json
    from polaris.config import mariadb_conn, neo4j_driver, CORPS
    drv = neo4j_driver()
    try:
        with drv.session() as s:
            rows = s.run("MATCH (o:Organization) RETURN o.corp_code AS c").data()
            org_set = {r["c"] for r in rows if r.get("c")}
    finally:
        drv.close()
    new_corps = [c for c in CORPS if c not in org_set]
    if not new_corps:
        return 0
    typer.echo(f"[build] 신규 회사 감지: {new_corps} → news_raw.meta rule_recheck 마커 (룰 재실행, LLM 결과 보존)")
    conn = mariadb_conn(); cur = conn.cursor()
    # 기존 meta 보존하고 needs_rule_recheck 플래그만 추가
    cur.execute("""UPDATE news_raw
                   SET meta = JSON_SET(COALESCE(meta, JSON_OBJECT()), '$.needs_rule_recheck', TRUE)""")
    n = cur.rowcount; conn.commit(); cur.close(); conn.close()
    return n


@app.command()
def build(
    skip_init: bool = typer.Option(False, "--skip-init",
        help="init-db 건너뛰기 (이미 스키마 있을 때)"),
    sources: str = typer.Option("all",
        help="load-source 대상 (all / news,krx,bok,kosis,ftc / none)"),
    skip_chunking: bool = typer.Option(False, "--skip-chunking",
        help="stage_a/b + chunk/table + chunk/text + embed 건너뛰기 (raw·청크·임베딩 이미 갱신 완료 시)"),
    skip_graph: bool = typer.Option(False, "--skip-graph",
        help="graph-extract + ER 인덱스 재빌드 건너뛰기 (정형 그래프 영역 갱신 X)"),
    skip_semantic: bool = typer.Option(False, "--skip-semantic",
        help="의미 그래프 LLM 추출 건너뛰기 (회사당 30분~수 시간 절약, 기본 실행)"),
    no_invalidate_news: bool = typer.Option(False, "--no-invalidate-news",
        help="신규 회사 감지 시 news_raw.meta 무효화 skip"),
):
    """전체 적재 통합: alias + 정제 + 청크화 + 임베딩 + 3DB 적재 + load-source + finmetric + 그래프 추출.

    신규 회사 추가 자동 처리 (정형 영역, 항상 실행):
      1)  organizations.yml 에 corps.json lookup 기반 stub 엔트리 자동 append
      2)  raw -> 01_filtered (stage_a)
      3)  HTML 스냅샷 + per-doc 요약 + document_index.jsonl (stage_b1~b3)
      4)  DART JSON -> table_nl.jsonl + body_clean -> text.jsonl (chunk.table/text)
      5)  bge-m3 임베딩 (idempotent: 기존 npy 보존, --force 로 재생성)
      6)  MariaDB / Qdrant / Neo4j 적재 (chunk_index + dart_raw_index + document_index)
      7)  news / krx / bok / kosis / ftc load-source
      8)  Neo4j Organization + FinMetric (load-finmetric)
      9)  graph-extract (Person / EXECUTIVE_OF / INVESTS_IN / AFFILIATED_WITH / Event)
      10) ER 인덱스 재빌드 (polaris-org-er, 신규 회사 alias 임베딩 추가)
      11) load-chunk-nodes (Neo4j :Chunk T4 lookup, 의미 그래프 evidence anchor)

    의미 그래프 (항상 실행, --skip-semantic 으로 끌 수 있음):
      12) graph-extract-semantic (qwen3.5:9b, --resume 으로 신규 청크만)
      13) graph-load-semantic (Statement / Relation / Event :LLMExtracted MERGE)

    예시:
      polaris build                    # 전부 자동 (의미 그래프 포함, 회사당 30분~수 시간)
      polaris build --skip-init        # 스키마 그대로 (회사 추가 표준)
      polaris build --skip-semantic    # 의미 그래프 LLM skip (정형만)
      polaris build --sources none     # DART + FinMetric + 그래프 만
      polaris build --skip-chunking    # 이미 청크·임베딩 끝나 있을 때
      polaris build --skip-graph       # 정형 그래프 추출도 skip (검색만 갱신)
    """
    import importlib
    from polaris.db import init_qdrant, init_mariadb, init_neo4j
    from polaris.db import load_qdrant, load_mariadb, load_neo4j
    from polaris.admin import (load_finmetric, ensure_aliases as _ea,
                                load_chunk_nodes)
    from polaris.ingest import (stage_a_collect, stage_b1_html, stage_b2_clean,
                                 stage_b3_doc_index)
    from polaris.chunk import table as chunk_table, text as chunk_text
    from polaris.embed import bge_m3
    from polaris.graph import extract_all as graph_extract, er_index as graph_er

    def _run(label: str, mod):
        with _isolated_argv(label):
            mod.main()

    # 0/8 organizations.yml 자동 추가 — 신규 회사가 있으면 stub 엔트리 append
    typer.echo("=== 0/8 organizations.yml alias 자동 추가 ===")
    res = _ea.ensure_aliases()
    if res.get("added"):
        typer.echo(f"  추가: {res['added']}")
    if res.get("missing_meta"):
        typer.echo(f"  [warn] corps.json 미등록: {res['missing_meta']}")
    if not res.get("added") and not res.get("missing_meta"):
        typer.echo(f"  모든 corp_code 이미 alias 사전에 존재 ({len(res.get('skipped_existing', []))}건)")

    if not skip_init:
        typer.echo("\n=== 1/8 init-db (3DB 스키마) ===")
        _run("polaris-init-qdrant", init_qdrant)
        _run("polaris-init-mariadb", init_mariadb)
        _run("polaris-init-neo4j", init_neo4j)

    if not skip_chunking:
        typer.echo("\n=== 2/8 stage_a (raw → 01_filtered) ===")
        _run("polaris-stage-a", stage_a_collect)

        typer.echo("\n=== 3/8 stage_b1~b3 (snapshots + per-doc 요약 + document_index) ===")
        _run("polaris-stage-b1", stage_b1_html)
        _run("polaris-stage-b2", stage_b2_clean)
        _run("polaris-stage-b3", stage_b3_doc_index)

        typer.echo("\n=== 4/8 chunk.table + chunk.text (DART JSON → 청크 JSONL) ===")
        _run("polaris-chunk-table", chunk_table)
        _run("polaris-chunk-text", chunk_text)

        typer.echo("\n=== 5/8 embed.bge_m3 (청크 → 1024d 벡터, idempotent) ===")
        _run("polaris-embed-bge-m3", bge_m3)
    else:
        typer.echo("=== 2~5/8 stage_a/b + chunk + embed: skip (--skip-chunking) ===")

    typer.echo("\n=== 6/8 load (DART 청크·메타·그래프 → 3DB) ===")
    # 순서 중요: load_mariadb 가 standby_run_id 발급 → qdrant/neo4j 가 SELECT
    _run("polaris-load-mariadb", load_mariadb)
    _run("polaris-load-qdrant", load_qdrant)
    _run("polaris-load-neo4j", load_neo4j)

    # 6/8 이 standby_run_id 를 발급 → 이후 load-source(7/8)·finmetric(8/N)·graph(9~)
    # 가 active(promote 전엔 None) 가 아닌 standby 로 적재하도록 환경변수 노출.
    import os as _os
    from polaris.config import mariadb_conn as _mc
    _conn = _mc(); _cur = _conn.cursor()
    _cur.execute("SELECT standby_run_id FROM active_run_manifest WHERE id=1")
    _standby = _cur.fetchone()[0]
    _cur.close(); _conn.close()
    if _standby:
        _os.environ["POLARIS_TARGET_RUN_ID"] = _standby
        typer.echo(f"[build] 적재 대상 run_id = standby={_standby} (load-source·finmetric·graph 공통)")

    if sources != "none":
        typer.echo(f"\n=== 7/8 load-source {sources} ===")
        targets = list(SOURCE_MODULES) if sources == "all" else \
                  [s.strip() for s in sources.split(",") if s.strip()]
        for t in targets:
            if t not in SOURCE_MODULES:
                typer.echo(f"[warn] unknown source: {t} (skip)")
                continue
            mod_name, desc = SOURCE_MODULES[t]
            typer.echo(f"  - {t}: {desc}")
            _run(f"polaris-load-{t}", importlib.import_module(mod_name))
    else:
        typer.echo("\n=== 7/8 load-source: skip (sources=none) ===")

    typer.echo("\n=== 8/N load-finmetric (Neo4j Organization + FinMetric) ===")
    _run("polaris-load-finmetric", load_finmetric)

    if not skip_graph:
        # 그래프 적재 대상은 standby_run_id (방금 적재된 청크의 run_id) — promote 후 active 와 일치
        import os as _os
        from polaris.config import mariadb_conn as _mc
        _conn = _mc(); _cur = _conn.cursor()
        _cur.execute("SELECT standby_run_id FROM active_run_manifest WHERE id=1")
        _standby = _cur.fetchone()[0]
        _cur.close(); _conn.close()
        _prev_target = _os.environ.get("POLARIS_TARGET_RUN_ID", "")
        if _standby:
            _os.environ["POLARIS_TARGET_RUN_ID"] = _standby
            typer.echo(f"\n[build] graph 적재 대상 run_id = standby={_standby}")

        try:
            typer.echo("\n=== 9/N graph-extract (Person/EXECUTIVE_OF/INVESTS_IN/AFFILIATED_WITH/Event) ===")
            _run("polaris-graph-extract", graph_extract)

            typer.echo("\n=== 10/N graph-rebuild-er-index (polaris-org-er Qdrant 컬렉션) ===")
            _run("polaris-graph-er", graph_er)

            typer.echo("\n=== 11/N load-chunk-nodes (Neo4j :Chunk T4 lookup, 의미 그래프 evidence anchor) ===")
            _run("polaris-load-chunk-nodes", load_chunk_nodes)
        finally:
            if _prev_target:
                _os.environ["POLARIS_TARGET_RUN_ID"] = _prev_target
            else:
                _os.environ.pop("POLARIS_TARGET_RUN_ID", None)
    else:
        typer.echo("\n=== 9~11/N graph-extract + ER + chunk-nodes: skip (--skip-graph) ===")

    if not skip_semantic:
        from polaris.graph import pipeline as graph_semantic, loader_semantic
        typer.echo("\n=== 12/N graph-extract-semantic (qwen3.5:9b 의미 추출, --resume) ===")
        typer.echo("  ※ 회사당 30분~수 시간 — 끄려면 --skip-semantic")
        # --resume 으로 idempotent: 이미 처리한 chunk_id 이후만
        import sys as _sys
        saved = _sys.argv
        _sys.argv = ["polaris-graph-extract-semantic", "--resume"]
        try:
            graph_semantic.main()
        finally:
            _sys.argv = saved

        typer.echo("\n=== 13/N graph-load-semantic (Statement/Relation/Event :LLMExtracted) ===")
        _run("polaris-graph-load-semantic", loader_semantic)
    else:
        typer.echo("\n=== 12~13/N graph-extract-semantic: skip (--skip-semantic) ===")

    typer.echo("\n빌드 완료. 검증 후 promote 하세요:")
    typer.echo("  polaris verify        # 적재 정합 확인")
    typer.echo("  polaris promote-run   # standby → active 스위치")


@app.command()
def version():
    """패키지 버전."""
    from polaris import __version__
    typer.echo(f"polaris {__version__}")


if __name__ == "__main__":
    app()
