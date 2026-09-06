#!/usr/bin/env python3
"""Measure what the routing decision is actually worth, in tokens.

The claim this skill rests on is that reading a text-based PDF as extracted
Markdown costs far less context than reading it as rendered page images. That
claim is a measurable property of the two representations -- it does not need an
agent in the loop -- so this benchmark measures it directly and reproducibly.

Image token cost follows Anthropic's documented approximation,
tokens ~= (width * height) / 750, applied after the long edge is clamped to
1568 px the way the API downscales oversized images.

Usage:  python3 bench/token_economics.py [--pages 40] [--dpi 200]
"""
import argparse, io, os, subprocess, sys, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

MAX_EDGE = 1568
PIXELS_PER_TOKEN = 750

BODY = (
    "The fundamental problem of communication is that of reproducing at one point either "
    "exactly or approximately a message selected at another point. Frequently the messages "
    "have meaning, that is they refer to or are correlated according to some system with "
    "certain physical or conceptual entities. These semantic aspects of communication are "
    "irrelevant to the engineering problem. The significant aspect is that the actual "
    "message is one selected from a set of possible messages. The system must be designed "
    "to operate for each possible selection, not just the one which will actually be "
    "chosen, since this is unknown at the time of design. "
)


def build_report(path, pages, chars_per_page=3200):
    """A report at a chosen text density, in characters of body text per page."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    width, height = A4
    c = canvas.Canvas(str(path), pagesize=A4)
    words = (BODY * 60).split()
    cursor = 0
    per_line = 95
    lines_per_page = max(1, chars_per_page // per_line)
    for page in range(pages):
        c.setFont("Helvetica-Bold", 14)
        c.drawString(56, height - 60, f"{page + 1}. Section heading for page {page + 1}")
        c.setFont("Helvetica", 10.5)
        y = height - 90
        for _ in range(lines_per_page):
            line, count = [], 0
            while count < per_line and cursor < len(words):
                w = words[cursor]; cursor = (cursor + 1) % len(words)
                line.append(w); count += len(w) + 1
            c.drawString(56, y, " ".join(line))
            y -= 14
            if y < 60:
                break
        if page % 5 == 4:                     # a table every fifth page
            c.setFont("Helvetica", 9)
            for row in range(4):
                c.drawString(56, 60 - row * 11, f"row {row}   {row * 137}   {row * 4.2:.2f}   ok")
        c.showPage()
    c.save()


def count_text_tokens(text):
    try:
        import tiktoken
        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return max(1, len(text) // 4)          # coarse fallback


def image_tokens(width, height):
    scale = min(1.0, MAX_EDGE / max(width, height))
    w, h = int(width * scale), int(height * scale)
    return round(w * h / PIXELS_PER_TOKEN), (w, h)


def measure(pages, dpi, chars_per_page, tmp):
    import pdf_inspector
    import render_pages
    from PIL import Image
    pdf = os.path.join(tmp, f"r_{pages}p_{chars_per_page}c.pdf")
    build_report(pdf, pages, chars_per_page)
    md = pdf_inspector.process_pdf(pdf).markdown or ""
    text_tok = count_text_tokens(md)
    rendered = render_pages.render(pdf, pages=[1], dpi=dpi, out_dir=tmp)
    with Image.open(rendered[0][0]) as im:
        per_page_tok, dims = image_tokens(*im.size)
    return {"pdf": pdf, "chars": len(md), "text": text_tok,
            "per_page": per_page_tok, "image": per_page_tok * pages, "dims": dims}


def sweep(pages, dpi):
    print(f"{pages}-page document, images rendered at {dpi} dpi\n")
    print(f"{'density (chars/page)':>21} | {'text tok':>9} | {'image tok':>10} | {'ratio':>6}")
    print("-" * 55)
    tmp = tempfile.mkdtemp(prefix="tokensweep-")
    for cpp, label in [(600, "slide / cover"), (1600, "sparse report"),
                       (3200, "journal page"), (5000, "dense two-column")]:
        m = measure(pages, dpi, cpp, tmp)
        print(f"{cpp:>7} {label:<13} | {m['text']:>9,} | {m['image']:>10,} | "
              f"{m['image'] / max(m['text'], 1):>5.1f}x")
        os.remove(m["pdf"])
    for f in os.listdir(tmp):
        os.remove(os.path.join(tmp, f))
    os.rmdir(tmp)
    print("\nImage cost is flat per page; text cost scales with density, so the")
    print("saving is largest exactly where a document is easy to read anyway.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=40)
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--chars-per-page", type=int, default=3200,
                    help="body text density; ~3200 is a typical journal page, ~600 a slide")
    ap.add_argument("--sweep", action="store_true", help="table across densities")
    ap.add_argument("--keep", action="store_true", help="keep the generated PDF")
    a = ap.parse_args()

    import pdf_inspector
    import render_pages

    if a.sweep:
        return sweep(a.pages, a.dpi)

    tmp = tempfile.mkdtemp(prefix="tokenbench-")
    pdf = os.path.join(tmp, f"report_{a.pages}p.pdf")
    build_report(pdf, a.pages, a.chars_per_page)

    d = pdf_inspector.detect_pdf(pdf)
    md = pdf_inspector.process_pdf(pdf).markdown or ""
    text_tok = count_text_tokens(md)

    rendered = render_pages.render(pdf, pages=[1], dpi=a.dpi, out_dir=tmp)
    from PIL import Image
    with Image.open(rendered[0][0]) as im:
        per_page_tok, dims = image_tokens(*im.size)
    image_tok = per_page_tok * a.pages

    print(f"document          : {a.pages} pages, {os.path.getsize(pdf) / 1024:.0f} KB")
    print(f"classification    : {d.pdf_type}, confidence {d.confidence:.2f}, "
          f"{d.processing_time_ms:.1f} ms")
    print(f"markdown          : {len(md):,} chars -> {text_tok:,} tokens")
    print(f"rendered @ {a.dpi} dpi : {dims[0]}x{dims[1]} px after clamp -> "
          f"{per_page_tok:,} tokens/page -> {image_tok:,} tokens")
    print()
    print(f"ratio             : {image_tok / max(text_tok, 1):.1f}x more context to read "
          f"the same document as images")
    print(f"saved by routing  : {image_tok - text_tok:,} tokens on this document")
    if not a.keep:
        for f in os.listdir(tmp):
            os.remove(os.path.join(tmp, f))
        os.rmdir(tmp)
    else:
        print(f"\nkept: {pdf}")


if __name__ == "__main__":
    main()
