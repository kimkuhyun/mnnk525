# -*- coding: utf-8 -*-
"""POLARIS 결정론적 청커.
DART 정기보고서 원본 zip -> chunk_index 적재용 jsonl 청크 생성.
LLM 호출/네트워크 없음. 표준 라이브러리만 사용.

실행 (저장소 루트에서):
    PYTHONIOENCODING=utf-8 python -X utf8 db/chunk/chunk.py
출력 깨지면 PYTHONIOENCODING=utf-8 확인.
"""
import zipfile
import re
import html
import hashlib
import json
import glob
import unicodedata
from pathlib import Path

ROOT = Path(r"C:\Users\kimkuhyn\Desktop\mnnk525")
RAW = ROOT / "db" / "raw"
OUT = ROOT / "db" / "chunk" / "output"

# 회사명 -> corp_code
COMPANIES = {
    "삼성전자": "00126380",
    "SK하이닉스": "00164779",
    "한미반도체": "00161383",
}

# 청킹 정책
MAX_CHARS = 800
OVERLAP = 80
MIN_TEXT = 20            # 산문 청크 최소 길이
GRID_CELL_LIMIT = 120    # 표 셀(grid 칸) 초과 시 데이터행 그룹 분할

# 청킹 대상 장 (TITLE 로마숫자 prefix)
TARGET_CHAPTERS = {"II", "IV", "V", "IX", "X", "XI"}
# III장에서 청킹할 절 번호 (TITLE "3."=연결재무제표 주석, "5."=재무제표 주석)
CH3_TARGET_SECTIONS = {"3", "5"}

ROMAN_RE = re.compile(r'^\s*((?:XII|XI|IX|IV|VI{0,3}|V|I{1,3}|X))\s*\.')
SEC2_NUM_RE = re.compile(r'^\s*(\d+)\s*\.')


# -------------------- 노이즈 정규화 --------------------
def clean(s):
    s = re.sub(r'<[^>]+>', '', s)
    s = html.unescape(s).replace('　', ' ')   # 전각공백 -> 공백
    s = re.sub(r'<표\d*>|\[표\s*\d+\]', '', s)
    s = re.sub(r'주\d+\)', '', s)                  # 각주 마커
    s = re.sub(r'[※□○●]', '', s)  # ※ □ ○ ●
    return re.sub(r'[ \t]+', ' ', s).strip()


def clean_block(s):
    """산문 블록용: clean + 빈 줄 3연속+ -> 1줄, 연속공백 정리."""
    s = clean(s)
    s = re.sub(r'\n{3,}', '\n', s)
    return s.strip()


# -------------------- 표 그리드 파서 (검증본) --------------------
def parse_table(tbl):
    rows = re.findall(r'<TR\b[^>]*>(.*?)</TR>', tbl, re.S)
    grid = []
    pending = {}
    for r in rows:
        cells = re.findall(r'<T[HUD]\b([^>]*)>(.*?)</T[HUD]>', r, re.S)
        line = []
        col = 0

        def fill():
            nonlocal col
            while col in pending:
                txt, rem = pending[col]
                line.append(txt)
                if rem - 1 > 0:
                    pending[col] = (txt, rem - 1)
                else:
                    pending.pop(col)
                col += 1

        for attrs, body in cells:
            fill()
            txt = clean(body)
            cs = int(re.search(r'COLSPAN="?(\d+)', attrs, re.I).group(1)) if re.search(r'COLSPAN', attrs, re.I) else 1
            rs = int(re.search(r'ROWSPAN="?(\d+)', attrs, re.I).group(1)) if re.search(r'ROWSPAN', attrs, re.I) else 1
            for k in range(cs):
                line.append(txt)
                if rs > 1:
                    pending[col] = (txt, rs - 1)
                col += 1
        fill()
        grid.append(line)
    w = max((len(r) for r in grid), default=0)
    return [r + [''] * (w - len(r)) for r in grid]


