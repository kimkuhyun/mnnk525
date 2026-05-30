"""FTC (공정위) 대규모기업집단 데이터 → 청크 + 3DB 적재.

입력: {DATA_ROOT}/rawData/_common/ftc/{endpoint}/{endpoint}__{year}_{groupId}_p{page}.xml
청킹: (endpoint, groupId, year) = 1 그룹 청크. XML 내 row 들을 NL 요약.

예시:
  "공정위 SK그룹(K1000050) 2025년 소속회사 198개 — 일부 명단:
   (주)대한송유관공사 / 박창길 대표 / 파이프라인 운송업
   (주)드림어스컴퍼니 / 김동훈 대표 / 오디오물 제공 서비스업
   ..."
"""
from __future__ import annotations
import hashlib, re, time
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx

from polaris.config import (
    DATA_ROOT, mariadb_conn, qdrant_client,
    OLLAMA_BASE, OLLAMA_EMBED_MODEL, get_active_run,
)

FTC_DIR = DATA_ROOT / "rawData" / "_common" / "ftc"
MACRO_CORP = "00000000"
BATCH = 32

# 그룹코드 → 그룹명 (주요 5개 정도. 나머지는 코드 그대로)
GROUP_NAMES = {
    "K1000032": "삼성", "K1000050": "SK", "K1000046": "현대자동차",
    "K1000034": "LG", "K1000040": "롯데", "K1000038": "포스코",
    "K1000018": "한화", "K1000054": "GS", "K1000028": "현대중공업",
    "K3000306": "기타",
}


def _hash16(*parts: str) -> str:
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _chunk_uuid(chunk_id: str) -> str:
    h = hashlib.md5(chunk_id.encode("utf-8")).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


# 6 종 파일명 패턴 dispatch (FTC endpoint 별 mode 가 다름)
#   year_group     : name__YYYY_GROUP_pN.xml         (affiliationCompSttusList, executiveCompSttusList 등)
#   year_only      : name__YYYY_pN.xml               (appnGroupSttusList)
#   ym_jurirno     : name__YYYYMM_{jurirno13}_pN.xml (holdingProgCompStusList)
#   ym_only        : name__YYYYMM_pN.xml             (sllInnerQotaList, grupRotatInvstmntList, holdingGenFinCompSttusList, innerQotaEqltrmCmprAssetsList)
#   group_only     : name__GROUP_pN.xml              (innerQotaEqltrmCmprUnityList)
#   period_group   : name__YYYY_GROUP_pN.xml         (tyAssetsRentDelngDtlsList — year_group 과 동일 형태)
_FNAME_PATTERNS: list[tuple[re.Pattern, callable]] = [
    # (regex, extract: match → (ep, year, gid))
    (re.compile(r"^([a-zA-Z]+)__(\d{4})_([A-Z][0-9]{6,7})_p(\d+)\.xml$"),
     lambda m: (m.group(1), m.group(2), m.group(3))),
    (re.compile(r"^([a-zA-Z]+)__(\d{4})_p(\d+)\.xml$"),
     lambda m: (m.group(1), m.group(2), None)),
    (re.compile(r"^([a-zA-Z]+)__(\d{6})_([0-9]{13})_p(\d+)\.xml$"),
     lambda m: (m.group(1), m.group(2)[:4], m.group(3))),
    (re.compile(r"^([a-zA-Z]+)__(\d{6})_p(\d+)\.xml$"),
     lambda m: (m.group(1), m.group(2)[:4], None)),
    (re.compile(r"^([a-zA-Z]+)__([A-Z][0-9]{6,7})_p(\d+)\.xml$"),
     lambda m: (m.group(1), None, m.group(2))),
]


def _parse_fname(name: str) -> tuple[str, str | None, str | None] | None:
    """파일명 → (endpoint, year, group_id). 매치 안 되면 None."""
    for rgx, extract in _FNAME_PATTERNS:
        m = rgx.match(name)
        if m:
            return extract(m)
    return None


def parse_ftc_xml(path: Path) -> list[dict]:
    """XML → row dict 리스트. 루트 children 의 각 element 가 row."""
    try:
        tree = ET.parse(path)
    except Exception:
        return []
    root = tree.getroot()
    rows = []
    for child in root:
        # numOfRows, pageNo, resultCode 등 메타는 skip
        if child.tag in ("numOfRows", "pageNo", "resultCode",
                         "resultMsg", "totalCount"):
            continue
        row = {sub.tag: (sub.text or "").strip() for sub in child}
        if row:
            rows.append(row)
    return rows


def _fmt_amt(s: str | None) -> str:
    """금액 문자열 → '123억' 포맷. 변환 실패 시 원본 또는 '-'."""
    if not s:
        return "-"
    try:
        v = int(s)
    except (ValueError, TypeError):
        return s
    if abs(v) >= 100_000_000:
        return f"{v / 1e8:,.0f}억"
    if abs(v) >= 10_000:
        return f"{v / 1e4:,.0f}만"
    return f"{v:,}"


