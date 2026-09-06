#!/usr/bin/env python3
"""Render PDF pages to PNG for a visual read, and refuse to hand back a blank page.

Renderer choice is not cosmetic. poppler's pdftoppm needs the Adobe-Japan1 (and
friends) language packs to draw CJK; without them it emits a page containing the
table rules and no glyphs -- which looks exactly like a genuinely empty form and
is therefore a plausible wrong answer. pypdfium2 carries its own font handling
and does not have that failure mode.

Usage: python3 render_pages.py FILE.pdf [--pages 1,3] [--dpi 200] [--out DIR]
"""
import argparse, os, subprocess, sys

# A page carrying text has a meaningful spread of ink. A font-failure render is
# near-uniform white with only thin rules, which lands an order of magnitude
# below this.
BLANK_INK_THRESHOLD = 0.005


def ensure(mod, pkg):
    try:
        return __import__(mod)
    except ImportError:
        pass
    for extra in (["--break-system-packages"], []):
        if subprocess.run([sys.executable, "-m", "pip", "install", "-q", pkg] + extra,
                          capture_output=True).returncode == 0:
            try:
                return __import__(mod)
            except ImportError:
                break
    return None


def ink_fraction(image):
    """Share of pixels dark enough to be marks rather than paper. Pure."""
    grey = image.convert("L")
    px = grey.tobytes()
    if not px:
        return 0.0
    return sum(1 for v in px if v < 200) / len(px)


def is_probably_blank(ink):
    """A render this empty is more likely a font failure than an empty page."""
    return ink < BLANK_INK_THRESHOLD


def render(pdf_path, pages=None, dpi=200, out_dir="."):
    """Render pages to PNG. Returns [(path, ink_fraction), ...]."""
    pdfium = ensure("pypdfium2", "pypdfium2")
    if pdfium is None:
        raise RuntimeError("pypdfium2 unavailable; try PyMuPDF (import fitz). "
                           "Avoid pdftoppm for CJK documents.")
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(str(pdf_path)))[0]

    # The document and every page must be closed before returning. Windows
    # refuses to delete or move a file while a handle is open, so leaking one
    # here turns "render then clean up" into a PermissionError -- on Windows
    # only, which is exactly the kind of bug a single-platform test never sees.
    doc = pdfium.PdfDocument(str(pdf_path))
    results = []
    try:
        wanted = list(pages) if pages else list(range(1, len(doc) + 1))
        for n in wanted:
            page = doc[n - 1]
            try:
                image = page.render(scale=dpi / 72).to_pil()
            finally:
                close = getattr(page, "close", None)
                if close:
                    close()
            path = os.path.join(out_dir, f"{stem}_p{n}.png")
            image.save(path)
            results.append((path, ink_fraction(image)))
            image.close()
    finally:
        doc.close()
    return results


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--pages", help="1-indexed, e.g. 1,3")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--out", default=".")
    a = ap.parse_args(argv)

    pages = [int(x) for x in a.pages.split(",")] if a.pages else None
    try:
        results = render(a.pdf, pages, a.dpi, a.out)
    except RuntimeError as e:
        sys.stderr.write(f"{e}\n")
        return 1

    for path, ink in results:
        flag = ("  <-- nearly blank: suspect a font or renderer failure rather than "
                "an empty page") if is_probably_blank(ink) else ""
        print(f"{path}  ink={ink:.4f}{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
