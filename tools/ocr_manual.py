"""OCR scanned Atari PILOT manuals to searchable text.

Renders each PDF page to a bitmap with PyMuPDF, then runs Tesseract over it.
Written for the two image-only Atari PILOT manuals; the External Specification
already ships an OCR text layer from the Internet Archive and is not processed
here.

Usage:
    uv run --with pymupdf python tools/ocr_manual.py <pdf> <outdir> [first] [last]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import fitz  # PyMuPDF

TESSERACT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
DPI = 200
PSM = "6"  # assume a single uniform block of text


def ocr_page(doc: fitz.Document, index: int, outdir: Path, tmp: Path) -> str:
    """Render and OCR a single page, returning the recognised text."""
    page = doc[index]
    pix = page.get_pixmap(dpi=DPI)
    img = tmp / f"page-{index + 1:04d}.png"
    pix.save(img)

    base = tmp / f"page-{index + 1:04d}"
    subprocess.run(
        [
            str(TESSERACT),
            str(img),
            str(base),
            "--psm",
            PSM,
            "-l",
            "eng",
        ],
        check=True,
        capture_output=True,
    )
    text = base.with_suffix(".txt").read_text(encoding="utf-8", errors="replace")

    # Keep the page image; drop the intermediate PNG to bound disk usage.
    target = outdir / f"page-{index + 1:04d}.txt"
    target.write_text(text, encoding="utf-8")
    img.unlink(missing_ok=True)
    return text


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2

    pdf = Path(sys.argv[1])
    outdir = Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)
    tmp = outdir / "_pages"
    tmp.mkdir(exist_ok=True)

    doc = fitz.open(pdf)
    first = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    last = int(sys.argv[4]) if len(sys.argv) > 4 else doc.page_count

    combined: list[str] = []
    for n in range(first, min(last, doc.page_count) + 1):
        text = ocr_page(doc, n - 1, outdir, tmp)
        combined.append(f"\n===== PAGE {n} =====\n{text}")
        print(f"  page {n}/{last}: {len(text)} chars", flush=True)

    name = pdf.stem.replace(" ", "_")
    out = outdir.parent / f"{name}_ocr.txt"
    out.write_text("".join(combined), encoding="utf-8")
    print(f"wrote {out} ({sum(len(c) for c in combined)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