# -------------------- 재귀 텍스트 분할 --------------------
def split_recursive(text, max_chars=MAX_CHARS, overlap=OVERLAP):
    """문단 -> 문장 -> 문자 재귀분할, overlap 적용."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    # 1) 문단
    paras = [p for p in re.split(r'\n+', text) if p.strip()]
    units = paras if len(paras) > 1 else None
    # 2) 문장
    if units is None:
        sents = re.split(r'(?<=[。\.!?])\s+|(?<=[。\.!?])(?=\S)', text)
        sents = [s for s in sents if s.strip()]
        units = sents if len(sents) > 1 else None
    # 3) 문자
    if units is None:
        units = [text[i:i + max_chars] for i in range(0, len(text), max_chars - overlap)]
        return [u.strip() for u in units if u.strip()]

    chunks = []
    cur = ""
    for u in units:
        u = u.strip()
        if not u:
            continue
        if len(u) > max_chars:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.extend(split_recursive(u, max_chars, overlap))
            continue
        if cur and len(cur) + 1 + len(u) > max_chars:
            chunks.append(cur)
            tail = cur[-overlap:] if overlap < len(cur) else cur
            cur = (tail + " " + u).strip()
        else:
            cur = (cur + "\n" + u).strip() if cur else u
    if cur:
        chunks.append(cur)
    return [c for c in chunks if c.strip()]


# -------------------- 표 -> 자연어 --------------------
UNIT_RE = re.compile(r'\(단위\s*[:：][^)]*\)')


def find_unit(grid, pre_text):
    for m in UNIT_RE.finditer(pre_text or ''):
        return m.group(0)
    for row in grid:
        for cell in row:
            m = UNIT_RE.search(cell)
            if m:
                return m.group(0)
    return ""


def _has_num(s):
    return bool(re.search(r'\d', s))


# 기간 라벨(숫자 포함이지만 헤더에 쓰임) — 데이터값으로 오판 방지
PERIOD_RE = re.compile(
    r'^(제\s*\d+\s*(기(말|초)?|분기|반기)|\d{4}\s*(년|\.\s*\d{1,2}(\.\s*\d{1,2})?)?|'
    r'[당전]\s*(반|분)?\s*기|전\s*전\s*기|\d+\s*분기|반기|상\s*반기|하\s*반기|FY\s*\d+)$'
)


def _cell_is_numeric(c):
    """숫자 데이터 셀 판정. 기간 라벨(제57기·2023년·당기 등)은 라벨로 취급(비숫자)."""
    c = c.strip()
    if not c or PERIOD_RE.match(c):
        return False
    return bool(re.search(r'\d', c))


def _is_fullspan(row):
    """비어있지 않은 셀이 2개 이상이며 모두 동일 값 = colspan 캡션/제목 행."""
    ne = [c.strip() for c in row if c.strip()]
    return len(ne) >= 2 and len(set(ne)) == 1


def _row_num_ratio(row):
    ne = [c.strip() for c in row if c.strip()]
    if not ne:
        return 0.0
    return sum(1 for c in ne if _cell_is_numeric(c)) / len(ne)


def effective_cols(grid):
    """fullspan 캡션 행을 제외한 실제 컬럼 폭(데이터/헤더행의 최대 비어있지않은 셀 수)."""
    best = 0
    for row in grid:
        if _is_fullspan(row):
            continue
        best = max(best, sum(1 for c in row if c.strip()))
    return best


def detect_header_rows(rows):
    """선두의 라벨성(숫자비율 0.5 미만) 행을 헤더로. 데이터행(숫자 우세) 만나면 멈춤.
    계층 헤더(4행 이상)도 허용(스캔 8행). 단 데이터 영역에 숫자가 전혀 없는
    텍스트 전용 표는 과흡수 방지 위해 헤더 1행으로 고정."""
    if not rows:
        return 0
    if len(rows) == 1:
        return 1
    n = 0
    for i in range(min(4, len(rows) - 1)):   # 헤더 최대 4단, 최소 1 데이터행 보존
        if _row_num_ratio(rows[i]) >= 0.5:
            break
        n += 1
    n = max(n, 1)
    # 헤더 이후 영역에 숫자 데이터가 없으면(텍스트 전용 표) 헤더 1행으로 축소
    if not any(_row_num_ratio(r) >= 0.5 for r in rows[n:]):
        return 1
    return n


def build_column_names(rows, hdr_n):
    w = max((len(r) for r in rows), default=0)
    names = []
    for c in range(w):
        toks = []
        for r in range(hdr_n):
            v = rows[r][c].strip() if c < len(rows[r]) else ''
            if v and (not toks or toks[-1] != v):
                toks.append(v)
        # 컬럼명은 하위 2단계(가장 구체적)만 사용 — 초심층 헤더 장황함 방지
        names.append(' '.join(toks[-2:]).strip())
    # 중복 컬럼명 -> 위치 접미사로 구분 (모든 컬럼 동일라벨 방지)
    counts = {}
    for nm in names:
        if nm:
            counts[nm] = counts.get(nm, 0) + 1
    seen = {}
    for i, nm in enumerate(names):
        if nm and counts[nm] > 1:
            seen[nm] = seen.get(nm, 0) + 1
            names[i] = "%s(%d)" % (nm, seen[nm])
    return names


def table_to_nl(grid, unit):
    """grid -> (header_line, [data_line,...], hdr_n)."""
    # 완전히 빈 행 제거
    grid = [r for r in grid if any(c.strip() for c in r)]
    if not grid:
        return "", [], 0
    # 선두 fullspan 캡션/제목 행 제거(단위는 find_unit 이 따로 보존)
    while grid and _is_fullspan(grid[0]):
        grid = grid[1:]
    if not grid:
        return "", [], 0
    hdr_n = detect_header_rows(grid)
    col_names = build_column_names(grid, hdr_n)
    header_line = "헤더: " + " | ".join([c for c in col_names if c]) if any(col_names) else ""
    data_lines = []
    for r in range(hdr_n, len(grid)):
        row = grid[r]
        if _is_fullspan(row):       # 중간 소제목(전체 병합) 행은 건너뜀
            continue
        rowhead = row[0].strip() if row else ''
        parts = []
        for c in range(1, len(row)):
            val = row[c].strip()
            cn = col_names[c].strip() if c < len(col_names) else ''
            if not val:
                continue
            if cn:
                parts.append("%s=%s" % (cn, val))
            else:
                parts.append(val)
        if not rowhead and not parts:
            continue
        if rowhead and parts:
            data_lines.append("%s | %s" % (rowhead, "; ".join(parts)))
        elif rowhead:
            data_lines.append(rowhead)
        else:
            data_lines.append("; ".join(parts))
    return header_line, data_lines, hdr_n


# -------------------- 청크 레코드 --------------------
def mk_chunk(corp_code, rcept_no, chunk_type, section_path, prefix, body, seq):
    embedding_text = prefix + "\n" + body
    chunk_id = hashlib.sha1(
        (corp_code + rcept_no + section_path + str(seq) + body).encode('utf-8')
    ).hexdigest()[:16]
    token_count = max(1, len(embedding_text) // 2)
    return {
        "chunk_id": chunk_id,
        "corp_code": corp_code,
        "rcept_no": rcept_no,
        "chunk_type": chunk_type,
        "section_path": section_path,
        "embedding_text": embedding_text,
        "token_count": token_count,
    }


# -------------------- 섹션 추출 --------------------
def first_title(segment):
    m = re.search(r'<TITLE[^>]*>(.*?)</TITLE>', segment, re.S)
    return clean(m.group(1)) if m else ''


def iter_target_segments(xml):
    """메인 본문 xml에서 청킹 대상 (section_path, segment_text) 리스트.
    SECTION-1(장) 단위로 자르고, 대상 장이면 그 본문(절 포함)을 통째로 사용.
    III장은 대상 절(3,5)만 SECTION-2 단위로 잘라 사용."""
    segs = []
    # SECTION-1 시작 위치들
    s1_starts = [m.start() for m in re.finditer(r'<SECTION-1\b', xml)]
    s1_starts.append(len(xml))
    for i in range(len(s1_starts) - 1):
        block = xml[s1_starts[i]:s1_starts[i + 1]]
        title = first_title(block)
        rm = ROMAN_RE.match(title)
        if not rm:
            continue
        roman = rm.group(1)
        if roman in TARGET_CHAPTERS:
            segs.append((title.strip(), block))
        elif roman == "III":
            # SECTION-2 단위로 절 분리
            s2_starts = [m.start() for m in re.finditer(r'<SECTION-2\b', block)]
            s2_starts.append(len(block))
            for j in range(len(s2_starts) - 1):
                sub = block[s2_starts[j]:s2_starts[j + 1]]
                stitle = first_title(sub)
                sm = SEC2_NUM_RE.match(stitle)
                if sm and sm.group(1) in CH3_TARGET_SECTIONS:
                    segs.append(("III. 재무에 관한 사항 > " + stitle.strip(), sub))
        # else: 스킵 장 (I, VI, VII, VIII, XII)
    return segs


def extract_prose(segment):
    """segment 내 <P> 텍스트만 모아 정규화된 블록 반환 (표 안 P는 TABLE 제거 후라 제외)."""
    # TABLE 영역 제거 -> 표 안 텍스트 배제
    no_table = re.sub(r'<TABLE\b.*?</TABLE>', ' ', segment, flags=re.S)
    parts = re.findall(r'<P\b[^>]*>(.*?)</P>', no_table, re.S)
    texts = []
    for p in parts:
        t = clean(p)
        if t:
            texts.append(t)
    block = "\n".join(texts)
    return clean_block(block)


def extract_tables(segment):
    """(table_xml, preceding_text) 리스트."""
    out = []
    for m in re.finditer(r'<TABLE\b.*?</TABLE>', segment, re.S):
        pre = segment[max(0, m.start() - 400):m.start()]
        pre_txt = clean(pre)
        out.append((m.group(0), pre_txt))
    return out


# -------------------- 메인 처리 --------------------
def load_list_meta():
    """corp_code -> {rcept_no: {report_nm, rcept_dt}}"""
    meta = {}
    for comp, code in COMPANIES.items():
        meta[code] = {}
        for f in glob.glob(str(RAW / comp / "list" / "list_*.json")):
            try:
                data = json.load(open(f, encoding='utf-8'))
            except Exception:
                continue
            items = data if isinstance(data, list) else None
            if items is None and isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, list):
                        items = v
                        break
            if not items:
                continue
            for it in items:
                rn = str(it.get('rcept_no', ''))
                if rn:
                    meta[code][rn] = {
                        "report_nm": it.get('report_nm', ''),
                        "rcept_dt": it.get('rcept_dt', ''),
                        "corp_name": it.get('corp_name', comp),
                    }
    return meta


def process_table(tbl_xml, pre_txt, corp_code, rcept_no, section_path, prefix, seq_state, stats):
    grid = parse_table(tbl_xml)
    total_cells = sum(len(r) for r in grid)
    unit = find_unit(grid, pre_txt)
    header_line, data_lines, hdr_n = table_to_nl(grid, unit)
    # 스킵: 단일컬럼(표지·서명·단일문단 래퍼) 또는 데이터행 없음.
    # 헤더+1행짜리 다열 표는 보존(단일행 실데이터 손실 방지).
    if effective_cols(grid) <= 1 or not data_lines:
        stats['skipped_tables'] += 1
        return []
    cap = (unit + "\n") if unit else ""
    head = (header_line + "\n") if header_line else ""
    records = []
    if total_cells > GRID_CELL_LIMIT and len(data_lines) > 1:
        # 데이터행 그룹 분할 (각 그룹에 헤더+단위 반복)
        ncols = len(grid[0]) if grid and grid[0] else 1
        per = max(1, GRID_CELL_LIMIT // max(1, ncols))
        for gi in range(0, len(data_lines), per):
            group = data_lines[gi:gi + per]
            body = cap + head + "\n".join(group)
            records.append(mk_chunk(corp_code, rcept_no, "table_nl", section_path,
                                    prefix, body.strip(), seq_state[0]))
            seq_state[0] += 1
    else:
        body = cap + head + "\n".join(data_lines)
        records.append(mk_chunk(corp_code, rcept_no, "table_nl", section_path,
                                prefix, body.strip(), seq_state[0]))
        seq_state[0] += 1
    return records


def process_xml(xml, doc_is_sub, sub_docname, corp_code, rcept_no, report_nm, comp_name, stats):
    """하나의 xml(메인 또는 sub)에서 청크 레코드 리스트 반환."""
    records = []
    seq_state = [0]

    if doc_is_sub:
        # 감사보고서 전체를 대상으로
        segments = [(sub_docname, xml)]
    else:
        segments = iter_target_segments(xml)

    for section_path, segment in segments:
        prefix = "[%s · %s · %s]" % (comp_name, report_nm, section_path)

        # 산문
        prose = extract_prose(segment)
        if prose:
            for piece in split_recursive(prose):
                if len(piece) < MIN_TEXT:
                    continue
                rec = mk_chunk(corp_code, rcept_no, "text_micro", section_path,
                               prefix, piece, seq_state[0])
                seq_state[0] += 1
                records.append(rec)
                stats['text_micro'] += 1

        # 표
        for tbl_xml, pre_txt in extract_tables(segment):
            recs = process_table(tbl_xml, pre_txt, corp_code, rcept_no,
                                  section_path, prefix, seq_state, stats)
            for r in recs:
                records.append(r)
                stats['table_nl'] += 1
    return records


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    meta = load_list_meta()

    grand = {'text_micro': 0, 'table_nl': 0, 'skipped_tables': 0, 'docs': 0, 'chunks': 0}
    per_company = {}
    samples_text = []
    samples_table = []
    failures = []

    for comp, code in COMPANIES.items():
        per_company.setdefault(comp, {'text_micro': 0, 'table_nl': 0, 'docs': 0, 'chunks': 0})
        zips = sorted(glob.glob(str(RAW / comp / "documents" / "*.zip")))
        for zp in zips:
            rcept_no = Path(zp).stem
            m = meta.get(code, {}).get(rcept_no, {})
            report_nm = m.get('report_nm') or rcept_no
            comp_name = m.get('corp_name') or comp
            try:
                z = zipfile.ZipFile(zp)
            except Exception as e:
                failures.append("%s zip open 실패: %s" % (zp, e))
                continue
            names = z.namelist()
            doc_records = []
            stats = {'text_micro': 0, 'table_nl': 0, 'skipped_tables': 0}

            # 메인 본문 (밑줄 없는 xml)
            main_names = [n for n in names if n.lower().endswith('.xml') and '_' not in Path(n).stem]
            sub_names = [n for n in names if n.lower().endswith('.xml') and '_' in Path(n).stem]

            for mn in main_names:
                try:
                    xml = z.read(mn).decode('utf-8', 'replace')
                except Exception as e:
                    failures.append("%s/%s read 실패: %s" % (rcept_no, mn, e))
                    continue
                recs = process_xml(xml, False, None, code, rcept_no, report_nm, comp_name, stats)
                if not recs:
                    failures.append("%s/%s: 대상 섹션 0개" % (rcept_no, mn))
                doc_records.extend(recs)

            for sn in sub_names:
                try:
                    xml = z.read(sn).decode('utf-8', 'replace')
                except Exception as e:
                    failures.append("%s/%s read 실패: %s" % (rcept_no, sn, e))
                    continue
                dn = re.search(r'<DOCUMENT-NAME[^>]*>(.*?)</DOCUMENT-NAME>', xml, re.S)
                sub_docname = clean(dn.group(1)) if dn else "감사보고서"
                recs = process_xml(xml, True, sub_docname, code, rcept_no, report_nm, comp_name, stats)
                doc_records.extend(recs)

            # 샘플 수집
            for r in doc_records:
                if r['chunk_type'] == 'text_micro' and len(samples_text) < 2:
                    samples_text.append(r)
                elif r['chunk_type'] == 'table_nl' and len(samples_table) < 2:
                    samples_table.append(r)

            # 출력
            outpath = OUT / ("%s_%s.jsonl" % (comp, rcept_no))
            with open(outpath, 'w', encoding='utf-8') as f:
                for r in doc_records:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")

            n_text = sum(1 for r in doc_records if r['chunk_type'] == 'text_micro')
            n_tbl = sum(1 for r in doc_records if r['chunk_type'] == 'table_nl')
            per_company[comp]['text_micro'] += n_text
            per_company[comp]['table_nl'] += n_tbl
            per_company[comp]['docs'] += 1
            per_company[comp]['chunks'] += len(doc_records)
            grand['text_micro'] += n_text
            grand['table_nl'] += n_tbl
            grand['skipped_tables'] += stats['skipped_tables']
            grand['docs'] += 1
            grand['chunks'] += len(doc_records)
            print("  [%s] %s (%s) -> text_micro=%d table_nl=%d skip_tbl=%d total=%d"
                  % (comp, rcept_no, report_nm, n_text, n_tbl, stats['skipped_tables'], len(doc_records)))

    # ---------- 요약 보고 ----------
    print("\n" + "=" * 70)
    print("청킹 요약")
    print("=" * 70)
    for comp in COMPANIES:
        c = per_company[comp]
        print("  %-10s docs=%d  text_micro=%d  table_nl=%d  total=%d"
              % (comp, c['docs'], c['text_micro'], c['table_nl'], c['chunks']))
    print("-" * 70)
    print("  전체 docs=%d  text_micro=%d  table_nl=%d  total_chunks=%d  skipped_tables=%d"
          % (grand['docs'], grand['text_micro'], grand['table_nl'], grand['chunks'], grand['skipped_tables']))
    if failures:
        print("\n[파싱/대상 경고] %d건:" % len(failures))
        for fl in failures[:40]:
            print("  - " + fl)
    else:
        print("\n[파싱 경고] 없음")

    print("\n----- text_micro 샘플 -----")
    for s in samples_text:
        print("chunk_id=%s section_path=%s" % (s['chunk_id'], s['section_path']))
        print(s['embedding_text'][:500])
        print("...")
    print("\n----- table_nl 샘플 -----")
    for s in samples_table:
        print("chunk_id=%s section_path=%s" % (s['chunk_id'], s['section_path']))
        print(s['embedding_text'][:500])
        print("...")

    print("\n출력 경로: %s" % OUT)


if __name__ == "__main__":
    main()
