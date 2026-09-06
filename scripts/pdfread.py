#!/usr/bin/env python3
"""Classify a PDF, then extract Markdown or report which pages need visual reading.

Usage:
    python3 pdfread.py FILE.pdf                 # verdict + full Markdown
    python3 pdfread.py FILE.pdf --pages 3,4,5   # 1-indexed page subset
    python3 pdfread.py FILE.pdf --detect-only   # verdict only, no extraction
    python3 pdfread.py FILE.pdf --per-page      # Markdown split per page
    python3 pdfread.py FILE.pdf --json          # machine-readable verdict

Exit codes: 0 = text extracted, 2 = read these pages visually, 1 = error.

The decision helpers below (looks_like_text, decide_route, try_poppler,
parse_pages) are pure or dependency-injected so they can be tested without a
PDF; see tests/.
"""
import argparse, json, re, subprocess, sys, unicodedata as ud

# Tuned on a small hand-checked sample: mojibake from a broken CID font scores
# ~0.67 with ~33 words, real prose scores >0.95 with hundreds, and an
# image-only page yields a high ratio but almost no words. Widen these for a
# corpus of very short documents.
MIN_LETTER_RATIO = 0.85
MIN_WORDS = 40

WORD_RE = re.compile(r"[\w　-鿿＀-￯]{2,}")
KEEP_PUNCT = "。、，.,%()（）:：-—/"


def ensure_lib():
    """Import pdf-inspector, installing it on first use if necessary."""
    try:
        import pdf_inspector  # noqa: F401
        return
    except ImportError:
        pass
    for extra in (["--break-system-packages"], []):
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pdf-inspector"] + extra,
                           capture_output=True, text=True)
        if r.returncode == 0:
            return
    sys.stderr.write("pdf-inspector could not be installed. Fall back to pdftotext -layout "
                     "or pdfplumber, and rasterize with scripts/render_pages.py.\n")
    sys.exit(1)


def looks_like_text(t):
    """Tell real text apart from mojibake and from an empty scan.

    A font with no /ToUnicode map decodes to isolated symbols, so few
    characters land in a letter or digit category and almost nothing forms
    multi-character words. An image-only page yields the opposite shape: a
    clean ratio over a handful of characters. Requiring both a high ratio and
    a real word count separates all three.

    Returns (usable, ratio, word_count).
    """
    t = (t or "").strip()
    ns = [c for c in t if not c.isspace()]
    if not ns:
        return False, 0.0, 0
    good = sum(1 for c in ns if ud.category(c) in ("Lo", "Ll", "Lu", "Nd") or c in KEEP_PUNCT)
    words = len(WORD_RE.findall(t))
    ratio = good / len(ns)
    return (ratio >= MIN_LETTER_RATIO and words >= MIN_WORDS), round(ratio, 3), words


def decide_route(page_count, pages_needing_ocr, has_encoding_issues, wanted_pages=None):
    """Turn a classification into a routing decision. Pure.

    Returns (route, pages_needing_visual_read, scope) where route is one of
    TEXT (extract, do not rasterize), MIXED (extract the sound pages, look at
    the rest) or VISUAL (the text layer is not usable at all).

    A broken encoding outranks the per-page OCR list: pdf-inspector can report
    `has_encoding_issues` while still calling the document text-based, and in
    that case none of its text can be trusted.
    """
    scope = [int(p) for p in wanted_pages] if wanted_pages else list(range(1, (page_count or 0) + 1))
    ocr = set(pages_needing_ocr or ())
    if has_encoding_issues:
        return "VISUAL", list(scope), scope
    visual = sorted(p for p in scope if p in ocr)
    if scope and set(scope) <= ocr:
        return "VISUAL", visual, scope
    return ("MIXED" if visual else "TEXT"), visual, scope


