"""Stage B-1: 스냅샷 PNG 생성.

PDF 있음 → PyMuPDF로 1쪽 PNG (300dpi 1/2)
PDF 없음 → body_clean.txt 앞 500자를 PIL로 PNG 렌더 (맑은 고딕)

출력: ___test/2_Chuck/02_meta/snapshots/{corp}/{rcept_no}.png
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont

from polaris.config import (
    DATA_ROOT, FILTERED_DIR, META_DIR,
    CORPS as _ENV_CORPS, CORP_NAMES as _ENV_CORP_NAMES, get_corp_meta,
)
RAW = DATA_ROOT / "rawData"
CLEAN = FILTERED_DIR
OUT = META_DIR / "snapshots"
LOG = META_DIR / "_b1_log.jsonl"

CORPS = list(_ENV_CORPS)
CORP_NAMES = {cc: (_ENV_CORP_NAMES.get(cc) or get_corp_meta(cc).get("corp_name", cc))
              for cc in CORPS}

# 한글 폰트 (Windows)
FONT_PATH = "C:/Windows/Fonts/malgun.ttf"
FONT_PATH_BOLD = "C:/Windows/Fonts/malgunbd.ttf"


def snapshot_pdf(pdf_path: Path, out_path: Path, dpi: int = 150) -> dict:
    """PDF 1쪽 → PNG."""
    try:
        doc = fitz.open(pdf_path)
        if len(doc) == 0:
            return {"status": "empty_pdf"}
        page = doc[0]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pix.save(out_path)
        doc.close()
        return {"status": "ok", "method": "pdf", "size_kb": out_path.stat().st_size // 1024,
                "width": pix.width, "height": pix.height}
    except Exception as e:
        return {"status": "error", "method": "pdf", "error": str(e)}


def snapshot_text(text_path: Path, out_path: Path, rcept_no: str,
                  width: int = 900, max_chars: int = 800) -> dict:
    """본문 텍스트 앞 부분을 PNG로 렌더 (PIL)."""
    try:
        if not text_path.is_file():
            return {"status": "no_text"}
        text = text_path.read_text(encoding="utf-8")
        if not text:
            return {"status": "empty_text"}
        snippet = text[:max_chars]

        # 폰트
        font_title = ImageFont.truetype(FONT_PATH_BOLD, 20)
        font_body = ImageFont.truetype(FONT_PATH, 14)

        # 줄 단위 wrap (대략)
        lines = []
        title_line = f"[rcept_no: {rcept_no}]"
        lines.append((title_line, font_title))
        lines.append(("", font_body))
        for para in snippet.split("\n"):
            # wrap: 한 줄 ~60자
            if not para.strip():
                lines.append(("", font_body))
                continue
            words = para.split()
            cur = ""
            for w in words:
                if len(cur) + len(w) + 1 > 60:
                    lines.append((cur, font_body))
                    cur = w
                else:
                    cur = (cur + " " + w) if cur else w
            if cur:
                lines.append((cur, font_body))

        # 높이 계산
        line_h = 22
        height = 20 + len(lines) * line_h + 20
        img = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(img)
        y = 20
        for ln, fnt in lines:
            draw.text((20, y), ln, font=fnt, fill="black")
            y += line_h

        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path)
        return {"status": "ok", "method": "text",
                "size_kb": out_path.stat().st_size // 1024,
                "width": width, "height": height, "chars": len(snippet)}
    except Exception as e:
        return {"status": "error", "method": "text", "error": str(e)}


def main():
    t0 = time.time()
    log_lines = []
    summary = {"pdf_ok": 0, "text_ok": 0, "fail": 0, "per_corp": {}}

    for corp in CORPS:
        print(f"\n=== {CORP_NAMES[corp]} ({corp}) ===")
        docs_dir = RAW / corp / "documents"
        clean_dir = CLEAN / corp / "body_clean"
        out_dir = OUT / corp
        out_dir.mkdir(parents=True, exist_ok=True)
        corp_stat = {"pdf": 0, "text": 0, "fail": 0}

        for rno_dir in sorted(docs_dir.iterdir()):
            if not rno_dir.is_dir():
                continue
            rno = rno_dir.name
            out_path = out_dir / f"{rno}.png"
            pdf_path = rno_dir / "original.pdf"

            if pdf_path.is_file():
                r = snapshot_pdf(pdf_path, out_path)
            else:
                text_path = clean_dir / f"{rno}.txt"
                r = snapshot_text(text_path, out_path, rno)

            r.update({"corp": corp, "rcept_no": rno})
            log_lines.append(r)
            if r["status"] == "ok":
                if r["method"] == "pdf":
                    summary["pdf_ok"] += 1
                    corp_stat["pdf"] += 1
                else:
                    summary["text_ok"] += 1
                    corp_stat["text"] += 1
            else:
                summary["fail"] += 1
                corp_stat["fail"] += 1

        summary["per_corp"][corp] = corp_stat
        print(f"  PDF→PNG {corp_stat['pdf']} | text→PNG {corp_stat['text']} | fail {corp_stat['fail']}")

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("w", encoding="utf-8") as f:
        for line in log_lines:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    elapsed = time.time() - t0
    total = summary["pdf_ok"] + summary["text_ok"] + summary["fail"]
    print(f"\n=== Stage B-1 완료 ({elapsed:.1f}s) ===")
    print(f"  PDF→PNG: {summary['pdf_ok']}건")
    print(f"  text→PNG: {summary['text_ok']}건")
    print(f"  fail: {summary['fail']}건")
    print(f"  총 스냅샷: {total}/{135}")
    print(f"  로그: {LOG}")

    # manifest 업데이트
    manifest = DATA_ROOT / "2_Chuck" / "_manifest.json"
    m = {}
    if manifest.exists():
        try:
            m = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            m = {}
    m["stage_b1"] = {
        "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_sec": elapsed,
        "summary": summary,
    }
    manifest.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
