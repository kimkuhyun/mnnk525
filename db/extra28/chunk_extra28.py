# -*- coding: utf-8 -*-
"""POLARIS 결정론적 청커 — extra28 (연결사 28개).
corps.tsv 의 28개사를 대상으로 chunk.py 와 동일한 로직·파라미터로 청킹.
LLM 호출/네트워크 없음. 표준 라이브러리만 사용.

실행 (저장소 루트에서):
    PYTHONIOENCODING=utf-8 python -X utf8 db/extra28/chunk_extra28.py
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

# corps.tsv 로드: 회사명 -> corp_code
def load_companies():
    tsv = ROOT / "db" / "extra28" / "corps.tsv"
    result = {}
    with open(tsv, encoding='utf-8') as f:
        for i, line in enumerate(f):
            line = line.rstrip('\n')
            if i == 0 or not line.strip():
                continue  # 헤더 또는 빈 줄 스킵
            parts = line.split('\t')
            if len(parts) >= 2:
                corp_code = parts[0].strip()
                name = parts[1].strip()
                if corp_code and name:
                    result[name] = corp_code
    return result

COMPANIES = load_companies()

# 청킹 정책 (chunk.py 와 동일)
MAX_CHARS = 800
OVERLAP = 80
MIN_TEXT = 20
GRID_CELL_LIMIT = 120

TARGET_CHAPTERS = {"II", "IV", "V", "IX", "X", "XI"}
CH3_TARGET_SECTIONS = {"3", "5"}

ROMAN_RE = re.compile(r'^\s*((?:XII|XI|IX|IV|VI{0,3}|V|I{1,3}|X))\s*\.')
SEC2_NUM_RE = re.compile(r'^\s*(\d+)\s*\.')


# -------------------- 노이즈 정규화 --------------------
def clean(s):
    s = re.sub(r'<[^>]+>', '', s)
    s = html.unescape(s).replace('　', ' ')
    s = re.sub(r'<표\d*>|\[표\s*\d+\]', '', s)
    s = re.sub(r'주\d+\)', '', s)
    s = re.sub(r'[※□○●]', '', s)
    return re.sub(r'[ \t]+', ' ', s).strip()


def clean_block(s):
    s = clean(s)
    s = re.sub(r'\n{3,}', '\n', s)
    return s.strip()


# -------------------- 표 그리드 파서 --------------------
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
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    paras = [p for p in re.split(r'\n+', text) if p.strip()]
    units = paras if len(paras) > 1 else None
    if units is None:
        sents = re.split(r'(?<=[。\.!?])\s+|(?<=[。\.!?])(?=\S)', text)
        sents = [s for s in sents if s.strip()]
        units = sents if len(sents) > 1 else None
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


PERIOD_RE = re.compile(
    r'^(제\s*\d+\s*(기(말|초)?|분기|반기)|\d{4}\s*(년|\.\s*\d{1,2}(\.\s*\d{1,2})?)?|'
    r'[당전]\s*(반|분)?\s*기|전\s*전\s*기|\d+\s*분기|반기|상\s*반기|하\s*반기|FY\s*\d+)$'
)


def _cell_is_numeric(c):
    c = c.strip()
    if not c or PERIOD_RE.match(c):
        return False
    return bool(re.search(r'\d', c))


def _is_fullspan(row):
    ne = [c.strip() for c in row if c.strip()]
    return len(ne) >= 2 and len(set(ne)) == 1


def _row_num_ratio(row):
    ne = [c.strip() for c in row if c.strip()]
    if not ne:
        return 0.0
    return sum(1 for c in ne if _cell_is_numeric(c)) / len(ne)


def effective_cols(grid):
    best = 0
    for row in grid:
        if _is_fullspan(row):
            continue
        best = max(best, sum(1 for c in row if c.strip()))
    return best


def detect_header_rows(rows):
    if not rows:
        return 0
    if len(rows) == 1:
        return 1
    n = 0
    for i in range(min(4, len(rows) - 1)):
        if _row_num_ratio(rows[i]) >= 0.5:
            break
        n += 1
    n = max(n, 1)
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
        names.append(' '.join(toks[-2:]).strip())
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
    grid = [r for r in grid if any(c.strip() for c in r)]
    if not grid:
        return "", [], 0
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
        if _is_fullspan(row):
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
    segs = []
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
            s2_starts = [m.start() for m in re.finditer(r'<SECTION-2\b', block)]
            s2_starts.append(len(block))
            for j in range(len(s2_starts) - 1):
                sub = block[s2_starts[j]:s2_starts[j + 1]]
                stitle = first_title(sub)
                sm = SEC2_NUM_RE.match(stitle)
                if sm and sm.group(1) in CH3_TARGET_SECTIONS:
                    segs.append(("III. 재무에 관한 사항 > " + stitle.strip(), sub))
    return segs


def extract_prose(segment):
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
    out = []
    for m in re.finditer(r'<TABLE\b.*?</TABLE>', segment, re.S):
        pre = segment[max(0, m.start() - 400):m.start()]
        pre_txt = clean(pre)
        out.append((m.group(0), pre_txt))
    return out


# -------------------- 메인 처리 --------------------
def load_list_meta():
    """corp_code -> {rcept_no: {report_nm, rcept_dt, corp_name}}"""
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
    if effective_cols(grid) <= 1 or not data_lines:
        stats['skipped_tables'] += 1
        return []
    cap = (unit + "\n") if unit else ""
    head = (header_line + "\n") if header_line else ""
    records = []
    if total_cells > GRID_CELL_LIMIT and len(data_lines) > 1:
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
    records = []
    seq_state = [0]

    if doc_is_sub:
        segments = [(sub_docname, xml)]
    else:
        segments = iter_target_segments(xml)

    for section_path, segment in segments:
        prefix = "[%s · %s · %s]" % (comp_name, report_nm, section_path)

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

        for tbl_xml, pre_txt in extract_tables(segment):
            recs = process_table(tbl_xml, pre_txt, corp_code, rcept_no,
                                  section_path, prefix, seq_state, stats)
            for r in recs:
                records.append(r)
                stats['table_nl'] += 1
    return records


def main():
    import sys
    OUT.mkdir(parents=True, exist_ok=True)
    meta = load_list_meta()

    grand = {'text_micro': 0, 'table_nl': 0, 'skipped_tables': 0, 'docs': 0, 'chunks': 0}
    per_company = {}
    failures = []
    skipped_companies = []   # zip 0개
    chunked_companies = []   # 실제 청킹된 회사

    for comp, code in COMPANIES.items():
        per_company.setdefault(comp, {'text_micro': 0, 'table_nl': 0, 'docs': 0, 'chunks': 0})
        zips = sorted(glob.glob(str(RAW / comp / "documents" / "*.zip")))
        if not zips:
            skipped_companies.append(comp)
            continue
        chunked_companies.append(comp)

        for zp in zips:
            rcept_no = Path(zp).stem
            # 멱등: 이미 출력 파일이 있으면 건너뜀
            outpath = OUT / ("%s_%s.jsonl" % (comp, rcept_no))
            if outpath.exists():
                sys.stdout.write("  [SKIP] %s_%s already exists\n" % (comp, rcept_no))
                sys.stdout.flush()
                continue

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
            sys.stdout.write("  [%s] %s (%s) -> text_micro=%d table_nl=%d skip_tbl=%d total=%d\n"
                  % (comp, rcept_no, report_nm, n_text, n_tbl, stats['skipped_tables'], len(doc_records)))
            sys.stdout.flush()

    # ---------- 요약 보고 ----------
    sys.stdout.write("\n" + "=" * 70 + "\n")
    sys.stdout.write("청킹 요약 (extra28)\n")
    sys.stdout.write("=" * 70 + "\n")
    sys.stdout.write("청킹된 회사 (%d개):\n" % len(chunked_companies))
    for comp in chunked_companies:
        c = per_company[comp]
        sys.stdout.write("  %-15s docs=%d  text_micro=%d  table_nl=%d  total=%d\n"
              % (comp, c['docs'], c['text_micro'], c['table_nl'], c['chunks']))
    sys.stdout.write("-" * 70 + "\n")
    sys.stdout.write("  전체 docs=%d  text_micro=%d  table_nl=%d  total_chunks=%d  skipped_tables=%d\n"
          % (grand['docs'], grand['text_micro'], grand['table_nl'], grand['chunks'], grand['skipped_tables']))
    sys.stdout.write("\n정기보고서 없음(zip 0개) — %d개사:\n" % len(skipped_companies))
    for comp in skipped_companies:
        sys.stdout.write("  - %s\n" % comp)
    if failures:
        sys.stdout.write("\n[파싱/대상 경고] %d건:\n" % len(failures))
        for fl in failures[:40]:
            sys.stdout.write("  - " + fl + "\n")
    else:
        sys.stdout.write("\n[파싱 경고] 없음\n")
    sys.stdout.write("\n출력 경로: %s\n" % OUT)
    sys.stdout.flush()


if __name__ == "__main__":
    main()
