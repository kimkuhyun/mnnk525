"""Diagnostic dump — 7개 데이터 적재 문제의 sample + 통계 수집.

산출물: sample/data/diagnostics/<problem>.json + summary.json

P0-1. Chunk evidence 엣지 부착률 (0.16%)
P0-2. Event PROV 100% 누락
P1-1. Organization 중복 (corp_code ×3)
P1-2. Stale chunk (current run 외)
P2-1. Entity FP (일반명사)
P2-2. Statement confidence 분포
P3-1. Qdrant↔Neo4j Chunk 불일치
P3-2. LLM 비율 / unlinked
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 패키지 경로
_HERE = Path(__file__).resolve()
_PKG = _HERE.parent.parent
sys.path.insert(0, str(_PKG))
sys.path.insert(0, str(_PKG / "src"))

# .env 가 우선되도록 OS env 중 stale 한 것 제거
os.environ.pop("QDRANT_COLLECTION_ACTIVE", None)

from polaris.config import (  # noqa: E402
    neo4j_driver,
    qdrant_client,
    get_active_run,
)

OUT = Path(r"C:\Users\kimkuhyn\Desktop\mnnk525\sample\data\diagnostics")
OUT.mkdir(parents=True, exist_ok=True)


def jdump(name: str, data) -> None:
    p = OUT / name
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"  → {p.relative_to(OUT.parent.parent)}  ({p.stat().st_size:,} bytes)")


def main() -> int:
    summary = {}

    drv = neo4j_driver()
    active_run_id, active_col = get_active_run()
    summary["active_run_id"] = active_run_id
    summary["active_qdrant_collection"] = active_col

    with drv.session() as s:
        # ─────────────────────────────────────────────────────
        # P0-1. Chunk 엣지 부착률
        # ─────────────────────────────────────────────────────
        print("[P0-1] Chunk evidence edges …")
        total = s.run("MATCH (c:Chunk) RETURN count(c) AS n").single()["n"]
        with_edges = s.run(
            "MATCH (c:Chunk)-[r:hasActor|hasObject|MENTIONS|wasGeneratedBy]-() "
            "RETURN count(DISTINCT c) AS n"
        ).single()["n"]
        edge_types = [
            dict(r)
            for r in s.run(
                "MATCH (c:Chunk)-[r]->(b) WHERE NOT b:Chunk "
                "RETURN type(r) AS type, count(*) AS count ORDER BY count DESC LIMIT 12"
            )
        ]
        # current run 만
        cur_total = s.run(
            "MATCH (c:Chunk) WHERE c.run_id=$r RETURN count(*) AS n", r=active_run_id
        ).single()["n"]
        cur_with = s.run(
            "MATCH (c:Chunk)-[:hasActor|hasObject|MENTIONS]-() WHERE c.run_id=$r "
            "RETURN count(DISTINCT c) AS n",
            r=active_run_id,
        ).single()["n"]
        # 엣지가 *있는* Chunk 의 corp_code 분포 (어디에 몰렸나)
        edge_corp_dist = [
            dict(r)
            for r in s.run(
                "MATCH (c:Chunk)-[:hasActor|hasObject]-() "
                "RETURN c.corp_code AS corp_code, count(DISTINCT c) AS chunks "
                "ORDER BY chunks DESC LIMIT 20"
            )
        ]
        # 엣지 없는 Chunk sample 30개
        isolated_sample = [
            dict(r)
            for r in s.run(
                "MATCH (c:Chunk) WHERE NOT (c)-[:hasActor|hasObject|MENTIONS]-() "
                "RETURN c.chunk_id AS chunk_id, c.corp_code AS corp_code, "
                "c.chunk_type AS chunk_type, c.section_path AS section_path "
                "LIMIT 30"
            )
        ]
        p01 = {
            "chunk_total_all_runs": total,
            "chunk_with_edges": with_edges,
            "coverage_pct": round(with_edges * 100.0 / max(total, 1), 4),
            "chunk_total_active_run": cur_total,
            "chunk_with_edges_active_run": cur_with,
            "coverage_active_pct": round(cur_with * 100.0 / max(cur_total, 1), 4),
            "edge_types_from_chunk": edge_types,
            "edge_chunk_corp_distribution": edge_corp_dist,
            "isolated_chunk_sample": isolated_sample,
        }
        jdump("p01_chunk_edges.json", p01)
        summary["p01_chunk_edges"] = {
            "coverage_pct": p01["coverage_pct"],
            "isolated_chunks": total - with_edges,
        }

        # ─────────────────────────────────────────────────────
        # P0-2. Event PROV
        # ─────────────────────────────────────────────────────
        print("[P0-2] Event PROV …")
        ev_total = s.run("MATCH (e:Event) RETURN count(e) AS n").single()["n"]
        ev_with = s.run(
            "MATCH (e:Event)-[:wasDerivedFrom]->(:Chunk) RETURN count(DISTINCT e) AS n"
        ).single()["n"]
        ev_sample_props = [
            dict(r)
            for r in s.run(
                "MATCH (e:Event) RETURN keys(e) AS keys, e.source_chunk_id AS source_chunk_id, "
                "e.event_id AS event_id, e.label AS label LIMIT 10"
            )
        ]
        # Statement PROV
        st_total = s.run("MATCH (s:Statement) RETURN count(s) AS n").single()["n"]
        st_with = s.run(
            "MATCH (s:Statement)-[:wasDerivedFrom]->(:Chunk) RETURN count(DISTINCT s) AS n"
        ).single()["n"]
        # Event 의 모든 property keys 분포
        ev_keys_dist = [
            dict(r)
            for r in s.run(
                "MATCH (e:Event) UNWIND keys(e) AS k "
                "RETURN k AS prop, count(*) AS c ORDER BY c DESC LIMIT 20"
            )
        ]
        p02 = {
            "event_total": ev_total,
            "event_with_prov": ev_with,
            "event_orphan_pct": round((ev_total - ev_with) * 100.0 / max(ev_total, 1), 2),
            "statement_total": st_total,
            "statement_with_prov": st_with,
            "statement_orphan_pct": round((st_total - st_with) * 100.0 / max(st_total, 1), 2),
            "event_property_keys": ev_keys_dist,
            "event_sample": ev_sample_props,
        }
        jdump("p02_event_prov.json", p02)
        summary["p02_event_prov"] = {
            "event_orphan_pct": p02["event_orphan_pct"],
            "statement_orphan_pct": p02["statement_orphan_pct"],
        }

        # ─────────────────────────────────────────────────────
        # P1-1. Organization 중복
        # ─────────────────────────────────────────────────────
        print("[P1-1] Organization duplicates …")
        dup_rows = [
            dict(r)
            for r in s.run(
                """
                MATCH (o:Organization) WHERE o.name IS NOT NULL
                WITH o.name AS name, collect(DISTINCT o.corp_code) AS codes
                WHERE size(codes) > 1
                RETURN name, codes, size(codes) AS n
                ORDER BY n DESC, name
                """
            )
        ]
        # corp_code prefix 패턴 분석 — 어떤 생성 규칙이 쓰였나
        prefix_dist = {}
        for row in dup_rows:
            for code in row["codes"]:
                if not code:
                    pat = "<null>"
                elif code.startswith("unknown_"):
                    pat = "unknown_*"
                elif code.startswith("XDJ_"):
                    pat = "XDJ_*"
                elif code.startswith("X") and len(code) == 8:
                    pat = "X+7hex"
                elif len(code) == 16 and all(c in "0123456789abcdef" for c in code):
                    pat = "16hex"
                elif len(code) == 8 and code.isdigit():
                    pat = "8digit (DART)"
                else:
                    pat = "other"
                prefix_dist[pat] = prefix_dist.get(pat, 0) + 1
        p11 = {
            "dup_groups": len(dup_rows),
            "dup_node_total": sum(r["n"] for r in dup_rows),
            "corp_code_prefix_distribution": prefix_dist,
            "top_30_duplicates": dup_rows[:30],
        }
        jdump("p11_org_duplicates.json", p11)
        summary["p11_org_duplicates"] = {
            "dup_groups": p11["dup_groups"],
            "prefix_patterns": list(prefix_dist.keys()),
        }

        # ─────────────────────────────────────────────────────
        # P1-2. Stale chunk (run_id 분포)
        # ─────────────────────────────────────────────────────
        print("[P1-2] Stale chunk distribution …")
        run_dist = [
            dict(r)
            for r in s.run(
                "MATCH (c:Chunk) RETURN c.run_id AS run_id, count(*) AS chunks "
                "ORDER BY chunks DESC LIMIT 20"
            )
        ]
        # active_run_manifest 에서 active+standby 만 살아 있어야
        try:
            from polaris.config import mariadb_conn

            conn = mariadb_conn()
            cur = conn.cursor()
            cur.execute(
                "SELECT active_run_id, standby_run_id, standby_status FROM active_run_manifest WHERE id=1"
            )
            manifest = cur.fetchone()
            cur.close()
            conn.close()
            mf = {
                "active_run_id": manifest[0],
                "standby_run_id": manifest[1],
                "standby_status": manifest[2],
            }
        except Exception as e:
            mf = {"error": f"{type(e).__name__}: {e}"}
        p12 = {
            "chunk_total": sum(r["chunks"] for r in run_dist),
            "run_count": len(run_dist),
            "active_run_chunks": next(
                (r["chunks"] for r in run_dist if r["run_id"] == active_run_id), 0
            ),
            "manifest": mf,
            "run_id_distribution": run_dist,
        }
        jdump("p12_stale_chunks.json", p12)
        summary["p12_stale_chunks"] = {
            "run_count": p12["run_count"],
            "active_run_chunks": p12["active_run_chunks"],
            "stale_chunks": p12["chunk_total"] - p12["active_run_chunks"],
        }

        # ─────────────────────────────────────────────────────
        # P2-1. Entity FP (일반명사)
        # ─────────────────────────────────────────────────────
        print("[P2-1] Entity FP …")
        # 짧은 라벨 (2-4글자) + 일반명사 의심 추출
        suspect_terms = [
            "IDM","Foundry","Fabless","파운드리","메모리","반도체","DRAM","NAND","HBM",
            "전기전자업","패널업체","OEM","ODM","파운드","DDR5","CXL","CE","DM","DS","DX","MX",
            "Place","Plant","Studio","Library","EDA Tool","IP","Your Fab",
        ]
        fp_org = {}
        fp_person = {}
        fp_product = {}
        fp_place = {}
        fp_tech = {}
        for t in suspect_terms:
            for label, target in [
                ("Organization", fp_org),
                ("Person", fp_person),
                ("Product", fp_product),
                ("Place", fp_place),
                ("Technology", fp_tech),
            ]:
                try:
                    n = s.run(
                        f"MATCH (x:{label}) WHERE x.name = $t RETURN count(*) AS c", t=t
                    ).single()["c"]
                    if n > 0:
                        target[t] = n
                except Exception:
                    pass
        # 짧은(<=3자) Org 이름 sample — 노이즈 가능성 ↑
        short_orgs = [
            dict(r)
            for r in s.run(
                "MATCH (o:Organization) WHERE o.name IS NOT NULL AND size(o.name) <= 3 "
                "RETURN o.name AS name, o.corp_code AS corp_code, "
                "labels(o) AS labels LIMIT 50"
            )
        ]
        p21 = {
            "fp_organization": fp_org,
            "fp_person": fp_person,
            "fp_product": fp_product,
            "fp_place": fp_place,
            "fp_technology": fp_tech,
            "short_org_sample": short_orgs,
        }
        jdump("p21_entity_fp.json", p21)
        summary["p21_entity_fp"] = {
            "fp_org_count": sum(fp_org.values()),
            "fp_product_count": sum(fp_product.values()),
        }

        # ─────────────────────────────────────────────────────
        # P2-2. Statement confidence 분포
        # ─────────────────────────────────────────────────────
        print("[P2-2] Statement confidence distribution …")
        dist = s.run(
            """
            MATCH (st:Statement)
            RETURN
              sum(CASE WHEN st.confidence >= 0.95 THEN 1 ELSE 0 END) AS bucket_95,
              sum(CASE WHEN st.confidence >= 0.9  AND st.confidence < 0.95 THEN 1 ELSE 0 END) AS bucket_90,
              sum(CASE WHEN st.confidence >= 0.8  AND st.confidence < 0.9  THEN 1 ELSE 0 END) AS bucket_80,
              sum(CASE WHEN st.confidence >= 0.7  AND st.confidence < 0.8  THEN 1 ELSE 0 END) AS bucket_70,
              sum(CASE WHEN st.confidence < 0.7   AND st.confidence IS NOT NULL THEN 1 ELSE 0 END) AS bucket_low,
              sum(CASE WHEN st.confidence IS NULL THEN 1 ELSE 0 END) AS bucket_null,
              avg(st.confidence) AS avg, count(*) AS total
            """
        ).single()
        p22 = dict(dist)
        # Statement key 분포 — evidence_count 같은 다른 신호 있는지
        key_dist = [
            dict(r)
            for r in s.run(
                "MATCH (st:Statement) UNWIND keys(st) AS k "
                "RETURN k AS prop, count(*) AS c ORDER BY c DESC LIMIT 20"
            )
        ]
        p22["statement_keys_available"] = key_dist
        jdump("p22_confidence_distribution.json", p22)
        summary["p22_confidence"] = {
            "high_pct": round((p22["bucket_95"] + p22["bucket_90"]) * 100.0 / max(p22["total"], 1), 1),
            "avg": float(p22["avg"]) if p22["avg"] is not None else None,
        }

        # ─────────────────────────────────────────────────────
        # P3-2. LLM 비율 / unlinked
        # ─────────────────────────────────────────────────────
        print("[P3-2] LLM ratio + unlinked …")
        llm_ratio = {}
        for lbl in ["Organization", "Person", "Product", "Technology", "Event", "Place", "Statement"]:
            try:
                t = s.run(f"MATCH (x:{lbl}) RETURN count(x) AS n").single()["n"]
                llm = s.run(f"MATCH (x:{lbl}:LLMExtracted) RETURN count(x) AS n").single()["n"]
                llm_ratio[lbl] = {"total": t, "llm": llm, "pct": round(llm * 100.0 / max(t, 1), 2)}
            except Exception:
                pass

        # unlinked.jsonl 위치 추정
        unlinked_files = []
        try:
            from polaris.config import DATA_ROOT

            for p in DATA_ROOT.rglob("unlinked*.jsonl"):
                unlinked_files.append({"path": str(p), "size": p.stat().st_size})
        except Exception:
            pass

        p32 = {
            "llm_ratio_by_label": llm_ratio,
            "unlinked_files": unlinked_files,
        }
        jdump("p32_llm_ratio.json", p32)
        summary["p32_llm_ratio"] = {
            "person_llm_pct": llm_ratio.get("Person", {}).get("pct"),
            "org_llm_pct": llm_ratio.get("Organization", {}).get("pct"),
        }

    drv.close()

    # ─────────────────────────────────────────────────────
    # P3-1. Qdrant ↔ Neo4j Chunk 불일치
    # ─────────────────────────────────────────────────────
    print("[P3-1] Qdrant ↔ Neo4j diff …")
    try:
        qc = qdrant_client()
        # Qdrant chunk_id set (scroll)
        q_ids = set()
        offset = None
        while True:
            pts, offset = qc.scroll(
                collection_name=active_col,
                limit=512,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for p in pts:
                pl = p.payload or {}
                cid = pl.get("chunk_id")
                if cid:
                    q_ids.add(cid)
            if offset is None:
                break
        # Neo4j chunk_id (current run)
        drv2 = neo4j_driver()
        n_ids = set()
        with drv2.session() as s:
            for r in s.run(
                "MATCH (c:Chunk) WHERE c.run_id=$r RETURN c.chunk_id AS cid", r=active_run_id
            ):
                n_ids.add(r["cid"])
        drv2.close()
        q_only = q_ids - n_ids
        n_only = n_ids - q_ids
        # sample (first 30 of each)
        q_only_sample = sorted(q_only)[:30]
        n_only_sample = sorted(n_only)[:30]
        p31 = {
            "qdrant_count": len(q_ids),
            "neo4j_count": len(n_ids),
            "qdrant_only": len(q_only),
            "neo4j_only": len(n_only),
            "qdrant_only_sample": q_only_sample,
            "neo4j_only_sample": n_only_sample,
        }
    except Exception as e:
        p31 = {"error": f"{type(e).__name__}: {e}"}
    jdump("p31_qdrant_neo4j_diff.json", p31)
    summary["p31_qdrant_neo4j_diff"] = {
        "qdrant_only": p31.get("qdrant_only"),
        "neo4j_only": p31.get("neo4j_only"),
    }

    # ─────────────────────────────────────────────────────
    # summary
    # ─────────────────────────────────────────────────────
    jdump("summary.json", summary)
    print("\n=== diagnostic dump complete ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