def try_poppler(path, pages=None, runner=subprocess.run):
    """Ask poppler for the text pdf-inspector could not decode.

    poppler reconstructs Unicode from a font's embedded CMap rather than
    relying on /ToUnicode, so it sometimes reads a page pdf-inspector calls
    garbled. Cheap enough to always try before paying to rasterize.

    Returns (status, text) with status in {"ok", "missing", "failed"}.
    Distinguishing "missing" matters: poppler is not installed by default on
    Windows or macOS, and reporting that as "recovery failed" would hide the
    fact that installing it may well read the document.
    """
    cmd = ["pdftotext", "-layout"]
    if pages:
        cmd += ["-f", str(min(pages)), "-l", str(max(pages))]
    try:
        r = runner(cmd + [path, "-"], capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        return "missing", None
    except (OSError, subprocess.SubprocessError):
        return "failed", None
    if getattr(r, "returncode", 1) != 0:
        return "failed", None
    return "ok", r.stdout


def recovery_note(status, ratio, words):
    """The one-line explanation for a failed recovery attempt. Pure."""
    if status == "missing":
        return ("(pdftotext is not installed, so the poppler recovery path was skipped -- "
                "installing poppler-utils may well read this document)")
    if status == "failed":
        return "(pdftotext failed on this file)"
    return f"(pdftotext ran but its output is unusable too: letter-ratio {ratio}, {words} words)"


def parse_pages(spec):
    """Parse a 1-indexed page spec like '1,3,5-9'. Pure. None means 'all'."""
    if not spec:
        return None
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def _attempt_recovery(path, pages, max_chars, enabled):
    """Try poppler; print either the recovered text or why it did not work.

    Returns True when text was recovered and printed.
    """
    if not enabled:
        print("(recovery disabled with --no-fallback)")
        return False
    status, alt = try_poppler(path, pages)
    ok, ratio, words = looks_like_text(alt)
    if ok:
        print(f"\n=== RECOVERED TEXT (pdftotext -layout; letter-ratio {ratio}, "
              f"{words} words) ===")
        print("pdf-inspector could not decode this font, but poppler could. "
              "Layout is preserved as spacing, not as Markdown tables.")
        print(alt[:max_chars] if max_chars else alt)
        return True
    print(recovery_note(status, ratio, words))
    return False


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--pages", help="1-indexed, e.g. 1,3,5-9")
    ap.add_argument("--detect-only", action="store_true")
    ap.add_argument("--per-page", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--max-chars", type=int, default=0, help="truncate Markdown output")
    ap.add_argument("--no-fallback", action="store_true", help="skip the pdftotext recovery attempt")
    a = ap.parse_args(argv)

    ensure_lib()
    import pdf_inspector

    d = pdf_inspector.detect_pdf(a.pdf)
    want = parse_pages(a.pages)
    broken = bool(getattr(d, "has_encoding_issues", False))
    route, visual, scope = decide_route(d.page_count, d.pages_needing_ocr, broken, want)
    ocr = set(d.pages_needing_ocr or ())

    verdict = {
        "file": a.pdf, "pdf_type": d.pdf_type, "confidence": round(d.confidence, 3),
        "page_count": d.page_count, "has_encoding_issues": broken,
        "pages_needing_visual_read": visual, "route": route,
    }
    if a.json:
        print(json.dumps(verdict, ensure_ascii=False))
    else:
        print("=== VERDICT ===")
        for k, v in verdict.items():
            print(f"{k}: {v}")
        if route == "VISUAL" and not a.no_fallback:
            print("\nThe pdf-inspector text layer is unusable here; trying poppler before "
                  "falling back to a visual read.")
        elif route == "MIXED":
            print(f"\nText below covers the clean pages. Pages {visual} still need a visual read.")
    if a.detect_only:
        return 0

    if route == "VISUAL":
        if _attempt_recovery(a.pdf, visual, a.max_chars, not a.no_fallback):
            return 0
        print("Render the pages with scripts/render_pages.py and read the images.")
        return 2

    print("\n=== MARKDOWN ===")
    if a.per_page or want:
        idx = [p - 1 for p in scope if p not in ocr]
        res = pdf_inspector.extract_pages_markdown(a.pdf, pages=idx) if idx else None
        for p in (res.pages if res else []):
            print(f"\n<!-- page {p.page + 1} -->")
            print(p.markdown)
    else:
        r = pdf_inspector.process_pdf(a.pdf)
        md = r.markdown or ""
        if r.has_encoding_issues or not md.strip():
            # detect_pdf can miss a broken CID font that full extraction catches.
            if _attempt_recovery(a.pdf, None, a.max_chars, not a.no_fallback):
                return 0
            print("No usable text: the font carries no ToUnicode map. Render the pages "
                  "with scripts/render_pages.py.")
            return 2
        if r.pages_with_tables:
            print(f"<!-- tables detected on pages {list(r.pages_with_tables)}; detection "
                  f"misses some tables and can swap right-aligned columns, so verify any "
                  f"number you rely on against the rendered page -->")
        print(md[:a.max_chars] if a.max_chars else md)
    return 0 if route == "TEXT" else 2


if __name__ == "__main__":
    sys.exit(main())