def _summarize_rows(endpoint: str, rows: list[dict], max_items: int = 30) -> str:
    """endpoint 별 NL 요약. 필드명은 실측 XML 기준 (2024-2025 응답)."""
    if not rows:
        return f"{endpoint}: 0건"

    if endpoint == "appnGroupSttusList":
        # 대규모기업집단 지정 현황 (전체 그룹)
        lines = [
            f"{r.get('unityGrupNm','')}({r.get('unityGrupCode','')}): "
            f"동일인 {r.get('smerNm','')}, 대표회사 {r.get('repreCmpny','')}, "
            f"계열사 {r.get('sumCmpnyCo','-')}개, 구분 {r.get('entrprsCl','')}"
            for r in rows[:max_items]
        ]
        return f"대규모기업집단 {len(rows)}개 지정 현황:\n" + "\n".join(lines)

    if endpoint == "affiliationCompSttusList":
        # 소속회사 현황 (그룹 1개의 계열사 명단)
        lines = [
            f"{r.get('entrprsNm','')} (대표 {r.get('rprsntvNm','')}) — "
            f"{r.get('indutyNm','')} ({r.get('indutyCode','')}), "
            f"종업원 {r.get('ordtmEmplyCo','-')}명, 설립 {(r.get('fondDe','') or '')[:4]}"
            for r in rows[:max_items]
        ]
        return f"소속회사 {len(rows)}개 — 일부 명단:\n" + "\n".join(lines)

    if endpoint in ("appnGroupAffiList", "afltCmpySttusList"):
        # 계열사 (구형 endpoint 포함)
        lines = [
            f"{r.get('entrprsNm','')} (대표 {r.get('rprsntvNm','')}) — "
            f"jurirno={r.get('jurirno','')}, 편입 {(r.get('grinil','') or '')[:4]}"
            for r in rows[:max_items]
        ]
        return f"계열사 {len(rows)}개:\n" + "\n".join(lines)

    if endpoint == "executiveCompSttusList":
        # 임원 현황 — 회사별 임원 집계
        by_co: dict[str, list[str]] = defaultdict(list)
        for r in rows:
            by_co[r.get("entrprsNm", "")].append(
                f"{r.get('exctvNm','')}({r.get('ofcpsNm','')})"
            )
        co_items = list(by_co.items())[:max_items]
        lines = [
            f"{co}: 임원 {len(execs)}명 — {', '.join(execs[:5])}"
            + (f" 외 {len(execs) - 5}명" if len(execs) > 5 else "")
            for co, execs in co_items
        ]
        return f"임원 현황 {len(rows)}건 / 회사 {len(by_co)}개:\n" + "\n".join(lines)

    if endpoint == "financeCompSttusList":
        # 재무 현황 — 자산·자본·부채·매출·순익 (억 단위)
        lines = [
            f"{r.get('entrprsNm','')}: 자산 {_fmt_amt(r.get('assetsTotamt'))}, "
            f"자본 {_fmt_amt(r.get('caplTotamt'))}, 부채 {_fmt_amt(r.get('debtTotamt'))}, "
            f"매출 {_fmt_amt(r.get('selngAmount'))}, 순익 {_fmt_amt(r.get('thstrmNtpfAmount'))} "
            f"({(r.get('stacntDudt','') or '')} 기준)"
            for r in rows[:max_items]
        ]
        return f"소속회사 재무 {len(rows)}건:\n" + "\n".join(lines)

    if endpoint == "stockholderCompSttusList":
        # 주주현황
        lines = [
            f"{r.get('entrprsNm','')}: 주주 {r.get('shrholdrNm','')}"
            f"({r.get('shrholdrSe','')}) {r.get('allQotaRate','-')}%, "
            f"보유주식 {r.get('posesnStockCo','-')}주"
            for r in rows[:max_items]
        ]
        return f"주주현황 {len(rows)}건:\n" + "\n".join(lines)

    if endpoint == "innerQotaEqltrmCmprUnityList":
        # 내부지분 동일기간 비교 (연도별 추이)
        lines = [
            f"{r.get('presentnYear','')}: 총자본 {_fmt_amt(r.get('caplAmount'))}, "
            f"동일인 {_fmt_amt(r.get('smerCaplAmount'))}, "
            f"계열사 {_fmt_amt(r.get('entrprsCaplAmount'))}, "
            f"자사주 {_fmt_amt(r.get('tesstkCaplAmount'))}"
            for r in rows[:max_items]
        ]
        return f"내부지분 동일기간 비교 {len(rows)}년:\n" + "\n".join(lines)

    if endpoint == "tyAssetsRentDelngDtlsList":
        # 계열편입·제외·유예
        lines = [
            f"{r.get('entrprsNm','')}: 변동 {r.get('psitnCmpnyChangeSeCode','')} "
            f"({r.get('incrprDe','') or r.get('exclDe','') or r.get('postpneBeginDe','')})"
            for r in rows[:max_items]
        ]
        return f"계열편입·제외·유예 {len(rows)}건:\n" + "\n".join(lines)

    # 일반 fallback (첫 5 키)
    keys = list(rows[0].keys())[:5]
    lines = [" / ".join(f"{k}={r.get(k,'')}" for k in keys) for r in rows[:max_items]]
    return f"{endpoint} {len(rows)}건:\n" + "\n".join(lines)


