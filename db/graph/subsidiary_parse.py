"""사업보고서 XII '연결대상 종속회사 현황(상세)' 표 파싱 → 자회사명 목록.

엄격 XML 파서 금지(bare & 있음) — 정규식으로 SUB_CMPN 테이블그룹 내
ACODE="CRP_NM"(상호) / ACODE="EST_DT"(설립일) 셀만 추출.

zip 안에 메인 XML(rcept.xml) 한 개 + 분리 첨부(rcept_NNNNN.xml) 있음.
종속회사 표는 메인 XML 안에 있음. zip 직접 메모리에서 읽음(임시폴더 안 씀).
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

from db import BIZ_REPORT_RCEPT, RAW_DIR

# SUB_CMPN 테이블그룹 = '연결대상 종속회사 현황(상세)' 의 데이터 표
_GROUP_START = re.compile(r'<TABLE-GROUP[^>]*ACLASS="SUB_CMPN"', re.IGNORECASE)
_CRP_NM = re.compile(r'ACODE="CRP_NM"[^>]*>([^<]*)<', re.IGNORECASE)
_EST_DT = re.compile(r'ACODE="EST_DT"[^>]*>([^<]*)<', re.IGNORECASE)
# 한 행(TR) 안에서 CRP_NM·EST_DT 묶기 위해 행 단위 분해
_TR = re.compile(r"<TR\b.*?</TR>", re.IGNORECASE | re.DOTALL)


def _read_main_xml(zip_path: Path, rcept_no: str) -> str | None:
    """zip 안 메인 XML({rcept}.xml) 텍스트 반환."""
    if not zip_path.exists():
        return None
    with zipfile.ZipFile(zip_path) as zf:
        target = f"{rcept_no}.xml"
        names = zf.namelist()
        pick = target if target in names else None
        if pick is None:
            # 가장 큰 xml = 메인
            xmls = [n for n in names if n.lower().endswith(".xml")]
            if not xmls:
                return None
            pick = max(xmls, key=lambda n: zf.getinfo(n).file_size)
        data = zf.read(pick)
    for enc in ("utf-8", "cp949", "euc-kr"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _extract_group(xml: str) -> str | None:
    """SUB_CMPN 테이블그룹 블록(시작 ~ 매칭 </TABLE-GROUP>) 텍스트."""
    m = _GROUP_START.search(xml)
    if not m:
        return None
    start = m.start()
    end = xml.find("</TABLE-GROUP>", start)
    if end < 0:
        end = len(xml)
    return xml[start:end]


def _clean_name(raw: str) -> str:
    s = (raw or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def parse_subsidiaries(zip_path: Path, rcept_no: str) -> list[dict]:
    """[{name, founded(설립일 raw), rcept_no}] 반환. 중복(name) 제거."""
    xml = _read_main_xml(zip_path, rcept_no)
    if xml is None:
        return []
    group = _extract_group(xml)
    if group is None:
        return []
    rows: list[dict] = []
    seen: set[str] = set()
    for trm in _TR.finditer(group):
        tr = trm.group(0)
        nm = _CRP_NM.search(tr)
        if not nm:
            continue
        name = _clean_name(nm.group(1))
        if not name or name in ("상호", "-"):
            continue
        if name in seen:
            continue
        seen.add(name)
        est = _EST_DT.search(tr)
        founded = _clean_name(est.group(1)) if est else ""
        rows.append({"name": name, "founded": founded, "rcept_no": rcept_no})
    return rows


def iter_company_subsidiaries():
    """회사폴더별 (회사폴더, corp_code없음→상위에서 매핑, rcept_no, [subs]) 산출.

    최신 사업보고서 우선이되, 가능한 보고서 모두 파싱하고 name 기준 dedup.
    """
    for folder, rcepts in BIZ_REPORT_RCEPT.items():
        docs_dir = RAW_DIR / folder / "documents"
        merged: dict[str, dict] = {}
        used_rcept: list[str] = []
        # 최신(뒤) 보고서가 우선되도록 정렬: rcept 큰 것 먼저 채움
        for rcept in sorted(rcepts, reverse=True):
            zip_path = docs_dir / f"{rcept}.zip"
            subs = parse_subsidiaries(zip_path, rcept)
            if subs:
                used_rcept.append(rcept)
            for s in subs:
                if s["name"] not in merged:
                    merged[s["name"]] = s
        yield folder, used_rcept, list(merged.values())


if __name__ == "__main__":
    for folder, used, subs in iter_company_subsidiaries():
        print(f"[{folder}] rcept={used} 종속회사 {len(subs)}건")
        for s in subs[:5]:
            print("   ", s["name"], "|", s["founded"], "|", s["rcept_no"])
