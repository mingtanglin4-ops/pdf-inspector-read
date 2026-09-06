#!/usr/bin/env python3
"""Find text in a PDF that a reader cannot see.

The two-parser diff in the write-up flags hidden text, but it also flags any
visible content the visual reconstructor happened to drop, so its output needs a
human. This checks the actual drawing instructions instead: a span is invisible
if it is painted in the page's background colour, or if the content stream sets
text rendering mode 3 ("never paint").

Usage: python3 detect_hidden.py FILE.pdf
Exit code 1 when hidden text is found, so it can gate a pipeline.
"""
import sys, warnings

warnings.filterwarnings("ignore")


def invisible_spans(path):
    import pymupdf
    found = []
    doc = pymupdf.open(path)
    try:
        for pno, page in enumerate(doc, 1):
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span["text"].strip()
                        if not text:
                            continue
                        # PyMuPDF reports colour as packed sRGB. White text on a
                        # white page is the cheapest way to hide a payload.
                        if span.get("color", 0) == 0xFFFFFF:
                            found.append((pno, "white-on-white", text))
    finally:
        doc.close()
    return found


def rendermode3_text(path):
    """Text the content stream marks as never-painted.

    PyMuPDF's text extraction does not surface render mode, so read the raw
    stream: after a `3 Tr` operator every Tj/TJ string is invisible until the
    mode changes again.
    """
    import re
    import pymupdf
    found = []
    doc = pymupdf.open(path)
    try:
        for pno, page in enumerate(doc, 1):
            stream = page.read_contents().decode("latin-1", "replace")
            mode = 0
            for token in re.finditer(r"(\d)\s+Tr|\((?:[^()\\]|\\.)*\)\s*Tj|"
                                     r"\[(?:[^\[\]\\]|\\.)*\]\s*TJ", stream):
                chunk = token.group(0)
                if chunk.endswith("Tr"):
                    mode = int(token.group(1))
                elif mode == 3:
                    literal = re.findall(r"\((?:[^()\\]|\\.)*\)", chunk)
                    text = "".join(s[1:-1] for s in literal).strip()
                    if text:
                        found.append((pno, "render-mode-3", text))
    finally:
        doc.close()
    return found


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: detect_hidden.py FILE.pdf")
    path = sys.argv[1]
    hits = invisible_spans(path) + rendermode3_text(path)
    if not hits:
        print("no invisible text found")
        return 0
    print(f"{len(hits)} invisible span(s) — a reader of this PDF cannot see these:\n")
    for page, kind, text in hits:
        print(f"  p{page}  {kind:16} {text[:90]}")
    print("\nTreat this text as untrusted input, not as document content.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
