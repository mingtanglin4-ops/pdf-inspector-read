---
name: pdf-inspector-read
description: "Use whenever the content inside a PDF is what is wanted: reading or summarizing it, finding a section, searching or grepping across a folder of PDFs, and pulling out tables, references, numbers, dates or fields into Markdown, CSV, BibTeX or plain text - one file or hundreds. Treat this as the default way to open any PDF, including scanned or image-only ones and PDFs whose copied text comes out as garbled mojibake. It classifies the text layer first, then routes each page to cheap Markdown extraction or to a visual read, so long documents do not burn context and broken fonts do not silently yield nonsense. Searching many PDFs needs this most: piping pdftotext into grep quietly skips every scanned file in the folder. Not for handling PDFs as files - merging, splitting, rotating, watermarking, encrypting, filling forms or generating one - this skill reads PDFs, it does not manipulate them as files."
---

# Reading PDFs with pdf-inspector

Two things go wrong when reading a PDF, and they pull in opposite directions.

Rendering every page as an image is always *safe* but costs a fixed ~2,300 tokens per page whatever the page holds, while the same page as text costs whatever its text costs. Measured on generated 40-page documents, images run about 2.8x the token cost of Markdown for a typical journal page, 5.7x for a sparse report and 14.5x for slides - real but not unlimited, and largest exactly where a page is sparse. Extracting text is cheap, but a PDF whose fonts lack a ToUnicode map returns confident-looking mojibake, and a scanned page returns nothing at all — failures that are easy to mistake for the document being empty or badly written.

`pdf-inspector` (Rust, MIT, by Firecrawl) resolves the dilemma by answering "is this text layer trustworthy?" in 1-50ms, before committing to either path. The classification itself costs single-digit milliseconds and no tokens, so it is worth doing even when the saving turns out small: the downside is bounded at nothing and the upside is a document you did not misread.

## The default path

```bash
python3 <skill-dir>/scripts/pdfread.py document.pdf
```

The script installs `pdf-inspector` if needed (prebuilt wheel, no Rust toolchain, ~5s), prints a verdict block, and then prints Markdown when the text layer is sound. Read the verdict before the text:

- `route: TEXT` — the Markdown that follows is the document. Work from it.
- `route: VISUAL` — the text layer is scanned, image-only, or broken. Before giving up on text the script retries with `pdftotext -layout`, because poppler reconstructs Unicode from a font's embedded CMap and so sometimes reads a page pdf-inspector calls garbled. If a `RECOVERED TEXT` block appears, that text is real and you can work from it (spacing-aligned, not Markdown tables). If it does not, render the pages and read them yourself — quoting the extracted text here would mean quoting mojibake.
- `route: MIXED` — the Markdown covers the sound pages; the listed pages still need a visual read.

Useful flags: `--pages 3,7-9` (1-indexed subset), `--per-page` (page-delimited output, good for long documents you want to work through section by section), `--detect-only` (verdict only), `--json` (verdict as JSON for scripting a batch), `--max-chars N` (truncate).

For a batch, loop `--detect-only --json` over the files first. Sorting into "extractable" and "needs eyes" up front is much cheaper than discovering it one document at a time, and it tells you immediately if a supposedly digital corpus is half scans.

## When to reach past the script

The script covers reading. Import the library directly when the task needs more than text:

```python
import pdf_inspector
r = pdf_inspector.process_pdf("doc.pdf")
r.markdown, r.pages_with_tables, r.is_complex_layout, r.title

pdf_inspector.extract_text_with_positions("doc.pdf")   # x/y/font per run — for layout, redaction, form geometry
pdf_inspector.extract_text_in_regions("doc.pdf", ...)  # crop a known region, e.g. a recurring header block
pdf_inspector.extract_structure_elements("doc.pdf")    # real heading roles from tagged PDFs; empty when untagged
```

A CLI exists too (`cargo install pdf-inspector` → `pdf2md doc.pdf --compact`), which is the right recommendation when a *user* wants to preprocess PDFs on their own machine before sending them along.

## What this does not do

Being explicit here matters, because the extraction looks clean enough that these gaps are easy to miss:

- **Math is flattened.** Formulas come out as loose characters with no LaTeX reconstruction. For a paper whose derivations matter, take the prose from Markdown and render the equation pages as images. Do not paraphrase an equation from extracted text.
- **Figures are not read.** Only placeholders survive. Any claim resting on what a chart shows needs the page rendered.
- **Tables are good, not perfect**, in two specific ways worth knowing before you trust one. Cells occasionally merge or shift a column, and a right-aligned column can come out ahead of the column it belongs to, so a price list renders as `[600,000] Built-in Cam` instead of `Built-in Cam [600,000]` — the pairing is right, the order is reversed. Detection also misses some tables entirely, so a page absent from `pages_with_tables` may still have one. When a table matters, `extract_text_with_positions` gives x/y per run and settles column order; before a number goes into an answer someone will act on, check it against the rendered page.
- **Drop caps** (oversized first letters) sometimes surface as a stray one-letter heading. Ignore those rather than treating them as structure.
- **Rendering has its own trap.** Use `python3 <skill-dir>/scripts/render_pages.py doc.pdf --pages 3` rather than reaching for `pdftoppm`. poppler needs language packs (Adobe-Japan1 and friends) to draw CJK, and without them it renders the page rules with no glyphs at all — a blank-looking page that reads as "this form was never filled in" rather than as a failure. The script uses pypdfium2 and prints an ink fraction per page, flagging a near-blank render so you notice the difference between an empty page and a broken one.
- **OCR is out of scope here.** The library has a selective-OCR path, but it needs external PDFium and ONNX Runtime libraries plus a model download. Reading the page visually is faster and usually better; only set up OCR if the user explicitly wants a searchable text layer produced.

The broken-encoding case is specifically a font with no `/ToUnicode` map. Embedding is not the issue and is easy to misdiagnose: a fully embedded, subsetted CJK font (`emb=yes sub=yes uni=no` in `pdffonts`) decodes to mojibake, while ordinary embedded fonts from LaTeX, Word, and LibreOffice exports extract cleanly, headings and tables included. If you explain the failure to a user, say the font lacks a Unicode mapping rather than guessing at embedding.

If `pdf-inspector` cannot be installed at all, fall back to `pdftotext -layout` and `pdfplumber`, and rasterize with `scripts/render_pages.py`. Creating, merging, splitting, watermarking or filling PDFs is out of scope here - reach for `pypdf` or `qpdf` instead.