def build_chunks() -> list[dict]:
    chunks = []
    if not FTC_DIR.is_dir():
        return chunks
    # 같은 (endpoint, year, group_id) 의 모든 page 통합
    bucket: dict[tuple, list[dict]] = defaultdict(list)
    for ep_dir in sorted(FTC_DIR.iterdir()):
        if not ep_dir.is_dir():
            continue
        endpoint = ep_dir.name
        for xf in sorted(ep_dir.glob("*.xml")):
            parsed = _parse_fname(xf.name)
            if not parsed:
                continue
            _, year, gid = parsed
            rows = parse_ftc_xml(xf)
            if rows:
                bucket[(endpoint, year, gid)].extend(rows)
    for (endpoint, year, gid), rows in bucket.items():
        # gid 가 None 이면 (year_only / ym_only) macro 청크 — group_name="전체"
        group_name = GROUP_NAMES.get(gid, gid) if gid else "전체"
        # gid 가 None 인 경우 cid 충돌 방지 위해 빈 문자열로
        cid = _hash16("ftc", endpoint, year or "", gid or "")
        # rcept_no 자리 (chunk_index.rcept_no VARCHAR(14)) — gid 또는 year+endpoint 키
        rcept_key = (gid or f"{year or ''}_{endpoint}")[:14]
        # 헤더 라벨: year 또는 "전체기간"
        year_label = f"{year}년" if year else "전체기간"
        text = (
            f"공정위 FTC {endpoint} {group_name}({gid or '-'}) {year_label}\n\n"
            + _summarize_rows(endpoint, rows)
        )
        chunks.append({
            "chunk_id": cid,
            "endpoint": endpoint,
            "year": int(year) if year and year.isdigit() else None,
            "group_id": gid or "",
            "group_name": group_name,
            "rcept_key": rcept_key,
            "row_count": len(rows),
            "embedding_text": text,
        })
    return chunks


def main():
    run_id, collection = get_active_run()
    print(f"[ftc-load] active run_id={run_id} collection={collection}")
    chunks = build_chunks()
    print(f"[ftc-load] 청크: {len(chunks):,}")
    if not chunks:
        return 0

    print(f"[ftc-load] 임베딩 (batch={BATCH})...")
    vectors: dict[str, list[float]] = {}
    t0 = time.time()
    with httpx.Client(timeout=120) as http:
        for i in range(0, len(chunks), BATCH):
            batch = chunks[i:i + BATCH]
            texts = [c["embedding_text"] for c in batch]
            r = http.post(f"{OLLAMA_BASE}/api/embed",
                          json={"model": OLLAMA_EMBED_MODEL, "input": texts})
            r.raise_for_status()
            for c, v in zip(batch, r.json()["embeddings"]):
                vectors[c["chunk_id"]] = v
    print(f"[ftc-load] 임베딩 완료: {len(vectors)} ({time.time() - t0:.0f}s)")

    conn = mariadb_conn(); cur = conn.cursor()
    for c in chunks:
        cur.execute("""INSERT INTO chunk_index
            (chunk_id, run_id, corp_code, rcept_no, chunk_type,
             bsns_year, endpoint, embedding_text, ingest_status, ready_at)
            VALUES (%s, %s, %s, %s, 'ftc_meta', %s, %s, %s, 'ready', NOW())
            ON DUPLICATE KEY UPDATE
              embedding_text=VALUES(embedding_text),
              ingest_status='ready', ready_at=NOW()""",
            (c["chunk_id"], run_id, MACRO_CORP, c["rcept_key"],
             c["year"], c["endpoint"][:128], c["embedding_text"]))
    conn.commit(); cur.close(); conn.close()
    print(f"[ftc-load] MariaDB INSERT: {len(chunks)}")

    qc = qdrant_client()
    from qdrant_client.models import PointStruct
    points = []
    for c in chunks:
        v = vectors.get(c["chunk_id"])
        if not v: continue
        points.append(PointStruct(
            id=_chunk_uuid(c["chunk_id"]), vector=v,
            payload={
                "chunk_id": c["chunk_id"], "chunk_type": "ftc_meta",
                "corp_code": MACRO_CORP, "rcept_no": c["rcept_key"],
                "bsns_year": c["year"], "endpoint": c["endpoint"],
                "group_id": c["group_id"], "group_name": c["group_name"],
                "row_count": c["row_count"],
                "ingest_status": "ready", "run_id": run_id,
            },
        ))
    for i in range(0, len(points), 100):
        qc.upsert(collection_name=collection, points=points[i:i + 100])
    print(f"[ftc-load] Qdrant upsert: {len(points)}")
    print(f"[ftc-load] 완료. {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
